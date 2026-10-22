import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router'

// Each page is its own chunk, so the first visit only downloads the page it lands on.
const ReviewDesk = lazy(() => import('./pages/ReviewDesk').then((m) => ({ default: m.ReviewDesk })))
const SubmitReceipt = lazy(() => import('./pages/SubmitReceipt').then((m) => ({ default: m.SubmitReceipt })))
const StartFund = lazy(() => import('./pages/StartFund').then((m) => ({ default: m.StartFund })))
const ThankYous = lazy(() => import('./pages/ThankYous').then((m) => ({ default: m.ThankYous })))
const ImpactReceipt = lazy(() => import('./pages/ImpactReceipt').then((m) => ({ default: m.ImpactReceipt })))
const Give = lazy(() => import('./pages/Give').then((m) => ({ default: m.Give })))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

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
              <Route path="/" element={<ReviewDesk requestId="KT-0142" />} />
              <Route path="/requests/:id" element={<RequestPage />} />
              <Route path="/submit" element={<SubmitReceipt />} />
              <Route path="/funds/new" element={<StartFund />} />
              <Route path="/requests/:id/thanks" element={<ThankYous />} />
              <Route path="/gifts/:id" element={<ImpactReceipt />} />
              <Route path="/give" element={<Give />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </MotionConfig>
    </QueryClientProvider>
  )
}
