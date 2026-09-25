"""Phase 2 backend tests: calendar/demo-workflow/workload + role scoping + team simplification."""
import os
import pytest
import requests
from datetime import date, timedelta

def _read_frontend_env():
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env()).rstrip("/") + "/api"
MGR_EMAIL = "paripsa.tripathi@beet.health"
EMP_EMAIL = "priya@beet.health"
ADMIN_EMAIL = "admin@beet.health"


def _login(email):
    r = requests.post(f"{BASE}/auth/request-otp", json={"email": email}, timeout=15)
    assert r.status_code == 200, r.text
    otp = r.json().get("dev_otp")
    assert otp, "dev_otp missing"
    r2 = requests.post(f"{BASE}/auth/verify-otp", json={"email": email, "otp": otp}, timeout=15)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    return body["token"], body["user"]


@pytest.fixture(scope="module")
def mgr():
    tok, u = _login(MGR_EMAIL)
    return {"token": tok, "user": u, "h": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def emp():
    tok, u = _login(EMP_EMAIL)
    return {"token": tok, "user": u, "h": {"Authorization": f"Bearer {tok}"}}


# ---------- team simplification regression ----------
def test_only_three_users_exist(mgr):
    r = requests.get(f"{BASE}/users", headers=mgr["h"], timeout=15)
    assert r.status_code == 200
    emails = sorted([u["email"] for u in r.json() if u.get("active", True)])
    assert ADMIN_EMAIL in emails
    assert MGR_EMAIL in emails
    assert EMP_EMAIL in emails
    assert "arjun@beet.health" not in emails
    assert "neha@beet.health" not in emails


def test_no_leads_refer_to_deleted_users(mgr):
    r = requests.get(f"{BASE}/leads", headers=mgr["h"], timeout=15)
    assert r.status_code == 200
    leads = r.json() if isinstance(r.json(), list) else r.json().get("leads", [])
    users_r = requests.get(f"{BASE}/users", headers=mgr["h"], timeout=15).json()
    valid_ids = {u["id"] for u in users_r}
    for l in leads:
        for f in ("owner", "demo_owner", "followup_assigned_to"):
            v = l.get(f)
            if v:
                assert v in valid_ids, f"Lead {l.get('name')} field {f} refers to unknown user {v}"


# ---------- calendar role scoping ----------
def test_calendar_manager_sees_team(mgr):
    start = (date.today() - timedelta(days=60)).isoformat()
    end = (date.today() + timedelta(days=90)).isoformat()
    r = requests.get(f"{BASE}/calendar", headers=mgr["h"],
                     params={"start": start, "end": end}, timeout=15)
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) > 0
    kinds = {e["kind"] for e in events}
    assert kinds.issubset({"demo", "followup", "task"})


def test_calendar_manager_employee_filter(mgr, emp):
    start = (date.today() - timedelta(days=60)).isoformat()
    end = (date.today() + timedelta(days=90)).isoformat()
    r = requests.get(f"{BASE}/calendar", headers=mgr["h"],
                     params={"start": start, "end": end, "employee": emp["user"]["id"]}, timeout=15)
    assert r.status_code == 200
    for e in r.json()["events"]:
        assert e["assignee_id"] == emp["user"]["id"]


def test_calendar_employee_sees_only_own(emp):
    start = (date.today() - timedelta(days=60)).isoformat()
    end = (date.today() + timedelta(days=90)).isoformat()
    r = requests.get(f"{BASE}/calendar", headers=emp["h"],
                     params={"start": start, "end": end}, timeout=15)
    assert r.status_code == 200
    for e in r.json()["events"]:
        assert e["assignee_id"] == emp["user"]["id"], f"Leaked event: {e}"


# ---------- workload ----------
def test_workload_manager_ok(mgr, emp):
    r = requests.get(f"{BASE}/workload", headers=mgr["h"], timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body and "today" in body
    ids = {row["employee_id"] for row in body["rows"]}
    assert emp["user"]["id"] in ids
    for row in body["rows"]:
        for k in ("open_leads", "open_tasks", "today_tasks", "overdue_tasks",
                  "upcoming_demos", "open_follow_ups", "overdue_follow_ups"):
            assert k in row and isinstance(row[k], int)


def test_workload_employee_forbidden(emp):
    r = requests.get(f"{BASE}/workload", headers=emp["h"], timeout=15)
    assert r.status_code == 403


# ---------- demo workflow (manager schedules -> Priya presenter -> complete + next action) ----------
@pytest.fixture(scope="module")
def priya_lead(mgr, emp):
    r = requests.get(f"{BASE}/leads", headers=mgr["h"], timeout=15).json()
    leads = r if isinstance(r, list) else r.get("leads", [])
    # pick a lead owned by priya, not terminal
    for l in leads:
        if l.get("owner") == emp["user"]["id"] and l.get("status") not in ("Converted", "Lost", "Closed", "Not Interested"):
            return l
    pytest.skip("No suitable priya-owned lead")


def test_demo_schedule_and_complete_flow(mgr, emp, priya_lead):
    lid = priya_lead["id"]
    demo_date = (date.today() + timedelta(days=3)).isoformat()

    # Schedule
    r = requests.post(f"{BASE}/leads/{lid}/demo/schedule", headers=mgr["h"],
                      json={"demo_date": demo_date, "demo_time": "10:00",
                            "presenter_id": emp["user"]["id"], "note": "TEST_ demo"}, timeout=20)
    assert r.status_code == 200, r.text
    resp = r.json()
    lead = resp["lead"]
    assert lead["status"] == "Demo Booked"
    assert lead["demo_status"] == "Scheduled"
    assert lead["demo_owner"] == emp["user"]["id"]
    assert lead["demo_date"][:10] == demo_date
    assert resp["task"] is not None
    assert emp["user"]["name"].split()[0].lower() in resp["task"]["title"].lower() or \
           priya_lead["name"] in resp["task"]["title"]

    # Verify notification exists for Priya
    n = requests.get(f"{BASE}/notifications", headers=emp["h"], timeout=15).json()
    assert any(item.get("link", "").endswith(lid) or lid in item.get("link", "") for item in n), \
        "Priya should have received a demo assignment notification"

    # Verify timeline event
    tl = requests.get(f"{BASE}/leads/{lid}/timeline", headers=mgr["h"], timeout=15)
    if tl.status_code == 200:
        events = tl.json() if isinstance(tl.json(), list) else tl.json().get("events", [])
        assert any("Demo" in str(e) or "demo" in str(e).lower() for e in events)

    # Complete with next action = Follow-up assigned back to Priya
    due = (date.today() + timedelta(days=5)).isoformat()
    r2 = requests.post(f"{BASE}/leads/{lid}/demo/complete", headers=mgr["h"],
                       json={"demo_status": "Completed", "outcome": "Positive",
                             "new_status": "Proposal Sent",
                             "next_action": "Follow-up",
                             "next_owner_id": emp["user"]["id"],
                             "next_due_date": due,
                             "next_priority": "High"}, timeout=20)
    assert r2.status_code == 200, r2.text
    resp2 = r2.json()
    lead2 = resp2["lead"]
    assert lead2["demo_status"] == "Completed"
    assert lead2["status"] == "Proposal Sent"
    assert lead2.get("followup_assigned_to") == emp["user"]["id"]
    assert lead2.get("next_follow_up", "")[:10] == due
    assert resp2["task"] is not None
    assert "follow" in resp2["task"]["title"].lower()


def test_demo_schedule_requires_active_presenter(mgr, priya_lead):
    r = requests.post(f"{BASE}/leads/{priya_lead['id']}/demo/schedule", headers=mgr["h"],
                      json={"demo_date": (date.today() + timedelta(days=2)).isoformat(),
                            "presenter_id": "nonexistent-id", "note": ""}, timeout=15)
    assert r.status_code == 400


# ---------- phase-1 regression sanity ----------
def test_employee_cannot_access_team_performance(emp):
    r = requests.get(f"{BASE}/performance/team", headers=emp["h"], timeout=15)
    assert r.status_code == 403


def test_employee_cannot_access_audit(emp):
    r = requests.get(f"{BASE}/audit", headers=emp["h"], timeout=15)
    assert r.status_code == 403


def test_notifications_unread_count(emp):
    r = requests.get(f"{BASE}/notifications/unread-count", headers=emp["h"], timeout=15)
    assert r.status_code == 200
    assert "count" in r.json()
