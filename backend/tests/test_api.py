from pathlib import Path

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


# AI review through the API ------------------------------------------------------------------

DEMO = Path(__file__).resolve().parents[1] / "demo" / "receipts"


def upload(client, photo, mime="image/jpeg", purpose="relief supplies"):
    return client.post("/api/requests", data={"fund_code": FUND, "partner_id": "hualien-mountain-kitchen",
                                              "purpose": purpose},
                       files={"receipt": (photo.name, photo.read_bytes(), mime)})


def test_seeded_request_comes_from_the_ai_review_of_the_demo_receipt(client):
    d = client.get("/api/requests/KT-0142").json()
    assert [(i["category"], i["verdict"]) for i in d["items"]] == [
        ("shelter", "fits"), ("food", "fits"), ("children_supplies", "fits"), ("cash_equivalent", "blocked")]
    assert all(len(i["box"]) == 4 for i in d["items"])
    assert d["ai"]["cached"] is True and d["flags"] == []
    assert [r["kind"] for r in d["fund"]["rules"]] == ["Where", "For", "Who", "Never", "Until"]
    photo = client.get(d["receipt_url"])
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"


def test_uploaded_receipt_from_the_wrong_city_is_blocked_with_reasons(client):
    r = upload(client, DEMO / "taipei-corner-store.jpg")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["id"] == "KT-0143" and d["status"] == "reviewed"
    assert d["payable_cents"] == 0 and d["requested_cents"] == 6110
    assert [f["kind"] for f in d["flags"]] == ["region"]
    reasons = {i["category"]: i["reason"] for i in d["items"]}
    assert reasons["alcohol_tobacco"].startswith("Alcohol")
    assert reasons["water"].startswith("Bought in Taipei City")
    assert client.post(f"/api/requests/{d['id']}/approve").status_code == 409  # nothing to pay


def test_the_same_receipt_twice_is_caught(client):
    r = upload(client, DEMO / "hualien-home-mart.jpg")
    d = r.json()
    assert [f["kind"] for f in d["flags"]] == ["duplicate"]
    assert "KT-0142" in d["flags"][0]["message"] and d["payable_cents"] == 0


def test_receipts_without_an_ai_answer_get_a_clear_503(client, tmp_path):
    photo = tmp_path / "new.jpg"
    photo.write_bytes(b"\xff\xd8 not in the cache")
    r = upload(client, photo)
    assert r.status_code == 503 and r.json()["error"] == "ai_unavailable"


def test_only_photos_are_accepted(client, tmp_path):
    doc = tmp_path / "receipt.pdf"
    doc.write_bytes(b"%PDF")
    assert upload(client, doc, mime="application/pdf").status_code == 409


def test_demo_receipts_are_listed_and_served_but_nothing_outside_the_folder(client):
    demos = client.get("/api/demo/receipts").json()
    assert {d["name"] for d in demos} == {"hualien-home-mart", "hualien-family-pharmacy", "taipei-corner-store"}
    assert client.get(demos[0]["url"]).headers["content-type"] == "image/jpeg"
    assert client.get("/api/demo/receipts/..%2F..%2Fapp%2Fconfig.py").status_code == 404
    assert client.get("/api/demo/receipts/nope.jpg").status_code == 404


def test_pages_of_the_single_page_app_fall_back_to_index_html(conn, fake_paypal, llm, tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    settings = Settings(paypal_env="sandbox", paypal_client_id="x", paypal_client_secret="y", paypal_webhook_id="",
                        partner_email=PARTNER_EMAIL, llm_provider="replay", gemini_api_key="", llm_daily_cap=5, demo_mode=False,
                        db_path=":memory:", frontend_dist=str(dist))
    with TestClient(create_app(settings, paypal=fake_paypal, conn=conn, llm=llm)) as c:
        assert c.get("/submit").text == "<div id=root></div>"
        assert c.get("/requests/KT-0142").text == "<div id=root></div>"
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/api/nope").status_code == 404
        assert c.get("/api/health").json()["ok"] is True


# Funds and donor limits ----------------------------------------------------------------------

KIDS_POLICY = {"region": "Hualien County", "allowed": ["shelter", "food", "water", "children_supplies"],
               "never": ["staff_cost"], "beneficiaries": "kids", "until": "2026-12-31"}


def test_categories_list_every_spending_category(client):
    body = client.get("/api/limits/categories").json()
    assert len(body["categories"]) == 14
    assert {"key": "children_supplies", "label": "kids' supplies"} in body["categories"]
    assert body["always_never"] == ["alcohol_tobacco", "cash_equivalent"]


def test_preview_shows_how_a_policy_would_judge_receipts_already_read(client):
    rows = {r["name"]: r for r in client.post("/api/limits/preview", json=KIDS_POLICY).json()}
    assert (rows["hualien-home-mart"]["fits"], rows["hualien-home-mart"]["payable_cents"]) == (3, 7760)
    assert rows["hualien-family-pharmacy"]["fits"] == 2
    assert rows["taipei-corner-store"]["fits"] == 0
    assert rows["taipei-corner-store"]["flags"][0]["kind"] == "region"

    # Same receipts, a Taipei food-and-water fund: now the corner store's water and noodles fit.
    taipei = {"region": "Taipei City", "allowed": ["food", "water"], "never": [], "beneficiaries": None, "until": None}
    rows = {r["name"]: r for r in client.post("/api/limits/preview", json=taipei).json()}
    assert (rows["taipei-corner-store"]["fits"], rows["taipei-corner-store"]["payable_cents"]) == (2, 2630)
    assert rows["hualien-home-mart"]["fits"] == 0


def test_create_and_list_funds(client):
    body = {"name": "Taitung Flood Families", "donor_words": "Food and water for flooded families in Taitung.",
            "policy": {"region": "Taitung County", "allowed": ["food", "water", "cash_equivalent"], "never": []}}
    r = client.post("/api/funds", json=body)
    assert r.status_code == 201, r.text
    fund = r.json()
    assert fund["code"] == "FUND-TAITUNG-FLOOD-FAMILIES"
    assert [c["kind"] for c in fund["rules"]] == ["Where", "For", "Never"]
    assert "cash equivalents" not in fund["rules"][1]["value"]  # stripped from allowed
    assert client.post("/api/funds", json=body).json()["code"] == "FUND-TAITUNG-FLOOD-FAMILIES-2"
    codes = [f["code"] for f in client.get("/api/funds").json()]
    assert codes == ["FUND-HUALIEN-KIDS", "FUND-TAITUNG-FLOOD-FAMILIES", "FUND-TAITUNG-FLOOD-FAMILIES-2"]


def test_a_fund_must_allow_something_and_only_known_categories(client):
    base = {"name": "Empty fund", "donor_words": "nothing at all"}
    assert client.post("/api/funds", json={**base, "policy": {"allowed": []}}).status_code == 409
    assert client.post("/api/funds", json={**base, "policy": {"allowed": ["yachts"]}}).status_code == 422


def test_parse_limits_with_a_live_model(conn, fake_paypal, tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.llm import LLM
    from app.main import create_app

    class Model:
        calls = 0

        def generate_json(self, **_):
            Model.calls += 1
            return {**KIDS_POLICY, "region": "Taitung County"}, "fake-model"

    settings = Settings(paypal_env="sandbox", paypal_client_id="x", paypal_client_secret="y", paypal_webhook_id="",
                        partner_email=PARTNER_EMAIL, llm_provider="gemini", gemini_api_key="k", llm_daily_cap=50, demo_mode=False,
                        db_path=":memory:", frontend_dist=str(tmp_path / "none"))
    with TestClient(create_app(settings, paypal=fake_paypal, conn=conn, llm=LLM(Model()))) as c:
        calls_after_seed = Model.calls
        words = {"donor_words": "Only for kids in Taitung, not staff, by the end of the year."}
        first = c.post("/api/limits/parse", json=words).json()
        again = c.post("/api/limits/parse", json=words).json()
    assert first["policy"]["region"] == "Taitung County" and first["cached"] is False
    assert again["cached"] is True and Model.calls == calls_after_seed + 1
    assert first["rules"][0] == {"kind": "Where", "value": "Taitung County"}


# Donor impact receipts -----------------------------------------------------------------------

def test_impact_receipt_says_what_each_gift_bought(client):
    gifts = [give(client, 5000, "Mei L."), give(client, 2000, "Jordan P."), give(client, 2500, "Anonymous")]
    client.post("/api/requests/KT-0142/approve")
    client.post("/api/requests/KT-0142/refresh")

    mei = client.get(f"/api/gifts/{gifts[0]['id']}/impact").json()
    assert (mei["gift"]["donor"], mei["used_cents"], mei["left_cents"]) == ("Mei L.", 5000, 0)
    [spend] = mei["spends"]
    assert spend["request_id"] == "KT-0142" and spend["status"] == "paid"
    assert spend["payout_transaction_id"] == "TXN-BATCH-1" and spend["paid_at"]
    assert [(i["label"], i["yours_cents"]) for i in spend["items"]] == [
        ("4 Waterproof tarp 3x4m", 3200), ("2 Rice 10 kg", 1800), ("6 Kids raincoat", 0)]
    assert [(d["donor"], d["cents"], d["you"]) for d in spend["donors"]] == [
        ("Mei L.", 5000, True), ("Jordan P.", 2000, False), ("Anonymous", 760, False)]
    assert all(i["box"] for i in spend["items"])
    assert [r["label"] for r in spend["refused"]] == ["1 Prepaid gift card"]

    anon = client.get(f"/api/gifts/{gifts[2]['id']}/impact").json()
    assert (anon["used_cents"], anon["left_cents"]) == (760, 1740)
    assert [(i["key"], i["yours_cents"]) for i in anon["spends"][0]["items"] if i["yours_cents"]] == [("line-3", 760)]


def test_an_unspent_gift_has_no_spends_yet(client):
    gift = give(client, 2500)
    body = client.get(f"/api/gifts/{gift['id']}/impact").json()
    assert body["spends"] == [] and body["left_cents"] == 2500
    assert client.get("/api/gifts/9999/impact").status_code == 404


def test_public_config_exposes_the_client_id_but_never_the_secret(client):
    body = client.get("/api/config").json()
    assert body == {"paypal_client_id": "x", "paypal_env": "sandbox", "demo_mode": False}
    assert "y" not in str(body.values())


def test_demo_reset_is_off_unless_demo_mode(client):
    assert client.post("/api/demo/reset").status_code == 404


def test_demo_mode_seeds_gifts_and_reset_lets_the_demo_run_again(conn, fake_paypal, llm, tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    settings = Settings(paypal_env="sandbox", paypal_client_id="x", paypal_client_secret="y", paypal_webhook_id="",
                        partner_email=PARTNER_EMAIL, llm_provider="replay", gemini_api_key="", llm_daily_cap=5,
                        demo_mode=True, db_path=":memory:", frontend_dist=str(tmp_path / "none"))
    with TestClient(create_app(settings, paypal=fake_paypal, conn=conn, llm=llm)) as c:
        assert c.get(f"/api/funds/{FUND}").json()["available_cents"] == 9500
        assert c.post("/api/requests/KT-0142/approve").json()["status"] == "paying"
        assert c.post("/api/demo/reset").json() == {"ok": True}
        again = c.get("/api/requests/KT-0142").json()
        assert again["status"] == "reviewed" and again["payout"] is None
        assert c.get(f"/api/funds/{FUND}").json()["available_cents"] == 9500
        assert c.post("/api/requests/KT-0142/approve").status_code == 200
