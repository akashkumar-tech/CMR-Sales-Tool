"""Idempotent demo seed: 1 Manager + 1 Employee (Paripsa + Priya) + sample leads/activities/tasks/demos.
Run: python seed_demo.py           (safe to re-run — upserts users by email, skips existing leads by name)
     python seed_demo.py --reset   (deletes the demo leads below + their activities/tasks, then seeds them fresh)

The data is shaped like the app's own writes so every dashboard tile matches the list it opens:
activities carry real types/contact methods and are spread over this month, lost leads carry a lost reason,
tasks link to their lead, and conversions carry demo/payment dates.
"""
import asyncio, os, re, sys, uuid, random
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / '.env')
client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]

APP_TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Kolkata"))   # same team time zone as the backend
NOW = datetime.now(timezone.utc)
TODAY = NOW.astimezone(APP_TZ).date()
MONTH_START = datetime(TODAY.year, TODAY.month, 1, tzinfo=APP_TZ).astimezone(timezone.utc)

# Activity type -> contact method label (see DEFAULT_OPTIONS in server.py)
CONTACT_METHOD = {"Call": "Phone Call", "WhatsApp": "WhatsApp", "Email": "Email",
                  "Instagram": "Instagram", "LinkedIn": "LinkedIn"}
LOST = ("Lost", "Not Interested", "Closed")


def iso(dt):
    return dt.isoformat()


def day(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


def norm_email(e):
    return (e or "").strip().lower()


def norm_phone(p):
    if not p:
        return None
    digits = re.sub(r"\D", "", p)
    return (digits[-10:] if len(digits) > 10 else digits) or None


def outcome_for(status):
    if status in LOST:
        return "Not interested"
    if status == "New Lead":
        return ""
    if status == "Contacted":
        return "Asked to follow up later"
    return "Interested"


async def ensure_user(name, email, role, emp_id, team, manager_id=None, employment="Full-time"):
    email = norm_email(email)
    existing = await db.users.find_one({"email": email})
    if existing:
        await db.users.update_one({"email": email}, {"$set": {"role": role, "active": True, "team": team}})
        return existing["id"]
    uid = str(uuid.uuid4())
    await db.users.insert_one({
        "id": uid, "name": name, "email": email, "role": role, "employee_id": emp_id,
        "team": team, "manager_id": manager_id, "joining_date": day(-120),
        "employment_type": employment, "active": True, "created_by": None, "created_at": iso(NOW),
    })
    return uid


async def ensure_lead(i, s, owner, owner_name, team):
    """s: one entry of SAMPLES. Returns the lead id (existing or new)."""
    existing = await db.leads.find_one({"name": s["name"]})
    if existing:
        return existing["id"]
    lid = str(uuid.uuid4())
    status, methods = s["status"], s.get("methods", [])
    phone = f"98{random.randint(10000000, 99999999)}"
    email = f"contact{i}@{s['name'].split()[0].lower().strip('.')}.com"

    # Interactions spread evenly from the start of this month to now, so they all count as "this month"
    # and the latest one is the lead's last interaction.
    span = NOW - MONTH_START
    stamps = [MONTH_START + span * (k + 1) / (len(methods) + 1) for k in range(len(methods))]
    created = min(stamps[0] - timedelta(hours=2), NOW) if stamps else NOW

    demo = s.get("demo")   # (day offset, demo_status)
    doc = {
        "id": lid, "name": s["name"], "phone": phone, "email": email, "instagram": "", "linkedin": "",
        "practice": s["name"], "location": "Bengaluru", "source": s["source"], "status": status,
        "owner": owner, "team": team, "added_by": owner, "added_by_name": owner_name,
        "notes": "", "next_follow_up": day(s["follow"]) if s.get("follow") is not None and status not in LOST + ("Converted",) else None,
        "followup_assigned_to": owner,
        "demo_date": day(demo[0]) if demo else None, "demo_time": "15:00" if demo else None,
        "demo_owner": owner if demo else None, "demo_status": demo[1] if demo else None,
        "invoice_status": None, "payment_status": None,
        "conversion_status": "Converted" if status == "Converted" else "Lost" if status in LOST else "Open",
        "lost_reason": s.get("lost_reason"), "lost_notes": "",
        "custom": {}, "response": "",
        "last_interaction_at": iso(stamps[-1]) if stamps else None,
        "last_contacted_by": owner if stamps else None,
        "last_contacted_by_name": owner_name if stamps else None,
        "last_contact_method": CONTACT_METHOD[methods[-1]] if methods else None,
        "total_interactions": len(methods),
        "created_at": iso(created), "updated_at": iso(stamps[-1] if stamps else NOW), "version": 1, "seed": True,
    }
    if demo and demo[1] == "Completed":
        doc["demo_completed_at"] = day(demo[0])
    if status == "Converted":
        doc.update({"invoice_status": "Sent", "payment_status": "Paid", "payment_date": day(-1)})
    np_, ne = norm_phone(phone), norm_email(email) or None
    if np_ and not await db.leads.find_one({"normalized_phone": np_}):
        doc["normalized_phone"] = np_
    if ne and not await db.leads.find_one({"normalized_email": ne}):
        doc["normalized_email"] = ne
    await db.leads.insert_one(doc)

    for k, (typ, ts) in enumerate(zip(methods, stamps)):
        last = k == len(methods) - 1
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "lead_id": lid, "lead_name": s["name"],
            "employee_id": owner, "employee_name": owner_name,
            "type": typ, "contact_method": CONTACT_METHOD[typ],
            "notes": f"{typ} with {s['name']}" + (f" — {s['lost_reason'].lower()}" if last and s.get("lost_reason") else ""),
            "outcome": outcome_for(status) if last else "", "next_action": "", "timestamp": iso(ts), "seed": True,
        })
    return lid


# follow = next follow-up (days from today), demo = (days from today, demo status)
SAMPLES = [
    {"name": "Dr. Meera Clinic", "status": "Contacted", "source": "Instagram", "follow": -2, "methods": ["Instagram", "WhatsApp"]},
    {"name": "SmileCare Dental", "status": "Interested", "source": "Referral", "follow": 0, "methods": ["Call", "WhatsApp", "Call"]},
    {"name": "Wellness Physio", "status": "Demo Booked", "source": "Website", "follow": 3, "demo": (3, "Scheduled"), "methods": ["Email"]},
    {"name": "GreenLeaf Ayurveda", "status": "Demo Completed", "source": "LinkedIn", "follow": 5, "demo": (-1, "Completed"),
     "methods": ["LinkedIn", "Call", "Email", "Call"]},
    {"name": "CityHeart Cardiology", "status": "Demo Booked", "source": "Cold Outreach", "follow": 2, "demo": (2, "Scheduled"),
     "methods": ["Call", "WhatsApp", "Email", "WhatsApp", "Call"], "owner": "priya"},
    {"name": "Sunrise Pediatrics", "status": "Converted", "source": "Referral", "demo": (-7, "Completed"),
     "methods": ["Call", "Email", "Call", "WhatsApp", "Call", "Email"]},
    {"name": "Apollo Skin", "status": "Not Interested", "source": "Instagram", "lost_reason": "Too expensive", "methods": ["Instagram", "Call"]},
    {"name": "BrightEyes Optometry", "status": "Lost", "source": "Clinic Directory", "lost_reason": "No response",
     "methods": ["Call", "WhatsApp", "Email"]},
    {"name": "Nova IVF", "status": "New Lead", "source": "Website", "follow": 1},
]


async def reset(owner_ids):
    names = [s["name"] for s in SAMPLES]
    ids = [l["id"] for l in await db.leads.find({"name": {"$in": names}, "owner": {"$in": owner_ids}}, {"id": 1}).to_list(100)]
    await db.activities.delete_many({"lead_id": {"$in": ids}})
    await db.tasks.delete_many({"$or": [{"lead_id": {"$in": ids}}, {"seed": True}]})
    await db.leads.delete_many({"id": {"$in": ids}})
    print(f"Reset: removed {len(ids)} demo lead(s) and their activities/tasks")


async def main():
    mgr_id = await ensure_user("Paripsa Tripathi", "paripsa.tripathi@beet.health", "manager", "MGR-001", "Sales")
    priya = await ensure_user("Priya Sharma", "priya@beet.health", "employee", "EMP-101", "Sales", mgr_id)
    people = {"priya": (priya, "Priya Sharma", "Sales"), "mgr": (mgr_id, "Paripsa Tripathi", "Sales")}

    if "--reset" in sys.argv:
        await reset([priya, mgr_id])

    lead_ids = {}
    for i, s in enumerate(SAMPLES):
        owner, oname, team = people[s.get("owner") or ("priya" if i % 2 == 0 else "mgr")]
        lead_ids[s["name"]] = await ensure_lead(i, s, owner, oname, team)

    # Priya's workspace: tasks linked to their leads + a notification.
    if await db.tasks.count_documents({"assigned_to": priya}) == 0:
        for title, lead, days, prio in [("Follow up with Dr. Meera Clinic", "Dr. Meera Clinic", -1, "High"),
                                        ("Send pricing to CityHeart Cardiology", "CityHeart Cardiology", 0, "Medium"),
                                        ("Prepare demo deck for SmileCare", "SmileCare Dental", 2, "Low")]:
            await db.tasks.insert_one({"id": str(uuid.uuid4()), "title": title, "lead_id": lead_ids.get(lead), "lead_name": lead,
                                       "assigned_to": priya, "assigned_by": mgr_id, "assigned_by_name": "Paripsa Tripathi",
                                       "due_date": day(days), "due_time": "11:00", "responsibility": "",
                                       "priority": prio, "status": "To Do", "notes": "", "created_by": mgr_id,
                                       "created_at": iso(NOW), "seed": True})
        await db.notifications.insert_one({"id": str(uuid.uuid4()), "user_id": priya, "type": "assignment",
                                           "title": "Paripsa Tripathi assigned you: Follow-up",
                                           "body": "Dr. Meera Clinic · High", "link": "/dashboard", "read": False,
                                           "created_at": iso(NOW)})

    users = await db.users.find({}).to_list(100)
    print("Users:")
    for u in users:
        print(" ", u["email"], "|", u["role"], "| active:", u.get("active"), "| team:", u.get("team"))
    print("Total leads:", await db.leads.count_documents({}))

asyncio.run(main())
