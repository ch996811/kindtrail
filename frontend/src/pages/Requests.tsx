import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { getConfig, listRequests, resetDemo, type RequestStatus } from '../api'
import { TopBar } from '../components/TopBar'
import { usd } from '../model'

const STATUS: Record<RequestStatus, { text: string; tone: string }> = {
  reviewed: { text: 'Waiting for you', tone: 'bg-pink text-white' },
  paying: { text: 'Paying', tone: 'bg-sun text-wine' },
  paid: { text: 'Paid', tone: 'bg-mint-bg text-mint' },
  returned: { text: 'Sent back', tone: 'bg-plum-bg text-plum' },
}

const day = (iso: string) => new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

/** The charity's inbox: every spending request field partners have sent, waiting ones first. */
export function Requests() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['requests'], queryFn: listRequests })
  const config = useQuery({ queryKey: ['config'], queryFn: getConfig, staleTime: Infinity })
  const reset = useMutation({ mutationFn: resetDemo, onSuccess: () => qc.invalidateQueries() })
  const waiting = q.data?.filter((r) => r.status === 'reviewed').length ?? 0

  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar active="Review desk" role="charity" />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[22ch] text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">
            {!q.data
              ? 'Requests'
              : waiting === 0
                ? 'Nothing is waiting for you'
                : waiting === 1
                  ? '1 request is waiting for you'
                  : `${waiting} requests are waiting for you`}
          </h1>
          <p className="mt-2.5 mb-0 max-w-[60ch] text-[17px] text-wine/80">
            Field partners send receipts here. The AI has already read each one and checked every line against the donors&rsquo; limits;
            you decide what gets paid.
          </p>
          <Link
            to="/reconcile"
            className="mt-3 mr-2 inline-block rounded-full bg-white/70 px-4 py-1.5 text-sm font-semibold text-wine no-underline hover:bg-white"
          >
            Check the ledger against PayPal&rsquo;s report
          </Link>
          {q.data && waiting === 0 && config.data?.demo_mode && (
            <button
              type="button"
              onClick={() => reset.mutate()}
              disabled={reset.isPending}
              className="mt-4 block rounded-[14px] bg-wine px-[18px] py-3 font-bold text-white disabled:opacity-60"
            >
              {reset.isPending ? 'Resetting...' : 'Run the demo again'}
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-[1160px] px-6 pt-[30px] pb-16">
        {q.isPending && <p role="status">Loading...</p>}
        {q.error && <p role="alert">Couldn&rsquo;t load requests: {q.error.message}</p>}
        <ul className="m-0 grid list-none gap-3 p-0">
          {q.data?.map((r) => {
            const s = STATUS[r.status]
            return (
              <li key={r.id}>
                <Link
                  to={`/requests/${r.id}`}
                  className="grid items-center gap-x-6 gap-y-2 rounded-[22px] bg-white px-[22px] py-[18px] text-wine no-underline transition-shadow hover:shadow-[0_10px_30px_-18px_rgb(58_11_37/0.5)] sm:grid-cols-[1fr_auto_auto]"
                >
                  <div>
                    <div className="flex flex-wrap items-baseline gap-x-3">
                      <span className="text-lg font-bold">{r.partner}</span>
                      <span className="text-sm text-wine-2">
                        {r.id}, sent {day(r.submitted_at)}
                      </span>
                    </div>
                    <div className="text-[15px] text-wine-2">
                      {r.purpose}, from the {r.fund}
                    </div>
                    {r.flags[0] && <div className="mt-1 text-sm font-medium text-plum">{r.flags[0]}</div>}
                  </div>
                  <div className="text-[15px] tabular-nums sm:text-right">
                    <div className="font-bold">{usd(r.payable_cents / 100)} payable</div>
                    <div className="text-sm text-wine-2">
                      {r.fits} of {r.lines} lines fit, of {usd(r.requested_cents / 100)}
                    </div>
                  </div>
                  <span className={`justify-self-start rounded-full px-3 py-1 text-sm font-semibold sm:justify-self-end ${s.tone}`}>{s.text}</span>
                </Link>
              </li>
            )
          })}
        </ul>
        {q.data?.length === 0 && <p className="text-wine-2">No requests yet. A field partner can send one from Send a receipt.</p>}
      </main>
    </>
  )
}
