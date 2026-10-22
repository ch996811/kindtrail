"""The ledger: which gift paid for what, and does it agree with PayPal?

Gifts in a fund are spent oldest first (FIFO), so every payout cent traces back to a donor.
"""
import sqlite3
from dataclasses import dataclass
from typing import Any


class InsufficientFunds(Exception):
    def __init__(self, available_cents: int, needed_cents: int):
        self.available_cents = available_cents
        self.needed_cents = needed_cents
        super().__init__(f"fund has {available_cents} cents available, request needs {needed_cents}")


@dataclass(frozen=True)
class GiftBalance:
    gift_id: int
    donor_name: str
    amount_cents: int
    used_cents: int
    captured_at: str

    @property
    def remaining_cents(self) -> int:
        return self.amount_cents - self.used_cents


def gift_balances(conn: sqlite3.Connection, fund_code: str) -> list[GiftBalance]:
    rows = conn.execute(
        """
        SELECT g.id, g.donor_name, g.amount_cents, g.captured_at,
               COALESCE((SELECT SUM(a.amount_cents) FROM allocations a WHERE a.gift_id = g.id), 0) AS used
        FROM gifts g
        WHERE g.fund_code = ? AND g.status = 'captured'
        ORDER BY g.captured_at, g.id
        """,
        (fund_code,),
    ).fetchall()
    return [GiftBalance(r["id"], r["donor_name"], r["amount_cents"], r["used"], r["captured_at"]) for r in rows]


def plan_fifo(balances: list[GiftBalance], amount_cents: int) -> list[tuple[GiftBalance, int]]:
    """Split amount_cents across gifts, oldest first. Raises InsufficientFunds if they can't cover it."""
    if amount_cents <= 0:
        return []
    plan: list[tuple[GiftBalance, int]] = []
    left = amount_cents
    for b in balances:
        if left == 0:
            break
        take = min(b.remaining_cents, left)
        if take > 0:
            plan.append((b, take))
            left -= take
    if left > 0:
        raise InsufficientFunds(sum(b.remaining_cents for b in balances), amount_cents)
    return plan


def item_total_cents(item: sqlite3.Row | dict[str, Any]) -> int:
    return int(item["qty"]) * int(item["unit_cents"])


def request_amounts(items: list[sqlite3.Row]) -> tuple[int, int]:
    """(requested, payable): payable only counts lines the review says fit the fund."""
    requested = sum(item_total_cents(i) for i in items)
    payable = sum(item_total_cents(i) for i in items if i["verdict"] == "fits")
    return requested, payable


def split_by_item(allocations: list[tuple[int, int]], items: list[tuple[str, int]]) -> list[tuple[int, str, int]]:
    """Which gift paid for which line, walking both in order (gifts oldest first, lines as printed).

    allocations: [(gift_id, cents)] for one request; items: [(item_key, cents)] of the lines that fit.
    Returns [(gift_id, item_key, cents)] segments. Totals must match; that's what approval guarantees.
    """
    segments: list[tuple[int, str, int]] = []
    queue = [[key, cents] for key, cents in items if cents > 0]
    i = 0
    for gift_id, cents in allocations:
        left = cents
        while left > 0 and i < len(queue):
            take = min(left, queue[i][1])
            segments.append((gift_id, queue[i][0], take))
            left -= take
            queue[i][1] -= take
            if queue[i][1] == 0:
                i += 1
    return segments


# Reconciliation ----------------------------------------------------------------------------

def reconcile(gifts: list[dict[str, Any]], payouts: list[dict[str, Any]],
              paypal_txns: list[dict[str, Any]]) -> dict[str, Any]:
    """Match our ledger against PayPal Transaction Search by transaction id.

    gifts:   [{gift_id, capture_id, amount_cents, fund_code, source}]
    payouts: [{request_id, transaction_id, amount_cents}]
    Amounts from PayPal are signed: captures positive, payouts negative.
    """
    by_id = {t.get("transaction_id"): t for t in paypal_txns if t.get("transaction_id")}
    seen: set[str] = set()
    matched, mismatched, ours_only = [], [], []

    def check(kind: str, ref: str, txn_id: str | None, expected_cents: int, extra: dict[str, Any]) -> None:
        row = {"kind": kind, "ref": ref, "transaction_id": txn_id, "ours_cents": expected_cents, **extra}
        txn = by_id.get(txn_id) if txn_id else None
        if txn is None:
            ours_only.append(row)
            return
        seen.add(txn_id)
        theirs = round(float(txn["transaction_amount"]["value"]) * 100)
        row["paypal_cents"] = theirs
        row["paypal_status"] = txn.get("transaction_status")
        (matched if theirs == expected_cents else mismatched).append(row)

    for g in gifts:
        check("gift", f"gift-{g['gift_id']}", g.get("capture_id"), g["amount_cents"],
              {"fund_code": g.get("fund_code"), "source": g.get("source", "paypal")})
    for p in payouts:
        check("payout", p["request_id"], p.get("transaction_id"), -p["amount_cents"], {})

    paypal_only = [
        {"transaction_id": t["transaction_id"], "event_code": t.get("transaction_event_code"),
         "paypal_cents": round(float(t["transaction_amount"]["value"]) * 100),
         "custom_field": t.get("custom_field"), "paypal_status": t.get("transaction_status")}
        for tid, t in by_id.items() if tid not in seen
    ]
    return {
        "matched": matched,
        "mismatched": mismatched,
        "ours_only": ours_only,
        "paypal_only": paypal_only,
        "balanced": not mismatched and not ours_only,
    }
