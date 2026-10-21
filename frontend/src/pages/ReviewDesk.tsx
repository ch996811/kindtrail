import { useState } from 'react'
import { ActionBar, type Stage } from '../components/ActionBar'
import { ReceiptPhoto } from '../components/ReceiptPhoto'
import { ReviewPanel } from '../components/ReviewPanel'
import { SideTiles } from '../components/SideTiles'
import { TopBar } from '../components/TopBar'
import { Trail } from '../components/Trail'
import { lineTotal, usd, type ReviewRequest } from '../data/demo'

export function ReviewDesk({ request }: { request: ReviewRequest }) {
  const [stage, setStage] = useState<Stage>('review')
  const requested = request.items.reduce((s, it) => s + lineTotal(it), 0)
  const payable = request.items.filter((it) => it.verdict === 'fits').reduce((s, it) => s + lineTotal(it), 0)

  // TODO(W1): call POST /api/requests/:id/approve, which sends the PayPal Payouts batch.
  const approve = () => {
    setStage('paying')
    window.setTimeout(() => setStage('paid'), 1200)
  }

  const stops = [
    { label: 'Gifts in', detail: `${request.gifts.length} donors` },
    { label: 'Asked', detail: request.submitted },
    { label: stage === 'review' ? 'Your review' : 'Approved', detail: 'by Lin' },
    { label: 'Paid', detail: 'via PayPal' },
    { label: 'Thank-you', detail: 'to each donor' },
  ]

  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar active="Requests" />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[20ch] text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">
            {request.partner} needs {usd(requested)} for {request.purpose}
          </h1>
          <p className="mt-2.5 mb-0 max-w-[56ch] text-[17px] text-wine/80">
            {stage === 'paid'
              ? `Request ${request.id} is paid. Next, each donor gets a receipt showing what their gift bought.`
              : `Request ${request.id} from the ${request.fund}. The AI has checked the receipt; it's your call now.`}
          </p>
          <Trail stops={stops} current={stage === 'paid' ? 3 : 2} />
        </div>
      </header>

      <main className="mx-auto grid max-w-[1160px] items-start gap-[26px] px-6 pt-[30px] pb-[130px] lg:grid-cols-[5fr_7fr]">
        <ReceiptPhoto request={request} />
        <div>
          <ReviewPanel request={request} />
          <SideTiles request={request} />
        </div>
      </main>

      <ActionBar partner={request.partner} amount={payable} stage={stage} onApprove={approve} />
    </>
  )
}
