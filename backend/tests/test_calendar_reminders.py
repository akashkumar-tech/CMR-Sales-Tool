"""Calendar + reminder regression tests (calendar & reminders audit, CAL-01 … REM-09).

Live HTTP tests like the rest of this suite; they create their own users and data. Run ONLY against a local/dev
backend with OTP_DEV_MODE=true:

    REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests/test_calendar_reminders.py
"""
import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@beet.health")
RUN = uuid.uuid4().hex[:6]
TODAY = datetime.now(ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Kolkata"))).date()
day = lambda n: (TODAY + timedelta(days=n)).isoformat()


def login(email):
    r = requests.post(f"{API}/auth/request-otp", json={"email": email})
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": r.json()["dev_otp"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]


@pytest.fixture(scope="module")
def admin():
    return login(ADMIN_EMAIL)


def _user(admin, role, tag):
    h, _ = admin
    r = requests.post(f"{API}/users", headers=h, json={"name": f"Cal {tag} {RUN}", "email": f"cal.{tag}.{RUN}@beet.health", "role": role})
    assert r.status_code == 200, r.text
    return login(r.json()["email"])


@pytest.fixture(scope="module")
def mgr(admin):
    return _user(admin, "manager", "mgr")


@pytest.fixture(scope="module")
def emp(admin):
    return _user(admin, "employee", "emp")


def cal(h, **extra):
    r = requests.get(f"{API}/calendar", headers=h, params={"start": day(-40), "end": day(80), **extra})
    assert r.status_code == 200, r.text
    return r.json()["events"]


def items(h, lead_id=None, title=None, **extra):
    return [e for e in cal(h, **extra) if (lead_id is None or e.get("lead_id") == lead_id) and (title is None or e.get("title") == title)]


def new_lead(h, **kw):
    r = requests.post(f"{API}/leads", headers=h, json={"name": f"Cal {RUN} {uuid.uuid4().hex[:5]}", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def put(h, lid, **kw):
    v = requests.get(f"{API}/leads/{lid}", headers=h).json()["version"]
    r = requests.put(f"{API}/leads/{lid}", headers=h, json={**kw, "expected_version": v})
    assert r.status_code == 200, r.text
    return r.json()


def open_tasks(h, lid, resp):
    return [t for t in requests.get(f"{API}/tasks", headers=h).json()
            if t.get("lead_id") == lid and t.get("responsibility") == resp and t["status"] not in ("Completed", "Cancelled")]


# ---------------- follow-ups ----------------
def test_followup_moves_with_every_date_change(mgr):
    h, _ = mgr
    l = new_lead(h, next_follow_up=day(10))
    assert [(e["kind"], e["date"]) for e in items(h, l["id"])] == [("followup", day(10))]
    put(h, l["id"], next_follow_up=day(11))
    assert [e["date"] for e in items(h, l["id"])] == [day(11)]
    requests.post(f"{API}/activities", headers=h, json={"lead_id": l["id"], "type": "Call", "notes": "x", "next_follow_up": day(12)})
    assert [e["date"] for e in items(h, l["id"])] == [day(12)]
    put(h, l["id"], next_follow_up="")
    assert items(h, l["id"]) == []


def test_cal05_followup_done_clears_it(mgr):
    h, _ = mgr
    l = new_lead(h, next_follow_up=day(5))
    r = requests.post(f"{API}/activities", headers=h, json={"lead_id": l["id"], "type": "Call", "notes": "spoke", "followup_done": True})
    assert r.status_code == 200 and "Follow-up marked done" in r.json()["notes"]
    assert requests.get(f"{API}/leads/{l['id']}", headers=h).json()["next_follow_up"] is None
    assert items(h, l["id"]) == []
    # done + new date = the next follow-up
    put(h, l["id"], next_follow_up=day(6))
    requests.post(f"{API}/activities", headers=h, json={"lead_id": l["id"], "type": "Call", "notes": "again", "followup_done": True, "next_follow_up": day(9)})
    assert [e["date"] for e in items(h, l["id"])] == [day(9)]


def test_cal04_followup_handover_has_one_date(mgr, emp):
    h, _ = mgr
    eh, e = emp
    l = new_lead(h, next_follow_up=day(3))
    requests.post(f"{API}/leads/{l['id']}/handover", headers=h, json={"responsibility": "follow_up", "assignee_id": e["id"], "due_date": day(7)})
    mine = items(eh, l["id"])
    assert [(x["kind"], x["date"], x["assignee_id"]) for x in mine] == [("followup", day(7), e["id"])]
    assert items(h, l["id"], employee=_mgr_id(h)) == []
    assert len(open_tasks(h, l["id"], "follow_up")) == 1
    # a second handover replaces the first task instead of adding another
    requests.post(f"{API}/leads/{l['id']}/handover", headers=h, json={"responsibility": "follow_up", "assignee_id": e["id"], "due_date": day(8)})
    assert len(open_tasks(h, l["id"], "follow_up")) == 1
    assert [x["date"] for x in items(eh, l["id"])] == [day(8)]


def _mgr_id(h):
    return requests.get(f"{API}/auth/me", headers=h).json()["id"]


def test_followup_task_completion_completes_followup(mgr, emp):
    h, _ = mgr
    eh, e = emp
    l = new_lead(h)
    t = requests.post(f"{API}/leads/{l['id']}/handover", headers=h,
                      json={"responsibility": "follow_up", "assignee_id": e["id"], "due_date": day(4)}).json()["task"]
    assert [x["date"] for x in items(eh, l["id"])] == [day(4)]
    requests.patch(f"{API}/tasks/{t['id']}", headers=eh, json={"status": "Completed"})
    assert items(eh, l["id"]) == []


def test_cal06_07_archived_and_closed_leads_leave_the_calendar(mgr, emp):
    h, _ = mgr
    _, e = emp
    l = new_lead(h, next_follow_up=day(4))
    requests.patch(f"{API}/leads/{l['id']}/archive", headers=h)
    assert items(h, l["id"]) == []
    requests.patch(f"{API}/leads/{l['id']}/archive", headers=h)
    assert len(items(h, l["id"])) == 1
    d = new_lead(h)
    requests.post(f"{API}/leads/{d['id']}/demo/schedule", headers=h, json={"demo_date": day(6), "presenter_id": e["id"]})
    t = requests.post(f"{API}/tasks", headers=h, json={"title": f"Cal {RUN} closed-lead task", "lead_id": d["id"], "due_date": day(6)}).json()
    assert {x["kind"] for x in items(h, d["id"])} == {"demo", "task"}
    requests.patch(f"{API}/leads/{d['id']}/stage", headers=h, json={"status": "Not Interested", "lost_reason": "Not a good fit"})
    assert items(h, d["id"]) == []
    # converted clients keep their tasks (onboarding etc.)
    c = new_lead(h)
    requests.post(f"{API}/tasks", headers=h, json={"title": f"Cal {RUN} onboarding", "lead_id": c["id"], "due_date": day(6)})
    requests.patch(f"{API}/leads/{c['id']}/stage", headers=h, json={"status": "Converted"})
    assert [x["kind"] for x in items(h, c["id"])] == ["task"]


# ---------------- tasks ----------------
def test_cal01_task_status_on_calendar(mgr):
    h, _ = mgr
    title = f"Cal {RUN} status task"
    t = requests.post(f"{API}/tasks", headers=h, json={"title": title, "due_date": day(9), "due_time": "10:30"}).json()
    ev = items(h, title=title)
    assert len(ev) == 1 and ev[0]["task_id"] == t["id"] and ev[0]["done"] is False and ev[0]["time"] == "10:30"
    requests.patch(f"{API}/tasks/{t['id']}", headers=h, json={"status": "Completed"})
    ev = items(h, title=title)
    assert len(ev) == 1 and ev[0]["done"] is True            # kept, flagged done (greyed in the UI)
    requests.patch(f"{API}/tasks/{t['id']}", headers=h, json={"status": "Cancelled"})
    assert items(h, title=title) == []                        # cancelled = hidden


def test_task_edit_and_delete_reflect_on_calendar(mgr, emp):
    h, m = mgr
    eh, e = emp
    title = f"Cal {RUN} edit task"
    t = requests.post(f"{API}/tasks", headers=h, json={"title": title, "due_date": day(2), "assigned_to": e["id"]}).json()
    assert [x["date"] for x in items(eh, title=title)] == [day(2)]
    assert requests.patch(f"{API}/tasks/{t['id']}", headers=eh, json={"due_date": day(3), "due_time": "09:15"}).status_code == 200
    ev = items(eh, title=title)
    assert [(x["date"], x["time"]) for x in ev] == [(day(3), "09:15")]
    assert requests.delete(f"{API}/tasks/{t['id']}", headers=eh).status_code == 200
    assert items(eh, title=title) == []


def test_cal08_admin_items_are_on_the_calendar(admin, mgr):
    ah, a = admin
    h, _ = mgr
    title = f"Cal {RUN} admin task"
    requests.post(f"{API}/tasks", headers=ah, json={"title": title, "due_date": day(4)})
    assert len(items(ah, title=title)) == 1
    assert len(items(h, title=title)) == 1                     # visible in the manager's whole-team view
    assert len(items(h, title=title, employee=a["id"])) == 1


# ---------------- demos ----------------
def test_cal03_demo_is_one_item_through_reschedules_and_presenter_changes(mgr, emp):
    h, m = mgr
    eh, e = emp
    l = new_lead(h)
    requests.post(f"{API}/leads/{l['id']}/demo/schedule", headers=h, json={"demo_date": day(12), "demo_time": "15:00", "presenter_id": e["id"]})
    ev = items(eh, l["id"])
    assert [(x["kind"], x["date"], x["time"]) for x in ev] == [("demo", day(12), "15:00")]
    assert len(open_tasks(h, l["id"], "demo")) == 1
    requests.post(f"{API}/leads/{l['id']}/demo/schedule", headers=h, json={"demo_date": day(14), "demo_time": "11:00", "presenter_id": e["id"]})
    assert [(x["kind"], x["date"]) for x in items(eh, l["id"])] == [("demo", day(14))]
    ot = open_tasks(h, l["id"], "demo")
    assert len(ot) == 1 and ot[0]["due_date"] == day(14)
    put(h, l["id"], demo_date=day(16), demo_time="12:30")
    assert [(x["date"], x["time"]) for x in items(eh, l["id"])] == [(day(16), "12:30")]
    ot = open_tasks(h, l["id"], "demo")
    assert len(ot) == 1 and (ot[0]["due_date"], ot[0]["due_time"]) == (day(16), "12:30")
    put(h, l["id"], demo_owner=m["id"])
    assert items(eh, l["id"]) == []
    assert [x["kind"] for x in items(h, l["id"], employee=m["id"])] == ["demo"]
    ot = open_tasks(h, l["id"], "demo")
    assert len(ot) == 1 and ot[0]["assigned_to"] == m["id"]


def test_cal02_demo_outcomes(mgr, emp):
    h, _ = mgr
    eh, e = emp
    done = new_lead(h)
    requests.post(f"{API}/leads/{done['id']}/demo/schedule", headers=h, json={"demo_date": day(-1), "presenter_id": e["id"]})
    requests.post(f"{API}/leads/{done['id']}/demo/complete", headers=h, json={"demo_status": "Completed"})
    ev = items(eh, done["id"])
    assert len(ev) == 1 and ev[0]["done"] is True and ev[0]["status"] == "Completed"
    assert open_tasks(h, done["id"], "demo") == []
    noshow = new_lead(h)
    requests.post(f"{API}/leads/{noshow['id']}/demo/schedule", headers=h, json={"demo_date": day(-2), "presenter_id": e["id"]})
    requests.post(f"{API}/leads/{noshow['id']}/demo/complete", headers=h, json={"demo_status": "No-show"})
    ev = items(eh, noshow["id"])
    assert len(ev) == 1 and ev[0]["done"] is True and ev[0]["status"] == "No-show"
    cancel = new_lead(h)
    requests.post(f"{API}/leads/{cancel['id']}/demo/schedule", headers=h, json={"demo_date": day(3), "presenter_id": e["id"]})
    requests.post(f"{API}/leads/{cancel['id']}/demo/complete", headers=h, json={"demo_status": "Cancelled"})
    assert items(eh, cancel["id"]) == [] and open_tasks(h, cancel["id"], "demo") == []


# ---------------- scope ----------------
def test_employee_sees_only_own(emp, mgr):
    eh, e = emp
    _, m = mgr
    assert {x["assignee_id"] for x in cal(eh)} <= {e["id"]}
    assert {x["assignee_id"] for x in cal(eh, employee=m["id"])} <= {e["id"]}


# ---------------- reminders ----------------
def test_rem_preview_and_manual_run(admin, mgr, emp):
    h, m = mgr
    eh, e = emp
    due = new_lead(h, next_follow_up=day(0), owner=e["id"])
    overdue = new_lead(h, next_follow_up=day(-2), owner=e["id"])
    archived = new_lead(h, next_follow_up=day(0), owner=e["id"])
    requests.patch(f"{API}/leads/{archived['id']}/archive", headers=h)
    handed = new_lead(h, next_follow_up=day(0))        # owner = manager, follow-up handed to the employee
    requests.post(f"{API}/leads/{handed['id']}/handover", headers=h, json={"responsibility": "follow_up", "assignee_id": e["id"], "create_task": False})
    prev = requests.get(f"{API}/reminders/preview", headers=eh).json()
    got = {l["id"] for l in prev["due"]} | {l["id"] for l in prev["overdue"]}
    assert {due["id"], overdue["id"], handed["id"]} <= got
    assert archived["id"] not in got                                   # REM-04
    mprev = requests.get(f"{API}/reminders/preview", headers=h).json()
    assert handed["id"] not in {l["id"] for l in mprev["due"] + mprev["overdue"]}   # REM-05: only the assignee
    requests.post(f"{API}/tasks", headers=h, json={"title": f"Cal {RUN} task today", "due_date": day(0), "assigned_to": e["id"]})
    dl = new_lead(h)
    requests.post(f"{API}/leads/{dl['id']}/demo/schedule", headers=h, json={"demo_date": day(0), "demo_time": "23:59", "presenter_id": e["id"]})
    r = requests.post(f"{API}/reminders/run", headers=h)
    assert r.status_code == 200
    row = [s for s in r.json()["sent"] if s["email"] == e["email"]][0]
    for k in ("user", "email", "due", "overdue", "tasks", "demos", "emailed"):
        assert k in row
    assert row["tasks"] >= 1 and row["demos"] >= 1                     # REM-01
    assert requests.post(f"{API}/reminders/run", headers=eh).status_code == 403
