MediCare Doctor Registration Fix

WHY:
The doctor registration route inserts into DOCTOR_APPLICATIONS using
DOCTOR_APPLICATIONS_SEQ. The error message shown in the browser is generic;
the common cause is that the table or sequence was not created in the Oracle
schema used by Flask.

STEPS:
1. Back up your project.
2. Open doctor_registration_migration.sql in SQL Developer.
3. Connect using the SAME Oracle username configured in the project's .env.
4. Run the whole script with F5 (Run Script).
5. Confirm both DOCTOR_APPLICATIONS and DOCTOR_APPLICATIONS_SEQ appear.
6. Restart Flask and submit the form again.

The package also includes the current app.py, db.py, doctor registration
template, shared flash/effects templates, stylesheet, requirements, and
.env.example for reference. Preserve your own .env file; do not replace it.

If it still fails, check the PowerShell terminal for:
"Public doctor application failed" and the ORA- error below it.
