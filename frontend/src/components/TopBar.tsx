import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router'

// In the order a dollar travels: a donor sets limits and gives, a partner asks, the charity reviews.
const NAV = [
  { label: 'How it works', to: '/' },
  { label: 'Start a fund', to: '/funds/new' },
  { label: 'Give', to: '/give' },
  { label: 'Send a receipt', to: '/submit' },
  { label: 'Review desk', to: '/requests' },
] as const

export type Role = 'donor' | 'partner' | 'charity'

// Whose eyes each page is seen through, so a visitor always knows which person they're playing,
// and can switch to another person's view from any page.
const ROLES: Record<Role, { view: string; initial: string; who: string; does: string; to: string }> = {
  donor: { view: 'Donor view', initial: 'D', who: 'A donor', does: 'Give to a fund, or start one with your own limits', to: '/give' },
  partner: { view: 'Partner view', initial: 'H', who: 'Hualien Mountain Kitchen', does: 'A field partner: send a receipt to be paid back', to: '/submit' },
  charity: { view: 'Charity view', initial: 'L', who: 'Lin at the charity', does: 'Review requests and pay partners through PayPal', to: '/requests' },
}

/** A button that opens a small panel; closes on Escape, on a click outside, or when a link inside is used. */
function Popover({ label, button, className, children }: { label: string; button: ReactNode; className: string; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <div ref={box} className="relative">
      <button type="button" aria-label={label} aria-expanded={open} onClick={() => setOpen((o) => !o)} className={className}>
        {button}
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className={`transition-transform ${open ? 'rotate-180' : ''}`}>
          <path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-[calc(100%+8px)] right-0 z-50 w-[300px] rounded-[18px] bg-white p-2 text-left text-wine shadow-[0_18px_40px_-12px_rgb(58_11_37/0.45)]">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

export function TopBar({ active, role }: { active?: (typeof NAV)[number]['label']; role?: Role }) {
  const r = role ? ROLES[role] : null
  return (
    <div className="mx-auto flex max-w-[1160px] items-center gap-x-6 gap-y-3 px-6 py-[18px] max-[1120px]:flex-wrap">
      <Link to="/" className="flex items-baseline gap-2 text-wine no-underline">
        <b className="text-2xl font-extrabold tracking-[-0.015em] [font-variation-settings:'opsz'_96,'wdth'_95]">kindtrail</b>
        <span className="font-tc text-base leading-none font-black text-pink-deep">善蹤</span>
      </Link>
      <nav aria-label="Main" className="flex gap-1 max-lg:order-last max-lg:w-full max-[1120px]:flex-wrap">
        {NAV.map((item) => (
          <Link
            key={item.label}
            to={item.to}
            aria-current={item.label === active ? 'page' : undefined}
            className={
              item.label === active
                ? 'whitespace-nowrap rounded-full bg-white px-3.5 py-1.5 font-medium text-wine no-underline'
                : 'whitespace-nowrap rounded-full px-3.5 py-1.5 font-medium text-wine/70 no-underline hover:text-wine'
            }
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2.5 text-sm">
        <Popover
          label="About the PayPal sandbox"
          button="PayPal sandbox"
          className="flex items-center gap-1.5 whitespace-nowrap rounded-full bg-wine/10 px-3 py-1.5 font-medium hover:bg-wine/15"
        >
          {() => (
            <p className="m-0 px-3 py-2 text-[14px] leading-snug">
              Everything here runs in <b>PayPal&rsquo;s sandbox</b>: test accounts and test money, so no real card is ever charged.
              Payouts go to a sandbox account that plays the field partner, and the AI reads receipts for real.
            </p>
          )}
        </Popover>
        <Popover
          label={r ? `Viewing as ${r.who}. Switch view` : 'Choose whose view to see'}
          button={
            <>
              <span className="font-semibold max-sm:hidden">{r ? r.view : 'Choose a view'}</span>
              {r && <span className="grid size-[28px] place-items-center rounded-full bg-wine text-[13px] font-bold text-white">{r.initial}</span>}
            </>
          }
          className="flex items-center gap-2 whitespace-nowrap rounded-full bg-white py-1 pr-2.5 pl-3 hover:bg-blush"
        >
          {(close) => (
            <ul className="m-0 grid list-none gap-0.5 p-0">
              <li className="px-3 pt-1.5 pb-1 text-[12px] font-bold tracking-[0.06em] text-wine-2 uppercase">See the demo as</li>
              {(Object.keys(ROLES) as Role[]).map((k) => (
                <li key={k}>
                  <Link
                    to={ROLES[k].to}
                    onClick={close}
                    aria-current={k === role ? 'true' : undefined}
                    className={`flex items-start gap-3 rounded-[12px] px-3 py-2.5 text-wine no-underline hover:bg-blush ${k === role ? 'bg-blush/70' : ''}`}
                  >
                    <span className="grid size-[30px] flex-none place-items-center rounded-full bg-wine text-[13px] font-bold text-white">{ROLES[k].initial}</span>
                    <span className="grid">
                      <b className="text-[14.5px]">
                        {ROLES[k].who}
                        {k === role && <span className="ml-1.5 font-medium text-wine-2">(you&rsquo;re here)</span>}
                      </b>
                      <span className="text-[13px] leading-snug text-wine-2">{ROLES[k].does}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Popover>
      </div>
    </div>
  )
}
