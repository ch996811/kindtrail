import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { getFund, listRequests } from '../api'
import { TopBar } from '../components/TopBar'
import { Trail } from '../components/Trail'
import { usd } from '../model'

const SAMPLE_FUND = 'FUND-HUALIEN-KIDS'
const SAMPLE_REQUEST = 'KT-0142'

const ROLES = [
  {
    initial: 'D',
    tone: 'bg-petal text-pink-deep',
    title: 'A donor gives, with limits',
    body: 'Gives through PayPal and says in plain words what the gift may pay for, like “only for kids in Hualien.” Later gets a receipt showing exactly what it bought.',
    links: [
      { to: '/funds/new', label: 'Start a fund' },
      { to: '/give', label: 'Give' },
    ],
  },
  {
    initial: 'H',
    tone: 'bg-sun text-[#7A5200]',
    title: 'A field partner asks to be paid back',
    body: 'Hualien Mountain Kitchen buys tarps, rice and raincoats on the ground, then sends a photo of the receipt.',
    links: [{ to: '/submit', label: 'Send a receipt' }],
  },
  {
    initial: 'L',
    tone: 'bg-mint-bg text-mint',
    title: 'The charity checks, then pays',
    body: 'The AI reads every line and checks it against the donors’ limits. Lin at the charity approves, and PayPal pays the partner. Nothing is paid without a person.',
    links: [{ to: '/requests', label: 'Review desk' }],
  },
]

const STATUS_TEXT = { reviewed: 'waiting for review', paying: 'paying', paid: 'paid', returned: 'sent back' } as const

export function Home() {
  const fund = useQuery({ queryKey: ['fund', SAMPLE_FUND], queryFn: () => getFund(SAMPLE_FUND) })
  const requests = useQuery({ queryKey: ['requests'], queryFn: listRequests })
  const firstGift = fund.data?.gifts[0]
  const sample = requests.data?.find((r) => r.id === SAMPLE_REQUEST)

  const steps = [
    {
      title: 'Turn a donor’s words into rules',
      body: 'Pick an example and watch the AI write the fund’s rules. Change one and see how three receipts would be judged.',
      to: '/funds/new',
      cta: 'Start a fund',
    },
    {
      title: 'Send a receipt as the partner',
      body: 'Choose a demo receipt. The AI reads it in a few seconds and boxes every line on the photo, green if it fits, plum if not.',
      to: '/submit',
      cta: 'Send a receipt',
    },
    {
      title: 'Approve it as the charity',
      body: `Open request ${SAMPLE_REQUEST} and approve it. PayPal Payouts sends the money and the coin reaches “Paid.”`,
      to: `/requests/${SAMPLE_REQUEST}`,
      cta: `Review ${SAMPLE_REQUEST}`,
    },
    {
      title: `See what ${firstGift ? firstGift.donor.split(' ')[0] : 'a donor'}’s gift bought`,
      body: 'After the payout, the donor’s receipt shows which lines their money paid for, and the PayPal transaction that proves it.',
      to: firstGift ? `/gifts/${firstGift.gift_id}` : '/requests',
      cta: 'Open the receipt',
    },
  ]

  const stops = [
    { label: 'A donor gives', detail: 'with limits' },
    { label: 'A partner asks', detail: 'with a receipt' },
    { label: 'AI + a person', detail: 'check every line' },
    { label: 'PayPal pays', detail: 'the partner' },
    { label: 'The donor sees', detail: 'what it bought' },
  ]

  return (
    <>
      <header className="rounded-b-[36px] bg-band pb-[34px]">
        <TopBar active="How it works" />
        <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
          <h1 className="font-display m-0 max-w-[17ch] text-[clamp(34px,5.2vw,64px)] leading-[1.02] font-extrabold">
            Every donated dollar knows where it went
          </h1>
          <p className="mt-3 mb-0 max-w-[62ch] text-[18px] text-wine/80">
            Small charities promise donors their gifts will be used a certain way. Kindtrail reads every spending receipt with AI, checks it
            against the donors&rsquo; own words, pays the field partner through PayPal, and shows each donor what their money bought.
          </p>
          <a href="#try" className="mt-5 inline-block rounded-[14px] bg-wine px-[18px] py-3 font-bold text-white no-underline">
            Try it in four steps
          </a>
          <Trail stops={stops} current={4} />
        </div>
      </header>

      <main className="mx-auto max-w-[1160px] px-6 pt-[34px] pb-16">
        <section aria-labelledby="roles">
          <h2 id="roles" className="font-heading m-0 text-3xl font-bold">
            Three people, one trail
          </h2>
          <div className="mt-4 grid gap-[18px] md:grid-cols-3">
            {ROLES.map((r) => (
              <article key={r.title} className="flex flex-col rounded-[28px] bg-white px-[24px] py-[22px]">
                <span className={`grid size-12 place-items-center rounded-full text-lg font-extrabold ${r.tone}`} aria-hidden="true">
                  {r.initial}
                </span>
                <h3 className="font-heading mt-4 mb-1 text-xl font-bold">{r.title}</h3>
                <p className="m-0 flex-1 text-[15px] text-wine-2">{r.body}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {r.links.map((l) => (
                    <Link key={l.to} to={l.to} className="rounded-full bg-blush px-3.5 py-1.5 text-sm font-semibold text-wine no-underline hover:bg-petal">
                      {l.label}
                    </Link>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section id="try" aria-labelledby="steps" className="mt-12 scroll-mt-6">
          <h2 id="steps" className="font-heading m-0 text-3xl font-bold">
            Try it in four steps
          </h2>
          <p className="mt-1 mb-0 max-w-[62ch] text-[16px] text-wine-2">
            Each step is a different person&rsquo;s view. Everything runs on PayPal&rsquo;s sandbox, so no real money moves.
          </p>
          <ol className="m-0 mt-4 grid list-none gap-3 p-0">
            {steps.map((s, n) => (
              <li key={s.title} className="grid items-center gap-x-5 gap-y-3 rounded-[22px] bg-white px-[22px] py-[18px] sm:grid-cols-[auto_1fr_auto]">
                <span className="grid size-11 place-items-center rounded-full bg-wine text-lg font-extrabold text-white" aria-hidden="true">
                  {n + 1}
                </span>
                <div>
                  <h3 className="m-0 text-lg font-bold">{s.title}</h3>
                  <p className="m-0 text-[15px] text-wine-2">{s.body}</p>
                </div>
                <Link to={s.to} className="justify-self-start rounded-[14px] bg-pink px-4 py-2.5 font-bold text-white no-underline hover:bg-pink-hover sm:justify-self-end">
                  {s.cta}
                </Link>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="story" className="mt-12">
          <h2 id="story" className="font-heading m-0 text-3xl font-bold">
            The sample story
          </h2>
          <p className="mt-1 mb-0 max-w-[66ch] text-[16px] text-wine-2">
            So you can click straight through, the demo comes with one made-up story: a typhoon fund for kids in Hualien, Taiwan, three
            donors, and a receipt from Hualien Mountain Kitchen waiting for review. You can open your own fund in Start a fund. The demo
            resets itself after a quiet spell, and the review desk has a button to run it again.
          </p>
          <div className="mt-4 grid gap-[18px] lg:grid-cols-[7fr_5fr]">
            <article className="rounded-[28px] bg-white px-[24px] py-[22px]">
              <h3 className="font-heading m-0 text-xl font-bold">{fund.data?.name ?? 'The fund'}</h3>
              {fund.data?.donor_words && <p className="mt-2 mb-3 text-[16px] leading-snug">&ldquo;{fund.data.donor_words}&rdquo;</p>}
              <div className="flex flex-wrap gap-2">
                {(fund.data?.rules ?? []).map((r) => (
                  <span key={r.kind} className="rounded-full bg-blush px-[13px] py-1.5 text-sm">
                    <b className="font-semibold text-pink-deep">{r.kind}</b> {r.value}
                  </span>
                ))}
              </div>
              <p className="mt-3 mb-0 text-sm text-wine-2">A donor wrote the sentence in quotes; the AI turned it into these rules.</p>
            </article>
            <div className="grid gap-[18px]">
              <article className="rounded-[22px] bg-white px-[22px] py-5">
                <h3 className="font-heading m-0 text-xl font-bold">Donors</h3>
                <ul className="m-0 mt-2 list-none p-0 text-[15px]">
                  {(fund.data?.gifts ?? []).map((g) => (
                    <li key={g.gift_id} className="flex justify-between gap-3 py-1">
                      <Link to={`/gifts/${g.gift_id}`} className="font-semibold text-wine">
                        {g.donor}
                      </Link>
                      <span className="tabular-nums text-wine-2">gave {usd(g.given_cents / 100)}</span>
                    </li>
                  ))}
                </ul>
              </article>
              <article className="rounded-[22px] bg-white px-[22px] py-5">
                <h3 className="font-heading m-0 text-xl font-bold">The receipt</h3>
                <p className="mt-1 mb-0 text-[15px] text-wine-2">
                  {sample ? (
                    <>
                      <Link to={`/requests/${sample.id}`} className="font-semibold text-wine">
                        {sample.id}
                      </Link>
                      : {sample.partner} asks for {usd(sample.requested_cents / 100)}, {sample.fits} of {sample.lines} lines fit the fund.
                      Now {STATUS_TEXT[sample.status]}.
                    </>
                  ) : (
                    'Loading...'
                  )}
                </p>
              </article>
            </div>
          </div>
        </section>

        <footer className="mt-14 border-t-2 border-petal pt-5 text-sm text-wine-2">
          Built for the PayPal AI Hackathon with PayPal Orders v2, Payouts, Webhooks and Transaction Search, and Google Gemini.{' '}
          <a href="https://github.com/ch996811/kindtrail" className="font-semibold text-wine">
            Source code on GitHub
          </a>
          .
        </footer>
      </main>
    </>
  )
}
