"""Create the additional MediCare tables required by the new tabs.

Run from the project folder after schema.sql has already been applied:
    python migrate_extensions.py

Uses the same .env and Oracle connection settings as app.py. Safe to rerun for
objects that already exist. It does not drop or modify existing patient data.
"""
from db import get_connection

DDL = [
    ("table MEDICAL_RECORDS", """CREATE TABLE medical_records (
        record_id NUMBER PRIMARY KEY,
        patient_id NUMBER NOT NULL REFERENCES patients(patient_id),
        visit_date DATE NOT NULL,
        diagnosis VARCHAR2(250) NOT NULL,
        notes VARCHAR2(2000),
        prescription VARCHAR2(2000),
        created_by VARCHAR2(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )"""),
    ("sequence MEDICAL_RECORDS_SEQ", "CREATE SEQUENCE medical_records_seq START WITH 1 INCREMENT BY 1"),
    ("table DOCTOR_AVAILABILITY", """CREATE TABLE doctor_availability (
        availability_id NUMBER PRIMARY KEY,
        doctor_id NUMBER NOT NULL REFERENCES doctors(doctor_id),
        day_of_week NUMBER(1) NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
        start_time VARCHAR2(5) NOT NULL,
        end_time VARCHAR2(5) NOT NULL,
        is_available CHAR(1) DEFAULT 'Y' NOT NULL CHECK (is_available IN ('Y','N')),
        CONSTRAINT chk_availability_time CHECK (start_time < end_time)
    )"""),
    ("sequence DOCTOR_AVAILABILITY_SEQ", "CREATE SEQUENCE doctor_availability_seq START WITH 1 INCREMENT BY 1"),
    ("table INVOICES", """CREATE TABLE invoices (
        invoice_id NUMBER PRIMARY KEY,
        appointment_id NUMBER NOT NULL UNIQUE REFERENCES appointments(appointment_id),
        amount NUMBER(10,2) NOT NULL CHECK (amount >= 0),
        payment_status VARCHAR2(10) DEFAULT 'UNPAID' NOT NULL CHECK (payment_status IN ('UNPAID','PAID')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        paid_at TIMESTAMP
    )"""),
    ("sequence INVOICES_SEQ", "CREATE SEQUENCE invoices_seq START WITH 1 INCREMENT BY 1"),
    ("table AUDIT_LOGS", """CREATE TABLE audit_logs (
        audit_id NUMBER PRIMARY KEY,
        user_id NUMBER,
        username VARCHAR2(50),
        action VARCHAR2(50) NOT NULL,
        entity_type VARCHAR2(50) NOT NULL,
        entity_id VARCHAR2(50),
        details VARCHAR2(1000),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )"""),
    ("sequence AUDIT_LOGS_SEQ", "CREATE SEQUENCE audit_logs_seq START WITH 1 INCREMENT BY 1"),
    ("index IDX_APPOINTMENTS_DATE_STATUS", "CREATE INDEX idx_appointments_date_status ON appointments(appointment_date, status)"),
    ("index IDX_APPOINTMENTS_DOCTOR_DATE", "CREATE INDEX idx_appointments_doctor_date ON appointments(doctor_id, appointment_date)"),
    ("index IDX_MEDICAL_RECORDS_PATIENT_DATE", "CREATE INDEX idx_medical_records_patient_date ON medical_records(patient_id, visit_date)"),
    ("table DOCTOR_APPLICATIONS", """CREATE TABLE doctor_applications (
        application_id NUMBER PRIMARY KEY,
        full_name VARCHAR2(100) NOT NULL,
        specialization VARCHAR2(100) NOT NULL,
        phone VARCHAR2(20),
        email VARCHAR2(254),
        consultation_fee NUMBER(10,2) CHECK (consultation_fee >= 0 OR consultation_fee IS NULL),
        status VARCHAR2(12) DEFAULT 'PENDING' NOT NULL CHECK (status IN ('PENDING','APPROVED','REJECTED')),
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        reviewed_at TIMESTAMP,
        reviewed_by VARCHAR2(50)
    )"""),
    ("sequence DOCTOR_APPLICATIONS_SEQ", "CREATE SEQUENCE doctor_applications_seq START WITH 1 INCREMENT BY 1"),
]

# ORA-00955 means an object with that name already exists. Do not suppress
# other Oracle errors: they usually indicate a wrong schema or missing base table.
connection = get_connection()
cursor = connection.cursor()
try:
    for label, sql in DDL:
        try:
            cursor.execute(sql)
            connection.commit()
            print(f"CREATED: {label}")
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == 955 or "ORA-00955" in str(exc):
                print(f"EXISTS:  {label}")
                connection.rollback()
            else:
                connection.rollback()
                print(f"FAILED:  {label}\n{exc}")
                raise

    cursor.execute("""SELECT table_name FROM user_tables
        WHERE table_name IN ('MEDICAL_RECORDS','DOCTOR_AVAILABILITY',
        'INVOICES','AUDIT_LOGS','DOCTOR_APPLICATIONS') ORDER BY table_name""")
    found = [row[0] for row in cursor.fetchall()]
    print("\nExtension tables visible to this Oracle user:")
    for name in found:
        print(f"  - {name}")
    missing = sorted(set(['MEDICAL_RECORDS','DOCTOR_AVAILABILITY','INVOICES','AUDIT_LOGS','DOCTOR_APPLICATIONS']) - set(found))
    if missing:
        raise RuntimeError("Some tables are still missing: " + ", ".join(missing))
    print("\nMigration completed. Restart Flask and retest the tabs.")
finally:
    cursor.close()
    connection.close()
