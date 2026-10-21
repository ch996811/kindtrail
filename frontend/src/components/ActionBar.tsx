import { AnimatePresence, motion } from 'motion/react'
import { usd } from '../model'

export type Stage = 'review' | 'paying' | 'paid'

interface Props {
  partner: string
  amount: number
  stage: Stage
  notice?: string // an error or a reason approval is blocked
  canApprove: boolean
  onApprove: () => void
}

/** Floating decision bar. Approving moves the coin to the "Paid" stop once PayPal confirms. */
export function ActionBar({ partner, amount, stage, notice, canApprove, onApprove }: Props) {
  const message =
    notice ?? (stage === 'paid' ? `${usd(amount)} sent to ${partner} through PayPal Payouts` : `Pays ${partner} via PayPal Payouts`)
  return (
    <div className="fixed bottom-[18px] left-1/2 flex w-[min(760px,calc(100%-32px))] -translate-x-1/2 items-center gap-2.5 rounded-[22px] bg-wine py-3 pr-3 pl-[22px] text-white shadow-[0_18px_40px_-16px_rgb(58_11_37/0.6)] max-sm:flex-wrap">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={message}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          className={`mr-auto text-[14.5px] ${notice ? 'text-petal' : 'text-white/80 max-sm:hidden'}`}
          role={notice ? 'alert' : 'status'}
        >
          {message}
        </motion.span>
      </AnimatePresence>
      {stage !== 'paid' ? (
        <>
          <button type="button" disabled={stage === 'paying'} className="rounded-[14px] bg-white/12 px-[18px] py-3 font-bold disabled:opacity-50 max-sm:flex-1">
            Send back
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={stage === 'paying' || !canApprove}
            className="rounded-[14px] bg-pink px-[18px] py-3 font-bold hover:bg-pink-hover disabled:cursor-not-allowed disabled:opacity-60 max-sm:flex-1"
          >
            {stage === 'paying' ? 'Paying...' : `Approve ${usd(amount)}`}
          </button>
        </>
      ) : (
        <button type="button" className="rounded-[14px] bg-white px-[18px] py-3 font-bold text-wine max-sm:flex-1">
          Send donor thank-yous
        </button>
      )}
    </div>
  )
}
