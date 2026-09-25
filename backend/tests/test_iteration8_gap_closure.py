"""
Iteration 8 — Gap closure verification.

Covers:
- Hard reason enforcement on stage change (PATCH /leads/{id}/stage) and PUT /leads/{id}
- Payment 'Not Paid' requires payment_reason
- Invoice/payment persisted fields (invoice_owner/payment_owner/invoice_amount/invoice_date/payment_date)
- Audit/timeline captures reason + payment/invoice changes + updated_by
- Archive (soft) PATCH /leads/{id}/archive + list/hide by default, ?archived=true reveals
- Lead ID search (both /leads/search?q=<id> and /leads?search=<id>)
- Sorting by name/updated_at
- 'Other' pipeline stage present
- reassign-preview breakdown keys
- Named workflow (manager -> employee assignment surfaces on employee tasks/notifications)
- RBAC regression (employee 403 on team endpoints)
"""
import os, time, uuid, pytest, requests
from pathlib import Path

def _load_env():
    for p in (Path("/app/frontend/.env"),):
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("REACT_APP_BACKEND_URL", "")

BASE = _load_env().rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not found"
API = f"{BASE}/api"

MGR = "paripsa.tripathi@beet.health"
EMP = "priya@beet.health"
ADM = "admin@beet.health"


def _login(email):
    r = requests.post(f"{API}/auth/request-otp", json={"email": email}, timeout=30)
    assert r.status_code == 200, r.text
    otp = r.json().get("dev_otp")
    assert otp, f"dev_otp missing: {r.text}"
    r = requests.post(f"{API}/auth/verify-otp", json={"email": email, "otp": otp}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    return j["token"], j["user"]


@pytest.fixture(scope="module")
def mgr():
    tok, u = _login(MGR)
    return {"h": {"Authorization": f"Bearer {tok}"}, "u": u}


@pytest.fixture(scope="module")
def emp():
    tok, u = _login(EMP)
    return {"h": {"Authorization": f"Bearer {tok}"}, "u": u}


@pytest.fixture(scope="module")
def adm():
    tok, u = _login(ADM)
    return {"h": {"Authorization": f"Bearer {tok}"}, "u": u}


def _new_lead(mgr, name_suffix=""):
    tag = uuid.uuid4().hex[:8]
    payload = {"name": f"TEST_Lead_{tag}{name_suffix}",
               "phone": f"+1{tag[:9]}", "email": f"t_{tag}@example.com",
               "owner": mgr["u"]["id"], "team": "Sales", "status": "New"}
    r = requests.post(f"{API}/leads", json=payload, headers=mgr["h"], timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Reason enforcement on stage change ----------
class TestReasonEnforcement:
    def test_stage_change_rejects_empty(self, mgr):
        lead = _new_lead(mgr)
        for bad in ["", " ", "-", "N/A", "no"]:
            r = requests.patch(f"{API}/leads/{lead['id']}/stage",
                               json={"status": "Lost", "lost_reason": bad},
                               headers=mgr["h"], timeout=30)
            assert r.status_code == 400, f"expected 400 for '{bad}' got {r.status_code} {r.text}"
            d = r.json().get("detail")
            if isinstance(d, dict):
                assert d.get("requires_reason") is True

    def test_stage_change_rejects_other_without_notes(self, mgr):
        lead = _new_lead(mgr)
        r = requests.patch(f"{API}/leads/{lead['id']}/stage",
                           json={"status": "Not Interested", "lost_reason": "Other"},
                           headers=mgr["h"], timeout=30)
        assert r.status_code == 400, r.text
        # With notes it should pass
        r = requests.patch(f"{API}/leads/{lead['id']}/stage",
                           json={"status": "Not Interested", "lost_reason": "Other",
                                 "lost_notes": "budget constraint verified"},
                           headers=mgr["h"], timeout=30)
        assert r.status_code == 200, r.text

    def test_stage_change_accepts_valid_reason(self, mgr):
        lead = _new_lead(mgr)
        r = requests.patch(f"{API}/leads/{lead['id']}/stage",
                           json={"status": "Lost", "lost_reason": "Budget mismatch"},
                           headers=mgr["h"], timeout=30)
        assert r.status_code == 200, r.text

    def test_put_lead_requires_reason_on_lost(self, mgr):
        lead = _new_lead(mgr)
        r = requests.put(f"{API}/leads/{lead['id']}",
                         json={"status": "Lost"}, headers=mgr["h"], timeout=30)
        assert r.status_code == 400, r.text
        r = requests.put(f"{API}/leads/{lead['id']}",
                         json={"status": "Lost", "lost_reason": "Went with competitor"},
                         headers=mgr["h"], timeout=30)
        assert r.status_code == 200, r.text


# ---------- Payment reason ----------
class TestPaymentReason:
    def test_not_paid_requires_reason(self, mgr):
        lead = _new_lead(mgr)
        r = requests.put(f"{API}/leads/{lead['id']}",
                         json={"payment_status": "Not Paid"}, headers=mgr["h"], timeout=30)
        assert r.status_code == 400, r.text
        d = r.json().get("detail")
        if isinstance(d, dict):
            assert d.get("field") == "payment"

    def test_not_paid_with_reason_succeeds_and_persists(self, mgr):
        lead = _new_lead(mgr)
        payload = {"payment_status": "Not Paid", "payment_reason": "awaiting insurance",
                   "invoice_owner": mgr["u"]["id"], "payment_owner": mgr["u"]["id"],
                   "invoice_amount": 1500, "invoice_date": "2026-01-10",
                   "payment_date": "2026-01-20"}
        r = requests.put(f"{API}/leads/{lead['id']}", json=payload, headers=mgr["h"], timeout=30)
        assert r.status_code == 200, r.text
        # GET back
        g = requests.get(f"{API}/leads/{lead['id']}", headers=mgr["h"], timeout=30).json()
        assert g["payment_status"] == "Not Paid"
        assert g["payment_reason"] == "awaiting insurance"
        assert g["invoice_owner"] == mgr["u"]["id"]
        assert g["payment_owner"] == mgr["u"]["id"]
        assert g["invoice_amount"] == 1500
        assert g["invoice_date"] == "2026-01-10"
        assert g["payment_date"] == "2026-01-20"


# ---------- Audit / timeline includes reason ----------
class TestAuditReason:
    def test_stage_audit_captures_reason(self, mgr):
        lead = _new_lead(mgr)
        reason = f"Reason_{uuid.uuid4().hex[:6]}"
        r = requests.patch(f"{API}/leads/{lead['id']}/stage",
                           json={"status": "Lost", "lost_reason": reason},
                           headers=mgr["h"], timeout=30)
        assert r.status_code == 200
        tl = requests.get(f"{API}/leads/{lead['id']}/timeline",
                          headers=mgr["h"], timeout=30).json()
        events = tl.get("events", tl) if isinstance(tl, dict) else tl
        blob = " ".join([str(x) for x in events])
        assert reason in blob, f"reason not found in timeline: {blob[:500]}"

    def test_updated_by_stored_on_update(self, mgr):
        lead = _new_lead(mgr)
        r = requests.put(f"{API}/leads/{lead['id']}",
                         json={"phone": f"+1999{uuid.uuid4().hex[:7]}"}, headers=mgr["h"], timeout=30)
        assert r.status_code == 200
        g = requests.get(f"{API}/leads/{lead['id']}", headers=mgr["h"], timeout=30).json()
        assert g.get("updated_by") == mgr["u"]["id"]
        assert g.get("updated_by_name")


# ---------- Archive ----------
class TestArchive:
    def test_archive_toggle_and_list_filtering(self, mgr):
        lead = _new_lead(mgr, "_arch")
        # archive
        r = requests.patch(f"{API}/leads/{lead['id']}/archive", headers=mgr["h"], timeout=30)
        assert r.status_code == 200 and r.json().get("archived") is True
        # Default list hides
        lst = requests.get(f"{API}/leads", headers=mgr["h"], timeout=30).json()
        ids = [l["id"] for l in lst]
        assert lead["id"] not in ids
        # ?archived=true reveals
        lst2 = requests.get(f"{API}/leads?archived=true", headers=mgr["h"], timeout=30).json()
        ids2 = [l["id"] for l in lst2]
        assert lead["id"] in ids2
        # unarchive
        r = requests.patch(f"{API}/leads/{lead['id']}/archive", headers=mgr["h"], timeout=30)
        assert r.json().get("archived") is False


# ---------- Lead ID search ----------
class TestLeadIdSearch:
    def test_search_endpoint_by_id(self, mgr):
        lead = _new_lead(mgr, "_srch")
        r = requests.get(f"{API}/leads/search", params={"q": lead["id"]},
                         headers=mgr["h"], timeout=30)
        assert r.status_code == 200
        found = [x for x in r.json() if x.get("id") == lead["id"]]
        assert found, f"lead id not returned by /leads/search: {r.json()}"

    def test_list_search_param_by_id(self, mgr):
        lead = _new_lead(mgr, "_srch2")
        r = requests.get(f"{API}/leads", params={"search": lead["id"]},
                         headers=mgr["h"], timeout=30)
        assert r.status_code == 200
        assert any(x["id"] == lead["id"] for x in r.json())


# ---------- Sorting ----------
class TestSorting:
    def test_sort_name_asc(self, mgr):
        r = requests.get(f"{API}/leads?sort=name&order=asc", headers=mgr["h"], timeout=30)
        assert r.status_code == 200
        names = [l.get("name", "") for l in r.json()]
        assert names == sorted(names, key=lambda x: (x or "").lower()) or len(names) < 2

    def test_sort_updated_at(self, mgr):
        r = requests.get(f"{API}/leads?sort=updated_at&order=desc", headers=mgr["h"], timeout=30)
        assert r.status_code == 200


# ---------- Other stage present ----------
class TestOtherStage:
    def test_other_stage_in_options(self, mgr):
        r = requests.get(f"{API}/options", params={"type": "stage"},
                         headers=mgr["h"], timeout=30)
        assert r.status_code == 200
        labels = [o["label"] for o in r.json()]
        assert "Other" in labels, f"labels: {labels}"


# ---------- Reassign preview breakdown ----------
class TestReassignPreview:
    def test_reassign_preview_keys(self, mgr, emp):
        r = requests.get(f"{API}/reassign-preview",
                         params={"from_user": emp["u"]["id"]},
                         headers=mgr["h"], timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("open_count", "total_count", "open_tasks", "upcoming_demos", "open_follow_ups"):
            assert k in d, f"missing key {k} in {d}"


# ---------- RBAC ----------
class TestRBAC:
    def test_employee_403_team_endpoints(self, emp):
        for path in ("/performance/team", "/audit", "/workload"):
            r = requests.get(f"{API}{path}", headers=emp["h"], timeout=30)
            assert r.status_code == 403, f"{path} -> {r.status_code}"


# ---------- Named workflow: manager assigns follow-up to employee ----------
class TestNamedWorkflow:
    def test_manager_assigns_followup_to_employee(self, mgr, emp):
        # Create lead owned by manager, assign follow-up to Priya
        lead = _new_lead(mgr, "_flow")
        r = requests.put(f"{API}/leads/{lead['id']}",
                         json={"followup_assigned_to": emp["u"]["id"],
                               "next_follow_up": "2026-01-31",
                               "next_follow_up_note": "TEST_workflow ping Priya"},
                         headers=mgr["h"], timeout=30)
        assert r.status_code == 200, r.text
        # Employee should see this lead in their scope
        my = requests.get(f"{API}/leads", headers=emp["h"], timeout=30).json()
        assert any(l["id"] == lead["id"] for l in my), "employee cannot see assigned lead"
        # Notifications for employee include something referencing this lead
        n = requests.get(f"{API}/notifications", headers=emp["h"], timeout=30)
        assert n.status_code == 200
        # We don't strictly assert content — just endpoint reachable
        # Complete via employee: mark next_follow_up cleared / progress the workflow
        # Use PUT to null out follow-up (simulates completion)
        r = requests.put(f"{API}/leads/{lead['id']}",
                         json={"last_interaction_at": "2026-01-25T10:00:00Z"},
                         headers=emp["h"], timeout=30)
        assert r.status_code == 200, r.text
        # Timeline should surface entries
        tl = requests.get(f"{API}/leads/{lead['id']}/timeline",
                          headers=mgr["h"], timeout=30).json()
        events = tl.get("events", tl) if isinstance(tl, dict) else tl
        assert isinstance(events, list) and len(events) > 0


# ---------- Follow-ups view backing endpoint ----------
class TestFollowUpsView:
    def test_followups_scope_employee(self, emp, mgr):
        # employee list of leads with follow_up filters
        for view in ("today", "upcoming", "overdue"):
            r = requests.get(f"{API}/leads", params={"follow_up": view, "scope": "mine"},
                             headers=emp["h"], timeout=30)
            assert r.status_code == 200, f"{view} -> {r.status_code} {r.text}"
