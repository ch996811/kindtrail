import itertools
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.db import connect  # noqa: E402
from app.llm import LLM, ReplayProvider  # noqa: E402
from app.main import create_app  # noqa: E402
from app.paypal import PayPalError  # noqa: E402

PARTNER_EMAIL = "partner@personal.example.com"


class FakePayPal:
    """Stands in for PayPalClient with the response shapes the sandbox returned on 2026-10-21."""

    def __init__(self):
        self.ids = itertools.count(1)
        self.orders: dict[str, dict] = {}
        self.payouts: list[dict] = []
        self.fail_payout = False
        self.capture_override: dict | None = None
        self.transactions: list[dict] = []
        self.verify_result = True

    def create_donation_order(self, *, fund_code, fund_name, amount_cents, request_id):
        oid = f"ORDER-{next(self.ids)}"
        self.orders[oid] = {"fund_code": fund_code, "amount_cents": amount_cents}
        return {"id": oid, "status": "PAYER_ACTION_REQUIRED",
                "links": [{"rel": "payer-action", "href": f"https://www.sandbox.paypal.com/checkoutnow?token={oid}"}]}

    def capture_order(self, order_id):
        o = self.orders[order_id]
        capture = {"id": f"CAP-{order_id}", "status": "COMPLETED", "custom_id": o["fund_code"],
                   "amount": {"currency_code": "USD", "value": f"{o['amount_cents'] / 100:.2f}"}}
        capture.update(self.capture_override or {})
        return {"id": order_id, "status": "COMPLETED", "purchase_units": [{"payments": {"captures": [capture]}}]}

    def create_payout(self, **kwargs):
        if self.fail_payout:
            raise PayPalError(422, {"name": "INSUFFICIENT_FUNDS", "message": "Sender does not have sufficient funds."})
        self.payouts.append(kwargs)
        return {"batch_header": {"payout_batch_id": f"BATCH-{len(self.payouts)}", "batch_status": "PENDING"}}

    def get_payout_batch(self, payout_batch_id):
        p = self.payouts[int(payout_batch_id.split("-")[1]) - 1]
        return {"batch_header": {"payout_batch_id": payout_batch_id, "batch_status": "SUCCESS",
                                 "fees": {"currency": "USD", "value": "0.15"}},
                "items": [{"transaction_id": f"TXN-{payout_batch_id}", "transaction_status": "SUCCESS",
                           "payout_item_fee": {"currency": "USD", "value": "0.15"},
                           "payout_item": {"sender_item_id": p["sender_item_id"]}}]}

    def search_transactions(self, start, end):
        return self.transactions

    def verify_webhook(self, *, webhook_id, headers, event):
        return self.verify_result


@pytest.fixture
def fake_paypal():
    return FakePayPal()


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def llm():
    # Replay only: the committed demo cache answers the demo receipts; anything else is "AI unavailable".
    return LLM(ReplayProvider(), daily_cap=5)


@pytest.fixture
def client(conn, fake_paypal, llm, tmp_path):
    settings = Settings(paypal_env="sandbox", paypal_client_id="x", paypal_client_secret="y",
                        paypal_webhook_id="WH-TEST", partner_email=PARTNER_EMAIL, llm_provider="replay",
                        gemini_api_key="", llm_daily_cap=5, db_path=":memory:",
                        frontend_dist=str(tmp_path / "no-dist"))
    with TestClient(create_app(settings, paypal=fake_paypal, conn=conn, llm=llm)) as c:
        yield c
