
import os
import csv
import io
import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

import oracledb
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort, make_response
)
from werkzeug.security import check_password_hash

from db import get_connection

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY is missing from .env")

# Session-bound CSRF token: all HTML forms receive the token from _effects.html.
@app.context_processor
def inject_template_security():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["csrf_token"]}

@app.before_request
def protect_post_requests():
    if request.method == "POST":
        expected = session.get("csrf_token")
        supplied = request.form.get("csrf_token", "")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400, description="Your form session expired. Refresh the page and try again.")

@app.after_request
def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

def log_audit(action, entity_type, entity_id=None, details=None):
    """Write an audit entry without allowing audit failures to break a user action."""
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """INSERT INTO audit_logs (audit_id, user_id, username, action,
                   entity_type, entity_id, details, created_at)
               VALUES (audit_logs_seq.NEXTVAL, :uid, :username, :action,
                   :entity_type, :entity_id, :details, CURRENT_TIMESTAMP)""",
            {"uid": session.get("user_id"), "username": session.get("username", "unknown"),
             "action": action[:50], "entity_type": entity_type[:50],
             "entity_id": str(entity_id)[:50] if entity_id is not None else None,
             "details": details[:1000] if details else None},
        )
        connection.commit()
    except Exception:
        app.logger.warning("Audit log insert failed; apply schema_extensions.sql", exc_info=True)
        if connection:
            connection.rollback()
    finally:
        close_db(cursor, connection)

def require_admin():
    if session.get("role") != "ADMIN":
        abort(403)


def login_required():
    if "user_id" not in session:
        flash("Please log in to continue.", "warning")
        return False
    return True


def valid_birth_date(value):
    if not value:
        return None
    parsed = date.fromisoformat(value)
    if parsed > date.today():
        raise ValueError("Date of birth cannot be in the future.")
    return parsed


def close_db(cursor, connection):
    if cursor:
        cursor.close()
    if connection:
        connection.close()


# ==================================================
# LOGIN
# ==================================================

@app.route("/", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Enter both username and password.", "error")
            return render_template("login.html")

        connection = cursor = None
        try:
            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT user_id, username, password_hash, role
                FROM users
                WHERE username = :username
                """,
                {"username": username},
            )
            user = cursor.fetchone()

            if user and check_password_hash(user[2], password):
                session.clear()
                session["user_id"] = user[0]
                session["username"] = user[1]
                session["role"] = user[3]
                return redirect(url_for("dashboard"))

            flash("Invalid username or password.", "error")

        except Exception:
            app.logger.exception("Login failed")
            flash("Unable to log in. Check the database connection.", "error")
        finally:
            close_db(cursor, connection)

    return render_template("login.html")


# ==================================================
# DASHBOARD
# ==================================================

@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))

    stats = {
        "total_patients": 0,
        "total_doctors": 0,
        "today_appointments": 0,
    }

    upcoming_appointments = []
    appointment_statuses = []
    monthly_trend = []
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM patients")
        stats["total_patients"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM doctors")
        stats["total_doctors"] = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM appointments
            WHERE appointment_date >= TRUNC(SYSDATE)
              AND appointment_date < TRUNC(SYSDATE) + 1
              AND status = 'BOOKED'
            """
        )
        stats["today_appointments"] = cursor.fetchone()[0]

        cursor.execute(
            """SELECT a.appointment_id, p.full_name, d.full_name,
                      d.specialization, a.appointment_date, a.reason, a.status
               FROM appointments a JOIN patients p ON p.patient_id=a.patient_id
               JOIN doctors d ON d.doctor_id=a.doctor_id
               WHERE a.appointment_date >= SYSDATE AND a.status='BOOKED'
               ORDER BY a.appointment_date"""
        )
        upcoming_appointments = cursor.fetchall()[:5]
        cursor.execute("SELECT status, COUNT(*) FROM appointments GROUP BY status")
        appointment_statuses = cursor.fetchall()
        cursor.execute("""SELECT TO_CHAR(appointment_date, 'YYYY-MM') month_key,
                                 COUNT(*) total
                          FROM appointments
                          WHERE appointment_date >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -5)
                          GROUP BY TO_CHAR(appointment_date, 'YYYY-MM')
                          ORDER BY month_key""")
        monthly_trend = cursor.fetchall()

    except Exception:
        app.logger.exception("Dashboard statistics query failed")
        flash("Could not load all dashboard statistics.", "error")
    finally:
        close_db(cursor, connection)

    return render_template(
        "dashboard.html",
        stats=stats,
        username=session.get("username", "User"),
        role=session.get("role", "STAFF"),
        upcoming_appointments=upcoming_appointments,
        appointment_statuses=appointment_statuses,
        monthly_trend=monthly_trend,
    )


# ==================================================
# PATIENTS: LIST, SEARCH, REGISTER
# ==================================================

@app.route("/patients", methods=["GET", "POST"])
def patients():
    if not login_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        dob_text = request.form.get("date_of_birth", "").strip()
        gender = request.form.get("gender", "").strip() or None
        phone = request.form.get("phone", "").strip() or None
        address = request.form.get("address", "").strip() or None

        if not full_name or len(full_name) > 100:
            flash("Patient name is required and must be at most 100 characters.", "error")
            return redirect(url_for("patients"))

        if gender not in (None, "Male", "Female", "Other"):
            flash("Select a valid gender.", "error")
            return redirect(url_for("patients"))

        try:
            dob = valid_birth_date(dob_text)
        except ValueError:
            flash("Enter a valid date of birth that is not in the future.", "error")
            return redirect(url_for("patients"))

        connection = cursor = None
        try:
            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO patients
                    (patient_id, full_name, date_of_birth,
                     gender, phone, address)
                VALUES
                    (patients_seq.NEXTVAL, :full_name, :dob,
                     :gender, :phone, :address)
                """,
                {
                    "full_name": full_name,
                    "dob": dob,
                    "gender": gender,
                    "phone": phone,
                    "address": address,
                },
            )
            connection.commit()
            log_audit("CREATE", "PATIENT", details=f"Registered patient: {full_name}")
            flash("Patient registered successfully.", "success")
        except Exception:
            if connection:
                connection.rollback()
            app.logger.exception("Patient registration failed")
            flash("Could not register the patient.", "error")
        finally:
            close_db(cursor, connection)

        return redirect(url_for("patients"))

    search_query = request.args.get("search", "").strip()
    patient_rows = []
    connection = cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        if search_query:
            pattern = f"%{search_query}%"
            cursor.execute(
                """
                SELECT patient_id, full_name, date_of_birth,
                       gender, phone, address
                FROM patients
                WHERE LOWER(full_name) LIKE LOWER(:name_search)
                   OR phone LIKE :phone_search
                ORDER BY patient_id DESC
                """,
                {"name_search": pattern, "phone_search": pattern},
            )
        else:
            cursor.execute(
                """
                SELECT patient_id, full_name, date_of_birth,
                       gender, phone, address
                FROM patients
                ORDER BY patient_id DESC
                """
            )

        patient_rows = cursor.fetchall()
    except Exception:
        app.logger.exception("Patient retrieval failed")
        flash("Could not load patient records.", "error")
    finally:
        close_db(cursor, connection)

    return render_template(
        "patients.html",
        patients=patient_rows,
        search_query=search_query,
        today=date.today().isoformat(),
    )


# ==================================================
# PATIENTS: EDIT
# ==================================================

@app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
def edit_patient(patient_id):
    if not login_required():
        return redirect(url_for("login"))

    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            dob_text = request.form.get("date_of_birth", "").strip()
            gender = request.form.get("gender", "").strip() or None
            phone = request.form.get("phone", "").strip() or None
            address = request.form.get("address", "").strip() or None

            if not full_name or len(full_name) > 100:
                flash("Enter a patient name of 1–100 characters.", "error")
                return redirect(url_for("edit_patient", patient_id=patient_id))

            if gender not in (None, "Male", "Female", "Other"):
                flash("Select a valid gender.", "error")
                return redirect(url_for("edit_patient", patient_id=patient_id))

            try:
                dob = valid_birth_date(dob_text)
            except ValueError:
                flash("Enter a valid date of birth that is not in the future.", "error")
                return redirect(url_for("edit_patient", patient_id=patient_id))

            cursor.execute(
                """
                UPDATE patients
                SET full_name = :full_name,
                    date_of_birth = :dob,
                    gender = :gender,
                    phone = :phone,
                    address = :address
                WHERE patient_id = :patient_id
                """,
                {
                    "full_name": full_name,
                    "dob": dob,
                    "gender": gender,
                    "phone": phone,
                    "address": address,
                    "patient_id": patient_id,
                },
            )

            if cursor.rowcount == 0:
                connection.rollback()
                abort(404)

            connection.commit()
            log_audit("UPDATE", "PATIENT", patient_id, f"Updated patient: {full_name}")
            flash("Patient details updated successfully.", "success")
            return redirect(url_for("patients"))

        cursor.execute(
            """
            SELECT patient_id, full_name, date_of_birth,
                   gender, phone, address
            FROM patients
            WHERE patient_id = :patient_id
            """,
            {"patient_id": patient_id},
        )
        patient = cursor.fetchone()

        if patient is None:
            abort(404)

        return render_template("edit_patient.html", patient=patient)

    finally:
        close_db(cursor, connection)


# ==================================================
# PATIENTS: DELETE
# ==================================================

@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
def delete_patient(patient_id):
    if not login_required():
        return redirect(url_for("login"))

    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM patients WHERE patient_id = :patient_id",
            {"patient_id": patient_id},
        )

        if cursor.rowcount == 0:
            connection.rollback()
            flash("Patient record was not found.", "error")
        else:
            connection.commit()
            log_audit("DELETE", "PATIENT", patient_id, "Deleted patient record")
            flash("Patient deleted successfully.", "success")

    except oracledb.IntegrityError:
        if connection:
            connection.rollback()
        flash("This patient has appointments and cannot be deleted.", "error")
    except Exception:
        if connection:
            connection.rollback()
        app.logger.exception("Patient deletion failed")
        flash("Could not delete the patient.", "error")
    finally:
        close_db(cursor, connection)

    return redirect(url_for("patients"))


# ==================================================
# DOCTORS: LIST, SEARCH, REGISTER
# ==================================================

@app.route("/doctors", methods=["GET", "POST"])
def doctors():
    if not login_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        specialization = request.form.get("specialization", "").strip()
        phone = request.form.get("phone", "").strip() or None
        fee_text = request.form.get("consultation_fee", "").strip()

        if not full_name or len(full_name) > 100:
            flash("Doctor name is required and must be at most 100 characters.", "error")
            return redirect(url_for("doctors"))

        if not specialization or len(specialization) > 100:
            flash("Specialization is required and must be at most 100 characters.", "error")
            return redirect(url_for("doctors"))

        fee = None
        if fee_text:
            try:
                fee = Decimal(fee_text)
                if not fee.is_finite() or fee < 0 or fee > Decimal("99999999.99"):
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                flash("Enter a valid non-negative consultation fee.", "error")
                return redirect(url_for("doctors"))

        connection = cursor = None
        try:
            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO doctors
                    (doctor_id, full_name, specialization,
                     phone, consultation_fee)
                VALUES
                    (doctors_seq.NEXTVAL, :full_name, :specialization,
                     :phone, :fee)
                """,
                {
                    "full_name": full_name,
                    "specialization": specialization,
                    "phone": phone,
                    "fee": fee,
                },
            )
            connection.commit()
            log_audit("CREATE", "DOCTOR", details=f"Registered doctor: {full_name}")
            flash("Doctor registered successfully.", "success")
        except Exception:
            if connection:
                connection.rollback()
            app.logger.exception("Doctor registration failed")
            flash("Could not register the doctor.", "error")
        finally:
            close_db(cursor, connection)

        return redirect(url_for("doctors"))

    search_query = request.args.get("search", "").strip()
    doctor_rows = []
    connection = cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        if search_query:
            pattern = f"%{search_query}%"
            cursor.execute(
                """
                SELECT doctor_id, full_name, specialization,
                       phone, consultation_fee
                FROM doctors
                WHERE LOWER(full_name) LIKE LOWER(:name_search)
                   OR LOWER(specialization) LIKE LOWER(:specialty_search)
                ORDER BY doctor_id DESC
                """,
                {"name_search": pattern, "specialty_search": pattern},
            )
        else:
            cursor.execute(
                """
                SELECT doctor_id, full_name, specialization,
                       phone, consultation_fee
                FROM doctors
                ORDER BY doctor_id DESC
                """
            )

        doctor_rows = cursor.fetchall()
    except Exception:
        app.logger.exception("Doctor retrieval failed")
        flash("Could not load doctor records.", "error")
    finally:
        close_db(cursor, connection)

    return render_template(
        "doctors.html",
        doctors=doctor_rows,
        search_query=search_query,
    )


# ==================================================
# DOCTORS: EDIT
# ==================================================

@app.route("/doctors/<int:doctor_id>/edit", methods=["GET", "POST"])
def edit_doctor(doctor_id):
    if not login_required():
        return redirect(url_for("login"))

    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            specialization = request.form.get("specialization", "").strip()
            phone = request.form.get("phone", "").strip() or None
            fee_text = request.form.get("consultation_fee", "").strip()

            if not full_name or len(full_name) > 100:
                flash("Enter a doctor name of 1–100 characters.", "error")
                return redirect(url_for("edit_doctor", doctor_id=doctor_id))

            if not specialization or len(specialization) > 100:
                flash("Enter a specialization of 1–100 characters.", "error")
                return redirect(url_for("edit_doctor", doctor_id=doctor_id))

            fee = None
            if fee_text:
                try:
                    fee = Decimal(fee_text)
                    if not fee.is_finite() or fee < 0 or fee > Decimal("99999999.99"):
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    flash("Enter a valid non-negative consultation fee.", "error")
                    return redirect(url_for("edit_doctor", doctor_id=doctor_id))

            cursor.execute(
                """
                UPDATE doctors
                SET full_name = :full_name,
                    specialization = :specialization,
                    phone = :phone,
                    consultation_fee = :fee
                WHERE doctor_id = :doctor_id
                """,
                {
                    "full_name": full_name,
                    "specialization": specialization,
                    "phone": phone,
                    "fee": fee,
                    "doctor_id": doctor_id,
                },
            )

            if cursor.rowcount == 0:
                connection.rollback()
                abort(404)

            connection.commit()
            log_audit("UPDATE", "DOCTOR", doctor_id, f"Updated doctor: {full_name}")
            flash("Doctor details updated successfully.", "success")
            return redirect(url_for("doctors"))

        cursor.execute(
            """
            SELECT doctor_id, full_name, specialization,
                   phone, consultation_fee
            FROM doctors
            WHERE doctor_id = :doctor_id
            """,
            {"doctor_id": doctor_id},
        )
        doctor = cursor.fetchone()

        if doctor is None:
            abort(404)

        return render_template("edit_doctor.html", doctor=doctor)

    finally:
        close_db(cursor, connection)


# ==================================================
# DOCTORS: DELETE
# ==================================================

@app.route("/doctors/<int:doctor_id>/delete", methods=["POST"])
def delete_doctor(doctor_id):
    if not login_required():
        return redirect(url_for("login"))

    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM doctors WHERE doctor_id = :doctor_id",
            {"doctor_id": doctor_id},
        )

        if cursor.rowcount == 0:
            connection.rollback()
            flash("Doctor record was not found.", "error")
        else:
            connection.commit()
            log_audit("DELETE", "DOCTOR", doctor_id, "Deleted doctor record")
            flash("Doctor deleted successfully.", "success")

    except oracledb.IntegrityError:
        if connection:
            connection.rollback()
        flash("This doctor has appointments and cannot be deleted.", "error")
    except Exception:
        if connection:
            connection.rollback()
        app.logger.exception("Doctor deletion failed")
        flash("Could not delete the doctor.", "error")
    finally:
        close_db(cursor, connection)

    return redirect(url_for("doctors"))


# ==================================================
# APPOINTMENTS: LIST, SEARCH, BOOK
# ==================================================

@app.route("/appointments", methods=["GET", "POST"])
def appointments():
    if not login_required():
        return redirect(url_for("login"))

    connection = cursor = None

    if request.method == "POST":
        patient_text = request.form.get("patient_id", "").strip()
        doctor_text = request.form.get("doctor_id", "").strip()
        date_text = request.form.get("appointment_date", "").strip()
        reason = request.form.get("reason", "").strip() or None

        try:
            patient_id = int(patient_text)
            doctor_id = int(doctor_text)
            appointment_datetime = datetime.strptime(
                date_text, "%Y-%m-%dT%H:%M"
            )

            if appointment_datetime <= datetime.now():
                flash("Choose an appointment date and time in the future.", "error")
                return redirect(url_for("appointments"))

            if reason and len(reason) > 500:
                flash("The appointment reason must be 500 characters or fewer.", "error")
                return redirect(url_for("appointments"))

        except (ValueError, TypeError):
            flash("Enter valid patient, doctor, date, and time details.", "error")
            return redirect(url_for("appointments"))

        try:
            connection = get_connection()
            cursor = connection.cursor()

            # Check that both selected records exist.
            cursor.execute(
                "SELECT COUNT(*) FROM patients WHERE patient_id = :pid",
                {"pid": patient_id},
            )
            if cursor.fetchone()[0] == 0:
                flash("The selected patient does not exist.", "error")
                return redirect(url_for("appointments"))

            cursor.execute(
                "SELECT COUNT(*) FROM doctors WHERE doctor_id = :did",
                {"did": doctor_id},
            )
            if cursor.fetchone()[0] == 0:
                flash("The selected doctor does not exist.", "error")
                return redirect(url_for("appointments"))

            # Enforce configured doctor availability when schedules exist.
            cursor.execute("SELECT COUNT(*) FROM doctor_availability WHERE doctor_id=:did AND day_of_week=:dow AND is_available='Y' AND start_time <= :start_time AND end_time > :start_time",
                           {"did": doctor_id, "dow": appointment_datetime.weekday(), "start_time": appointment_datetime.strftime("%H:%M")})
            availability_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM doctor_availability WHERE doctor_id=:did", {"did": doctor_id})
            schedule_exists = cursor.fetchone()[0] > 0
            if schedule_exists and availability_count == 0:
                flash("The selected doctor is not available at that day and time. Check the availability schedule.", "error")
                return redirect(url_for("appointments"))

            # Appointments are treated as 30-minute slots to prevent overlaps.
            cursor.execute("""SELECT COUNT(*) FROM appointments
                              WHERE doctor_id=:did AND status='BOOKED'
                                AND appointment_date < :slot_end
                                AND appointment_date + (30/1440) > :slot_start""",
                           {"did": doctor_id, "slot_start": appointment_datetime,
                            "slot_end": appointment_datetime + timedelta(minutes=30)})
            if cursor.fetchone()[0] > 0:
                flash("This doctor already has a booking that overlaps this 30-minute slot.", "error")
                return redirect(url_for("appointments"))

            # Oracle DATE stores both the date and time.
            cursor.execute(
                """
                INSERT INTO appointments
                    (appointment_id, patient_id, doctor_id,
                     appointment_date, reason, status)
                VALUES
                    (appointments_seq.NEXTVAL, :patient_id, :doctor_id,
                     :appointment_date, :reason, 'BOOKED')
                """,
                {
                    "patient_id": patient_id,
                    "doctor_id": doctor_id,
                    "appointment_date": appointment_datetime,
                    "reason": reason,
                },
            )

            connection.commit()
            log_audit("CREATE", "APPOINTMENT", details=f"Patient {patient_id}, doctor {doctor_id}, {appointment_datetime:%Y-%m-%d %H:%M}")
            flash("Appointment booked successfully.", "success")

        except oracledb.IntegrityError as exc:
            if connection:
                connection.rollback()

            error_text = str(exc).upper()
            if "ORA-00001" in error_text:
                flash(
                    "This doctor already has an appointment at that exact date and time.",
                    "error",
                )
            elif "ORA-02291" in error_text:
                flash("The selected patient or doctor no longer exists.", "error")
            else:
                app.logger.exception("Appointment booking constraint error")
                flash("The appointment could not be booked because of a database constraint.", "error")

        except Exception:
            if connection:
                connection.rollback()
            app.logger.exception("Appointment booking failed")
            flash("Could not book the appointment.", "error")

        finally:
            close_db(cursor, connection)

        return redirect(url_for("appointments"))

    # Retrieve patient and doctor options for the booking form.
    patient_options = []
    doctor_options = []
    appointment_rows = []
    search_query = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip().upper()
    if status_filter not in {"", "BOOKED", "COMPLETED", "CANCELLED"}:
        status_filter = ""

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT patient_id, full_name FROM patients ORDER BY full_name"
        )
        patient_options = cursor.fetchall()

        cursor.execute(
            """
            SELECT doctor_id, full_name, specialization
            FROM doctors
            ORDER BY full_name
            """
        )
        doctor_options = cursor.fetchall()

        base_query = """
            SELECT a.appointment_id,
                   p.full_name,
                   d.full_name,
                   d.specialization,
                   a.appointment_date,
                   a.reason,
                   a.status
            FROM appointments a
            JOIN patients p ON p.patient_id = a.patient_id
            JOIN doctors d ON d.doctor_id = a.doctor_id
        """

        if search_query:
            pattern = f"%{search_query}%"
            cursor.execute(
                base_query
                + """
                WHERE (LOWER(p.full_name) LIKE LOWER(:patient_search)
                   OR LOWER(d.full_name) LIKE LOWER(:doctor_search))
                   AND (:status_filter IS NULL OR a.status = :status_filter)
                ORDER BY a.appointment_date DESC
                """,
                {
                    "patient_search": pattern,
                    "doctor_search": pattern,
                    "status_filter": status_filter or None,
                },
            )
        else:
            cursor.execute(
                base_query + " WHERE (:status_filter IS NULL OR a.status = :status_filter) ORDER BY a.appointment_date DESC",
                {"status_filter": status_filter or None},
            )

        appointment_rows = cursor.fetchall()

    except Exception:
        app.logger.exception("Appointment retrieval failed")
        flash("Could not load appointment information.", "error")
    finally:
        close_db(cursor, connection)

    calendar_events = []
    for row in appointment_rows:
        if row[4]:
            calendar_events.append({
                "id": str(row[0]),
                "title": f"{row[1]} · {row[2]}",
                "start": row[4].isoformat(),
                "url": url_for("appointments") + "#appointment-" + str(row[0]),
                "extendedProps": {"status": row[6], "reason": row[5] or "", "doctor": row[2]},
            })

    return render_template(
        "appointments.html",
        patients=patient_options,
        doctors=doctor_options,
        appointments=appointment_rows,
        calendar_events=calendar_events,
        search_query=search_query,
        status_filter=status_filter,
        now=datetime.now().strftime("%Y-%m-%dT%H:%M"),
    )


# ==================================================
# APPOINTMENTS: UPDATE STATUS
# ==================================================

@app.route(
    "/appointments/<int:appointment_id>/status",
    methods=["POST"],
)
def update_appointment_status(appointment_id):
    if not login_required():
        return redirect(url_for("login"))

    new_status = request.form.get("status", "").strip().upper()
    allowed_statuses = {"BOOKED", "COMPLETED", "CANCELLED"}

    if new_status not in allowed_statuses:
        flash("Invalid appointment status.", "error")
        return redirect(url_for("appointments"))

    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE appointments
            SET status = :status
            WHERE appointment_id = :appointment_id
            """,
            {
                "status": new_status,
                "appointment_id": appointment_id,
            },
        )

        if cursor.rowcount == 0:
            connection.rollback()
            flash("Appointment was not found.", "error")
        else:
            connection.commit()
            log_audit("STATUS_CHANGE", "APPOINTMENT", appointment_id, f"Status changed to {new_status}")
            flash("Appointment status updated.", "success")

    except Exception:
        if connection:
            connection.rollback()
        app.logger.exception("Appointment status update failed")
        flash("Could not update the appointment status.", "error")
    finally:
        close_db(cursor, connection)

    return redirect(url_for("appointments"))


# ==================================================
# PATIENT MEDICAL RECORDS / VISITS
# ==================================================

@app.route("/patients/<int:patient_id>/records", methods=["GET", "POST"])
def patient_records(patient_id):
    if not login_required():
        return redirect(url_for("login"))
    connection = cursor = None
    try:
        connection = get_connection(); cursor = connection.cursor()
        cursor.execute("SELECT patient_id, full_name, date_of_birth, gender, phone, address FROM patients WHERE patient_id=:pid", {"pid": patient_id})
        patient = cursor.fetchone()
        if not patient: abort(404)
        if request.method == "POST":
            visit_date_text = request.form.get("visit_date", "").strip()
            diagnosis = request.form.get("diagnosis", "").strip()
            notes = request.form.get("notes", "").strip() or None
            prescription = request.form.get("prescription", "").strip() or None
            try:
                visit_date = datetime.strptime(visit_date_text, "%Y-%m-%dT%H:%M")
                if visit_date > datetime.now(): raise ValueError
                if not diagnosis or len(diagnosis) > 250 or (notes and len(notes)>2000) or (prescription and len(prescription)>2000): raise ValueError
            except ValueError:
                flash("Enter a valid visit date (not in the future), diagnosis, and notes within the allowed lengths.", "error")
                return redirect(url_for("patient_records", patient_id=patient_id))
            cursor.execute("""INSERT INTO medical_records (record_id, patient_id, visit_date, diagnosis, notes, prescription, created_by)
                              VALUES (medical_records_seq.NEXTVAL, :pid, :visit_date, :diagnosis, :notes, :prescription, :username)""",
                           {"pid": patient_id, "visit_date": visit_date, "diagnosis": diagnosis, "notes": notes, "prescription": prescription, "username": session.get("username")})
            connection.commit(); log_audit("CREATE", "MEDICAL_RECORD", patient_id, f"Added visit record for patient {patient_id}")
            flash("Visit record saved.", "success")
            return redirect(url_for("patient_records", patient_id=patient_id))
        cursor.execute("SELECT record_id, visit_date, diagnosis, notes, prescription, created_by FROM medical_records WHERE patient_id=:pid ORDER BY visit_date DESC", {"pid": patient_id})
        records = cursor.fetchall()
        return render_template("patient_records.html", patient=patient, records=records, now=datetime.now().strftime("%Y-%m-%dT%H:%M"))
    finally:
        close_db(cursor, connection)

# ==================================================
# DOCTOR AVAILABILITY
# ==================================================

@app.route("/availability", methods=["GET", "POST"])
def availability():
    if not login_required(): return redirect(url_for("login"))
    connection = cursor = None
    try:
        connection = get_connection(); cursor = connection.cursor()
        if request.method == "POST":
            try:
                doctor_id = int(request.form.get("doctor_id", ""))
                day = int(request.form.get("day_of_week", "-1"))
                start_time = request.form.get("start_time", "")
                end_time = request.form.get("end_time", "")
                datetime.strptime(start_time, "%H:%M"); datetime.strptime(end_time, "%H:%M")
                if day not in range(7) or start_time >= end_time: raise ValueError
            except (ValueError, TypeError):
                flash("Choose a doctor, weekday, and valid start/end times.", "error")
                return redirect(url_for("availability"))
            cursor.execute("SELECT COUNT(*) FROM doctors WHERE doctor_id=:did", {"did": doctor_id})
            if cursor.fetchone()[0] == 0:
                flash("Selected doctor does not exist.", "error"); return redirect(url_for("availability"))
            cursor.execute("""INSERT INTO doctor_availability (availability_id, doctor_id, day_of_week, start_time, end_time, is_available)
                              VALUES (doctor_availability_seq.NEXTVAL, :did, :day, :start_time, :end_time, 'Y')""",
                           {"did": doctor_id, "day": day, "start_time": start_time, "end_time": end_time})
            connection.commit(); log_audit("CREATE", "AVAILABILITY", doctor_id, f"Added weekday {day} {start_time}-{end_time}")
            flash("Doctor availability added.", "success")
            return redirect(url_for("availability"))
        cursor.execute("SELECT doctor_id, full_name, specialization FROM doctors ORDER BY full_name"); doctors = cursor.fetchall()
        cursor.execute("SELECT av.availability_id, d.full_name, d.specialization, av.day_of_week, av.start_time, av.end_time, av.is_available FROM doctor_availability av JOIN doctors d ON d.doctor_id=av.doctor_id ORDER BY d.full_name, av.day_of_week, av.start_time")
        schedules = cursor.fetchall()
        return render_template("availability.html", doctors=doctors, schedules=schedules, days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])
    finally: close_db(cursor, connection)

@app.route("/availability/<int:availability_id>/delete", methods=["POST"])
def delete_availability(availability_id):
    if not login_required(): return redirect(url_for("login"))
    connection = cursor = None
    try:
        connection=get_connection(); cursor=connection.cursor()
        cursor.execute("DELETE FROM doctor_availability WHERE availability_id=:aid", {"aid": availability_id})
        if cursor.rowcount: connection.commit(); log_audit("DELETE", "AVAILABILITY", availability_id); flash("Availability slot deleted.", "success")
        else: connection.rollback(); flash("Availability slot not found.", "error")
    except Exception:
        if connection: connection.rollback()
        app.logger.exception("Availability deletion failed"); flash("Could not delete availability slot.", "error")
    finally: close_db(cursor, connection)
    return redirect(url_for("availability"))

# ==================================================
# BILLING / INVOICES
# ==================================================

@app.route("/billing", methods=["GET", "POST"])
def billing():
    if not login_required(): return redirect(url_for("login"))
    connection = cursor = None
    try:
        connection=get_connection(); cursor=connection.cursor()
        if request.method == "POST":
            try:
                appointment_id=int(request.form.get("appointment_id", ""))
                amount=Decimal(request.form.get("amount", ""))
                if not amount.is_finite() or amount < 0 or amount > Decimal("99999999.99"): raise ValueError
            except (ValueError, InvalidOperation):
                flash("Enter a valid appointment and non-negative amount.", "error"); return redirect(url_for("billing"))
            cursor.execute("SELECT COUNT(*) FROM appointments WHERE appointment_id=:aid", {"aid": appointment_id})
            if cursor.fetchone()[0] == 0:
                flash("Appointment not found.", "error"); return redirect(url_for("billing"))
            cursor.execute("SELECT COUNT(*) FROM invoices WHERE appointment_id=:aid", {"aid": appointment_id})
            if cursor.fetchone()[0]:
                flash("An invoice already exists for this appointment.", "error"); return redirect(url_for("billing"))
            cursor.execute("INSERT INTO invoices (invoice_id, appointment_id, amount, payment_status, created_at) VALUES (invoices_seq.NEXTVAL, :aid, :amount, 'UNPAID', CURRENT_TIMESTAMP)", {"aid": appointment_id, "amount": amount})
            connection.commit(); log_audit("CREATE", "INVOICE", appointment_id, f"Invoice created for {amount}")
            flash("Invoice created.", "success"); return redirect(url_for("billing"))
        cursor.execute("""SELECT a.appointment_id, p.full_name, d.full_name, a.appointment_date, d.consultation_fee
                          FROM appointments a JOIN patients p ON p.patient_id=a.patient_id JOIN doctors d ON d.doctor_id=a.doctor_id
                          WHERE a.status IN ('BOOKED','COMPLETED') AND NOT EXISTS (SELECT 1 FROM invoices i WHERE i.appointment_id=a.appointment_id)
                          ORDER BY a.appointment_date DESC""")
        billable_appointments=cursor.fetchall()
        cursor.execute("""SELECT i.invoice_id, i.appointment_id, p.full_name, d.full_name, i.amount, i.payment_status, i.created_at
                          FROM invoices i JOIN appointments a ON a.appointment_id=i.appointment_id JOIN patients p ON p.patient_id=a.patient_id JOIN doctors d ON d.doctor_id=a.doctor_id
                          ORDER BY i.invoice_id DESC""")
        invoices=cursor.fetchall()
        return render_template("billing.html", billable_appointments=billable_appointments, invoices=invoices)
    finally: close_db(cursor, connection)

@app.route("/billing/<int:invoice_id>/paid", methods=["POST"])
def mark_invoice_paid(invoice_id):
    if not login_required(): return redirect(url_for("login"))
    connection=cursor=None
    try:
        connection=get_connection(); cursor=connection.cursor()
        cursor.execute("UPDATE invoices SET payment_status='PAID', paid_at=CURRENT_TIMESTAMP WHERE invoice_id=:iid AND payment_status='UNPAID'", {"iid": invoice_id})
        if cursor.rowcount: connection.commit(); log_audit("PAYMENT", "INVOICE", invoice_id, "Marked invoice paid"); flash("Invoice marked as paid.", "success")
        else: connection.rollback(); flash("Invoice not found or already paid.", "warning")
    except Exception:
        if connection: connection.rollback()
        app.logger.exception("Invoice payment update failed"); flash("Could not update payment status.", "error")
    finally: close_db(cursor, connection)
    return redirect(url_for("billing"))

# PDF REPORTS AND RECEIPTS
# ==================================================

@app.route("/reports/summary.pdf")
def export_summary_pdf():
    if not login_required():
        return redirect(url_for("login"))
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except ImportError:
        flash("PDF export requires ReportLab. Install requirements.txt and try again.", "error")
        return redirect(url_for("reports"))

    connection = cursor = None
    output = io.BytesIO()
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM patients")
        patient_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM doctors")
        doctor_count = cursor.fetchone()[0]
        cursor.execute("SELECT status, COUNT(*) FROM appointments GROUP BY status ORDER BY status")
        status_rows = cursor.fetchall()
        cursor.execute("SELECT COUNT(*), NVL(SUM(amount),0), NVL(SUM(CASE WHEN payment_status='PAID' THEN amount ELSE 0 END),0), NVL(SUM(CASE WHEN payment_status='UNPAID' THEN amount ELSE 0 END),0) FROM invoices")
        billing_summary = cursor.fetchone()

        doc = SimpleDocTemplate(output, pagesize=A4, title="MediCare Clinic Summary")
        styles = getSampleStyleSheet()
        story = [Paragraph("MediCare Clinic — Summary Report", styles["Title"]),
                 Paragraph(f"Generated: {datetime.now():%d %B %Y, %H:%M}", styles["Normal"]), Spacer(1, 16)]
        rows = [["Metric", "Value"], ["Registered patients", str(patient_count)],
                ["Registered doctors", str(doctor_count)], ["Invoices", str(billing_summary[0] or 0)],
                ["Total invoiced", f"INR {billing_summary[1] or 0:.2f}"],
                ["Paid", f"INR {billing_summary[2] or 0:.2f}"],
                ["Outstanding", f"INR {billing_summary[3] or 0:.2f}"]]
        rows.extend([[f"Appointments — {status}", str(count)] for status, count in status_rows])
        table = Table(rows, colWidths=[300, 170], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#123047")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#d5e0e8")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f3f8fa")]),
            ("PADDING", (0,0), (-1,-1), 8),
        ]))
        story.append(table)
        doc.build(story)
        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = "attachment; filename=medicare_summary.pdf"
        return response
    except Exception:
        app.logger.exception("PDF summary export failed")
        flash("Could not generate the PDF report.", "error")
        return redirect(url_for("reports"))
    finally:
        close_db(cursor, connection)


@app.route("/billing/<int:invoice_id>/receipt.pdf")
def invoice_receipt_pdf(invoice_id):
    if not login_required():
        return redirect(url_for("login"))
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except ImportError:
        flash("PDF receipts require ReportLab. Install requirements.txt and try again.", "error")
        return redirect(url_for("billing"))

    connection = cursor = None
    output = io.BytesIO()
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("""SELECT i.invoice_id, i.appointment_id, p.full_name, d.full_name,
                                 d.specialization, i.amount, i.payment_status, i.created_at, i.paid_at
                          FROM invoices i JOIN appointments a ON a.appointment_id=i.appointment_id
                          JOIN patients p ON p.patient_id=a.patient_id
                          JOIN doctors d ON d.doctor_id=a.doctor_id
                          WHERE i.invoice_id=:iid""", {"iid": invoice_id})
        invoice = cursor.fetchone()
        if not invoice:
            abort(404)
        doc = SimpleDocTemplate(output, pagesize=A4, title=f"MediCare Invoice {invoice_id}")
        styles = getSampleStyleSheet()
        story = [Paragraph("MediCare Clinic", styles["Title"]),
                 Paragraph(f"Invoice / Receipt #{invoice[0]}", styles["Heading2"]),
                 Spacer(1, 12)]
        data = [["Field", "Details"], ["Appointment", str(invoice[1])], ["Patient", str(invoice[2])],
                ["Doctor", str(invoice[3])], ["Specialization", str(invoice[4])],
                ["Amount", f"INR {invoice[5]:.2f}"], ["Payment status", str(invoice[6])],
                ["Created", invoice[7].strftime("%d %b %Y %H:%M") if invoice[7] else "—"],
                ["Paid at", invoice[8].strftime("%d %b %Y %H:%M") if invoice[8] else "—"]]
        table = Table(data, colWidths=[150, 320])
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#123047")),
                                   ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                                   ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#d5e0e8")),
                                   ("PADDING", (0,0), (-1,-1), 9)]))
        story.append(table)
        story.append(Spacer(1, 18))
        story.append(Paragraph("This document is generated by the MediCare Clinic Management System.", styles["Normal"]))
        doc.build(story)
        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f"attachment; filename=medicare_invoice_{invoice_id}.pdf"
        return response
    except Exception:
        app.logger.exception("Invoice PDF generation failed")
        flash("Could not generate this receipt.", "error")
        return redirect(url_for("billing"))
    finally:
        close_db(cursor, connection)


# ==================================================
# REPORTS / GLOBAL SEARCH / AUDIT
# ==================================================

@app.route("/reports")
def reports():
    if not login_required(): return redirect(url_for("login"))
    connection=cursor=None
    try:
        connection=get_connection(); cursor=connection.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM appointments GROUP BY status ORDER BY status"); status_totals=cursor.fetchall()
        cursor.execute("SELECT d.full_name, COUNT(a.appointment_id) FROM doctors d LEFT JOIN appointments a ON a.doctor_id=d.doctor_id GROUP BY d.full_name ORDER BY COUNT(a.appointment_id) DESC, d.full_name"); doctor_load=cursor.fetchall()
        cursor.execute("SELECT TO_CHAR(appointment_date,'YYYY-MM') month_key, COUNT(*) total FROM appointments GROUP BY TO_CHAR(appointment_date,'YYYY-MM') ORDER BY month_key DESC"); monthly=cursor.fetchall()
        cursor.execute("SELECT COUNT(*), NVL(SUM(amount),0), SUM(CASE WHEN payment_status='PAID' THEN amount ELSE 0 END), SUM(CASE WHEN payment_status='UNPAID' THEN amount ELSE 0 END) FROM invoices"); billing_summary=cursor.fetchone()
        return render_template("reports.html", status_totals=status_totals, doctor_load=doctor_load, monthly=monthly, billing_summary=billing_summary)
    finally: close_db(cursor, connection)

@app.route("/reports/appointments.csv")
def export_appointments_csv():
    if not login_required(): return redirect(url_for("login"))
    connection=cursor=None
    try:
        connection=get_connection(); cursor=connection.cursor()
        cursor.execute("""SELECT a.appointment_id, p.full_name, d.full_name, d.specialization, a.appointment_date, a.reason, a.status
                          FROM appointments a JOIN patients p ON p.patient_id=a.patient_id JOIN doctors d ON d.doctor_id=a.doctor_id ORDER BY a.appointment_date DESC""")
        output=io.StringIO(); writer=csv.writer(output); writer.writerow(["Appointment ID","Patient","Doctor","Specialization","Date and time","Reason","Status"])
        writer.writerows(cursor.fetchall())
        response=make_response('\ufeff'+output.getvalue()); response.headers["Content-Type"]="text/csv; charset=utf-8"; response.headers["Content-Disposition"]="attachment; filename=medicare_appointments.csv"; return response
    finally: close_db(cursor, connection)

@app.route("/search")
def global_search():
    if not login_required(): return redirect(url_for("login"))
    q=request.args.get("q", "").strip()[:100]
    patients=[]; doctors=[]; appointments=[]
    if q:
        connection=cursor=None
        try:
            connection=get_connection(); cursor=connection.cursor(); pattern=f"%{q}%"
            cursor.execute("SELECT patient_id, full_name, phone FROM patients WHERE LOWER(full_name) LIKE LOWER(:q) OR phone LIKE :q ORDER BY full_name", {"q":pattern}); patients=cursor.fetchall()[:10]
            cursor.execute("SELECT doctor_id, full_name, specialization FROM doctors WHERE LOWER(full_name) LIKE LOWER(:q) OR LOWER(specialization) LIKE LOWER(:q) ORDER BY full_name", {"q":pattern}); doctors=cursor.fetchall()[:10]
            cursor.execute("SELECT a.appointment_id, p.full_name, d.full_name, a.appointment_date, a.status FROM appointments a JOIN patients p ON p.patient_id=a.patient_id JOIN doctors d ON d.doctor_id=a.doctor_id WHERE LOWER(p.full_name) LIKE LOWER(:q) OR LOWER(d.full_name) LIKE LOWER(:q) ORDER BY a.appointment_date DESC", {"q":pattern}); appointments=cursor.fetchall()[:10]
        finally: close_db(cursor, connection)
    return render_template("search.html", q=q, patients=patients, doctors=doctors, appointments=appointments)

@app.route("/audit")
def audit_logs():
    if not login_required(): return redirect(url_for("login"))
    require_admin()
    connection=cursor=None
    try:
        connection=get_connection(); cursor=connection.cursor()
        cursor.execute("SELECT audit_id, username, action, entity_type, entity_id, details, created_at FROM audit_logs ORDER BY audit_id DESC")
        logs=cursor.fetchall()[:200]; return render_template("audit.html", logs=logs)
    finally: close_db(cursor, connection)

# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
