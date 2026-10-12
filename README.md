# MediCare Clinic Management System

Flask + Oracle Database 11g XE clinic management application. It uses Oracle sequences and bind variables and is designed to preserve the existing route names and database connection setup.

## Features

- Login and session-based access, CSRF protection for POST forms, and security response headers.
- Patient and doctor CRUD, appointment booking/status management, search, and appointment conflict checks.
- Doctor weekly availability management.
- Patient medical/visit records.
- Invoice creation, payment status, and downloadable PDF receipts.
- Dashboard statistics and upcoming appointments.
- Appointment table and calendar views, with day/week/month-style calendar navigation.
- CSV appointment export and PDF clinic summary report.
- Global search and ADMIN-only audit log view.
- Light, dark, and ocean themes; responsive layouts; reduced-motion support; cursor particles.

## Requirements

- Python 3.10 or later (3.11+ recommended)
- Oracle Database 11g XE with the `xe` service and a user/schema that can create/use the application's tables and sequences
- Oracle Instant Client if Thick mode is required by your Oracle client/server setup
- Internet connection for Flatpickr, FullCalendar, and web fonts currently loaded from CDNs

## Installation (Windows PowerShell)

1. Open PowerShell in this project folder.
2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and enter your local Oracle credentials and a long random `FLASK_SECRET_KEY`. Do not commit `.env` or share it in screenshots.
5. Run `schema.sql` in SQL*Plus or SQL Developer using the target Oracle schema.
6. Run `schema_extensions.sql` in SQL Developer/SQL*Plus in the same schema, OR use the included Python migration runner with your project virtual environment active: `python migrate_extensions.py`. The runner uses the same `.env` connection as Flask, creates medical records, doctor availability, invoices, audit logs, doctor applications, sequences and indexes, and reports missing objects. Run it only after `schema.sql`. Back up your database before applying schema changes.
7. Optional: run `seed.sql` to add sample doctors. It is intended for an empty/test database; avoid repeatedly running it in production because it inserts new sample rows each time.
8. Create an application user:

   ```powershell
   python create_user.py
   ```

9. Start Flask:

   ```powershell
   python app.py
   ```

10. Open the local URL printed by Flask (normally `http://127.0.0.1:5000`).

## Database notes

- The base schema is Oracle 11g-compatible and uses sequences instead of identity columns.
- Run `schema_extensions.sql` after `schema.sql` before using visit records, availability, billing, or audit logs.
- Appointment booking treats appointments as 30-minute slots and checks configured doctor availability when that doctor has any availability rows. Doctors without configured availability retain the current permissive behavior.
- Appointment collision checks in application code improve usability; for concurrent production traffic, consider a separate reservation/locking strategy because a pre-insert check alone cannot eliminate every race condition.

## Security and privacy

- `.env` is deliberately not included. Never commit secrets or real patient data.
- Use synthetic data for demos and coursework screenshots.
- This is an educational project, not a certified clinical system. Before real clinical use, conduct a security review, formal role/permission review, backup/restore testing, and applicable privacy/compliance assessment.
- CSRF tokens are added by the shared template script. Keep JavaScript enabled for form submission protection.
- Restrict database privileges to only the schema objects needed by the app and use HTTPS if deployed beyond localhost.

## Validation performed for this package

- Python files pass `py_compile` syntax validation.
- Jinja templates pass template parsing validation.
- A live Oracle end-to-end test was not run in this build environment because the Oracle Python driver and a project database connection are not available here. Test all CRUD flows, booking conflicts, migration scripts, and PDF exports against your own test schema before submitting or deploying.
