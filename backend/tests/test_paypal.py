"""PayPalClient against responses recorded from the sandbox (2026-11-10)."""
import httpx
import pytest

from app.paypal import PayPalClient, PayPalError, PayPalUnreachable, existing_batch_id

DUPLICATE = {"name": "USER_BUSINESS_ERROR", "message": "User business error.", "debug_id": "ca5836265792f",
             "details": [{"field": "SENDER_BATCH_ID", "location": "body",
                          "issue": "Batch with given sender_batch_id already exists",
                          "link": [{"href": "https://api.sandbox.paypal.com/v1/payments/payouts/52KQWX23F4ENS",
                                    "rel": "self", "method": "GET", "encType": "application/json"}]}], "links": []}


def client_with(handler) -> PayPalClient:
    c = PayPalClient("https://api-m.sandbox.paypal.com", "id", "secret")
    c._http = httpx.Client(base_url="https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(handler))
    return c


def token_or(handler):
    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "T", "expires_in": 3600})
        return handler(request)
    return route


def test_existing_batch_id_reads_paypals_refusal():
    assert existing_batch_id(PayPalError(400, DUPLICATE)) == "52KQWX23F4ENS"
    assert existing_batch_id(PayPalError(422, {"name": "INSUFFICIENT_FUNDS"})) is None


def test_create_payout_again_returns_the_batch_paypal_already_made():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(400, json=DUPLICATE)
        return httpx.Response(200, json={"batch_header": {"payout_batch_id": "52KQWX23F4ENS", "batch_status": "SUCCESS"},
                                         "items": []})

    result = client_with(token_or(handler)).create_payout(sender_batch_id="KT-1-x", sender_item_id="KT-1",
                                                          receiver_email="p@example.com", amount_cents=100, note="n", subject="s")
    assert result["batch_header"]["payout_batch_id"] == "52KQWX23F4ENS"
    assert seen == [("POST", "/v1/payments/payouts"), ("GET", "/v1/payments/payouts/52KQWX23F4ENS")]


def test_other_refusals_are_raised_and_timeouts_are_ambiguous():
    refuse = client_with(token_or(lambda r: httpx.Response(422, json={"name": "INSUFFICIENT_FUNDS", "message": "no"})))
    with pytest.raises(PayPalError) as e:
        refuse.create_payout(sender_batch_id="b", sender_item_id="i", receiver_email="e", amount_cents=1, note="n", subject="s")
    assert not e.value.ambiguous

    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(PayPalUnreachable) as e:
        client_with(token_or(slow)).get_payout_batch("B")
    assert e.value.ambiguous and e.value.status == 0
    assert PayPalError(503, {}).ambiguous


def test_search_transactions_returns_when_the_report_was_refreshed():
    body = {"transaction_details": [{"transaction_info": {"transaction_id": "A"}}], "total_pages": 1,
            "last_refreshed_datetime": "2026-11-10T05:59:59Z"}
    from datetime import datetime, timezone
    txns, refreshed = client_with(token_or(lambda r: httpx.Response(200, json=body))).search_transactions(
        datetime(2026, 11, 8, tzinfo=timezone.utc), datetime(2026, 11, 10, tzinfo=timezone.utc))
    assert txns == [{"transaction_id": "A"}] and refreshed == "2026-11-10T05:59:59Z"
