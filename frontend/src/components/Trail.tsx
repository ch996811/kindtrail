import { animate, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { useLayoutEffect, useRef, useState } from 'react'

// The trail is drawn in a 1000 x 90 design space, then stretched horizontally to the real
// width so strokes stay even and the stop circles stay round at any screen size.
const H = 90
const START: [number, number] = [10, 60]
const SEGMENTS: { cmd: 'C' | 'S'; pts: [number, number][] }[] = [
  { cmd: 'C', pts: [[120, 10], [160, 85], [250, 50]] },
  { cmd: 'S', pts: [[400, 10], [500, 45]] },
  { cmd: 'S', pts: [[650, 85], [750, 40]] },
  { cmd: 'S', pts: [[900, 15], [990, 45]] },
]
const STOPS = [START, ...SEGMENTS.map((s) => s.pts[s.pts.length - 1])]

function pathUpTo(k: number, segments: number) {
  const p = ([x, y]: [number, number]) => `${(x * k).toFixed(1)} ${y}`
  return [`M${p(START)}`, ...SEGMENTS.slice(0, segments).map((s) => `${s.cmd} ${s.pts.map(p).join(', ')}`)].join(' ')
}

export interface TrailStop {
  label: string
  detail?: string
}

/** The money's journey: a coin walks the path up to the current stop. */
export function Trail({ stops, current }: { stops: TrailStop[]; current: number }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const fullRef = useRef<SVGPathElement>(null)
  const prefixRefs = useRef<(SVGPathElement | null)[]>([])
  const shownStop = useRef<number | null>(null)
  const [width, setWidth] = useState(1000)
  const reduceMotion = useReducedMotion()

  const walked = useMotionValue(0)
  const dash = useTransform(walked, (l) => `${l} 100000`)
  const coinX = useTransform(walked, (l) => fullRef.current?.getPointAtLength(l).x ?? START[0])
  const coinY = useTransform(walked, (l) => fullRef.current?.getPointAtLength(l).y ?? START[1])

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    // Measure now so the first paint is right; ResizeObserver only reports once the tab renders.
    setWidth(Math.max(320, el.getBoundingClientRect().width))
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(320, entry.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useLayoutEffect(() => {
    const target = current === 0 ? 0 : (prefixRefs.current[current]?.getTotalLength() ?? 0)
    const firstShow = shownStop.current === null
    const moved = shownStop.current !== current
    shownStop.current = current
    if (reduceMotion || !moved) {
      walked.set(target) // resize or no motion wanted: jump, don't replay
      return
    }
    const controls = animate(walked, target, {
      duration: firstShow ? 1.8 : 1.2,
      delay: firstShow ? 0.3 : 0,
      ease: [0.4, 0, 0.2, 1],
    })
    return () => controls.stop()
  }, [current, width, reduceMotion, walked])

  const k = width / 1000
  const full = pathUpTo(k, SEGMENTS.length)

  return (
    <div className="mt-6" aria-label="Where this money is on its trail">
      <div ref={wrapRef}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} className="block overflow-visible" aria-hidden="true">
          {SEGMENTS.map((_, i) => (
            <path
              key={i}
              ref={(el) => {
                prefixRefs.current[i + 1] = el
              }}
              d={pathUpTo(k, i + 1)}
              fill="none"
              stroke="none"
            />
          ))}
          <path d={full} fill="none" stroke="rgb(58 11 37 / 0.3)" strokeWidth={4} strokeLinecap="round" strokeDasharray="1 12" />
          <motion.path ref={fullRef} d={full} fill="none" className="stroke-wine" strokeWidth={4} strokeLinecap="round" style={{ strokeDasharray: dash }} />
          {STOPS.map(([x, y], i) => (
            <circle
              key={i}
              cx={x * k}
              cy={y}
              r={i === current ? 11 : 9}
              strokeWidth={4}
              className={i <= current ? 'fill-wine stroke-wine' : 'fill-white stroke-wine'}
            />
          ))}
          <motion.circle r={12} cx={coinX} cy={coinY} className="fill-coin stroke-wine" strokeWidth={2.5} />
        </svg>
      </div>
      <ol className="mt-1.5 grid grid-cols-5 text-sm max-sm:text-xs">
        {stops.map((s, i) => (
          <li
            key={s.label}
            className={[
              'text-wine/70',
              i === 0 ? 'text-left' : i === stops.length - 1 ? 'text-right' : 'text-center',
              i !== current && i !== 0 && i !== stops.length - 1 ? 'max-sm:invisible' : '',
            ].join(' ')}
            aria-current={i === current ? 'step' : undefined}
          >
            <strong
              className={
                i === current
                  ? 'inline-block rounded-full bg-wine px-2.5 py-px text-[15px] font-bold text-white max-sm:px-2 max-sm:text-[13px]'
                  : 'block text-[15px] font-bold text-wine max-sm:text-[13px]'
              }
            >
              {s.label}
            </strong>
            {i !== current && s.detail && <span className="block">{s.detail}</span>}
          </li>
        ))}
      </ol>
    </div>
  )
}
