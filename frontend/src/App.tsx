import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Link, Route, Routes, useParams } from 'react-router'
import { TopBar } from './components/TopBar'

// Each page is its own chunk, so the first visit only downloads the page it lands on.
const Home = lazy(() => import('./pages/Home').then((m) => ({ default: m.Home })))
const Requests = lazy(() => import('./pages/Requests').then((m) => ({ default: m.Requests })))
const ReviewDesk = lazy(() => import('./pages/ReviewDesk').then((m) => ({ default: m.ReviewDesk })))
const SubmitReceipt = lazy(() => import('./pages/SubmitReceipt').then((m) => ({ default: m.SubmitReceipt })))
const StartFund = lazy(() => import('./pages/StartFund').then((m) => ({ default: m.StartFund })))
const ThankYous = lazy(() => import('./pages/ThankYous').then((m) => ({ default: m.ThankYous })))
const ImpactReceipt = lazy(() => import('./pages/ImpactReceipt').then((m) => ({ default: m.ImpactReceipt })))
const Give = lazy(() => import('./pages/Give').then((m) => ({ default: m.Give })))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

function NotFound() {
  return (
    <header className="rounded-b-[36px] bg-band pb-12">
      <TopBar />
      <div className="mx-auto max-w-[1160px] px-6 pt-[18px]">
        <h1 className="font-display m-0 text-[clamp(30px,4.4vw,52px)] leading-[1.06] font-extrabold">There&rsquo;s no page here</h1>
        <p className="mt-2.5 mb-5 text-[17px] text-wine/80">The link may be old: the demo starts over now and then.</p>
        <Link to="/" className="inline-block rounded-[14px] bg-pink px-[18px] py-3 font-bold text-white no-underline hover:bg-pink-hover">
          See how Kindtrail works
        </Link>
      </div>
    </header>
  )
}

function RequestPage() {
  const { id = 'KT-0142' } = useParams()
  return <ReviewDesk key={id} requestId={id} />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <BrowserRouter>
          <Suspense fallback={<div className="min-h-[340px] rounded-b-[36px] bg-band" aria-busy="true" />}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/requests" element={<Requests />} />
              <Route path="/requests/:id" element={<RequestPage />} />
              <Route path="/submit" element={<SubmitReceipt />} />
              <Route path="/funds/new" element={<StartFund />} />
              <Route path="/requests/:id/thanks" element={<ThankYous />} />
              <Route path="/gifts/:id" element={<ImpactReceipt />} />
              <Route path="/give" element={<Give />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </MotionConfig>
    </QueryClientProvider>
  )
}
