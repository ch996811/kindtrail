import { motion } from 'motion/react'
import { lineTotal, usd, type ReviewRequest } from '../model'

function Check() {
  return (
    <svg width="16" height="16" viewBox="0 0 14 14" aria-hidden="true">
      <path d="M2.5 7.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Cross() {
  return (
    <svg width="16" height="16" viewBox="0 0 14 14" aria-hidden="true">
      <path d="M3.5 3.5l7 7m0-7l-7 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}

function Ring({ fits, total, delay }: { fits: number; total: number; delay: number }) {
  const c = 2 * Math.PI * 30
  return (
    <svg className="size-[74px] flex-none" viewBox="0 0 74 74" aria-hidden="true">
      <circle cx="37" cy="37" r="30" fill="none" className="stroke-blush" strokeWidth="10" />
      <motion.circle
        cx="37"
        cy="37"
        r="30"
        fill="none"
        className="stroke-mint"
        strokeWidth="10"
        strokeLinecap="round"
        transform="rotate(-90 37 37)"
        strokeDasharray={c}
        initial={{ strokeDashoffset: c }}
        animate={{ strokeDashoffset: c * (1 - fits / total) }}
        transition={{ delay: Math.max(0, delay), duration: 0.8, ease: 'easeOut' }}
      />
      <text x="37" y="43" textAnchor="middle" className="fill-wine text-lg font-extrabold">
        {fits}/{total}
      </text>
    </svg>
  )
}

const MODEL_NAMES: Record<string, string> = {
  'gemini-3.5-flash-lite': 'Gemini 3.5 Flash Lite',
  'gemma-4-31b-it': 'Gemma 4',
}

function headline(fits: number, blocked: { label: string }[]) {
  const total = fits + blocked.length
  if (blocked.length === 0) return 'Every item fits the fund.'
  if (fits === 0) return "Nothing on this receipt can be paid from donors' money."
  const what = blocked.length === 1 ? `The ${blocked[0].label.replace(/^\d+ /, '').toLowerCase()} can't` : `${blocked.length} items can't`
  return `${fits} of ${total} items fit. ${what} be covered by donors' money.`
}

interface Props {
  request: ReviewRequest
  activeItem: string | null
  onActivate: (id: string | null) => void
  revealDelay?: number // seconds before the verdict rows start appearing
}

/** The AI's verdict: one row per receipt line, revealed in order. */
export function ReviewPanel({ request, activeItem, onActivate, revealDelay = 1.9 }: Props) {
  const fits = request.items.filter((it) => it.verdict === 'fits')
  const requested = request.items.reduce((s, it) => s + lineTotal(it), 0)
  const payable = fits.reduce((s, it) => s + lineTotal(it), 0)
  const blocked = request.items.filter((it) => it.verdict === 'blocked')
  const reader = MODEL_NAMES[request.aiModel ?? ''] ?? 'Gemini'

  return (
    <section className="rounded-[28px] bg-white px-[26px] pt-[26px] pb-[18px]">
      <h2 className="font-heading m-0 mb-1 text-2xl font-bold">What the AI found</h2>
      <p className="m-0 text-[15px] text-wine-2">{reader} read every line; the rule engine checked it against the donors' limits.</p>

      {request.flags?.map((f) => (
        <p
          key={f.kind + f.message}
          role="alert"
          className={`mt-4 mb-0 rounded-2xl px-4 py-3 text-[15px] font-medium ${f.severity === 'block' ? 'bg-plum text-white' : 'bg-sun text-wine'}`}
        >
          {f.message}
        </p>
      ))}

      <div className="my-[18px] flex items-center gap-4">
        <Ring fits={fits.length} total={request.items.length} delay={revealDelay - 0.3} />
        <div>
          <p className="m-0 text-xl leading-snug font-bold tracking-[-0.01em]">{headline(fits.length, blocked)}</p>
          <p className="m-0 text-[15px] text-wine-2">
            Suggested payout: {usd(payable)} of {usd(requested)}
          </p>
        </div>
      </div>

      <ul className="m-0 list-none p-0">
        {request.items.map((it, i) => {
          const ok = it.verdict === 'fits'
          const active = activeItem === it.id
          return (
            <motion.li
              key={it.id}
              onMouseEnter={() => onActivate(it.id)}
              onMouseLeave={() => onActivate(null)}
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: revealDelay + i * 0.15, type: 'spring', stiffness: 380, damping: 18 }}
              className={`-mx-3 grid origin-left grid-cols-[36px_1fr_auto] items-start gap-3 rounded-2xl px-3 py-[13px] transition-colors ${
                ok ? (active ? 'bg-mint-bg/60' : '') : active ? 'bg-petal' : 'bg-plum-bg'
              }`}
            >
              <span className={`grid size-9 place-items-center rounded-xl ${ok ? 'bg-mint-bg text-mint' : 'bg-plum text-white'}`}>
                {ok ? <Check /> : <Cross />}
                <span className="sr-only">{ok ? 'Fits the fund' : 'Not allowed'}</span>
              </span>
              <div>
                <div className="font-semibold">{it.label}</div>
                <div className="text-[14.5px] text-wine-2">{it.reason}</div>
              </div>
              <span className={`font-bold tabular-nums ${ok ? '' : 'text-wine-2 line-through'}`}>{usd(lineTotal(it))}</span>
            </motion.li>
          )
        })}
      </ul>
    </section>
  )
}
