"""Day-1 probe: can this sandbox app do everything Kindtrail needs?

Checks, in order: OAuth token, a DONATION order tagged with a fund code,
a Payouts batch to the sandbox personal account, balances, transaction search.
Stdlib only so it runs before any dependencies are installed.

    python backend/scripts/sandbox_smoke.py            # all checks
    python backend/scripts/sandbox_smoke.py --no-payout
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = "https://api-m.sandbox.paypal.com"


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def call(method, path, token=None, body=None, form=None, basic=None):
    headers = {"Accept": "application/json"}
    data = None
    if basic:
        headers["Authorization"] = "Basic " + base64.b64encode(basic.encode()).decode()
    if token:
        headers["Authorization"] = "Bearer " + token
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:500].decode("utf-8", "replace")}


def show(label, status, payload, keys=None):
    ok = 200 <= status < 300
    print("[%s] %s -> HTTP %s" % ("OK" if ok else "FAIL", label, status))
    if keys and ok:
        for k in keys:
            print("     %s: %s" % (k, payload.get(k)))
    if not ok:
        print("     " + json.dumps(payload)[:800])
    return ok


def main():
    env = load_env(os.path.join(ROOT, ".env"))
    do_payout = "--no-payout" not in sys.argv

    st, tok = call("POST", "/v1/oauth2/token", form={"grant_type": "client_credentials"},
                   basic=env["PAYPAL_CLIENT_ID"] + ":" + env["PAYPAL_CLIENT_SECRET"])
    if not show("oauth token", st, tok, ["app_id", "expires_in"]):
        return 1
    token = tok["access_token"]
    scopes = tok.get("scope", "")
    for s in ("payouts", "reporting", "checkout"):
        hits = [x for x in scopes.split() if s in x]
        print("     scope '%s': %s" % (s, ", ".join(x.rsplit("/", 1)[-1] for x in hits) or "MISSING"))

    order = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": "gift-smoke",
            "custom_id": "FUND-HUALIEN-KIDS",
            "description": "Gift to Hualien Kids Typhoon Fund",
            "amount": {"currency_code": "USD", "value": "50.00",
                       "breakdown": {"item_total": {"currency_code": "USD", "value": "50.00"}}},
            "items": [{"name": "Gift: Hualien Kids Typhoon Fund", "quantity": "1",
                       "unit_amount": {"currency_code": "USD", "value": "50.00"},
                       "category": "DONATION"}],
        }],
    }
    st, o = call("POST", "/v2/checkout/orders", token, body=order)
    if show("create DONATION order", st, o, ["id", "status"]):
        approve = [l["href"] for l in o.get("links", []) if l.get("rel") in ("approve", "payer-action")]
        print("     approve link: %s" % (approve[0] if approve else None))
        st, g = call("GET", "/v2/checkout/orders/" + o["id"], token)
        pu = (g.get("purchase_units") or [{}])[0]
        print("     read back custom_id=%s item category=%s" % (
            pu.get("custom_id"), (pu.get("items") or [{}])[0].get("category")))

    if do_payout:
        batch_id = "kt-smoke-%d" % int(time.time())
        payout = {
            "sender_batch_header": {"sender_batch_id": batch_id,
                                    "email_subject": "Kindtrail payout for request KT-0142"},
            "items": [{"recipient_type": "EMAIL",
                       "amount": {"value": "7.60", "currency": "USD"},
                       "receiver": env["PAYPAL_SANDBOX_PERSONAL_EMAIL"],
                       "note": "Hualien Kids Typhoon Fund: tarps, rice, kids raincoats",
                       "sender_item_id": "KT-0142"}],
        }
        st, p = call("POST", "/v1/payments/payouts", token, body=payout)
        if show("create payout batch", st, p):
            hdr = p.get("batch_header", {})
            pid = hdr.get("payout_batch_id")
            print("     payout_batch_id=%s status=%s" % (pid, hdr.get("batch_status")))
            time.sleep(4)
            st, b = call("GET", "/v1/payments/payouts/" + pid, token)
            if show("read payout batch", st, b):
                print("     batch_status=%s" % b.get("batch_header", {}).get("batch_status"))
                for it in b.get("items", []):
                    print("     item %s: %s %s" % (it.get("payout_item", {}).get("sender_item_id"),
                                                  it.get("transaction_status"),
                                                  json.dumps(it.get("errors"))[:300] if it.get("errors") else ""))

    st, bal = call("GET", "/v1/reporting/balances", token)
    if show("balances", st, bal):
        for b in bal.get("balances", []):
            print("     %s total=%s available=%s" % (b.get("currency"), b.get("total_balance", {}).get("value"),
                                                    b.get("available_balance", {}).get("value")))

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    q = urllib.parse.urlencode({"start_date": start.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                                "end_date": end.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                                "fields": "transaction_info"})
    st, tx = call("GET", "/v1/reporting/transactions?" + q, token)
    if show("transaction search (30d)", st, tx):
        print("     transactions found: %s" % len(tx.get("transaction_details", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
