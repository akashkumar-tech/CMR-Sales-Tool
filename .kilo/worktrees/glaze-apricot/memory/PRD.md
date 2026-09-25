# Beet.Health CRM — PRD

## Problem statement
Web CRM & sales-management system for Beet.Health. FastAPI + MongoDB backend, React/Vite frontend.
- **Auth**: email + OTP only (no passwords). Only Admin-approved, active users may request an OTP. No self-registration.
- **RBAC (backend-enforced)**: admin, manager, employee, intern.
  - admin: full access incl. CRM configuration, custom fields, roles, users, all data.
  - manager: owner-level operational visibility — all leads, team performance, assignments, exports, audit, imports; can add staff & assign leads.
  - employee/intern: only own/involved leads, tasks, follow-ups, demos, activities & performance; global search for duplicate prevention.
- Configurable CRM (statuses/pipeline, sources, contact methods, activity types, lost reasons, demos, payment options, custom fields, teams/users) from Settings.
- Leads, Kanban, activities, tasks/follow-ups, demos, dashboards, reporting, imports/exports, audit history, duplicate prevention, assignment history, saved filter views, bulk reassignment.
- Transactional email (Emergent email integration): OTP, daily follow-up reminders, welcome/onboarding deep-link emails.

## Seed policy
Only the initial Admin (`admin@beet.health`) is seeded at startup. All staff are created from Settings → Team Members. A separate idempotent demo seed (`/app/backend/seed_demo.py`) creates a Manager test account + small team + sample leads for demos/testing.

## Implemented (as of 2026-06)
- OTP auth, approved-user gate, JWT sessions, rate limiting (5/10min).
- Full RBAC across all endpoints; reassignment revokes prior-owner access (added_by no longer grants access; follow-up/demo assignees cascade on owner change).
- Configurable options engine + Settings UI; custom fields; teams/users management with unique employee_id.
- Leads with LinkedIn + interaction metadata (last interaction/by/method, total interactions); smart duplicate detection (phone/email/IG/LinkedIn).
- Kanban, activities, tasks, demos, dashboards (clickable metrics), reports, audit, CSV export, CSV/XLSX tracker import.
- Saved filter views, bulk reassignment (open leads only) + preview, welcome email sign-in deep link (APP_URL).
- Daily follow-up reminder scheduler + manual trigger.

### 2026-06-23 — Manager login bug fix (iteration 4)
- **Root cause**: only `admin@beet.health` existed in DB; the Manager's email was never seeded, so the approved-user gate returned 403. No code bug.
- **Fix**: `seed_demo.py` seeds active Manager `paripsa.tripathi@beet.health` (role=manager, Sales) + demo team (Priya/Arjun employees, Neha intern) + 8 sample leads/activities. Added Manager quick-fill button on Login.
- **Verified (testing agent, 13/13 backend + frontend)**: manager OTP login → role=manager → /dashboard with full visibility (all leads, team performance, teams, users, audit, reports); can add employees + assign leads; non-approved emails still 403; employees still blocked from manager endpoints/routes.

### 2026-06-23 — Phase 1 workflow upgrade (iteration 5)
Major "live/collaborative CRM" upgrade — Phase 1 of 3. Choices: smart polling (no websockets), internal calendar later, professional Beet.Health look w/ pink/coral accents (central theme tokens in index.css), balanced auto-emails.
- **Real-time**: `useAutoRefresh` polling (interval + window-focus + visibility) across leads, tasks, drawer, notifications. Lead `version` field + `expected_version` → HTTP 409 on concurrent edits; drawer shows a stale banner + Reload. DB is source of truth.
- **Unified lead timeline**: `GET /api/leads/{id}/timeline` merges activities + handovers + audit change-log into human-readable chronological events; drawer Timeline tab renders it.
- **Assign/Handover workflow (single action)**: `POST /api/leads/{id}/handover` updates ownership field + creates a Task (assigned_by, due date/time, priority, note) + assignment record + audit + in-app notification + email — in one call. UI: `HandoverDialog` from drawer ("Assign") and All Leads row menu. Responsibilities: owner/presales/sales/demo/follow_up/pricing/invoice/payment/onboarding/success/other.
- **Notification center**: header bell (unread count, dropdown, mark read / read-all), persists across refresh; deep link `/dashboard?open=<leadId>`. Endpoints under `/api/notifications`.
- **Tasks**: statuses To Do/In Progress/Completed/Cancelled; shows priority + "by <assigner>"; completing a task logs a timeline activity + notifies assigner. Fixed legacy `member`-role empty assignee dropdown.
- **Reasons enforcement**: negative statuses (Not Interested/Lost/Closed) require a reason before save; reason shown in lead table + drawer header.
- **Branding**: pink/coral accent via central CSS tokens (`--primary`, `--brand-from/to`, `.brand-gradient`), applied to buttons/nav/badges/logo/login.
- **Verified (testing agent, 15/15 backend + all frontend flows)**. No bugs. Follow-ups: a11y DialogTitle warnings, native date pickers, optional seed timeline backfill.

### 2026-06-23 — Employee workspace + RBAC demonstration (iteration 6)
Delivered a complete employee-facing workspace and proved all three views + server-side permissions.
- **Dashboard split** (`Dashboard.jsx`): `ManagerDashboard` (command centre) vs `EmployeeDashboard` (action-focused). Employee dashboard shows 10 personal KPIs (leads added, contacted, responses, interested, demos booked/completed, follow-ups done, conversions, tasks completed, overdue) via `/performance/me`, plus My Tasks (today/overdue/upcoming + Done button), My Follow-ups, My Demos, My Recent Activity, notification bell. "Only you can see these numbers" privacy note.
- **RBAC (backend-enforced, verified)**: employee `/performance/team` & `/audit` → 403; `/leads`,`/activities`,`/tasks` scoped to involvement; `/performance/me` self-only; manager-only routes (`/all-leads`,`/team-performance`) hidden in sidebar AND redirect to `/dashboard`. `/users` now returns a minimal directory (id/name/role/team/active) to non-managers — no emails/HR fields.
- **Demos page** fixed (legacy `member` role filter) + shows demo owner/time/status; auto-refresh.
- **Full round-trip verified**: manager handover → employee notification + task + timeline event → employee completes → manager sees completion (timeline + notification).
- **Seed** (`seed_demo.py`) enriched so Priya has tasks + a demo + notifications for a live employee demo.
- **Verified (testing agent, 9/9 backend + all frontend flows, iteration 6)**. No bugs.

### 2026-06-23 — Phase 2: Calendar + Demo Workflow + Team Workload (iteration 7)
Demo team simplified to **1 manager (Paripsa) + 1 employee (Priya)** — Arjun & Neha removed, their leads/tasks moved to Priya (migration run once).
- **Shared Calendar** (`CalendarPage.jsx`, `GET /api/calendar`): month grid of demos/follow-ups/tasks, role-scoped (manager = whole team + per-employee filter; employee = own only), colour-coded chips, click opens the linked lead. Nav `nav-calendar`.
- **Demo Workflow**: `POST /api/leads/{id}/demo/schedule` (assign presenter → auto task + notification + email + timeline; status→Demo Booked/Scheduled) and `POST /api/leads/{id}/demo/complete` (set result, optionally move status, log timeline, and prompt a NEXT ACTION that assigns follow-up/pricing/etc via the shared `assign_work()` helper). UI: `DemoScheduleDialog` + `DemoCompleteDialog` in LeadDrawer Demo tab.
- **Team Workload** (`Workload.jsx`, `GET /api/workload`, manager-only, employee 403): per-employee open leads, open/today/overdue tasks, upcoming demos, open/overdue follow-ups, with clickable drill-downs. Nav `nav-workload` (manager-only).
- Shared `assign_work()` backend helper now underpins demo next-actions (and mirrors handover).
- **Verified (testing agent, 12/12 backend + all frontend flows, iteration 7)**. No functional bugs. Carry-over nit: native date pickers in demo dialogs (design only).

### 2026-06-23 — Gap-closure pass (correctness + completeness)
Executed the approved gap-audit plan.
- **Hard reason enforcement** (backend `valid_reason()` in both `move_stage` and `update_lead`): rejects blank/whitespace/`-`/`N/A`/<3 chars; "Other" requires notes; applies to Not Interested/Lost/Closed **and payment "Not Paid"**. Reason stored + surfaced in audit/timeline. Frontend reason modal disables Confirm until valid.
- **Invoice/Payment fields**: invoice_owner, payment_owner, invoice_amount, invoice_date, payment_date, payment_reason (Not-Paid requires reason); changes audited.
- **Timeline/audit completeness**: payment_status/invoice_status changes audited; reason text appended to status/payment audit; `updated_by`/`updated_by_name` now tracked on every lead write.
- **Lead table**: archive (soft, hidden by default + "Show archived" toggle + menu action), Lead ID added to global search, server-side `sort`/`order` params.
- **"Other" pipeline stage** seeded.
- **Dedicated Follow-ups view** (Today/Upcoming/Overdue/All Open), nav + route.
- **Reassign-preview breakdown** now returns open_tasks/upcoming_demos/open_follow_ups for the deactivation/offboarding flow.
- **Email safety gate** (`_assert_safe_email`) enforced on every send (blocks forms/inputs, non-https links, credential-ask phrasing).
- **README** rewritten with production deploy + backup + migration + walkthroughs.
- Curl-verified: reason 400s + valid 200, payment Not-Paid 400/200, Lead-ID search, archive hide, preview breakdown. Deferred (flagged): full column-config/pagination UI, calendar "Meetings" type, in-Settings deactivation modal (uses existing bulk-reassign + enriched preview), turning OTP dev-mode off (one env switch, kept ON for preview).

### 2026-06-24 — Reports date filters + Sales Funnel (iteration 9)
- **Reports periods**: Day/Week/Month/Quarter/Year + Custom (start/end); backend `period_bounds` extended; leads filtered by created_at, activities by timestamp.
- **Sales totals**: leads, outreach, responses, demos, trials, follow-ups, invoices, payments, conversions, losses — 10 clickable cards that drill into the leads list (manager → /all-leads, employee → /my-leads).
- **Sales Funnel**: New Lead→Contacted→Interested→Demo→Trial→Pricing→Invoice→Payment→Converted with cumulative per-stage counts, conversion %, and lost count; clickable bars drill into the matching status.
- **Employee/owner + team filters** (managers); auto-refresh; real CRM data only; employee scope enforced server-side (lead_scope), by_employee empty for employees, cannot widen via params.
- **Verified (testing agent, 14/14 backend + all frontend flows, iteration 9)**. No bugs. Note: employee reports use lead_scope (owner+followup+demo) — a superset of the manager's owner-only ?employee= filter (by design).

### 2026-06-24 — Sales Funnel refinement
- Funnel now uses the exact 10 steps: Leads Generated → People Contacted → Any Reply → Idea Explained → Interested / Asked for Demo → Demo Booked → Demo Completed → Commercials Opened / Invoice Raised → Invoice Paid → Clients Added (cumulative reached by pipeline order; real data). Actual count + conversion % per step; each bar clickable to the matching leads; Day/Week/Month/Quarter/Year/Custom + employee/owner filters.
- Added **Avg days Demo Completed → Invoice Paid** (payment_date − demo_completed_at) with sample count. Backend now stamps `demo_completed_at` (on stage/demo completion) and `payment_date` (on Paid). seed backfills real dates on won leads.
- Self-verified: curl (funnel counts monotonic, avg=5.0 days/1 sample) + screenshot.

## Credentials
See `/app/memory/test_credentials.md`.

## Backlog / remaining (P1/P2)
- P1: Flip `OTP_DEV_MODE=false` and guard the `dev_otp` response field before any production deploy.
- P2: Modularize `server.py` (auth/users/leads/options/imports/reminders).
- P2: `seed_demo.py` re-run silently re-promotes/re-activates demoted seeded users — gate behind an explicit flag.
- P2: Validate real production email delivery (OTP/welcome/reminders) against a reachable inbox.
