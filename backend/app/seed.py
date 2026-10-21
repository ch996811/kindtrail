"""Demo data: one fund, one field partner, one reviewed request (KT-0142).

The AI review results on the request are fixed here until the review agent lands (week 2).
Gifts normally come from real sandbox checkouts; `demo_gifts=True` adds three made-up ones
(source='seed') so the UI has something to show. Reconciliation flags those as ours-only.
"""
import json
import sqlite3

from .db import transaction

FUND = {
    "code": "FUND-HUALIEN-KIDS",
    "name": "Hualien Kids Typhoon Fund",
    "donor_words": "Please use my gift only for kids in Hualien who lost their homes in the typhoon. Not for staff costs.",
    "rules": [
        {"kind": "Where", "value": "Hualien County"},
        {"kind": "For", "value": "shelter, food, kids' supplies"},
        {"kind": "Who", "value": "families with children"},
        {"kind": "Never", "value": "staff, cash equivalents"},
        {"kind": "Until", "value": "Dec 31"},
    ],
}

ITEMS = [
    ("tarp", "Waterproof tarp 3x4m", "4 waterproof tarps", 4, 800, "fits", "Shelter, an allowed use"),
    ("rice", "Rice 10 kg", "2 bags of rice, 10 kg", 2, 1200, "fits", "Food, an allowed use"),
    ("coat", "Kids raincoat", "6 kids' raincoats", 6, 360, "fits", "For children, exactly who the fund serves"),
    ("card", "Prepaid gift card", "1 prepaid gift card", 1, 880, "blocked",
     "Cash equivalents break the donors' limits. The partner can pay this from general funds."),
]

DEMO_GIFTS = [("Mei L.", 5000, "2026-10-21T09:12:00Z"), ("Jordan P.", 2000, "2026-10-22T14:40:00Z"),
              ("Anonymous", 2500, "2026-10-23T08:05:00Z")]


def seed(conn: sqlite3.Connection, partner_email: str, demo_gifts: bool = False) -> None:
    with transaction(conn):
        conn.execute("INSERT OR IGNORE INTO funds (code, name, donor_words, rules_json) VALUES (?, ?, ?, ?)",
                     (FUND["code"], FUND["name"], FUND["donor_words"], json.dumps(FUND["rules"])))
        conn.execute("INSERT OR IGNORE INTO partners (id, name, paypal_email, region, month_cap_cents) VALUES (?, ?, ?, ?, ?)",
                     ("hualien-mountain-kitchen", "Hualien Mountain Kitchen", partner_email or "partner@example.com",
                      "Hualien County", 200000))
        new = conn.execute(
            "INSERT OR IGNORE INTO requests (id, fund_code, partner_id, purpose, shop_json, status, submitted_at) "
            "VALUES (?, ?, ?, ?, ?, 'reviewed', ?)",
            ("KT-0142", FUND["code"], "hualien-mountain-kitchen", "typhoon families",
             json.dumps({"name": "HUALIEN HOME MART", "branch": "Ji'an branch", "printed_at": "2026-10-24 14:32",
                         "region": "Hualien County"}), "2026-10-24T06:40:00Z"),
        ).rowcount
        if new:
            conn.executemany(
                "INSERT INTO request_items (request_id, item_key, receipt_text, label, qty, unit_cents, verdict, reason) "
                "VALUES ('KT-0142', ?, ?, ?, ?, ?, ?, ?)", ITEMS)
        if demo_gifts and not conn.execute("SELECT 1 FROM gifts WHERE source = 'seed'").fetchone():
            conn.executemany(
                "INSERT INTO gifts (fund_code, donor_name, amount_cents, status, source, created_at, captured_at) "
                "VALUES (?, ?, ?, 'captured', 'seed', ?, ?)",
                [(FUND["code"], name, cents, at, at) for name, cents, at in DEMO_GIFTS])


def reset_request(conn: sqlite3.Connection, request_id: str = "KT-0142") -> None:
    """Put a request back to 'reviewed' so the demo can be run again. Sandbox money already sent stays sent."""
    with transaction(conn):
        conn.execute("DELETE FROM allocations WHERE request_id = ?", (request_id,))
        conn.execute("DELETE FROM payouts WHERE request_id = ?", (request_id,))
        conn.execute("UPDATE requests SET status = 'reviewed', approved_by = NULL, approved_at = NULL WHERE id = ?",
                     (request_id,))
