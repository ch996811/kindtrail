"""Prepare the local database for a demo run.

    python backend/scripts/seed_demo.py --demo-gifts   # add three made-up captured gifts (source='seed')
    python backend/scripts/seed_demo.py --reset        # put KT-0142 back to 'reviewed' to run the demo again

Seeded gifts never went through PayPal, so /api/reconcile lists them as ours-only.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import load_settings  # noqa: E402
from app.db import connect  # noqa: E402
from app.llm import make_llm  # noqa: E402
from app.seed import reset_request, seed  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo-gifts", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    s = load_settings()
    conn = connect(s.db_path)
    seed(conn, s.partner_email, make_llm(s.llm_provider, s.gemini_api_key, s.llm_daily_cap), demo_gifts=args.demo_gifts)
    if args.reset:
        reset_request(conn)
    gifts = conn.execute("SELECT id, donor_name, amount_cents, status, source FROM gifts ORDER BY id").fetchall()
    for g in gifts:
        print(f"gift {g['id']}: {g['donor_name']} {g['amount_cents'] / 100:.2f} {g['status']} ({g['source']})")
    req = conn.execute("SELECT status FROM requests WHERE id = 'KT-0142'").fetchone()
    print(f"KT-0142: {req['status']}")


if __name__ == "__main__":
    main()
