import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { getReconciliation, type MatchState, type PayPalRow, type Reconciliation } from '../api'
import { TopBar } from '../components/TopBar'
import { usd } from '../model'

const STATE: Record<MatchState, { text: string; tone: string }> = {
  matched: { text: 'Matched', tone: 'bg-mint-bg text-mint' },
  waiting: { text: 'Waiting for PayPal', tone: 'bg-sun text-wine' },
  not_paypal: { text: 'Not through PayPal', tone: 'bg-blush text-wine-2' },
  failed: { text: 'Didn’t go through', tone: 'bg-plum-bg text-plum' },
  mismatch: { text: 'Doesn’t match', tone: 'bg-pink text-white' },
  missing: { text: 'Missing at PayPal', tone: 'bg-pink text-white' },
}

/** Money as PayPal's report shows it: money in positive, money out negative. */
const signed = (cents: number) => `${cents < 0 ? '−' : '+'}${usd(Math.abs(cents) / 100)}`
const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : ''

function Pill({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`justify-self-start rounded-full px-3 py-1 text-sm font-semibold whitespace-nowrap sm:justify-self-end ${tone}`}>{children}</span>
}

function PayPalRows({ rows }: { rows: PayPalRow[] }) {
  return (
    <ul className="m-0 mt-2 grid list-none gap-1 p-0 text-[13.5px] text-wine-2">
      {rows.map((r) => (
        <li key={r.transaction_id} className="flex flex-wrap gap-x-2">
          <span className="font-receipt">{r.transaction_id}</span>
          <span>
            {r.event} ({r.event_code}) {signed(r.cents)}
            {r.fee_cents !== 0 && `, fee ${usd(Math.abs(r.fee_cents) / 100)}`}
            {r.custom_field && `, custom_field ${r.custom_field}`}
          </span>
        </li>
      ))}
    </ul>
  )
}

function LedgerRow({ row }: { row: Reconciliation['rows'][number] }) {
  const s = STATE[row.state]
  const pp = row.paypal
  return (
    <li className="grid items-start gap-x-6 gap-y-2 rounded-[22px] bg-white px-[22px] py-[18px] sm:grid-cols-[1fr_auto_auto]">
      <div>
        <div className="flex flex-wrap items-baseline gap-x-3">
          <span className="text-lg font-bold">{row.label}</span>
          <span className="text-sm text-wine-2">
            {when(row.at)}
            {row.earlier && ', from an earlier run of the demo'}
          </span>
        </div>
        <div className="text-[15px] text-wine-2">{row.detail}</div>
        {pp && pp.related.length > 0 && (
          <div className="mt-1 text-[13.5px] text-wine-2">
            PayPal lists this payout as {pp.related.length + 1} rows: the payment, a hold on the balance for the amount plus the fee, and
            the hold&rsquo;s release. Kindtrail groups them; the hold and release cancel out.
          </div>
        )}
      </div>
      <div className="text-[15px] tabular-nums sm:text-right">
        <div>
          <span className="text-wine-2">Ledger </span>
          <b>{signed(row.ours_cents)}</b>
        </div>
        {pp && (
          <div>
            <span className="text-wine-2">PayPal </span>
            <b>{signed(pp.cents)}</b>
            {pp.fee_cents !== 0 && <span className="text-wine-2">, fee {usd(Math.abs(pp.fee_cents) / 100)}</span>}
          </div>
        )}
        {row.transaction_id && <div className="font-receipt text-[13px] text-wine-2">{row.transaction_id}</div>}
      </div>
      <Pill tone={s.tone}>{s.text}</Pill>
    </li>
  )
}

function PayPalOnly({ group }: { group: Reconciliation['paypal_only'][number] }) {
  return (
    <li className="grid items-start gap-x-6 gap-y-1 rounded-[22px] bg-white px-[22px] py-[16px] sm:grid-cols-[1fr_auto_auto]">
      <div>
        <div className="flex flex-wrap items-baseline gap-x-3">
          <span className="font-bold">{group.label}</span>
          <span className="text-sm text-wine-2">{when(group.at)}</span>
        </div>
        <PayPalRows rows={group.rows} />
      </div>
      <div className="text-[15px] font-bold tabular-nums sm:text-right">{signed(group.net_cents)} net</div>
      {group.attention ? (
        <Pill tone="bg-pink text-white">To look at</Pill>
      ) : (
        <Pill tone="bg-blush text-wine-2">{group.before_ledger ? 'Before this ledger' : 'Not a gift or payout'}</Pill>
      )}
    </li>
  )
}

/** The charity's check that its ledger and PayPal agree, gift by gift and payout by payout. */
export function Reconcile() {
  const q = useQuery({ queryKey: ['reconcile'], queryFn: getReconciliation, staleTime: 60_000 })
  const d = q.data
  const recent = d?.paypal_only.filter((g) => !g.before_ledger) ?? []
  const earlier = d?.paypal_only.filter((g) => g.before_ledger) ?? []
  const n = d?.summary.to_check ?? 0
  const nothingYet = d && n === 0 && d.summary.matched + d.summary.waiting + d.summary.failed === 0

  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar active="Review desk" role="charity" />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[22ch] text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">
            {!d
              ? 'Checking the ledger against PayPal'
              : nothingYet
                ? 'No PayPal money in this ledger yet'
                : n === 0
                  ? 'The ledger agrees with PayPal'
                  : `${n} ${n === 1 ? 'thing' : 'things'} to look at`}
          </h1>
          <p className="mt-2.5 mb-0 max-w-[62ch] text-[17px] text-wine/80">
            Kindtrail matches every gift and payout in its ledger to PayPal&rsquo;s Transaction Search report by transaction ID. PayPal
            updates that report every few hours, so a payout made just now shows as waiting first.
            {nothingYet && ' Approve a request on the review desk and its payout will appear here.'}
          </p>
          {d && (
            <div className="mt-4 flex flex-wrap items-center gap-2 text-sm font-semibold">
              <span className="rounded-full bg-mint-bg px-3 py-1 text-mint">{d.summary.matched} matched</span>
              <span className="rounded-full bg-sun px-3 py-1">{d.summary.waiting} waiting for PayPal&rsquo;s report</span>
              {d.summary.not_paypal > 0 && (
                <span className="rounded-full bg-white/70 px-3 py-1 text-wine-2">{d.summary.not_paypal} demo gifts, not through PayPal</span>
              )}
              {d.summary.failed > 0 && <span className="rounded-full bg-plum-bg px-3 py-1 text-plum">{d.summary.failed} didn&rsquo;t go through</span>}
              <span className={`rounded-full px-3 py-1 ${n ? 'bg-pink text-white' : 'bg-white/70 text-wine-2'}`}>{n} to look at</span>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-[1160px] px-6 pt-[30px] pb-16">
        {q.isPending && <p role="status">Asking PayPal for its report. This takes about ten seconds.</p>}
        {q.error && (
          <p role="alert" className="rounded-2xl bg-plum px-4 py-3 font-medium text-white">
            Couldn&rsquo;t get PayPal&rsquo;s report: {q.error.message}
          </p>
        )}
        {d && (
          <>
            <p className="mt-0 mb-5 text-sm text-wine-2">
              PayPal&rsquo;s report is current to {when(d.refreshed_at) || 'an unknown time'}. Checked {when(d.checked_at)}.{' '}
              <button type="button" onClick={() => q.refetch()} disabled={q.isFetching} className="font-bold text-wine underline disabled:opacity-60">
                {q.isFetching ? 'Checking...' : 'Check again'}
              </button>{' '}
              <Link to="/requests" className="font-bold text-wine">
                Back to the requests
              </Link>
            </p>

            <h2 className="font-heading m-0 mb-3 text-2xl font-bold">In this ledger</h2>
            <ul className="m-0 grid list-none gap-3 p-0">
              {d.rows.map((r) => (
                <LedgerRow key={`${r.kind}-${r.ref}-${r.transaction_id}-${r.at}`} row={r} />
              ))}
            </ul>

            <h2 className="font-heading mt-9 mb-1 text-2xl font-bold">In PayPal&rsquo;s report, not in this ledger</h2>
            <p className="mt-0 mb-3 text-[15px] text-wine-2">Since this ledger started on {when(d.ledger_started_at)}.</p>
            {recent.length === 0 ? (
              <p className="m-0 rounded-[22px] bg-white px-[22px] py-[16px]">Nothing. Every PayPal payment since then is in the ledger.</p>
            ) : (
              <ul className="m-0 grid list-none gap-3 p-0">
                {recent.map((g) => (
                  <PayPalOnly key={g.rows[0]?.transaction_id} group={g} />
                ))}
              </ul>
            )}

            {earlier.length > 0 && (
              <details className="mt-6">
                <summary className="cursor-pointer font-semibold">
                  {earlier.length} earlier sandbox {earlier.length === 1 ? 'payment' : 'payments'}, from before this ledger started
                </summary>
                <p className="mt-2 mb-3 max-w-[70ch] text-[15px] text-wine-2">
                  The hosted demo starts a fresh ledger when its server restarts, but PayPal keeps every sandbox transaction. These are
                  shown for context, grouped the same way, and aren&rsquo;t counted as problems.
                </p>
                <ul className="m-0 grid list-none gap-3 p-0">
                  {earlier.map((g) => (
                    <PayPalOnly key={g.rows[0]?.transaction_id} group={g} />
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </main>
    </>
  )
}
