import { lineTotal, type ReviewRequest } from '../model'

/** The partner's receipt photo, with every line the AI read marked by its verdict. */
export function ReceiptPhoto({ request }: { request: ReviewRequest }) {
  const total = request.items.reduce((sum, it) => sum + lineTotal(it), 0)
  return (
    <figure className="m-0 lg:sticky lg:top-6 rounded-[28px] bg-petal px-[22px] pt-7 pb-5">
      <div
        role="img"
        aria-label="Photo of the receipt submitted with this request"
        className="mx-auto w-full max-w-[330px] rotate-[1.5deg] rounded bg-[#FFFEFA] px-[18px] pt-5 pb-6 font-receipt text-[13px] leading-relaxed max-sm:text-[11px] text-[#3d3438] shadow-[0_18px_30px_-20px_rgb(58_11_37/0.55)]"
      >
        <div className="text-center text-sm font-bold">{request.shop.name}</div>
        <div className="mb-2.5 text-center text-[#8d8187]">
          {request.shop.branch}, {request.shop.printedAt}
        </div>
        {request.items.map((it) => (
          <div
            key={it.id}
            className={`-mx-[7px] my-[3px] flex justify-between gap-2 rounded-md px-[7px] py-[3px] ${
              it.verdict === 'fits' ? 'bg-mint-bg' : 'bg-plum text-white'
            }`}
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
      <figcaption className="mt-4 text-center text-sm text-wine-2">The partner's photo, with each line the AI read</figcaption>
    </figure>
  )
}
