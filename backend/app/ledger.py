"""The ledger: which gift paid for what, and does it agree with PayPal?

Gifts in a fund are spent oldest first (FIFO), so every payout cent traces back to a donor.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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

# Transaction Search event codes Kindtrail's sandbox account produces (PayPal's names, checked 2026-11-10).
EVENT_NAMES = {
    "T0001": "Mass payment",                      # a Payouts payment to the partner
    "T0006": "Express Checkout payment",          # a donor's gift through Checkout
    "T1503": "Hold on available balance",         # Payouts holds the amount plus fee first...
    "T1105": "Reversal of general account hold",  # ...and releases the hold when the payment goes out
    "T1900": "General account correction",        # e.g. the sandbox's initial balance
}
STATUS_NAMES = {"S": "completed", "P": "pending", "D": "denied", "V": "reversed"}  # transaction_status codes


def _when(iso: str | None) -> datetime | None:
    """PayPal and the ledger write times as '...Z' or '...+0000'; compare them as datetimes."""
    if not iso:
        return None
    iso = iso.strip().replace("Z", "+00:00")
    if len(iso) > 5 and iso[-5] in "+-" and iso[-3] != ":":
        iso = iso[:-2] + ":" + iso[-2:]
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _cents(money: dict[str, Any] | None) -> int:
    return round(float(money["value"]) * 100) if money and money.get("value") not in (None, "") else 0


def _groups(txns: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group PayPal's rows by the payment they belong to. A payout shows up as three rows: a hold on the balance
    (T1503), then the payment (T0001) and the hold's release (T1105), both pointing at the hold through
    paypal_reference_id. The hold and its release cancel out."""
    by_id = {t["transaction_id"]: t for t in txns if t.get("transaction_id")}
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in txns:
        ref = by_id.get(t.get("paypal_reference_id") or "")
        key = ref["transaction_id"] if ref and ref.get("transaction_event_code") == "T1503" else t.get("transaction_id")
        groups.setdefault(key or "", []).append(t)
    return list(groups.values())


def _main(group: list[dict[str, Any]]) -> dict[str, Any]:
    """The row that says what happened: the payment itself, not its hold or release."""
    for code in ("T0001", "T0006"):
        for t in group:
            if t.get("transaction_event_code") == code:
                return t
    return next((t for t in group if t.get("transaction_event_code") not in ("T1503", "T1105")), group[0])


def _row(t: dict[str, Any]) -> dict[str, Any]:
    code = t.get("transaction_event_code")
    return {"transaction_id": t.get("transaction_id"), "event_code": code, "event": EVENT_NAMES.get(code, code),
            "cents": _cents(t.get("transaction_amount")), "fee_cents": _cents(t.get("fee_amount")),
            "at": t.get("transaction_initiation_date"), "custom_field": t.get("custom_field"),
            "status": STATUS_NAMES.get(t.get("transaction_status"), t.get("transaction_status"))}


def reconcile(entries: list[dict[str, Any]], paypal_txns: list[dict[str, Any]], *, refreshed_at: str | None,
              ledger_started_at: str | None) -> dict[str, Any]:
    """Match the ledger against PayPal's Transaction Search report by transaction id.

    entries: the ledger's gifts and payouts, [{kind: 'gift'|'payout', ref, label, at, transaction_id,
             ours_cents, source: 'paypal'|'seed', status, earlier}]. Amounts are signed the way PayPal signs
             them: gifts in are positive, payouts out are negative.
    refreshed_at: PayPal's last_refreshed_datetime. Anything newer can't be in the report yet.
    ledger_started_at: PayPal rows from before then belong to an earlier ledger, so they're context, not problems.
    """
    groups = _groups(paypal_txns)
    by_main = {_main(g).get("transaction_id"): g for g in groups}
    refreshed, started = _when(refreshed_at), _when(ledger_started_at)
    used: set[int] = set()
    rows = []

    for e in entries:
        row = {**e, "paypal": None}
        group = by_main.get(e.get("transaction_id")) if e.get("transaction_id") else None
        if e.get("source") == "seed":
            row["state"], row["detail"] = "not_paypal", "A demo gift added without PayPal, so PayPal has no record of it."
        elif group is not None:
            used.add(id(group))
            main = _main(group)
            theirs = _row(main)
            row["paypal"] = {**theirs, "related": [_row(t) for t in group if t is not main]}
            if theirs["cents"] != e["ours_cents"]:
                row["state"] = "mismatch"
                row["detail"] = f"PayPal shows {theirs['cents'] / 100:+,.2f}, the ledger {e['ours_cents'] / 100:+,.2f}."
            elif main.get("transaction_status") in ("D", "V"):
                row["state"], row["detail"] = "mismatch", f"PayPal says this payment was {theirs['status']}."
            else:
                row["state"], row["detail"] = "matched", "Same transaction ID and amount in PayPal's report."
        elif e["kind"] == "payout" and e.get("status") in ("FAILED", "RETURNED", "BLOCKED", "REFUNDED", "REVERSED",
                                                           "DENIED", "CANCELED"):
            row["state"], row["detail"] = "failed", "PayPal didn't complete this payout, so nothing was paid."
        elif not e.get("transaction_id"):
            row["state"], row["detail"] = "waiting", "PayPal hasn't confirmed this payout with a transaction ID yet."
        elif refreshed is None or (_when(e.get("at")) or refreshed) > refreshed:
            row["state"], row["detail"] = "waiting", "Not in PayPal's report yet: the report runs a few hours behind."
        else:
            row["state"], row["detail"] = "missing", "Not in PayPal's report, though the report covers this time."
        rows.append(row)

    paypal_only = []
    for g in groups:
        if id(g) in used:
            continue
        main = _main(g)
        code, tag = main.get("transaction_event_code"), main.get("custom_field")
        if code == "T0001":
            kind, label = "payout", f"Payout for {tag}" if tag else "Payout"
        elif code == "T0006":
            kind, label = "gift", f"Gift tagged {tag}" if tag else "Checkout payment"
        elif code in ("T1503", "T1105"):
            kind, label = "payout", "Hold for a payout" + (" and its release" if len(g) > 1 else "")
        else:
            kind, label = "account", main.get("transaction_subject") or EVENT_NAMES.get(code, code or "Other")
        when = _when(main.get("transaction_initiation_date"))
        before = bool(started and when and when < started)
        paypal_only.append({
            "kind": kind, "label": label, "at": main.get("transaction_initiation_date"), "before_ledger": before,
            "net_cents": sum(_cents(t.get("transaction_amount")) + _cents(t.get("fee_amount")) for t in g),
            # A payment after the ledger started that the ledger doesn't know about is a real question.
            "attention": not before and kind in ("payout", "gift"),
            "rows": [_row(t) for t in sorted(g, key=lambda t: (t.get("transaction_initiation_date") or ""))],
        })
    paypal_only.sort(key=lambda p: p["at"] or "", reverse=True)

    count = {s: sum(1 for r in rows if r["state"] == s) for s in ("matched", "waiting", "not_paypal", "failed")}
    to_check = sum(1 for r in rows if r["state"] in ("mismatch", "missing")) + sum(1 for p in paypal_only if p["attention"])
    return {"rows": rows, "paypal_only": paypal_only, "summary": {**count, "to_check": to_check},
            "balanced": to_check == 0, "refreshed_at": refreshed_at, "ledger_started_at": ledger_started_at}
