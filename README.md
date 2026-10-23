# Wayfare - Travel Bus Booking Management System

Python (Flask) backend, MySQL database, HTML/CSS/JavaScript frontend.
Three sign-in roles: **Admin**, **Customer**, **Bus manager**.

## Run it (Windows, VS Code)

1. Install MySQL Server and make sure it is running.
2. Open `backend/config.py` and set your MySQL `password` (or set the `DB_PASSWORD` environment variable).
3. In a terminal:

```
cd bus_booking\backend
pip install -r requirements.txt
python setup_db.py
python app.py
```

4. Open http://localhost:5000 in your browser.

`setup_db.py` creates the `busbook` database, the tables and demo data. Running it again resets everything.

## Demo accounts

| Role | Username | Password |
|---|---|---|
| Admin | admin | admin123 |
| Bus manager | manager (or manager2) | manager123 |
| Customer | customer | customer123 |

Customers can also create their own account from the sign-in page.

## What each role can do

- **Customer**: search trips (direct and with a change of bus), sort by time or fare, book 1-6 seats (best seat
  automatically or pick on the seat map), see an itemised fare, join the waitlist on a full bus, cancel tickets
  with a refund, undo the last booking, find a ticket by PNR, print tickets.
- **Bus manager**: add trips for their buses, see occupancy / waitlist / revenue per trip, view the passenger list,
  fill free seats from the waitlist (by arrival order or best revenue), cancel a trip (full refunds), find tickets.
- **Admin**: everything a manager can do for all buses, plus overview statistics, cities and routes,
  buses and their managers, user accounts, and every booking.

## Module map (for your viva - this lives only in the backend, nothing is shown in the UI)

| Module | Where in code | Used for |
|---|---|---|
| 1 Linked List | `ds.LinkedList` | Passenger manifest per trip (`/details`) |
| 2 Stack / Queue | `ds.Stack`, `ds.Queue` | Stack: undo last booking (`/api/undo`). Queue: waitlist, served first-come first-served (`promote`) |
| 3 BST | `ds.BST` | Trips keyed by `from\|to\|date\|time\|id`: range lookup in search, in-order listing route-wise in the manager/admin trips table |
| 4 Graph + BFS | `ds.Graph.bfs_paths` | Cities = nodes, routes = edges. Finds direct and connecting itineraries (up to 3 legs) |
| 5 Quick Sort + Binary Search | `ds.quick_sort`, `ds.binary_search` | Sort results by departure/fare; find a ticket by PNR in O(log n) |
| 6 Greedy | `ds.greedy_allocate`, `ds.greedy_fill` | Best seat allocation, group seating, revenue-first waitlist fill |
| 7 Stack postfix evaluator | `ds.evaluate_postfix`, `ds.fare_breakdown` | Fare = (rate x km + class surcharge) x 1.05; refund = fare x % / 100 |

## Notes

- Fare classes: Economy +0, Premium +120, Deluxe +250 (edit `CLASS_SURCHARGE` in `ds.py`). Tax is 5%.
- Refund rules: 90% if 24h+ before departure, 60% if 6h+, otherwise 30%. Undo and trip cancellation refund 100%.
- The undo history is kept in memory, so it resets when the server restarts.
- Change `SECRET_KEY` in `config.py` before deploying anywhere public.
