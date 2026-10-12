
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import oracledb
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from werkzeug.security import check_password_hash

from db import get_connection

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY is missing from .env")


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
                WHERE LOWER(p.full_name) LIKE LOWER(:patient_search)
                   OR LOWER(d.full_name) LIKE LOWER(:doctor_search)
                ORDER BY a.appointment_date DESC
                """,
                {
                    "patient_search": pattern,
                    "doctor_search": pattern,
                },
            )
        else:
            cursor.execute(
                base_query + " ORDER BY a.appointment_date DESC"
            )

        appointment_rows = cursor.fetchall()

    except Exception:
        app.logger.exception("Appointment retrieval failed")
        flash("Could not load appointment information.", "error")
    finally:
        close_db(cursor, connection)

    return render_template(
        "appointments.html",
        patients=patient_options,
        doctors=doctor_options,
        appointments=appointment_rows,
        search_query=search_query,
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
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
