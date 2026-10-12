-- Run as the SAME Oracle user configured in your Flask .env.
-- Oracle 11g XE compatible. Does not drop or modify existing clinic data.
SET DEFINE OFF

BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE doctor_applications (
      application_id NUMBER PRIMARY KEY,
      full_name VARCHAR2(100) NOT NULL,
      specialization VARCHAR2(100) NOT NULL,
      phone VARCHAR2(20),
      email VARCHAR2(254),
      consultation_fee NUMBER(10,2),
      status VARCHAR2(12) DEFAULT ''PENDING'' NOT NULL
        CHECK (status IN (''PENDING'', ''APPROVED'', ''REJECTED'')),
      submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
      reviewed_at TIMESTAMP,
      reviewed_by VARCHAR2(50),
      CONSTRAINT chk_doc_app_fee CHECK (consultation_fee >= 0 OR consultation_fee IS NULL)
    )';
  DBMS_OUTPUT.PUT_LINE('Created DOCTOR_APPLICATIONS');
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE = -955 THEN
      DBMS_OUTPUT.PUT_LINE('DOCTOR_APPLICATIONS already exists');
    ELSE
      RAISE;
    END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE SEQUENCE doctor_applications_seq START WITH 1 INCREMENT BY 1';
  DBMS_OUTPUT.PUT_LINE('Created DOCTOR_APPLICATIONS_SEQ');
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE = -955 THEN
      DBMS_OUTPUT.PUT_LINE('DOCTOR_APPLICATIONS_SEQ already exists');
    ELSE
      RAISE;
    END IF;
END;
/

SELECT table_name FROM user_tables
WHERE table_name = 'DOCTOR_APPLICATIONS';

SELECT sequence_name FROM user_sequences
WHERE sequence_name = 'DOCTOR_APPLICATIONS_SEQ';
