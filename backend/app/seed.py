"""Demo data: one fund, one field partner, one reviewed request (KT-0142).

The fund's limits and KT-0142's review come from the real AI pipeline. backend/demo/llm_cache.json
holds those model answers, so this works with no API key (and costs no quota). If an answer is
missing, the fixed fallback below keeps the demo usable.

Gifts normally come from real sandbox checkouts; `demo_gifts=True` adds three made-up ones
(source='seed') so the UI has something to show. Reconciliation flags those as ours-only.
"""
import json
import sqlite3
from pathlib import Path

from . import service
from .db import now_iso, transaction
from .llm import LLM, AIUnavailable

DEMO_DIR = Path(__file__).resolve().parents[1] / "demo"

FUND_CODE = "FUND-HUALIEN-KIDS"
FUND_NAME = "Hualien Kids Typhoon Fund"
FUND_CREATED = "2026-10-08"  # anchors "by the end of the year" in the donor's words
DONOR_WORDS = ("Please use my gift only for kids in Hualien who lost their homes in the typhoon. "
               "Not for staff costs. Spend it by the end of the year.")
FALLBACK_POLICY = {"region": "Hualien County", "allowed": ["shelter", "food", "water", "children_supplies"],
                   "never": ["staff_cost"], "beneficiaries": "kids who lost their homes", "until": "2026-12-31"}

PARTNER_ID = "hualien-mountain-kitchen"
DEMO_REQUEST = {"id": "KT-0142", "receipt": "hualien-home-mart.jpg", "purpose": "typhoon families",
                "submitted_at": "2026-10-14T06:40:00Z"}

DEMO_GIFTS = [("Mei L.", 5000, "2026-10-10T09:12:00Z"), ("Jordan P.", 2000, "2026-10-11T14:40:00Z"),
              ("Anonymous", 2500, "2026-10-12T08:05:00Z")]


def load_demo_cache(conn: sqlite3.Connection) -> int:
    path = DEMO_DIR / "llm_cache.json"
    if not path.exists():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    conn.executemany("INSERT OR IGNORE INTO llm_cache (key, task, model, response, created_at) VALUES (?, ?, ?, ?, ?)",
                     [(r["key"], r["task"], r["model"], json.dumps(r["response"]), now_iso()) for r in rows])
    return len(rows)


def seed(conn: sqlite3.Connection, partner_email: str, llm: LLM | None = None, demo_gifts: bool = False) -> None:
    if llm is not None:
        load_demo_cache(conn)

    fund = conn.execute("SELECT policy_json FROM funds WHERE code = ?", (FUND_CODE,)).fetchone()
    if fund is None or not fund["policy_json"]:
        policy = FALLBACK_POLICY
        if llm is not None:
            try:
                policy = service.parse_limits(conn, llm, DONOR_WORDS, today=FUND_CREATED)["policy"]
            except AIUnavailable:
                pass
        with transaction(conn):
            conn.execute("INSERT OR IGNORE INTO funds (code, name, donor_words, rules_json) VALUES (?, ?, ?, '[]')",
                         (FUND_CODE, FUND_NAME, DONOR_WORDS))
            conn.execute("UPDATE funds SET policy_json = ?, donor_words = ? WHERE code = ?",
                         (json.dumps(policy), DONOR_WORDS, FUND_CODE))

    conn.execute("INSERT OR IGNORE INTO partners (id, name, paypal_email, region, month_cap_cents) VALUES (?, ?, ?, ?, ?)",
                 (PARTNER_ID, "Hualien Mountain Kitchen", partner_email or "partner@example.com", "Hualien County", 200000))

    if llm is not None and not conn.execute("SELECT 1 FROM requests WHERE id = ?", (DEMO_REQUEST["id"],)).fetchone():
        try:
            service.create_request(conn, llm, fund_code=FUND_CODE, partner_id=PARTNER_ID,
                                   purpose=DEMO_REQUEST["purpose"], image=(DEMO_DIR / "receipts" / DEMO_REQUEST["receipt"]).read_bytes(),
                                   mime="image/jpeg", request_id=DEMO_REQUEST["id"],
                                   submitted_at=DEMO_REQUEST["submitted_at"])
        except AIUnavailable:
            pass  # no cached answer and no key: the demo starts without KT-0142

    if demo_gifts and not conn.execute("SELECT 1 FROM gifts WHERE source = 'seed'").fetchone():
        conn.executemany(
            "INSERT INTO gifts (fund_code, donor_name, amount_cents, status, source, created_at, captured_at) "
            "VALUES (?, ?, ?, 'captured', 'seed', ?, ?)",
            [(FUND_CODE, name, cents, at, at) for name, cents, at in DEMO_GIFTS])


def reset_request(conn: sqlite3.Connection, request_id: str = "KT-0142") -> None:
    """Put a request back to 'reviewed' so the demo can be run again. Sandbox money already sent stays sent."""
    with transaction(conn):
        conn.execute("DELETE FROM allocations WHERE request_id = ?", (request_id,))
        conn.execute("DELETE FROM payouts WHERE request_id = ?", (request_id,))
        conn.execute("UPDATE requests SET status = 'reviewed', approved_by = NULL, approved_at = NULL WHERE id = ?",
                     (request_id,))
