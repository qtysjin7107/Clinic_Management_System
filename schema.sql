
-- =====================================================
-- CLINIC MANAGEMENT SYSTEM
-- Oracle 11g XE
-- =====================================================

SET DEFINE OFF
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON

-- =====================================================
-- 1. USERS TABLE
-- =====================================================

BEGIN
    EXECUTE IMMEDIATE '
        CREATE TABLE users (
            user_id NUMBER PRIMARY KEY,
            username VARCHAR2(50) NOT NULL UNIQUE,
            password_hash VARCHAR2(255) NOT NULL,
            role VARCHAR2(20) DEFAULT ''STAFF'' NOT NULL,
            CONSTRAINT chk_user_role
                CHECK (role IN (''ADMIN'', ''STAFF''))
        )';
    DBMS_OUTPUT.PUT_LINE('USERS table created.');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -955 THEN
            DBMS_OUTPUT.PUT_LINE('USERS table already exists.');
        ELSE
            RAISE;
        END IF;
END;
/

-- =====================================================
-- 2. PATIENTS TABLE
-- =====================================================

BEGIN
    EXECUTE IMMEDIATE '
        CREATE TABLE patients (
            patient_id NUMBER PRIMARY KEY,
            full_name VARCHAR2(100) NOT NULL,
            date_of_birth DATE,
            gender VARCHAR2(20),
            phone VARCHAR2(20),
            address VARCHAR2(250),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chk_patient_gender
                CHECK (
                    gender IN (''Male'', ''Female'', ''Other'')
                    OR gender IS NULL
                )
        )';
    DBMS_OUTPUT.PUT_LINE('PATIENTS table created.');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -955 THEN
            DBMS_OUTPUT.PUT_LINE('PATIENTS table already exists.');
        ELSE
            RAISE;
        END IF;
END;
/

-- =====================================================
-- 3. DOCTORS TABLE
-- =====================================================

BEGIN
    EXECUTE IMMEDIATE '
        CREATE TABLE doctors (
            doctor_id NUMBER PRIMARY KEY,
            full_name VARCHAR2(100) NOT NULL,
            specialization VARCHAR2(100) NOT NULL,
            phone VARCHAR2(20),
            consultation_fee NUMBER(10,2),
            CONSTRAINT chk_doctor_fee
                CHECK (
                    consultation_fee >= 0
                    OR consultation_fee IS NULL
                )
        )';
    DBMS_OUTPUT.PUT_LINE('DOCTORS table created.');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -955 THEN
            DBMS_OUTPUT.PUT_LINE('DOCTORS table already exists.');
        ELSE
            RAISE;
        END IF;
END;
/

-- =====================================================
-- 4. APPOINTMENTS TABLE
-- =====================================================

BEGIN
    EXECUTE IMMEDIATE '
        CREATE TABLE appointments (
            appointment_id NUMBER PRIMARY KEY,
            patient_id NUMBER NOT NULL,
            doctor_id NUMBER NOT NULL,
            appointment_date DATE NOT NULL,
            reason VARCHAR2(500),
            status VARCHAR2(20) DEFAULT ''BOOKED'' NOT NULL,

            CONSTRAINT fk_appt_patient
                FOREIGN KEY (patient_id)
                REFERENCES patients(patient_id),

            CONSTRAINT fk_appt_doctor
                FOREIGN KEY (doctor_id)
                REFERENCES doctors(doctor_id),

            CONSTRAINT chk_appt_status
                CHECK (
                    status IN (
                        ''BOOKED'',
                        ''COMPLETED'',
                        ''CANCELLED''
                    )
                ),

            CONSTRAINT uq_doctor_appointment
                UNIQUE (doctor_id, appointment_date)
        )';
    DBMS_OUTPUT.PUT_LINE('APPOINTMENTS table created.');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -955 THEN
            DBMS_OUTPUT.PUT_LINE(
                'APPOINTMENTS table already exists.'
            );
        ELSE
            RAISE;
        END IF;
END;
/

-- =====================================================
-- 5. SEQUENCES
-- =====================================================

BEGIN
    EXECUTE IMMEDIATE
        'CREATE SEQUENCE users_seq START WITH 1 INCREMENT BY 1';
    DBMS_OUTPUT.PUT_LINE('USERS_SEQ created.');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -955 THEN
            DBMS_OUTPUT.PUT_LINE('USERS_SEQ already exists.');
        ELSE
            RAISE;
        END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE
        'CREATE SEQUENCE patients_seq START WITH 1 INCREMENT BY 1';
    DBMS_OUTPUT.PUT_LINE('PATIENTS_SEQ created.');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -955 THEN
            DBMS_OUTPUT.PUT_LINE('PATIENTS_SEQ already exists.');
        ELSE
            RAISE;
        END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE
        'CREATE SEQUENCE doctors_seq START WITH 1 INCREMENT BY 1';
    DBMS_OUTPUT.PUT_LINE('DOCTORS_SEQ created.');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -955 THEN
            DBMS_OUTPUT.PUT_LINE('DOCTORS_SEQ already exists.');
        ELSE
            RAISE;
        END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE
        'CREATE SEQUENCE appointments_seq START WITH 1 INCREMENT BY 1';
    DBMS_OUTPUT.PUT_LINE('APPOINTMENTS_SEQ created.');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -955 THEN
            DBMS_OUTPUT.PUT_LINE('APPOINTMENTS_SEQ already exists.');
        ELSE
            RAISE;
        END IF;
END;
/

-- =====================================================
-- 6. VERIFY TABLES
-- =====================================================

SELECT table_name
FROM user_tables
WHERE table_name IN (
    'USERS',
    'PATIENTS',
    'DOCTORS',
    'APPOINTMENTS'
)
ORDER BY table_name;

-- =====================================================
-- END OF SCHEMA
-- =====================================================
