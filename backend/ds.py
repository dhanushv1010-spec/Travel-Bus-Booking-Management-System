"""
Core data structures and algorithms used by the booking system.
Backend only - nothing in this file is exposed to the frontend.

Module 1  Linked List ............ active booking registry / manifests
Module 2  Stack + Queue .......... undo of last booking / waitlist (FIFO)
Module 3  BST .................... trips keyed by route + date + time
Module 4  Graph + BFS ............ city network, reachable & connecting trips
Module 5  Quick Sort + Binary Search ... ranking trips, PNR lookup
Module 6  Greedy ................. seat allocation, fare optimisation, conflict resolution
Module 7  Stack postfix evaluator  fare calculation and refunds
"""
from decimal import Decimal, ROUND_HALF_UP


class _Node:
    __slots__ = ("data", "next")

    def __init__(self, data):
        self.data = data
        self.next = None


# ---------------------------------------------------------------- Module 1
class LinkedList:
    """Singly linked list with head and tail pointers."""

    def __init__(self):
        self.head = self.tail = None
        self.size = 0

    def append(self, data):
        node = _Node(data)
        if self.tail:
            self.tail.next = node
        else:
            self.head = node
        self.tail = node
        self.size += 1

    def remove(self, pred):
        prev, cur = None, self.head
        while cur:
            if pred(cur.data):
                if prev:
                    prev.next = cur.next
                else:
                    self.head = cur.next
                if cur is self.tail:
                    self.tail = prev
                self.size -= 1
                return cur.data
            prev, cur = cur, cur.next
        return None

    def __iter__(self):
        cur = self.head
        while cur:
            yield cur.data
            cur = cur.next

    def __len__(self):
        return self.size


# ---------------------------------------------------------------- Module 2
class Stack:
    """LIFO stack built on linked nodes."""

    def __init__(self):
        self.top = None
        self.size = 0

    def push(self, data):
        node = _Node(data)
        node.next = self.top
        self.top = node
        self.size += 1

    def pop(self):
        if not self.top:
            raise IndexError("stack is empty")
        node = self.top
        self.top = node.next
        self.size -= 1
        return node.data

    def peek(self):
        return self.top.data if self.top else None

    def is_empty(self):
        return self.top is None

    def __len__(self):
        return self.size


class Queue:
    """FIFO queue built on linked nodes."""

    def __init__(self):
        self.head = self.tail = None
        self.size = 0

    def enqueue(self, data):
        node = _Node(data)
        if self.tail:
            self.tail.next = node
        else:
            self.head = node
        self.tail = node
        self.size += 1

    def dequeue(self):
        if not self.head:
            raise IndexError("queue is empty")
        node = self.head
        self.head = node.next
        if not self.head:
            self.tail = None
        self.size -= 1
        return node.data

    def is_empty(self):
        return self.head is None

    def __iter__(self):
        cur = self.head
        while cur:
            yield cur.data
            cur = cur.next

    def __len__(self):
        return self.size


# ---------------------------------------------------------------- Module 3
class _TreeNode:
    __slots__ = ("key", "val", "left", "right")

    def __init__(self, key, val):
        self.key, self.val = key, val
        self.left = self.right = None


class BST:
    """Binary search tree keyed by strings."""

    def __init__(self):
        self.root = None
        self.count = 0

    def insert(self, key, val):
        if not self.root:
            self.root = _TreeNode(key, val)
            self.count += 1
            return
        cur = self.root
        while True:
            if key == cur.key:
                cur.val = val
                return
            side = "left" if key < cur.key else "right"
            nxt = getattr(cur, side)
            if nxt is None:
                setattr(cur, side, _TreeNode(key, val))
                self.count += 1
                return
            cur = nxt

    def search(self, key):
        cur = self.root
        while cur:
            if key == cur.key:
                return cur.val
            cur = cur.left if key < cur.key else cur.right
        return None

    def delete(self, key):
        def _del(node, k):
            if not node:
                return None
            if k < node.key:
                node.left = _del(node.left, k)
            elif k > node.key:
                node.right = _del(node.right, k)
            else:
                if not node.left:
                    return node.right
                if not node.right:
                    return node.left
                succ = node.right
                while succ.left:
                    succ = succ.left
                node.key, node.val = succ.key, succ.val
                node.right = _del(node.right, succ.key)
            return node

        self.root = _del(self.root, key)

    def inorder(self):
        out, stack, cur = [], [], self.root
        while stack or cur:
            while cur:
                stack.append(cur)
                cur = cur.left
            cur = stack.pop()
            out.append((cur.key, cur.val))
            cur = cur.right
        return out

    def preorder(self):
        out, stack = [], [self.root] if self.root else []
        while stack:
            n = stack.pop()
            out.append((n.key, n.val))
            if n.right:
                stack.append(n.right)
            if n.left:
                stack.append(n.left)
        return out

    def postorder(self):
        out = []

        def walk(n):
            if n:
                walk(n.left)
                walk(n.right)
                out.append((n.key, n.val))

        walk(self.root)
        return out

    def prefix(self, p):
        """All entries whose key starts with p, in key order (range query)."""
        out = []

        def walk(n):
            if not n:
                return
            if n.key >= p:
                walk(n.left)
            if n.key.startswith(p):
                out.append((n.key, n.val))
            if n.key < p + "\uffff":
                walk(n.right)

        walk(self.root)
        return out


# ---------------------------------------------------------------- Module 4
class Graph:
    """Undirected weighted graph (adjacency list): cities = nodes, routes = edges."""

    def __init__(self):
        self.adj = {}

    def add_edge(self, a, b, w=1):
        self.adj.setdefault(a, []).append((b, w))
        self.adj.setdefault(b, []).append((a, w))

    def bfs_paths(self, src, dst, max_legs=3):
        """Breadth-first search returning every simple path src -> dst with at
        most max_legs hops, shortest paths first."""
        found, q = [], Queue()
        q.enqueue([src])
        while not q.is_empty():
            path = q.dequeue()
            last = path[-1]
            if last == dst and len(path) > 1:
                found.append(path)
                continue
            if len(path) - 1 >= max_legs:
                continue
            for nb, _ in self.adj.get(last, []):
                if nb not in path:
                    q.enqueue(path + [nb])
        return found

    def reachable(self, src):
        seen, q = {src}, Queue()
        q.enqueue(src)
        while not q.is_empty():
            for nb, _ in self.adj.get(q.dequeue(), []):
                if nb not in seen:
                    seen.add(nb)
                    q.enqueue(nb)
        return seen


# ---------------------------------------------------------------- Module 5
def quick_sort(items, key=lambda x: x):
    a = list(items)

    def part(lo, hi):
        mid = (lo + hi) // 2
        a[mid], a[hi] = a[hi], a[mid]
        pivot, i = key(a[hi]), lo
        for j in range(lo, hi):
            if key(a[j]) < pivot:
                a[i], a[j] = a[j], a[i]
                i += 1
        a[i], a[hi] = a[hi], a[i]
        return i

    def qs(lo, hi):
        while lo < hi:
            p = part(lo, hi)
            if p - lo < hi - p:
                qs(lo, p - 1)
                lo = p + 1
            else:
                qs(p + 1, hi)
                hi = p - 1

    qs(0, len(a) - 1)
    return a


def binary_search(a, target, key=lambda x: x):
    lo, hi = 0, len(a) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        k = key(a[mid])
        if k == target:
            return mid
        if k < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


# ---------------------------------------------------------------- Module 6
SEATS_PER_ROW = 4


def seat_kind(n):
    return "window" if (n - 1) % SEATS_PER_ROW in (0, SEATS_PER_ROW - 1) else "aisle"


def seat_score(n, pref):
    row = (n - 1) // SEATS_PER_ROW
    miss = 0 if pref in ("any", "front") or seat_kind(n) == pref else 1
    return (miss, row, n)


def greedy_allocate(free, k, pref="any"):
    """Best-available seat(s). Free seats are ranked with Quick Sort; one seat
    takes the best-ranked seat. A group takes the tightest block of adjacent
    free seats, or - when no block exists - the free seats nearest to the best
    one (locally best choice each step, earlier choices never revisited)."""
    ranked = quick_sort(free, key=lambda n: seat_score(n, pref))
    if k <= 1:
        return ranked[:1]
    fs, best = set(free), None
    for start in sorted(fs):
        block = list(range(start, start + k))
        if all(n in fs for n in block):
            rows = (block[-1] - 1) // SEATS_PER_ROW - (start - 1) // SEATS_PER_ROW
            cost = (rows, sum(seat_score(n, pref)[0] for n in block), start)
            if best is None or cost < best[0]:
                best = (cost, block)
    if best:
        return best[1]
    anchor = ranked[0]
    rest = quick_sort([n for n in free if n != anchor],
                      key=lambda n: (abs(n - anchor), seat_score(n, pref)))
    return sorted([anchor] + rest[: k - 1])


def greedy_fill(requests, free):
    """Revenue-optimising fill: take requests by best fare per seat first, keep
    every request that still fits in the remaining capacity."""
    ranked = quick_sort(requests, key=lambda r: (-(r["fare"] / r["seats"]), r["id"]))
    chosen = []
    for r in ranked:
        if r["seats"] <= free:
            chosen.append(r)
            free -= r["seats"]
    return chosen


# ---------------------------------------------------------------- Module 7
def evaluate_postfix(tokens):
    st = Stack()
    for t in tokens:
        if t in ("+", "-", "*", "/"):
            b, a = st.pop(), st.pop()
            st.push(a + b if t == "+" else a - b if t == "-" else a * b if t == "*" else a / b)
        else:
            st.push(Decimal(str(t)))
    result = st.pop()
    if not st.is_empty():
        raise ValueError("malformed expression")
    return result


def r2(x):
    return Decimal(x).quantize(Decimal("0.01"), ROUND_HALF_UP)


CLASS_SURCHARGE = {"Economy": 0, "Premium": 120, "Deluxe": 250}
TAX_PERCENT = 5


def fare_breakdown(rate, distance, seat_class):
    """fare = (rate x distance + surcharge) x (100 + tax) / 100, evaluated in postfix."""
    sur = CLASS_SURCHARGE[seat_class]
    base = evaluate_postfix([rate, distance, "*"])
    sub = evaluate_postfix([rate, distance, "*", sur, "+"])
    total = evaluate_postfix([rate, distance, "*", sur, "+", 100 + TAX_PERCENT, "*", 100, "/"])
    return {"distance_charge": r2(base), "class_surcharge": r2(sur), "subtotal": r2(sub),
            "tax": r2(total) - r2(sub), "total": r2(total)}


def refund_pct(hours_before):
    return 90 if hours_before >= 24 else 60 if hours_before >= 6 else 30


def refund_amount(fare, hours_before, full=False):
    pct = 100 if full else refund_pct(hours_before)
    return r2(evaluate_postfix([fare, pct, "*", 100, "/"]))
