"""Phase 1 workflow tests: handover, timeline, notifications, expected_version, reasons, task lifecycle."""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or
            open('/app/frontend/.env').read().split('=', 1)[1].strip()).rstrip('/')
API = f"{BASE_URL}/api"

# Clear OTP state to avoid rate limits
try:
    from pymongo import MongoClient
    _env = dict(l.strip().split('=', 1) for l in open('/app/backend/.env') if '=' in l and not l.startswith('#'))
    _mc = MongoClient(_env.get('MONGO_URL', '').strip('"'))
    _db = _mc[_env.get('DB_NAME', '').strip('"')]
    _db.otps.delete_many({})
except Exception as _e:
    _db = None
    print(f"otps preclean skipped: {_e}")

MGR = "paripsa.tripathi@beet.health"
EMP1 = "priya@beet.health"
EMP2 = "arjun@beet.health"
INTERN = "neha@beet.health"


def _h(t): return {"Authorization": f"Bearer {t}"}


def _login(email):
    if _db is not None:
        try:
            _db.otps.delete_many({"email": email.lower()})
        except Exception:
            pass
    r = requests.post(f"{API}/auth/request-otp", json={"email": email}, timeout=15)
    assert r.status_code == 200, r.text
    otp = r.json().get("dev_otp")
    assert otp
    r2 = requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp}, timeout=15)
    assert r2.status_code == 200, r2.text
    return r2.json()


@pytest.fixture(scope="module")
def mgr(): return _login(MGR)


@pytest.fixture(scope="module")
def emp1(): return _login(EMP1)


@pytest.fixture(scope="module")
def emp2(): return _login(EMP2)


@pytest.fixture(scope="module")
def intern(): return _login(INTERN)


def _make_lead(mgr, owner_id, name="TEST_PhaseLead", phone=None):
    payload = {"name": name, "phone": phone or f"+199955510{int(time.time()) % 1000:03d}", "owner": owner_id}
    r = requests.post(f"{API}/leads", json=payload, headers=_h(mgr["token"]))
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Handover ----------
class TestHandover:
    def test_handover_followup_creates_task_and_notification(self, mgr, emp1, emp2):
        lead = _make_lead(mgr, emp1["user"]["id"], name="TEST_HandoverFU")
        lid = lead["id"]
        try:
            payload = {"responsibility": "follow_up", "assignee_id": emp2["user"]["id"],
                       "due_date": "2030-06-01", "due_time": "10:00",
                       "priority": "High", "note": "Please call"}
            r = requests.post(f"{API}/leads/{lid}/handover", json=payload, headers=_h(mgr["token"]))
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["lead"]["followup_assigned_to"] == emp2["user"]["id"]
            task = body["task"]
            assert task and task["status"] == "To Do"
            assert task["assigned_to"] == emp2["user"]["id"]
            assert task["assigned_by"] == mgr["user"]["id"]
            assert task["priority"] == "High"
            # notification exists for assignee
            notifs = requests.get(f"{API}/notifications", headers=_h(emp2["token"])).json()
            assert any(n.get("type") == "assignment" and lid in (n.get("link") or "") for n in notifs), \
                f"no assignment notif in {notifs[:3]}"
            # task appears in assignee task list
            tasks = requests.get(f"{API}/tasks?view=upcoming", headers=_h(emp2["token"])).json()
            assert any(t["id"] == task["id"] for t in tasks)
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))

    def test_handover_owner_updates_ownership_records_audit(self, mgr, emp1, emp2):
        lead = _make_lead(mgr, emp1["user"]["id"], name="TEST_HandoverOwner")
        lid = lead["id"]
        try:
            r = requests.post(f"{API}/leads/{lid}/handover",
                              json={"responsibility": "owner", "assignee_id": emp2["user"]["id"],
                                    "priority": "Medium"},
                              headers=_h(mgr["token"]))
            assert r.status_code == 200, r.text
            assert r.json()["lead"]["owner"] == emp2["user"]["id"]
            hist = requests.get(f"{API}/leads/{lid}/history", headers=_h(mgr["token"])).json()
            assert any(a.get("to") == emp2["user"]["id"] for a in hist.get("assignments", []))
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))

    def test_employee_cannot_reassign_owner(self, mgr, emp1, emp2):
        lead = _make_lead(mgr, emp1["user"]["id"], name="TEST_EmpNoOwnerReassign")
        lid = lead["id"]
        try:
            r = requests.post(f"{API}/leads/{lid}/handover",
                              json={"responsibility": "owner", "assignee_id": emp2["user"]["id"]},
                              headers=_h(emp1["token"]))
            assert r.status_code == 403
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))


# ---------- Timeline ----------
class TestTimeline:
    def test_timeline_human_readable_events(self, mgr, emp1, emp2):
        lead = _make_lead(mgr, emp1["user"]["id"], name="TEST_TimelineLead")
        lid = lead["id"]
        try:
            # trigger a stage change (Contacted)
            requests.patch(f"{API}/leads/{lid}/stage", json={"status": "Contacted"}, headers=_h(emp1["token"]))
            # add an activity
            requests.post(f"{API}/activities",
                          json={"lead_id": lid, "type": "Call", "contact_method": "Call", "outcome": "Interested"},
                          headers=_h(emp1["token"]))
            # a handover
            requests.post(f"{API}/leads/{lid}/handover",
                          json={"responsibility": "follow_up", "assignee_id": emp2["user"]["id"],
                                "priority": "Medium"}, headers=_h(mgr["token"]))
            r = requests.get(f"{API}/leads/{lid}/timeline", headers=_h(mgr["token"]))
            assert r.status_code == 200, r.text
            events = r.json()["events"]
            assert len(events) >= 3, f"only {len(events)} events"
            # human-readable text fields present
            for e in events:
                assert "event" in e and "actor" in e and "timestamp" in e
            kinds = {e.get("kind") for e in events}
            assert "handover" in kinds
            # sorted desc
            ts = [e["timestamp"] for e in events]
            assert ts == sorted(ts, reverse=True)
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))


# ---------- Expected version / concurrent edit ----------
class TestExpectedVersion:
    def test_stale_version_returns_409_conflict(self, mgr, emp1):
        lead = _make_lead(mgr, emp1["user"]["id"], name="TEST_VersionLead")
        lid = lead["id"]
        try:
            current = requests.get(f"{API}/leads/{lid}", headers=_h(mgr["token"])).json()
            v = current.get("version", 1)
            # first update succeeds and bumps version
            r1 = requests.put(f"{API}/leads/{lid}",
                              json={"notes": "first", "expected_version": v},
                              headers=_h(mgr["token"]))
            assert r1.status_code == 200
            # second update with same stale expected_version -> 409 conflict
            r2 = requests.put(f"{API}/leads/{lid}",
                              json={"notes": "second", "expected_version": v},
                              headers=_h(mgr["token"]))
            assert r2.status_code == 409
            detail = r2.json().get("detail", {})
            assert detail.get("conflict") is True
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))

    def test_matching_version_updates_ok(self, mgr, emp1):
        lead = _make_lead(mgr, emp1["user"]["id"], name="TEST_VersionOk")
        lid = lead["id"]
        try:
            v = requests.get(f"{API}/leads/{lid}", headers=_h(mgr["token"])).json().get("version", 1)
            r = requests.put(f"{API}/leads/{lid}",
                             json={"notes": "ok", "expected_version": v},
                             headers=_h(mgr["token"]))
            assert r.status_code == 200
            v2 = requests.get(f"{API}/leads/{lid}", headers=_h(mgr["token"])).json().get("version", 1)
            assert v2 == v + 1
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))


# ---------- Notifications center ----------
class TestNotifications:
    def test_unread_count_and_mark_read(self, mgr, emp1, emp2):
        # generate a notification for emp2 via handover
        lead = _make_lead(mgr, emp1["user"]["id"], name="TEST_NotifLead")
        lid = lead["id"]
        try:
            requests.post(f"{API}/leads/{lid}/handover",
                          json={"responsibility": "follow_up", "assignee_id": emp2["user"]["id"]},
                          headers=_h(mgr["token"]))
            time.sleep(0.5)
            c1 = requests.get(f"{API}/notifications/unread-count", headers=_h(emp2["token"]))
            assert c1.status_code == 200
            assert c1.json()["count"] >= 1
            notifs = requests.get(f"{API}/notifications", headers=_h(emp2["token"])).json()
            assert notifs
            nid = notifs[0]["id"]
            r = requests.post(f"{API}/notifications/{nid}/read", headers=_h(emp2["token"]))
            assert r.status_code == 200
            # mark all
            r2 = requests.post(f"{API}/notifications/read-all", headers=_h(emp2["token"]))
            assert r2.status_code == 200
            assert requests.get(f"{API}/notifications/unread-count", headers=_h(emp2["token"])).json()["count"] == 0
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))

    def test_notifications_scoped_to_user(self, emp1, mgr):
        r = requests.get(f"{API}/notifications", headers=_h(emp1["token"]))
        assert r.status_code == 200
        for n in r.json():
            assert n["user_id"] == emp1["user"]["id"]


# ---------- Task completion notifies assigner + timeline ----------
class TestTaskCompletionFlow:
    def test_complete_handover_task_notifies_assigner_and_logs_activity(self, mgr, emp1, emp2):
        lead = _make_lead(mgr, emp1["user"]["id"], name="TEST_TaskCompleteLead")
        lid = lead["id"]
        try:
            r = requests.post(f"{API}/leads/{lid}/handover",
                              json={"responsibility": "follow_up", "assignee_id": emp2["user"]["id"],
                                    "priority": "Medium"},
                              headers=_h(mgr["token"]))
            tid = r.json()["task"]["id"]
            # snapshot mgr unread
            before = requests.get(f"{API}/notifications/unread-count", headers=_h(mgr["token"])).json()["count"]
            r2 = requests.patch(f"{API}/tasks/{tid}", json={"status": "Completed"}, headers=_h(emp2["token"]))
            assert r2.status_code == 200
            time.sleep(0.5)
            after = requests.get(f"{API}/notifications/unread-count", headers=_h(mgr["token"])).json()["count"]
            assert after >= before + 1, f"assigner not notified: {before} -> {after}"
            # timeline should include a Task Completed / activity event
            tl = requests.get(f"{API}/leads/{lid}/timeline", headers=_h(mgr["token"])).json()["events"]
            assert any("task" in (e.get("event", "") + e.get("text", "")).lower()
                       or "completed" in (e.get("event", "") + e.get("text", "")).lower()
                       for e in tl), f"no completion event: {tl[:5]}"
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))


# ---------- Reasons enforcement via PUT and PATCH stage ----------
class TestReasonsEnforcement:
    @pytest.mark.parametrize("status", ["Not Interested", "Lost"])
    def test_negative_status_requires_reason(self, mgr, emp1, status):
        lead = _make_lead(mgr, emp1["user"]["id"], name=f"TEST_Reason_{status.replace(' ', '')}")
        lid = lead["id"]
        try:
            r = requests.patch(f"{API}/leads/{lid}/stage", json={"status": status}, headers=_h(mgr["token"]))
            assert r.status_code == 400
            body = r.json()
            assert "reason" in str(body).lower() or body.get("detail", {}).get("requires_reason")
            r2 = requests.patch(f"{API}/leads/{lid}/stage",
                                json={"status": status, "lost_reason": "budget"},
                                headers=_h(mgr["token"]))
            assert r2.status_code == 200
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))


# ---------- Security regression ----------
class TestSecurityRegression:
    @pytest.mark.parametrize("path", ["/performance/team", "/audit"])
    def test_employee_forbidden_manager_endpoints(self, emp1, path):
        r = requests.get(f"{API}{path}", headers=_h(emp1["token"]))
        assert r.status_code == 403

    def test_unapproved_email_still_403(self):
        r = requests.post(f"{API}/auth/request-otp", json={"email": "stranger@example.com"})
        assert r.status_code == 403


# ---------- Task assignee dropdown (regression: legacy 'member' role) ----------
class TestTaskAssigneeList:
    def test_manager_users_list_includes_all_active_roles(self, mgr):
        r = requests.get(f"{API}/users", headers=_h(mgr["token"]))
        assert r.status_code == 200
        users = r.json()
        roles = {u["role"] for u in users if u.get("active", True)}
        # ensure at least employee & intern exist; no stale 'member' filter causing empty list
        assert "employee" in roles
        assert len(users) >= 3
