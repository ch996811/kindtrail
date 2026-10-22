import { useMutation, useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { createFund, getCategories, parseLimits, previewPolicy, type ParsedLimits, type Policy, type PreviewRow } from '../api'
import { TopBar } from '../components/TopBar'
import { Trail } from '../components/Trail'
import { usd } from '../model'

const EXAMPLES = [
  {
    title: 'Kids in Hualien',
    words: 'Please use my gift only for kids in Hualien who lost their homes in the typhoon. Not for staff costs. Spend it by the end of the year.',
  },
  { title: 'Food in Taitung', words: 'Food and drinking water for flooded families in Taitung. Nothing else, please.' },
  { title: 'Rebuilding homes', words: 'Help families in Hualien rebuild: shelter only, never staff wages, and spend it by March 2027.' },
]
const MODEL_NAMES: Record<string, string> = { 'gemini-3.5-flash-lite': 'Gemini 3.5 Flash Lite', 'gemma-4-31b-it': 'Gemma 4' }
const DEMO_LABELS: Record<string, string> = {
  'hualien-home-mart': 'Home goods store, Hualien',
  'hualien-family-pharmacy': 'Pharmacy, Hualien',
  'taipei-corner-store': 'Corner store, Taipei',
}

export function StartFund() {
  const cats = useQuery({ queryKey: ['categories'], queryFn: getCategories, staleTime: Infinity })
  const [words, setWords] = useState('')
  const [name, setName] = useState('')
  const [parsed, setParsed] = useState<ParsedLimits | null>(null)
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [started, setStarted] = useState(0)

  const parse = useMutation({
    mutationFn: () => parseLimits(words),
    onMutate: () => setStarted(performance.now()),
    onSuccess: (p) => {
      setParsed(p)
      setPolicy(p.policy)
    },
  })
  const settled = useSettled(policy, 300) // don't re-judge on every keystroke
  const preview = useQuery({
    queryKey: ['preview', settled],
    queryFn: () => previewPolicy(settled!),
    enabled: !!settled && settled.allowed.length > 0,
    placeholderData: (prev) => prev,
  })
  const create = useMutation({ mutationFn: () => createFund({ name, donor_words: words, policy: policy! }) })

  const label = (key: string) => cats.data?.categories.find((c) => c.key === key)?.label ?? key
  const alwaysNever = cats.data?.always_never ?? []

  const stops = [
    { label: 'Your gift', detail: 'with your limits' },
    { label: 'Asked', detail: 'by field partners' },
    { label: 'Review', detail: 'against your limits' },
    { label: 'Paid', detail: 'via PayPal' },
    { label: 'Thank-you', detail: 'what it bought' },
  ]

  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar active="Start a fund" />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[20ch] text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">Say how your gift may be used</h1>
          <p className="mt-2.5 mb-0 max-w-[60ch] text-[17px] text-wine/80">
            Write it the way you&rsquo;d tell a friend. The AI turns your words into rules, and every receipt is checked against them before
            any money moves.
          </p>
          <Trail stops={stops} current={0} />
        </div>
      </header>

      <main className="mx-auto grid max-w-[1160px] items-start gap-[26px] px-6 pt-[30px] pb-16 lg:grid-cols-[5fr_7fr] lg:grid-rows-[auto_1fr]">
        <section className="rounded-[28px] bg-white px-[26px] py-[24px] lg:col-start-1 lg:row-start-1">
          <h2 className="font-heading m-0 text-2xl font-bold">In your own words</h2>
          <label htmlFor="words" className="mt-1 block text-[15px] text-wine-2">
            Where should it go, what may it pay for, and until when?
          </label>
          <textarea
            id="words"
            value={words}
            onChange={(e) => setWords(e.target.value)}
            rows={5}
            maxLength={2000}
            placeholder="Only for kids in Hualien who lost their homes..."
            className="mt-3 w-full resize-y rounded-[16px] border-2 border-blush bg-blush/60 px-4 py-3 text-[17px] leading-snug outline-none focus:border-pink"
          />
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-wine-2">Start from an example:</span>
            {EXAMPLES.map((ex) => (
              <button key={ex.title} type="button" onClick={() => setWords(ex.words)} className="rounded-full bg-petal px-3 py-1 font-semibold hover:bg-band">
                {ex.title}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => parse.mutate()}
            disabled={words.trim().length < 3 || parse.isPending}
            className="mt-5 rounded-[14px] bg-pink px-[18px] py-3 font-bold text-white hover:bg-pink-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {parse.isPending ? 'Reading your words...' : parsed ? 'Read my words again' : 'Turn my words into rules'}
          </button>
          {parse.isPending && <Elapsed since={started} />}
          {parse.error && (
            <p role="alert" className="mt-3 mb-0 text-[15px] font-medium text-plum">
              {parse.error.message}
            </p>
          )}
        </section>

        {/* Phones read top to bottom: words, rules and preview, then naming. Desktop puts naming under the words. */}
        <div className="grid gap-[18px] lg:col-start-2 lg:row-span-2 lg:row-start-1">
          {!policy ? (
            <section className="grid min-h-[300px] place-items-center rounded-[28px] border-[2.5px] border-dashed border-wine/20 px-8 text-center">
              <p className="m-0 max-w-[36ch] text-lg text-wine-2">Your rules will appear here, ready for you to check and adjust before anything is saved.</p>
            </section>
          ) : (
            <>
              <RulesCard
                policy={policy}
                onChange={setPolicy}
                parsed={parsed!}
                categories={cats.data?.categories ?? []}
                alwaysNever={alwaysNever}
                label={label}
                locked={!!create.data}
              />
              <PreviewCard rows={preview.data} loading={preview.isFetching} empty={policy.allowed.length === 0} />
            </>
          )}
        </div>

        {policy && (
          <section className="rounded-[28px] bg-white px-[26px] py-[24px] lg:col-start-1 lg:row-start-2">
            {create.data ? (
              <>
                <h2 className="font-heading m-0 text-2xl font-bold">{create.data.name} is open</h2>
                <p className="mt-1 mb-4 text-[15px] text-wine-2">
                  Every PayPal gift to it carries the tag <b className="font-semibold text-wine">{create.data.code}</b>, and every receipt
                  is checked against the rules you set.
                </p>
                <Link
                  to={`/submit?fund=${encodeURIComponent(create.data.code)}`}
                  className="inline-block rounded-[14px] bg-pink px-[18px] py-3 font-bold text-white no-underline hover:bg-pink-hover"
                >
                  Send a receipt to this fund
                </Link>
              </>
            ) : (
              <>
                <h2 className="font-heading m-0 text-2xl font-bold">Name the fund</h2>
                <input
                  aria-label="Fund name"
                  value={name}
                  maxLength={80}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Taitung Flood Families"
                  className="mt-3 w-full rounded-[14px] border-2 border-blush bg-blush/60 px-4 py-3 text-[16px] outline-none focus:border-pink"
                />
                <button
                  type="button"
                  onClick={() => create.mutate()}
                  disabled={name.trim().length < 3 || policy.allowed.length === 0 || create.isPending}
                  className="mt-4 rounded-[14px] bg-wine px-[18px] py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {create.isPending ? 'Creating...' : 'Create the fund'}
                </button>
                {create.error && (
                  <p role="alert" className="mt-3 mb-0 text-[15px] font-medium text-plum">
                    {create.error.message}
                  </p>
                )}
              </>
            )}
          </section>
        )}
      </main>
    </>
  )
}

/** `value`, but only once it has stopped changing for `ms`. */
function useSettled<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const t = window.setTimeout(() => setSettled(value), ms)
    return () => window.clearTimeout(t)
  }, [value, ms])
  return settled
}

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(since)
  useEffect(() => {
    const t = window.setInterval(() => setNow(performance.now()), 100)
    return () => window.clearInterval(t)
  }, [])
  return (
    <span className="ml-3 font-bold text-wine-2 tabular-nums" role="status">
      {((now - since) / 1000).toFixed(1)} s
    </span>
  )
}

function Chip({ text, tone, onRemove, title }: { text: string; tone: 'fits' | 'never' | 'locked'; onRemove?: () => void; title?: string }) {
  const styles = { fits: 'bg-mint-bg text-mint', never: 'bg-plum text-white', locked: 'bg-plum/80 text-white' }
  return (
    <motion.span
      layout
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.8 }}
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full py-1.5 pr-2 pl-3 text-sm font-semibold ${styles[tone]}`}
    >
      {text}
      {onRemove ? (
        <button type="button" onClick={onRemove} aria-label={`Remove ${text}`} className="grid size-5 place-items-center rounded-full hover:bg-black/10">
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <path d="M2 2l6 6m0-6l-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
      ) : (
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className="mr-1 opacity-80">
          <rect x="2.5" y="5.5" width="7" height="5" rx="1" fill="currentColor" />
          <path d="M4 5.5V4a2 2 0 014 0v1.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
        </svg>
      )}
    </motion.span>
  )
}

function RulesCard(props: {
  policy: Policy
  onChange: (p: Policy) => void
  parsed: ParsedLimits
  categories: { key: string; label: string }[]
  alwaysNever: string[]
  label: (k: string) => string
  locked: boolean
}) {
  const { policy, onChange, label, locked } = props
  const set = (patch: Partial<Policy>) => onChange({ ...policy, ...patch })
  const unused = props.categories.filter((c) => !policy.allowed.includes(c.key) && !policy.never.includes(c.key) && !props.alwaysNever.includes(c.key))
  const field = 'w-full rounded-[12px] border-2 border-blush bg-blush/60 px-3 py-2 text-[15px] outline-none focus:border-pink disabled:opacity-70'

  return (
    <section className="rounded-[28px] bg-white px-[26px] py-[24px]">
      <h2 className="font-heading m-0 text-2xl font-bold">The rules Kindtrail will enforce</h2>
      <p className="mt-1 mb-0 text-[15px] text-wine-2">
        {MODEL_NAMES[props.parsed.model] ?? props.parsed.model} read your words
        {props.parsed.cached ? ' (this exact wording was read before, so no AI quota was used)' : ` in ${props.parsed.seconds} s`}. Change
        anything that&rsquo;s not quite right.
      </p>

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-sm font-bold text-pink-deep">Where</span>
          <input className={field} disabled={locked} value={policy.region ?? ''} placeholder="Anywhere" onChange={(e) => set({ region: e.target.value || null })} />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-bold text-pink-deep">Spend by</span>
          <input className={field} disabled={locked} type="date" value={policy.until ?? ''} onChange={(e) => set({ until: e.target.value || null })} />
        </label>
        <label className="block sm:col-span-2">
          <span className="mb-1.5 block text-sm font-bold text-pink-deep">Who it&rsquo;s for</span>
          <input className={field} disabled={locked} value={policy.beneficiaries ?? ''} placeholder="Anyone the fund serves" onChange={(e) => set({ beneficiaries: e.target.value || null })} />
        </label>
      </div>

      <div className="mt-5">
        <span className="mb-2 block text-sm font-bold text-pink-deep">Can pay for</span>
        <div className="flex flex-wrap items-center gap-2">
          <AnimatePresence initial={true}>
            {policy.allowed.map((c) => (
              <Chip key={c} text={label(c)} tone="fits" onRemove={locked ? undefined : () => set({ allowed: policy.allowed.filter((x) => x !== c) })} />
            ))}
          </AnimatePresence>
          {!locked && unused.length > 0 && (
            <select
              aria-label="Add a use"
              value=""
              onChange={(e) => e.target.value && set({ allowed: [...policy.allowed, e.target.value] })}
              className="rounded-full border-2 border-dashed border-mint/50 bg-white px-3 py-1 text-sm font-semibold text-mint"
            >
              <option value="">+ Add a use</option>
              {unused.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          )}
        </div>
        {policy.allowed.length === 0 && <p className="mt-2 mb-0 text-sm font-medium text-plum">Add at least one use, or the fund can&rsquo;t pay for anything.</p>}
      </div>

      <div className="mt-5">
        <span className="mb-2 block text-sm font-bold text-pink-deep">Never pays for</span>
        <div className="flex flex-wrap gap-2">
          <AnimatePresence initial={true}>
            {policy.never.filter((c) => !props.alwaysNever.includes(c)).map((c) => (
              <Chip key={`never-${c}`} text={label(c)} tone="never" onRemove={locked ? undefined : () => set({ never: policy.never.filter((x) => x !== c) })} />
            ))}
            {props.alwaysNever.map((c) => (
              <Chip key={`locked-${c}`} text={label(c)} tone="locked" title="Kindtrail never pays for this from restricted gifts, whatever a donor writes." />
            ))}
          </AnimatePresence>
        </div>
      </div>
    </section>
  )
}

function PreviewCard({ rows, loading, empty }: { rows?: PreviewRow[]; loading: boolean; empty: boolean }) {
  return (
    <section className="rounded-[28px] bg-white px-[26px] py-[24px]" aria-busy={loading}>
      <h2 className="font-heading m-0 text-2xl font-bold">What these rules would do</h2>
      <p className="mt-1 mb-0 text-[15px] text-wine-2">Three receipts the AI has already read, judged by your rules. Change a rule and watch them update.</p>
      {empty ? (
        <p className="mt-4 mb-0 text-[15px] text-wine-2">With nothing allowed, every line would be refused.</p>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {(rows ?? []).map((r) => (
            <article key={r.name} className="overflow-hidden rounded-2xl bg-blush">
              <img src={`/api/demo/receipts/${r.name}.jpg`} alt="" className="block h-24 w-full object-cover object-top" />
              <div className="px-3.5 pt-3 pb-3.5">
                <h3 className="m-0 text-sm font-bold">{DEMO_LABELS[r.name] ?? r.shop}</h3>
                <motion.p
                  key={`${r.fits}-${r.payable_cents}`}
                  initial={{ opacity: 0.2, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`mt-1 mb-0 text-xl font-extrabold ${r.fits === 0 ? 'text-plum' : r.fits === r.lines ? 'text-mint' : 'text-wine'}`}
                >
                  {r.fits} of {r.lines} lines fit
                </motion.p>
                <p className="m-0 text-sm text-wine-2">
                  {usd(r.payable_cents / 100)} of {usd(r.requested_cents / 100)} payable
                </p>
                {r.flags[0] && <p className="mt-2 mb-0 rounded-lg bg-plum px-2 py-1 text-xs font-medium text-white">{r.flags[0].message}</p>}
                {r.blocked.length > 0 && (
                  <ul className="mt-2 mb-0 list-none p-0 text-xs text-wine-2">
                    {r.blocked.filter((b) => b.reason !== r.flags[0]?.message).slice(0, 3).map((b) => (
                      <li key={b.label} className="mt-1">
                        <b className="font-semibold text-wine">{b.label}</b>: {b.reason}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
