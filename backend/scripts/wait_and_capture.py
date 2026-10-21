"""Wait for a donor to approve a sandbox order, then capture it through the running API.

Used while there is no checkout page yet: create a gift with POST /api/gifts, open the
approve_url, pay with the sandbox personal account, and this script finishes the capture.

    python backend/scripts/wait_and_capture.py ORDER_ID [--api http://127.0.0.1:8000] [--minutes 40]
"""
import argparse
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import load_settings  # noqa: E402
from app.paypal import PayPalClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("order_id")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--minutes", type=float, default=40)
    args = ap.parse_args()

    s = load_settings()
    pp = PayPalClient(s.paypal_base_url, s.paypal_client_id, s.paypal_client_secret)
    deadline = time.monotonic() + args.minutes * 60
    last = None
    while time.monotonic() < deadline:
        status = pp.get_order(args.order_id).get("status")
        if status != last:
            print(f"order {args.order_id}: {status}", flush=True)
            last = status
        if status == "APPROVED":
            r = httpx.post(f"{args.api}/api/gifts/{args.order_id}/capture", timeout=60)
            print(f"capture -> HTTP {r.status_code}: {r.text}", flush=True)
            return 0 if r.status_code == 200 else 1
        if status == "COMPLETED":
            print("already captured", flush=True)
            return 0
        time.sleep(5)
    print(f"gave up after {args.minutes} minutes; last status {last}", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
