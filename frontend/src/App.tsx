import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router'
import { ReviewDesk } from './pages/ReviewDesk'
import { StartFund } from './pages/StartFund'
import { SubmitReceipt } from './pages/SubmitReceipt'

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
          <Routes>
            <Route path="/" element={<ReviewDesk requestId="KT-0142" />} />
            <Route path="/requests/:id" element={<RequestPage />} />
            <Route path="/submit" element={<SubmitReceipt />} />
            <Route path="/funds/new" element={<StartFund />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </MotionConfig>
    </QueryClientProvider>
  )
}
