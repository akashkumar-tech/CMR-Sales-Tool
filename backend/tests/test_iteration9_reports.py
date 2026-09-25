"""Iteration 9 — Reports & Sales Funnel tests (backend)."""
import os
import time
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

MANAGER_EMAIL = "paripsa.tripathi@beet.health"
EMPLOYEE_EMAIL = "priya@beet.health"
ADMIN_EMAIL = "admin@beet.health"

FUNNEL_ORDER = ["New Lead", "Contacted", "Interested", "Demo", "Trial", "Pricing", "Invoice", "Payment", "Converted"]
SALES_KEYS = {"leads", "outreach", "responses", "demos", "trials", "follow_ups", "invoices", "payments", "conversions", "losses"}


def _login(email):
    r = requests.post(f"{BASE}/auth/request-otp", json={"email": email}, timeout=15)
    assert r.status_code == 200, r.text
    otp = r.json().get("dev_otp")
    assert otp, r.json()
    r2 = requests.post(f"{BASE}/auth/verify-otp", json={"email": email, "otp": otp}, timeout=15)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    return body["token"], body["user"]


@pytest.fixture(scope="module")
def mgr():
    t, u = _login(MANAGER_EMAIL)
    return {"token": t, "user": u, "h": {"Authorization": f"Bearer {t}"}}


@pytest.fixture(scope="module")
def emp():
    time.sleep(1)
    t, u = _login(EMPLOYEE_EMAIL)
    return {"token": t, "user": u, "h": {"Authorization": f"Bearer {t}"}}


# ---- period parameter ----
@pytest.mark.parametrize("period", ["day", "week", "month", "quarter", "year"])
def test_reports_periods(mgr, period):
    r = requests.get(f"{BASE}/reports?period={period}", headers=mgr["h"], timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "sales" in d and "funnel" in d and "totals" in d
    assert SALES_KEYS.issubset(d["sales"].keys()), f"Missing sales keys: {SALES_KEYS - d['sales'].keys()}"
    for k in SALES_KEYS:
        assert isinstance(d["sales"][k], int), f"sales.{k} not int"
    # Funnel: 9 stages in order
    assert [f["stage"] for f in d["funnel"]] == FUNNEL_ORDER
    counts = [f["count"] for f in d["funnel"]]
    for i in range(len(counts) - 1):
        assert counts[i] >= counts[i + 1], f"Funnel not monotonic non-increasing at {period}: {counts}"
    # pct relative to first stage
    first = counts[0] if counts[0] else 1
    for f in d["funnel"]:
        expected = round(f["count"] / first * 100) if counts[0] else 0
        # allow off-by-1 rounding when count[0] == 0 — pct should be 0
        if counts[0] == 0:
            assert f["pct"] in (0,)
        else:
            assert f["pct"] == expected


def test_reports_custom_range(mgr):
    r = requests.get(f"{BASE}/reports?period=custom&start=2024-01-01&end=2030-12-31", headers=mgr["h"], timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert SALES_KEYS.issubset(d["sales"].keys())
    assert d["sales"]["leads"] >= 0


def test_reports_custom_narrow_range(mgr):
    # Yesterday range should mostly zero out counts
    r = requests.get(f"{BASE}/reports?period=custom&start=1999-01-01&end=1999-01-02", headers=mgr["h"], timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert d["sales"]["leads"] == 0
    assert all(f["count"] == 0 for f in d["funnel"])


# ---- employee/team filter (manager) ----
def _get_priya_id(mgr):
    r = requests.get(f"{BASE}/users", headers=mgr["h"], timeout=15)
    assert r.status_code == 200
    for u in r.json():
        if u["email"] == EMPLOYEE_EMAIL:
            return u["id"]
    pytest.fail("Priya not found")


def test_manager_employee_filter(mgr):
    pid = _get_priya_id(mgr)
    r_all = requests.get(f"{BASE}/reports?period=year", headers=mgr["h"], timeout=20).json()
    r_priya = requests.get(f"{BASE}/reports?period=year&employee={pid}", headers=mgr["h"], timeout=20).json()
    # Priya's slice cannot exceed total
    assert r_priya["sales"]["leads"] <= r_all["sales"]["leads"]
    # by_employee should only contain Priya (or be filtered)
    names = [e["name"] for e in r_priya["by_employee"]]
    assert len(names) <= 1


def test_manager_team_filter(mgr):
    r = requests.get(f"{BASE}/reports?period=year&team=Sales", headers=mgr["h"], timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert SALES_KEYS.issubset(d["sales"].keys())


# ---- permissions ----
def test_employee_scope_isolated(mgr, emp):
    pid = _get_priya_id(mgr)
    # employee's own reports
    r_emp = requests.get(f"{BASE}/reports?period=year", headers=emp["h"], timeout=20).json()
    # by_employee must be empty for employees
    assert r_emp["by_employee"] == [], f"employee by_employee should be empty, got {r_emp['by_employee']}"
    # manager's Priya-scoped
    r_mgr_priya = requests.get(f"{BASE}/reports?period=year&employee={pid}", headers=mgr["h"], timeout=20).json()
    # employee scope (owner OR followup OR demo_owner) is a superset of manager?employee=priya (owner only)
    assert r_emp["sales"]["leads"] >= r_mgr_priya["sales"]["leads"]
    assert r_emp["funnel"][0]["count"] >= r_mgr_priya["funnel"][0]["count"]


def test_employee_cannot_widen_scope(mgr, emp):
    # Employee sending employee=<manager_id> or team should be ignored (still scoped to self)
    r_self = requests.get(f"{BASE}/reports?period=year", headers=emp["h"], timeout=20).json()
    # try to widen using paripsa id
    users = requests.get(f"{BASE}/users", headers=mgr["h"], timeout=15).json()
    mgr_id = next(u["id"] for u in users if u["email"] == MANAGER_EMAIL)
    r_widen = requests.get(f"{BASE}/reports?period=year&employee={mgr_id}&team=Sales", headers=emp["h"], timeout=20).json()
    assert r_widen["sales"]["leads"] == r_self["sales"]["leads"]
    assert r_widen["by_employee"] == []


def test_employee_can_access_reports_endpoint(emp):
    r = requests.get(f"{BASE}/reports?period=month", headers=emp["h"], timeout=20)
    assert r.status_code == 200


# ---- sales totals derived from real data ----
def test_sales_totals_consistency(mgr):
    r = requests.get(f"{BASE}/reports?period=year", headers=mgr["h"], timeout=20).json()
    # demos == by_stage Demo Booked + Demo Completed
    by_stage = {row["stage"]: row["count"] for row in r["by_stage"]}
    assert r["sales"]["demos"] == by_stage.get("Demo Booked", 0) + by_stage.get("Demo Completed", 0)
    assert r["sales"]["conversions"] == by_stage.get("Converted", 0)
    assert r["sales"]["invoices"] == by_stage.get("Invoice Raised", 0)
    assert r["sales"]["payments"] == by_stage.get("Paid", 0)
    assert r["sales"]["trials"] == by_stage.get("Trial", 0)
    assert r["sales"]["leads"] == sum(by_stage.values())


# ---- regression: existing charts arrays present ----
def test_regression_existing_chart_arrays(mgr):
    r = requests.get(f"{BASE}/reports?period=month", headers=mgr["h"], timeout=20).json()
    for key in ["by_stage", "by_source", "by_channel", "by_employee", "daily"]:
        assert key in r and isinstance(r[key], list), f"missing {key}"
