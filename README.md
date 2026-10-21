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
| GET | `/api/requests/{id}` | A spending request with its line verdicts and which gifts would pay for it |
| POST | `/api/requests/{id}/approve` | Allocate gifts oldest-first, then pay the partner through PayPal Payouts |
| POST | `/api/requests/{id}/refresh` | Pull the payout status from PayPal |
| GET | `/api/reconcile` | Match the ledger against PayPal Transaction Search |
| POST | `/api/webhooks/paypal` | Verified PayPal webhooks (captures, payout items) |

## License

MIT
