import { useQuery } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { useState } from 'react'
import { useParams } from 'react-router'
import { getGiftImpact, type GiftImpact } from '../api'
import { BoxedPhoto } from '../components/BoxedPhoto'
import { TopBar } from '../components/TopBar'
import { Trail } from '../components/Trail'
import { usd } from '../model'

type Spend = GiftImpact['spends'][number]

/** "Oct 24" from an ISO timestamp or a receipt's "YYYY-MM-DD HH:MM". */
function day(value?: string | null) {
  if (!value) return ''
  return new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const SHARE_TONES = ['bg-sun', 'bg-mint-bg', 'bg-petal', 'bg-blush']

function Tick() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" className="mt-1 flex-none text-mint">
      <path d="M2.5 7.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function ImpactReceipt() {
  const { id = '' } = useParams()
  const q = useQuery({ queryKey: ['impact', id], queryFn: () => getGiftImpact(id) })

  if (q.isPending || q.error) {
    return (
      <header className="rounded-b-[36px] bg-band pb-10">
        <TopBar />
        <p className="mx-auto max-w-[1160px] px-6 pt-6 text-lg" role={q.error ? 'alert' : 'status'}>
          {q.error ? `Couldn't load this gift: ${q.error.message}` : 'Loading your receipt...'}
        </p>
      </header>
    )
  }

  const d = q.data
  const first = d.gift.donor === 'Anonymous' ? null : d.gift.donor.split(' ')[0]
  const spend = d.spends[0]
  const stops = [
    { label: 'Your gift', detail: day(d.gift.given_at) },
    { label: 'Asked', detail: spend ? day(spend.submitted_at) : 'not yet' },
    { label: 'Approved', detail: spend?.approved_by ? `by ${spend.approved_by}` : '' },
    { label: 'Paid', detail: spend?.paid_at ? day(spend.paid_at) : 'via PayPal' },
    { label: 'Thank-you', detail: 'this page' },
  ]

  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[20ch] text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">
            {first ? `${first}, here’s` : 'Here’s'} what your {usd(d.gift.amount_cents / 100)} did
          </h1>
          <p className="mt-2.5 mb-0 max-w-[62ch] text-[17px] text-wine/80">
            {spend
              ? `You gave to the ${d.fund.name} on ${day(d.gift.given_at)}. ${spend.partner} spent it on ${day(spend.shop.printed_at)}, and every line was checked against your limits before PayPal paid a cent.`
              : `You gave to the ${d.fund.name} on ${day(d.gift.given_at)}. Your gift is waiting for the first request that fits your limits.`}
          </p>
          <Trail stops={stops} current={!spend ? 0 : spend.status === 'paid' ? 4 : 3} />
        </div>
      </header>

      <main className="mx-auto max-w-[1160px] px-6 pt-[30px] pb-16">
        {d.spends.map((s) => (
          <SpendView key={s.request_id} spend={s} />
        ))}

        <section className="mt-[26px] grid gap-[18px] lg:grid-cols-[7fr_5fr]">
          <div className="rounded-[22px] bg-white px-[22px] py-5">
            <h2 className="font-heading m-0 text-xl font-bold">Your limits</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {d.fund.rules.map((r) => (
                <span key={r.kind} className="rounded-full bg-blush px-[13px] py-1.5 text-sm">
                  <b className="font-semibold text-pink-deep">{r.kind}</b> {r.value}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-[22px] bg-wine px-[22px] py-5 text-white">
            <h2 className="font-heading m-0 text-xl font-bold">
              {d.left_cents > 0 ? `${usd(d.left_cents / 100)} is still waiting` : 'Every dollar is accounted for'}
            </h2>
            <p className="mt-1 mb-0 text-[15px] text-white/80">
              {d.left_cents > 0
                ? 'It stays in the fund until a request fits your limits, and you’ll get another receipt when it’s spent.'
                : `All ${usd(d.gift.amount_cents / 100)} of your gift went to purchases that matched your limits.`}
            </p>
          </div>
        </section>

        {d.gift.source === 'seed' && (
          <p className="mt-6 mb-0 text-center text-sm text-wine-2">
            Demo gift: made up for this sandbox demo, so it never went through PayPal. The payout above is a real PayPal sandbox payout.
          </p>
        )}
      </main>
    </>
  )
}

function SpendView({ spend }: { spend: Spend }) {
  const [active, setActive] = useState<string | null>(null)
  const mine = spend.items.filter((i) => i.yours_cents > 0)
  const others = spend.items.filter((i) => i.yours_cents === 0)
  const photoItems = spend.items.map((i) => ({
    id: i.key,
    receiptText: i.label,
    label: i.label,
    qty: 1,
    unitPrice: i.total_cents / 100,
    verdict: 'fits' as const,
    reason: '',
    box: i.box ?? undefined,
  }))
  let tone = 0

  return (
    <div className="grid items-start gap-[26px] lg:grid-cols-[5fr_7fr]">
      <figure className="m-0 rounded-[28px] bg-petal px-[22px] pt-7 pb-5 lg:sticky lg:top-6">
        {spend.receipt_url && (
          <BoxedPhoto
            src={spend.receipt_url}
            alt={`Receipt from ${spend.shop.name}`}
            items={photoItems}
            activeItem={active}
            onActivate={setActive}
            highlight={new Set(mine.map((i) => i.key))}
            delay={0.9}
          />
        )}
        <figcaption className="mt-4 text-center text-sm text-wine-2">
          {spend.shop.name}, {spend.shop.branch}. The green boxes are what your money paid for.
        </figcaption>
      </figure>

      <div className="grid gap-[18px]">
        <section className="rounded-[28px] bg-white px-[26px] py-[24px]">
          <h2 className="font-heading m-0 text-2xl font-bold">Your {usd(spend.your_cents / 100)} paid for</h2>
          <ul className="m-0 mt-4 grid list-none gap-4 p-0">
            {mine.map((i, n) => (
              <motion.li
                key={i.key}
                onMouseEnter={() => setActive(i.key)}
                onMouseLeave={() => setActive(null)}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 1.2 + n * 0.15 }}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-lg font-bold">{i.label}</span>
                  <span className="font-bold tabular-nums">{usd(i.yours_cents / 100)}</span>
                </div>
                <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-blush" aria-hidden="true">
                  <motion.i
                    className="block h-full rounded-full bg-pink"
                    initial={{ width: 0 }}
                    animate={{ width: `${(i.yours_cents / i.total_cents) * 100}%` }}
                    transition={{ delay: 1.3 + n * 0.15, duration: 0.6, ease: 'easeOut' }}
                  />
                </div>
                <div className="mt-1 text-sm text-wine-2">
                  {i.yours_cents === i.total_cents ? 'The whole line, paid by you' : `${usd(i.yours_cents / 100)} of the ${usd(i.total_cents / 100)} line; other donors covered the rest`}
                </div>
              </motion.li>
            ))}
          </ul>
          {others.length > 0 && (
            <p className="mt-4 mb-0 text-[15px] text-wine-2">
              Other donors covered {others.map((i) => i.label.toLowerCase()).join(', ')}.
            </p>
          )}
        </section>

        <section className="rounded-[22px] bg-white px-[22px] py-5">
          <h2 className="font-heading m-0 text-xl font-bold">
            Shared with {spend.donors.length - 1} other {spend.donors.length - 1 === 1 ? 'donor' : 'donors'}
          </h2>
          <div className="mt-3 flex h-4 overflow-hidden rounded-full" aria-hidden="true">
            {spend.donors.map((dn) => (
              <i
                key={dn.donor + dn.cents}
                className={dn.you ? 'bg-pink-deep' : SHARE_TONES[tone++ % SHARE_TONES.length]}
                style={{ width: `${(dn.cents / spend.payable_cents) * 100}%` }}
              />
            ))}
          </div>
          <ul className="m-0 mt-3 flex list-none flex-wrap gap-x-5 gap-y-1 p-0 text-sm">
            {spend.donors.map((dn) => (
              <li key={dn.donor + dn.cents} className={dn.you ? 'font-bold text-pink-deep' : 'text-wine-2'}>
                {dn.you ? 'You' : dn.donor} {usd(dn.cents / 100)}
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-[22px] bg-white px-[22px] py-5">
          <h2 className="font-heading m-0 text-xl font-bold">Checked, approved, paid</h2>
          <ul className="m-0 mt-3 grid list-none gap-2.5 p-0 text-[15px]">
            <li className="flex gap-2.5">
              <Tick />
              <span>
                The AI read the receipt from {spend.shop.name} and Kindtrail&rsquo;s rules checked every line against your limits.
              </span>
            </li>
            {spend.refused.map((r) => (
              <li key={r.label} className="flex gap-2.5">
                <Tick />
                <span>
                  {r.label} ({usd(r.total_cents / 100)}) broke the limits, so none of your money paid for it.
                </span>
              </li>
            ))}
            {spend.approved_by && (
              <li className="flex gap-2.5">
                <Tick />
                <span>
                  {spend.approved_by} at the charity approved the payout on {day(spend.approved_at)}.
                </span>
              </li>
            )}
            <li className="flex gap-2.5">
              <Tick />
              <span>
                {spend.paid_at
                  ? `PayPal sent ${usd(spend.payable_cents / 100)} to ${spend.partner} on ${day(spend.paid_at)}.`
                  : `PayPal is sending ${usd(spend.payable_cents / 100)} to ${spend.partner} now.`}
                {spend.payout_transaction_id && (
                  <>
                    {' '}
                    Transaction <code className="rounded bg-blush px-1.5 py-0.5 text-[13px]">{spend.payout_transaction_id}</code>
                  </>
                )}
              </span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  )
}
