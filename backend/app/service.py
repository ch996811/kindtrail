"""Use cases that touch both the database and PayPal."""
import json
import sqlite3
import uuid
from typing import Any, Protocol

from . import ledger
from .db import now_iso, to_cents, transaction
from .paypal import PayPalError, approve_link


class PayPal(Protocol):
    def create_donation_order(self, *, fund_code: str, fund_name: str, amount_cents: int, request_id: str) -> dict: ...
    def capture_order(self, order_id: str) -> dict: ...
    def create_payout(self, *, sender_batch_id: str, sender_item_id: str, receiver_email: str,
                      amount_cents: int, note: str, subject: str) -> dict: ...
    def get_payout_batch(self, payout_batch_id: str) -> dict: ...


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


# Gifts ------------------------------------------------------------------------------------

def create_gift(conn: sqlite3.Connection, paypal: PayPal, *, fund_code: str, donor_name: str,
                amount_cents: int) -> dict[str, Any]:
    fund = conn.execute("SELECT * FROM funds WHERE code = ?", (fund_code,)).fetchone()
    if fund is None:
        raise NotFound(f"no fund {fund_code}")
    order = paypal.create_donation_order(fund_code=fund_code, fund_name=fund["name"],
                                         amount_cents=amount_cents, request_id=f"gift-{uuid.uuid4()}")
    cur = conn.execute(
        "INSERT INTO gifts (fund_code, donor_name, amount_cents, status, paypal_order_id, created_at) "
        "VALUES (?, ?, ?, 'created', ?, ?)",
        (fund_code, donor_name, amount_cents, order["id"], now_iso()),
    )
    return {"gift_id": cur.lastrowid, "order_id": order["id"], "approve_url": approve_link(order)}


def capture_gift(conn: sqlite3.Connection, paypal: PayPal, order_id: str) -> dict[str, Any]:
    gift = conn.execute("SELECT * FROM gifts WHERE paypal_order_id = ?", (order_id,)).fetchone()
    if gift is None:
        raise NotFound(f"no gift for order {order_id}")
    if gift["status"] == "captured":
        return dict(gift)  # already done (e.g. the webhook got here first)

    result = paypal.capture_order(order_id)
    unit = result["purchase_units"][0]
    capture = unit["payments"]["captures"][0]
    if capture["status"] != "COMPLETED":
        raise Conflict(f"capture status is {capture['status']}, not COMPLETED")
    paid = to_cents(capture["amount"]["value"])
    if paid != gift["amount_cents"] or capture["amount"]["currency_code"] != "USD":
        raise Conflict(f"PayPal captured {capture['amount']}, expected {gift['amount_cents']} cents USD")
    fund_tag = capture.get("custom_id") or unit.get("custom_id")
    if fund_tag and fund_tag != gift["fund_code"]:
        raise Conflict(f"order is tagged {fund_tag}, gift belongs to {gift['fund_code']}")

    conn.execute(
        "UPDATE gifts SET status = 'captured', paypal_capture_id = ?, captured_at = ? WHERE id = ?",
        (capture["id"], now_iso(), gift["id"]),
    )
    return dict(conn.execute("SELECT * FROM gifts WHERE id = ?", (gift["id"],)).fetchone())


# Requests ---------------------------------------------------------------------------------

def _load_request(conn: sqlite3.Connection, request_id: str) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    req = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if req is None:
        raise NotFound(f"no request {request_id}")
    items = conn.execute("SELECT * FROM request_items WHERE request_id = ? ORDER BY id", (request_id,)).fetchall()
    return req, items


def request_detail(conn: sqlite3.Connection, request_id: str) -> dict[str, Any]:
    req, items = _load_request(conn, request_id)
    fund = conn.execute("SELECT * FROM funds WHERE code = ?", (req["fund_code"],)).fetchone()
    partner = conn.execute("SELECT * FROM partners WHERE id = ?", (req["partner_id"],)).fetchone()
    requested, payable = ledger.request_amounts(items)

    # After approval show the real allocations; before it, preview what FIFO would take.
    rows = conn.execute(
        """SELECT a.amount_cents, g.id AS gift_id, g.donor_name, g.amount_cents AS given, g.captured_at
           FROM allocations a JOIN gifts g ON g.id = a.gift_id WHERE a.request_id = ? ORDER BY a.id""",
        (request_id,),
    ).fetchall()
    balances = {b.gift_id: b for b in ledger.gift_balances(conn, req["fund_code"])}
    if rows:
        funding = [{"gift_id": r["gift_id"], "donor": r["donor_name"], "date": r["captured_at"],
                    "given_cents": r["given"], "used_here_cents": r["amount_cents"],
                    "left_cents": balances[r["gift_id"]].remaining_cents} for r in rows]
        shortfall = 0
    else:
        try:
            plan = ledger.plan_fifo(list(balances.values()), payable)
            shortfall = 0
        except ledger.InsufficientFunds as e:
            plan = ledger.plan_fifo(list(balances.values()), e.available_cents)
            shortfall = payable - e.available_cents
        funding = [{"gift_id": b.gift_id, "donor": b.donor_name, "date": b.captured_at, "given_cents": b.amount_cents,
                    "used_here_cents": take, "left_cents": b.remaining_cents - take} for b, take in plan]

    month_spent = conn.execute(
        """SELECT COALESCE(SUM(p.amount_cents), 0) FROM payouts p JOIN requests r ON r.id = p.request_id
           WHERE r.partner_id = ? AND substr(p.created_at, 1, 7) = substr(?, 1, 7) AND p.request_id != ?""",
        (partner["id"], now_iso(), request_id),
    ).fetchone()[0]
    payout = conn.execute("SELECT * FROM payouts WHERE request_id = ?", (request_id,)).fetchone()

    return {
        "id": req["id"],
        "status": req["status"],
        "purpose": req["purpose"],
        "submitted_at": req["submitted_at"],
        "approved_by": req["approved_by"],
        "partner": {"id": partner["id"], "name": partner["name"], "region": partner["region"]},
        "fund": {"code": fund["code"], "name": fund["name"], "donor_words": fund["donor_words"],
                 "rules": json.loads(fund["rules_json"])},
        "shop": json.loads(req["shop_json"]),
        "items": [{"key": i["item_key"], "receipt_text": i["receipt_text"], "label": i["label"], "qty": i["qty"],
                   "unit_cents": i["unit_cents"], "total_cents": ledger.item_total_cents(i),
                   "verdict": i["verdict"], "reason": i["reason"]} for i in items],
        "requested_cents": requested,
        "payable_cents": payable,
        "funding": funding,
        "shortfall_cents": shortfall,
        "checks": {"month_spent_cents": month_spent, "month_cap_cents": partner["month_cap_cents"]},
        "payout": dict(payout) if payout else None,
    }


def approve_request(conn: sqlite3.Connection, paypal: PayPal, request_id: str, approver: str) -> dict[str, Any]:
    """Allocate gifts FIFO, then pay the partner the payable amount through PayPal Payouts."""
    with transaction(conn):
        req, items = _load_request(conn, request_id)
        if req["status"] != "reviewed":
            raise Conflict(f"request {request_id} is {req['status']}, only reviewed requests can be approved")
        _, payable = ledger.request_amounts(items)
        if payable <= 0:
            raise Conflict("nothing on this receipt fits the fund")
        plan = ledger.plan_fifo(ledger.gift_balances(conn, req["fund_code"]), payable)
        for balance, cents in plan:
            conn.execute("INSERT INTO allocations (gift_id, request_id, amount_cents) VALUES (?, ?, ?)",
                         (balance.gift_id, request_id, cents))
        sender_batch_id = f"{request_id}-{uuid.uuid4().hex[:10]}"
        stamp = now_iso()
        conn.execute(
            "INSERT INTO payouts (request_id, sender_batch_id, amount_cents, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'CREATED', ?, ?)",
            (request_id, sender_batch_id, payable, stamp, stamp),
        )
        conn.execute("UPDATE requests SET status = 'paying', approved_by = ?, approved_at = ? WHERE id = ?",
                     (approver, stamp, request_id))
        partner = conn.execute("SELECT * FROM partners WHERE id = ?", (req["partner_id"],)).fetchone()
        fund = conn.execute("SELECT name FROM funds WHERE code = ?", (req["fund_code"],)).fetchone()

    # The money only moves after our ledger has committed. If PayPal refuses, undo the ledger.
    fits = ", ".join(i["label"] for i in items if i["verdict"] == "fits")
    try:
        result = paypal.create_payout(
            sender_batch_id=sender_batch_id, sender_item_id=request_id, receiver_email=partner["paypal_email"],
            amount_cents=payable, subject=f"Kindtrail payout for request {request_id}",
            note=f"{fund['name']}: {fits}",
        )
    except PayPalError:
        with transaction(conn):
            conn.execute("DELETE FROM allocations WHERE request_id = ?", (request_id,))
            conn.execute("DELETE FROM payouts WHERE request_id = ?", (request_id,))
            conn.execute("UPDATE requests SET status = 'reviewed', approved_by = NULL, approved_at = NULL WHERE id = ?",
                         (request_id,))
        raise

    header = result.get("batch_header", {})
    conn.execute("UPDATE payouts SET payout_batch_id = ?, status = ?, updated_at = ? WHERE request_id = ?",
                 (header.get("payout_batch_id"), header.get("batch_status", "PENDING"), now_iso(), request_id))
    return request_detail(conn, request_id)


def refresh_payout(conn: sqlite3.Connection, paypal: PayPal, request_id: str) -> dict[str, Any]:
    payout = conn.execute("SELECT * FROM payouts WHERE request_id = ?", (request_id,)).fetchone()
    if payout is None or not payout["payout_batch_id"]:
        raise NotFound(f"request {request_id} has no payout yet")
    batch = paypal.get_payout_batch(payout["payout_batch_id"])
    apply_payout_batch(conn, request_id, batch)
    return request_detail(conn, request_id)


def apply_payout_batch(conn: sqlite3.Connection, request_id: str, batch: dict[str, Any]) -> None:
    header = batch.get("batch_header", {})
    item = next((i for i in batch.get("items", [])
                 if i.get("payout_item", {}).get("sender_item_id") == request_id), {})
    fee = item.get("payout_item_fee") or header.get("fees")
    status = header.get("batch_status", "PENDING")
    conn.execute(
        "UPDATE payouts SET status = ?, transaction_id = COALESCE(?, transaction_id), fee_cents = COALESCE(?, fee_cents), "
        "updated_at = ? WHERE request_id = ?",
        (status, item.get("transaction_id"), to_cents(fee["value"]) if fee else None, now_iso(), request_id),
    )
    if status == "SUCCESS" and item.get("transaction_status") in (None, "SUCCESS"):
        conn.execute("UPDATE requests SET status = 'paid' WHERE id = ? AND status = 'paying'", (request_id,))


# Webhooks ---------------------------------------------------------------------------------

def handle_webhook(conn: sqlite3.Connection, event: dict[str, Any], verified: bool) -> str:
    """Record every event once; only verified events may change the ledger."""
    resource = event.get("resource") or {}
    inserted = conn.execute(
        "INSERT OR IGNORE INTO webhook_events (id, event_type, resource_id, verified, payload, received_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (event.get("id"), event.get("event_type", ""), resource.get("id"), int(verified), json.dumps(event), now_iso()),
    ).rowcount
    if not inserted:
        return "duplicate"
    if not verified:
        return "stored-unverified"

    kind = event.get("event_type", "")
    if kind == "PAYMENT.CAPTURE.COMPLETED":
        order_id = (resource.get("supplementary_data") or {}).get("related_ids", {}).get("order_id")
        gift = conn.execute("SELECT * FROM gifts WHERE paypal_order_id = ?", (order_id,)).fetchone()
        if gift and gift["status"] == "created" and to_cents(resource["amount"]["value"]) == gift["amount_cents"]:
            conn.execute("UPDATE gifts SET status = 'captured', paypal_capture_id = ?, captured_at = ? WHERE id = ?",
                         (resource["id"], now_iso(), gift["id"]))
            return "gift-captured"
    elif kind.startswith("PAYMENT.PAYOUTS-ITEM."):
        item = resource.get("payout_item") or {}
        request_id = item.get("sender_item_id")
        if request_id and conn.execute("SELECT 1 FROM payouts WHERE request_id = ?", (request_id,)).fetchone():
            batch_status = "SUCCESS" if resource.get("transaction_status") == "SUCCESS" else "PROCESSING"
            apply_payout_batch(conn, request_id, {"batch_header": {"batch_status": batch_status},
                                                  "items": [resource]})
            return "payout-updated"
    return "ignored"


# Funds ------------------------------------------------------------------------------------

def fund_summary(conn: sqlite3.Connection, fund_code: str) -> dict[str, Any]:
    fund = conn.execute("SELECT * FROM funds WHERE code = ?", (fund_code,)).fetchone()
    if fund is None:
        raise NotFound(f"no fund {fund_code}")
    balances = ledger.gift_balances(conn, fund_code)
    return {
        "code": fund["code"],
        "name": fund["name"],
        "donor_words": fund["donor_words"],
        "rules": json.loads(fund["rules_json"]),
        "received_cents": sum(b.amount_cents for b in balances),
        "spent_cents": sum(b.used_cents for b in balances),
        "available_cents": sum(b.remaining_cents for b in balances),
        "gifts": [{"gift_id": b.gift_id, "donor": b.donor_name, "date": b.captured_at, "given_cents": b.amount_cents,
                   "used_cents": b.used_cents, "left_cents": b.remaining_cents} for b in balances],
    }
