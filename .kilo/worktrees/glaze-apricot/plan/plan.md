# Beet.Health CRM — Gap Audit & Completion Plan

This plan treats **every requirement from the whole project plus the latest consolidated
checklist as one specification**. Nothing already built will be removed, simplified, or
replaced. Below is (1) an honest audit of the current build, (2) exactly what this pass will
add/fix, (3) decisions worth challenging, and (4) what only your tech team can do.

Legend: ✅ working · ⚠️ partial · ❌ missing · 🔧 broken/needs fixing

---

## 1. Gap audit of the current CRM

### Platform / auth / users
- ✅ Private, browser-based desktop CRM (no mobile app, no app stores)
- ✅ Beet.Health work-email + OTP login, approved-users-only, inactive users blocked, no public signup
- ✅ Secrets via environment variables
- ✅ Roles admin/manager/employee/intern; user fields (employee ID, name, email, role, manager, team, joining date, employment type, active/inactive); admin add/edit/activate/deactivate; historical records retained

### Leads
- ✅ Core lead fields, owner, follow-up owner, demo owner, last-interaction tracking, total interactions, next follow-up, custom fields, created-by/date
- ⚠️ "Assigned by" is captured in assignment history but not shown as a first-class lead field; "updated by" (who last edited) is not tracked, only "updated at"
- ⚠️ Lead table: search + filter + saved filters + shared views work; **sort, pagination, and user-configurable core columns are missing/limited** (currently loads all rows, custom-field columns toggle only)
- ⚠️ Global search covers name/phone/email/Instagram/LinkedIn but **not Lead ID**
- ⚠️ Three-dot row menu has some actions; missing a full set (view/edit/add note/schedule follow-up/book demo/change stage/**archive**)
- ✅ Duplicate prevention: normalization + DB-level unique constraints + concurrent protection + "existing lead shown"; name alone does not block

### Pipeline, reasons, timeline
- ✅ Pipeline stages incl. New Lead, Contacted, Replied, Interested, Demo Booked/Completed/No-show, Rescheduled, Trial, Pricing Shared, Follow-up, Invoice Raised, Payment Pending, Paid, Not Paid, Converted, Not Interested, Lost, Closed (⚠️ "Other" stage not seeded)
- 🔧 **Mandatory reasons are only partly enforced.** Reason is required for Not Interested/Lost/Closed, but: **Not Paid does not require a reason**; the reason is **not validated** (a blank, a space, "-", or "N/A" is currently accepted); selecting "Other" does **not** force additional notes. This is the single most important correctness gap you called out.
- ⚠️ Timeline records creation, assignment/handover, status changes, interactions, tasks, demos, follow-ups — but the **reason is not stored on the audit/status event itself**, and payment/invoice changes are not consistently timelined
- ✅ Interaction logging auto-updates last-interaction fields and total interactions
- ⚠️ Audit trail records user/time/action/prev/new for status, owner, follow-up, demo & assignments; **payment/invoice changes, configuration changes, and reason text are not consistently audited**

### Assignment / notifications / tasks / calendar / demos / follow-ups
- ✅ One-action assign/handover (task + in-app notification + email + timeline + dashboard update); different people can own different stages
- ✅ In-app + email notifications for assignment/reassignment/demo/follow-up/task; polling does not create duplicate notifications
- ✅ Tasks with priority + statuses (To Do/In Progress/Completed/Cancelled); ⚠️ an explicit "Overdue" status label is shown via views rather than stored
- ✅ Internal calendar (demos, follow-ups, tasks), role-scoped, auto-updates; ⚠️ no "Meetings" event type
- ✅ Demo workflow (schedule → presenter task → outcome → next action); statuses Scheduled/Completed/No-show/Rescheduled/Cancelled
- ⚠️ Follow-ups exist as lead fields + calendar + dashboard, but there is **no dedicated Follow-ups view with Today/Upcoming/Overdue/Completed tabs**
- ❌ **Invoice/Payment is thin**: only status flags exist. Missing invoice owner, payment owner, amount, dates, and "Not Paid requires reason"

### Real-time / workload / performance / config / import
- ✅ Smart auto-refresh polling + optimistic concurrency (version checks)
- ✅ Team workload board (manager); ✅ team + individual performance for managers, own-only for employees, backend-enforced
- ✅ Configurable options (statuses, stages, sources, contact methods, activity types, reasons, demo statuses, follow-up types, payment statuses, teams, users, roles) and custom fields
- ⚠️ Custom field types — need to confirm date/time and checkbox are fully supported end-to-end
- ⚠️ CSV/XLSX import exists (map → preview → duplicate check → confirm); needs to reliably show the full count set (total/valid/duplicates/invalid/missing/imported)
- ✅ Saved filters + shared team views
- ⚠️ Bulk reassignment + preview exist, but the preview does not break down affected tasks/demos/follow-ups, and there is **no dedicated deactivation flow that shows a leaver's open work before reassigning**

### Email / production
- ✅ Email is delivered via Resend through Emergent's managed proxy to **real inboxes**, and is designed to keep working after deployment (see decision #1). 🔧 the send path does not yet run the required safety gate, and 🔧 OTP dev-mode is still on (code shown on screen)
- ⚠️ README is **out of date** (references removed demo accounts; says import/custom fields are "not built" when they are) and lacks full production/deploy/backup/migration instructions

---

## 2. What this pass will build/fix (all ⚠️ ❌ 🔧 above)

1. **Mandatory reasons — hard enforcement, front and back.** Reason required for Not Interested, Lost, Closed **and Not Paid**; reject blank/whitespace/"-"/"N/A"/too-short; if "Other" is chosen, additional notes become required; closing the modal cancels the status change; the API rejects any status/payment change lacking a valid reason; the previous status, new status, reason, notes, user, date and exact time are recorded on the timeline and audit trail.
2. **Invoice & Payment** upgraded to real fields: invoice owner, payment owner, amount, invoice/payment dates, statuses (Invoice Raised / Payment Pending / Paid / Not Paid), with Not Paid requiring a reason; changes timelined and audited.
3. **Dedicated Follow-ups view** with Today / Upcoming / Overdue / Completed.
4. **Lead table**: add sorting, pagination, and configurable columns; add Lead ID to global search; complete the three-dot menu (view/edit/add note/schedule follow-up/book demo/change stage/convert/lost/closed/**archive**/assign/reassign).
5. **Assignment metadata** surfaced on the lead ("assigned by", "updated by" + updated date/time).
6. **Timeline & audit completeness**: include payment/invoice changes, configuration changes, and the reason text on the relevant events.
7. **Employee deactivation flow**: before deactivating, show the leaver's open leads/tasks/demos/follow-ups, offer bulk reassignment with a full preview and confirmation, keep historical records; every change audited.
8. **Bulk reassignment preview** expanded to show affected tasks/demos/follow-ups counts.
9. **Import**: ensure the full count summary (total/valid/duplicates/invalid/missing/imported) is shown and every imported row is real data.
10. **Custom fields**: confirm/complete all eight types (text, long text, number, date, date/time, dropdown, multi-select, checkbox) end-to-end.
11. **Config**: add the "Other" pipeline stage; confirm every dropdown across the app is options-driven.
12. **Email compliance + production readiness**: add the mandatory email safety gate to every send; turn OTP dev-mode off and stop exposing the code once you're ready to migrate.
13. **Rewrite the README/handbook** and add a production deployment + backup + migration + admin-setup guide, and clear admin/manager/employee test walkthroughs.
14. **Full end-to-end verification** of the two workflows you named (manager-assigns-task round trip; and the reason-block-on-save flow) plus a regression pass over everything above, with results written up.

Nothing currently working (dashboards, Kanban, calendar, workload, performance, notifications, handover, duplicate prevention, OTP) will be removed or simplified.

---

## 3. Decisions worth challenging (tell me if you disagree)

1. **Email/Resend — please read.** On this hosting platform, Resend is provided through a
   managed email proxy and already delivers to real inboxes; the integration's rules
   **explicitly forbid wiring a bring-your-own Resend API key/SMTP**. The send address is a
   platform-verified domain (display name = "Beet.Health"). Practical effect: your tech team
   does **not** need a Resend account for email to work, and it keeps working after
   deployment. *If you specifically require emails to originate from your own
   `@beet.health` domain/Resend account, that is a platform-level arrangement outside the
   app code and cannot be met by app changes alone — flag it and I'll document it as a
   deployment dependency rather than silently ignoring it.*
2. **"Not Paid" reason** will be enforced both when it's chosen as a pipeline stage and when
   it's set as a payment status. Assumed required (you listed it under mandatory reasons).
3. **Calendar "Meetings"**: I'll add a simple internal meeting/event type on the calendar
   (title, date/time, optional linked lead, attendee). Assumed in scope; say if you'd rather
   defer it.
4. **Archive**: "archived" leads will be hidden from default lists but retained and
   filterable (soft archive, never deleted). Assumed.
5. **Pagination**: server-side paging on the leads table (page size ~50). Assumed.
6. **OTP dev-mode**: I'll keep it ON in the preview so you can test without an inbox, and
   provide a single switch to turn it OFF (and hide the on-screen code) for production. Say
   if you want it off in preview immediately.

---

## 4. What only your tech team can do (deployment dependencies)

The app, database schema, seed/migration routine, environment-variable list, README and
deploy guide will be delivered. The following are outside the app and must be done by your
team with Beet.Health-controlled accounts:
- Provision the production **host**, **MongoDB database**, and **domain/DNS**.
- Own the **GitHub repository** (use the "Save to GitHub" action) and CI if desired.
- Set production **secrets/env** (JWT secret, Mongo URL, admin email, email key, app URL,
  CORS origins) and set OTP dev-mode OFF.
- Decide on and run **database backups** per the guidance provided.
- (Only if you require your own sending domain) arrange sender-domain verification — see
  decision #1.

---

## 5. Final handoff you'll receive before migrating
- This gap audit updated to show every item resolved, plus anything still open and why.
- Admin / manager / employee test walkthroughs and credentials.
- Data import/migration instructions and production deployment + backup instructions.
- Exact end-to-end test results for the manager-assignment round trip and the
  reason-blocked-save flow, plus a regression summary.
