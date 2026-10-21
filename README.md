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

## Try the sandbox probe

```bash
cp .env.example .env   # fill in sandbox client id / secret and test account emails
python backend/scripts/sandbox_smoke.py
```

## License

MIT
