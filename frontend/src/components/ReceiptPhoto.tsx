import { motion } from 'motion/react'
import { lineTotal, type ReviewRequest } from '../model'

interface Props {
  request: ReviewRequest
  activeItem: string | null
  onActivate: (id: string | null) => void
}

/** The partner's receipt photo, with a box on every line the AI read, colored by its verdict. */
export function ReceiptPhoto({ request, activeItem, onActivate }: Props) {
  return (
    <figure className="m-0 rounded-[28px] bg-petal px-[22px] pt-7 pb-5 lg:sticky lg:top-6">
      {request.receiptUrl ? <Photo request={request} activeItem={activeItem} onActivate={onActivate} /> : <TypedReceipt request={request} />}
      <figcaption className="mt-4 text-center text-sm text-wine-2">
        {request.receiptUrl ? 'The partner’s photo. Boxes show where the AI read each line.' : 'The partner’s photo, with each line the AI read'}
      </figcaption>
    </figure>
  )
}

function Photo({ request, activeItem, onActivate }: Props) {
  return (
    <div className="relative mx-auto w-full max-w-[400px] overflow-hidden rounded-xl shadow-[0_18px_30px_-20px_rgb(58_11_37/0.55)]">
      <img src={request.receiptUrl} alt={`Receipt from ${request.shop.name}`} className="block w-full" />
      {request.items.map((it, i) => {
        if (!it.box) return null
        const [y0, x0, y1, x1] = it.box
        const ok = it.verdict === 'fits'
        const active = activeItem === it.id
        return (
          <motion.button
            key={it.id}
            type="button"
            aria-label={`${it.label}: ${ok ? 'fits the fund' : 'not allowed'}`}
            onMouseEnter={() => onActivate(it.id)}
            onMouseLeave={() => onActivate(null)}
            onFocus={() => onActivate(it.id)}
            onBlur={() => onActivate(null)}
            initial={{ opacity: 0, scale: 1.08 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 1.9 + i * 0.15, duration: 0.3, ease: 'easeOut' }}
            className={[
              'absolute cursor-default rounded-[6px] border-[2.5px] transition-[background-color,box-shadow]',
              ok ? 'border-mint bg-mint/10' : 'border-plum bg-plum/20',
              active ? (ok ? 'bg-mint/25 shadow-[0_0_0_4px_rgb(18_133_95/0.25)]' : 'bg-plum/35 shadow-[0_0_0_4px_rgb(91_22_64/0.3)]') : '',
            ].join(' ')}
            style={{ top: `${y0 / 10}%`, left: `${x0 / 10}%`, width: `${(x1 - x0) / 10}%`, height: `${(y1 - y0) / 10}%` }}
          />
        )
      })}
    </div>
  )
}

/** Fallback when there is no photo: draw the receipt from the extracted lines. */
function TypedReceipt({ request }: { request: ReviewRequest }) {
  const total = request.items.reduce((sum, it) => sum + lineTotal(it), 0)
  return (
    <div
      role="img"
      aria-label="Receipt submitted with this request"
      className="mx-auto w-full max-w-[330px] rotate-[1.5deg] rounded bg-[#FFFEFA] px-[18px] pt-5 pb-6 font-receipt text-[13px] leading-relaxed text-[#3d3438] shadow-[0_18px_30px_-20px_rgb(58_11_37/0.55)] max-sm:text-[11px]"
    >
      <div className="text-center text-sm font-bold">{request.shop.name}</div>
      <div className="mb-2.5 text-center text-[#8d8187]">
        {request.shop.branch}, {request.shop.printedAt}
      </div>
      {request.items.map((it) => (
        <div
          key={it.id}
          className={`-mx-[7px] my-[3px] flex justify-between gap-2 rounded-md px-[7px] py-[3px] ${it.verdict === 'fits' ? 'bg-mint-bg' : 'bg-plum text-white'}`}
        >
          <span>{it.receiptText}</span>
          <span>
            {it.qty} x {it.unitPrice.toFixed(2)}
          </span>
          <span>{lineTotal(it).toFixed(2)}</span>
        </div>
      ))}
      <div className="my-2.5 border-t-2 border-dashed border-[#d8cdd2]" />
      <div className="flex justify-between text-sm font-bold">
        <span>TOTAL USD</span>
        <span>{total.toFixed(2)}</span>
      </div>
    </div>
  )
}
