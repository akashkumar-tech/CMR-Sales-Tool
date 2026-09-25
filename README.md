# Beet.Health CRM

A private, browser-based sales & client-success CRM for the Beet.Health team.
FastAPI + MongoDB backend, React (CRA) frontend. Email + OTP login (no passwords,
approved work-emails only). Real-time-feel via smart polling; backend-enforced RBAC.

## Roles
- **admin** — full access: CRM config, custom fields, users, all data, audit.
- **manager** — all leads, team performance, team workload, calendar (whole team),
  assignments, imports, exports, audit, bulk reassignment.
- **employee / intern** — only own/involved leads, tasks, follow-ups, demos, calendar
  (own), activities and personal KPIs. Global search for duplicate prevention.
  Blocked (403) from `/performance/team`, `/audit`, `/workload`.

## Key features
Leads (owner + per-stage owners, last-interaction tracking, custom fields, archive),
configurable pipeline & options, **mandatory validated reasons** for Not
Interested/Lost/Closed/Not-Paid (blank/"-"/"N/A"/short rejected; "Other" forces
notes), unified lead timeline + audit trail (who/when/prev→new + reason),
one-action assign/handover (task + in-app notification + email + timeline),
demo workflow (schedule → presenter task → outcome → next action),
tasks + shared calendar + dedicated Follow-ups view, team workload board,
invoice/payment fields (owner/amount/dates), CSV/XLSX import (map→preview→dedupe→commit),
saved & shared filter views, duplicate prevention (normalized phone/email/IG/LinkedIn
+ DB unique indexes), concurrent-edit protection (version check → 409).

## Environment variables

### backend/.env
| Key | Purpose |
|-----|---------|
| `MONGO_URL` | MongoDB connection string |
| `DB_NAME` | Database name |
| `JWT_SECRET` | Session token signing secret |
| `ADMIN_EMAIL` | Bootstrap admin seeded on first start |
| `ADMIN_NAME` | Bootstrap admin display name |
| `EMERGENT_EMAIL_KEY` | Managed email (Resend) proxy key — see Email below |
| `EMAIL_FROM_NAME` | Sender display name (e.g. `Beet.Health`) |
| `APP_URL` | Public app URL used in email deep-links |
| `OTP_DEV_MODE` | `true` shows the OTP on screen/response (preview only). **Set `false` in production** — then the code is only emailed, and a failed send returns an error. |
| `APPROVED_EMAIL_DOMAIN` | Only emails at this domain can be added as staff (e.g. `beet.health`; empty = any) |
| `APP_TIMEZONE` | Team time zone for "today", report periods and the 08:00 reminder (default `Asia/Kolkata`) |

`backend/.env` is git-ignored. Start from `backend/.env.example`; for local frontend work copy
`frontend/.env.example` to `frontend/.env.local`.

### frontend/.env
| Key | Purpose |
|-----|---------|
| `REACT_APP_BACKEND_URL` | Public backend base URL (all API routes are under `/api`) |

Never hard-code URLs/secrets; everything comes from `.env`.

## Local run (managed by supervisor)
Backend `0.0.0.0:8001`, frontend `3000`. Restart after `.env`/dependency changes:
`sudo supervisorctl restart backend` / `frontend`. Use `yarn` for frontend deps.

## Email (Resend via Emergent managed proxy)
Email is delivered through Emergent's managed Resend proxy to **real inboxes** and
keeps working after deployment. Set `EMERGENT_EMAIL_KEY` + `EMAIL_FROM_NAME`.
A safety gate blocks forms/inputs, non-https links and credential-ask phrasing on
every send. Bring-your-own Resend/SMTP keys are not used. If you require emails to
originate from your own `@beet.health` sending domain, that is a platform-level
domain-verification arrangement handled outside the app (deployment dependency).

## Seeding & demo
`python backend/seed_demo.py` creates the demo team (Manager **Paripsa**, Employee
**Priya**) + 8 sample leads, tasks, a demo and notifications. In production, only the
bootstrap **admin** (`ADMIN_EMAIL`) is seeded; all staff are created from
Settings → Team Members. See `memory/test_credentials.md` for login details.

## Production deployment (Beet.Health tech team)
1. Provision host, a **MongoDB** instance, and domain/DNS.
2. Set all backend `.env` values above; set `OTP_DEV_MODE=false`.
3. Set `REACT_APP_BACKEND_URL` to the public backend URL; build the frontend.
4. First boot seeds the admin from `ADMIN_EMAIL`; log in via OTP and create staff.
5. Use "Save to GitHub" to own the repository.

### Database backup & migration
- **Backup:** `mongodump --uri "$MONGO_URL" --db "$DB_NAME" --out backup/$(date +%F)` (schedule daily).
- **Restore:** `mongorestore --uri "$MONGO_URL" --nsInclude "$DB_NAME.*" backup/<date>`.
- **Migration:** import legacy leads via Settings → Import (CSV/XLSX) with column
  mapping, preview and duplicate-skipping. Never drop collections in production;
  add fields with defaults (documents without a field are treated as unset/false,
  e.g. `archived`).

## Test walkthroughs
- **Admin:** log in → Settings (options, custom fields, users) → add a manager/employee.
- **Manager:** Dashboard command-centre → All Leads → open a lead → Assign/Handover
  to the employee (they get a notification + email + task) → Team Workload / Calendar.
- **Employee:** personal dashboard (own KPIs) → My Tasks/Follow-ups/Demos → open a
  lead, log an interaction, complete a task (updates the timeline the manager sees).
- **Reason block:** set a lead to Lost/Not Interested → a reason is required before save.
