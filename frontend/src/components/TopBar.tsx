import { Link } from 'react-router'

// Only pages that exist. Donors and reconciliation join as they're built.
const NAV = [
  { label: 'Review desk', to: '/' },
  { label: 'Send a receipt', to: '/submit' },
  { label: 'Start a fund', to: '/funds/new' },
] as const

export function TopBar({ active }: { active: (typeof NAV)[number]['label'] }) {
  return (
    <div className="mx-auto flex max-w-[1160px] items-center gap-x-6 gap-y-3 px-6 py-[18px] max-md:flex-wrap">
      <Link to="/" className="flex items-baseline gap-2 text-wine no-underline">
        <b className="text-2xl font-extrabold tracking-[-0.015em] [font-variation-settings:'opsz'_96,'wdth'_95]">kindtrail</b>
        <span className="font-tc text-base leading-none font-black text-pink-deep">善蹤</span>
      </Link>
      <nav aria-label="Main" className="flex gap-1 max-md:order-last max-md:w-full">
        {NAV.map((item) => (
          <Link
            key={item.label}
            to={item.to}
            aria-current={item.label === active ? 'page' : undefined}
            className={
              item.label === active
                ? 'rounded-full bg-white px-3.5 py-1.5 font-medium text-wine no-underline'
                : 'rounded-full px-3.5 py-1.5 font-medium text-wine/70 no-underline hover:text-wine'
            }
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2.5 text-sm">
        <span className="rounded-full bg-wine/10 px-3 py-1">PayPal sandbox</span>
        <span className="grid size-[34px] place-items-center rounded-full bg-wine font-bold text-white" aria-label="Signed in as Lin">
          L
        </span>
      </div>
    </div>
  )
}
