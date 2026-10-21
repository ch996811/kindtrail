import { MotionConfig } from 'motion/react'
import { demoRequest } from './data/demo'
import { ReviewDesk } from './pages/ReviewDesk'

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <ReviewDesk request={demoRequest} />
    </MotionConfig>
  )
}
