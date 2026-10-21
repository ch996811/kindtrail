import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ActionBar, type Stage } from '../components/ActionBar'
import { ReceiptPhoto } from '../components/ReceiptPhoto'
import { ReviewPanel } from '../components/ReviewPanel'
import { SideTiles } from '../components/SideTiles'
import { TopBar } from '../components/TopBar'
import { Trail } from '../components/Trail'
import { approveRequest, getRequest, refreshRequest, toReviewModel } from '../api'
import { usd } from '../model'

const APPROVER = 'Lin'

export function ReviewDesk({ requestId }: { requestId: string }) {
  const qc = useQueryClient()
  const [activeItem, setActiveItem] = useState<string | null>(null)
  const key = ['request', requestId]
  const { data, error, isPending } = useQuery({ queryKey: key, queryFn: () => getRequest(requestId) })

  // While PayPal processes the payout, ask the backend to re-check it every 2 seconds.
  useQuery({
    queryKey: [...key, 'payout'],
    queryFn: async () => {
      const fresh = await refreshRequest(requestId)
      qc.setQueryData(key, fresh)
      return fresh.status
    },
    enabled: data?.status === 'paying',
    refetchInterval: 2000,
  })

  const approve = useMutation({
    mutationFn: () => approveRequest(requestId, APPROVER),
    onSuccess: (fresh) => qc.setQueryData(key, fresh),
  })

  if (isPending || error) {
    return (
      <header className="rounded-b-[36px] bg-band pb-10">
        <TopBar active="Requests" />
        <p className="mx-auto max-w-[1160px] px-6 pt-6 text-lg" role={error ? 'alert' : 'status'}>
          {error ? `Couldn't load request ${requestId}: ${error.message}` : `Loading request ${requestId}...`}
        </p>
      </header>
    )
  }

  const request = toReviewModel(data)
  const stage: Stage = data.status === 'paid' ? 'paid' : data.status === 'paying' || approve.isPending ? 'paying' : 'review'
  const notice = approve.error
    ? approve.error.message
    : data.payable_cents === 0 && stage === 'review'
      ? 'Nothing on this receipt fits the fund. Send it back to the partner.'
      : data.shortfall_cents > 0
      ? `The fund is ${usd(data.shortfall_cents / 100)} short. Wait for more gifts before paying.`
      : undefined

  const stops = [
    {
      label: 'Gifts in',
      detail: data.payable_cents === 0 ? 'nothing to pay' : `${data.funding.length} ${data.funding.length === 1 ? 'donor' : 'donors'}`,
    },
    { label: 'Asked', detail: request.submitted },
    { label: stage === 'review' ? 'Your review' : 'Approved', detail: `by ${data.approved_by ?? APPROVER}` },
    { label: 'Paid', detail: 'via PayPal' },
    { label: 'Thank-you', detail: 'to each donor' },
  ]

  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar active="Requests" />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[20ch] text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">
            {request.partner} needs {usd(data.requested_cents / 100)} for {request.purpose}
          </h1>
          <p className="mt-2.5 mb-0 max-w-[56ch] text-[17px] text-wine/80">
            {stage === 'paid'
              ? `Request ${request.id} is paid. Next, each donor gets a receipt showing what their gift bought.`
              : stage === 'paying'
                ? `Sending ${usd(data.payable_cents / 100)} through PayPal Payouts. This usually takes a few seconds.`
                : `Request ${request.id} from the ${request.fund}. The AI has checked the receipt; it's your call now.`}
          </p>
          <Trail stops={stops} current={stage === 'paid' ? 3 : 2} />
        </div>
      </header>

      <main className="mx-auto grid max-w-[1160px] items-start gap-[26px] px-6 pt-[30px] pb-[130px] lg:grid-cols-[5fr_7fr]">
        <ReceiptPhoto request={request} activeItem={activeItem} onActivate={setActiveItem} />
        <div>
          <ReviewPanel request={request} activeItem={activeItem} onActivate={setActiveItem} />
          <SideTiles request={request} />
        </div>
      </main>

      <ActionBar
        partner={request.partner}
        amount={data.payable_cents / 100}
        stage={stage}
        notice={notice}
        canApprove={data.shortfall_cents === 0 && data.payable_cents > 0}
        onApprove={() => approve.mutate()}
      />
    </>
  )
}
