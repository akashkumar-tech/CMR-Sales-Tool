"""Regression tests for the audit bug fixes (BUG-002 … BUG-043).

Live HTTP tests like the rest of this suite. They create their own users and data, so run them ONLY against a
local/dev backend with OTP_DEV_MODE=true (never production):

    REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests/test_bugfixes.py
"""
import csv
import io
import os
import random
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import openpyxl
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@beet.health")
RUN = uuid.uuid4().hex[:6]


def login(email):
    r = requests.post(f"{API}/auth/request-otp", json={"email": email})
    assert r.status_code == 200, r.text
    otp = r.json()["dev_otp"]
    r = requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]


def lead(h, **kw):
    body = {"name": f"QA {RUN} {uuid.uuid4().hex[:6]}"}
    body.update(kw)
    r = requests.post(f"{API}/leads", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def phone():
    return "9" + "".join(random.choice("0123456789") for _ in range(9))


def get_lead(h, lid):
    return requests.get(f"{API}/leads/{lid}", headers=h)


@pytest.fixture(scope="module")
def admin():
    return login(ADMIN_EMAIL)


@pytest.fixture(scope="module")
def mgr(admin):
    h, _ = admin
    r = requests.post(f"{API}/users", headers=h, json={"name": f"QA Mgr {RUN}", "email": f"qa.mgr.{RUN}@beet.health", "role": "manager"})
    assert r.status_code == 200, r.text
    return login(r.json()["email"])


@pytest.fixture(scope="module")
def emp(admin):
    h, _ = admin
    r = requests.post(f"{API}/users", headers=h, json={"name": f"QA Emp {RUN}", "email": f"qa.emp.{RUN}@beet.health", "role": "employee"})
    assert r.status_code == 200, r.text
    return login(r.json()["email"])


# ---------------- auth ----------------
def test_otp_request_response_unchanged_in_dev_mode():
    """OTP generation is untouched: dev mode still returns a 6-digit code."""
    r = requests.post(f"{API}/auth/request-otp", json={"email": ADMIN_EMAIL})
    j = r.json()
    assert r.status_code == 200 and j["sent"] is True and j["dev_mode"] is True
    assert len(j["dev_otp"]) == 6 and j["dev_otp"].isdigit()


def test_bug002_verify_attempts_are_limited(admin):
    h, _ = admin
    email = f"qa.lock.{RUN}@beet.health"
    assert requests.post(f"{API}/users", headers=h, json={"name": "QA Lock", "email": email, "role": "employee"}).status_code == 200
    code = requests.post(f"{API}/auth/request-otp", json={"email": email}).json()["dev_otp"]
    wrong = "000000" if code != "000000" else "111111"
    statuses = [requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": wrong}).status_code for _ in range(5)]
    assert statuses == [400] * 5
    assert requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": wrong}).status_code == 429
    # locked out: even the right code is refused until the window passes
    assert requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": code}).status_code == 429


def test_bug033_logout_revokes_token(admin):
    h, _ = login(ADMIN_EMAIL)
    assert requests.get(f"{API}/auth/me", headers=h).status_code == 200
    assert requests.post(f"{API}/auth/logout", headers=h).status_code == 200
    assert requests.get(f"{API}/auth/me", headers=h).status_code == 401
    # other sessions of the same user are unaffected
    assert requests.get(f"{API}/auth/me", headers=admin[0]).status_code == 200


# ---------------- team ----------------
def test_bug006_manager_can_edit_employee(mgr, emp):
    h, _ = mgr
    _, e = emp
    r = requests.patch(f"{API}/users/{e['id']}", headers=h, json={"name": e["name"], "role": e["role"], "team": "QA Team"})
    assert r.status_code == 200, r.text
    assert r.json()["team"] == "QA Team"
    # a real role change still needs admin
    assert requests.patch(f"{API}/users/{e['id']}", headers=h, json={"role": "intern"}).status_code == 403


def test_bug020_manager_cannot_manage_admins_or_self(admin, mgr):
    ah, a = admin
    mh, m = mgr
    assert requests.patch(f"{API}/users/{a['id']}", headers=mh, json={"active": False}).status_code == 403
    assert requests.patch(f"{API}/users/{m['id']}", headers=mh, json={"active": False}).status_code == 400
    assert requests.get(f"{API}/auth/me", headers=ah).status_code == 200


def test_bug036_only_approved_domain(admin):
    h, _ = admin
    r = requests.post(f"{API}/users", headers=h, json={"name": "Outsider", "email": f"qa.{RUN}@gmail.com", "role": "employee"})
    assert r.status_code == 400


# ---------------- leads ----------------
def test_bug012_search_is_literal(mgr):
    h, _ = mgr
    special = lead(h, name=f"QA (Paren) {RUN}")
    r = requests.get(f"{API}/leads", headers=h, params={"search": f"(Paren) {RUN}"})
    assert r.status_code == 200 and [l["id"] for l in r.json()] == [special["id"]]
    assert requests.get(f"{API}/leads/search", headers=h, params={"q": "(("}).status_code == 200
    dot = requests.get(f"{API}/leads", headers=h, params={"search": f".{RUN}"}).json()
    assert dot == []  # "." is no longer a wildcard


def test_bug008_cleared_followup_is_not_overdue(mgr):
    h, _ = mgr
    l = lead(h, next_follow_up="")
    assert get_lead(h, l["id"]).json()["next_follow_up"] is None
    l2 = lead(h, next_follow_up="2099-01-01")
    requests.put(f"{API}/leads/{l2['id']}", headers=h, json={"next_follow_up": ""})
    assert get_lead(h, l2["id"]).json()["next_follow_up"] is None
    overdue = {x["id"] for x in requests.get(f"{API}/leads", headers=h, params={"follow_up": "overdue"}).json()}
    assert l["id"] not in overdue and l2["id"] not in overdue


def test_bug009_demo_outcome_enforces_reason(mgr):
    h, m = mgr
    l = lead(h)
    requests.post(f"{API}/leads/{l['id']}/demo/schedule", headers=h, json={"demo_date": "2030-01-01", "presenter_id": m["id"]})
    r = requests.post(f"{API}/leads/{l['id']}/demo/complete", headers=h, json={"new_status": "Lost"})
    assert r.status_code == 400 and r.json()["detail"]["requires_reason"]
    assert requests.post(f"{API}/leads/{l['id']}/demo/complete", headers=h, json={"new_status": "Banana"}).status_code == 400
    r = requests.post(f"{API}/leads/{l['id']}/demo/complete", headers=h, json={"new_status": "Lost", "lost_reason": "Too expensive"})
    assert r.status_code == 200
    ld = r.json()["lead"]
    assert ld["status"] == "Lost" and ld["lost_reason"] == "Too expensive" and ld["conversion_status"] == "Lost"


def test_bug015_reopen_resets_loss_and_needs_new_reason(mgr):
    h, _ = mgr
    l = lead(h)
    requests.patch(f"{API}/leads/{l['id']}/stage", headers=h, json={"status": "Lost", "lost_reason": "Too expensive"})
    r = requests.patch(f"{API}/leads/{l['id']}/stage", headers=h, json={"status": "Interested"}).json()
    assert r["conversion_status"] == "Open" and r["lost_reason"] is None
    r = requests.put(f"{API}/leads/{l['id']}", headers=h, json={"status": "Not Interested"})
    assert r.status_code == 400  # the old reason is not silently reused


def test_bug023_unknown_status_and_users_rejected(mgr):
    h, m = mgr
    l = lead(h)
    assert requests.put(f"{API}/leads/{l['id']}", headers=h, json={"status": "Banana"}).status_code == 400
    assert requests.patch(f"{API}/leads/{l['id']}/assign", headers=h, json={"field": "owner", "user_id": "ghost"}).status_code == 400
    assert requests.post(f"{API}/leads/bulk-reassign", headers=h, json={"from_user": m["id"], "to_user": "ghost"}).status_code == 400


def test_bug035_input_validation(mgr):
    h, _ = mgr
    assert requests.post(f"{API}/leads", headers=h, json={"name": "   "}).status_code == 422
    assert requests.post(f"{API}/leads", headers=h, json={"name": "X" * 5000}).status_code == 422
    l = lead(h)
    assert requests.put(f"{API}/leads/{l['id']}", headers=h, json={"invoice_amount": -1}).status_code == 422
    assert requests.put(f"{API}/leads/{l['id']}", headers=h, json={"next_follow_up": "not-a-date"}).status_code == 422
    assert requests.put(f"{API}/leads/{l['id']}", headers=h, json={"invoice_amount": 1500, "next_follow_up": "2030-02-03"}).status_code == 200


def test_bug034_instagram_and_linkedin_duplicates_blocked(mgr):
    h, _ = mgr
    lead(h, instagram=f"@qa.handle.{RUN}", linkedin=f"https://linkedin.com/in/qa-{RUN}")
    r = requests.post(f"{API}/leads", headers=h, json={"name": f"QA {RUN} dupe", "instagram": f"qa.handle.{RUN}"})
    assert r.status_code == 409 and r.json()["detail"]["existing_id"]
    r = requests.post(f"{API}/leads", headers=h, json={"name": f"QA {RUN} dupe2", "linkedin": f"HTTP://LinkedIn.com/in/QA-{RUN}/"})
    assert r.status_code == 409


def test_bug011_every_lead_write_bumps_version(mgr, emp):
    h, _ = mgr
    _, e = emp
    l = lead(h, next_follow_up="2030-01-01")
    v = get_lead(h, l["id"]).json()["version"]
    requests.post(f"{API}/activities", headers=h, json={"lead_id": l["id"], "type": "Call", "notes": "x", "next_follow_up": "2030-06-15"})
    v2 = get_lead(h, l["id"]).json()["version"]
    requests.patch(f"{API}/leads/{l['id']}/assign", headers=h, json={"field": "owner", "user_id": e["id"]})
    requests.patch(f"{API}/leads/{l['id']}/archive", headers=h)
    v3 = get_lead(h, l["id"]).json()["version"]
    assert v < v2 < v3
    stale = requests.put(f"{API}/leads/{l['id']}", headers=h, json={"next_follow_up": "2030-01-01", "expected_version": v})
    assert stale.status_code == 409 and stale.json()["detail"]["conflict"]


def test_bug014_paid_stage_records_payment(mgr):
    h, _ = mgr
    l = lead(h)
    r = requests.patch(f"{API}/leads/{l['id']}/stage", headers=h, json={"status": "Paid"}).json()
    assert r["payment_status"] == "Paid" and r["payment_date"]


def test_bug028_delete_lead_removes_its_tasks(mgr, emp):
    h, _ = mgr
    eh, e = emp
    l = lead(h)
    requests.post(f"{API}/leads/{l['id']}/handover", headers=h, json={"responsibility": "follow_up", "assignee_id": e["id"]})
    assert requests.delete(f"{API}/leads/{l['id']}", headers=h).status_code == 200
    assert not [t for t in requests.get(f"{API}/tasks", headers=eh).json() if t.get("lead_id") == l["id"]]
    assert not [n for n in requests.get(f"{API}/notifications", headers=eh).json() if l["id"] in (n.get("link") or "")]


# ---------------- handover / tasks / RBAC ----------------
def test_bug010_task_handover_grants_access_while_open(mgr, emp):
    h, _ = mgr
    eh, e = emp
    l = lead(h)
    assert get_lead(eh, l["id"]).status_code == 403
    task = requests.post(f"{API}/leads/{l['id']}/handover", headers=h,
                         json={"responsibility": "pricing", "assignee_id": e["id"]}).json()["task"]
    assert get_lead(eh, l["id"]).status_code == 200
    requests.patch(f"{API}/tasks/{task['id']}", headers=eh, json={"status": "Completed"})
    assert get_lead(eh, l["id"]).status_code == 403


def test_bug017_my_tasks_view_is_personal(mgr, emp):
    h, m = mgr
    _, e = emp
    requests.post(f"{API}/tasks", headers=h, json={"title": f"QA {RUN} for emp", "assigned_to": e["id"]})
    mine = requests.get(f"{API}/tasks", headers=h, params={"view": "mine"}).json()
    assert mine is not None and all(t["assigned_to"] == m["id"] for t in mine)


def test_bug021_employee_cannot_silently_reassign(mgr, emp):
    h, m = mgr
    eh, e = emp
    l = lead(eh)
    r = requests.put(f"{API}/leads/{l['id']}", headers=eh, json={"followup_assigned_to": m["id"], "demo_owner": m["id"]})
    assert r.status_code == 200 and r.json()["followup_assigned_to"] == e["id"] and r.json()["demo_owner"] is None
    t = requests.post(f"{API}/tasks", headers=eh, json={"title": f"QA {RUN} own"}).json()
    assert requests.patch(f"{API}/tasks/{t['id']}", headers=eh, json={"assigned_to": m["id"]}).status_code == 403


def test_bug022_task_needs_lead_access(mgr, emp):
    h, _ = mgr
    eh, _ = emp
    secret = lead(h)
    r = requests.post(f"{API}/tasks", headers=eh, json={"title": "x", "lead_id": secret["id"]})
    assert r.status_code == 403
    assert not requests.get(f"{API}/activities", headers=h, params={"lead_id": secret["id"]}).json()


# ---------------- reports / metrics ----------------
def _funnel(h):
    return {f["stage"]: f["count"] for f in requests.get(f"{API}/reports", headers=h, params={"period": "year"}).json()["funnel"]}


def test_bug013_funnel_side_branches(mgr):
    h, _ = mgr
    before = _funnel(h)
    for st in ("Other", "Demo No-show", "Not Paid"):
        lead(h, status=st)
    d = {k: v - before[k] for k, v in _funnel(h).items()}
    assert d["Leads Generated"] == 3
    assert d["Clients Added"] == 0 and d["Invoice Paid"] == 0 and d["Demo Completed"] == 1  # only Not Paid (after invoice)
    assert d["Demo Booked"] == 2 and d["Commercials Opened / Invoice Raised"] == 1


def test_bug024_overdue_metric_matches_list(mgr):
    h, m = mgr
    l = lead(h, next_follow_up="2020-01-01")
    requests.patch(f"{API}/leads/{l['id']}/stage", headers=h, json={"status": "Lost", "lost_reason": "Too expensive"})
    rows = requests.get(f"{API}/performance/team", headers=h, params={"employee": m["id"]}).json()["rows"]
    listed = [x for x in requests.get(f"{API}/leads", headers=h, params={"follow_up": "overdue"}).json()
              if x.get("followup_assigned_to") == m["id"]]
    assert rows[0]["overdue_follow_ups"] == len(listed)


def test_bug026_today_uses_team_timezone(mgr):
    h, _ = mgr
    tz = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Kolkata"))
    assert requests.get(f"{API}/workload", headers=h).json()["today"] == datetime.now(tz).date().isoformat()


def test_bug029_no_show_demos_are_not_upcoming(mgr, emp):
    h, _ = mgr
    _, e = emp
    l = lead(h)
    requests.post(f"{API}/leads/{l['id']}/demo/schedule", headers=h, json={"demo_date": "2099-01-01", "presenter_id": e["id"]})
    row = lambda: [r for r in requests.get(f"{API}/workload", headers=h).json()["rows"] if r["employee_id"] == e["id"]][0]
    before = row()["upcoming_demos"]
    requests.post(f"{API}/leads/{l['id']}/demo/complete", headers=h, json={"demo_status": "No-show"})
    assert row()["upcoming_demos"] == before - 1


def test_bug038_audit_shows_names(mgr, emp):
    h, _ = mgr
    _, e = emp
    l = lead(h)
    requests.patch(f"{API}/leads/{l['id']}/assign", headers=h, json={"field": "owner", "user_id": e["id"]})
    entry = [a for a in requests.get(f"{API}/audit", headers=h).json() if a["entity_id"] == l["id"] and a["action"] == "reassign"][0]
    assert entry["new"] == e["name"]


def test_bug039_calendar_open_ended_range(mgr):
    h, _ = mgr
    assert requests.get(f"{API}/calendar", headers=h, params={"start": "2026-01-01"}).status_code == 200
    assert requests.get(f"{API}/calendar", headers=h, params={"end": "2026-12-31"}).status_code == 200


# ---------------- import / export / settings ----------------
def test_bug025_export_neutralises_formulas(mgr):
    h, _ = mgr
    lead(h, name=f'=HYPERLINK("http://x.example","{RUN}")', phone="+91 " + phone())
    rows = list(csv.reader(io.StringIO(requests.get(f"{API}/export/leads.csv", headers=h).text)))
    row = [r for r in rows if "HYPERLINK" in r[0] and RUN in r[0]][0]
    assert row[0].startswith("'=") and row[1].startswith("+91")


def test_bug005_037_import_reads_cells_as_text(mgr):
    h, _ = mgr
    p1, p2 = phone(), phone()
    content = f"Name,Phone,Status\nQA Imp A {RUN},{p1},contacted\nQA Imp B {RUN},,New Lead\nQA Imp C {RUN},{p2},Hot\n"
    rows = requests.post(f"{API}/import/parse", headers=h, files={"file": ("t.csv", content.encode(), "text/csv")}).json()["rows"]
    assert rows[0]["Phone"] == p1
    res = requests.post(f"{API}/import/commit", headers=h,
                        json={"mapping": {"name": "Name", "phone": "Phone", "status": "Status"}, "rows": rows}).json()
    assert res["imported"] == 2 and res["invalid"] == 1   # "Hot" is not a configured stage
    imported = requests.get(f"{API}/leads", headers=h, params={"search": f"QA Imp A {RUN}"}).json()[0]
    assert imported["phone"] == p1 and imported["status"] == "Contacted"
    assert requests.post(f"{API}/leads/check-duplicate", headers=h, json={"phone": p1}).json()["duplicates"]
    wb = openpyxl.Workbook(); ws = wb.active; ws.append(["Name", "Phone"]); ws.append(["X", 9988776655]); ws.append(["Y", None])
    buf = io.BytesIO(); wb.save(buf)
    rows = requests.post(f"{API}/import/parse", headers=h, files={"file": ("t.xlsx", buf.getvalue())}).json()["rows"]
    assert rows[0]["Phone"] == "9988776655" and rows[1]["Phone"] == ""
    r = requests.post(f"{API}/import/parse", headers=h, files={"file": ("w.csv", "Name,City\nDr. José,Bogotá\n".encode("cp1252"))})
    assert r.status_code == 200 and r.json()["rows"][0]["Name"] == "Dr. José"


def test_bug027_option_rename_cascades_and_protects(admin):
    h, _ = admin
    lost = [o for o in requests.get(f"{API}/options", headers=h, params={"type": "stage"}).json() if o["label"] == "Lost"][0]
    assert requests.patch(f"{API}/options/{lost['id']}", headers=h, json={"label": "Lost Deal"}).status_code == 400
    src = requests.post(f"{API}/options", headers=h, json={"type": "source", "label": f"QA Src {RUN}"}).json()
    l = lead(h, source=f"QA Src {RUN}")
    assert requests.patch(f"{API}/options/{src['id']}", headers=h, json={"label": f"QA Source {RUN}"}).status_code == 200
    assert get_lead(h, l["id"]).json()["source"] == f"QA Source {RUN}"
    requests.patch(f"{API}/options/{src['id']}", headers=h, json={"archived": True})


def test_bug043_required_custom_fields(admin):
    h, _ = admin
    cf = requests.post(f"{API}/custom-fields", headers=h, json={"label": f"QA Req {RUN}", "type": "text", "required": True}).json()
    try:
        assert requests.post(f"{API}/leads", headers=h, json={"name": f"QA {RUN} nocf"}).status_code == 400
        l = lead(h, custom={cf["key"]: "value"})
        r = requests.put(f"{API}/leads/{l['id']}", headers=h, json={"custom": {cf["key"]: ""}})
        assert r.status_code == 400
    finally:
        requests.patch(f"{API}/custom-fields/{cf['id']}", headers=h, json={"archived": True})
