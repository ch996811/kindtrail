import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ApiError, getFund, listDemoReceipts, submitReceipt, toReviewModel, type RequestDetail } from '../api'
import { BoxedPhoto } from '../components/BoxedPhoto'
import { ReviewPanel } from '../components/ReviewPanel'
import { TopBar } from '../components/TopBar'
import { Trail } from '../components/Trail'

// The demo is signed in as one field partner; the fund comes from ?fund= (default: the Hualien kids fund).
const DEFAULT_FUND = 'FUND-HUALIEN-KIDS'
const PARTNER = { id: 'hualien-mountain-kitchen', name: 'Hualien Mountain Kitchen' }
const MAX_BYTES = 6 * 1024 * 1024
const TYPES = ['image/jpeg', 'image/png', 'image/webp']
const DEMO_LABELS: Record<string, string> = {
  'hualien-home-mart': 'Home goods store, Hualien',
  'hualien-family-pharmacy': 'Pharmacy, Hualien',
  'taipei-corner-store': 'Corner store, Taipei',
}

type Phase = { name: 'choose' } | { name: 'reading'; started: number } | { name: 'done'; result: RequestDetail } | { name: 'error'; message: string; quota: boolean }

export function SubmitReceipt() {
  const qc = useQueryClient()
  const [params] = useSearchParams()
  const fundCode = params.get('fund') ?? DEFAULT_FUND
  const fund = useQuery({ queryKey: ['fund', fundCode], queryFn: () => getFund(fundCode) })
  const demos = useQuery({ queryKey: ['demo-receipts'], queryFn: listDemoReceipts })
  const [photo, setPhoto] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [purpose, setPurpose] = useState('relief supplies')
  const [phase, setPhase] = useState<Phase>({ name: 'choose' })
  const [activeItem, setActiveItem] = useState<string | null>(null)
  const [pickError, setPickError] = useState<string | null>(null)

  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview])

  function choose(file: File) {
    if (!TYPES.includes(file.type)) return setPickError('Please choose a JPEG, PNG or WebP photo.')
    if (file.size > MAX_BYTES) return setPickError('That photo is over 6 MB. Try a smaller one.')
    setPickError(null)
    setPhoto(file)
    setPreview(URL.createObjectURL(file))
    setPhase({ name: 'choose' })
  }

  async function chooseDemo(url: string, name: string) {
    const blob = await (await fetch(url)).blob()
    choose(new File([blob], `${name}.jpg`, { type: 'image/jpeg' }))
  }

  async function send() {
    if (!photo) return
    setPhase({ name: 'reading', started: performance.now() })
    try {
      const result = await submitReceipt({ fundCode, partnerId: PARTNER.id, purpose, photo })
      qc.setQueryData(['request', result.id], result) // the review desk opens instantly
      setPhase({ name: 'done', result })
    } catch (e) {
      const err = e as ApiError
      setPhase({ name: 'error', message: err.message, quota: err.status === 503 })
    }
  }

  function reset() {
    setPhoto(null)
    setPreview(null)
    setPhase({ name: 'choose' })
  }

  const done = phase.name === 'done' ? phase.result : null
  const model = done ? toReviewModel(done) : null
  const stops = [
    { label: 'Gifts in', detail: fund.data ? `${fund.data.gifts.length} donors` : '' },
    { label: 'Your receipt', detail: 'today' },
    { label: 'Review', detail: 'by the charity' },
    { label: 'Paid', detail: 'via PayPal' },
    { label: 'Thank-you', detail: 'to each donor' },
  ]

  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar active="Send a receipt" />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[22ch] text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">
            Send a receipt to the {fund.data?.name ?? 'fund'}
          </h1>
          <p className="mt-2.5 mb-0 max-w-[60ch] text-[17px] text-wine/80">
            You&rsquo;re signed in as {PARTNER.name}. The AI reads every line of your receipt and checks it against what donors asked
            for. A person at the charity approves the payout.
          </p>
          <Trail stops={stops} current={done ? 2 : 1} />
        </div>
      </header>

      <main className="mx-auto grid max-w-[1160px] items-start gap-[26px] px-6 pt-[30px] pb-16 lg:grid-cols-[5fr_7fr]">
        <section className="rounded-[28px] bg-petal px-[22px] pt-7 pb-5 lg:sticky lg:top-6" aria-label="Receipt photo">
          {!preview ? (
            <Dropzone onPick={choose} />
          ) : done && model ? (
            <BoxedPhoto src={preview} alt="Your receipt" items={model.items} activeItem={activeItem} onActivate={setActiveItem} delay={0.15} />
          ) : (
            <Scanning src={preview} reading={phase.name === 'reading'} />
          )}
          {pickError && (
            <p role="alert" className="mt-3 mb-0 text-center text-[15px] font-medium text-plum">
              {pickError}
            </p>
          )}
          {preview && phase.name !== 'reading' && !done && (
            <button type="button" onClick={reset} className="mx-auto mt-4 block text-sm font-semibold text-wine-2 underline underline-offset-4">
              Choose a different photo
            </button>
          )}
        </section>

        <div className="grid gap-[18px]">
          {phase.name === 'choose' && (
            <ChooseCard
              purpose={purpose}
              onPurpose={setPurpose}
              canSend={!!photo && purpose.trim().length > 0}
              onSend={send}
              demos={demos.data ?? []}
              onDemo={chooseDemo}
              rules={fund.data?.rules ?? []}
            />
          )}
          {phase.name === 'reading' && <ReadingCard started={phase.started} />}
          {phase.name === 'error' && <ErrorCard message={phase.message} quota={phase.quota} onRetry={send} onReset={reset} />}
          {done && model && (
            <>
              <section className="rounded-[28px] bg-white px-[26px] py-[22px]">
                <h2 className="font-heading m-0 text-2xl font-bold">Sent to the charity as {done.id}</h2>
                <p className="mt-1 mb-4 text-[15px] text-wine-2">
                  {done.ai?.cached
                    ? 'This demo receipt was read earlier, so its answer came from the cache and used no AI quota.'
                    : `The AI read it in ${done.ai?.seconds ?? '?'} seconds.`}{' '}
                  A reviewer will see the same verdicts and decide.
                </p>
                <div className="flex flex-wrap gap-2.5">
                  <Link to={`/requests/${done.id}`} className="rounded-[14px] bg-pink px-[18px] py-3 font-bold text-white no-underline hover:bg-pink-hover">
                    Open on the review desk
                  </Link>
                  <button type="button" onClick={reset} className="rounded-[14px] bg-blush px-[18px] py-3 font-bold text-wine">
                    Send another receipt
                  </button>
                </div>
              </section>
              <ReviewPanel request={model} activeItem={activeItem} onActivate={setActiveItem} revealDelay={0.3} />
            </>
          )}
        </div>
      </main>
    </>
  )
}

function Dropzone({ onPick }: { onPick: (f: File) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setOver(false)
    const f = e.dataTransfer.files[0]
    if (f) onPick(f)
  }
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`grid min-h-[380px] place-items-center rounded-2xl border-[2.5px] border-dashed px-6 text-center transition-colors ${
        over ? 'border-pink bg-white' : 'border-wine/25 bg-white/50'
      }`}
    >
      <div>
        <svg width="56" height="56" viewBox="0 0 56 56" aria-hidden="true" className="mx-auto">
          <rect x="14" y="6" width="28" height="40" rx="3" className="fill-white stroke-wine" strokeWidth="2.5" />
          <path d="M20 16h16M20 22h12M20 28h16M20 34h9" className="stroke-wine/50" strokeWidth="2.5" strokeLinecap="round" />
          <circle cx="40" cy="42" r="10" className="fill-pink" />
          <path d="M40 37v10M35 42h10" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
        <p className="mt-4 mb-1 text-lg font-bold">Drop a photo of the receipt here</p>
        <p className="m-0 text-[15px] text-wine-2">JPEG, PNG or WebP, up to 6 MB</p>
        <button
          type="button"
          onClick={() => input.current?.click()}
          className="mt-5 rounded-[14px] bg-wine px-[18px] py-3 font-bold text-white"
        >
          Choose a photo
        </button>
        <input
          ref={input}
          type="file"
          accept={TYPES.join(',')}
          capture="environment"
          className="sr-only"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            const f = e.target.files?.[0]
            if (f) onPick(f)
            e.target.value = ''
          }}
        />
      </div>
    </div>
  )
}

/** The photo while the AI reads it: a soft pink band sweeps down the receipt. */
function Scanning({ src, reading }: { src: string; reading: boolean }) {
  return (
    <div className="relative mx-auto w-full max-w-[400px] overflow-hidden rounded-xl shadow-[0_18px_30px_-20px_rgb(58_11_37/0.55)]">
      <img src={src} alt="Your receipt" className="block w-full" />
      {reading && (
        <>
          <div className="absolute inset-0 bg-wine/10" />
          <motion.div
            aria-hidden="true"
            className="absolute inset-x-0 top-0 h-[12%] bg-gradient-to-b from-transparent via-pink/45 to-transparent"
            initial={{ y: '-100%' }}
            animate={{ y: '850%' }}
            transition={{ duration: 1.6, repeat: Infinity, ease: 'linear' }}
          />
        </>
      )}
    </div>
  )
}

function ChooseCard(props: {
  purpose: string
  onPurpose: (v: string) => void
  canSend: boolean
  onSend: () => void
  demos: { name: string; url: string }[]
  onDemo: (url: string, name: string) => void
  rules: { kind: string; value: string }[]
}) {
  return (
    <>
      <section className="rounded-[28px] bg-white px-[26px] py-[24px]">
        <h2 className="font-heading m-0 text-2xl font-bold">What did you buy it for?</h2>
        <label htmlFor="purpose" className="mt-1 block text-[15px] text-wine-2">
          A few words for the reviewer
        </label>
        <input
          id="purpose"
          value={props.purpose}
          maxLength={120}
          onChange={(e) => props.onPurpose(e.target.value)}
          className="mt-3 w-full rounded-[14px] border-2 border-blush bg-blush/60 px-4 py-3 text-[16px] outline-none focus:border-pink"
        />
        <button
          type="button"
          disabled={!props.canSend}
          onClick={props.onSend}
          className="mt-4 rounded-[14px] bg-pink px-[18px] py-3 font-bold text-white hover:bg-pink-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          Check this receipt
        </button>
        {!props.canSend && <p className="mt-2 mb-0 text-sm text-wine-2">Add a photo first, or try one of the demo receipts below.</p>}
      </section>

      <section className="rounded-[22px] bg-white px-[22px] py-5">
        <h2 className="font-heading m-0 text-xl font-bold">No receipt handy? Try one of ours</h2>
        <div className="mt-3 grid grid-cols-3 gap-3 max-sm:grid-cols-1">
          {props.demos.map((d) => (
            <button
              key={d.name}
              type="button"
              onClick={() => props.onDemo(d.url, d.name)}
              className="group overflow-hidden rounded-2xl bg-blush text-left focus-visible:outline-3"
            >
              <img src={d.url} alt="" className="block h-28 w-full object-cover object-top transition-transform group-hover:scale-105" />
              <span className="block px-3 py-2 text-sm font-semibold">{DEMO_LABELS[d.name] ?? d.name}</span>
            </button>
          ))}
        </div>
      </section>

      {props.rules.length > 0 && (
        <section className="rounded-[22px] bg-white px-[22px] py-5">
          <h2 className="font-heading m-0 text-xl font-bold">What donors allow</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {props.rules.map((r) => (
              <span key={r.kind} className="rounded-full bg-blush px-[13px] py-1.5 text-sm">
                <b className="font-semibold text-pink-deep">{r.kind}</b> {r.value}
              </span>
            ))}
          </div>
        </section>
      )}
    </>
  )
}

function ReadingCard({ started }: { started: number }) {
  const [now, setNow] = useState(started)
  useEffect(() => {
    const t = window.setInterval(() => setNow(performance.now()), 100)
    return () => window.clearInterval(t)
  }, [])
  return (
    <section className="rounded-[28px] bg-white px-[26px] py-[24px]" role="status" aria-live="polite">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="font-heading m-0 text-2xl font-bold">Reading your receipt</h2>
        <span className="font-bold text-wine-2 tabular-nums">{((now - started) / 1000).toFixed(1)} s</span>
      </div>
      <p className="mt-2 mb-0 text-[15px] text-wine-2">
        The AI lists every line and sorts it into a spending category. Then Kindtrail&rsquo;s rules check each one against what donors
        asked for. This usually takes a few seconds.
      </p>
    </section>
  )
}

function ErrorCard({ message, quota, onRetry, onReset }: { message: string; quota: boolean; onRetry: () => void; onReset: () => void }) {
  return (
    <section className="rounded-[28px] bg-white px-[26px] py-[24px]" role="alert">
      <h2 className="font-heading m-0 text-2xl font-bold">{quota ? 'The AI is resting for today' : 'That didn’t work'}</h2>
      <p className="mt-2 mb-4 text-[15px] text-wine-2">
        {quota ? 'Kindtrail runs on a free AI quota and today’s is used up. The demo receipts still work.' : message}
      </p>
      <div className="flex flex-wrap gap-2.5">
        {!quota && (
          <button type="button" onClick={onRetry} className="rounded-[14px] bg-pink px-[18px] py-3 font-bold text-white">
            Try again
          </button>
        )}
        <button type="button" onClick={onReset} className="rounded-[14px] bg-blush px-[18px] py-3 font-bold text-wine">
          {quota ? 'Pick a demo receipt' : 'Choose a different photo'}
        </button>
      </div>
    </section>
  )
}
