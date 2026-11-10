"""Thin PayPal REST client: Orders v2, Payouts, Transaction Search, webhook verification.

Every call shape here was checked against the sandbox on 2026-10-21
(see backend/scripts/sandbox_smoke.py).
"""
import threading
import time
from datetime import datetime
from typing import Any

import httpx

from .db import to_usd


class PayPalError(Exception):
    def __init__(self, status: int, body: dict[str, Any]):
        self.status = status
        self.body = body
        name = body.get("name") or body.get("error") or "PAYPAL_ERROR"
        message = body.get("message") or body.get("error_description") or ""
        details = body.get("details") or []
        if details and isinstance(details, list):
            first = details[0]
            message = f"{message} ({first.get('issue', '')}: {first.get('description', '')})".strip()
        super().__init__(f"PayPal {status} {name}: {message}")

    @property
    def ambiguous(self) -> bool:
        """True when PayPal may or may not have done what was asked (its own server error, a timeout)."""
        return self.status == 0 or self.status >= 500


class PayPalUnreachable(PayPalError):
    """No answer from PayPal: a timeout or a dropped connection. The request may still have gone through."""

    def __init__(self, error: Exception):
        super().__init__(0, {"name": "NO_ANSWER", "message": f"{type(error).__name__}: {error}"})


def existing_batch_id(err: PayPalError) -> str | None:
    """The batch PayPal already made with this sender_batch_id, from its refusal to make a second one.
    Checked in the sandbox on 2026-11-10: 400 USER_BUSINESS_ERROR, issue "Batch with given sender_batch_id already
    exists", with a link to the first batch."""
    for d in err.body.get("details") or []:
        if d.get("field") == "SENDER_BATCH_ID" and "already exists" in (d.get("issue") or ""):
            for link in d.get("link") or []:
                if link.get("rel") == "self" and "/payouts/" in link.get("href", ""):
                    return link["href"].rstrip("/").rsplit("/", 1)[-1]
    return None


class PayPalClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str, timeout: float = 30.0):
        self._http = httpx.Client(base_url=base_url, timeout=timeout)
        self._auth = (client_id, client_secret)
        self._token = ""
        self._token_expires = 0.0
        self._lock = threading.Lock()

    @property
    def has_credentials(self) -> bool:
        return all(self._auth)

    def warm_up(self) -> None:
        """Fetch the OAuth token early so the first approval doesn't pay for it."""
        self._access_token()

    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._token_expires - 60:
                return self._token
            try:
                r = self._http.post("/v1/oauth2/token", data={"grant_type": "client_credentials"}, auth=self._auth)
            except httpx.TransportError as e:
                raise PayPalUnreachable(e) from e
            if r.status_code >= 400:
                raise PayPalError(r.status_code, _json(r))
            body = r.json()
            self._token = body["access_token"]
            self._token_expires = time.monotonic() + int(body.get("expires_in", 300))
            return self._token

    def _call(self, method: str, path: str, *, json: Any = None, params: dict | None = None,
              request_id: str | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id  # makes retries safe for Orders calls
        try:
            r = self._http.request(method, path, json=json, params=params, headers=headers)
        except httpx.TransportError as e:  # timeouts included
            raise PayPalUnreachable(e) from e
        if r.status_code >= 400:
            raise PayPalError(r.status_code, _json(r))
        return _json(r)

    # Orders v2 -----------------------------------------------------------------------------

    def create_donation_order(self, *, fund_code: str, fund_name: str, amount_cents: int,
                              request_id: str) -> dict[str, Any]:
        value = to_usd(amount_cents)
        return self._call("POST", "/v2/checkout/orders", request_id=request_id, json={
            "intent": "CAPTURE",
            "purchase_units": [{
                "custom_id": fund_code,
                "description": f"Gift to {fund_name}"[:127],
                "amount": {"currency_code": "USD", "value": value,
                           "breakdown": {"item_total": {"currency_code": "USD", "value": value}}},
                # No items.category=DONATION: PayPal only allows it for accounts approved for donations
                # (PERMISSION_DENIED_FOR_DONATION_ITEMS on our sandbox account). custom_id carries the fund.
                "items": [{"name": f"Gift: {fund_name}"[:127], "quantity": "1",
                           "unit_amount": {"currency_code": "USD", "value": value}}],
            }],
            "payment_source": {"paypal": {"experience_context": {
                "brand_name": "Kindtrail", "shipping_preference": "NO_SHIPPING", "user_action": "PAY_NOW",
            }}},
        })

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v2/checkout/orders/{order_id}")

    def capture_order(self, order_id: str) -> dict[str, Any]:
        return self._call("POST", f"/v2/checkout/orders/{order_id}/capture", json={},
                          request_id=f"capture-{order_id}")

    # Payouts -------------------------------------------------------------------------------

    def create_payout(self, *, sender_batch_id: str, sender_item_id: str, receiver_email: str,
                      amount_cents: int, note: str, subject: str) -> dict[str, Any]:
        """Safe to repeat with the same sender_batch_id: PayPal refuses to make a second batch with that id and
        points to the first one, which is returned instead. (PayPal-Request-Id doesn't replay Payouts responses.)"""
        try:
            return self._call("POST", "/v1/payments/payouts", json={
                "sender_batch_header": {"sender_batch_id": sender_batch_id, "email_subject": subject[:255]},
                "items": [{
                    "recipient_type": "EMAIL",
                    "receiver": receiver_email,
                    "amount": {"value": to_usd(amount_cents), "currency": "USD"},
                    "sender_item_id": sender_item_id[:63],
                    "note": note[:4000],
                }],
            })
        except PayPalError as e:
            first = existing_batch_id(e)
            if first is None:
                raise
            return self.get_payout_batch(first)

    def get_payout_batch(self, payout_batch_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/payments/payouts/{payout_batch_id}")

    # Reporting -----------------------------------------------------------------------------

    def search_transactions(self, start: datetime, end: datetime) -> tuple[list[dict[str, Any]], str | None]:
        """All transaction_info records in [start, end], and when PayPal last refreshed the report (it clips
        end_date to that, typically one to three hours ago). PayPal allows at most 31 days per call."""
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            body = self._call("GET", "/v1/reporting/transactions", params={
                "start_date": start.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                "end_date": end.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                "fields": "transaction_info",
                "page_size": 500,
                "page": page,
            })
            out.extend(d["transaction_info"] for d in body.get("transaction_details", []))
            if page >= int(body.get("total_pages", 1) or 1):
                return out, body.get("last_refreshed_datetime")
            page += 1

    # Webhooks ------------------------------------------------------------------------------

    def verify_webhook(self, *, webhook_id: str, headers: dict[str, str], event: dict[str, Any]) -> bool:
        h = {k.lower(): v for k, v in headers.items()}
        body = self._call("POST", "/v1/notifications/verify-webhook-signature", json={
            "auth_algo": h.get("paypal-auth-algo", ""),
            "cert_url": h.get("paypal-cert-url", ""),
            "transmission_id": h.get("paypal-transmission-id", ""),
            "transmission_sig": h.get("paypal-transmission-sig", ""),
            "transmission_time": h.get("paypal-transmission-time", ""),
            "webhook_id": webhook_id,
            "webhook_event": event,
        })
        return body.get("verification_status") == "SUCCESS"


def _json(r: httpx.Response) -> dict[str, Any]:
    if not r.content:
        return {}
    try:
        return r.json()
    except ValueError:
        return {"message": r.text[:500]}


def approve_link(order: dict[str, Any]) -> str | None:
    for link in order.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            return link["href"]
    return None
