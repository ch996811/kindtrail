import type { ReactNode } from 'react'
import { usd, type Gift, type ReviewRequest } from '../data/demo'

const TONE: Record<Gift['tone'], string> = {
  pink: 'bg-petal text-pink-deep',
  sun: 'bg-sun text-[#7A5200]',
  mint: 'bg-mint-bg text-mint',
}

function Tile({ title, wide, children }: { title: string; wide?: boolean; children: ReactNode }) {
  return (
    <section className={`rounded-[22px] bg-white px-[22px] py-5 ${wide ? 'sm:col-span-2' : ''}`}>
      <h2 className="font-heading m-0 mb-1 text-2xl font-bold">{title}</h2>
      {children}
    </section>
  )
}

/** Donor limits, whose gifts pay for this request, and the non-AI checks. */
export function SideTiles({ request }: { request: ReviewRequest }) {
  const { checks } = request
  return (
    <div className="mt-[18px] grid gap-[18px] sm:grid-cols-2">
      <Tile title="What donors asked for" wide>
        <p className="mt-3 mb-3.5 text-lg leading-snug font-medium [font-variation-settings:'opsz'_24]">
          <span className="relative top-3 mr-0.5 text-[34px] leading-[0] font-extrabold text-pink" aria-hidden="true">
            &ldquo;
          </span>
          {request.donorWords}
        </p>
        <div className="flex flex-wrap gap-2">
          {request.rules.map((r) => (
            <span key={r.kind} className="rounded-full bg-blush px-[13px] py-1.5 text-sm">
              <b className="font-semibold text-pink-deep">{r.kind}</b> {r.value}
            </span>
          ))}
        </div>
      </Tile>

      <Tile title="Whose dollars">
        <ul className="m-0 mt-3.5 grid list-none gap-2.5 p-0">
          {request.gifts.map((g) => {
            const left = g.given - g.usedHere
            return (
              <li key={g.donor} className="flex items-center gap-3">
                <span className={`grid size-[38px] flex-none place-items-center rounded-full font-bold ${TONE[g.tone]}`} aria-hidden="true">
                  {g.initial}
                </span>
                <div>
                  {g.donor}
                  <div className="text-[13.5px] text-wine-2">{left > 0 ? `${usd(left)} still waiting` : `${g.date} gift, fully used`}</div>
                </div>
                <span className="ml-auto font-bold tabular-nums">{usd(g.usedHere)}</span>
              </li>
            )
          })}
        </ul>
      </Tile>

      <Tile title="Also checked">
        <ul className="m-0 mt-3 grid list-none gap-2.5 p-0 text-[15px]">
          <li className="flex justify-between gap-2.5">
            <span>Receipt used before?</span>
            <span className={`font-semibold ${checks.duplicateReceipt ? 'text-plum' : 'text-mint'}`}>{checks.duplicateReceipt ? 'Yes' : 'No'}</span>
          </li>
          <li className="flex justify-between gap-2.5">
            <span>Shop in Hualien?</span>
            <span className="font-semibold text-mint">Yes, {checks.shopInRegion}</span>
          </li>
          <li className="flex justify-between gap-2.5">
            <span>Partner's monthly cap</span>
            <span className="text-right font-semibold tabular-nums">
              {usd(checks.monthSpent).replace('.00', '')} / {usd(checks.monthCap).replace('.00', '')}
            </span>
          </li>
        </ul>
        <div className="mt-2.5 h-2.5 overflow-hidden rounded-full bg-blush" aria-hidden="true">
          <i className="block h-full rounded-full bg-pink" style={{ width: `${(checks.monthSpent / checks.monthCap) * 100}%` }} />
        </div>
      </Tile>
    </div>
  )
}
