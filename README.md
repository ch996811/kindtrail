# Kindtrail 善蹤

**Every donated dollar knows where it went.**

Small charities and disaster-relief groups promise donors their gifts will be used a certain way
("only for kids in Hualien"), but checking every spending request by hand is slow and error-prone,
and donors never see what their money bought.

Kindtrail closes that loop:

1. **Donors give** through PayPal Checkout. Each gift is tagged with the fund it belongs to, and
   donors can describe their limits in plain words; AI turns them into structured rules.
2. **Field partners ask for money** with an amount, a purpose and a receipt photo.
3. **AI reviews every request**: it reads the receipt line by line, a deterministic rule engine
   checks each item against the fund's limits, and the reviewer gets a verdict with reasons.
4. **Approved requests are paid** through PayPal Payouts.
5. **Every dollar is traced** back to the individual gifts that funded it, and each donor gets an
   impact receipt: "your $50 bought 4 tarps for the Hualien Mountain Kitchen."

> Status: in active development for the [PayPal AI Hackathon](https://paypalaihackathon.devpost.com/).
> Everything runs against the PayPal **sandbox** with made-up data.

## How the AI review works

The model reads; plain Python decides.

1. **Donor limits.** A donor writes their limits in plain words ("only for kids in Hualien, not for staff
   costs, by the end of the year"). Gemini turns that into a policy: region, allowed and ruled-out
   spending categories, who it is for, and an end date.
2. **Receipt reading.** A partner uploads a receipt photo. Gemini returns every line with its quantity,
   price, a spending category and the line's position on the photo.
3. **Rule engine.** Deterministic code (`backend/app/review.py`) checks each line against the policy:
   allowed or ruled-out category, shop region, purchase date, a resubmitted receipt, and arithmetic that
   doesn't add up. Cash equivalents and alcohol are never paid from restricted gifts.
   Donors see the policy before it is saved, can add or remove uses, and get a live preview of how
   it would judge receipts the AI has already read.
4. **Reviewer.** A person sees the photo with every line boxed green or red, the reason for each
   verdict, and approves the payout.

Models (free tier): `gemini-3.5-flash-lite` with minimal thinking (about 3 s per receipt), falling back
to `gemma-4-31b-it`. Every answer is cached, a daily cap protects the free quota, and
`backend/demo/llm_cache.json` ships the answers for the demo receipts, so the hosted demo works even
with no key (`LLM_PROVIDER=replay`).

## Stack

- Backend: Python, FastAPI, SQLite
- Frontend: React, TypeScript, Vite, Tailwind CSS
- PayPal: Orders v2 (donations), Payouts, Webhooks, Transaction Search
- AI: Gemini (receipt vision, rule extraction, explanations) behind a provider switch, with cached
  replays so the hosted demo keeps working when free quotas run out

## Run it locally

Needs Python 3.10+ and Node 20.19+.

```bash
cp .env.example .env                      # sandbox client id / secret and test account emails
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements-dev.txt   # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m pytest backend/tests
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

`npm run build` writes `frontend/dist`, which the API serves at http://localhost:8000.

To check that a sandbox app has everything Kindtrail needs (orders, payouts, balances,
transaction search), run `python backend/scripts/sandbox_smoke.py`.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/api/gifts` | Create a PayPal order for a gift, tagged with the fund in `custom_id` |
| POST | `/api/gifts/{order_id}/capture` | Capture an approved order and add the gift to the fund |
| GET | `/api/funds/{code}` | Fund balance and every gift's spent / left amounts |
| POST | `/api/limits/parse` | Turn a donor's plain-language limits into a structured policy |
| GET | `/api/limits/categories` | Spending categories, and the ones never paid from restricted gifts |
| POST | `/api/limits/preview` | Judge receipts the AI has already read against a draft policy (no AI calls) |
| GET / POST | `/api/funds` | List funds / open a fund from a donor's words and the checked policy |
| POST | `/api/requests` | Upload a receipt photo; the AI reads it and the rule engine judges every line |
| GET | `/api/requests/{id}/receipt` | The receipt photo |
| GET | `/api/requests/{id}` | A spending request with its line verdicts and which gifts would pay for it |
| POST | `/api/requests/{id}/approve` | Allocate gifts oldest-first, then pay the partner through PayPal Payouts |
| POST | `/api/requests/{id}/refresh` | Pull the payout status from PayPal |
| GET | `/api/reconcile` | Match the ledger against PayPal Transaction Search |
| POST | `/api/webhooks/paypal` | Verified PayPal webhooks (captures, payout items) |

## License

MIT
