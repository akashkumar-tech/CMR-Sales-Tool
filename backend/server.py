from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from html import escape
import re, io, csv, uuid, random, logging, hashlib, asyncio
import jwt, httpx

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
OTP_DEV_MODE = os.environ.get("OTP_DEV_MODE", "false").lower() == "true"
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Beet.Health CRM")
APP_URL = os.environ.get("APP_URL", "").rstrip("/")
APPROVED_EMAIL_DOMAIN = os.environ.get("APPROVED_EMAIL_DOMAIN", "").strip().lower().lstrip("@")
# Team time zone: defines "today" for follow-ups/tasks, report periods and the morning reminder.
APP_TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Kolkata"))

app = FastAPI()
api = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("beet")

MANAGER_ROLES = ("admin", "manager")
ALL_ROLES = ("admin", "manager", "employee", "intern")
STAFF_ROLES = ("manager", "employee", "intern")

# ---------- default configurable options ----------
DEFAULT_OPTIONS = {
    "stage": [("New Lead", False), ("Contacted", False), ("Replied", False), ("Interested", False),
              ("Demo Booked", False), ("Demo Completed", False), ("Demo No-show", False), ("Rescheduled", False),
              ("Trial", False), ("Pricing Shared", False), ("Follow-up", False), ("Invoice Raised", False),
              ("Payment Pending", False), ("Paid", False), ("Not Paid", False), ("Converted", False),
              ("Not Interested", True), ("Lost", True), ("Closed", True), ("Other", False)],
    "source": [("Instagram", False), ("LinkedIn", False), ("Referral", False), ("Website", False),
               ("WhatsApp", False), ("Cold Outreach", False), ("Clinic Directory", False), ("Other", False)],
    "contact_method": [("Instagram", False), ("LinkedIn", False), ("WhatsApp", False), ("Phone Call", False),
                       ("Email", False), ("Website", False), ("Referral", False), ("Other", False)],
    "activity_type": [("Call", False), ("WhatsApp", False), ("Instagram", False), ("LinkedIn", False),
                      ("Email", False), ("Note", False), ("Demo", False), ("Follow-up", False)],
    "lost_reason": [("Too expensive", False), ("Not interested", False), ("Already using another platform", False),
                    ("Not the decision maker", False), ("Not a good fit", False), ("No response", False),
                    ("Timing issue", False), ("Wants to reconsider later", False), ("Other", False)],
    "demo_status": [("Scheduled", False), ("Completed", False), ("No-show", False), ("Rescheduled", False), ("Cancelled", False)],
    "followup_type": [("Call", False), ("WhatsApp", False), ("Email", False), ("Instagram", False),
                      ("LinkedIn", False), ("Demo Prep", False), ("Other", False)],
    "invoice_status": [("Not Raised", False), ("Raised", False), ("Sent", False)],
    "payment_status": [("Unpaid", False), ("Pending", False), ("Paid", False), ("Not Paid", False)],
}

# ---------- helpers ----------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def today_local():
    """Today's date (YYYY-MM-DD) in the team's time zone — due dates are stored as plain local dates."""
    return datetime.now(APP_TZ).date().isoformat()

def local_day_start_utc(d):
    """UTC ISO timestamp of local midnight at the start of date d (timestamps are stored in UTC)."""
    return datetime(d.year, d.month, d.day, tzinfo=APP_TZ).astimezone(timezone.utc).isoformat()

# Date fields hold "YYYY-MM-DD" strings; None and "" both mean "no date" and must never count as overdue.
HAS_DATE = {"$nin": [None, ""]}
TERMINAL = ["Converted", "Lost", "Closed", "Not Interested"]
# Demo statuses that mean the demo is no longer upcoming ("No Show" = legacy spelling written by older UI).
DEMO_CLOSED = ["Completed", "Cancelled", "No-show", "No Show"]

def norm_email(e):
    return (e or "").strip().lower()

def norm_phone(p):
    if not p:
        return None
    digits = re.sub(r"\D", "", p)
    if not digits:
        return None
    return digits[-10:] if len(digits) > 10 else digits

def norm_handle(h):
    if not h:
        return None
    return re.sub(r"^@+", "", (h or "").strip().lower()) or None

def norm_linkedin(u):
    if not u:
        return None
    u = (u or "").strip().lower().rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u or None

def clean(doc):
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc

def create_token(uid, email):
    return jwt.encode({"sub": uid, "email": email, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access",
                       "jti": uuid.uuid4().hex},
                      JWT_SECRET, algorithm=JWT_ALG)

async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else None
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    if payload.get("jti") and await db.revoked_tokens.find_one({"jti": payload["jti"]}):
        raise HTTPException(401, "Session ended. Please sign in again.")
    request.state.token_payload = payload
    user = await db.users.find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(401, "User not found")
    if not user.get("active", True):
        raise HTTPException(403, "Account deactivated")
    return clean(user)

async def require_manager(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in MANAGER_ROLES:
        raise HTTPException(403, "Manager or admin access required")
    return user

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return user

def is_manager(u):
    return u.get("role") in MANAGER_ROLES

async def audit(actor, action, entity, entity_id, field="", prev="", new="", detail=""):
    await db.audit.insert_one({"id": str(uuid.uuid4()), "actor_id": actor["id"], "actor_name": actor["name"],
                               "action": action, "entity": entity, "entity_id": entity_id, "field": field,
                               "prev": str(prev), "new": str(new), "detail": detail, "timestamp": now_iso()})

PLACEHOLDER_REASONS = {"", "-", "--", "n/a", "na", "none", "null", ".", "..", "tbd", "xx", "n.a."}

def valid_reason(reason, notes=None):
    r = (reason or "").strip()
    if len(r) < 3 or r.lower() in PLACEHOLDER_REASONS:
        return False, "Please choose or type a specific reason (at least 3 characters)."
    if r.lower() == "other" and len((notes or "").strip()) < 3:
        return False, "Please add details in the notes when choosing 'Other'."
    return True, ""

def _is_blank(v):
    return v is None or (isinstance(v, str) and not v.strip()) or v == []

async def missing_required_custom(custom):
    """Labels of required (non-archived) custom fields that have no value in `custom`."""
    req = await db.custom_fields.find({"required": True, "archived": {"$ne": True}}).to_list(200)
    return [f["label"] for f in req if _is_blank((custom or {}).get(f["key"]))]

async def stage_option(label):
    return await db.options.find_one({"type": "stage", "label": label})

def status_updates(new_status, lead, opt, reason=None, notes=None):
    """Fields that must change together with a lead's status, on every path that changes it.
    Callers must have validated the reason already when opt requires one."""
    upd = {}
    if new_status == "Converted":
        upd["conversion_status"] = "Converted"
    elif opt and opt.get("requires_reason"):
        upd.update({"conversion_status": "Lost", "lost_reason": reason, "lost_notes": notes or ""})
    else:  # reopened / progressing lead: clear the previous loss
        upd.update({"conversion_status": "Open", "lost_reason": None, "lost_notes": ""})
    if new_status == "Demo Completed" and lead.get("status") != "Demo Completed":
        upd["demo_completed_at"] = now_iso()
    if new_status == "Paid":
        if lead.get("payment_status") != "Paid":
            upd["payment_status"] = "Paid"
        if not lead.get("payment_date"):
            upd["payment_date"] = now_iso()
    return upd

def _assert_safe_email(subject, html):
    import re as _re
    low = f"{subject}\n{html}".lower()
    for p in ("reply with your password", "reply with the code", "send your password", "cvv",
              "seed phrase", "recovery phrase", "social security number", "confirm your card number",
              "your full card number", "confirm your bank details"):
        if p in low:
            raise ValueError(f"credential-ask phrase: {p}")
    if "<form" in low or "<input" in low:
        raise ValueError("form/input not allowed in email")
    for mm in _re.finditer(r'(?:href|src)="([^"]+)"', html, _re.I):
        u = mm.group(1).strip().lower()
        if u.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not u.startswith("https://"):
            raise ValueError(f"non-https link/asset: {u}")
    return True

async def can_access_lead(user, lead):
    if is_manager(user):
        return True
    uid = user["id"]
    if uid in (lead.get("owner"), lead.get("followup_assigned_to"), lead.get("demo_owner")):
        return True
    # Task-type handovers (pricing, invoice, onboarding…) give access while the assigned task is open.
    return bool(await db.tasks.find_one({"lead_id": lead["id"], "assigned_to": uid,
                                         "status": {"$nin": ["Completed", "Cancelled"]}}))

def lead_scope(user):
    if is_manager(user):
        return {}
    uid = user["id"]
    return {"$or": [{"owner": uid}, {"followup_assigned_to": uid}, {"demo_owner": uid}]}

RESPONSIBILITY_FIELD = {"owner": "owner", "follow_up": "followup_assigned_to", "demo": "demo_owner"}
RESPONSIBILITY_LABELS = {
    "owner": "Lead ownership", "presales": "Pre-sales", "sales": "Sales", "demo": "Demo",
    "follow_up": "Follow-up", "pricing": "Pricing", "invoice": "Invoice", "payment": "Payment follow-up",
    "onboarding": "Client onboarding", "success": "Client success", "other": "Task",
}

async def notify(user_id, ntype, title, body="", link=""):
    if not user_id:
        return
    await db.notifications.insert_one({"id": str(uuid.uuid4()), "user_id": user_id, "type": ntype,
                                       "title": title, "body": body, "link": link, "read": False,
                                       "created_at": now_iso()})

async def send_assignment_email(assignee, actor_name, label, lead, due_date, due_time, priority, note, link):
    if not EMAIL_KEY:
        return
    due_txt = ""
    if due_date:
        due_txt = f" by {escape(due_date)}" + (f" {escape(due_time)}" if due_time else "")
    button = ""
    if APP_URL:
        button = (f'<p style="margin:18px 0"><a href="{APP_URL}{link}" '
                  f'style="background:#E11D6B;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;'
                  f'font-weight:bold;display:inline-block">Open in CRM</a></p>')
    html = (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif">'
            f'<h2 style="color:#E11D6B;margin:0 0 8px">New assignment: {escape(label)}</h2>'
            f'<p>Hi {escape(assignee.get("name") or "there")}, <b>{escape(actor_name)}</b> assigned you '
            f'<b>{escape(label)}</b> for <b>{escape(lead.get("name") or "")}</b>{due_txt}.</p>'
            f'<p>Priority: <b>{escape(priority or "Medium")}</b></p>'
            f'{("<p><b>Note:</b> " + escape(note) + "</p>") if note else ""}'
            f'{button}'
            f'<p style="font-size:12px;color:#888">Sent by {escape(EMAIL_FROM_NAME)}. '
            f'We never ask for your password or codes by email.</p></td></tr></table>')
    try:
        await send_email(assignee.get("email"), f"{EMAIL_FROM_NAME}: {label} assigned — {lead.get('name','')}", html)
    except Exception as e:
        logger.error(f"assignment email failed: {e}")

def _open_resp_tasks(lid, resp):
    return {"lead_id": lid, "responsibility": resp, "status": {"$nin": ["Completed", "Cancelled"]}}

async def sync_resp_tasks(lid, resp, changes):
    """Keep a lead's open demo / follow-up task in step with the lead's own date, time and person."""
    if changes:
        await db.tasks.update_many(_open_resp_tasks(lid, resp), {"$set": changes})

async def close_resp_tasks(lid, resp, status, reason=""):
    stamp = "completed_at" if status == "Completed" else "cancelled_at"
    await db.tasks.update_many(_open_resp_tasks(lid, resp),
                               {"$set": {"status": status, stamp: now_iso(), **({"closed_reason": reason} if reason else {})}})

async def assign_work(lead, responsibility, assignee, by_user, due_date=None, due_time=None,
                      priority="Medium", note="", follow_up_date=None):
    """Single reliable assignment: update lead field + assignment record + audit + task + notify + email."""
    label = RESPONSIBILITY_LABELS.get(responsibility, "Task")
    field = RESPONSIBILITY_FIELD.get(responsibility)
    prev = lead.get(field) if field else None
    prev_name = ""
    if prev:
        pu = await db.users.find_one({"id": prev})
        prev_name = pu["name"] if pu else ""
    upd = {"updated_at": now_iso()}
    if field:
        upd[field] = assignee["id"]
        if responsibility == "owner":
            if lead.get("followup_assigned_to") in (None, prev): upd["followup_assigned_to"] = assignee["id"]
            if lead.get("demo_owner") == prev: upd["demo_owner"] = assignee["id"]
    if responsibility == "follow_up" and follow_up_date:
        upd["next_follow_up"] = follow_up_date
    await db.leads.update_one({"id": lead["id"]}, {"$set": upd, "$inc": {"version": 1}})
    if responsibility in ("demo", "follow_up"):
        await close_resp_tasks(lead["id"], responsibility, "Cancelled", "Replaced by a new assignment")
    await db.assignments.insert_one({"id": str(uuid.uuid4()), "lead_id": lead["id"], "field": responsibility,
                                     "from": prev, "to": assignee["id"], "by": by_user["id"], "by_name": by_user["name"],
                                     "note": note or "", "timestamp": now_iso()})
    await audit(by_user, "reassign", "lead", lead["id"], field=responsibility, prev=prev_name,
                new=assignee["name"], detail=lead["name"])
    task = {"id": str(uuid.uuid4()), "title": f"{label} — {lead['name']}", "lead_id": lead["id"], "lead_name": lead["name"],
            "assigned_to": assignee["id"], "assigned_by": by_user["id"], "assigned_by_name": by_user["name"],
            "due_date": due_date, "due_time": due_time, "priority": priority or "Medium", "status": "To Do",
            "responsibility": responsibility, "notes": note or "", "created_by": by_user["id"], "created_at": now_iso()}
    await db.tasks.insert_one(dict(task))
    link = f"/dashboard?open={lead['id']}"
    if assignee["id"] != by_user["id"]:
        await notify(assignee["id"], "assignment", f"{by_user['name']} assigned you: {label}",
                     lead["name"] + (f" · due {due_date}" if due_date else "") + f" · {priority or 'Medium'}", link)
        await send_assignment_email(assignee, by_user["name"], label, lead, due_date, due_time, priority, note, link)
    return task

# ---------- email ----------
async def send_otp_email(to, code):
    if not EMAIL_KEY:
        return False
    subject = f"Your {EMAIL_FROM_NAME} login code"
    html = (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif">'
            f'<p style="font-size:16px">Your one-time login code for {escape(EMAIL_FROM_NAME)} is:</p>'
            f'<p style="font-size:32px;font-weight:bold;letter-spacing:6px;color:#4F46E5">{escape(code)}</p>'
            f'<p style="color:#555">This code expires in 10 minutes. If you did not request it, you can ignore this email.</p>'
            f'<p style="font-size:12px;color:#888">Sent by {escape(EMAIL_FROM_NAME)}. We never ask for your password or codes by reply.</p>'
            f'</td></tr></table>')
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send", headers={"X-Email-Key": EMAIL_KEY},
                             json={"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME})
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"OTP email failed: {e}")
        return False

async def send_email(to, subject, html):
    if not EMAIL_KEY:
        return False
    try:
        _assert_safe_email(subject, html)
    except ValueError as e:
        logger.error(f"email blocked by safety gate: {e}")
        return False
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send", headers={"X-Email-Key": EMAIL_KEY},
                             json={"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME})
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"email failed: {e}")
        return False

async def send_welcome_email(user, back=False):
    if not EMAIL_KEY:
        return False
    title = "Welcome back to" if back else "Welcome to"
    button = (f'<p style="margin:18px 0"><a href="{escape(APP_URL)}/login" '
              f'style="background:#4F46E5;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;'
              f'font-weight:bold;display:inline-block">Sign in to your CRM</a></p>') if APP_URL else ""
    html = (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif">'
            f'<h2 style="color:#4F46E5;margin:0 0 8px">{title} {escape(EMAIL_FROM_NAME)}</h2>'
            f'<p>Hi {escape(user.get("name") or "there")}, your CRM access is ready.</p>'
            f'<p>Sign in any time using your Beet.Health work email <b>{escape(user.get("email") or "")}</b> — '
            f'we\'ll email you a one-time code, no password needed.</p>'
            f'{button}'
            f'<p style="color:#555">Role: <b>{escape(user.get("role") or "")}</b>'
            f'{(" &middot; Team: <b>" + escape(user.get("team")) + "</b>") if user.get("team") else ""}</p>'
            f'<p style="font-size:12px;color:#888">Sent by {escape(EMAIL_FROM_NAME)}. '
            f'We never ask for your password or codes by email.</p></td></tr></table>')
    return await send_email(user.get("email"), f"{title} {EMAIL_FROM_NAME}", html)

REMINDER_HOUR = 8               # daily digest from 08:00 in APP_TIMEZONE
REMINDER_TICK_SECONDS = 300     # scheduler wake-up interval (catch-up, retries, demo nudges)
REMINDER_MAX_ATTEMPTS = 3       # delivery attempts per reminder before giving up
DEMO_NUDGE_MINUTES = 60         # presenter nudge this long before a demo starts
TASK_CLOSED = ["Completed", "Cancelled"]
CALENDAR_LEAD_RESP = ("demo", "follow_up")   # these tasks are represented by the lead's own demo / follow-up

async def _inactive_user_ids():
    return [u["id"] for u in await db.users.find({"active": False}, {"id": 1}).to_list(2000)]

async def build_user_followups(uid, inactive=None):
    """Follow-ups due today / overdue for the person responsible: the follow-up assignee, or the lead owner
    when there is no (active) assignee. Archived and closed leads are excluded."""
    today = today_local()
    inactive = await _inactive_user_ids() if inactive is None else inactive
    leads = await db.leads.find({"$or": [{"followup_assigned_to": uid},
                                         {"owner": uid, "followup_assigned_to": {"$in": [None, ""] + inactive}}],
                                 "next_follow_up": {**HAS_DATE, "$lte": today + "T99"},
                                 "status": {"$nin": TERMINAL}, "archived": {"$ne": True}}).to_list(500)
    overdue = [l for l in leads if l["next_follow_up"][:10] < today]
    due = [l for l in leads if l["next_follow_up"][:10] == today]
    return due, overdue

async def build_user_digest(uid, inactive=None):
    """Everything a person should act on today: follow-ups, open tasks due/overdue, and today's demos."""
    today = today_local()
    due, overdue = await build_user_followups(uid, inactive)
    tasks = await db.tasks.find({"assigned_to": uid, "status": {"$nin": TASK_CLOSED},
                                 "responsibility": {"$nin": list(CALENDAR_LEAD_RESP)},
                                 "due_date": {**HAS_DATE, "$lte": today + "T99"}}).to_list(500)
    lead_ids = [t["lead_id"] for t in tasks if t.get("lead_id")]
    dead = {l["id"] for l in await db.leads.find({"id": {"$in": lead_ids}, "$or": [
        {"archived": True}, {"status": {"$in": LOST_STATUSES}}]}, {"id": 1}).to_list(1000)}
    tasks = sorted([t for t in tasks if t.get("lead_id") not in dead], key=lambda t: (t["due_date"], t.get("due_time") or ""))
    demos = await db.leads.find({"demo_owner": uid, "demo_date": {"$gte": today, "$lte": today + "T99"},
                                 "demo_status": {"$nin": DEMO_CLOSED}, "status": {"$nin": LOST_STATUSES},
                                 "archived": {"$ne": True}}).to_list(200)
    demos.sort(key=lambda l: l.get("demo_time") or "99")
    return {"due": due, "overdue": overdue, "tasks": tasks, "demos": demos}

async def claim_reminder(kind, key, uid):
    """Atomically take the right to send one reminder (unique per kind/key/user, see startup indexes).
    Returns the log record, or None when it was already sent, is being sent, or ran out of attempts.
    Safe with several backend processes and after restarts."""
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    try:
        return await db.reminder_log.find_one_and_update(
            {"kind": kind, "date": key, "user_id": uid,
             "$or": [{"status": "failed", "attempts": {"$lt": REMINDER_MAX_ATTEMPTS}},
                     {"status": "sending", "updated_at": {"$lt": stale}}]},
            {"$set": {"status": "sending", "updated_at": now_iso()}, "$inc": {"attempts": 1}},
            upsert=True, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        return None

async def finish_reminder(kind, key, uid, status, **extra):
    await db.reminder_log.update_one({"kind": kind, "date": key, "user_id": uid},
                                     {"$set": {"status": status, "updated_at": now_iso(), **extra},
                                      "$setOnInsert": {"attempts": 1}}, upsert=True)

def _crm_link(path, text):
    # The outbound email safety gate only allows https links, so links are added only for an https APP_URL.
    return f' <a href="{escape(APP_URL)}{path}">{escape(text)}</a>' if APP_URL.startswith("https://") else ""

def _digest_html(u, d):
    def section(title, items):
        return (f'<h3 style="margin:18px 0 6px">{escape(title)}</h3><ul>{"".join(items)}</ul>') if items else ""
    overdue_ids = {l["id"] for l in d["overdue"]}
    fu = [f'<li>{escape(l["name"])} — {escape(l.get("practice") or "")} (follow-up {escape(l["next_follow_up"][:10])}'
          f'{", overdue" if l["id"] in overdue_ids else ""}){_crm_link("/dashboard?open=" + l["id"], "Open")}</li>'
          for l in d["overdue"] + d["due"]]
    tk = [f'<li>{escape(t.get("title") or "Task")} — due {escape(t["due_date"][:10])}'
          f'{" " + escape(t["due_time"]) if t.get("due_time") else ""} · {escape(t.get("priority") or "Medium")}'
          f'{_crm_link("/dashboard?open=" + t["lead_id"], "Open lead") if t.get("lead_id") else ""}</li>' for t in d["tasks"]]
    dm = [f'<li>{escape(l.get("demo_time") or "time not set")} — demo with {escape(l["name"])}'
          f'{_crm_link("/dashboard?open=" + l["id"], "Open")}</li>' for l in d["demos"]]
    button = (f'<p style="margin:18px 0"><a href="{escape(APP_URL)}/dashboard" style="background:#E11D6B;color:#fff;'
              f'text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:bold;display:inline-block">Open CRM</a></p>'
              if APP_URL.startswith("https://") else "")
    return (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif">'
            f'<h2 style="color:#4F46E5;margin:0 0 8px">Your plan for today</h2>'
            f'<p>Hi {escape(u["name"])}, you have <b>{len(d["due"])}</b> follow-ups due today, <b>{len(d["overdue"])}</b> overdue, '
            f'<b>{len(d["tasks"])}</b> tasks and <b>{len(d["demos"])}</b> demos.</p>'
            f'{section("Demos today", dm)}{section("Follow-ups", fu)}{section("Tasks due", tk)}{button}'
            f'<p style="font-size:12px;color:#888">Sent by {escape(EMAIL_FROM_NAME)}. '
            f'We never ask for your password or codes by email.</p></td></tr></table>')

async def run_reminders(only_uid=None, force=False):
    """Daily digest. Scheduler (force=False): at most one successful digest per person per day, retried on failure.
    Manual "Send Reminders Now" (force=True): sends now and records it, so the scheduled run skips that person."""
    today = today_local()
    inactive = await _inactive_user_ids()
    sent = []
    for u in await db.users.find({"active": True}).to_list(500):
        if only_uid and u["id"] != only_uid:
            continue
        if not force and not await claim_reminder("digest", today, u["id"]):
            continue
        d = await build_user_digest(u["id"], inactive)
        if not any(d.values()):
            if not force:
                await finish_reminder("digest", today, u["id"], "empty")
            continue
        subject = (f"{EMAIL_FROM_NAME}: {len(d['due'])} due, {len(d['overdue'])} overdue follow-ups · "
                   f"{len(d['tasks'])} tasks · {len(d['demos'])} demos today")
        ok = await send_email(u["email"], subject, _digest_html(u, d))
        await finish_reminder("digest", today, u["id"], "sent" if ok else "failed", manual=force)
        sent.append({"user": u["name"], "email": u["email"], "due": len(d["due"]), "overdue": len(d["overdue"]),
                     "tasks": len(d["tasks"]), "demos": len(d["demos"]), "emailed": ok})
    await db.system.update_one({"key": "last_reminder"}, {"$set": {"key": "last_reminder", "at": now_iso()}}, upsert=True)
    return sent

async def send_demo_nudges():
    """In-app notification + email to the presenter shortly before each of today's demos (once per demo slot)."""
    now = datetime.now(APP_TZ)
    today = now.date().isoformat()
    for l in await db.leads.find({"demo_date": {"$gte": today, "$lte": today + "T99"}, "demo_time": HAS_DATE,
                                  "demo_owner": HAS_DATE, "demo_status": {"$nin": DEMO_CLOSED},
                                  "status": {"$nin": LOST_STATUSES}, "archived": {"$ne": True}}).to_list(1000):
        try:
            hh, mm = (int(x) for x in l["demo_time"][:5].split(":"))
        except ValueError:
            continue
        mins = (now.replace(hour=hh, minute=mm, second=0, microsecond=0) - now).total_seconds() / 60
        if not 0 <= mins <= DEMO_NUDGE_MINUTES:
            continue
        key = f"{today} {l['demo_time'][:5]} {l['id']}"   # a rescheduled demo gets a new nudge
        claim = await claim_reminder("demo_nudge", key, l["demo_owner"])
        if not claim:
            continue
        link = f"/dashboard?open={l['id']}"
        if claim.get("attempts") == 1:   # in-app notification once; only the email is retried
            await notify(l["demo_owner"], "demo_reminder", f"Demo at {l['demo_time'][:5]}: {l['name']}",
                         f"Starts in {max(0, round(mins))} min", link)
        owner = await db.users.find_one({"id": l["demo_owner"], "active": True})
        ok = False
        if owner:
            html = (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif">'
                    f'<h2 style="color:#4F46E5;margin:0 0 8px">Demo at {escape(l["demo_time"][:5])} today</h2>'
                    f'<p>Hi {escape(owner["name"])}, your demo with <b>{escape(l["name"])}</b> starts in about '
                    f'{max(0, round(mins))} minutes.{_crm_link(link, "Open lead")}</p>'
                    f'<p style="font-size:12px;color:#888">Sent by {escape(EMAIL_FROM_NAME)}. '
                    f'We never ask for your password or codes by email.</p></td></tr></table>')
            ok = await send_email(owner["email"], f"{EMAIL_FROM_NAME}: demo at {l['demo_time'][:5]} — {l['name']}", html)
        await finish_reminder("demo_nudge", key, l["demo_owner"], "sent" if ok else "failed", lead_id=l["id"])

async def reminder_tick():
    if datetime.now(APP_TZ).hour >= REMINDER_HOUR:
        res = await run_reminders()
        if res:
            logger.info(f"Daily reminders: {sum(r['emailed'] for r in res)} emailed, {sum(not r['emailed'] for r in res)} failed")
    await send_demo_nudges()

async def reminder_scheduler():
    """Wakes every few minutes. Because each reminder is claimed in reminder_log, a restart after 08:00 still
    sends today's digest (catch-up), failed sends are retried, and several processes never double-send."""
    while True:
        try:
            await reminder_tick()
        except Exception as e:
            logger.error(f"reminder job failed: {e}")
        await asyncio.sleep(REMINDER_TICK_SECONDS)

# ---------- models ----------
class EmailIn(BaseModel):
    email: EmailStr

class VerifyIn(BaseModel):
    email: EmailStr
    otp: str

class UserIn(BaseModel):
    name: str
    email: EmailStr
    role: str = "employee"
    employee_id: Optional[str] = None
    team: Optional[str] = ""
    manager_id: Optional[str] = None
    joining_date: Optional[str] = None
    employment_type: Optional[str] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    team: Optional[str] = None
    manager_id: Optional[str] = None
    joining_date: Optional[str] = None
    employment_type: Optional[str] = None
    active: Optional[bool] = None

# Lead field that stores each option type's label (renames are cascaded to these).
OPTION_LEAD_FIELD = {"stage": "status", "source": "source", "demo_status": "demo_status",
                     "invoice_status": "invoice_status", "payment_status": "payment_status", "lost_reason": "lost_reason"}
# Labels the backend/frontend logic refers to by name (terminal statuses, funnel, KPIs, demo/payment rules).
PROTECTED_OPTION_LABELS = {
    "stage": {"New Lead", "Contacted", "Replied", "Interested", "Demo Booked", "Demo Completed", "Demo No-show",
              "Rescheduled", "Trial", "Pricing Shared", "Invoice Raised", "Payment Pending", "Paid", "Not Paid",
              "Converted", "Not Interested", "Lost", "Closed", "Other"},
    "demo_status": {"Scheduled", "Completed", "No-show", "Cancelled"},
    "payment_status": {"Paid", "Not Paid"},
    "lost_reason": {"Other"},
}

class OptionIn(BaseModel):
    type: str
    label: str
    requires_reason: bool = False

class OptionUpdate(BaseModel):
    label: Optional[str] = None
    order: Optional[int] = None
    archived: Optional[bool] = None
    requires_reason: Optional[bool] = None

class ReorderIn(BaseModel):
    type: str
    ordered_ids: List[str]

NAME_MAX, SHORT_MAX, LONG_MAX = 200, 300, 10000
LEAD_DATE_FIELDS = ("next_follow_up", "demo_date", "invoice_date", "payment_date")

def _check_date(v):
    """Allow None, "" (a cleared date input) or an ISO date/datetime; reject anything else."""
    if v is None or v.strip() == "":
        return v if v is None else ""
    try:
        date.fromisoformat(v.strip()[:10])
    except ValueError:
        raise ValueError("must be a date in YYYY-MM-DD format")
    return v.strip()

def _check_name(v):
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("Lead name is required")
    return v

class LeadIn(BaseModel):
    name: str = Field(max_length=NAME_MAX)
    phone: Optional[str] = Field("", max_length=SHORT_MAX)
    email: Optional[str] = Field("", max_length=SHORT_MAX)
    instagram: Optional[str] = Field("", max_length=SHORT_MAX)
    linkedin: Optional[str] = Field("", max_length=SHORT_MAX)
    practice: Optional[str] = Field("", max_length=SHORT_MAX)
    location: Optional[str] = Field("", max_length=SHORT_MAX)
    source: Optional[str] = Field("", max_length=SHORT_MAX)
    status: str = Field("New Lead", max_length=SHORT_MAX)
    owner: Optional[str] = None
    team: Optional[str] = Field("", max_length=SHORT_MAX)
    notes: Optional[str] = Field("", max_length=LONG_MAX)
    next_follow_up: Optional[str] = None
    followup_assigned_to: Optional[str] = None
    custom: Optional[dict] = None
    force: bool = False

    check_name = field_validator("name")(_check_name)
    check_dates = field_validator("next_follow_up")(_check_date)

class LeadUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=NAME_MAX)
    phone: Optional[str] = Field(None, max_length=SHORT_MAX)
    email: Optional[str] = Field(None, max_length=SHORT_MAX)
    instagram: Optional[str] = Field(None, max_length=SHORT_MAX)
    linkedin: Optional[str] = Field(None, max_length=SHORT_MAX)
    practice: Optional[str] = Field(None, max_length=SHORT_MAX)
    location: Optional[str] = Field(None, max_length=SHORT_MAX)
    source: Optional[str] = Field(None, max_length=SHORT_MAX)
    status: Optional[str] = Field(None, max_length=SHORT_MAX)
    owner: Optional[str] = None
    team: Optional[str] = Field(None, max_length=SHORT_MAX)
    notes: Optional[str] = Field(None, max_length=LONG_MAX)
    next_follow_up: Optional[str] = None
    followup_assigned_to: Optional[str] = None
    demo_date: Optional[str] = None
    demo_time: Optional[str] = Field(None, pattern=r"^(|\d{2}:\d{2}(:\d{2})?)$")
    demo_owner: Optional[str] = None
    demo_status: Optional[str] = Field(None, max_length=SHORT_MAX)
    invoice_status: Optional[str] = Field(None, max_length=SHORT_MAX)
    payment_status: Optional[str] = Field(None, max_length=SHORT_MAX)
    invoice_owner: Optional[str] = None
    payment_owner: Optional[str] = None
    invoice_amount: Optional[float] = Field(None, ge=0)
    invoice_date: Optional[str] = None
    payment_date: Optional[str] = None
    payment_reason: Optional[str] = Field(None, max_length=SHORT_MAX)
    conversion_status: Optional[str] = Field(None, max_length=SHORT_MAX)
    lost_reason: Optional[str] = Field(None, max_length=SHORT_MAX)
    lost_notes: Optional[str] = Field(None, max_length=LONG_MAX)
    response: Optional[str] = Field(None, max_length=LONG_MAX)
    custom: Optional[dict] = None
    expected_version: Optional[int] = None

    check_name = field_validator("name")(_check_name)
    check_dates = field_validator(*LEAD_DATE_FIELDS)(_check_date)

class AssignIn(BaseModel):
    field: str  # owner | followup_assigned_to | demo_owner
    user_id: str

class StageIn(BaseModel):
    status: str
    lost_reason: Optional[str] = None
    lost_notes: Optional[str] = None

class ActivityIn(BaseModel):
    lead_id: str
    type: str
    contact_method: Optional[str] = ""
    notes: Optional[str] = ""
    outcome: Optional[str] = ""
    next_action: Optional[str] = ""
    next_follow_up: Optional[str] = None
    followup_done: bool = False   # this interaction completes the lead's current follow-up

class TaskIn(BaseModel):
    title: str
    lead_id: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: str = "Medium"
    status: str = "To Do"
    notes: Optional[str] = ""
    responsibility: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    assigned_to: Optional[str] = None

class DupIn(BaseModel):
    phone: Optional[str] = ""
    email: Optional[str] = ""
    instagram: Optional[str] = ""
    linkedin: Optional[str] = ""

# ---------- auth ----------
@api.post("/auth/request-otp")
async def request_otp(body: EmailIn):
    email = norm_email(body.email)
    user = await db.users.find_one({"email": email})
    if not user or not user.get("active", True):
        raise HTTPException(403, "This email is not approved for CRM access. Contact your admin.")
    # rate limit: max 5 in 10 min
    since = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    recent = await db.otps.count_documents({"email": email, "created_at": {"$gte": since}})
    if recent >= 5:
        raise HTTPException(429, "Too many OTP requests. Please try again later.")
    code = f"{random.randint(0, 999999):06d}"
    await db.otps.insert_one({"id": str(uuid.uuid4()), "email": email,
                              "code_hash": hashlib.sha256(code.encode()).hexdigest(),
                              "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                              "used": False, "created_at": now_iso()})
    sent = await send_otp_email(email, code)
    if OTP_DEV_MODE:
        logger.info(f"OTP for {email}: {code} (emailed={sent})")
        return {"sent": True, "email": email, "dev_otp": code, "dev_mode": True}
    # Production: the code is only ever delivered by email — never in the response or logs.
    logger.info(f"OTP requested for {email} (emailed={sent})")
    if not sent:
        raise HTTPException(503, "We couldn't send your login code right now. Please try again in a few minutes.")
    return {"sent": True, "email": email}

OTP_MAX_FAILED_ATTEMPTS = 5   # wrong codes allowed per email per 10 minutes

@api.post("/auth/verify-otp")
async def verify_otp(body: VerifyIn):
    email = norm_email(body.email)
    since = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    if await db.otp_failures.count_documents({"email": email, "created_at": {"$gte": since}}) >= OTP_MAX_FAILED_ATTEMPTS:
        raise HTTPException(429, "Too many incorrect codes. Please wait 10 minutes and request a new code.")
    rec = await db.otps.find_one({"email": email, "code_hash": hashlib.sha256(body.otp.encode()).hexdigest(), "used": False},
                                 sort=[("created_at", -1)])
    if not rec:
        await db.otp_failures.insert_one({"email": email, "created_at": now_iso()})
        raise HTTPException(400, "Invalid code. Please check and try again.")
    await db.otp_failures.delete_many({"email": email})
    if rec["expires_at"] < now_iso():
        raise HTTPException(400, "Code expired. Please request a new one.")
    await db.otps.update_one({"id": rec["id"]}, {"$set": {"used": True}})
    user = await db.users.find_one({"email": email})
    if not user or not user.get("active", True):
        raise HTTPException(403, "Account not active.")
    await db.users.update_one({"id": user["id"]}, {"$set": {"last_login": now_iso()}})
    token = create_token(user["id"], user["email"])
    return {"token": token, "user": clean(user)}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

@api.post("/auth/logout")
async def logout(request: Request, user: dict = Depends(get_current_user)):
    payload = request.state.token_payload
    if payload.get("jti"):
        await db.revoked_tokens.insert_one({"jti": payload["jti"], "user_id": user["id"],
                                            "expires_at": datetime.fromtimestamp(payload["exp"], timezone.utc)})
    return {"ok": True}

# ---------- users ----------
@api.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    if is_manager(user):
        users = await db.users.find({}).to_list(1000)
        return [clean(u) for u in users]
    # Non-managers get a minimal team directory (for assignee dropdowns) — no private HR/perf fields.
    users = await db.users.find({"active": True}).to_list(1000)
    return [{"id": u["id"], "name": u["name"], "role": u["role"], "team": u.get("team"), "active": u.get("active", True)} for u in users]

@api.post("/users")
async def create_user(body: UserIn, mgr: dict = Depends(require_manager)):
    if body.role not in ALL_ROLES:
        raise HTTPException(400, "Invalid role")
    if body.role == "admin" and mgr.get("role") != "admin":
        raise HTTPException(403, "Only admin can create admins")
    email = norm_email(body.email)
    if APPROVED_EMAIL_DOMAIN and not email.endswith("@" + APPROVED_EMAIL_DOMAIN):
        raise HTTPException(400, f"Only @{APPROVED_EMAIL_DOMAIN} work emails can be added")
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "A user with this email already exists")
    emp_id = (body.employee_id or "").strip() or None
    if emp_id and await db.users.find_one({"employee_id": emp_id}):
        raise HTTPException(400, "This Employee ID is already in use")
    doc = {"id": str(uuid.uuid4()), "name": body.name, "email": email, "role": body.role,
           "employee_id": emp_id, "team": body.team or "", "manager_id": body.manager_id,
           "joining_date": body.joining_date, "employment_type": body.employment_type or "",
           "active": True, "created_by": mgr["id"], "created_at": now_iso()}
    await db.users.insert_one(dict(doc))
    await audit(mgr, "create", "user", doc["id"], detail=f"Added {body.name} ({body.role})")
    try:
        await send_welcome_email(doc)
    except Exception as e:
        logger.error(f"welcome email failed: {e}")
    return clean(doc)

@api.patch("/users/{uid}")
async def update_user(uid: str, body: UserUpdate, mgr: dict = Depends(require_manager)):
    u = await db.users.find_one({"id": uid})
    if not u:
        raise HTTPException(404, "Not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates.get("role") == u.get("role"):
        updates.pop("role")   # edit forms always send the current role; only a real change needs admin
    if mgr.get("role") != "admin" and u.get("role") in MANAGER_ROLES and uid != mgr["id"]:
        raise HTTPException(403, "Only admin can change admin or manager accounts")
    if updates.get("active") is False and uid == mgr["id"]:
        raise HTTPException(400, "You can't deactivate your own account")
    if "role" in updates:
        if mgr.get("role") != "admin":
            raise HTTPException(403, "Only admin can change roles")
        if updates["role"] not in ALL_ROLES:
            raise HTTPException(400, "Invalid role")
    if updates.get("active") is False and u.get("role") == "admin":
        if await db.users.count_documents({"role": "admin", "active": True}) <= 1:
            raise HTTPException(400, "Cannot deactivate the last active admin")
    await db.users.update_one({"id": uid}, {"$set": updates})
    for k, v in updates.items():
        await audit(mgr, "update", "user", uid, field=k, prev=u.get(k, ""), new=v)
    if updates.get("active") is True and not u.get("active", True):
        try:
            await send_welcome_email({**u, **updates}, back=True)
        except Exception as e:
            logger.error(f"welcome email failed: {e}")
    return clean(await db.users.find_one({"id": uid}))

class BulkReassignIn(BaseModel):
    from_user: str
    to_user: str
    include_closed: bool = False

@api.post("/leads/bulk-reassign")
async def bulk_reassign(body: BulkReassignIn, mgr: dict = Depends(require_manager)):
    if body.from_user == body.to_user:
        raise HTTPException(400, "Pick a different target owner")
    target = await db.users.find_one({"id": body.to_user, "active": True})
    if not target:
        raise HTTPException(400, "Pick an active team member")
    source = await db.users.find_one({"id": body.from_user})
    from_name = source["name"] if source else body.from_user
    q = {"owner": body.from_user}
    if not body.include_closed:
        q["status"] = {"$nin": ["Converted", "Lost", "Closed", "Not Interested"]}
    leads = await db.leads.find(q).to_list(5000)
    for l in leads:
        updates = {"owner": body.to_user, "updated_at": now_iso()}
        if l.get("followup_assigned_to") in (None, body.from_user):
            updates["followup_assigned_to"] = body.to_user
        if l.get("demo_owner") == body.from_user:
            updates["demo_owner"] = body.to_user
        await db.leads.update_one({"id": l["id"]}, {"$set": updates, "$inc": {"version": 1}})
        await db.assignments.insert_one({"id": str(uuid.uuid4()), "lead_id": l["id"], "field": "owner",
                                         "from": body.from_user, "to": body.to_user, "by": mgr["id"],
                                         "by_name": mgr["name"], "timestamp": now_iso()})
        await audit(mgr, "reassign", "lead", l["id"], field="owner", prev=from_name, new=target["name"], detail=l["name"])
    return {"reassigned": len(leads)}

@api.get("/teams")
async def list_teams(user: dict = Depends(get_current_user)):
    teams = await db.users.distinct("team")
    return sorted([t for t in teams if t])

@api.get("/reassign-preview")
async def reassign_preview(from_user: str, include_closed: bool = False, mgr: dict = Depends(require_manager)):
    q = {"owner": from_user}
    total = await db.leads.count_documents(q)
    if not include_closed:
        q["status"] = {"$nin": ["Converted", "Lost", "Closed", "Not Interested"]}
    open_count = await db.leads.count_documents(q)
    today = today_local()
    open_tasks = await db.tasks.count_documents({"assigned_to": from_user, "status": {"$nin": ["Completed", "Cancelled"]}})
    upcoming_demos = await db.leads.count_documents({"demo_owner": from_user, "demo_date": {"$gte": today}, "demo_status": {"$nin": DEMO_CLOSED}})
    open_follow_ups = await db.leads.count_documents({"followup_assigned_to": from_user, "next_follow_up": HAS_DATE, "status": {"$nin": ["Converted", "Lost", "Closed", "Not Interested"]}})
    return {"open_count": open_count, "total_count": total, "open_tasks": open_tasks,
            "upcoming_demos": upcoming_demos, "open_follow_ups": open_follow_ups}

class SavedFilterIn(BaseModel):
    name: str
    filters: dict

@api.get("/saved-filters")
async def list_saved_filters(user: dict = Depends(get_current_user)):
    items = await db.saved_filters.find({"user_id": user["id"]}).sort("created_at", 1).to_list(100)
    return [clean(i) for i in items]

@api.post("/saved-filters")
async def create_saved_filter(body: SavedFilterIn, user: dict = Depends(get_current_user)):
    doc = {"id": str(uuid.uuid4()), "user_id": user["id"], "name": body.name,
           "filters": body.filters, "created_at": now_iso()}
    await db.saved_filters.insert_one(dict(doc))
    return clean(doc)

@api.delete("/saved-filters/{fid}")
async def delete_saved_filter(fid: str, user: dict = Depends(get_current_user)):
    await db.saved_filters.delete_one({"id": fid, "user_id": user["id"]})
    return {"ok": True}

@api.get("/users/{uid}/activity")
async def user_activity(uid: str, mgr: dict = Depends(require_manager)):
    acts = await db.activities.find({"employee_id": uid}).sort("timestamp", -1).to_list(200)
    return [clean(a) for a in acts]

# ---------- options / config ----------
@api.get("/options")
async def get_options(type: Optional[str] = None, include_archived: bool = False, user: dict = Depends(get_current_user)):
    q = {} if include_archived else {"archived": {"$ne": True}}
    if type:
        q["type"] = type
        opts = await db.options.find(q).sort("order", ASCENDING).to_list(500)
        return [clean(o) for o in opts]
    opts = await db.options.find(q).sort("order", ASCENDING).to_list(2000)
    grouped = {}
    for o in opts:
        grouped.setdefault(o["type"], []).append(clean(o))
    return grouped

@api.post("/options")
async def add_option(body: OptionIn, adm: dict = Depends(require_manager)):
    existing = await db.options.find({"type": body.type}).sort("order", -1).to_list(1)
    order = (existing[0]["order"] + 1) if existing else 0
    doc = {"id": str(uuid.uuid4()), "type": body.type, "label": body.label, "order": order,
           "archived": False, "requires_reason": body.requires_reason}
    await db.options.insert_one(dict(doc))
    await audit(adm, "create", "option", doc["id"], detail=f"{body.type}: {body.label}")
    return clean(doc)

@api.patch("/options/{oid}")
async def update_option(oid: str, body: OptionUpdate, adm: dict = Depends(require_manager)):
    o = await db.options.find_one({"id": oid})
    if not o:
        raise HTTPException(404, "Not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    new_label = (updates.get("label") or "").strip()
    renaming = "label" in updates and new_label != o["label"]
    if renaming:
        if not new_label:
            raise HTTPException(400, "Option name can't be empty")
        if o["label"] in PROTECTED_OPTION_LABELS.get(o["type"], ()):
            raise HTTPException(400, f"\"{o['label']}\" is used by built-in rules and reports and can't be renamed. "
                                     "Add a new option instead.")
        if await db.options.find_one({"type": o["type"], "label": new_label, "id": {"$ne": oid}}):
            raise HTTPException(400, f"\"{new_label}\" already exists")
        updates["label"] = new_label
    await db.options.update_one({"id": oid}, {"$set": updates})
    if renaming and OPTION_LEAD_FIELD.get(o["type"]):
        # Leads store the label itself, so carry existing records over to the new name.
        fld = OPTION_LEAD_FIELD[o["type"]]
        await db.leads.update_many({fld: o["label"]}, {"$set": {fld: new_label}, "$inc": {"version": 1}})
    await audit(adm, "update", "option", oid, detail=f"{o['type']}: {updates}")
    return clean(await db.options.find_one({"id": oid}))

@api.post("/options/reorder")
async def reorder_options(body: ReorderIn, adm: dict = Depends(require_manager)):
    for i, oid in enumerate(body.ordered_ids):
        await db.options.update_one({"id": oid, "type": body.type}, {"$set": {"order": i}})
    return {"ok": True}

# ---------- leads ----------
@api.get("/leads")
async def list_leads(request: Request, user: dict = Depends(get_current_user)):
    p = request.query_params
    q = lead_scope(user)
    if p.get("scope") == "mine":
        q = {"$or": [{"owner": user["id"]}, {"followup_assigned_to": user["id"]}, {"demo_owner": user["id"]}]}
    for f in ("status", "source", "owner", "team", "demo_status", "payment_status", "invoice_status"):
        if p.get(f):
            q[f] = p.get(f)
    if p.get("assigned_to"):
        q["owner"] = p.get("assigned_to")
    if p.get("follow_up"):
        today = today_local()
        fu = p.get("follow_up")
        if fu == "overdue":
            q["next_follow_up"] = {**HAS_DATE, "$lt": today}
            q["status"] = {"$nin": ["Converted", "Lost", "Closed", "Not Interested"]}
        elif fu == "today":
            q["next_follow_up"] = today
        elif fu == "upcoming":
            q["next_follow_up"] = {"$gt": today}
    if not p.get("include_archived") and p.get("archived") != "true":
        q["archived"] = {"$ne": True}
    elif p.get("archived") == "true":
        q["archived"] = True
    if p.get("search"):
        raw = p.get("search")
        s = re.escape(raw)  # literal text search — user input is not a regex
        q["$and"] = q.get("$and", []) + [{"$or": [
            {"name": {"$regex": s, "$options": "i"}}, {"practice": {"$regex": s, "$options": "i"}},
            {"phone": {"$regex": s, "$options": "i"}}, {"email": {"$regex": s, "$options": "i"}},
            {"instagram": {"$regex": s, "$options": "i"}}, {"linkedin": {"$regex": s, "$options": "i"}},
            {"id": raw}]}]
    sort_field = p.get("sort") or "created_at"
    if sort_field not in ("created_at", "updated_at", "name", "status", "next_follow_up", "last_interaction_at"):
        sort_field = "created_at"
    order = -1 if (p.get("order") or "desc") == "desc" else 1
    leads = await db.leads.find(q).sort(sort_field, order).to_list(3000)
    return [clean(l) for l in leads]

@api.get("/leads/search")
async def search_leads(q: str = "", user: dict = Depends(get_current_user)):
    """Global lookup across ALL leads (duplicate prevention / coordinated outreach) — minimal fields."""
    if not q or len(q) < 2:
        return []
    rx = {"$regex": re.escape(q), "$options": "i"}  # literal text search
    leads = await db.leads.find({"$or": [{"name": rx}, {"phone": rx}, {"email": rx}, {"instagram": rx}, {"linkedin": rx}, {"id": q}]}).limit(25).to_list(25)
    users = {u["id"]: u["name"] for u in await db.users.find({}).to_list(1000)}
    return [{"id": l["id"], "name": l["name"], "phone": l.get("phone"), "email": l.get("email"),
             "status": l.get("status"), "owner_name": users.get(l.get("owner"), "—"),
             "last_interaction_at": l.get("last_interaction_at"), "last_contacted_by": l.get("last_contacted_by_name"),
             "practice": l.get("practice")} for l in leads]

@api.post("/leads/check-duplicate")
async def check_dup(body: DupIn, user: dict = Depends(get_current_user)):
    ors = []
    np_, ne = norm_phone(body.phone), norm_email(body.email) or None
    ni, nl = norm_handle(body.instagram), norm_linkedin(body.linkedin)
    if np_: ors.append({"normalized_phone": np_})
    if ne: ors.append({"normalized_email": ne})
    if ni: ors.append({"normalized_instagram": ni})
    if nl: ors.append({"normalized_linkedin": nl})
    if not ors:
        return {"duplicates": []}
    found = await db.leads.find({"$or": ors}).to_list(10)
    users = {u["id"]: u["name"] for u in await db.users.find({}).to_list(1000)}
    out = []
    for l in found:
        matched = []
        if np_ and l.get("normalized_phone") == np_: matched.append("phone")
        if ne and l.get("normalized_email") == ne: matched.append("email")
        if ni and l.get("normalized_instagram") == ni: matched.append("instagram")
        if nl and l.get("normalized_linkedin") == nl: matched.append("linkedin")
        out.append({"id": l["id"], "name": l["name"], "phone": l.get("phone"), "email": l.get("email"),
                    "status": l.get("status"), "owner_name": users.get(l.get("owner"), "—"),
                    "matched_on": matched, "last_interaction_at": l.get("last_interaction_at"),
                    "last_contacted_by": l.get("last_contacted_by_name")})
    return {"duplicates": out}

@api.post("/leads")
async def create_lead(body: LeadIn, user: dict = Depends(get_current_user)):
    np_, ne = norm_phone(body.phone), norm_email(body.email) or None
    ni, nl = norm_handle(body.instagram), norm_linkedin(body.linkedin)
    dup_q = []
    if np_: dup_q.append({"normalized_phone": np_})
    if ne: dup_q.append({"normalized_email": ne})
    if ni: dup_q.append({"normalized_instagram": ni})
    if nl: dup_q.append({"normalized_linkedin": nl})
    if dup_q:
        existing = await db.leads.find_one({"$or": dup_q})
        if existing:
            raise HTTPException(409, {"message": "Existing lead found. This contact already exists in the CRM.",
                                      "existing_id": existing["id"], "existing_name": existing["name"]})
    missing = await missing_required_custom(body.custom or {})
    if missing:
        raise HTTPException(400, f"Please fill in required field(s): {', '.join(missing)}")
    owner = body.owner if (is_manager(user) and body.owner) else user["id"]
    if owner != user["id"] and not await db.users.find_one({"id": owner, "active": True}):
        raise HTTPException(400, "Pick an active team member as owner")
    lid = str(uuid.uuid4())
    doc = {"id": lid, "name": body.name, "phone": body.phone or "", "email": body.email or "",
           "instagram": body.instagram or "", "linkedin": body.linkedin or "", "practice": body.practice or "",
           "location": body.location or "", "source": body.source or "", "status": body.status,
           "owner": owner, "team": body.team or "", "added_by": user["id"], "added_by_name": user["name"],
           "notes": body.notes or "", "next_follow_up": body.next_follow_up or None,
           "followup_assigned_to": body.followup_assigned_to or owner,
           "demo_date": None, "demo_time": None, "demo_owner": None, "demo_status": None,
           "invoice_status": None, "payment_status": None, "conversion_status": "Open",
           "custom": body.custom or {},
           "response": "", "last_interaction_at": None, "last_contacted_by": None,
           "last_contacted_by_name": None, "last_contact_method": None, "total_interactions": 0,
           "created_at": now_iso(), "updated_at": now_iso(), "version": 1}
    if np_: doc["normalized_phone"] = np_
    if ne: doc["normalized_email"] = ne
    if ni: doc["normalized_instagram"] = ni
    if nl: doc["normalized_linkedin"] = nl
    try:
        await db.leads.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(409, {"message": "Existing lead found. This contact already exists in the CRM."})
    await audit(user, "create", "lead", lid, detail=f"Created lead {body.name}")
    return clean(doc)

@api.get("/leads/{lid}")
async def get_lead(lid: str, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lid})
    if not lead:
        raise HTTPException(404, "Not found")
    if not await can_access_lead(user, lead):
        raise HTTPException(403, "You do not have access to this lead")
    return clean(lead)

@api.put("/leads/{lid}")
async def update_lead(lid: str, body: LeadUpdate, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lid})
    if not lead:
        raise HTTPException(404, "Not found")
    if not await can_access_lead(user, lead):
        raise HTTPException(403, "Access denied")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    ev = updates.pop("expected_version", None)
    if ev is not None and lead.get("version", 1) != ev:
        raise HTTPException(409, {"message": "This lead was just updated by someone else. Reload to see the latest version before saving.", "conflict": True})
    if "owner" in updates and not is_manager(user):
        updates.pop("owner")
    if not is_manager(user):
        # Follow-up / demo reassignment goes through Assign/Handover (audited + notified), not a plain edit.
        for f in ("followup_assigned_to", "demo_owner"):
            if f in updates and updates[f] != lead.get(f):
                updates.pop(f)
    for f in ("owner", "followup_assigned_to", "demo_owner", "invoice_owner", "payment_owner"):
        if updates.get(f) and updates[f] != lead.get(f) and not await db.users.find_one({"id": updates[f], "active": True}):
            raise HTTPException(400, "Pick an active team member")
    # A cleared date/time input arrives as "" — store it as "no date" so it never counts as overdue.
    for f in LEAD_DATE_FIELDS + ("demo_time",):
        if updates.get(f) == "":
            updates[f] = None
    if "custom" in updates:
        prev_custom = lead.get("custom") or {}
        cleared = [lbl for lbl in await missing_required_custom(updates["custom"])
                   if lbl not in await missing_required_custom(prev_custom)]
        if cleared:
            raise HTTPException(400, f"Required field(s) can't be left empty: {', '.join(cleared)}")
    # normalization + duplicate guard on unique fields
    if "phone" in updates:
        np_ = norm_phone(updates["phone"])
        if np_ and await db.leads.find_one({"normalized_phone": np_, "id": {"$ne": lid}}):
            raise HTTPException(409, {"message": "Another lead already uses this phone number."})
        updates["normalized_phone"] = np_
    if "email" in updates:
        ne = norm_email(updates["email"]) or None
        if ne and await db.leads.find_one({"normalized_email": ne, "id": {"$ne": lid}}):
            raise HTTPException(409, {"message": "Another lead already uses this email."})
        updates["normalized_email"] = ne
    if "instagram" in updates:
        ni = norm_handle(updates["instagram"])
        if ni and await db.leads.find_one({"normalized_instagram": ni, "id": {"$ne": lid}}):
            raise HTTPException(409, {"message": "Another lead already uses this Instagram handle."})
        updates["normalized_instagram"] = ni
    if "linkedin" in updates:
        nl = norm_linkedin(updates["linkedin"])
        if nl and await db.leads.find_one({"normalized_linkedin": nl, "id": {"$ne": lid}}):
            raise HTTPException(409, {"message": "Another lead already uses this LinkedIn profile."})
        updates["normalized_linkedin"] = nl
    # status must be a configured stage; stages that need a reason need a NEW, valid one (never the stale old one)
    if "status" in updates and updates["status"] != lead.get("status"):
        opt = await db.options.find_one({"type": "stage", "label": updates["status"], "archived": {"$ne": True}})
        if not opt:
            raise HTTPException(400, f"Unknown status \"{updates['status']}\"")
        reason, notes = updates.get("lost_reason"), updates.get("lost_notes")
        if opt.get("requires_reason"):
            ok, msg = valid_reason(reason, notes)
            if not ok:
                raise HTTPException(400, {"message": msg, "requires_reason": True})
        updates.update(status_updates(updates["status"], lead, opt, reason, notes))
    # "Not Paid" payment status requires a reason
    if updates.get("payment_status") == "Not Paid" and updates.get("payment_status") != lead.get("payment_status"):
        ok, _ = valid_reason(updates.get("payment_reason") or lead.get("payment_reason"), None)
        if not ok:
            raise HTTPException(400, {"message": "A reason is required when marking payment as Not Paid.", "requires_reason": True, "field": "payment"})
    updates["updated_at"] = now_iso()
    updates["updated_by"] = user["id"]; updates["updated_by_name"] = user["name"]
    if updates.get("payment_status") == "Paid" and not (updates.get("payment_date") or lead.get("payment_date")):
        updates["payment_date"] = now_iso()
    tracked = {"status": "status", "owner": "owner", "followup_assigned_to": "follow-up assignee",
               "demo_status": "demo status", "payment_status": "payment status", "invoice_status": "invoice status"}
    for f in tracked:
        if f in updates and updates[f] != lead.get(f):
            extra = ""
            if f == "status" and updates.get("lost_reason"): extra = f" (reason: {updates['lost_reason']})"
            if f == "payment_status" and updates.get("payment_reason"): extra = f" (reason: {updates['payment_reason']})"
            await audit(user, "update", "lead", lid, field=tracked[f], prev=lead.get(f, ""), new=str(updates[f]) + extra, detail=lead["name"])
    await db.leads.update_one({"id": lid}, {"$set": updates, "$inc": {"version": 1}})
    changed = lambda f: f in updates and updates[f] != lead.get(f)
    demo_sync = {}
    if changed("demo_date"): demo_sync["due_date"] = (updates["demo_date"] or "")[:10] or None
    if changed("demo_time"): demo_sync["due_time"] = updates["demo_time"]
    if changed("demo_owner") and updates["demo_owner"]: demo_sync["assigned_to"] = updates["demo_owner"]
    await sync_resp_tasks(lid, "demo", demo_sync)
    if changed("demo_owner") and updates["demo_owner"] and updates["demo_owner"] != user["id"]:
        when = (updates.get("demo_date") or lead.get("demo_date") or "")[:10]
        await notify(updates["demo_owner"], "assignment", f"{user['name']} assigned you: Demo",
                     lead["name"] + (f" · {when}" if when else ""), f"/dashboard?open={lid}")
    fu_sync = {}
    if changed("next_follow_up") and updates["next_follow_up"]: fu_sync["due_date"] = updates["next_follow_up"][:10]
    if changed("followup_assigned_to") and updates["followup_assigned_to"]: fu_sync["assigned_to"] = updates["followup_assigned_to"]
    await sync_resp_tasks(lid, "follow_up", fu_sync)
    return clean(await db.leads.find_one({"id": lid}))

@api.patch("/leads/{lid}/archive")
async def archive_lead(lid: str, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lid})
    if not lead:
        raise HTTPException(404, "Not found")
    if not await can_access_lead(user, lead):
        raise HTTPException(403, "Access denied")
    new_val = not lead.get("archived", False)
    await db.leads.update_one({"id": lid}, {"$set": {"archived": new_val, "updated_at": now_iso(),
                                                     "updated_by": user["id"], "updated_by_name": user["name"]},
                                            "$inc": {"version": 1}})
    await audit(user, "archive" if new_val else "unarchive", "lead", lid, field="archived",
                prev=str(lead.get("archived", False)), new=str(new_val), detail=lead["name"])
    return {"archived": new_val}

@api.patch("/leads/{lid}/stage")
async def move_stage(lid: str, body: StageIn, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lid})
    if not lead:
        raise HTTPException(404, "Not found")
    if not await can_access_lead(user, lead):
        raise HTTPException(403, "Access denied")
    opt = await db.options.find_one({"type": "stage", "label": body.status})
    if not opt:
        raise HTTPException(400, "Invalid stage")
    if opt.get("requires_reason"):
        ok, msg = valid_reason(body.lost_reason, body.lost_notes)
        if not ok:
            raise HTTPException(400, {"message": msg, "requires_reason": True})
    upd = {"status": body.status, "updated_at": now_iso(), "updated_by": user["id"], "updated_by_name": user["name"]}
    upd.update(status_updates(body.status, lead, opt, body.lost_reason, body.lost_notes))
    await db.leads.update_one({"id": lid}, {"$set": upd, "$inc": {"version": 1}})
    reason_txt = f" (reason: {body.lost_reason})" if body.lost_reason else ""
    await audit(user, "update", "lead", lid, field="status", prev=lead.get("status"), new=body.status + reason_txt, detail=lead["name"])
    await db.activities.insert_one({"id": str(uuid.uuid4()), "lead_id": lid, "lead_name": lead["name"],
                                    "employee_id": user["id"], "employee_name": user["name"], "type": "Status Change",
                                    "contact_method": "", "notes": f"Moved to {body.status}" + (f" — {body.lost_reason}" if body.lost_reason else "") + (f" · {body.lost_notes}" if body.lost_notes else ""),
                                    "outcome": "", "next_action": "", "timestamp": now_iso()})
    return clean(await db.leads.find_one({"id": lid}))

@api.patch("/leads/{lid}/assign")
async def assign_lead(lid: str, body: AssignIn, mgr: dict = Depends(require_manager)):
    lead = await db.leads.find_one({"id": lid})
    if not lead:
        raise HTTPException(404, "Not found")
    if body.field not in ("owner", "followup_assigned_to", "demo_owner"):
        raise HTTPException(400, "Invalid field")
    assignee = await db.users.find_one({"id": body.user_id, "active": True})
    if not assignee:
        raise HTTPException(400, "Pick an active team member")
    prev = lead.get(body.field)
    pu = await db.users.find_one({"id": prev}) if prev else None
    updates = {body.field: body.user_id, "updated_at": now_iso()}
    # When the lead owner changes, cascade any assignee that still mirrored the old owner
    # so access is actually revoked from the previous owner.
    if body.field == "owner":
        if lead.get("followup_assigned_to") in (None, prev):
            updates["followup_assigned_to"] = body.user_id
        if lead.get("demo_owner") == prev:
            updates["demo_owner"] = body.user_id
    await db.leads.update_one({"id": lid}, {"$set": updates, "$inc": {"version": 1}})
    await db.assignments.insert_one({"id": str(uuid.uuid4()), "lead_id": lid, "field": body.field,
                                     "from": prev, "to": body.user_id, "by": mgr["id"], "by_name": mgr["name"], "timestamp": now_iso()})
    await audit(mgr, "reassign", "lead", lid, field=body.field, prev=(pu["name"] if pu else (prev or "")),
                new=assignee["name"], detail=lead["name"])
    return clean(await db.leads.find_one({"id": lid}))

@api.get("/leads/{lid}/history")
async def lead_history(lid: str, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lid})
    if not lead or not await can_access_lead(user, lead):
        raise HTTPException(403, "Access denied")
    logs = await db.audit.find({"entity": "lead", "entity_id": lid}).sort("timestamp", -1).to_list(200)
    assigns = await db.assignments.find({"lead_id": lid}).sort("timestamp", -1).to_list(200)
    return {"audit": [clean(l) for l in logs], "assignments": [clean(a) for a in assigns]}

@api.delete("/leads/{lid}")
async def delete_lead(lid: str, mgr: dict = Depends(require_manager)):
    lead = await db.leads.find_one({"id": lid})
    if not lead:
        raise HTTPException(404, "Not found")
    await db.leads.delete_one({"id": lid})
    await db.activities.delete_many({"lead_id": lid})
    # Remove work items that only make sense with the lead (the audit trail is kept).
    await db.tasks.delete_many({"lead_id": lid})
    await db.assignments.delete_many({"lead_id": lid})
    await db.notifications.delete_many({"link": f"/dashboard?open={lid}"})
    await audit(mgr, "delete", "lead", lid, detail=lead.get("name", ""))
    return {"ok": True}

# ---------- activities ----------
@api.get("/activities")
async def list_activities(request: Request, user: dict = Depends(get_current_user)):
    p = request.query_params
    q = {}
    if not is_manager(user):
        q["employee_id"] = user["id"]
    if p.get("lead_id"): q["lead_id"] = p.get("lead_id")
    if p.get("employee_id") and is_manager(user): q["employee_id"] = p.get("employee_id")
    acts = await db.activities.find(q).sort("timestamp", -1).to_list(1500)
    return [clean(a) for a in acts]

@api.post("/activities")
async def create_activity(body: ActivityIn, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": body.lead_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not await can_access_lead(user, lead):
        raise HTTPException(403, "Access denied")
    ts = now_iso()
    notes = body.notes or ""
    if body.followup_done:
        notes = (notes + " · " if notes else "") + "Follow-up marked done"
    doc = {"id": str(uuid.uuid4()), "lead_id": body.lead_id, "lead_name": lead["name"],
           "employee_id": user["id"], "employee_name": user["name"], "type": body.type,
           "contact_method": body.contact_method or body.type, "notes": notes, "outcome": body.outcome,
           "next_action": body.next_action, "followup_done": body.followup_done, "timestamp": ts}
    await db.activities.insert_one(dict(doc))
    upd = {"last_interaction_at": ts, "last_contacted_by": user["id"], "last_contacted_by_name": user["name"],
           "last_contact_method": body.contact_method or body.type, "updated_at": ts}
    inc = {"total_interactions": 1}
    if body.next_follow_up:
        upd["next_follow_up"] = body.next_follow_up
        inc["version"] = 1   # an editable lead field changed — open drawers must reload before saving
    elif body.followup_done and lead.get("next_follow_up"):
        upd["next_follow_up"] = None   # done, and no new follow-up planned
        inc["version"] = 1
    await db.leads.update_one({"id": body.lead_id}, {"$set": upd, "$inc": inc})
    if body.followup_done:
        await close_resp_tasks(body.lead_id, "follow_up", "Completed", "Follow-up done")
    elif body.next_follow_up:
        await sync_resp_tasks(body.lead_id, "follow_up", {"due_date": body.next_follow_up[:10]})
    return clean(doc)

# ---------- tasks ----------
@api.get("/tasks")
async def list_tasks(request: Request, user: dict = Depends(get_current_user)):
    view = request.query_params.get("view")
    q = {} if is_manager(user) else {"assigned_to": user["id"]}
    today = today_local()
    if view == "today": q.update({"due_date": today, "status": {"$nin": ["Completed", "Cancelled"]}})
    elif view == "overdue": q.update({"due_date": {"$lt": today}, "status": {"$nin": ["Completed", "Cancelled"]}})
    elif view == "upcoming": q.update({"due_date": {"$gt": today}, "status": {"$nin": ["Completed", "Cancelled"]}})
    elif view == "completed": q["status"] = "Completed"
    elif view == "mine": q["assigned_to"] = user["id"]
    tasks = await db.tasks.find(q).sort("due_date", 1).to_list(1000)
    return [clean(t) for t in tasks]

@api.post("/tasks")
async def create_task(body: TaskIn, user: dict = Depends(get_current_user)):
    assigned = body.assigned_to if (is_manager(user) and body.assigned_to) else user["id"]
    lead_name = ""
    if body.lead_id:
        l = await db.leads.find_one({"id": body.lead_id})
        if not l:
            raise HTTPException(404, "Lead not found")
        if not await can_access_lead(user, l):
            raise HTTPException(403, "You do not have access to this lead")
        lead_name = l["name"]
    doc = body.model_dump(); doc.update({"id": str(uuid.uuid4()), "assigned_to": assigned, "lead_name": lead_name,
                                         "assigned_by": user["id"], "assigned_by_name": user["name"],
                                         "created_by": user["id"], "created_at": now_iso()})
    await db.tasks.insert_one(dict(doc))
    if assigned != user["id"]:
        await notify(assigned, "task", f"{user['name']} assigned you a task", body.title, f"/dashboard?open={body.lead_id or ''}")
        au = await db.users.find_one({"id": assigned})
        if au:
            await send_assignment_email(au, user["name"], "Task", {"name": lead_name or body.title},
                                        body.due_date, body.due_time, body.priority, body.notes,
                                        f"/dashboard?open={body.lead_id or ''}")
    if body.lead_id:
        await db.activities.insert_one({"id": str(uuid.uuid4()), "lead_id": body.lead_id, "lead_name": lead_name,
                                        "employee_id": user["id"], "employee_name": user["name"], "type": "Task Created",
                                        "contact_method": "", "notes": f"Task: {body.title}", "outcome": "",
                                        "next_action": "", "timestamp": now_iso()})
    return clean(doc)

@api.patch("/tasks/{tid}")
async def update_task(tid: str, body: TaskUpdate, user: dict = Depends(get_current_user)):
    t = await db.tasks.find_one({"id": tid})
    if not t:
        raise HTTPException(404, "Not found")
    if not is_manager(user) and t.get("assigned_to") != user["id"]:
        raise HTTPException(403, "Access denied")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not is_manager(user) and updates.get("assigned_to", t.get("assigned_to")) != t.get("assigned_to"):
        raise HTTPException(403, "Only managers can reassign tasks")
    just_completed = updates.get("status") == "Completed" and t.get("status") != "Completed"
    if just_completed:
        updates["completed_at"] = now_iso()
    await db.tasks.update_one({"id": tid}, {"$set": updates})
    if just_completed and t.get("responsibility") == "follow_up" and t.get("lead_id") and t.get("due_date"):
        await db.leads.update_one({"id": t["lead_id"], "followup_assigned_to": t.get("assigned_to"),
                                   "next_follow_up": {"$gte": t["due_date"][:10], "$lte": t["due_date"][:10] + "T99"}},
                                  {"$set": {"next_follow_up": None, "updated_at": now_iso()}, "$inc": {"version": 1}})
    if just_completed:
        if t.get("lead_id"):
            await db.activities.insert_one({"id": str(uuid.uuid4()), "lead_id": t["lead_id"], "lead_name": t.get("lead_name", ""),
                                            "employee_id": user["id"], "employee_name": user["name"], "type": "Task Completed",
                                            "contact_method": "", "notes": f"Completed task: {t.get('title', '')}", "outcome": "",
                                            "next_action": "", "timestamp": now_iso()})
        if t.get("assigned_by") and t["assigned_by"] != user["id"]:
            await notify(t["assigned_by"], "task_done", f"{user['name']} completed a task", t.get("title", ""),
                         f"/dashboard?open={t.get('lead_id', '')}")
    return clean(await db.tasks.find_one({"id": tid}))

@api.delete("/tasks/{tid}")
async def delete_task(tid: str, user: dict = Depends(get_current_user)):
    t = await db.tasks.find_one({"id": tid})
    if not t:
        raise HTTPException(404, "Not found")
    if not is_manager(user) and t.get("assigned_to") != user["id"]:
        raise HTTPException(403, "Access denied")
    await db.tasks.delete_one({"id": tid})
    return {"ok": True}

# ---------- performance ----------
def period_bounds(period, start, end):
    """(start, end) as UTC ISO strings; periods follow the team's local calendar (APP_TIMEZONE)."""
    now = datetime.now(timezone.utc)
    today = datetime.now(APP_TZ).date()
    first = None
    if period in ("today", "day"):
        first = today
    elif period == "week":
        first = today - timedelta(days=today.weekday())
    elif period == "month":
        first = today.replace(day=1)
    elif period == "quarter":
        first = today.replace(month=(today.month - 1) // 3 * 3 + 1, day=1)
    elif period == "year":
        first = today.replace(month=1, day=1)
    if first:
        return local_day_start_utc(first), now.isoformat()
    if period == "custom" and start and end:
        try:
            sd, ed = date.fromisoformat(start[:10]), date.fromisoformat(end[:10])
        except ValueError:
            raise HTTPException(400, "Dates must be in YYYY-MM-DD format")
        return local_day_start_utc(sd), local_day_start_utc(ed + timedelta(days=1))
    return None, None

async def compute_metrics(emp_id, s, e):
    aq = {"employee_id": emp_id}
    if s and e: aq["timestamp"] = {"$gte": s, "$lte": e}
    acts = await db.activities.find(aq).to_list(5000)
    ct = lambda t: sum(1 for a in acts if a["type"] == t)
    lq = {"added_by": emp_id}
    if s and e: lq["created_at"] = {"$gte": s, "$lte": e}
    leads_added = await db.leads.count_documents(lq)
    owned = await db.leads.find({"owner": emp_id}).to_list(5000)
    ls = lambda st: sum(1 for l in owned if l.get("status") == st)
    tq = {"assigned_to": emp_id, "status": "Completed"}
    if s and e: tq["completed_at"] = {"$gte": s, "$lte": e}
    tasks_done = await db.tasks.count_documents(tq)
    today = today_local()
    # Same definition as the "Overdue" lead list the tile opens: open, non-archived leads only.
    overdue = await db.leads.count_documents({"followup_assigned_to": emp_id, "next_follow_up": {**HAS_DATE, "$lt": today},
                                              "status": {"$nin": TERMINAL}, "archived": {"$ne": True}})
    return {"leads_added": leads_added,
            "contacted": len(set(a["lead_id"] for a in acts if a["type"] in ("Call", "WhatsApp", "Instagram", "LinkedIn", "Email"))),
            "calls": ct("Call"), "messages": ct("WhatsApp") + ct("Instagram") + ct("LinkedIn") + ct("Email"),
            "follow_ups": ct("Follow-up"), "responses": sum(1 for a in acts if a.get("outcome")),
            "interested": ls("Interested"), "demos_booked": ls("Demo Booked"), "demos_completed": ls("Demo Completed"),
            "demo_noshows": ls("Demo No-show"), "trials": ls("Trial"), "pricing_shared": ls("Pricing Shared"),
            "invoices": ls("Invoice Raised"), "payment_pending": ls("Payment Pending"), "paid": ls("Paid"),
            "conversions": ls("Converted"), "lost": ls("Lost") + ls("Not Interested"), "closed": ls("Closed"),
            "tasks_completed": tasks_done, "overdue_follow_ups": overdue}

@api.get("/performance/team")
async def team_perf(request: Request, mgr: dict = Depends(require_manager)):
    p = request.query_params
    s, e = period_bounds(p.get("period", "month"), p.get("start"), p.get("end"))
    members = await db.users.find({"role": {"$in": ["employee", "manager", "intern"]}}).to_list(500)
    if p.get("team"):
        members = [m for m in members if m.get("team") == p.get("team")]
    if p.get("employee"):
        members = [m for m in members if m["id"] == p.get("employee")]
    rows = []
    for m in members:
        rows.append({"employee_id": m["id"], "name": m["name"], "email": m["email"], "role": m["role"], **await compute_metrics(m["id"], s, e)})
    return {"rows": rows}

@api.get("/performance/me")
async def my_perf(request: Request, user: dict = Depends(get_current_user)):
    p = request.query_params
    s, e = period_bounds(p.get("period", "month"), p.get("start"), p.get("end"))
    return {"employee_id": user["id"], "name": user["name"], **await compute_metrics(user["id"], s, e)}

# ---------- reports ----------
# Funnel steps (label -> representative pipeline status; None = all leads). Cumulative "reached" by pipeline order.
FUNNEL_STEPS = [("Leads Generated", None), ("People Contacted", "Contacted"), ("Any Reply", "Replied"),
                ("Idea Explained", "Replied"), ("Interested / Asked for Demo", "Interested"),
                ("Demo Booked", "Demo Booked"), ("Demo Completed", "Demo Completed"),
                ("Commercials Opened / Invoice Raised", "Invoice Raised"), ("Invoice Paid", "Paid"),
                ("Clients Added", "Converted")]
LOST_STATUSES = ["Lost", "Not Interested", "Closed"]
# Side-branch stages sit later in the pipeline order than the step they actually imply. For the funnel they
# count as having reached only this main-path stage (None = counted in "Leads Generated" only).
FUNNEL_SIDE_BRANCH = {"Demo No-show": "Demo Booked", "Rescheduled": "Demo Booked",
                      "Not Paid": "Invoice Raised", "Other": None}
OUTREACH_TYPES = ("Call", "WhatsApp", "Instagram", "LinkedIn", "Email")

@api.get("/reports")
async def reports(request: Request, user: dict = Depends(get_current_user)):
    p = request.query_params
    s, e = period_bounds(p.get("period", "month"), p.get("start"), p.get("end"))
    team = p.get("team"); emp = p.get("employee")
    q = lead_scope(user)
    scope_ids = None
    if is_manager(user):
        if emp and emp != "all":
            q = {**q, "owner": emp}; scope_ids = [emp]
        elif team and team != "all":
            scope_ids = [u["id"] for u in await db.users.find({"team": team}).to_list(500)]
            q = {**q, "owner": {"$in": scope_ids}}
    else:
        scope_ids = [user["id"]]
    lq = {**q}
    if s and e:
        lq["created_at"] = {"$gte": s, "$lte": e}
    lq["archived"] = {"$ne": True}
    leads = await db.leads.find(lq).to_list(8000)

    stages = [o["label"] for o in await db.options.find({"type": "stage", "archived": {"$ne": True}}).sort("order", 1).to_list(100)]
    by_stage = {st: 0 for st in stages}
    by_source = {}
    for l in leads:
        st = l.get("status", "New Lead"); by_stage[st] = by_stage.get(st, 0) + 1
        src = l.get("source") or "Unknown"; by_source[src] = by_source.get(src, 0) + 1

    order_of = {lab: i for i, lab in enumerate(stages)}
    lost = sum(1 for l in leads if l.get("status") in LOST_STATUSES)
    total_leads = len(leads)
    def reached_count(status_label):
        thr = order_of.get(status_label)
        if thr is None:
            return 0
        n = 0
        for l in leads:
            st = l.get("status")
            if st in LOST_STATUSES:
                continue
            eff = FUNNEL_SIDE_BRANCH.get(st, st) if st in FUNNEL_SIDE_BRANCH else st
            if eff is not None and order_of.get(eff, -1) >= thr:
                n += 1
        return n
    funnel = []
    for lab, st in FUNNEL_STEPS:
        cnt = total_leads if st is None else reached_count(st)
        funnel.append({"stage": lab, "status": st, "count": cnt, "pct": round(cnt / total_leads * 100) if total_leads else 0})
    # Average days from Demo Completed -> Invoice Paid (real dates only)
    diffs = []
    for l in leads:
        paid = l.get("payment_date")
        demo_done = l.get("demo_completed_at") or l.get("demo_date")
        if paid and demo_done:
            try:
                d1 = datetime.fromisoformat(demo_done[:10]); d2 = datetime.fromisoformat(paid[:10])
                if d2 >= d1:
                    diffs.append((d2 - d1).days)
            except Exception:
                pass
    avg_days = round(sum(diffs) / len(diffs), 1) if diffs else None

    aq = {}
    if not is_manager(user):
        aq["employee_id"] = user["id"]
    elif emp and emp != "all":
        aq["employee_id"] = emp
    elif scope_ids is not None:
        aq["employee_id"] = {"$in": scope_ids}
    if s and e:
        aq["timestamp"] = {"$gte": s, "$lte": e}
    acts = await db.activities.find(aq).to_list(8000)
    by_channel = {}
    daily = {}
    outreach = responses = follow_ups = 0
    for a in acts:
        t = a.get("type", "")
        by_channel[t] = by_channel.get(t, 0) + 1
        d = a["timestamp"][:10]; daily[d] = daily.get(d, 0) + 1
        if t in OUTREACH_TYPES: outreach += 1
        if a.get("outcome"): responses += 1
        if t == "Follow-up": follow_ups += 1

    by_employee = []
    if is_manager(user):
        mem_q = {"role": {"$in": ["employee", "manager", "intern"]}}
        if team and team != "all": mem_q["team"] = team
        for m in await db.users.find(mem_q).to_list(500):
            if emp and emp != "all" and m["id"] != emp:
                continue
            by_employee.append({"name": m["name"], "count": sum(1 for a in acts if a.get("employee_id") == m["id"])})

    demos = by_stage.get("Demo Booked", 0) + by_stage.get("Demo Completed", 0)
    sales = {"leads": len(leads), "outreach": outreach, "responses": responses, "demos": demos,
             "trials": by_stage.get("Trial", 0), "follow_ups": follow_ups,
             "invoices": by_stage.get("Invoice Raised", 0),
             "payments": by_stage.get("Paid", 0), "conversions": by_stage.get("Converted", 0), "losses": lost}
    return {"by_stage": [{"stage": k, "count": v} for k, v in by_stage.items()],
            "by_source": [{"source": k, "count": v} for k, v in by_source.items()],
            "by_channel": [{"channel": k, "count": v} for k, v in by_channel.items()],
            "by_employee": by_employee,
            "daily": [{"date": k, "count": v} for k, v in sorted(daily.items())[-30:]],
            "funnel": funnel, "lost": lost, "sales": sales, "avg_days_demo_to_paid": avg_days, "avg_days_sample": len(diffs),
            "totals": {"total_leads": len(leads), "converted": by_stage.get("Converted", 0),
                       "demos": demos, "trials": by_stage.get("Trial", 0)}}

# ---------- audit ----------
@api.get("/audit")
async def get_audit(mgr: dict = Depends(require_manager)):
    logs = await db.audit.find({}).sort("timestamp", -1).to_list(500)
    return [clean(l) for l in logs]

# ---------- export ----------
_PHONE_LIKE = re.compile(r"^[+\-]?[\d\s().\-]+$")

def csv_safe(v):
    """Neutralise spreadsheet formulas (=, +, -, @, tab, CR) in exported cells; phone numbers stay as-is."""
    if isinstance(v, str) and v and v[0] in "=+-@\t\r" and not _PHONE_LIKE.match(v):
        return "'" + v
    return v

@api.get("/export/leads.csv")
async def export_csv(mgr: dict = Depends(require_manager)):
    leads = await db.leads.find({}).to_list(20000)
    users = {u["id"]: u["name"] for u in await db.users.find({}).to_list(1000)}
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Name", "Phone", "Email", "Instagram", "LinkedIn", "Practice", "Location", "Source", "Owner",
                "Team", "Status", "Last Interaction", "Last Contacted By", "Total Interactions", "Next Follow-up",
                "Follow-up Assignee", "Demo Owner", "Demo Status", "Invoice Status", "Payment Status",
                "Conversion", "Lost Reason", "Notes", "Date Created"])
    for l in leads:
        w.writerow([csv_safe(v) for v in [l.get("name", ""), l.get("phone", ""), l.get("email", ""), l.get("instagram", ""), l.get("linkedin", ""),
                    l.get("practice", ""), l.get("location", ""), l.get("source", ""), users.get(l.get("owner"), ""),
                    l.get("team", ""), l.get("status", ""), l.get("last_interaction_at", ""), l.get("last_contacted_by_name", ""),
                    l.get("total_interactions", 0), l.get("next_follow_up", ""), users.get(l.get("followup_assigned_to"), ""),
                    users.get(l.get("demo_owner"), ""), l.get("demo_status", ""), l.get("invoice_status", ""),
                    l.get("payment_status", ""), l.get("conversion_status", ""), l.get("lost_reason", ""),
                    l.get("notes", ""), l.get("created_at", "")]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=beet_leads.csv"})

class CustomFieldIn(BaseModel):
    label: str
    type: str = "text"
    options: Optional[List[str]] = None
    required: bool = False
    show_in_table: bool = False

class CustomFieldUpdate(BaseModel):
    label: Optional[str] = None
    options: Optional[List[str]] = None
    required: Optional[bool] = None
    archived: Optional[bool] = None
    show_in_table: Optional[bool] = None
    order: Optional[int] = None

@api.get("/custom-fields")
async def list_cf(include_archived: bool = False, user: dict = Depends(get_current_user)):
    q = {} if include_archived else {"archived": {"$ne": True}}
    cfs = await db.custom_fields.find(q).sort("order", ASCENDING).to_list(200)
    return [clean(c) for c in cfs]

@api.post("/custom-fields")
async def add_cf(body: CustomFieldIn, adm: dict = Depends(require_admin)):
    key = re.sub(r"[^a-z0-9]+", "_", body.label.strip().lower()).strip("_") + "_" + uuid.uuid4().hex[:4]
    n = await db.custom_fields.count_documents({})
    doc = {"id": str(uuid.uuid4()), "key": key, "label": body.label, "type": body.type,
           "options": body.options or [], "required": body.required, "show_in_table": body.show_in_table,
           "archived": False, "order": n}
    await db.custom_fields.insert_one(dict(doc))
    await audit(adm, "create", "custom_field", doc["id"], detail=body.label)
    return clean(doc)

@api.patch("/custom-fields/{cid}")
async def update_cf(cid: str, body: CustomFieldUpdate, adm: dict = Depends(require_admin)):
    cf = await db.custom_fields.find_one({"id": cid})
    if not cf:
        raise HTTPException(404, "Not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.custom_fields.update_one({"id": cid}, {"$set": updates})
    return clean(await db.custom_fields.find_one({"id": cid}))

# ---------- tracker import ----------
@api.post("/import/parse")
async def import_parse(file: UploadFile = File(...), mgr: dict = Depends(require_manager)):
    import pandas as pd
    content = await file.read()
    name = (file.filename or "").lower()
    # Read every cell as text: type inference turns phone columns with a blank cell (and Excel numbers)
    # into floats, which would store "9876543210.0" and break phone normalisation/duplicate checks.
    try:
        if name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)
        else:
            df = None
            for enc in ("utf-8-sig", "cp1252", "latin-1"):   # Excel saves CSVs as Windows-1252 by default
                try:
                    df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
    except Exception as e:
        raise HTTPException(400, f"Could not read file: {e}")
    df = df.fillna("")
    rows = df.astype(str).to_dict(orient="records")[:2000]
    return {"columns": [str(c) for c in df.columns], "rows": rows, "total": len(rows)}

class ImportCommit(BaseModel):
    mapping: dict
    rows: List[dict]
    owner: Optional[str] = None

@api.post("/import/commit")
async def import_commit(body: ImportCommit, mgr: dict = Depends(require_manager)):
    m = body.mapping
    owner = body.owner or mgr["id"]
    imported = dups = invalid = 0
    details = []
    seen_phone, seen_email, seen_ig, seen_li = set(), set(), set(), set()
    stage_by_lower = {o["label"].lower(): o["label"]
                      for o in await db.options.find({"type": "stage", "archived": {"$ne": True}}).to_list(200)}
    def g(row, field):
        col = m.get(field)
        return str(row.get(col, "")).strip() if col else ""
    for row in body.rows[:2000]:
        name = g(row, "name")
        if not name:
            invalid += 1; details.append({"name": "(blank)", "status": "invalid", "reason": "missing name"}); continue
        raw_status = g(row, "status")
        status = stage_by_lower.get(raw_status.lower()) if raw_status else "New Lead"
        if not status:
            invalid += 1; details.append({"name": name, "status": "invalid", "reason": f"unknown status '{raw_status}'"}); continue
        phone, email = g(row, "phone"), g(row, "email")
        np_, ne = norm_phone(phone), norm_email(email) or None
        ni, nl = norm_handle(g(row, "instagram")), norm_linkedin(g(row, "linkedin"))
        is_dup = False
        if np_ and (np_ in seen_phone or await db.leads.find_one({"normalized_phone": np_})): is_dup = True
        if ne and (ne in seen_email or await db.leads.find_one({"normalized_email": ne})): is_dup = True
        if ni and (ni in seen_ig or await db.leads.find_one({"normalized_instagram": ni})): is_dup = True
        if nl and (nl in seen_li or await db.leads.find_one({"normalized_linkedin": nl})): is_dup = True
        if is_dup:
            dups += 1; details.append({"name": name, "status": "duplicate"}); continue
        lid = str(uuid.uuid4())
        doc = {"id": lid, "name": name, "phone": phone, "email": email, "instagram": g(row, "instagram"),
               "linkedin": g(row, "linkedin"), "practice": g(row, "practice"), "location": g(row, "location"),
               "source": g(row, "source") or "Import", "status": status, "owner": owner,
               "team": "", "added_by": mgr["id"], "added_by_name": mgr["name"], "notes": g(row, "notes"),
               "next_follow_up": None, "followup_assigned_to": owner, "demo_date": None, "demo_status": None,
               "demo_owner": None, "invoice_status": None, "payment_status": None, "conversion_status": "Open",
               "custom": {}, "response": "", "last_interaction_at": None, "last_contacted_by": None,
               "last_contacted_by_name": None, "last_contact_method": None, "total_interactions": 0,
               "created_at": now_iso(), "updated_at": now_iso(), "version": 1}
        if np_: doc["normalized_phone"] = np_; seen_phone.add(np_)
        if ne: doc["normalized_email"] = ne; seen_email.add(ne)
        if ni: doc["normalized_instagram"] = ni; seen_ig.add(ni)
        if nl: doc["normalized_linkedin"] = nl; seen_li.add(nl)
        try:
            await db.leads.insert_one(dict(doc)); imported += 1; details.append({"name": name, "status": "imported"})
        except DuplicateKeyError:
            dups += 1; details.append({"name": name, "status": "duplicate"})
    await audit(mgr, "import", "lead", "batch", detail=f"{imported} imported, {dups} duplicates, {invalid} invalid")
    return {"total": len(body.rows), "imported": imported, "duplicates": dups, "invalid": invalid, "details": details[:200]}

# ---------- follow-up reminders ----------
@api.get("/reminders/preview")
async def reminders_preview(user: dict = Depends(get_current_user)):
    due, overdue = await build_user_followups(user["id"])
    return {"due": [clean(l) for l in due], "overdue": [clean(l) for l in overdue]}

@api.post("/reminders/run")
async def reminders_run(mgr: dict = Depends(require_manager)):
    return {"sent": await run_reminders(force=True)}

# ---------- lead timeline (unified chronological) ----------
@api.get("/leads/{lid}/timeline")
async def lead_timeline(lid: str, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lid})
    if not lead or not await can_access_lead(user, lead):
        raise HTTPException(403, "Access denied")
    users = {u["id"]: u["name"] for u in await db.users.find({}).to_list(1000)}
    events = []
    for a in await db.activities.find({"lead_id": lid}).to_list(1000):
        typ = a.get("type", "Activity")
        text = typ + (f" via {a['contact_method']}" if a.get("contact_method") and a["contact_method"] != typ else "")
        detail = a.get("notes") or ""
        if a.get("outcome"):
            detail = (detail + (" · " if detail else "") + f"Outcome: {a['outcome']}")
        if a.get("next_action"):
            detail = (detail + (" · " if detail else "") + f"Next: {a['next_action']}")
        events.append({"kind": "activity", "event": typ, "text": text, "detail": detail,
                       "actor": a.get("employee_name", "—"), "timestamp": a.get("timestamp")})
    for a in await db.assignments.find({"lead_id": lid}).to_list(500):
        label = RESPONSIBILITY_LABELS.get(a.get("field"), a.get("field"))
        frm = users.get(a.get("from"), "Unassigned") if a.get("from") else "Unassigned"
        to = users.get(a.get("to"), "—")
        events.append({"kind": "handover", "event": "Handover",
                       "text": f"{label} handed over: {frm} → {to}", "detail": a.get("note") or "",
                       "actor": a.get("by_name", "—"), "timestamp": a.get("timestamp")})
    for h in await db.audit.find({"entity": "lead", "entity_id": lid}).to_list(500):
        act = h.get("action")
        if act == "reassign":
            continue
        if act == "create":
            text = "Lead created"
        elif h.get("field"):
            text = f"changed {h['field']} from {h.get('prev') or '—'} to {h.get('new') or '—'}"
        else:
            text = act
        events.append({"kind": "change", "event": act, "text": text, "detail": "",
                       "actor": h.get("actor_name", "—"), "timestamp": h.get("timestamp")})
    events = [e for e in events if e.get("timestamp")]
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return {"events": events}

# ---------- unified assign / handover workflow ----------
class HandoverIn(BaseModel):
    responsibility: str
    assignee_id: str
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: str = "Medium"
    note: Optional[str] = ""
    create_task: bool = True

@api.post("/leads/{lid}/handover")
async def handover(lid: str, body: HandoverIn, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lid})
    if not lead:
        raise HTTPException(404, "Not found")
    if not await can_access_lead(user, lead) and not is_manager(user):
        raise HTTPException(403, "Access denied")
    if body.responsibility not in RESPONSIBILITY_LABELS:
        raise HTTPException(400, "Invalid responsibility")
    if body.responsibility == "owner" and not is_manager(user):
        raise HTTPException(403, "Only managers can reassign lead ownership")
    assignee = await db.users.find_one({"id": body.assignee_id, "active": True})
    if not assignee:
        raise HTTPException(400, "Pick an active team member")
    label = RESPONSIBILITY_LABELS[body.responsibility]
    field = RESPONSIBILITY_FIELD.get(body.responsibility)
    prev = lead.get(field) if field else None
    prev_name = ""
    if prev:
        pu = await db.users.find_one({"id": prev})
        prev_name = pu["name"] if pu else ""
    updates = {"updated_at": now_iso()}
    if field:
        updates[field] = body.assignee_id
        if body.responsibility == "owner":
            if lead.get("followup_assigned_to") in (None, prev):
                updates["followup_assigned_to"] = body.assignee_id
            if lead.get("demo_owner") == prev:
                updates["demo_owner"] = body.assignee_id
    if body.responsibility == "follow_up" and body.due_date:
        updates["next_follow_up"] = body.due_date   # one follow-up date, not a follow-up plus a differently dated task
    await db.leads.update_one({"id": lid}, {"$set": updates, "$inc": {"version": 1}})
    if body.create_task and body.responsibility in ("demo", "follow_up"):
        await close_resp_tasks(lid, body.responsibility, "Cancelled", "Replaced by a new assignment")
    await db.assignments.insert_one({"id": str(uuid.uuid4()), "lead_id": lid, "field": body.responsibility,
                                     "from": prev, "to": body.assignee_id, "by": user["id"], "by_name": user["name"],
                                     "note": body.note or "", "timestamp": now_iso()})
    await audit(user, "reassign", "lead", lid, field=body.responsibility, prev=prev_name,
                new=assignee["name"], detail=lead["name"])
    link = f"/dashboard?open={lid}"
    task = None
    if body.create_task:
        tid = str(uuid.uuid4())
        task = {"id": tid, "title": f"{label} — {lead['name']}", "lead_id": lid, "lead_name": lead["name"],
                "assigned_to": body.assignee_id, "assigned_by": user["id"], "assigned_by_name": user["name"],
                "due_date": body.due_date, "due_time": body.due_time, "priority": body.priority or "Medium",
                "status": "To Do", "responsibility": body.responsibility, "notes": body.note or "",
                "created_by": user["id"], "created_at": now_iso()}
        await db.tasks.insert_one(dict(task))
    if body.assignee_id != user["id"]:
        await notify(body.assignee_id, "assignment", f"{user['name']} assigned you: {label}",
                     lead["name"] + (f" · due {body.due_date}" if body.due_date else "") + f" · {body.priority or 'Medium'}", link)
        await send_assignment_email(assignee, user["name"], label, lead, body.due_date, body.due_time,
                                    body.priority, body.note, link)
    return {"lead": clean(await db.leads.find_one({"id": lid})), "task": clean(task) if task else None}

# ---------- demo workflow ----------
class DemoScheduleIn(BaseModel):
    demo_date: str
    demo_time: Optional[str] = None
    presenter_id: str
    note: Optional[str] = ""

class DemoCompleteIn(BaseModel):
    demo_status: str = "Completed"
    outcome: Optional[str] = ""
    note: Optional[str] = ""
    new_status: Optional[str] = None
    next_action: Optional[str] = None
    next_owner_id: Optional[str] = None
    next_due_date: Optional[str] = None
    next_due_time: Optional[str] = None
    next_priority: str = "Medium"
    lost_reason: Optional[str] = None   # required when new_status is a stage that needs a reason
    lost_notes: Optional[str] = None

@api.post("/leads/{lid}/demo/schedule")
async def demo_schedule(lid: str, body: DemoScheduleIn, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lid})
    if not lead or (not await can_access_lead(user, lead) and not is_manager(user)):
        raise HTTPException(403, "Access denied")
    presenter = await db.users.find_one({"id": body.presenter_id, "active": True})
    if not presenter:
        raise HTTPException(400, "Pick an active presenter")
    task = await assign_work(lead, "demo", presenter, user, due_date=body.demo_date, due_time=body.demo_time,
                             priority="High", note=body.note)
    upd = {"demo_date": body.demo_date, "demo_time": body.demo_time or None,
           "demo_status": "Scheduled", "status": "Demo Booked", "updated_at": now_iso()}
    if lead.get("status") != "Demo Booked":
        upd.update(status_updates("Demo Booked", lead, await stage_option("Demo Booked")))
    await db.leads.update_one({"id": lid}, {"$set": upd, "$inc": {"version": 1}})
    await db.activities.insert_one({"id": str(uuid.uuid4()), "lead_id": lid, "lead_name": lead["name"],
                                    "employee_id": user["id"], "employee_name": user["name"], "type": "Demo",
                                    "contact_method": "", "notes": f"Demo scheduled for {body.demo_date}" + (f" {body.demo_time}" if body.demo_time else "") + f" — presenter {presenter['name']}",
                                    "outcome": "", "next_action": "", "timestamp": now_iso()})
    return {"lead": clean(await db.leads.find_one({"id": lid})), "task": clean(task)}

@api.post("/leads/{lid}/demo/complete")
async def demo_complete(lid: str, body: DemoCompleteIn, user: dict = Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lid})
    if not lead or (not await can_access_lead(user, lead) and not is_manager(user)):
        raise HTTPException(403, "Access denied")
    prev_status = lead.get("status")
    upd = {"demo_status": body.demo_status, "updated_at": now_iso()}
    if body.demo_status == "Completed":
        upd["demo_completed_at"] = now_iso()
    if body.new_status and body.new_status != prev_status:
        # Same rules as every other status change: a configured stage, and a valid reason when it needs one.
        opt = await db.options.find_one({"type": "stage", "label": body.new_status, "archived": {"$ne": True}})
        if not opt:
            raise HTTPException(400, f"Unknown status \"{body.new_status}\"")
        if opt.get("requires_reason"):
            ok, msg = valid_reason(body.lost_reason, body.lost_notes)
            if not ok:
                raise HTTPException(400, {"message": msg, "requires_reason": True})
        upd["status"] = body.new_status
        upd.update(status_updates(body.new_status, lead, opt, body.lost_reason, body.lost_notes))
    await db.leads.update_one({"id": lid}, {"$set": upd, "$inc": {"version": 1}})
    task_close = {"Completed": "Completed", "Cancelled": "Cancelled", "No-show": "Cancelled", "No Show": "Cancelled"}.get(body.demo_status)
    if task_close:
        await close_resp_tasks(lid, "demo", task_close, f"Demo {body.demo_status}")
    note = "Demo " + body.demo_status + (f" — {body.outcome}" if body.outcome else "") + (f" · {body.note}" if body.note else "")
    await db.activities.insert_one({"id": str(uuid.uuid4()), "lead_id": lid, "lead_name": lead["name"],
                                    "employee_id": user["id"], "employee_name": user["name"], "type": "Demo",
                                    "contact_method": "", "notes": note, "outcome": body.outcome or "",
                                    "next_action": body.next_action or "", "timestamp": now_iso()})
    if body.new_status and body.new_status != prev_status:
        reason_txt = f" (reason: {body.lost_reason})" if upd.get("lost_reason") else ""
        await audit(user, "update", "lead", lid, field="status", prev=prev_status, new=body.new_status + reason_txt, detail=lead["name"])
    task = None
    if body.next_action and body.next_owner_id:
        no = await db.users.find_one({"id": body.next_owner_id, "active": True})
        if no:
            resp = {"Follow-up": "follow_up", "Pricing": "pricing", "Invoice": "invoice",
                    "Payment follow-up": "payment", "Onboarding": "onboarding", "Client success": "success"}.get(body.next_action, "follow_up")
            fresh = await db.leads.find_one({"id": lid})
            task = await assign_work(fresh, resp, no, user, due_date=body.next_due_date, due_time=body.next_due_time,
                                     priority=body.next_priority, note=body.note,
                                     follow_up_date=body.next_due_date if resp == "follow_up" else None)
    return {"lead": clean(await db.leads.find_one({"id": lid})), "task": clean(task) if task else None}

# ---------- calendar (role-scoped) ----------

@api.get("/calendar")
async def calendar(request: Request, user: dict = Depends(get_current_user)):
    """Demos and follow-ups come from the lead itself; tasks from tasks. Cancelled items, archived leads and open
    work on lost/closed leads are left out; completed items are kept but flagged done."""
    p = request.query_params
    start, end = p.get("start"), p.get("end")
    emp = p.get("employee")
    users = {u["id"]: u["name"] for u in await db.users.find({}).to_list(1000)}
    if is_manager(user):
        ids = [emp] if emp and emp != "all" else list(users)   # the whole team, admins included
    else:
        ids = [user["id"]]
    idset = set(ids)
    rng = {}
    if start: rng["$gte"] = start
    if end: rng["$lte"] = end + "T99"   # date fields may hold a full ISO timestamp
    rng = rng or HAS_DATE
    in_range = lambda d: (not start or start <= d) and (not end or d <= end)   # either bound may be omitted
    ev = []
    for l in await db.leads.find({"archived": {"$ne": True}, "$or": [
            {"demo_owner": {"$in": ids}, "demo_date": rng},
            {"followup_assigned_to": {"$in": ids}, "next_follow_up": rng}]}).to_list(None):
        dd, ds = (l.get("demo_date") or "")[:10], l.get("demo_status") or "Scheduled"
        if dd and l.get("demo_owner") in idset and in_range(dd) and ds != "Cancelled" and l.get("status") not in LOST_STATUSES:
            ev.append({"kind": "demo", "date": dd, "time": l.get("demo_time"), "title": f"Demo · {l['name']}",
                       "lead_id": l["id"], "lead_name": l["name"], "assignee_id": l.get("demo_owner"),
                       "assignee": users.get(l.get("demo_owner"), "—"), "status": ds, "done": ds in DEMO_CLOSED})
        fu = (l.get("next_follow_up") or "")[:10]
        if fu and l.get("followup_assigned_to") in idset and l.get("status") not in TERMINAL and in_range(fu):
            ev.append({"kind": "followup", "date": fu, "time": None, "title": f"Follow-up · {l['name']}",
                       "lead_id": l["id"], "lead_name": l["name"], "assignee_id": l.get("followup_assigned_to"),
                       "assignee": users.get(l.get("followup_assigned_to"), "—"), "status": l.get("status"), "done": False})
    # Demo / follow-up tasks are shown through the lead's own demo / follow-up event above (one item each).
    tasks = await db.tasks.find({"assigned_to": {"$in": ids}, "due_date": rng, "status": {"$ne": "Cancelled"},
                                 "responsibility": {"$nin": list(CALENDAR_LEAD_RESP)}}).to_list(None)
    task_leads = {l["id"]: l for l in await db.leads.find(
        {"id": {"$in": list({t["lead_id"] for t in tasks if t.get("lead_id")})}}, {"id": 1, "status": 1, "archived": 1}).to_list(None)}
    for t in tasks:
        td = (t.get("due_date") or "")[:10]
        if not td or not in_range(td):
            continue
        done = t.get("status") == "Completed"
        tl = task_leads.get(t.get("lead_id"))
        if tl and (tl.get("archived") or (tl.get("status") in LOST_STATUSES and not done)):
            continue
        ev.append({"kind": "task", "task_id": t["id"], "date": td, "time": t.get("due_time"), "title": t.get("title"),
                   "lead_id": t.get("lead_id"), "lead_name": t.get("lead_name"), "assignee_id": t.get("assigned_to"),
                   "assignee": users.get(t.get("assigned_to"), "—"), "status": t.get("status"), "priority": t.get("priority"),
                   "notes": t.get("notes") or "", "assigned_by_name": t.get("assigned_by_name"), "done": done})
    return {"events": ev}

# ---------- team workload (manager) ----------
@api.get("/workload")
async def workload(request: Request, mgr: dict = Depends(require_manager)):
    team = request.query_params.get("team")
    staff = await db.users.find({"role": {"$in": ["employee", "manager", "intern"]}, "active": True}).to_list(500)
    if team and team != "all":
        staff = [s for s in staff if s.get("team") == team]
    today = today_local()
    rows = []
    for m in staff:
        uid = m["id"]
        rows.append({
            "employee_id": uid, "name": m["name"], "role": m["role"], "team": m.get("team"),
            "open_leads": await db.leads.count_documents({"owner": uid, "status": {"$nin": TERMINAL}}),
            "open_tasks": await db.tasks.count_documents({"assigned_to": uid, "status": {"$nin": ["Completed", "Cancelled"]}}),
            "today_tasks": await db.tasks.count_documents({"assigned_to": uid, "due_date": today, "status": {"$nin": ["Completed", "Cancelled"]}}),
            "overdue_tasks": await db.tasks.count_documents({"assigned_to": uid, "due_date": {"$lt": today}, "status": {"$nin": ["Completed", "Cancelled"]}}),
            "upcoming_demos": await db.leads.count_documents({"demo_owner": uid, "demo_date": {"$gte": today}, "demo_status": {"$nin": DEMO_CLOSED}}),
            "open_follow_ups": await db.leads.count_documents({"followup_assigned_to": uid, "next_follow_up": HAS_DATE, "status": {"$nin": TERMINAL}}),
            "overdue_follow_ups": await db.leads.count_documents({"followup_assigned_to": uid, "next_follow_up": {**HAS_DATE, "$lt": today}, "status": {"$nin": TERMINAL}}),
        })
    return {"rows": rows, "today": today}

# ---------- notifications ----------
@api.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user)):
    items = await db.notifications.find({"user_id": user["id"]}).sort("created_at", -1).to_list(50)
    return [clean(i) for i in items]

@api.get("/notifications/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    return {"count": await db.notifications.count_documents({"user_id": user["id"], "read": False})}

@api.post("/notifications/{nid}/read")
async def mark_read(nid: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}

@api.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}

@api.get("/")
async def root():
    return {"message": "Beet.Health CRM API"}

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True,
                   allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
                   allow_methods=["*"], allow_headers=["*"])

# ---------- seed ----------
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.leads.create_index("id", unique=True)
    await db.leads.create_index("normalized_phone", unique=True, partialFilterExpression={"normalized_phone": {"$type": "string"}})
    await db.leads.create_index("normalized_email", unique=True, partialFilterExpression={"normalized_email": {"$type": "string"}})
    await db.otps.create_index("email")
    await db.custom_fields.create_index("id")
    await db.users.create_index("employee_id", unique=True, partialFilterExpression={"employee_id": {"$type": "string"}})
    await db.otp_failures.create_index("email")
    await db.revoked_tokens.create_index("jti")
    await db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0)   # drop once the JWT itself has expired
    await db.reminder_log.create_index([("kind", ASCENDING), ("date", ASCENDING), ("user_id", ASCENDING)], unique=True)
    asyncio.create_task(reminder_scheduler())

    # seed options — upsert each label so newly added DEFAULT_OPTIONS reach existing DBs
    for typ, items in DEFAULT_OPTIONS.items():
        base = await db.options.count_documents({"type": typ})
        for i, (label, req) in enumerate(items):
            if not await db.options.find_one({"type": typ, "label": label}):
                await db.options.insert_one({"id": str(uuid.uuid4()), "type": typ, "label": label,
                                             "order": base + i, "archived": False, "requires_reason": req})

    # seed users — ONLY the initial Admin is seeded. Admin adds all other staff
    # (managers/employees/interns) from Team Management inside the CRM.
    admin_email = norm_email(os.environ.get("ADMIN_EMAIL", "admin@beet.health"))
    if not await db.users.find_one({"email": admin_email}):
        await db.users.insert_one({"id": str(uuid.uuid4()), "name": os.environ.get("ADMIN_NAME", "Beet Admin"),
                                   "email": admin_email, "role": "admin", "employee_id": "ADMIN-001", "team": "",
                                   "manager_id": None, "joining_date": None, "employment_type": "Full-time",
                                   "active": True, "created_by": None, "created_at": now_iso()})
    # migrate legacy role "member" -> "employee"
    await db.users.update_many({"role": "member"}, {"$set": {"role": "employee"}})
    logger.info("Beet.Health seed complete")

@app.on_event("shutdown")
async def shutdown():
    client.close()
