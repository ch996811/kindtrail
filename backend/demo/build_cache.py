"""Run the real model on the demo inputs and save its answers to llm_cache.json.

The hosted demo loads that file at startup, so demo receipts work without a key or quota.
Re-run after changing a prompt or schema in app/review.py (cache keys include both).

    python backend/demo/build_cache.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app import review, seed, service  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.db import connect  # noqa: E402
from app.llm import cache_key, make_llm  # noqa: E402


def main() -> None:
    s = load_settings()
    if not s.gemini_api_key:
        sys.exit("GEMINI_API_KEY is not set")
    llm = make_llm("gemini", s.gemini_api_key, daily_cap=50)
    conn = connect(":memory:")
    seed.load_demo_cache(conn)  # answers whose prompt hasn't changed are reused, not re-asked
    used: set[str] = set()

    parsed = service.parse_limits(conn, llm, seed.DONOR_WORDS, today=seed.FUND_CREATED)
    used.add(cache_key("limits", review.LIMITS_PROMPT.format(today=seed.FUND_CREATED, words=seed.DONOR_WORDS),
                       review.LIMITS_SCHEMA, None))
    print(f"limits ({parsed['model']}): {json.dumps(parsed['policy'])}")
    policy = parsed["policy"]
    for photo in sorted((HERE / "receipts").glob("*.jpg")):
        a = llm.ask(conn, task="receipt", prompt=review.RECEIPT_PROMPT, schema=review.RECEIPT_SCHEMA,
                    image=photo.read_bytes(), mime="image/jpeg")
        used.add(cache_key("receipt", review.RECEIPT_PROMPT, review.RECEIPT_SCHEMA, photo.read_bytes()))
        judged = review.judge(a.data, policy)
        print(f"\n{photo.name} ({a.model}{', cached' if a.cached else ''}): {a.data['shop']} total={a.data['total']}")
        for ln in judged.lines:
            print(f"  {ln.verdict:7} {ln.category:17} {ln.label:28} {ln.line_cents / 100:7.2f}  {ln.reason}")
        for f in judged.flags:
            print(f"  FLAG {f['kind']}: {f['message']}")

    rows = [{"key": r["key"], "task": r["task"], "model": r["model"], "response": json.loads(r["response"])}
            for r in conn.execute("SELECT * FROM llm_cache ORDER BY task, key") if r["key"] in used]
    (HERE / "llm_cache.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {len(rows)} answers to {HERE / 'llm_cache.json'}")


if __name__ == "__main__":
    main()
