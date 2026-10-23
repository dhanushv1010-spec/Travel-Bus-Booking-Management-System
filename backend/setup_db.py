"""Creates the MySQL database, tables and demo data.   Run:  python setup_db.py"""
import os
import random
import string
from datetime import date, datetime, timedelta

import mysql.connector
from werkzeug.security import generate_password_hash

import config
from ds import CLASS_SURCHARGE, fare_breakdown, greedy_allocate

random.seed(7)
cfg = dict(config.DB)
dbname = cfg.pop("database")

conn = mysql.connector.connect(**cfg)
cur = conn.cursor()
cur.execute(f"CREATE DATABASE IF NOT EXISTS `{dbname}` CHARACTER SET utf8mb4")
cur.execute(f"USE `{dbname}`")

with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
    for stmt in f.read().split(";"):
        if stmt.strip():
            cur.execute(stmt)

# ---- users
users = [("System Admin", "admin", "admin123", "admin"),
         ("Ravi Kumar", "manager", "manager123", "manager"),
         ("Meena Iyer", "manager2", "manager123", "manager"),
         ("Demo Customer", "customer", "customer123", "customer"),
         ("Counter Sales", "counter", "counter123", "customer")]
for name, user, pw, role in users:
    cur.execute("INSERT INTO users (name,username,password_hash,role) VALUES (%s,%s,%s,%s)",
                (name, user, generate_password_hash(pw), role))
cur.execute("SELECT id,username FROM users")
uid = {u: i for i, u in cur.fetchall()}

# ---- cities and routes
cities = ["Bengaluru", "Mysuru", "Chennai", "Hyderabad", "Coimbatore", "Kochi", "Mangaluru"]
for c in cities:
    cur.execute("INSERT INTO cities (name) VALUES (%s)", (c,))
cur.execute("SELECT id,name FROM cities")
cid = {n: i for i, n in cur.fetchall()}

routes = [("Bengaluru", "Mysuru", 150), ("Bengaluru", "Chennai", 346), ("Bengaluru", "Hyderabad", 570),
          ("Bengaluru", "Coimbatore", 365), ("Coimbatore", "Kochi", 190), ("Mysuru", "Mangaluru", 270),
          ("Mysuru", "Coimbatore", 195), ("Chennai", "Coimbatore", 505), ("Hyderabad", "Chennai", 630)]
rid = {}
for a, b, km in routes:
    x, y = sorted((cid[a], cid[b]))
    cur.execute("INSERT INTO routes (city_a,city_b,distance_km) VALUES (%s,%s,%s)", (x, y, km))
    rid[frozenset((a, b))] = (cur.lastrowid, km)

# ---- buses: (reg, name, seats, rate, manager)
buses = [("KA01WF1001", "Wayfare Express", 40, 2.20, "manager"),
         ("KA01WF1002", "Deccan Queen", 40, 2.60, "manager"),
         ("KA05WF3001", "Southern Star", 40, 2.40, "manager2"),
         ("KL07WF4001", "Kerala Link", 36, 2.00, "manager2"),
         ("KA19WF5001", "Coastal Cruiser", 40, 2.30, "manager2"),
         ("TS09WF6001", "Charminar Liner", 40, 2.50, "manager"),
         ("TN01WF7001", "Marina Mail", 40, 2.30, "manager"),
         ("KA09WF8001", "Nilgiri Express", 40, 2.10, "manager2")]
bus = {}
for reg, name, seats, rate, mgr in buses:
    cur.execute("INSERT INTO buses (reg_no,name,total_seats,rate_per_km,manager_id) VALUES (%s,%s,%s,%s,%s)",
                (reg, name, seats, rate, uid[mgr]))
    bus[reg] = (cur.lastrowid, seats, rate)

# ---- daily trips: (bus, from, to, time, day parity or None)
plan = [("KA01WF1001", "Bengaluru", "Mysuru", "06:30", None), ("KA01WF1001", "Mysuru", "Bengaluru", "17:30", None),
        ("KA01WF1002", "Bengaluru", "Mysuru", "09:00", None), ("KA01WF1002", "Mysuru", "Bengaluru", "14:00", None),
        ("KA05WF3001", "Bengaluru", "Coimbatore", "07:00", None), ("KA05WF3001", "Coimbatore", "Bengaluru", "16:00", None),
        ("KL07WF4001", "Coimbatore", "Kochi", "15:00", None), ("KL07WF4001", "Kochi", "Coimbatore", "19:30", None),
        ("KA19WF5001", "Mysuru", "Mangaluru", "07:30", None), ("KA19WF5001", "Mangaluru", "Mysuru", "15:00", None),
        ("KA09WF8001", "Mysuru", "Coimbatore", "06:00", None), ("KA09WF8001", "Coimbatore", "Mysuru", "12:00", None),
        ("TS09WF6001", "Bengaluru", "Hyderabad", "19:00", 0), ("TS09WF6001", "Hyderabad", "Bengaluru", "19:00", 1),
        ("TN01WF7001", "Bengaluru", "Chennai", "22:00", 0), ("TN01WF7001", "Chennai", "Bengaluru", "22:00", 1)]
trip_rows = []
today = date.today()
for d in range(0, 8):
    day = today + timedelta(days=d)
    for reg, a, b, tm, parity in plan:
        if parity is not None and d % 2 != parity:
            continue
        if datetime.combine(day, datetime.strptime(tm, "%H:%M").time()) <= datetime.now():
            continue
        route_id, km = rid[frozenset((a, b))]
        cur.execute("""INSERT INTO trips (bus_id,route_id,source_id,dest_id,travel_date,departure_time)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (bus[reg][0], route_id, cid[a], cid[b], day, tm + ":00"))
        trip_rows.append((cur.lastrowid, reg, km, a, b, day, tm))

# ---- demo occupancy
first = ["Anil", "Bhavya", "Charan", "Divya", "Eshwar", "Farah", "Gopal", "Hema", "Imran", "Janani", "Kiran", "Lata"]
used = set()


def pnr():
    while True:
        p = "WF" + "".join(random.choices(string.digits, k=8))
        if p not in used:
            used.add(p)
            return p


showcase = trip_rows[0][0] if trip_rows else None   # a nearly full trip, to try the waitlist
for tid, reg, km, a, b, day, tm in trip_rows:
    _, seats, rate = bus[reg]
    n = seats - 2 if tid == showcase else random.randint(3, seats // 2)
    taken = sorted(random.sample(range(1, seats + 1), n))
    for s in taken:
        cls = random.choice(["Economy"] * 4 + ["Premium"] * 2 + ["Deluxe"])
        fare = fare_breakdown(rate, km, cls)["total"]
        p = pnr()
        cur.execute("""INSERT INTO bookings (pnr,group_ref,trip_id,user_id,passenger_name,age,seat_no,seat_class,
                       fare,status,active,booked_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'CONFIRMED',1,%s)""",
                    (p, p, tid, uid["counter"], f"{random.choice(first)} {random.choice('KMNRSV')}.",
                     random.randint(18, 70), s, cls, fare, datetime.now() - timedelta(hours=random.randint(1, 90))))

conn.commit()
cur.close()
conn.close()
print(f"Database '{dbname}' is ready with {len(trip_rows)} trips.")
print("Sign in with:  admin/admin123   manager/manager123   customer/customer123")
