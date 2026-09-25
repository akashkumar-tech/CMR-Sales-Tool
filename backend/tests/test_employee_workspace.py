"""Employee workspace + RBAC + manager->employee handover round-trip tests."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

EMP = "priya@beet.health"
EMP2 = "arjun@beet.health"
MGR = "paripsa.tripathi@beet.health"
ADMIN = "admin@beet.health"


def _login(email):
    r = requests.post(f"{API}/auth/request-otp", json={"email": email}, timeout=15)
    assert r.status_code == 200, r.text
    otp = r.json().get("dev_otp")
    assert otp, r.json()
    r2 = requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp}, timeout=15)
    assert r2.status_code == 200, r2.text
    return r2.json()["token"], r2.json()["user"]


@pytest.fixture(scope="module")
def emp_ctx():
    tok, u = _login(EMP)
    return {"token": tok, "user": u, "h": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def mgr_ctx():
    tok, u = _login(MGR)
    return {"token": tok, "user": u, "h": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def admin_ctx():
    tok, u = _login(ADMIN)
    return {"token": tok, "user": u, "h": {"Authorization": f"Bearer {tok}"}}


# ---- RBAC ----
def test_employee_perf_team_forbidden(emp_ctx):
    r = requests.get(f"{API}/performance/team", headers=emp_ctx["h"])
    assert r.status_code == 403


def test_employee_audit_forbidden(emp_ctx):
    r = requests.get(f"{API}/audit", headers=emp_ctx["h"])
    assert r.status_code == 403


def test_employee_leads_scoped(emp_ctx):
    r = requests.get(f"{API}/leads", headers=emp_ctx["h"])
    assert r.status_code == 200
    leads = r.json()
    assert isinstance(leads, list)
    uid = emp_ctx["user"]["id"]
    for l in leads:
        involved = (
            l.get("owner_id") == uid
            or l.get("followup_assigned_to") == uid
            or l.get("demo_owner") == uid
        )
        assert involved, f"Lead {l.get('id')} not involving employee: {l}"


def test_employee_perf_me_self(emp_ctx):
    r = requests.get(f"{API}/performance/me", headers=emp_ctx["h"])
    assert r.status_code == 200
    data = r.json()
    # Should be scalar KPIs, not a list per-user
    for k in ["leads_added", "contacted", "responses", "interested", "demos_booked",
              "demos_completed", "follow_ups", "conversions", "tasks_completed", "overdue_follow_ups"]:
        assert k in data, f"Missing KPI {k} in /performance/me: {data}"


def test_manager_perf_team_ok(mgr_ctx):
    r = requests.get(f"{API}/performance/team", headers=mgr_ctx["h"])
    assert r.status_code == 200
    data = r.json()
    rows = data if isinstance(data, list) else data.get("rows")
    assert isinstance(rows, list) and len(rows) > 0


def test_manager_audit_ok(mgr_ctx):
    r = requests.get(f"{API}/audit", headers=mgr_ctx["h"])
    assert r.status_code == 200


def test_admin_dashboards(admin_ctx):
    r = requests.get(f"{API}/performance/team", headers=admin_ctx["h"])
    assert r.status_code == 200
    r2 = requests.get(f"{API}/audit", headers=admin_ctx["h"])
    assert r2.status_code == 200
    r3 = requests.get(f"{API}/users", headers=admin_ctx["h"])
    assert r3.status_code == 200


def test_employee_tasks_scoped(emp_ctx):
    r = requests.get(f"{API}/tasks", headers=emp_ctx["h"])
    assert r.status_code == 200
    tasks = r.json()
    assert isinstance(tasks, list)
    uid = emp_ctx["user"]["id"]
    for t in tasks:
        assert t.get("assigned_to") == uid or t.get("assigned_by") == uid, f"Task not scoped: {t}"


# ---- Full manager -> employee handover round trip ----
def test_manager_to_employee_handover_roundtrip(mgr_ctx, emp_ctx):
    # Find a lead the manager can access; prefer one already owned by priya to keep in scope after
    r = requests.get(f"{API}/leads", headers=mgr_ctx["h"])
    assert r.status_code == 200
    leads = r.json()
    assert leads, "manager sees no leads"
    lead = leads[0]
    lead_id = lead["id"]

    priya_id = emp_ctx["user"]["id"]

    # Notifications baseline for priya
    r_n = requests.get(f"{API}/notifications", headers=emp_ctx["h"])
    assert r_n.status_code == 200
    before_n = len(r_n.json())

    # Handover
    payload = {
        "responsibility": "follow_up",
        "assignee_id": priya_id,
        "due_date": "2026-12-31",
        "priority": "high",
        "note": "TEST_handover_from_pytest",
    }
    r_h = requests.post(f"{API}/leads/{lead_id}/handover", headers=mgr_ctx["h"], json=payload)
    assert r_h.status_code in (200, 201), r_h.text

    time.sleep(0.5)

    # Priya should see the task
    r_t = requests.get(f"{API}/tasks", headers=emp_ctx["h"])
    assert r_t.status_code == 200
    my_tasks = [t for t in r_t.json() if t.get("assigned_to") == priya_id and t.get("lead_id") == lead_id]
    assert my_tasks, f"No task created for priya on {lead_id}"
    new_task = sorted(my_tasks, key=lambda x: x.get("created_at", ""), reverse=True)[0]
    task_id = new_task["id"]

    # Priya notifications increased
    r_n2 = requests.get(f"{API}/notifications", headers=emp_ctx["h"])
    assert r_n2.status_code == 200
    assert len(r_n2.json()) >= before_n + 1

    # Lead timeline has handover event
    r_tl = requests.get(f"{API}/leads/{lead_id}/timeline", headers=mgr_ctx["h"])
    assert r_tl.status_code == 200
    tl = r_tl.json()
    events = tl.get("events", tl) if isinstance(tl, dict) else tl
    assert any(("handover" in (e.get("kind") or "").lower()) or ("TEST_handover_from_pytest" in (e.get("detail") or e.get("text") or "")) for e in events), events[:5]

    # Priya completes task
    r_c = requests.patch(f"{API}/tasks/{task_id}", headers=emp_ctx["h"], json={"status": "Completed"})
    assert r_c.status_code == 200, r_c.text

    time.sleep(0.5)

    # Manager should get a notification (assigner)
    r_mn = requests.get(f"{API}/notifications", headers=mgr_ctx["h"])
    assert r_mn.status_code == 200
    assert any("task" in (n.get("kind") or n.get("type") or "").lower() or "complet" in (n.get("text") or n.get("message") or "").lower() for n in r_mn.json()), r_mn.json()[:3]

    # Lead timeline has task completed event
    r_tl2 = requests.get(f"{API}/leads/{lead_id}/timeline", headers=mgr_ctx["h"])
    assert r_tl2.status_code == 200
    tl2 = r_tl2.json()
    ev2 = tl2.get("events", tl2) if isinstance(tl2, dict) else tl2
    assert any("complet" in (e.get("text") or e.get("event") or "").lower() for e in ev2), ev2[:5]
