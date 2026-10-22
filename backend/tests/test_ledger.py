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


def txn(tid, value, **extra):
    return {"transaction_id": tid, "transaction_amount": {"currency_code": "USD", "value": value},
            "transaction_status": "S", **extra}


def test_reconcile_matches_by_transaction_id_with_signed_amounts():
    gifts = [{"gift_id": 1, "capture_id": "CAP1", "amount_cents": 8000, "fund_code": "F"}]
    payouts = [{"request_id": "KT-1", "transaction_id": "PAY1", "amount_cents": 7760}]
    result = reconcile(gifts, payouts, [txn("CAP1", "80.00"), txn("PAY1", "-77.60")])
    assert result["balanced"] is True
    assert {m["ref"] for m in result["matched"]} == {"gift-1", "KT-1"}
    assert result["paypal_only"] == []


def test_reconcile_flags_lag_mismatch_and_unknown_paypal_rows():
    gifts = [
        {"gift_id": 1, "capture_id": "CAP1", "amount_cents": 8000, "fund_code": "F"},
        {"gift_id": 2, "capture_id": None, "amount_cents": 5000, "fund_code": "F", "source": "seed"},
        {"gift_id": 3, "capture_id": "CAP3", "amount_cents": 1000, "fund_code": "F"},
    ]
    result = reconcile(gifts, [], [txn("CAP1", "80.00"), txn("CAP3", "9.00"), txn("OTHER", "-7.60")])
    assert result["balanced"] is False
    assert [r["ref"] for r in result["ours_only"]] == ["gift-2"]
    assert [(r["ref"], r["paypal_cents"]) for r in result["mismatched"]] == [("gift-3", 900)]
    assert [r["transaction_id"] for r in result["paypal_only"]] == ["OTHER"]


def test_split_by_item_walks_gifts_and_lines_in_order():
    from app.ledger import split_by_item

    segments = split_by_item([(1, 5000), (2, 2000), (3, 760)], [("tarp", 3200), ("rice", 2400), ("coat", 2160)])
    assert segments == [(1, "tarp", 3200), (1, "rice", 1800), (2, "rice", 600), (2, "coat", 1400), (3, "coat", 760)]
    assert sum(c for _, _, c in segments) == 7760
