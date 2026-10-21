"""SQLite storage. Money is always integer cents (USD)."""
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS funds (
    code         TEXT PRIMARY KEY,          -- goes into PayPal purchase_units.custom_id
    name         TEXT NOT NULL,
    donor_words  TEXT NOT NULL,             -- the limits as a donor wrote them
    rules_json   TEXT NOT NULL              -- [{kind, value}] extracted from donor_words
);

CREATE TABLE IF NOT EXISTS partners (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    paypal_email     TEXT NOT NULL,
    region           TEXT NOT NULL,
    month_cap_cents  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gifts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code          TEXT NOT NULL REFERENCES funds(code),
    donor_name         TEXT NOT NULL,
    amount_cents       INTEGER NOT NULL CHECK (amount_cents > 0),
    status             TEXT NOT NULL CHECK (status IN ('created', 'captured')),
    source             TEXT NOT NULL DEFAULT 'paypal' CHECK (source IN ('paypal', 'seed')),
    paypal_order_id    TEXT UNIQUE,
    paypal_capture_id  TEXT UNIQUE,
    created_at         TEXT NOT NULL,
    captured_at        TEXT
);

CREATE TABLE IF NOT EXISTS requests (
    id            TEXT PRIMARY KEY,         -- e.g. KT-0142; also the PayPal payout sender_item_id
    fund_code     TEXT NOT NULL REFERENCES funds(code),
    partner_id    TEXT NOT NULL REFERENCES partners(id),
    purpose       TEXT NOT NULL,
    shop_json     TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('reviewed', 'paying', 'paid', 'returned')),
    submitted_at  TEXT NOT NULL,
    approved_by   TEXT,
    approved_at   TEXT
);

CREATE TABLE IF NOT EXISTS request_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    TEXT NOT NULL REFERENCES requests(id),
    item_key      TEXT NOT NULL,
    receipt_text  TEXT NOT NULL,
    label         TEXT NOT NULL,
    qty           INTEGER NOT NULL,
    unit_cents    INTEGER NOT NULL,
    verdict       TEXT NOT NULL CHECK (verdict IN ('fits', 'blocked')),
    reason        TEXT NOT NULL
);

-- Which gift paid for which request. Oldest gifts are spent first (FIFO).
CREATE TABLE IF NOT EXISTS allocations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    gift_id       INTEGER NOT NULL REFERENCES gifts(id),
    request_id    TEXT NOT NULL REFERENCES requests(id),
    amount_cents  INTEGER NOT NULL CHECK (amount_cents > 0)
);

CREATE TABLE IF NOT EXISTS payouts (
    request_id       TEXT PRIMARY KEY REFERENCES requests(id),
    sender_batch_id  TEXT NOT NULL UNIQUE,  -- our idempotency key at PayPal
    payout_batch_id  TEXT,
    transaction_id   TEXT,
    amount_cents     INTEGER NOT NULL,
    fee_cents        INTEGER,
    status           TEXT NOT NULL,         -- PayPal batch status: PENDING, PROCESSING, SUCCESS, ...
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id           TEXT PRIMARY KEY,          -- PayPal event id, so redeliveries are ignored
    event_type   TEXT NOT NULL,
    resource_id  TEXT,
    verified     INTEGER NOT NULL,
    payload      TEXT NOT NULL,
    received_at  TEXT NOT NULL
);
"""


def connect(path: str, init: bool = True) -> sqlite3.Connection:
    # Autocommit mode; multi-statement writes go through transaction() below.
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if init:
        if path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE takes the write lock up front, so two approvals can't race."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_cents(value: str | float) -> int:
    return int(round(float(value) * 100))


def to_usd(cents: int) -> str:
    return f"{cents / 100:.2f}"
