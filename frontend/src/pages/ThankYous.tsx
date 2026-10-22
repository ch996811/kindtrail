import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { getRequest } from '../api'
import { TopBar } from '../components/TopBar'
import { usd } from '../model'

const TONES = ['bg-petal text-pink-deep', 'bg-sun text-[#7A5200]', 'bg-mint-bg text-mint']

/** After a payout: one receipt link per donor whose gift paid for the request. */
export function ThankYous() {
  const { id = '' } = useParams()
  const q = useQuery({ queryKey: ['request', id], queryFn: () => getRequest(id) })
  const [copied, setCopied] = useState<number | null>(null)

  async function copy(giftId: number) {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/gifts/${giftId}`)
      setCopied(giftId)
    } catch {
      setCopied(null)
    }
  }

  const d = q.data
  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar active="Review desk" />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[22ch] text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">
            Thank the donors behind <span className="whitespace-nowrap">{id}</span>
          </h1>
          <p className="mt-2.5 mb-0 max-w-[60ch] text-[17px] text-wine/80">
            Each donor gets their own receipt showing exactly which lines their money paid for, and the PayPal payout that proves it.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-[1160px] px-6 pt-[30px] pb-16">
        {q.isPending && <p role="status">Loading...</p>}
        {q.error && <p role="alert">Couldn&rsquo;t load {id}: {q.error.message}</p>}
        {d && d.status !== 'paid' && (
          <p className="rounded-2xl bg-sun px-4 py-3 font-medium">
            {id} isn&rsquo;t paid yet. Receipts are ready once PayPal confirms the payout.{' '}
            <Link to={`/requests/${id}`} className="font-bold text-wine">
              Back to the review desk
            </Link>
          </p>
        )}
        {d && d.status === 'paid' && (
          <div className="grid gap-[18px] sm:grid-cols-2 lg:grid-cols-3">
            {d.funding.map((f, n) => (
              <section key={f.gift_id} className="rounded-[28px] bg-white px-[24px] py-[22px]">
                <div className="flex items-center gap-3">
                  <span className={`grid size-12 place-items-center rounded-full text-lg font-extrabold ${TONES[n % TONES.length]}`} aria-hidden="true">
                    {f.donor === 'Anonymous' ? '?' : f.donor.charAt(0)}
                  </span>
                  <div>
                    <h2 className="font-heading m-0 text-xl font-bold">{f.donor}</h2>
                    <p className="m-0 text-sm text-wine-2">
                      {usd(f.used_here_cents / 100)} of a {usd(f.given_cents / 100)} gift went to {id}
                    </p>
                  </div>
                </div>
                <div className="mt-5 flex flex-wrap gap-2.5">
                  <Link to={`/gifts/${f.gift_id}`} className="rounded-[14px] bg-pink px-4 py-2.5 font-bold text-white no-underline hover:bg-pink-hover">
                    Open receipt
                  </Link>
                  <button type="button" onClick={() => copy(f.gift_id)} className="rounded-[14px] bg-blush px-4 py-2.5 font-bold text-wine">
                    {copied === f.gift_id ? 'Link copied' : 'Copy link'}
                  </button>
                </div>
              </section>
            ))}
          </div>
        )}
      </main>
    </>
  )
}
