"""Beet.Health CRM backend API test suite (OTP auth + RBAC + dup + config)."""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or
            open('/app/frontend/.env').read().split('=', 1)[1].strip()).rstrip('/')
API = f"{BASE_URL}/api"

# Best-effort clear of OTP rate-limit state before running suite
try:
    from pymongo import MongoClient
    _env = dict(l.strip().split('=', 1) for l in open('/app/backend/.env') if '=' in l and not l.startswith('#'))
    _mc = MongoClient(_env.get('MONGO_URL', '').strip('"'))
    _mc[_env.get('DB_NAME', '').strip('"')].otps.delete_many({})
except Exception as _e:
    print(f"otps preclean skipped: {_e}")

ADMIN = "admin@beet.health"
MGR = "manager@beet.health"
HARRY = "harry@beet.health"
LEO = "leo@beet.health"
BEN = "ben@beet.health"
STRANGER = "stranger@beet.health"


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _login(email):
    # Clear rate-limit state for this email each time to avoid 429 during test setup churn
    try:
        _mc[_env.get('DB_NAME', '').strip('"')].otps.delete_many({"email": email.lower()})
    except Exception:
        pass
    r = requests.post(f"{API}/auth/request-otp", json={"email": email}, timeout=15)
    assert r.status_code == 200, f"request-otp failed: {r.status_code} {r.text}"
    otp = r.json().get("dev_otp")
    assert otp, f"dev_otp missing in response: {r.text}"
    r2 = requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp}, timeout=15)
    assert r2.status_code == 200, f"verify-otp failed: {r2.status_code} {r2.text}"
    return r2.json()  # {token, user}


@pytest.fixture(scope="session")
def admin(): return _login(ADMIN)


@pytest.fixture(scope="session")
def mgr(): return _login(MGR)


@pytest.fixture(scope="session")
def harry(): return _login(HARRY)


@pytest.fixture(scope="session")
def leo(): return _login(LEO)


# ---------- Auth ----------
class TestAuth:
    def test_request_otp_returns_dev_code(self):
        r = requests.post(f"{API}/auth/request-otp", json={"email": HARRY})
        assert r.status_code == 200
        j = r.json()
        assert j["sent"] is True and "dev_otp" in j and len(j["dev_otp"]) == 6

    def test_verify_otp_success(self):
        d = _login(HARRY)
        assert d["token"] and d["user"]["email"] == HARRY
        assert d["user"]["role"] == "employee"

    def test_unapproved_email_rejected(self):
        r = requests.post(f"{API}/auth/request-otp", json={"email": STRANGER})
        assert r.status_code == 403

    def test_wrong_otp(self):
        requests.post(f"{API}/auth/request-otp", json={"email": HARRY})
        r = requests.post(f"{API}/auth/verify-otp", json={"email": HARRY, "otp": "000000"})
        assert r.status_code == 400

    def test_otp_single_use(self):
        try:
            _mc[_env.get('DB_NAME', '').strip('"')].otps.delete_many({"email": HARRY})
        except Exception:
            pass
        r = requests.post(f"{API}/auth/request-otp", json={"email": HARRY})
        otp = r.json()["dev_otp"]
        r1 = requests.post(f"{API}/auth/verify-otp", json={"email": HARRY, "otp": otp})
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/auth/verify-otp", json={"email": HARRY, "otp": otp})
        assert r2.status_code == 400

    def test_me_requires_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code in (401, 403)


# ---------- Deactivation gating ----------
class TestDeactivationGating:
    def test_deactivated_user_cannot_request_otp(self, mgr):
        # find Ben
        users = requests.get(f"{API}/users", headers=_h(mgr["token"])).json()
        ben = next(u for u in users if u["email"] == BEN)
        r = requests.patch(f"{API}/users/{ben['id']}", json={"active": False}, headers=_h(mgr["token"]))
        assert r.status_code == 200
        try:
            r2 = requests.post(f"{API}/auth/request-otp", json={"email": BEN})
            assert r2.status_code == 403
        finally:
            # reactivate
            requests.patch(f"{API}/users/{ben['id']}", json={"active": True}, headers=_h(mgr["token"]))


# ---------- Role scoping ----------
class TestRoleScoping:
    def test_manager_sees_all_leads(self, mgr):
        r = requests.get(f"{API}/leads", headers=_h(mgr["token"]))
        assert r.status_code == 200
        assert len(r.json()) >= 5

    def test_admin_sees_all_leads(self, admin):
        r = requests.get(f"{API}/leads", headers=_h(admin["token"]))
        assert r.status_code == 200

    def test_employee_sees_only_own(self, harry, mgr):
        all_leads = requests.get(f"{API}/leads", headers=_h(mgr["token"])).json()
        r = requests.get(f"{API}/leads", headers=_h(harry["token"]))
        assert r.status_code == 200
        my = r.json()
        assert len(my) < len(all_leads)
        hid = harry["user"]["id"]
        for l in my:
            assert (l.get("owner") == hid or l.get("added_by") == hid
                    or l.get("followup_assigned_to") == hid or l.get("demo_owner") == hid)

    def test_employee_cannot_read_others_lead(self, harry, leo, mgr):
        leads = requests.get(f"{API}/leads", headers=_h(mgr["token"])).json()
        hid = harry["user"]["id"]
        others = [l for l in leads if l.get("owner") != hid and l.get("added_by") != hid
                  and l.get("followup_assigned_to") != hid and l.get("demo_owner") != hid]
        assert others, "No non-Harry leads to test with"
        lid = others[0]["id"]
        r = requests.get(f"{API}/leads/{lid}", headers=_h(harry["token"]))
        assert r.status_code == 403
        r = requests.put(f"{API}/leads/{lid}", json={"notes": "x"}, headers=_h(harry["token"]))
        assert r.status_code == 403
        r = requests.patch(f"{API}/leads/{lid}/stage", json={"status": "Contacted"}, headers=_h(harry["token"]))
        assert r.status_code == 403


# ---------- Global search ----------
class TestGlobalSearch:
    def test_employee_global_search_cross_team(self, harry, mgr):
        # ensure there's a lead named containing 'Sarah' (seeded) somewhere
        leads = requests.get(f"{API}/leads", headers=_h(mgr["token"])).json()
        target = next((l for l in leads if "Sarah" in l.get("name", "")), None)
        q = "Sarah" if target else leads[0]["name"].split()[0]
        r = requests.get(f"{API}/leads/search", params={"q": q}, headers=_h(harry["token"]))
        assert r.status_code == 200
        res = r.json()
        assert len(res) >= 1
        # minimal fields
        for row in res:
            assert set(["id", "name", "status", "owner_name"]).issubset(row.keys())


# ---------- Manager-only endpoints ----------
class TestManagerOnly:
    @pytest.mark.parametrize("method,path,body", [
        ("get", "/performance/team", None),
        ("get", "/audit", None),
        ("get", "/export/leads.csv", None),
        ("post", "/users", {"name": "X", "email": "x@beet.health", "role": "employee"}),
        ("post", "/options", {"type": "source", "label": "TEST_Source"}),
    ])
    def test_employee_forbidden(self, harry, method, path, body):
        fn = getattr(requests, method)
        r = fn(f"{API}{path}", json=body, headers=_h(harry["token"])) if body else fn(f"{API}{path}", headers=_h(harry["token"]))
        assert r.status_code == 403, f"{method} {path} => {r.status_code}"

    def test_employee_cannot_patch_option(self, harry, mgr):
        opts = requests.get(f"{API}/options", params={"type": "source"}, headers=_h(mgr["token"])).json()
        assert opts
        oid = opts[0]["id"]
        r = requests.patch(f"{API}/options/{oid}", json={"label": "nope"}, headers=_h(harry["token"]))
        assert r.status_code == 403


# ---------- Duplicate detection ----------
class TestDuplicates:
    def test_check_duplicate_normalizes_phone(self, mgr):
        r = requests.post(f"{API}/leads/check-duplicate",
                          json={"phone": "+1 (415) 555-0101"}, headers=_h(mgr["token"]))
        assert r.status_code == 200
        dups = r.json()["duplicates"]
        assert any("phone" in d["matched_on"] for d in dups), f"got {dups}"

    def test_create_lead_duplicate_phone_409(self, mgr):
        # find an existing normalized_phone by looking at seeded leads
        leads = requests.get(f"{API}/leads", headers=_h(mgr["token"])).json()
        with_phone = next((l for l in leads if l.get("phone")), None)
        assert with_phone
        r = requests.post(f"{API}/leads",
                          json={"name": "TEST_DupPhone", "phone": with_phone["phone"]},
                          headers=_h(mgr["token"]))
        assert r.status_code == 409

    def test_create_lead_new_phone_ok(self, mgr):
        payload = {"name": "TEST_UniquePhone", "phone": "+19995551234", "email": "TEST_unique@beet.health"}
        r = requests.post(f"{API}/leads", json=payload, headers=_h(mgr["token"]))
        assert r.status_code == 200, r.text
        lid = r.json()["id"]
        # same name allowed
        r2 = requests.post(f"{API}/leads",
                           json={"name": "TEST_UniquePhone", "phone": "+19995551235", "email": "TEST_unique2@beet.health"},
                           headers=_h(mgr["token"]))
        assert r2.status_code == 200
        lid2 = r2.json()["id"]
        requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))
        requests.delete(f"{API}/leads/{lid2}", headers=_h(mgr["token"]))


# ---------- Options / config ----------
class TestConfig:
    def test_admin_add_archive_option(self, admin):
        # add
        r = requests.post(f"{API}/options",
                          json={"type": "source", "label": "TEST_TradeShow"}, headers=_h(admin["token"]))
        assert r.status_code == 200
        oid = r.json()["id"]
        # visible
        opts = requests.get(f"{API}/options", params={"type": "source"}, headers=_h(admin["token"])).json()
        assert any(o["id"] == oid for o in opts)
        # rename
        r = requests.patch(f"{API}/options/{oid}", json={"label": "TEST_TradeShowRenamed"}, headers=_h(admin["token"]))
        assert r.status_code == 200 and r.json()["label"] == "TEST_TradeShowRenamed"
        # archive
        r = requests.patch(f"{API}/options/{oid}", json={"archived": True}, headers=_h(admin["token"]))
        assert r.status_code == 200
        opts = requests.get(f"{API}/options", params={"type": "source"}, headers=_h(admin["token"])).json()
        assert not any(o["id"] == oid for o in opts)

    def test_add_stage_and_use(self, admin, mgr):
        r = requests.post(f"{API}/options",
                          json={"type": "stage", "label": "TEST_Nurture"}, headers=_h(admin["token"]))
        assert r.status_code == 200
        sid = r.json()["id"]
        # create lead using new stage
        r2 = requests.post(f"{API}/leads",
                           json={"name": "TEST_NurtureLead", "phone": "+19995559911", "status": "TEST_Nurture"},
                           headers=_h(mgr["token"]))
        assert r2.status_code == 200
        assert r2.json()["status"] == "TEST_Nurture"
        requests.delete(f"{API}/leads/{r2.json()['id']}", headers=_h(mgr["token"]))
        requests.patch(f"{API}/options/{sid}", json={"archived": True}, headers=_h(admin["token"]))


# ---------- Lost reason enforcement ----------
class TestLostReason:
    def test_lost_requires_reason(self, mgr, harry):
        # create a lead owned by mgr to control
        r = requests.post(f"{API}/leads",
                          json={"name": "TEST_LostReason", "phone": "+19995558801", "owner": harry["user"]["id"]},
                          headers=_h(mgr["token"]))
        assert r.status_code == 200
        lid = r.json()["id"]
        try:
            r1 = requests.patch(f"{API}/leads/{lid}/stage", json={"status": "Lost"}, headers=_h(harry["token"]))
            assert r1.status_code == 400
            body = r1.json()
            # requires_reason flag somewhere in body
            assert "reason" in str(body).lower() or body.get("detail", {}).get("requires_reason")
            r2 = requests.patch(f"{API}/leads/{lid}/stage",
                                json={"status": "Lost", "lost_reason": "budget"}, headers=_h(harry["token"]))
            assert r2.status_code == 200
            assert r2.json()["conversion_status"] == "Lost"
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))


# ---------- Activity + last interaction ----------
class TestActivities:
    def test_activity_updates_last_interaction(self, harry, mgr):
        leads = requests.get(f"{API}/leads", headers=_h(harry["token"])).json()
        assert leads
        lead = leads[0]
        prev_count = lead.get("total_interactions", 0)
        r = requests.post(f"{API}/activities",
                          json={"lead_id": lead["id"], "type": "WhatsApp", "contact_method": "WhatsApp",
                                "outcome": "Interested"}, headers=_h(harry["token"]))
        assert r.status_code == 200, r.text
        refreshed = requests.get(f"{API}/leads/{lead['id']}", headers=_h(harry["token"])).json()
        assert refreshed["total_interactions"] == prev_count + 1
        assert refreshed["last_contact_method"] == "WhatsApp"
        assert refreshed["last_contacted_by_name"] == harry["user"]["name"]
        assert refreshed["last_interaction_at"]

    def test_activity_forbidden_on_unowned_lead(self, harry, mgr):
        leads = requests.get(f"{API}/leads", headers=_h(mgr["token"])).json()
        hid = harry["user"]["id"]
        other = next(l for l in leads if l.get("owner") != hid and l.get("added_by") != hid)
        r = requests.post(f"{API}/activities",
                          json={"lead_id": other["id"], "type": "Call"}, headers=_h(harry["token"]))
        assert r.status_code == 403


# ---------- Assignment / reassignment ----------
class TestAssignment:
    def test_reassign_owner_changes_access(self, mgr, harry, leo):
        r = requests.post(f"{API}/leads",
                          json={"name": "TEST_ReassignFlow", "phone": "+19995558822", "owner": harry["user"]["id"]},
                          headers=_h(mgr["token"]))
        assert r.status_code == 200
        lid = r.json()["id"]
        try:
            # harry can read
            assert requests.get(f"{API}/leads/{lid}", headers=_h(harry["token"])).status_code == 200
            # reassign
            r2 = requests.patch(f"{API}/leads/{lid}/assign",
                                json={"field": "owner", "user_id": leo["user"]["id"]}, headers=_h(mgr["token"]))
            assert r2.status_code == 200
            assert r2.json()["owner"] == leo["user"]["id"]
            # harry now forbidden, leo ok
            assert requests.get(f"{API}/leads/{lid}", headers=_h(harry["token"])).status_code == 403
            assert requests.get(f"{API}/leads/{lid}", headers=_h(leo["token"])).status_code == 200
            # history
            h = requests.get(f"{API}/leads/{lid}/history", headers=_h(leo["token"]))
            assert h.status_code == 200
            body = h.json()
            assert any(a["to"] == leo["user"]["id"] for a in body["assignments"])
            assert any(a.get("field") == "owner" and a.get("new") == leo["user"]["id"] for a in body["audit"])
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))


# ---------- Audit ----------
class TestAudit:
    def test_manager_audit_and_status_change(self, mgr, harry):
        # trigger status change on a harry lead
        leads = requests.get(f"{API}/leads", headers=_h(harry["token"])).json()
        lid = leads[0]["id"]
        prev = leads[0]["status"]
        # pick a different valid stage
        stages = requests.get(f"{API}/options", params={"type": "stage"}, headers=_h(mgr["token"])).json()
        target = next(s["label"] for s in stages if s["label"] != prev and not s.get("requires_reason"))
        requests.patch(f"{API}/leads/{lid}/stage", json={"status": target}, headers=_h(harry["token"]))
        r = requests.get(f"{API}/audit", headers=_h(mgr["token"]))
        assert r.status_code == 200
        entries = r.json()
        assert any(e.get("entity_id") == lid and e.get("field") == "status" for e in entries)


# ---------- Tasks ----------
class TestTasks:
    def test_task_lifecycle(self, harry):
        r = requests.post(f"{API}/tasks",
                          json={"title": "TEST_Task", "due_date": "2030-01-01", "priority": "High"},
                          headers=_h(harry["token"]))
        assert r.status_code == 200
        tid = r.json()["id"]
        assert r.json()["assigned_to"] == harry["user"]["id"]
        assert any(t["id"] == tid for t in requests.get(f"{API}/tasks?view=upcoming", headers=_h(harry["token"])).json())
        r = requests.patch(f"{API}/tasks/{tid}", json={"status": "Completed"}, headers=_h(harry["token"]))
        assert r.status_code == 200 and r.json()["status"] == "Completed" and r.json().get("completed_at")
        assert any(t["id"] == tid for t in requests.get(f"{API}/tasks?view=completed", headers=_h(harry["token"])).json())
        requests.delete(f"{API}/tasks/{tid}", headers=_h(harry["token"]))


# ---------- Reminders (iteration 3) ----------
class TestReminders:
    def test_employee_preview(self, harry):
        r = requests.get(f"{API}/reminders/preview", headers=_h(harry["token"]))
        assert r.status_code == 200
        j = r.json()
        assert "due" in j and "overdue" in j
        assert isinstance(j["due"], list) and isinstance(j["overdue"], list)
        hid = harry["user"]["id"]
        for l in j["due"] + j["overdue"]:
            # scoped to Harry
            assert hid in (l.get("followup_assigned_to"), l.get("owner"))

    def test_employee_cannot_run(self, harry):
        r = requests.post(f"{API}/reminders/run", headers=_h(harry["token"]))
        assert r.status_code == 403

    def test_manager_run(self, mgr):
        r = requests.post(f"{API}/reminders/run", headers=_h(mgr["token"]))
        assert r.status_code == 200
        sent = r.json()["sent"]
        assert isinstance(sent, list)
        for s in sent:
            for k in ("user", "email", "due", "overdue", "emailed"):
                assert k in s

    def test_admin_run(self, admin):
        r = requests.post(f"{API}/reminders/run", headers=_h(admin["token"]))
        assert r.status_code == 200


# ---------- Custom fields (iteration 3) ----------
class TestCustomFields:
    def test_admin_create_list_archive(self, admin):
        r = requests.post(f"{API}/custom-fields",
                          json={"label": "TEST_Deal Size", "type": "dropdown",
                                "options": ["Small", "Medium", "Large"], "show_in_table": True},
                          headers=_h(admin["token"]))
        assert r.status_code == 200, r.text
        cf = r.json()
        assert cf["key"] and "test_deal_size" in cf["key"]
        assert cf["options"] == ["Small", "Medium", "Large"]
        cid = cf["id"]
        # list default excludes archived
        listed = requests.get(f"{API}/custom-fields", headers=_h(admin["token"])).json()
        assert any(c["id"] == cid for c in listed)
        # employee cannot create
        harry_tok = _login(HARRY)["token"]
        r2 = requests.post(f"{API}/custom-fields",
                           json={"label": "TEST_X", "type": "text"}, headers=_h(harry_tok))
        assert r2.status_code == 403
        # archive
        r3 = requests.patch(f"{API}/custom-fields/{cid}", json={"archived": True}, headers=_h(admin["token"]))
        assert r3.status_code == 200
        listed2 = requests.get(f"{API}/custom-fields", headers=_h(admin["token"])).json()
        assert not any(c["id"] == cid for c in listed2)

    def test_lead_custom_persist(self, admin, mgr):
        # create field
        r = requests.post(f"{API}/custom-fields",
                          json={"label": "TEST_DealSize2", "type": "dropdown",
                                "options": ["Small", "Medium", "Large"], "show_in_table": True},
                          headers=_h(admin["token"]))
        assert r.status_code == 200
        cf = r.json(); key = cf["key"]
        # create lead with custom
        r2 = requests.post(f"{API}/leads",
                           json={"name": "TEST_CFLead", "phone": "+19995557001",
                                 "custom": {key: "Large"}}, headers=_h(mgr["token"]))
        assert r2.status_code == 200
        lid = r2.json()["id"]
        try:
            got = requests.get(f"{API}/leads/{lid}", headers=_h(mgr["token"])).json()
            assert got.get("custom", {}).get(key) == "Large"
        finally:
            requests.delete(f"{API}/leads/{lid}", headers=_h(mgr["token"]))
            requests.patch(f"{API}/custom-fields/{cf['id']}", json={"archived": True}, headers=_h(admin["token"]))


# ---------- Filters powering dashboard clickable metrics ----------
class TestLeadFilters:
    def test_filter_status_converted(self, mgr):
        r = requests.get(f"{API}/leads", params={"status": "Converted"}, headers=_h(mgr["token"]))
        assert r.status_code == 200
        for l in r.json():
            assert l["status"] == "Converted"

    def test_filter_status_interested(self, mgr):
        r = requests.get(f"{API}/leads", params={"status": "Interested"}, headers=_h(mgr["token"]))
        assert r.status_code == 200
        for l in r.json():
            assert l["status"] == "Interested"

    def test_filter_followup_overdue(self, mgr):
        import datetime as _dt
        today = _dt.datetime.utcnow().date().isoformat()
        r = requests.get(f"{API}/leads", params={"follow_up": "overdue"}, headers=_h(mgr["token"]))
        assert r.status_code == 200
        for l in r.json():
            assert l.get("next_follow_up") and l["next_follow_up"] < today


# ---------- Tracker import (iteration 3) ----------
class TestImport:
    def _csv(self):
        return ("Name,Phone,Email,Practice,Source\n"
                "TEST_ImpAlice,+15005550101,alice@test.com,Alice Clinic,Instagram\n"
                "TEST_ImpBob,+15005550102,bob@test.com,Bob Physio,Referral\n"
                ",+15005550103,noname@test.com,NoName,Instagram\n"  # blank name -> invalid
                "TEST_ImpDup,+14155550101,dup@test.com,Dup Clinic,Instagram\n"  # duplicate phone with seed
                )

    def test_employee_forbidden_parse(self, harry):
        r = requests.post(f"{API}/import/parse",
                          files={"file": ("t.csv", self._csv(), "text/csv")},
                          headers=_h(harry["token"]))
        assert r.status_code == 403

    def test_employee_forbidden_commit(self, harry):
        r = requests.post(f"{API}/import/commit",
                          json={"mapping": {"name": "Name"}, "rows": []},
                          headers=_h(harry["token"]))
        assert r.status_code == 403

    def test_manager_parse_and_commit(self, mgr):
        parse = requests.post(f"{API}/import/parse",
                              files={"file": ("t.csv", self._csv(), "text/csv")},
                              headers=_h(mgr["token"]))
        assert parse.status_code == 200, parse.text
        pj = parse.json()
        assert "Name" in pj["columns"] and pj["total"] == 4

        commit = requests.post(f"{API}/import/commit",
                               json={"mapping": {"name": "Name", "phone": "Phone", "email": "Email",
                                                 "practice": "Practice", "source": "Source"},
                                     "rows": pj["rows"]},
                               headers=_h(mgr["token"]))
        assert commit.status_code == 200, commit.text
        summary = commit.json()
        assert summary["total"] == 4
        assert summary["invalid"] >= 1
        assert summary["duplicates"] >= 1
        assert summary["imported"] >= 1

        # Verify imported leads appear
        leads = requests.get(f"{API}/leads", params={"search": "TEST_Imp"}, headers=_h(mgr["token"])).json()
        alice = next((l for l in leads if l["name"] == "TEST_ImpAlice"), None)
        assert alice is not None
        # cleanup
        for l in leads:
            if l["name"].startswith("TEST_Imp"):
                requests.delete(f"{API}/leads/{l['id']}", headers=_h(mgr["token"]))


# ---------- CSV export ----------
class TestExport:
    def test_manager_csv(self, mgr):
        r = requests.get(f"{API}/export/leads.csv", headers=_h(mgr["token"]))
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        # header check
        first = r.text.splitlines()[0]
        for col in ("Name", "LinkedIn", "Owner", "Payment Status"):
            assert col in first, f"Missing column {col} in CSV header: {first}"
