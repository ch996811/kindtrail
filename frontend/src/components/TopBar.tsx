const NAV = ['Funds', 'Requests', 'Donors', 'Reconcile'] as const

export function TopBar({ active }: { active: (typeof NAV)[number] }) {
  return (
    <div className="mx-auto flex max-w-[1160px] items-center gap-6 px-6 py-[18px]">
      <a href="/" className="flex items-baseline gap-2 text-wine no-underline">
        <b className="text-2xl font-extrabold tracking-[-0.015em] [font-variation-settings:'opsz'_96,'wdth'_95]">kindtrail</b>
        <span className="font-tc text-base leading-none font-black text-pink-deep">善蹤</span>
      </a>
      <nav aria-label="Main" className="flex gap-1 max-md:hidden">
        {NAV.map((item) => (
          <a
            key={item}
            href="#"
            aria-current={item === active ? 'page' : undefined}
            className={
              item === active
                ? 'rounded-full bg-white px-3.5 py-1.5 font-medium text-wine'
                : 'rounded-full px-3.5 py-1.5 font-medium text-wine/70 hover:text-wine'
            }
          >
            {item}
          </a>
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
