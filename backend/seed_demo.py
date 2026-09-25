"""Idempotent demo seed: 1 Manager + 1 Employee (Paripsa + Priya) + sample leads/tasks/demos.
Run: python seed_demo.py   (safe to re-run — upserts by email, skips existing leads by name)
"""
import asyncio, os, uuid, random
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / '.env')
client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def norm_email(e):
    return (e or "").strip().lower()


def norm_phone(p):
    import re
    if not p:
        return None
    digits = re.sub(r"\D", "", p)
    return (digits[-10:] if len(digits) > 10 else digits) or None


TODAY = datetime.now(timezone.utc).date()


async def ensure_user(name, email, role, emp_id, team, manager_id=None, employment="Full-time"):
    email = norm_email(email)
    existing = await db.users.find_one({"email": email})
    if existing:
        await db.users.update_one({"email": email}, {"$set": {"role": role, "active": True, "team": team}})
        return existing["id"]
    uid = str(uuid.uuid4())
    await db.users.insert_one({
        "id": uid, "name": name, "email": email, "role": role, "employee_id": emp_id,
        "team": team, "manager_id": manager_id, "joining_date": (TODAY - timedelta(days=120)).isoformat(),
        "employment_type": employment, "active": True, "created_by": None, "created_at": now_iso(),
    })
    return uid


async def ensure_lead(name, owner, owner_name, status, source, team, phone, email,
                      practice, follow_days=None, demo_days=None, demo_status=None,
                      interactions=0, last_method=None):
    if await db.leads.find_one({"name": name}):
        return
    lid = str(uuid.uuid4())
    nf = (TODAY + timedelta(days=follow_days)).isoformat() if follow_days is not None else None
    dd = (TODAY + timedelta(days=demo_days)).isoformat() if demo_days is not None else None
    last_at = now_iso() if interactions else None
    doc = {
        "id": lid, "name": name, "phone": phone, "email": email, "instagram": "", "linkedin": "",
        "practice": practice, "location": "Bengaluru", "source": source, "status": status,
        "owner": owner, "team": team, "added_by": owner, "added_by_name": owner_name,
        "notes": "", "next_follow_up": nf, "followup_assigned_to": owner,
        "demo_date": dd, "demo_time": "15:00" if dd else None,
        "demo_owner": owner if demo_status else None, "demo_status": demo_status,
        "invoice_status": None, "payment_status": None,
        "conversion_status": ("Converted" if status == "Converted" else "Lost" if status in ("Lost", "Not Interested", "Closed") else "Open"),
        "custom": {}, "response": "",
        "last_interaction_at": last_at, "last_contacted_by": owner if interactions else None,
        "last_contacted_by_name": owner_name if interactions else None,
        "last_contact_method": last_method, "total_interactions": interactions,
        "created_at": now_iso(), "updated_at": now_iso(), "version": 1,
    }
    np_ = norm_phone(phone)
    ne = norm_email(email) or None
    if np_ and not await db.leads.find_one({"normalized_phone": np_}):
        doc["normalized_phone"] = np_
    if ne and not await db.leads.find_one({"normalized_email": ne}):
        doc["normalized_email"] = ne
    await db.leads.insert_one(doc)
    for i in range(interactions):
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "lead_id": lid, "lead_name": name,
            "employee_id": owner, "employee_name": owner_name,
            "type": last_method or "Call", "contact_method": last_method or "Call",
            "notes": f"Interaction {i+1} with {name}", "outcome": "Interested" if i == interactions - 1 else "",
            "next_action": "", "timestamp": now_iso(),
        })


async def main():
    mgr_id = await ensure_user("Paripsa Tripathi", "paripsa.tripathi@beet.health", "manager", "MGR-001", "Sales")
    priya = await ensure_user("Priya Sharma", "priya@beet.health", "employee", "EMP-101", "Sales", mgr_id)

    people = [(priya, "Priya Sharma", "Sales"), (mgr_id, "Paripsa Tripathi", "Sales")]

    samples = [
        ("Dr. Meera Clinic", "Contacted", "Instagram", -2, None, None, 2, "WhatsApp"),
        ("SmileCare Dental", "Interested", "Referral", 0, None, None, 3, "Call"),
        ("Wellness Physio", "Demo Booked", "Website", 3, 3, "Scheduled", 1, "Email"),
        ("GreenLeaf Ayurveda", "Demo Completed", "LinkedIn", 5, -1, "Completed", 4, "Call"),
        ("CityHeart Cardiology", "Pricing Shared", "Cold Outreach", 2, None, None, 5, "WhatsApp"),
        ("Sunrise Pediatrics", "Converted", "Referral", None, -7, "Completed", 6, "Call"),
        ("Apollo Skin", "Not Interested", "Instagram", None, None, None, 2, "Instagram"),
        ("Nova IVF", "New Lead", "Website", 1, None, None, 0, None),
    ]
    for i, (nm, status, source, fu, demo, ds, inter, method) in enumerate(samples):
        owner, oname, team = people[i % len(people)]
        await ensure_lead(nm, owner, oname, status, source, team,
                          f"98{random.randint(10000000, 99999999)}",
                          f"contact{i}@{nm.split()[0].lower()}.com",
                          nm, follow_days=fu, demo_days=demo, demo_status=ds,
                          interactions=inter, last_method=method)

    # Populate Priya's workspace with tasks + a demo + a notification.
    if await db.tasks.count_documents({"assigned_to": priya}) == 0:
        for title, days, prio in [("Follow up with Dr. Meera Clinic", -1, "High"),
                                   ("Send pricing to CityHeart Cardiology", 0, "Medium"),
                                   ("Prepare demo deck for SmileCare", 2, "Low")]:
            await db.tasks.insert_one({"id": str(uuid.uuid4()), "title": title, "lead_id": None, "lead_name": "",
                                       "assigned_to": priya, "assigned_by": mgr_id, "assigned_by_name": "Paripsa Tripathi",
                                       "due_date": (TODAY + timedelta(days=days)).isoformat(), "due_time": "11:00",
                                       "priority": prio, "status": "To Do", "notes": "", "created_by": mgr_id,
                                       "created_at": now_iso()})
        await db.notifications.insert_one({"id": str(uuid.uuid4()), "user_id": priya, "type": "assignment",
                                           "title": "Paripsa Tripathi assigned you: Follow-up",
                                           "body": "Dr. Meera Clinic · High", "link": "/dashboard", "read": False,
                                           "created_at": now_iso()})
    await db.leads.update_one({"name": "CityHeart Cardiology"},
                              {"$set": {"demo_date": (TODAY + timedelta(days=2)).isoformat(), "demo_time": "15:30",
                                        "demo_owner": priya, "demo_status": "Scheduled", "status": "Demo Booked"}})

    # Backfill real demo-completed + paid dates on already-won leads so the avg-days metric is real.
    for l in await db.leads.find({"$or": [{"status": "Converted"}, {"payment_status": "Paid"}]}).to_list(200):
        patch = {}
        if not l.get("demo_completed_at"):
            patch["demo_completed_at"] = l.get("demo_date") or (TODAY - timedelta(days=10)).isoformat()
        if not l.get("payment_date"):
            patch["payment_date"] = (TODAY - timedelta(days=3)).isoformat()
            patch["payment_status"] = "Paid"
        if patch:
            await db.leads.update_one({"id": l["id"]}, {"$set": patch})

    users = await db.users.find({}).to_list(100)
    leads = await db.leads.count_documents({})
    print("Users:")
    for u in users:
        print(" ", u["email"], "|", u["role"], "| active:", u.get("active"), "| team:", u.get("team"))
    print("Total leads:", leads)

asyncio.run(main())
