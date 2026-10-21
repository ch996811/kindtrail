from conftest import PARTNER_EMAIL

FUND = "FUND-HUALIEN-KIDS"


def give(client, cents, donor="Mei L."):
    r = client.post("/api/gifts", json={"fund_code": FUND, "donor_name": donor, "amount_cents": cents})
    assert r.status_code == 201, r.text
    order_id = r.json()["order_id"]
    assert r.json()["approve_url"].endswith(order_id)
    r = client.post(f"/api/gifts/{order_id}/capture")
    assert r.status_code == 200, r.text
    return r.json()


def test_one_gift_one_payout_and_the_ledger_balances(client, fake_paypal):
    gift = give(client, 8000)
    assert gift["status"] == "captured" and gift["paypal_capture_id"] == f"CAP-{gift['paypal_order_id']}"

    before = client.get("/api/requests/KT-0142").json()
    assert before["status"] == "reviewed"
    assert (before["requested_cents"], before["payable_cents"]) == (8640, 7760)  # gift card is blocked
    assert [(f["donor"], f["used_here_cents"]) for f in before["funding"]] == [("Mei L.", 7760)]

    r = client.post("/api/requests/KT-0142/approve", json={"approver": "Lin"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paying"
    [payout] = fake_paypal.payouts
    assert payout["sender_item_id"] == "KT-0142"
    assert payout["receiver_email"] == PARTNER_EMAIL
    assert payout["amount_cents"] == 7760
    assert "gift card" not in payout["note"]

    after = client.post("/api/requests/KT-0142/refresh").json()
    assert after["status"] == "paid"
    assert after["payout"]["fee_cents"] == 15
    assert after["payout"]["transaction_id"] == "TXN-BATCH-1"

    fund = client.get(f"/api/funds/{FUND}").json()
    assert (fund["received_cents"], fund["spent_cents"], fund["available_cents"]) == (8000, 7760, 240)

    fake_paypal.transactions = [
        {"transaction_id": gift["paypal_capture_id"], "transaction_amount": {"value": "80.00"}},
        {"transaction_id": "TXN-BATCH-1", "transaction_amount": {"value": "-77.60"}},
    ]
    rec = client.get("/api/reconcile").json()
    assert rec["balanced"] is True and len(rec["matched"]) == 2


def test_fifo_across_several_donors(client):
    give(client, 5000, "Mei L.")
    give(client, 2000, "Jordan P.")
    give(client, 2500, "Anonymous")
    detail = client.post("/api/requests/KT-0142/approve").json()
    assert [(f["donor"], f["used_here_cents"], f["left_cents"]) for f in detail["funding"]] == [
        ("Mei L.", 5000, 0), ("Jordan P.", 2000, 0), ("Anonymous", 760, 1740)]


def test_cannot_approve_twice(client, fake_paypal):
    give(client, 8000)
    assert client.post("/api/requests/KT-0142/approve").status_code == 200
    r = client.post("/api/requests/KT-0142/approve")
    assert r.status_code == 409
    assert len(fake_paypal.payouts) == 1


def test_not_enough_money_is_refused_without_side_effects(client, fake_paypal):
    give(client, 3000)
    r = client.post("/api/requests/KT-0142/approve")
    assert r.status_code == 409
    assert r.json()["available_cents"] == 3000
    assert fake_paypal.payouts == []
    detail = client.get("/api/requests/KT-0142").json()
    assert detail["status"] == "reviewed" and detail["shortfall_cents"] == 4760


def test_paypal_refusing_the_payout_rolls_the_ledger_back(client, fake_paypal, conn):
    give(client, 8000)
    fake_paypal.fail_payout = True
    r = client.post("/api/requests/KT-0142/approve")
    assert r.status_code == 502
    assert "INSUFFICIENT_FUNDS" in r.json()["message"]
    assert conn.execute("SELECT COUNT(*) FROM allocations").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM payouts").fetchone()[0] == 0
    assert client.get("/api/requests/KT-0142").json()["status"] == "reviewed"


def test_capture_rejects_amount_or_fund_that_does_not_match(client, fake_paypal):
    r = client.post("/api/gifts", json={"fund_code": FUND, "donor_name": "X", "amount_cents": 1000})
    order_id = r.json()["order_id"]
    fake_paypal.capture_override = {"amount": {"currency_code": "USD", "value": "1.00"}}
    assert client.post(f"/api/gifts/{order_id}/capture").status_code == 409
    fake_paypal.capture_override = {"custom_id": "SOME-OTHER-FUND"}
    assert client.post(f"/api/gifts/{order_id}/capture").status_code == 409


def test_unknown_fund_and_request_are_404(client):
    assert client.post("/api/gifts", json={"fund_code": "NOPE", "donor_name": "X", "amount_cents": 100}).status_code == 404
    assert client.get("/api/requests/KT-9999").status_code == 404


def test_webhook_redelivery_is_ignored_and_unverified_events_change_nothing(client, fake_paypal, conn):
    r = client.post("/api/gifts", json={"fund_code": FUND, "donor_name": "W", "amount_cents": 2500})
    order_id = r.json()["order_id"]
    event = {"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED",
             "resource": {"id": "CAP-W", "amount": {"currency_code": "USD", "value": "25.00"},
                          "supplementary_data": {"related_ids": {"order_id": order_id}}}}

    fake_paypal.verify_result = False
    assert client.post("/api/webhooks/paypal", json=event).json()["result"] == "stored-unverified"
    assert conn.execute("SELECT status FROM gifts WHERE paypal_order_id = ?", (order_id,)).fetchone()[0] == "created"

    fake_paypal.verify_result = True
    event2 = {**event, "id": "WH-2"}
    assert client.post("/api/webhooks/paypal", json=event2).json()["result"] == "gift-captured"
    assert client.post("/api/webhooks/paypal", json=event2).json()["result"] == "duplicate"
    assert conn.execute("SELECT status FROM gifts WHERE paypal_order_id = ?", (order_id,)).fetchone()[0] == "captured"
