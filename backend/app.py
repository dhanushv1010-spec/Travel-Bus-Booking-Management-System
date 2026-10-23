import json
import random
import string
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

import mysql.connector
from flask import Flask, g, jsonify, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import config
from ds import (BST, CLASS_SURCHARGE, Graph, LinkedList, Queue, Stack, binary_search,
                fare_breakdown, greedy_allocate, greedy_fill, quick_sort, r2, refund_amount)

app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.secret_key = config.SECRET_KEY
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

AVG_SPEED = 50          # km/h, used for arrival estimates
TRANSFER_MIN = 30       # minimum wait between connecting legs
MAX_GROUP = 6
ROLE_LABEL = {"admin": "an admin", "customer": "a customer", "manager": "a bus manager"}
UNDO = {}               # user id -> Stack of last booking actions


# ------------------------------------------------------------------ helpers
class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.msg, self.code = msg, code


@app.errorhandler(ApiError)
def _api_error(e):
    return jsonify(error=e.msg), e.code


@app.errorhandler(mysql.connector.IntegrityError)
def _integrity(e):
    if e.errno == 1062:
        return jsonify(error="That already exists."), 409
    return jsonify(error="This item is linked to other records, so it can't be removed."), 409


@app.errorhandler(mysql.connector.Error)
def _db_error(e):
    hints = {1045: "MySQL rejected the username or password. Check DB_USER / password in backend/config.py.",
             1049: "The database doesn't exist yet. Run: python setup_db.py",
             1146: "The tables are missing. Run: python setup_db.py",
             2003: "Can't reach MySQL. Make sure the MySQL server is running."}
    app.logger.error("Database error: %s", e)
    return jsonify(error=hints.get(getattr(e, "errno", None), f"Database error: {e}")), 500


@app.errorhandler(Exception)
def _unexpected(e):
    if isinstance(e, HTTPException):
        return e
    app.logger.exception("Unexpected error")
    return jsonify(error=f"Server error: {type(e).__name__}: {e}"), 500


@app.errorhandler(KeyError)
@app.errorhandler(ValueError)
@app.errorhandler(TypeError)
def _bad_input(e):
    return jsonify(error="Some details are missing or invalid. Please check and try again."), 400


def get_db():
    if "db" not in g:
        g.db = mysql.connector.connect(**config.DB)
    return g.db


@app.teardown_appcontext
def _close(_):
    db = g.pop("db", None)
    if db:
        db.close()


@app.after_request
def _finish(resp):
    db = g.get("db")
    if db:
        try:
            db.commit() if resp.status_code < 400 else db.rollback()
        except Exception:
            pass
    return resp


def query(sql, args=(), one=False):
    cur = get_db().cursor(dictionary=True)
    cur.execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    cur = get_db().cursor()
    cur.execute(sql, args)
    last = cur.lastrowid
    cur.close()
    return last


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, datetime):
        return o.strftime("%Y-%m-%d %H:%M")
    if isinstance(o, date):
        return o.isoformat()
    if isinstance(o, timedelta):
        s = int(o.total_seconds())
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}"
    return o


def ok(data=None, **kw):
    return jsonify(clean(data if data is not None else kw))


def need(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **k):
            if "uid" not in session:
                raise ApiError("Please sign in to continue.", 401)
            if roles and session["role"] not in roles:
                raise ApiError("You don't have access to this.", 403)
            return f(*a, **k)
        return wrapper
    return deco


def body():
    return request.get_json(force=True, silent=True) or {}


def hhmm(td):
    s = int(td.total_seconds())
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}"


# ------------------------------------------------------------------ trips
TRIP_SQL = """SELECT t.id,t.bus_id,t.route_id,t.source_id,t.dest_id,t.travel_date,t.departure_time,t.status,
  b.name AS bus_name,b.reg_no,b.total_seats,b.rate_per_km,b.manager_id,r.distance_km,
  cs.name AS source,cd.name AS dest
  FROM trips t JOIN buses b ON b.id=t.bus_id JOIN routes r ON r.id=t.route_id
  JOIN cities cs ON cs.id=t.source_id JOIN cities cd ON cd.id=t.dest_id"""

BOOKING_SQL = """SELECT b.id,b.pnr,b.group_ref,b.trip_id,b.user_id,b.passenger_name,b.age,b.seat_no,b.seat_class,
  b.fare,b.refund,b.status,b.booked_at,t.travel_date,t.departure_time,cs.name AS source,cd.name AS dest,
  bu.name AS bus_name,bu.reg_no,bu.manager_id,r.distance_km,u.name AS booked_by
  FROM bookings b JOIN trips t ON t.id=b.trip_id JOIN buses bu ON bu.id=t.bus_id JOIN routes r ON r.id=t.route_id
  JOIN cities cs ON cs.id=t.source_id JOIN cities cd ON cd.id=t.dest_id JOIN users u ON u.id=b.user_id"""


def dep_dt(t):
    return datetime.combine(t["travel_date"], datetime.min.time()) + t["departure_time"]


def duration_min(t):
    return round(t["distance_km"] / AVG_SPEED * 60)


def decorate(t, booked=0):
    d = dep_dt(t)
    dur = duration_min(t)
    fares = {c: fare_breakdown(t["rate_per_km"], t["distance_km"], c)["total"] for c in CLASS_SURCHARGE}
    return {**t, "dep": d, "arr": d + timedelta(minutes=dur), "duration": dur,
            "seats_left": t["total_seats"] - booked, "fares": fares, "fare": fares["Economy"]}


def trip_key(t):
    return f"{t['source_id']:04d}|{t['dest_id']:04d}|{t['travel_date']}|{hhmm(t['departure_time'])}|{t['id']:06d}"


def booked_map():
    return {r["trip_id"]: int(r["n"]) for r in query(
        "SELECT trip_id,COUNT(*) n FROM bookings WHERE status='CONFIRMED' GROUP BY trip_id")}


def lock_trip(tid):
    query("SELECT id FROM trips WHERE id=%s FOR UPDATE", (tid,))
    t = query(TRIP_SQL + " WHERE t.id=%s", (tid,), one=True)
    if not t:
        raise ApiError("Trip not found.", 404)
    return t


def free_seats(t):
    taken = {r["seat_no"] for r in query(
        "SELECT seat_no FROM bookings WHERE trip_id=%s AND status='CONFIRMED'", (t["id"],))}
    return [n for n in range(1, t["total_seats"] + 1) if n not in taken]


def ensure_open(t):
    if t["status"] != "SCHEDULED":
        raise ApiError("This trip has been cancelled.", 409)
    if dep_dt(t) <= datetime.now():
        raise ApiError("This trip has already departed.", 409)


# ------------------------------------------------------------------ auth
@app.get("/")
def index():
    return app.send_static_file("index.html")


def me_payload():
    return {"id": session["uid"], "name": session["name"], "role": session["role"]}


@app.post("/api/login")
def login():
    d = body()
    u = query("SELECT * FROM users WHERE username=%s", (str(d.get("username", "")).strip(),), one=True)
    if not u or not check_password_hash(u["password_hash"], str(d.get("password", ""))):
        raise ApiError("Wrong username or password.", 401)
    if d.get("role") and u["role"] != d["role"]:
        raise ApiError(f"This account is not registered as {ROLE_LABEL.get(d['role'], 'that role')}.", 403)
    session.clear()
    session.update(uid=u["id"], role=u["role"], name=u["name"])
    return ok(me_payload())


@app.post("/api/register")
def register():
    d = body()
    name, user, pw = str(d["name"]).strip(), str(d["username"]).strip(), str(d["password"])
    if len(name) < 2 or len(user) < 3 or len(pw) < 6:
        raise ApiError("Use a name, a username of 3+ characters and a password of 6+ characters.")
    uid = execute("INSERT INTO users (name,username,email,password_hash,role) VALUES (%s,%s,%s,%s,'customer')",
                  (name, user, str(d.get("email", "")).strip() or None, generate_password_hash(pw)))
    session.clear()
    session.update(uid=uid, role="customer", name=name)
    return ok(me_payload())


@app.post("/api/logout")
def logout():
    session.clear()
    return ok(done=True)


@app.get("/api/me")
def me():
    if "uid" not in session:
        raise ApiError("Not signed in.", 401)
    return ok(me_payload())


# ------------------------------------------------------------------ shared lookups
@app.get("/api/cities")
@need()
def cities():
    return ok(query("SELECT id,name FROM cities ORDER BY name"))


@app.get("/api/routes")
@need()
def routes():
    return ok(query("""SELECT r.id,r.city_a,r.city_b,r.distance_km,a.name a_name,b.name b_name
        FROM routes r JOIN cities a ON a.id=r.city_a JOIN cities b ON b.id=r.city_b ORDER BY a.name,b.name"""))


# ------------------------------------------------------------------ search (customer)
def next_trip_date(src, dst, day):
    sql = ("SELECT MIN(travel_date) d FROM trips WHERE status='SCHEDULED' AND travel_date>=%s "
           "AND TIMESTAMP(travel_date,departure_time)>NOW()")
    args = [day]
    if src:
        sql += " AND source_id=%s"
        args.append(src)
    if dst:
        sql += " AND dest_id=%s"
        args.append(dst)
    return query(sql, tuple(args), one=True)["d"]


@app.get("/api/search")
@need("customer")
def search():
    day = date.fromisoformat(request.args["date"])
    src = int(request.args["from"]) if request.args.get("from") else None
    dst = int(request.args["to"]) if request.args.get("to") else None
    sort = request.args.get("sort", "departure")
    if src and src == dst:
        raise ApiError("Choose two different cities.")
    if day < date.today():
        raise ApiError("Choose today or a later date.")
    now = datetime.now()

    booked = booked_map()
    taken = {}
    for r in query("""SELECT bk.trip_id,bk.seat_no FROM bookings bk JOIN trips t ON t.id=bk.trip_id
                      WHERE bk.status='CONFIRMED' AND t.travel_date=%s""", (day,)):
        taken.setdefault(r["trip_id"], []).append(r["seat_no"])
    tree = BST()
    for t in query(TRIP_SQL + " WHERE t.status='SCHEDULED' AND t.travel_date=%s", (day,)):
        d = decorate(t, booked.get(t["id"], 0))
        d["booked_seats"] = taken.get(t["id"], [])
        tree.insert(trip_key(t), d)

    skey = (lambda x: (x["fare"], x["dep"])) if sort == "fare" else (lambda x: (x["dep"], x["fare"]))

    # Browse mode: no city (or only one city) chosen -> list every bus running that day
    if not (src and dst):
        items = [v for _, v in tree.inorder() if v["dep"] > now
                 and (not src or v["source_id"] == src) and (not dst or v["dest_id"] == dst)]
        items = quick_sort(items, key=skey)
        return ok(direct=items, connecting=[], has_route=True, browse=True, last_date=None,
                  next_date=None if items else next_trip_date(src, dst, day))

    graph = Graph()
    for r in query("SELECT city_a,city_b,distance_km FROM routes"):
        graph.add_edge(r["city_a"], r["city_b"], r["distance_km"])

    def leg_trips(a, b):
        return [v for _, v in tree.prefix(f"{a:04d}|{b:04d}|{day}|") if v["dep"] > now]

    paths = graph.bfs_paths(src, dst, max_legs=3)
    direct = quick_sort(leg_trips(src, dst), key=skey)

    connecting = []
    for path in [p for p in paths if len(p) > 2]:
        legs = [leg_trips(path[i], path[i + 1]) for i in range(len(path) - 1)]
        for first in legs[0][:6]:
            chain, arr = [first], first["arr"]
            for nxt in legs[1:]:
                pick = next((x for x in nxt if x["dep"] >= arr + timedelta(minutes=TRANSFER_MIN)), None)
                if not pick:
                    chain = None
                    break
                chain.append(pick)
                arr = pick["arr"]
            if chain:
                connecting.append({"legs": chain, "dep": chain[0]["dep"], "arr": chain[-1]["arr"],
                                   "duration": int((chain[-1]["arr"] - chain[0]["dep"]).total_seconds() // 60),
                                   "fare": sum(x["fare"] for x in chain),
                                   "via": [c["source"] for c in chain[1:]]})
    connecting = quick_sort(connecting, key=skey)[:8]
    next_date = last_date = None
    if not direct and not connecting and paths:
        next_date = next_trip_date(src, dst, day)
        if not next_date:
            last_date = query("SELECT MAX(travel_date) d FROM trips WHERE status='SCHEDULED' AND source_id=%s "
                              "AND dest_id=%s", (src, dst), one=True)["d"]
    return ok(direct=direct, connecting=connecting, has_route=bool(paths), browse=False,
              next_date=next_date, last_date=last_date)


@app.get("/api/routes/overview")
@need("customer")
def routes_overview():
    stats = {(r["source_id"], r["dest_id"]): r for r in query(
        """SELECT source_id,dest_id,COUNT(*) n,MIN(TIMESTAMP(travel_date,departure_time)) nxt FROM trips
           WHERE status='SCHEDULED' AND TIMESTAMP(travel_date,departure_time)>NOW() GROUP BY source_id,dest_id""")}
    out = []
    for r in query("""SELECT r.city_a,r.city_b,r.distance_km,a.name a_name,b.name b_name FROM routes r
                     JOIN cities a ON a.id=r.city_a JOIN cities b ON b.id=r.city_b"""):
        for s, d, sn, dn in ((r["city_a"], r["city_b"], r["a_name"], r["b_name"]),
                             (r["city_b"], r["city_a"], r["b_name"], r["a_name"])):
            st = stats.get((s, d))
            out.append({"source_id": s, "dest_id": d, "source": sn, "dest": dn, "distance_km": r["distance_km"],
                        "trips": int(st["n"]) if st else 0, "next": st["nxt"] if st else None})
    return ok(sorted(out, key=lambda x: (x["source"], x["dest"])))


@app.get("/api/trips/<int:tid>/seats")
@need("customer")
def trip_seats(tid):
    t = query(TRIP_SQL + " WHERE t.id=%s", (tid,), one=True)
    if not t:
        raise ApiError("Trip not found.", 404)
    taken = [r["seat_no"] for r in query(
        "SELECT seat_no FROM bookings WHERE trip_id=%s AND status='CONFIRMED'", (tid,))]
    return ok(trip=decorate(t, len(taken)), booked=taken)


@app.get("/api/trips/<int:tid>/quote")
@need("customer")
def quote(tid):
    t = query(TRIP_SQL + " WHERE t.id=%s", (tid,), one=True)
    cls, count = request.args.get("cls", "Economy"), int(request.args.get("count", 1))
    if not t or cls not in CLASS_SURCHARGE or not 1 <= count <= MAX_GROUP:
        raise ApiError("Invalid request.")
    per = fare_breakdown(t["rate_per_km"], t["distance_km"], cls)
    return ok(per_seat=per, count=count, total=per["total"] * count)


# ------------------------------------------------------------------ booking
def clean_passengers(raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_GROUP:
        raise ApiError(f"Add between 1 and {MAX_GROUP} passengers.")
    out = []
    for p in raw:
        name, age = str(p.get("name", "")).strip()[:60], int(p.get("age", 0))
        if len(name) < 2 or not 1 <= age <= 120:
            raise ApiError("Each passenger needs a name and an age between 1 and 120.")
        out.append({"name": name, "age": age})
    return out


def new_pnr():
    while True:
        pnr = "WF" + "".join(random.choices(string.digits, k=8))
        if not query("SELECT id FROM bookings WHERE pnr=%s", (pnr,)):
            return pnr


def create_bookings(t, uid, pax, seats, cls):
    fare = fare_breakdown(t["rate_per_km"], t["distance_km"], cls)["total"]
    ids, group = [], None
    for p, s in zip(pax, seats):
        pnr = new_pnr()
        group = group or pnr
        ids.append(execute(
            """INSERT INTO bookings (pnr,group_ref,trip_id,user_id,passenger_name,age,seat_no,seat_class,fare,
               status,active,booked_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'CONFIRMED',1,%s)""",
            (pnr, group, t["id"], uid, p["name"], p["age"], s, cls, fare, datetime.now())))
    return ids


def bookings_by_ids(ids):
    if not ids:
        return []
    return query(BOOKING_SQL + " WHERE b.id IN (%s) ORDER BY b.seat_no" % ",".join(["%s"] * len(ids)), tuple(ids))


def with_flags(rows):
    now = datetime.now()
    for r in rows:
        r["can_cancel"] = r["status"] == "CONFIRMED" and dep_dt(r) > now
    return rows


@app.post("/api/book")
@need("customer")
def book():
    d = body()
    t = lock_trip(int(d["trip_id"]))
    ensure_open(t)
    pax = clean_passengers(d.get("passengers"))
    cls, pref = d.get("seat_class", "Economy"), d.get("preference", "any")
    if cls not in CLASS_SURCHARGE or pref not in ("any", "window", "aisle", "front"):
        raise ApiError("Invalid class or seat preference.")
    free = free_seats(t)
    manual = sorted({int(s) for s in d.get("seats") or []})
    if len(free) < len(pax):
        seats = None
    elif manual:
        if len(manual) != len(pax) or any(s not in free for s in manual):
            raise ApiError("One or more of the seats you picked were just taken. Please pick again.", 409)
        seats = manual
    else:
        seats = greedy_allocate(free, len(pax), pref)

    if seats is None:
        execute("""INSERT INTO waitlist (trip_id,user_id,seats_needed,seat_class,preference,passengers,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (t["id"], session["uid"], len(pax), cls, pref, json.dumps(pax), datetime.now()))
        return ok(waitlisted=True, message="This trip doesn't have enough free seats. "
                  "You're on the waitlist and will get seats automatically if some free up.")
    ids = create_bookings(t, session["uid"], pax, seats, cls)
    UNDO.setdefault(session["uid"], Stack()).push({"ids": ids})
    return ok(waitlisted=False, bookings=bookings_by_ids(ids))


def cancel_booking(b, t, full=False):
    hours = (dep_dt(t) - datetime.now()).total_seconds() / 3600
    refund = refund_amount(b["fare"], hours, full)
    execute("UPDATE bookings SET status='CANCELLED',active=NULL,refund=%s,cancelled_at=%s WHERE id=%s",
            (refund, datetime.now(), b["id"]))
    return refund


def promote(t, strategy="order"):
    """Seat waiting passengers into freed seats. 'order' serves the waitlist in
    arrival order; 'revenue' picks the requests worth the most per seat."""
    if t["status"] != "SCHEDULED" or dep_dt(t) <= datetime.now():
        return []
    free = free_seats(t)
    waiting = Queue()
    for w in query("SELECT * FROM waitlist WHERE trip_id=%s AND status='WAITING' ORDER BY id", (t["id"],)):
        waiting.enqueue(w)
    chosen = []
    if strategy == "revenue":
        reqs = [{"id": w["id"], "seats": w["seats_needed"], "w": w,
                 "fare": float(fare_breakdown(t["rate_per_km"], t["distance_km"], w["seat_class"])["total"])
                 * w["seats_needed"]} for w in waiting]
        chosen = [r["w"] for r in greedy_fill(reqs, len(free))]
    else:
        left = len(free)
        while not waiting.is_empty():
            w = waiting.dequeue()
            if w["seats_needed"] <= left:
                chosen.append(w)
                left -= w["seats_needed"]
    done = []
    for w in chosen:
        seats = greedy_allocate(free, w["seats_needed"], w["preference"])
        ids = create_bookings(t, w["user_id"], json.loads(w["passengers"]), seats, w["seat_class"])
        execute("UPDATE waitlist SET status='PROMOTED' WHERE id=%s", (w["id"],))
        free = [s for s in free if s not in seats]
        done.append({"waitlist_id": w["id"], "seats": seats, "booking_ids": ids})
    return done


@app.get("/api/my/bookings")
@need("customer")
def my_bookings():
    rows = query(BOOKING_SQL + " WHERE b.user_id=%s ORDER BY t.travel_date DESC,t.departure_time DESC,b.id",
                 (session["uid"],))
    return ok(with_flags(rows), )


@app.post("/api/bookings/<int:bid>/cancel")
@need("customer")
def cancel_ticket(bid):
    b = query(BOOKING_SQL + " WHERE b.id=%s", (bid,), one=True)
    if not b or b["user_id"] != session["uid"]:
        raise ApiError("Ticket not found.", 404)
    t = lock_trip(b["trip_id"])
    b = query(BOOKING_SQL + " WHERE b.id=%s", (bid,), one=True)
    if b["status"] != "CONFIRMED":
        raise ApiError("This ticket is already cancelled.", 409)
    if dep_dt(t) <= datetime.now():
        raise ApiError("This trip has already departed.", 409)
    refund = cancel_booking(b, t)
    promote(t)
    return ok(message=f"Ticket {b['pnr']} cancelled. Refund: ₹{refund}", refund=refund)


@app.post("/api/undo")
@need("customer")
def undo():
    st = UNDO.setdefault(session["uid"], Stack())
    while not st.is_empty():
        ids = st.pop()["ids"]
        live = [b for b in bookings_by_ids(ids) if b["status"] == "CONFIRMED" and b["user_id"] == session["uid"]]
        if not live:
            continue
        t = lock_trip(live[0]["trip_id"])
        if dep_dt(t) <= datetime.now():
            raise ApiError("That trip has already departed, so the booking can't be undone.", 409)
        refund = sum(cancel_booking(b, t, full=True) for b in live)
        promote(t)
        return ok(message=f"Last booking undone ({len(live)} seat{'s' if len(live) > 1 else ''}). "
                          f"Full refund: ₹{r2(refund)}")
    raise ApiError("There's no recent booking to undo.", 404)


@app.get("/api/my/waitlist")
@need("customer")
def my_waitlist():
    rows = query("""SELECT w.id,w.seats_needed,w.seat_class,w.created_at,t.travel_date,t.departure_time,
        cs.name source,cd.name dest FROM waitlist w JOIN trips t ON t.id=w.trip_id
        JOIN cities cs ON cs.id=t.source_id JOIN cities cd ON cd.id=t.dest_id
        WHERE w.user_id=%s AND w.status='WAITING' ORDER BY w.id""", (session["uid"],))
    return ok(rows)


@app.post("/api/waitlist/<int:wid>/cancel")
@need("customer")
def cancel_wait(wid):
    execute("UPDATE waitlist SET status='CANCELLED' WHERE id=%s AND user_id=%s AND status='WAITING'",
            (wid, session["uid"]))
    return ok(message="Removed from the waitlist.")


@app.get("/api/lookup/<pnr>")
@need()
def lookup(pnr):
    role, uid = session["role"], session["uid"]
    scope = {"customer": (" WHERE b.user_id=%s", (uid,)), "manager": (" WHERE bu.manager_id=%s", (uid,))}
    sql, args = scope.get(role, ("", ()))
    rows = quick_sort(query(BOOKING_SQL + sql, args), key=lambda r: r["pnr"])
    i = binary_search(rows, pnr.strip().upper(), key=lambda r: r["pnr"])
    if i < 0:
        raise ApiError("No ticket found with that PNR.", 404)
    return ok(with_flags([rows[i]])[0])


# ------------------------------------------------------------------ manager + admin: trips
def scope_sql():
    return ("b.manager_id=%s", (session["uid"],)) if session["role"] == "manager" else ("1=1", ())


def can_manage(t):
    return session["role"] == "admin" or t["manager_id"] == session["uid"]


@app.get("/api/manage/buses")
@need("manager", "admin")
def manage_buses():
    where, args = scope_sql()
    return ok(query(f"SELECT id,reg_no,name,total_seats,rate_per_km FROM buses b WHERE {where} ORDER BY name", args))


@app.get("/api/manage/trips")
@need("manager", "admin")
def manage_trips():
    where, args = scope_sql()
    stats = {r["trip_id"]: r for r in query(
        """SELECT trip_id,COALESCE(SUM(status='CONFIRMED'),0) booked,COALESCE(SUM(fare-refund),0) revenue
           FROM bookings GROUP BY trip_id""")}
    waits = {r["trip_id"]: r for r in query(
        "SELECT trip_id,COUNT(*) n,SUM(seats_needed) seats FROM waitlist WHERE status='WAITING' GROUP BY trip_id")}
    tree = BST()
    for t in query(TRIP_SQL + f" WHERE {where}", args):
        s, w = stats.get(t["id"]), waits.get(t["id"])
        d = decorate(t, int(s["booked"]) if s else 0)
        d.update(booked=int(s["booked"]) if s else 0, revenue=s["revenue"] if s else 0,
                 waiting=int(w["seats"]) if w else 0, departed=d["dep"] <= datetime.now())
        key = f"{t['source']}|{t['dest']}|{t['travel_date']}|{hhmm(t['departure_time'])}|{t['id']:06d}"
        tree.insert(key, d)
    return ok([v for _, v in tree.inorder()])   # route-wise, then by date and time


@app.post("/api/manage/trips")
@need("manager", "admin")
def add_trip():
    d = body()
    bus = query("SELECT * FROM buses WHERE id=%s", (int(d["bus_id"]),), one=True)
    if not bus or not (session["role"] == "admin" or bus["manager_id"] == session["uid"]):
        raise ApiError("Choose one of your buses.", 403)
    src, dst = int(d["source_id"]), int(d["dest_id"])
    route = query("SELECT * FROM routes WHERE (city_a=%s AND city_b=%s) OR (city_a=%s AND city_b=%s)",
                  (src, dst, dst, src), one=True)
    if not route:
        raise ApiError("There's no route between those cities.")
    first_day = date.fromisoformat(d["date"])
    hh, mm = [int(x) for x in str(d["time"]).split(":")[:2]]
    repeat = max(1, min(int(d.get("repeat_days") or 1), 60))
    length = timedelta(minutes=round(route["distance_km"] / AVG_SPEED * 60))
    created, reason = 0, None
    for i in range(repeat):
        day = first_day + timedelta(days=i)
        start = datetime.combine(day, datetime.min.time()) + timedelta(hours=hh, minutes=mm)
        if start <= datetime.now():
            reason = reason or "Pick a departure time in the future."
            continue
        end = start + length
        clash = None
        for o in query(TRIP_SQL + " WHERE t.bus_id=%s AND t.status='SCHEDULED' AND t.travel_date BETWEEN %s AND %s",
                       (bus["id"], day - timedelta(days=1), day + timedelta(days=1))):
            o_start = dep_dt(o)
            o_end = o_start + timedelta(minutes=duration_min(o))
            if start < o_end + timedelta(hours=1) and o_start < end + timedelta(hours=1):
                clash = o
                break
        if clash:
            reason = reason or (f"This bus is already on {clash['source']} to {clash['dest']} around that time "
                                "(allow a 1 hour turnaround).")
            continue
        execute("""INSERT INTO trips (bus_id,route_id,source_id,dest_id,travel_date,departure_time)
                   VALUES (%s,%s,%s,%s,%s,%s)""", (bus["id"], route["id"], src, dst, day, f"{hh:02d}:{mm:02d}:00"))
        created += 1
    if not created:
        raise ApiError(reason or "No trips were added.", 409)
    skipped = repeat - created
    return ok(created=created, message=f"{created} trip{'s' if created > 1 else ''} added."
              + (f" {skipped} day{'s' if skipped > 1 else ''} skipped because of clashes or past times." if skipped else ""))


@app.post("/api/manage/trips/<int:tid>/cancel")
@need("manager", "admin")
def cancel_trip(tid):
    t = lock_trip(tid)
    if not can_manage(t):
        raise ApiError("Not your trip.", 403)
    if t["status"] != "SCHEDULED":
        raise ApiError("This trip is already cancelled.", 409)
    rows = query(BOOKING_SQL + " WHERE b.trip_id=%s AND b.status='CONFIRMED'", (tid,))
    total = sum(cancel_booking(b, t, full=True) for b in rows)
    execute("UPDATE waitlist SET status='CANCELLED' WHERE trip_id=%s AND status='WAITING'", (tid,))
    execute("UPDATE trips SET status='CANCELLED' WHERE id=%s", (tid,))
    return ok(message=f"Trip cancelled. {len(rows)} ticket(s) refunded in full (₹{r2(total)}).")


@app.get("/api/manage/trips/<int:tid>/details")
@need("manager", "admin")
def trip_details(tid):
    t = query(TRIP_SQL + " WHERE t.id=%s", (tid,), one=True)
    if not t or not can_manage(t):
        raise ApiError("Trip not found.", 404)
    registry = LinkedList()
    for b in query(BOOKING_SQL + " WHERE b.trip_id=%s AND b.status='CONFIRMED' ORDER BY b.id", (tid,)):
        registry.append(b)
    waiting = Queue()
    for w in query("""SELECT w.id,w.seats_needed,w.seat_class,w.created_at,u.name FROM waitlist w
                      JOIN users u ON u.id=w.user_id WHERE w.trip_id=%s AND w.status='WAITING' ORDER BY w.id""", (tid,)):
        waiting.enqueue(w)
    booked = len(registry)
    return ok(trip=decorate(t, booked), manifest=list(registry), waitlist=list(waiting),
              free=t["total_seats"] - booked)


@app.post("/api/manage/trips/<int:tid>/fill")
@need("manager", "admin")
def fill_trip(tid):
    t = lock_trip(tid)
    if not can_manage(t):
        raise ApiError("Not your trip.", 403)
    strategy = "revenue" if body().get("strategy") == "revenue" else "order"
    done = promote(t, strategy)
    n = sum(len(x["seats"]) for x in done)
    return ok(message=f"{n} waitlisted seat(s) confirmed." if n else "No waitlisted request fits the free seats.")


# ------------------------------------------------------------------ admin
@app.get("/api/admin/stats")
@need("admin")
def stats():
    one = lambda sql: list(query(sql, one=True).values())[0] or 0
    by_route = query("""SELECT cs.name source,cd.name dest,COUNT(*) tickets,SUM(b.fare-b.refund) revenue
        FROM bookings b JOIN trips t ON t.id=b.trip_id JOIN cities cs ON cs.id=t.source_id
        JOIN cities cd ON cd.id=t.dest_id GROUP BY cs.name,cd.name ORDER BY revenue DESC LIMIT 8""")
    return ok(revenue=one("SELECT SUM(fare-refund) FROM bookings"),
              confirmed=one("SELECT COUNT(*) FROM bookings WHERE status='CONFIRMED'"),
              cancelled=one("SELECT COUNT(*) FROM bookings WHERE status='CANCELLED'"),
              upcoming=one("SELECT COUNT(*) FROM trips WHERE status='SCHEDULED' AND "
                           "TIMESTAMP(travel_date,departure_time)>NOW()"),
              waiting=one("SELECT COALESCE(SUM(seats_needed),0) FROM waitlist WHERE status='WAITING'"),
              buses=one("SELECT COUNT(*) FROM buses"),
              customers=one("SELECT COUNT(*) FROM users WHERE role='customer'"),
              managers=one("SELECT COUNT(*) FROM users WHERE role='manager'"),
              by_route=by_route)


@app.get("/api/admin/users")
@need("admin")
def users():
    return ok(query("SELECT id,name,username,email,role,created_at FROM users ORDER BY role,name"))


@app.post("/api/admin/users")
@need("admin")
def add_user():
    d = body()
    role = d["role"]
    if role not in ("manager", "customer", "admin") or len(str(d["password"])) < 6 or len(str(d["username"])) < 3:
        raise ApiError("Use a username of 3+ characters and a password of 6+ characters.")
    execute("INSERT INTO users (name,username,email,password_hash,role) VALUES (%s,%s,%s,%s,%s)",
            (str(d["name"]).strip(), str(d["username"]).strip(), d.get("email") or None,
             generate_password_hash(str(d["password"])), role))
    return ok(message="Account created.")


@app.delete("/api/admin/users/<int:uid>")
@need("admin")
def del_user(uid):
    if uid == session["uid"]:
        raise ApiError("You can't remove your own account.")
    execute("DELETE FROM users WHERE id=%s", (uid,))
    return ok(message="Account removed.")


@app.post("/api/admin/cities")
@need("admin")
def add_city():
    name = str(body()["name"]).strip()
    if len(name) < 2:
        raise ApiError("Enter a city name.")
    execute("INSERT INTO cities (name) VALUES (%s)", (name,))
    return ok(message="City added.")


@app.delete("/api/admin/cities/<int:cid>")
@need("admin")
def del_city(cid):
    execute("DELETE FROM cities WHERE id=%s", (cid,))
    return ok(message="City removed.")


@app.post("/api/admin/routes")
@need("admin")
def add_route():
    d = body()
    a, b, km = int(d["city_a"]), int(d["city_b"]), int(d["distance_km"])
    if a == b or km <= 0:
        raise ApiError("Choose two different cities and a distance above 0.")
    a, b = min(a, b), max(a, b)
    execute("INSERT INTO routes (city_a,city_b,distance_km) VALUES (%s,%s,%s)", (a, b, km))
    return ok(message="Route added.")


@app.delete("/api/admin/routes/<int:rid>")
@need("admin")
def del_route(rid):
    execute("DELETE FROM routes WHERE id=%s", (rid,))
    return ok(message="Route removed.")


@app.get("/api/admin/buses")
@need("admin")
def buses():
    return ok(query("""SELECT b.id,b.reg_no,b.name,b.total_seats,b.rate_per_km,b.manager_id,u.name manager
        FROM buses b LEFT JOIN users u ON u.id=b.manager_id ORDER BY b.name"""))


@app.post("/api/admin/buses")
@need("admin")
def add_bus():
    d = body()
    seats, rate = int(d["total_seats"]), float(d["rate_per_km"])
    if seats < 8 or seats > 60 or seats % 4 or rate <= 0:
        raise ApiError("Seats must be a multiple of 4 (8 to 60) and the rate above 0.")
    execute("INSERT INTO buses (reg_no,name,total_seats,rate_per_km,manager_id) VALUES (%s,%s,%s,%s,%s)",
            (str(d["reg_no"]).strip().upper(), str(d["name"]).strip(), seats, rate, d.get("manager_id") or None))
    return ok(message="Bus added.")


@app.post("/api/admin/buses/<int:bid>/manager")
@need("admin")
def assign_bus(bid):
    mid = body().get("manager_id") or None
    execute("UPDATE buses SET manager_id=%s WHERE id=%s", (mid, bid))
    return ok(message="Bus manager updated.")


@app.delete("/api/admin/buses/<int:bid>")
@need("admin")
def del_bus(bid):
    execute("DELETE FROM buses WHERE id=%s", (bid,))
    return ok(message="Bus removed.")


@app.get("/api/admin/bookings")
@need("admin")
def all_bookings():
    return ok(with_flags(query(BOOKING_SQL + " ORDER BY b.id DESC LIMIT 300")))


if __name__ == "__main__":
    app.run(debug=True, port=5000)