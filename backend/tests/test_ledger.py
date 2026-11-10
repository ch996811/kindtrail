import pytest

from app.ledger import GiftBalance, InsufficientFunds, plan_fifo, reconcile


def gift(gid, amount, used=0, at="2026-10-21T00:00:00Z"):
    return GiftBalance(gid, f"donor{gid}", amount, used, at)


def test_fifo_spends_oldest_gift_first_and_splits_the_last_one():
    balances = [gift(1, 5000), gift(2, 2000), gift(3, 2500)]
    plan = plan_fifo(balances, 7760)
    assert [(b.gift_id, cents) for b, cents in plan] == [(1, 5000), (2, 2000), (3, 760)]


def test_fifo_skips_gifts_already_used_up():
    plan = plan_fifo([gift(1, 5000, used=5000), gift(2, 2000, used=500)], 1000)
    assert [(b.gift_id, cents) for b, cents in plan] == [(2, 1000)]


def test_fifo_refuses_when_the_fund_cannot_cover_it():
    with pytest.raises(InsufficientFunds) as e:
        plan_fifo([gift(1, 3000), gift(2, 1000, used=400)], 7760)
    assert e.value.available_cents == 3600
    assert e.value.needed_cents == 7760


def txn(tid, value, code="T0006", at="2026-11-09T09:00:00Z", **extra):
    return {"transaction_id": tid, "transaction_event_code": code, "transaction_amount": {"currency_code": "USD", "value": value},
            "transaction_status": "S", "transaction_initiation_date": at, **extra}


def entry(kind, ref, txn_id, cents, at="2026-11-09T08:00:00Z", source="paypal", status="SUCCESS"):
    return {"kind": kind, "ref": ref, "label": ref, "at": at, "transaction_id": txn_id, "ours_cents": cents,
            "source": source, "status": status, "earlier": False}


STARTED = "2026-11-09T00:00:00Z"
REFRESHED = "2026-11-09T12:00:00Z"


def test_reconcile_matches_by_transaction_id_and_groups_a_payouts_hold_and_release():
    entries = [entry("gift", "gift-1", "CAP1", 8000), entry("payout", "KT-1", "PAY1", -7760)]
    report = [txn("CAP1", "80.00", fee_amount={"value": "-3.11"}),
              txn("HOLD1", "-79.15", code="T1503"),
              txn("PAY1", "-77.60", code="T0001", fee_amount={"value": "-1.55"}, paypal_reference_id="HOLD1", custom_field="KT-1"),
              txn("REL1", "79.15", code="T1105", paypal_reference_id="HOLD1", custom_field="KT-1")]
    result = reconcile(entries, report, refreshed_at=REFRESHED, ledger_started_at=STARTED)
    assert result["balanced"] is True
    assert [r["state"] for r in result["rows"]] == ["matched", "matched"]
    payout = result["rows"][1]["paypal"]
    assert (payout["cents"], payout["fee_cents"], payout["event"]) == (-7760, -155, "Mass payment")
    assert {r["transaction_id"] for r in payout["related"]} == {"HOLD1", "REL1"}
    assert result["paypal_only"] == []


def test_reconcile_tells_waiting_from_missing_and_mismatched():
    entries = [
        entry("gift", "gift-2", None, 5000, source="seed"),
        entry("gift", "gift-3", "CAP3", 1000),
        entry("payout", "KT-2", "PAY2", -500, at="2026-11-09T13:00:00Z"),  # newer than the report
        entry("payout", "KT-3", "PAY3", -500, at="2026-11-09T10:00:00Z"),  # covered by the report, not in it
        entry("payout", "KT-4", None, -500, status="NO_ANSWER"),
        entry("payout", "KT-5", "PAY5", -500, status="FAILED"),
    ]
    result = reconcile(entries, [txn("CAP3", "9.00")], refreshed_at=REFRESHED, ledger_started_at=STARTED)
    assert [(r["ref"], r["state"]) for r in result["rows"]] == [
        ("gift-2", "not_paypal"), ("gift-3", "mismatch"), ("KT-2", "waiting"), ("KT-3", "missing"),
        ("KT-4", "waiting"), ("KT-5", "failed")]
    assert result["summary"]["to_check"] == 2 and result["balanced"] is False


def test_paypal_rows_the_ledger_doesnt_know_are_problems_only_after_the_ledger_started():
    report = [txn("OLD", "-7.60", code="T0001", at="2026-11-08T09:00:00Z", custom_field="KT-0142"),
              txn("NEW", "-7.60", code="T0001", at="2026-11-09T09:00:00Z", custom_field="KT-0143"),
              txn("TOPUP", "5000.00", code="T1900", at="2026-11-09T09:30:00Z", transaction_subject="Initial balance")]
    result = reconcile([], report, refreshed_at=REFRESHED, ledger_started_at=STARTED)
    rows = {p["rows"][0]["transaction_id"]: p for p in result["paypal_only"]}
    assert (rows["OLD"]["before_ledger"], rows["OLD"]["attention"]) == (True, False)
    assert (rows["NEW"]["label"], rows["NEW"]["attention"]) == ("Payout for KT-0143", True)
    assert (rows["TOPUP"]["kind"], rows["TOPUP"]["label"], rows["TOPUP"]["attention"]) == ("account", "Initial balance", False)
    assert result["summary"]["to_check"] == 1


def test_split_by_item_walks_gifts_and_lines_in_order():
    from app.ledger import split_by_item

    segments = split_by_item([(1, 5000), (2, 2000), (3, 760)], [("tarp", 3200), ("rice", 2400), ("coat", 2160)])
    assert segments == [(1, "tarp", 3200), (1, "rice", 1800), (2, "rice", 600), (2, "coat", 1400), (3, "coat", 760)]
    assert sum(c for _, _, c in segments) == 7760
