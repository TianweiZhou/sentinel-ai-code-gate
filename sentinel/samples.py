'''Built-in demo scenarios. Each has a spec, human-owned acceptance tests, a flawed
"AI first draft" and a recorded repair, so the demo works offline (replay mode).'''

from __future__ import annotations

from sentinel.models import Sample

SIGNUP = Sample(
    id="signup",
    title="User sign-up service",
    tagline="SQL injection, MD5 passwords and two silently skipped requirements",
    spec='''Build a small user-registration module on SQLite.

`init_db(conn)` creates the users table.
`register_user(conn, username, password) -> int` registers a user.
`verify_password(conn, username, password) -> bool` checks a login.

R1: Usernames must be 3-20 characters of ASCII letters, digits or underscore; otherwise raise ValueError.
R2: Passwords must be at least 12 characters and contain a letter and a digit; otherwise raise ValueError.
R3: Never store the plain password - store a salted, slow hash (PBKDF2 or scrypt) with a per-user salt.
R4: Registering an existing username raises ValueError (usernames are case-insensitive).
R5: Return the new user's integer id.
R6: verify_password returns True only for the correct password, and False for unknown users.
''',
    tests='''import hashlib
import sqlite3

import pytest

from solution import init_db, register_user, verify_password

GOOD = "correct horse 9 battery"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    yield c
    c.close()


@pytest.mark.req("R1")
@pytest.mark.parametrize("name", ["ab", "a" * 21, "bob smith", "x'); DROP TABLE users;--", "émile"])
def test_rejects_invalid_usernames(conn, name):
    with pytest.raises(ValueError):
        register_user(conn, name, GOOD)


@pytest.mark.req("R1")
@pytest.mark.parametrize("name", ["abc", "a" * 20, "Dev_42"])
def test_accepts_valid_usernames(conn, name):
    assert register_user(conn, name, GOOD) > 0


@pytest.mark.req("R2")
@pytest.mark.parametrize("pw", ["short1a", "onlyletterslong", "123456789012", "a1a1a1a1a1x"])
def test_rejects_weak_passwords(conn, pw):
    with pytest.raises(ValueError):
        register_user(conn, "alice", pw)


@pytest.mark.req("R2")
def test_accepts_exactly_twelve_characters(conn):
    assert register_user(conn, "alice", "abcdefghij12") > 0


@pytest.mark.req("R3")
def test_password_is_never_stored_in_plain_text(conn):
    register_user(conn, "alice", GOOD)
    row = conn.execute("SELECT * FROM users").fetchone()
    stored = b"|".join(v if isinstance(v, bytes) else str(v).encode() for v in row)
    assert GOOD.encode() not in stored
    assert hashlib.md5(GOOD.encode()).hexdigest().encode() not in stored
    assert hashlib.sha256(GOOD.encode()).hexdigest().encode() not in stored


@pytest.mark.req("R3")
def test_same_password_gets_different_hashes(conn):
    register_user(conn, "alice", GOOD)
    register_user(conn, "bob_1", GOOD)
    cur = conn.execute("SELECT * FROM users ORDER BY id")
    secret = [i for i, d in enumerate(cur.description) if d[0] not in ("id", "username")]
    a, b = cur.fetchall()
    assert [a[i] for i in secret] != [b[i] for i in secret]


@pytest.mark.req("R4")
def test_duplicate_username_is_rejected_case_insensitively(conn):
    register_user(conn, "alice", GOOD)
    with pytest.raises(ValueError):
        register_user(conn, "Alice", GOOD)


@pytest.mark.req("R5")
def test_returns_increasing_integer_ids(conn):
    first = register_user(conn, "alice", GOOD)
    second = register_user(conn, "bob_1", GOOD)
    assert isinstance(first, int)
    assert second == first + 1


@pytest.mark.req("R6")
def test_verify_password(conn):
    register_user(conn, "alice", GOOD)
    assert verify_password(conn, "alice", GOOD) is True
    assert verify_password(conn, "alice", GOOD + "x") is False
    assert verify_password(conn, "nobody", GOOD) is False
''',
    generated='''import sqlite3
import hashlib


def init_db(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, salt TEXT)")


def register_user(conn, username, password):
    if len(username) < 3 or len(username) > 20:
        raise ValueError("bad username")
    existing = conn.execute(f"SELECT id FROM users WHERE username = '{username}'").fetchone()
    if existing:
        raise ValueError("user exists")
    hashed = hashlib.md5(password.encode()).hexdigest()
    cur = conn.execute(f"INSERT INTO users (username, password, salt) VALUES ('{username}', '{hashed}', '')")
    conn.commit()
    return cur.lastrowid


def verify_password(conn, username, password):
    row = conn.execute(f"SELECT password FROM users WHERE username = '{username}'").fetchone()
    if row == None:
        return False
    return row[0] == hashlib.md5(password.encode()).hexdigest()
''',
    repaired='''"""User registration backed by SQLite."""

import hashlib
import hmac
import re
import secrets
import sqlite3

_USERNAME = re.compile(r"[A-Za-z0-9_]{3,20}")
_ITERATIONS = 210_000  # OWASP guidance for PBKDF2-HMAC-SHA256 is 600k; lowered for demo speed


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE, password_hash BLOB, salt BLOB)"
    )


def _validate(username: str, password: str) -> None:
    if not _USERNAME.fullmatch(username):
        raise ValueError("username must be 3-20 letters, digits or underscores")
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if len(password) < 12 or not (has_letter and has_digit):
        raise ValueError("password must be 12+ characters with a letter and a digit")


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)


def register_user(conn: sqlite3.Connection, username: str, password: str) -> int:
    _validate(username, password)
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        raise ValueError("username already taken")
    salt = secrets.token_bytes(16)
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
        (username, _hash(password, salt), salt),
    )
    conn.commit()
    user_id = cur.lastrowid
    if user_id is None:
        raise RuntimeError("insert did not return an id")
    return user_id


def verify_password(conn: sqlite3.Connection, username: str, password: str) -> bool:
    row = conn.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        return False
    return hmac.compare_digest(row[0], _hash(password, row[1]))
''',
)

RATE_LIMITER = Sample(
    id="rate-limiter",
    title="Token-bucket rate limiter",
    tagline="Off-by-one, unbounded refill and no input validation",
    spec='''Build `TokenBucket(capacity, refill_per_second, clock=time.monotonic)` for API rate limiting.
`clock` is injectable so the bucket can be tested without sleeping.

R1: A new bucket starts full; `allow()` returns True and consumes one token while tokens remain.
R2: When there are not enough tokens, `allow()` returns False and consumes nothing.
R3: Tokens refill continuously at `refill_per_second` and never exceed `capacity`; `tokens` exposes the current level.
R4: `capacity` must be >= 1 and `refill_per_second` > 0, otherwise raise ValueError.
R5: `allow(cost)` takes a token cost (default 1); a request costing more than the available tokens is rejected.
''',
    tests='''import pytest

from solution import TokenBucket


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.mark.req("R1")
def test_starts_full_and_allows_up_to_capacity(clock):
    bucket = TokenBucket(3, 1, clock=clock)
    assert [bucket.allow() for _ in range(3)] == [True, True, True]


@pytest.mark.req("R2")
def test_rejects_when_empty_without_consuming(clock):
    bucket = TokenBucket(2, 1, clock=clock)
    bucket.allow()
    bucket.allow()
    assert bucket.allow() is False
    assert bucket.tokens == 0


@pytest.mark.req("R3")
def test_refills_at_configured_rate(clock):
    bucket = TokenBucket(3, 2, clock=clock)
    for _ in range(3):
        bucket.allow()
    clock.now += 0.5
    assert bucket.tokens == pytest.approx(1.0)
    assert bucket.allow() is True
    assert bucket.allow() is False


@pytest.mark.req("R3")
def test_never_refills_above_capacity(clock):
    bucket = TokenBucket(3, 2, clock=clock)
    clock.now += 3600
    assert bucket.tokens == 3
    assert [bucket.allow() for _ in range(4)] == [True, True, True, False]


@pytest.mark.req("R4")
@pytest.mark.parametrize("capacity, rate", [(0, 1), (-1, 1), (1, 0), (1, -0.5)])
def test_rejects_invalid_configuration(capacity, rate):
    with pytest.raises(ValueError):
        TokenBucket(capacity, rate)


@pytest.mark.req("R4")
def test_accepts_smallest_valid_configuration(clock):
    assert TokenBucket(1, 0.1, clock=clock).allow() is True


@pytest.mark.req("R5")
def test_cost_is_consumed_and_checked(clock):
    bucket = TokenBucket(5, 1, clock=clock)
    assert bucket.allow(3) is True
    assert bucket.allow(3) is False
    assert bucket.tokens == 2
    assert bucket.allow(2) is True
''',
    generated='''import time


class TokenBucket:
    def __init__(self, capacity, refill_per_second, clock=time.time):
        self.capacity = capacity
        self.rate = refill_per_second
        self.tokens = capacity
        self.clock = clock
        self.last = clock()

    def allow(self, cost=1):
        now = self.clock()
        self.tokens = self.tokens + (now - self.last) * self.rate
        self.last = now
        if self.tokens > cost:
            self.tokens -= cost
            return True
        return False
''',
    repaired='''"""Token-bucket rate limiter."""

import time
from collections.abc import Callable


class TokenBucket:
    """Allows bursts of up to `capacity` requests, refilling at a steady rate."""

    def __init__(self, capacity: int, refill_per_second: float, clock: Callable[[], float] = time.monotonic) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        self._capacity = capacity
        self._rate = refill_per_second
        self._tokens = float(capacity)
        self._clock = clock
        self._last = clock()

    @property
    def tokens(self) -> float:
        self._refill()
        return self._tokens

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(float(self._capacity), self._tokens + (now - self._last) * self._rate)
        self._last = now

    def allow(self, cost: int = 1) -> bool:
        self._refill()
        if cost <= self._tokens:
            self._tokens -= cost
            return True
        return False
''',
)

SALES_REPORT = Sample(
    id="sales-report",
    title="CSV sales report",
    tagline="Hallucinated API, eval() on input, and a requirement nobody tested",
    spec='''Build `summarize_sales(csv_text) -> dict` for CSV text with the header `region,product,quantity,unit_price`.
The result has the keys `total`, `by_region`, `top_product` and `skipped`.

R1: `total` is the sum of quantity x unit_price over valid rows, rounded to 2 decimals.
R2: `by_region` maps each region to its revenue, rounded to 2 decimals.
R3: Rows with a missing field or a non-numeric quantity/price are skipped and counted in `skipped`.
R4: `top_product` is the product with the highest revenue, or None when there are no valid rows.
R5: Negative quantities are refunds and must reduce revenue, but are rejected if larger than the units sold so far.
''',
    tests='''import pytest

from solution import summarize_sales

CSV = """region,product,quantity,unit_price
north,widget,2,9.99
south,widget,1,9.99
north,gadget,3,0.10
east,doohickey,1,0.333
south,,1,5.00
west,gizmo,abc,1.00
west,gizmo,__import__('os').getcwd(),1.00
east,gizmo,1
"""


@pytest.fixture
def summary():
    return summarize_sales(CSV)


@pytest.mark.req("R1")
def test_total_revenue(summary):
    assert summary["total"] == 30.6


@pytest.mark.req("R2")
def test_revenue_by_region(summary):
    assert summary["by_region"] == {"north": 20.28, "south": 9.99, "east": 0.33}


@pytest.mark.req("R3")
def test_malformed_rows_are_skipped_and_counted(summary):
    assert summary["skipped"] == 4


@pytest.mark.req("R4")
def test_top_product(summary):
    assert summary["top_product"] == "widget"


@pytest.mark.req("R4")
def test_no_valid_rows():
    result = summarize_sales("region,product,quantity,unit_price\\n")
    assert result == {"total": 0, "by_region": {}, "top_product": None, "skipped": 0}

# Note: no test is marked R5. The gate will refuse to pass until a human writes one.
''',
    generated='''import csv
import io
from statistics import weighted_mean


def summarize_sales(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    total = 0
    by_region = {}
    by_product = {}
    skipped = 0
    for row in reader:
        if row["region"] and row["product"]:
            if row["quantity"] and row["unit_price"]:
                try:
                    qty = eval(row["quantity"])
                    price = eval(row["unit_price"])
                    revenue = qty * price
                    total += revenue
                    if row["region"] in by_region:
                        by_region[row["region"]] += revenue
                    else:
                        by_region[row["region"]] = revenue
                    if row["product"] in by_product:
                        by_product[row["product"]] += revenue
                    else:
                        by_product[row["product"]] = revenue
                except Exception:
                    skipped += 1
            else:
                skipped += 1
        else:
            skipped += 1
    top = None
    best = 0
    for p in by_product:
        if by_product[p] > best:
            best = by_product[p]
            top = p
    return {"total": round(total, 2), "by_region": by_region, "top_product": top, "skipped": skipped}
''',
    repaired='''"""Sales CSV summary."""

import csv
import io
from collections import defaultdict
from collections.abc import Mapping
from typing import TypedDict


class Summary(TypedDict):
    total: float
    by_region: dict[str, float]
    top_product: str | None
    skipped: int


def _parse_row(row: Mapping[str, str | None]) -> tuple[str, str, float] | None:
    region, product = row.get("region"), row.get("product")
    try:
        quantity = float(row.get("quantity") or "")
        price = float(row.get("unit_price") or "")
    except ValueError:
        return None
    if not region or not product:
        return None
    return region, product, quantity * price


def summarize_sales(csv_text: str) -> Summary:
    by_region: defaultdict[str, float] = defaultdict(float)
    by_product: defaultdict[str, float] = defaultdict(float)
    skipped = 0
    for row in csv.DictReader(io.StringIO(csv_text)):
        parsed = _parse_row(row)
        if parsed is None:
            skipped += 1
            continue
        region, product, revenue = parsed
        by_region[region] += revenue
        by_product[product] += revenue
    return {
        "total": round(sum(by_region.values()), 2),
        "by_region": {region: round(value, 2) for region, value in by_region.items()},
        "top_product": max(by_product, key=by_product.__getitem__) if by_product else None,
        "skipped": skipped,
    }
''',
)

SAMPLES: dict[str, Sample] = {s.id: s for s in (SIGNUP, RATE_LIMITER, SALES_REPORT)}
