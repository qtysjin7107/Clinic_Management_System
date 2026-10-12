MediCare Clinic Management System — UI Upgrade

FILES
- templates/ : complete updated frontend templates
- static/css/style.css : complete updated stylesheet

INSTALL
1. Back up your existing templates and static/css/style.css.
2. Copy the templates/ folder contents into your project templates/ folder.
3. Replace static/css/style.css with the supplied file.
4. Restart Flask and hard-refresh the browser (Ctrl+F5).

PRESERVED
- Existing Flask endpoint names and form actions.
- Existing Oracle schema/data/backend contract.
- Appointment submission value format YYYY-MM-DDTHH:MM (Flatpickr alt display only).
- Existing light/dark/ocean theme storage and CRUD forms.

UI CHANGES
- Unified design tokens, controls, focus states, and responsive layouts.
- Client-side table pagination (8 visible rows per page) after existing server-side search.
- Improved appointment picker styling for all themes.
- Reduced particle cap (28 simultaneous particles) and slower event throttle for performance.
- Improved dashboard layout and a visual summary based only on existing stats values.
- Optional upcoming_appointments dashboard section: it renders records only if the Flask dashboard route supplies an upcoming_appointments iterable with appointment row shape [id, patient name, doctor name, specialization, datetime, reason, status]. If not supplied, the page displays a clear empty/info state. No backend changes are made by this package.

NOTES
- Flatpickr and Google Fonts are loaded from CDNs, so internet access is needed for those resources.
- Client-side pagination is presentation-only; server-side search and route behavior are unchanged.
- The CSS mini-chart summarizes current totals, not historical trends. For genuine weekly charts or appointment status breakdowns, the Flask route must pass real aggregated Oracle data.
