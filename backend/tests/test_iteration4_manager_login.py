"""Iteration 4: Verify seeded Manager account paripsa.tripathi@beet.health + demo team.
Focus: Manager OTP login, role=manager, full visibility, add-employee, assign-lead,
security still enforced (unapproved email, employee cannot access manager endpoints).
"""
import os
import uuid
import pytest
import requests

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or
            open('/app/frontend/.env').read().split('=', 1)[1].strip()).rstrip('/')
API = f"{BASE_URL}/api"

# Pre-clean otp rate-limit
try:
    from pymongo import MongoClient
    _env = dict(l.strip().split('=', 1) for l in open('/app/backend/.env') if '=' in l and not l.startswith('#'))
    _mc = MongoClient(_env['MONGO_URL'].strip('"'))
    _db = _mc[_env['DB_NAME'].strip('"')]
    _db.otps.delete_many({})
except Exception as e:
    print(f"otps preclean skipped: {e}")
    _db = None

PARIPSA = "paripsa.tripathi@beet.health"
PRIYA = "priya@beet.health"
ARJUN = "arjun@beet.health"
NEHA = "neha@beet.health"
ADMIN = "admin@beet.health"
STRANGER = f"random_{uuid.uuid4().hex[:6]}@beet.health"


def _h(t): return {"Authorization": f"Bearer {t}"}


def _login(email):
    if _db is not None:
        try:
            _db.otps.delete_many({"email": email.lower()})
        except Exception:
            pass
    r = requests.post(f"{API}/auth/request-otp", json={"email": email}, timeout=15)
    assert r.status_code == 200, f"request-otp {email}: {r.status_code} {r.text}"
    j = r.json()
    otp = j.get("dev_otp")
    assert otp, f"dev_otp missing for {email}: {j}"
    r2 = requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp}, timeout=15)
    assert r2.status_code == 200, f"verify-otp {email}: {r2.status_code} {r2.text}"
    return r2.json()


@pytest.fixture(scope="module")
def paripsa(): return _login(PARIPSA)


@pytest.fixture(scope="module")
def priya(): return _login(PRIYA)


# ---------- Manager OTP login ----------
class TestManagerLogin:
    def test_request_otp_returns_dev_code(self):
        r = requests.post(f"{API}/auth/request-otp", json={"email": PARIPSA})
        assert r.status_code == 200
        j = r.json()
        assert j["sent"] is True
        assert len(j["dev_otp"]) == 6

    def test_verify_otp_role_manager(self, paripsa):
        assert paripsa["token"]
        assert paripsa["user"]["email"] == PARIPSA
        assert paripsa["user"]["role"] == "manager", f"Expected manager, got {paripsa['user']['role']}"
        assert paripsa["user"]["name"] == "Paripsa Tripathi"


# ---------- Manager visibility ----------
class TestManagerVisibility:
    def test_leads_shows_all_8(self, paripsa):
        r = requests.get(f"{API}/leads", headers=_h(paripsa["token"]))
        assert r.status_code == 200
        leads = r.json()
        assert len(leads) >= 8, f"Expected >=8 leads, got {len(leads)}"

    def test_performance_team_ok(self, paripsa):
        r = requests.get(f"{API}/performance/team", headers=_h(paripsa["token"]))
        assert r.status_code == 200
        data = r.json()
        # Should include rows for team members
        assert isinstance(data, (list, dict))
        rows = data if isinstance(data, list) else data.get("rows", data.get("users", []))
        assert len(rows) >= 3, f"Expected rows for team members, got {len(rows)}: {data}"

    def test_teams_endpoint(self, paripsa):
        r = requests.get(f"{API}/teams", headers=_h(paripsa["token"]))
        assert r.status_code == 200
        teams = r.json()
        # Could be list of strings or list of objects
        names = [t if isinstance(t, str) else t.get("name") or t.get("label") for t in teams]
        assert "Sales" in names, f"Sales team missing: {names}"

    def test_users_endpoint(self, paripsa):
        r = requests.get(f"{API}/users", headers=_h(paripsa["token"]))
        assert r.status_code == 200
        users = r.json()
        emails = {u["email"] for u in users}
        for e in [PARIPSA, PRIYA, ARJUN, NEHA, ADMIN]:
            assert e in emails, f"user {e} missing: {emails}"

    def test_audit_ok(self, paripsa):
        r = requests.get(f"{API}/audit", headers=_h(paripsa["token"]))
        assert r.status_code == 200

    def test_reports_ok(self, paripsa):
        r = requests.get(f"{API}/reports", headers=_h(paripsa["token"]))
        assert r.status_code == 200


# ---------- Manager can add employee ----------
class TestManagerAddEmployee:
    def test_add_employee_and_duplicate_empid(self, paripsa):
        unique = uuid.uuid4().hex[:6]
        emp_id = f"TESTEMP-{unique}"
        payload = {"name": "TEST_NewEmp", "email": f"test_newemp_{unique}@beet.health",
                   "role": "employee", "employee_id": emp_id, "team": "Sales"}
        r = requests.post(f"{API}/users", json=payload, headers=_h(paripsa["token"]))
        assert r.status_code in (200, 201), f"add employee failed: {r.status_code} {r.text}"
        created = r.json()
        assert created.get("role") == "employee"
        new_id = created.get("id")

        # Duplicate employee_id
        payload2 = {"name": "TEST_NewEmp2", "email": f"test_newemp2_{unique}@beet.health",
                    "role": "employee", "employee_id": emp_id, "team": "Sales"}
        r2 = requests.post(f"{API}/users", json=payload2, headers=_h(paripsa["token"]))
        assert r2.status_code == 400, f"Expected 400 for dup emp_id, got {r2.status_code} {r2.text}"

        # Cleanup: deactivate new user
        if new_id:
            requests.patch(f"{API}/users/{new_id}", json={"active": False}, headers=_h(paripsa["token"]))


# ---------- Manager can assign/reassign lead ----------
class TestAssignLead:
    def test_reassign_and_preview(self, paripsa):
        # Find priya + arjun ids
        users = requests.get(f"{API}/users", headers=_h(paripsa["token"])).json()
        priya = next(u for u in users if u["email"] == PRIYA)
        arjun = next(u for u in users if u["email"] == ARJUN)

        leads = requests.get(f"{API}/leads", headers=_h(paripsa["token"])).json()
        # find a lead owned by priya
        target = next((l for l in leads if l.get("owner") == priya["id"]), leads[0])
        lid = target["id"]
        original_owner = target.get("owner")
        new_owner = arjun["id"] if original_owner != arjun["id"] else priya["id"]

        r = requests.patch(f"{API}/leads/{lid}/assign",
                           json={"field": "owner", "user_id": new_owner},
                           headers=_h(paripsa["token"]))
        assert r.status_code == 200, f"assign failed: {r.status_code} {r.text}"
        assert r.json().get("owner") == new_owner

        # Reassign preview
        r2 = requests.get(f"{API}/reassign-preview",
                          params={"from_user": new_owner, "to_user": priya["id"]},
                          headers=_h(paripsa["token"]))
        assert r2.status_code == 200, f"reassign-preview: {r2.status_code} {r2.text}"
        body = r2.json()
        assert "open_count" in body and "total_count" in body, f"Missing keys: {body}"

        # Restore original owner
        if original_owner:
            requests.patch(f"{API}/leads/{lid}/assign",
                           json={"field": "owner", "user_id": original_owner},
                           headers=_h(paripsa["token"]))


# ---------- Security still enforced ----------
class TestSecurity:
    def test_unapproved_email_rejected(self):
        r = requests.post(f"{API}/auth/request-otp", json={"email": STRANGER})
        assert r.status_code == 403, f"Expected 403 for stranger, got {r.status_code} {r.text}"

    def test_employee_role_is_employee(self, priya):
        assert priya["user"]["role"] == "employee"

    def test_employee_forbidden_manager_endpoints(self, priya):
        r1 = requests.get(f"{API}/performance/team", headers=_h(priya["token"]))
        assert r1.status_code == 403
        r2 = requests.get(f"{API}/audit", headers=_h(priya["token"]))
        assert r2.status_code == 403
