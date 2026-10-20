# Project Task Site

Flask starter for a task-submission site with account login, purchase requests, 120-day project period, five task slots per day, weekly withdrawal requests, admin review, and password reset.

## Important financial note
The project selection includes BDT 500, 1,000, 2,500, 5,000, 10,000, 15,000 and 20,000 packages, each with five task slots per day for up to 120 days. Example reward per approved task is BDT 1, 2, 3, 5, 8, 10 and 15 respectively. These are illustrative rates, not guaranteed income. Actual rewards should only be credited against verified revenue and an adequate payout budget. Before accepting money, verify the lawful business model, customer terms, sustainable funding and applicable Bangladesh laws. Purchases stay pending until an admin manually verifies payment.

## Windows
1. Install Python 3.11 or 3.12.
2. Extract ZIP and open Command Prompt in this folder.
3. Run:
   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   set ADMIN_USER=admin
   set ADMIN_PASSWORD=Use-A-Strong-Unique-Password
   set SECRET_KEY=Use-A-Long-Random-Secret
   python app.py
   ```
4. Visit http://127.0.0.1:5000
5. Admin: http://127.0.0.1:5000/admin

Local default admin (only if environment variable not set): `admin` / `ChangeThisAdmin123!`. Never use this on a public server.

## Password reset
The demo generates a single-use reset URL expiring in 30 minutes and displays it on the page after an email is submitted. For production, connect a verified email delivery provider and send the reset URL privately. Do not use the on-screen demo link in a public production site.

## Render
Push these files to GitHub, create a Render Blueprint from `render.yaml`, and set a strong `ADMIN_PASSWORD`. Use the managed PostgreSQL connection string. Start command: `gunicorn app:app`.

## Admin
- `/admin` dashboard
- `/admin/users` customers
- `/admin/purchases` verify payment references and approve/reject purchases
- `/admin/tasks` create one task slot per day (day 1–120, task 1–5)
- `/admin/submissions` verify proof
- `/admin/payouts` review withdrawals

Payout requests are accepted only on the configured weekday (`WEEKLY_PAYOUT_DAY`, default Friday). Mark a payout paid only after you actually send it externally. There is no bKash/Nagad/Rocket API integration in this starter. For production, use email verification, rate limiting, audit logs, database migrations, backups, and security/legal review.
