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

// Whose eyes each page is seen through, so a visitor always knows which person they're playing.
const ROLES: Record<Role, { view: string; initial: string; who: string }> = {
  donor: { view: 'Donor view', initial: 'D', who: 'a donor' },
  partner: { view: 'Partner view', initial: 'H', who: 'Hualien Mountain Kitchen, a field partner' },
  charity: { view: 'Charity view', initial: 'L', who: 'Lin, the charity reviewer' },
}

export function TopBar({ active, role }: { active?: (typeof NAV)[number]['label']; role?: Role }) {
  const r = role ? ROLES[role] : null
  return (
    <div className="mx-auto flex max-w-[1160px] items-center gap-x-6 gap-y-3 px-6 py-[18px] max-md:flex-wrap">
      <Link to="/" className="flex items-baseline gap-2 text-wine no-underline">
        <b className="text-2xl font-extrabold tracking-[-0.015em] [font-variation-settings:'opsz'_96,'wdth'_95]">kindtrail</b>
        <span className="font-tc text-base leading-none font-black text-pink-deep">善蹤</span>
      </Link>
      <nav aria-label="Main" className="flex gap-1 max-md:order-last max-md:w-full max-md:flex-wrap">
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
        {r && (
          <>
            <span className="rounded-full bg-white px-3 py-1 font-semibold max-sm:hidden">{r.view}</span>
            <span className="grid size-[34px] place-items-center rounded-full bg-wine font-bold text-white" title={`Viewing as ${r.who}`} aria-label={`Viewing as ${r.who}`}>
              {r.initial}
            </span>
          </>
        )}
      </div>
    </div>
  )
}
