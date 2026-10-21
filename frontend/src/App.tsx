import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { ReviewDesk } from './pages/ReviewDesk'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <ReviewDesk requestId={new URLSearchParams(window.location.search).get('request') ?? 'KT-0142'} />
      </MotionConfig>
    </QueryClientProvider>
  )
}
