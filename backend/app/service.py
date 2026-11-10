"""Use cases that touch both the database and PayPal."""
import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from . import ledger, review
from .db import now_iso, to_cents, transaction
from .llm import LLM
from .paypal import PayPalError, approve_link

log = logging.getLogger("uvicorn.error")

# PayPal's payout statuses, from the Payouts API spec (checked 2026-11-10). Item: SUCCESS, FAILED, PENDING, UNCLAIMED,
# RETURNED, ONHOLD, BLOCKED, REFUNDED, REVERSED. Batch: DENIED, PENDING, PROCESSING, SUCCESS, CANCELED.
# These mean the money didn't reach the partner, or came back, so the gifts go back to the fund.
PAYOUT_FAILED = ("FAILED", "RETURNED", "BLOCKED", "REFUNDED", "REVERSED", "DENIED", "CANCELED")
NO_ANSWER = "NO_ANSWER"  # PayPal didn't answer clearly; the next refresh asks again with the same sender_batch_id
_FAILED_SQL = ", ".join(f"'{s}'" for s in PAYOUT_FAILED)


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

    month_spent = _month_spent(conn, partner["id"], request_id)
    payout = conn.execute("SELECT * FROM payouts WHERE request_id = ?", (request_id,)).fetchone()
    review_info = json.loads(req["review_json"]) if req["review_json"] else {}
    rules = review.policy_chips(json.loads(fund["policy_json"])) if fund["policy_json"] else json.loads(fund["rules_json"])

    return {
        "id": req["id"],
        "status": req["status"],
        "purpose": req["purpose"],
        "submitted_at": req["submitted_at"],
        "approved_by": req["approved_by"],
        "partner": {"id": partner["id"], "name": partner["name"], "region": partner["region"]},
        "fund": {"code": fund["code"], "name": fund["name"], "donor_words": fund["donor_words"], "rules": rules},
        "shop": json.loads(req["shop_json"]),
        "receipt_url": f"/api/requests/{request_id}/receipt" if req["receipt_sha"] else None,
        "items": [{"key": i["item_key"], "receipt_text": i["receipt_text"], "label": i["label"], "qty": i["qty"],
                   "unit_cents": i["unit_cents"], "total_cents": ledger.item_total_cents(i), "category": i["category"],
                   "box": json.loads(i["box_json"]) if i["box_json"] else None,
                   "verdict": i["verdict"], "reason": i["reason"]} for i in items],
        "flags": review_info.get("flags", []),
        "ai": {k: review_info[k] for k in ("model", "cached", "seconds") if k in review_info} or None,
        "requested_cents": requested,
        "payable_cents": payable,
        "funding": funding,
        "shortfall_cents": shortfall,
        "checks": {"month_spent_cents": month_spent, "month_cap_cents": partner["month_cap_cents"]},
        "payout": dict(payout) if payout else None,
    }


def _month_spent(conn: sqlite3.Connection, partner_id: str, request_id: str) -> int:
    """What the partner has been paid this calendar month, not counting this request."""
    return conn.execute(
        f"""SELECT COALESCE(SUM(p.amount_cents), 0) FROM payouts p JOIN requests r ON r.id = p.request_id
           WHERE r.partner_id = ? AND substr(p.created_at, 1, 7) = substr(?, 1, 7) AND p.request_id != ?
           AND p.status NOT IN ({_FAILED_SQL})""",
        (partner_id, now_iso(), request_id),
    ).fetchone()[0]


def _must_be_reviewed(req: sqlite3.Row) -> None:
    """Two reviewers can have the same request open; the second one gets a plain answer, not a crash."""
    done = {"paying": "approved", "paid": "approved and paid", "returned": "sent back"}
    if req["status"] != "reviewed":
        raise Conflict(f"{req['id']} was already {done.get(req['status'], req['status'])}"
                       f"{' by ' + req['approved_by'] if req['approved_by'] and req['status'] != 'returned' else ''}. "
                       "The page now shows where it stands.")


def send_back_request(conn: sqlite3.Connection, request_id: str) -> dict[str, Any]:
    """The reviewer returns the request to the partner instead of paying it. No money moves."""
    with transaction(conn):
        req, _ = _load_request(conn, request_id)
        _must_be_reviewed(req)
        conn.execute("UPDATE requests SET status = 'returned' WHERE id = ?", (request_id,))
    return request_detail(conn, request_id)


def approve_request(conn: sqlite3.Connection, paypal: PayPal, request_id: str, approver: str) -> dict[str, Any]:
    """Allocate gifts FIFO, then pay the partner the payable amount through PayPal Payouts."""
    with transaction(conn):
        req, items = _load_request(conn, request_id)
        _must_be_reviewed(req)
        _, payable = ledger.request_amounts(items)
        if payable <= 0:
            raise Conflict("Nothing on this receipt fits the fund, so there is nothing to pay.")
        partner = conn.execute("SELECT * FROM partners WHERE id = ?", (req["partner_id"],)).fetchone()
        spent = _month_spent(conn, partner["id"], request_id)
        if spent + payable > partner["month_cap_cents"]:
            raise Conflict(f"Paying {payable / 100:,.2f} would take {partner['name']} past its monthly cap of "
                           f"{partner['month_cap_cents'] / 100:,.2f} ({spent / 100:,.2f} paid this month).")
        plan = ledger.plan_fifo(ledger.gift_balances(conn, req["fund_code"]), payable)
        # A payout PayPal refused or sent back before doesn't stop a new try.
        conn.execute(f"DELETE FROM payouts WHERE request_id = ? AND status IN ({_FAILED_SQL})", (request_id,))
        for balance, cents in plan:
            conn.execute("INSERT INTO allocations (gift_id, request_id, amount_cents) VALUES (?, ?, ?)",
                         (balance.gift_id, request_id, cents))
        # One sender_batch_id per try, fixed before PayPal is called: PayPal never makes two batches with the
        # same one, so asking again after an unclear answer can't pay the partner twice.
        stamp = now_iso()
        conn.execute(
            "INSERT INTO payouts (request_id, sender_batch_id, amount_cents, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'CREATED', ?, ?)",
            (request_id, f"{request_id}-{uuid.uuid4().hex[:10]}", payable, stamp, stamp),
        )
        conn.execute("UPDATE requests SET status = 'paying', approved_by = ?, approved_at = ? WHERE id = ?",
                     (approver, stamp, request_id))
    _send_payout(conn, paypal, request_id)
    return request_detail(conn, request_id)


def _send_payout(conn: sqlite3.Connection, paypal: PayPal, request_id: str) -> None:
    """Ask PayPal to pay, after the ledger has committed. A clear refusal undoes the approval. No clear answer
    (a timeout, a PayPal server error) keeps it: the money may have left, so the next refresh asks again with
    the same sender_batch_id and PayPal either makes the batch or points to the one it already made."""
    payout = conn.execute("SELECT * FROM payouts WHERE request_id = ?", (request_id,)).fetchone()
    req, items = _load_request(conn, request_id)
    partner = conn.execute("SELECT * FROM partners WHERE id = ?", (req["partner_id"],)).fetchone()
    fund = conn.execute("SELECT name FROM funds WHERE code = ?", (req["fund_code"],)).fetchone()
    fits = ", ".join(i["label"] for i in items if i["verdict"] == "fits")
    try:
        result = paypal.create_payout(
            sender_batch_id=payout["sender_batch_id"], sender_item_id=request_id, receiver_email=partner["paypal_email"],
            amount_cents=payout["amount_cents"], subject=f"Kindtrail payout for request {request_id}",
            note=f"{fund['name']}: {fits}",
        )
    except PayPalError as e:
        if not e.ambiguous:
            _undo_approval(conn, request_id)
            raise
        log.warning("payout %s: no clear answer from PayPal, will ask again: %s", payout["sender_batch_id"], e)
        conn.execute("UPDATE payouts SET status = ?, failure = ?, updated_at = ? WHERE request_id = ?",
                     (NO_ANSWER, str(e)[:300], now_iso(), request_id))
        return
    with transaction(conn):
        header = result.get("batch_header", {})
        conn.execute("UPDATE payouts SET payout_batch_id = ?, status = ?, failure = NULL, updated_at = ? "
                     "WHERE request_id = ?",
                     (header.get("payout_batch_id"), header.get("batch_status", "PENDING"), now_iso(), request_id))
        if result.get("items"):  # the batch an earlier try had already made, with its outcome
            apply_payout_batch(conn, request_id, result)


def _undo_approval(conn: sqlite3.Connection, request_id: str) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM allocations WHERE request_id = ?", (request_id,))
        conn.execute("DELETE FROM payouts WHERE request_id = ?", (request_id,))
        conn.execute("UPDATE requests SET status = 'reviewed', approved_by = NULL, approved_at = NULL WHERE id = ?",
                     (request_id,))


def _age_seconds(iso: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds()


def refresh_payout(conn: sqlite3.Connection, paypal: PayPal, request_id: str) -> dict[str, Any]:
    payout = conn.execute("SELECT * FROM payouts WHERE request_id = ?", (request_id,)).fetchone()
    if payout is None:
        raise NotFound(f"request {request_id} has no payout yet")
    if not payout["payout_batch_id"]:
        # No batch yet: PayPal gave no clear answer, or the server stopped mid-call. Ask again, same batch id.
        stuck = payout["status"] == NO_ANSWER or (payout["status"] == "CREATED" and _age_seconds(payout["updated_at"]) > 120)
        if stuck:
            _send_payout(conn, paypal, request_id)
        return request_detail(conn, request_id)
    batch = paypal.get_payout_batch(payout["payout_batch_id"])
    with transaction(conn):
        apply_payout_batch(conn, request_id, batch)
    return request_detail(conn, request_id)


def apply_payout_batch(conn: sqlite3.Connection, request_id: str, batch: dict[str, Any]) -> None:
    """Record what PayPal says about a request's payout. Call inside a transaction."""
    header = batch.get("batch_header", {})
    item = next((i for i in batch.get("items", [])
                 if i.get("payout_item", {}).get("sender_item_id") == request_id), {})
    fee = item.get("payout_item_fee") or header.get("fees")
    batch_status, item_status = header.get("batch_status", "PENDING"), item.get("transaction_status")
    errors = item.get("errors") if isinstance(item.get("errors"), dict) else {}
    conn.execute(
        "UPDATE payouts SET status = ?, transaction_id = COALESCE(?, transaction_id), fee_cents = COALESCE(?, fee_cents), "
        "failure = COALESCE(?, failure), updated_at = ? WHERE request_id = ?",
        (item_status or batch_status, item.get("transaction_id"), to_cents(fee["value"]) if fee else None,
         errors.get("message") or errors.get("name"), now_iso(), request_id),
    )
    if item_status in PAYOUT_FAILED or batch_status in PAYOUT_FAILED:
        # Nothing reached the partner (or it came back): free the gifts and put the request back for review.
        conn.execute("DELETE FROM allocations WHERE request_id = ?", (request_id,))
        conn.execute("UPDATE requests SET status = 'reviewed', approved_by = NULL, approved_at = NULL "
                     "WHERE id = ? AND status IN ('paying', 'paid')", (request_id,))
    elif item_status == "SUCCESS" or (item_status is None and batch_status == "SUCCESS"):
        # The item's own SUCCESS means the partner has the money, even while the batch still says PROCESSING.
        conn.execute("UPDATE requests SET status = 'paid' WHERE id = ? AND status = 'paying'", (request_id,))


# AI review ---------------------------------------------------------------------------------

def parse_limits(conn: sqlite3.Connection, llm: LLM, donor_words: str, today: str | None = None) -> dict[str, Any]:
    """Donor's plain words -> structured policy (model), plus display chips.

    `today` anchors phrases like "by the end of the year"; pass the fund's creation date so the
    prompt (and its cache key) stays the same from day to day.
    """
    prompt = review.LIMITS_PROMPT.format(today=today or now_iso()[:10], words=donor_words.strip())
    answer = llm.ask(conn, task="limits", prompt=prompt, schema=review.LIMITS_SCHEMA)
    # Always-refused categories are implicit: keep them out of both lists.
    policy = {**answer.data,
              "allowed": [c for c in answer.data.get("allowed", []) if c not in review.ALWAYS_NEVER],
              "never": [c for c in answer.data.get("never", []) if c not in review.ALWAYS_NEVER]}
    return {"policy": policy, "rules": review.policy_chips(policy), "model": answer.model, "cached": answer.cached,
            "seconds": answer.seconds}


def _next_request_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT MAX(CAST(substr(id, 4) AS INTEGER)) FROM requests WHERE id LIKE 'KT-%'").fetchone()
    return f"KT-{(row[0] or 0) + 1:04d}"


def create_request(conn: sqlite3.Connection, llm: LLM, *, fund_code: str, partner_id: str, purpose: str,
                   image: bytes, mime: str, request_id: str | None = None,
                   submitted_at: str | None = None) -> dict[str, Any]:
    """A partner's spending request: read the receipt with the model, then judge it with the rules."""
    fund = conn.execute("SELECT * FROM funds WHERE code = ?", (fund_code,)).fetchone()
    if fund is None:
        raise NotFound(f"no fund {fund_code}")
    if conn.execute("SELECT 1 FROM partners WHERE id = ?", (partner_id,)).fetchone() is None:
        raise NotFound(f"no partner {partner_id}")
    if not fund["policy_json"]:
        raise Conflict(f"fund {fund_code} has no structured limits yet")

    sha = hashlib.sha256(image).hexdigest()
    earlier = conn.execute("SELECT id FROM requests WHERE receipt_sha = ? ORDER BY submitted_at LIMIT 1", (sha,)).fetchone()
    answer = llm.ask(conn, task="receipt", prompt=review.RECEIPT_PROMPT, schema=review.RECEIPT_SCHEMA,
                     image=image, mime=mime)
    result = review.judge(answer.data, json.loads(fund["policy_json"]), duplicate_of=earlier["id"] if earlier else None)

    shop = {"name": result.shop.get("name", ""), "branch": result.shop.get("branch", ""),
            "printed_at": result.shop.get("printed_at", ""), "region": result.shop.get("region", "")}
    review_info = {"flags": result.flags, "model": answer.model, "cached": answer.cached, "seconds": answer.seconds,
                   "receipt_total_cents": result.receipt_total_cents}
    with transaction(conn):
        request_id = request_id or _next_request_id(conn)
        conn.execute("INSERT OR IGNORE INTO receipts (sha256, mime, bytes, created_at) VALUES (?, ?, ?, ?)",
                     (sha, mime, image, now_iso()))
        conn.execute(
            "INSERT INTO requests (id, fund_code, partner_id, purpose, shop_json, status, submitted_at, receipt_sha, "
            "review_json) VALUES (?, ?, ?, ?, ?, 'reviewed', ?, ?, ?)",
            (request_id, fund_code, partner_id, purpose, json.dumps(shop), submitted_at or now_iso(), sha,
             json.dumps(review_info)),
        )
        conn.executemany(
            "INSERT INTO request_items (request_id, item_key, receipt_text, label, qty, unit_cents, verdict, reason, "
            "category, box_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(request_id, f"line-{n + 1}", ln.receipt_text, ln.label, ln.qty, ln.unit_cents, ln.verdict, ln.reason,
              ln.category, json.dumps(ln.box) if ln.box else None) for n, ln in enumerate(result.lines)],
        )
    return request_detail(conn, request_id)


def receipt_image(conn: sqlite3.Connection, request_id: str) -> tuple[bytes, str]:
    row = conn.execute("SELECT r.bytes, r.mime FROM requests q JOIN receipts r ON r.sha256 = q.receipt_sha "
                       "WHERE q.id = ?", (request_id,)).fetchone()
    if row is None:
        raise NotFound(f"request {request_id} has no receipt photo")
    return row["bytes"], row["mime"]


# Donor impact ------------------------------------------------------------------------------

def gift_impact(conn: sqlite3.Connection, gift_id: int) -> dict[str, Any]:
    """Everything one gift paid for, line by line, with the PayPal payout that proves it."""
    gift = conn.execute(
        "SELECT g.*, f.name AS fund_name, f.policy_json, f.rules_json FROM gifts g JOIN funds f ON f.code = g.fund_code "
        "WHERE g.id = ? AND g.status = 'captured'", (gift_id,)).fetchone()
    if gift is None:
        raise NotFound(f"no gift {gift_id}")

    spends = []
    request_ids = [r[0] for r in conn.execute(
        "SELECT request_id FROM allocations WHERE gift_id = ? GROUP BY request_id ORDER BY MIN(id)", (gift_id,))]
    for request_id in request_ids:
        req, items = _load_request(conn, request_id)
        allocs = conn.execute("SELECT gift_id, amount_cents FROM allocations WHERE request_id = ? ORDER BY id",
                              (request_id,)).fetchall()
        fitting = [i for i in items if i["verdict"] == "fits"]
        mine: dict[str, int] = {}
        for gid, key, cents in ledger.split_by_item([(a["gift_id"], a["amount_cents"]) for a in allocs],
                                                    [(i["item_key"], ledger.item_total_cents(i)) for i in fitting]):
            if gid == gift_id:
                mine[key] = mine.get(key, 0) + cents
        donors = conn.execute(
            "SELECT a.gift_id, g.donor_name, SUM(a.amount_cents) AS cents FROM allocations a JOIN gifts g ON g.id = a.gift_id "
            "WHERE a.request_id = ? GROUP BY a.gift_id ORDER BY MIN(a.id)", (request_id,)).fetchall()
        partner = conn.execute("SELECT name FROM partners WHERE id = ?", (req["partner_id"],)).fetchone()
        payout = conn.execute("SELECT * FROM payouts WHERE request_id = ?", (request_id,)).fetchone()
        spends.append({
            "request_id": request_id,
            "status": req["status"],
            "partner": partner["name"],
            "purpose": req["purpose"],
            "shop": json.loads(req["shop_json"]),
            "receipt_url": f"/api/requests/{request_id}/receipt" if req["receipt_sha"] else None,
            "approved_by": req["approved_by"],
            "approved_at": req["approved_at"],
            "paid_at": payout["updated_at"] if payout and payout["status"] == "SUCCESS" else None,
            "payout_transaction_id": payout["transaction_id"] if payout else None,
            "payable_cents": sum(ledger.item_total_cents(i) for i in fitting),
            "your_cents": sum(a["amount_cents"] for a in allocs if a["gift_id"] == gift_id),
            "items": [{"key": i["item_key"], "label": i["label"], "total_cents": ledger.item_total_cents(i),
                       "yours_cents": mine.get(i["item_key"], 0),
                       "box": json.loads(i["box_json"]) if i["box_json"] else None} for i in fitting],
            "donors": [{"donor": d["donor_name"], "cents": d["cents"], "you": d["gift_id"] == gift_id} for d in donors],
            "submitted_at": req["submitted_at"],
            # Lines the rules refused: the partner had to pay those without donors' money.
            "refused": [{"label": i["label"], "total_cents": ledger.item_total_cents(i), "reason": i["reason"]}
                        for i in items if i["verdict"] != "fits"],
        })

    used = sum(s["your_cents"] for s in spends)
    rules = review.policy_chips(json.loads(gift["policy_json"])) if gift["policy_json"] else json.loads(gift["rules_json"])
    return {
        "gift": {"id": gift["id"], "donor": gift["donor_name"], "amount_cents": gift["amount_cents"],
                 "given_at": gift["captured_at"], "source": gift["source"],
                 "paypal_capture_id": gift["paypal_capture_id"]},
        "fund": {"code": gift["fund_code"], "name": gift["fund_name"], "rules": rules},
        "used_cents": used,
        "left_cents": gift["amount_cents"] - used,
        "spends": spends,
    }


# Reconciliation ---------------------------------------------------------------------------

def ledger_started_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = 'ledger_started_at'").fetchone()
    return row["value"] if row else None


def ledger_entries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every gift and payout this ledger knows about, including ones a demo reset moved to the archive,
    signed the way PayPal's report signs them (money in positive, money out negative)."""
    out: list[dict[str, Any]] = []
    for g in conn.execute("SELECT * FROM gifts WHERE status = 'captured' ORDER BY captured_at, id"):
        out.append({"kind": "gift", "ref": f"gift-{g['id']}", "label": f"Gift from {g['donor_name']}",
                    "at": g["captured_at"], "transaction_id": g["paypal_capture_id"], "ours_cents": g["amount_cents"],
                    "source": g["source"], "status": g["status"], "earlier": False})
    for p in conn.execute("SELECT p.*, pa.name AS partner FROM payouts p JOIN requests r ON r.id = p.request_id "
                          "JOIN partners pa ON pa.id = r.partner_id ORDER BY p.created_at"):
        out.append({"kind": "payout", "ref": p["request_id"], "label": f"Payout for {p['request_id']} to {p['partner']}",
                    "at": p["created_at"], "transaction_id": p["transaction_id"], "ours_cents": -p["amount_cents"],
                    "source": "paypal", "status": p["status"], "earlier": False})
    for a in conn.execute("SELECT * FROM ledger_archive ORDER BY id"):
        gift = a["kind"] == "gift"
        out.append({"kind": a["kind"], "ref": a["ref"], "label": f"Gift from {a['ref']}" if gift else f"Payout for {a['ref']}",
                    "at": a["happened_at"], "transaction_id": a["transaction_id"],
                    "ours_cents": a["amount_cents"] if gift else -a["amount_cents"], "source": "paypal",
                    "status": a["status"], "earlier": True})
    out.sort(key=lambda e: e["at"] or "", reverse=True)
    return out


# Webhooks ---------------------------------------------------------------------------------

def handle_webhook(conn: sqlite3.Connection, event: dict[str, Any]) -> str:
    """Act on a webhook event once, by its PayPal event id. Only call this with an event whose signature PayPal
    verified: unverified ones are never stored, so a later delivery that does verify still counts."""
    resource = event.get("resource") or {}
    kind = event.get("event_type", "")
    with transaction(conn):
        inserted = conn.execute(
            "INSERT OR IGNORE INTO webhook_events (id, event_type, resource_id, verified, payload, received_at) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (event.get("id"), kind, resource.get("id"), json.dumps(event), now_iso()),
        ).rowcount
        if not inserted:
            return "duplicate"
        return _apply_event(conn, kind, resource)


def _apply_event(conn: sqlite3.Connection, kind: str, resource: dict[str, Any]) -> str:
    if kind == "PAYMENT.CAPTURE.COMPLETED":
        order_id = (resource.get("supplementary_data") or {}).get("related_ids", {}).get("order_id")
        gift = conn.execute("SELECT * FROM gifts WHERE paypal_order_id = ?", (order_id,)).fetchone()
        if gift and gift["status"] == "created" and to_cents(resource["amount"]["value"]) == gift["amount_cents"]:
            conn.execute("UPDATE gifts SET status = 'captured', paypal_capture_id = ?, captured_at = ? WHERE id = ?",
                         (resource["id"], now_iso(), gift["id"]))
            return "gift-captured"
    elif kind.startswith("PAYMENT.PAYOUTS-ITEM."):
        request_id = (resource.get("payout_item") or {}).get("sender_item_id")
        payout = conn.execute("SELECT payout_batch_id FROM payouts WHERE request_id = ?", (request_id,)).fetchone()
        # Request ids start again after a demo reset, so the event has to be about this payout's batch.
        if payout and payout["payout_batch_id"] and payout["payout_batch_id"] == resource.get("payout_batch_id"):
            batch_status = "SUCCESS" if resource.get("transaction_status") == "SUCCESS" else "PROCESSING"
            apply_payout_batch(conn, request_id, {"batch_header": {"batch_status": batch_status}, "items": [resource]})
            return "payout-updated"
    elif kind == "PAYMENT.PAYOUTSBATCH.DENIED":
        header = resource.get("batch_header") or {}
        payout = conn.execute("SELECT request_id FROM payouts WHERE payout_batch_id = ?",
                              (header.get("payout_batch_id"),)).fetchone()
        if payout:
            apply_payout_batch(conn, payout["request_id"], {"batch_header": {**header, "batch_status": "DENIED"}})
            return "payout-denied"
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
        "rules": review.policy_chips(json.loads(fund["policy_json"])) if fund["policy_json"] else json.loads(fund["rules_json"]),
        "received_cents": sum(b.amount_cents for b in balances),
        "spent_cents": sum(b.used_cents for b in balances),
        "available_cents": sum(b.remaining_cents for b in balances),
        "gifts": [{"gift_id": b.gift_id, "donor": b.donor_name, "date": b.captured_at, "given_cents": b.amount_cents,
                   "used_cents": b.used_cents, "left_cents": b.remaining_cents} for b in balances],
    }


def list_funds(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [{"code": f["code"], "name": f["name"]} for f in conn.execute("SELECT code, name FROM funds ORDER BY rowid")]


def list_requests(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every spending request, waiting ones first, newest first within each status."""
    out = []
    for r in conn.execute(
            "SELECT q.*, p.name AS partner_name, f.name AS fund_name FROM requests q "
            "JOIN partners p ON p.id = q.partner_id JOIN funds f ON f.code = q.fund_code "
            "ORDER BY CASE q.status WHEN 'reviewed' THEN 0 WHEN 'paying' THEN 1 ELSE 2 END, q.submitted_at DESC"):
        items = conn.execute("SELECT * FROM request_items WHERE request_id = ?", (r["id"],)).fetchall()
        requested, payable = ledger.request_amounts(items)
        flags = json.loads(r["review_json"]).get("flags", []) if r["review_json"] else []
        out.append({"id": r["id"], "status": r["status"], "partner": r["partner_name"], "fund": r["fund_name"],
                    "purpose": r["purpose"], "submitted_at": r["submitted_at"], "requested_cents": requested,
                    "payable_cents": payable, "lines": len(items),
                    "fits": sum(1 for i in items if i["verdict"] == "fits"),
                    "flags": [f["message"] for f in flags]})
    return out


def _fund_code(conn: sqlite3.Connection, name: str) -> str:
    """FUND-<NAME-IN-CAPS>, made unique. It travels to PayPal in purchase_units.custom_id."""
    slug = "".join(c if c.isascii() and c.isalnum() else "-" for c in name.upper())
    slug = "-".join(part for part in slug.split("-") if part and part != "FUND")[:32] or "GIFTS"
    code, n = f"FUND-{slug}", 2
    while conn.execute("SELECT 1 FROM funds WHERE code = ?", (code,)).fetchone():
        code, n = f"FUND-{slug}-{n}", n + 1
    return code


def create_fund(conn: sqlite3.Connection, *, name: str, donor_words: str, policy: dict[str, Any]) -> dict[str, Any]:
    if not policy.get("allowed"):
        raise Conflict("a fund needs at least one use it can pay for")
    code = _fund_code(conn, name)
    conn.execute("INSERT INTO funds (code, name, donor_words, rules_json, policy_json) VALUES (?, ?, ?, '[]', ?)",
                 (code, name.strip(), donor_words.strip(), json.dumps(policy)))
    return fund_summary(conn, code)


# Limits ------------------------------------------------------------------------------------

def categories() -> dict[str, Any]:
    return {"categories": [{"key": c, "label": review.LABELS[c]} for c in review.CATEGORIES],
            "always_never": sorted(review.ALWAYS_NEVER)}


def preview_policy(conn: sqlite3.Connection, llm: LLM, policy: dict[str, Any],
                   receipts: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    """How a policy would judge receipts the AI has already read. Uses cached readings only."""
    out = []
    for name, image in receipts:
        answer = llm.lookup(conn, task="receipt", prompt=review.RECEIPT_PROMPT, schema=review.RECEIPT_SCHEMA, image=image)
        if answer is None:
            continue
        result = review.judge(answer.data, policy)
        fits = [ln for ln in result.lines if ln.verdict == "fits"]
        out.append({
            "name": name,
            "shop": result.shop.get("name", ""),
            "region": result.shop.get("region", ""),
            "lines": len(result.lines),
            "fits": len(fits),
            "requested_cents": sum(ln.line_cents for ln in result.lines),
            "payable_cents": sum(ln.line_cents for ln in fits),
            "blocked": [{"label": ln.label, "reason": ln.reason} for ln in result.lines if ln.verdict == "blocked"],
            "flags": result.flags,
        })
    return out
