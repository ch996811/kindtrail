import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { captureGift, createGift, getConfig, getFund } from '../api'
import { TopBar } from '../components/TopBar'
import { Trail } from '../components/Trail'
import { usd } from '../model'
import { setUpPayPal, type PayPalButtonSession } from '../paypal'

const DEFAULT_FUND = 'FUND-HUALIEN-KIDS'
const AMOUNTS = [10, 25, 50, 100]

type Status =
  | { name: 'loading' }
  | { name: 'ready' }
  | { name: 'unavailable'; message: string }
  | { name: 'paying' }
  | { name: 'done'; giftId: number; amountCents: number; donor: string; captureId: string }
  | { name: 'error'; message: string }

export function Give() {
  const [params] = useSearchParams()
  const fundCode = params.get('fund') ?? DEFAULT_FUND
  const fund = useQuery({ queryKey: ['fund', fundCode], queryFn: () => getFund(fundCode) })
  const config = useQuery({ queryKey: ['config'], queryFn: getConfig, staleTime: Infinity })
  const [amount, setAmount] = useState(50)
  const [custom, setCustom] = useState('')
  const [donor, setDonor] = useState('')
  const [status, setStatus] = useState<Status>({ name: 'loading' })
  const session = useRef<PayPalButtonSession | null>(null)

  const cents = Math.round((custom ? Number(custom) : amount) * 100)
  const valid = Number.isFinite(cents) && cents >= 100 && cents <= 1_000_000
  // The PayPal callbacks are created once, so they read the latest form values from a ref.
  const latest = useRef({ cents, donor, fundCode })
  latest.current = { cents, donor, fundCode }

  useEffect(() => {
    if (!config.data) return
    if (!config.data.paypal_client_id) {
      setStatus({ name: 'unavailable', message: 'PayPal isn’t configured on this server.' })
      return
    }
    let cancelled = false
    setUpPayPal(config.data.paypal_client_id, {
      onApprove: async (orderId) => {
        try {
          const gift = await captureGift(orderId)
          setStatus({ name: 'done', giftId: gift.id, amountCents: gift.amount_cents, donor: gift.donor_name, captureId: gift.paypal_capture_id })
        } catch (e) {
          setStatus({ name: 'error', message: (e as Error).message })
        }
      },
      onCancel: () => setStatus({ name: 'ready' }),
      onError: (e) => setStatus({ name: 'error', message: e instanceof Error ? e.message : 'PayPal reported an error.' }),
    })
      .then((s) => {
        if (cancelled) return
        session.current = s
        setStatus(s ? { name: 'ready' } : { name: 'unavailable', message: 'PayPal isn’t available for this browser or region.' })
      })
      .catch((e: Error) => !cancelled && setStatus({ name: 'unavailable', message: e.message }))
    return () => {
      cancelled = true
    }
  }, [config.data])

  async function pay() {
    if (!session.current || !valid) return
    setStatus({ name: 'paying' })
    const { cents: c, donor: name, fundCode: code } = latest.current
    const order = createGift({ fund_code: code, donor_name: name.trim() || 'Anonymous', amount_cents: c }).then((g) => ({ orderId: g.order_id }))
    try {
      await session.current.start({ presentationMode: 'auto' }, order)
    } catch (e) {
      setStatus({ name: 'error', message: (e as Error).message })
    }
  }

  const stops = [
    { label: 'Your gift', detail: 'through PayPal' },
    { label: 'Asked', detail: 'by field partners' },
    { label: 'Review', detail: 'against the limits' },
    { label: 'Paid', detail: 'via PayPal' },
    { label: 'Thank-you', detail: 'what it bought' },
  ]

  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar active="Give" />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[22ch] text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">
            Give to the {fund.data?.name ?? 'fund'}
          </h1>
          <p className="mt-2.5 mb-0 max-w-[62ch] text-[17px] text-wine/80">
            Your gift is tagged for this fund inside PayPal. Before any of it is spent, the AI reads the receipt and Kindtrail&rsquo;s rules check
            every line against the fund&rsquo;s limits. You&rsquo;ll get a receipt showing exactly what it bought.
          </p>
          <Trail stops={stops} current={0} />
        </div>
      </header>

      <main className="mx-auto grid max-w-[1160px] items-start gap-[26px] px-6 pt-[30px] pb-16 lg:grid-cols-[7fr_5fr]">
        {status.name === 'done' ? (
          <section className="rounded-[28px] bg-white px-[26px] py-[26px]" role="status">
            <h2 className="font-heading m-0 text-3xl font-bold">
              Thank you{status.donor !== 'Anonymous' ? `, ${status.donor.split(' ')[0]}` : ''}!
            </h2>
            <p className="mt-2 mb-5 text-[16px] text-wine-2">
              Your {usd(status.amountCents / 100)} is in the {fund.data?.name}. PayPal recorded it as capture{' '}
              <code className="rounded bg-blush px-1.5 py-0.5 text-[14px]">{status.captureId}</code>, tagged {fundCode}. It waits there until a
              receipt passes the fund&rsquo;s limits.
            </p>
            <Link to={`/gifts/${status.giftId}`} className="inline-block rounded-[14px] bg-pink px-[18px] py-3 font-bold text-white no-underline hover:bg-pink-hover">
              Track your gift
            </Link>
          </section>
        ) : (
          <section className="rounded-[28px] bg-white px-[26px] py-[24px]">
            <h2 className="font-heading m-0 text-2xl font-bold">How much?</h2>
            <div className="mt-4 flex flex-wrap gap-2.5" role="radiogroup" aria-label="Amount">
              {AMOUNTS.map((a) => (
                <button
                  key={a}
                  type="button"
                  role="radio"
                  aria-checked={!custom && amount === a}
                  onClick={() => {
                    setAmount(a)
                    setCustom('')
                  }}
                  className={`rounded-[14px] px-5 py-3 text-lg font-bold ${!custom && amount === a ? 'bg-wine text-white' : 'bg-blush text-wine hover:bg-petal'}`}
                >
                  ${a}
                </button>
              ))}
              <label className="flex items-center gap-1 rounded-[14px] bg-blush px-4 text-lg font-bold">
                $
                <input
                  aria-label="Other amount"
                  inputMode="decimal"
                  value={custom}
                  onChange={(e) => setCustom(e.target.value.replace(/[^0-9.]/g, ''))}
                  placeholder="Other"
                  className="w-20 bg-transparent py-3 outline-none placeholder:text-wine/40"
                />
              </label>
            </div>
            {!valid && <p className="mt-2 mb-0 text-sm font-medium text-plum">Gifts can be from $1 to $10,000.</p>}

            <label className="mt-6 block">
              <span className="block text-[15px] font-semibold">Name on your receipt</span>
              <input
                value={donor}
                maxLength={80}
                onChange={(e) => setDonor(e.target.value)}
                placeholder="Anonymous"
                className="mt-2 w-full rounded-[14px] border-2 border-blush bg-blush/60 px-4 py-3 text-[16px] outline-none focus:border-pink"
              />
            </label>

            <div className="mt-6">
              <paypal-button type="pay" hidden={status.name !== 'ready' && status.name !== 'error'} onClick={pay} className="block w-full max-w-[420px]" />
              {status.name === 'loading' && <p className="m-0 text-[15px] text-wine-2">Loading PayPal...</p>}
              {status.name === 'paying' && <p className="m-0 text-[15px] text-wine-2" role="status">Waiting for PayPal...</p>}
              {status.name === 'unavailable' && (
                <p className="m-0 text-[15px] font-medium text-plum" role="alert">
                  {status.message}
                </p>
              )}
              {status.name === 'error' && (
                <p className="mt-3 mb-0 text-[15px] font-medium text-plum" role="alert">
                  {status.message}
                </p>
              )}
              <p className="mt-4 mb-0 text-sm text-wine-2">
                This demo runs on PayPal&rsquo;s sandbox: sign in with a sandbox test buyer account. No real money moves.
              </p>
            </div>
          </section>
        )}

        <section className="rounded-[22px] bg-white px-[22px] py-5">
          <h2 className="font-heading m-0 text-xl font-bold">Where your gift can go</h2>
          {fund.data?.donor_words && <p className="mt-2 mb-3 text-[15px] leading-snug text-wine-2">&ldquo;{fund.data.donor_words}&rdquo;</p>}
          <div className="flex flex-wrap gap-2">
            {(fund.data?.rules ?? []).map((r) => (
              <span key={r.kind} className="rounded-full bg-blush px-[13px] py-1.5 text-sm">
                <b className="font-semibold text-pink-deep">{r.kind}</b> {r.value}
              </span>
            ))}
          </div>
          {fund.data && (
            <p className="mt-4 mb-0 text-sm text-wine-2">
              {usd(fund.data.received_cents / 100)} given so far, {usd(fund.data.available_cents / 100)} waiting for receipts that fit.
            </p>
          )}
        </section>
      </main>
    </>
  )
}
