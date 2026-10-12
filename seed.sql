
-- Sample doctors for Clinic Management System

INSERT INTO doctors (
    doctor_id,
    full_name,
    specialization,
    phone,
    consultation_fee
)
VALUES (
    doctors_seq.NEXTVAL,
    'Dr. Asha Sharma',
    'General Medicine',
    '9000000001',
    500
);

INSERT INTO doctors (
    doctor_id,
    full_name,
    specialization,
    phone,
    consultation_fee
)
VALUES (
    doctors_seq.NEXTVAL,
    'Dr. Rahul Mehta',
    'Dermatology',
    '9000000002',
    700
);

INSERT INTO doctors (
    doctor_id,
    full_name,
    specialization,
    phone,
    consultation_fee
)
VALUES (
    doctors_seq.NEXTVAL,
    'Dr. Neha Verma',
    'Pediatrics',
    '9000000003',
    600
);

COMMIT;
