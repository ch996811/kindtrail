import { motion } from 'motion/react'
import type { LineItem } from '../model'

interface Props {
  src: string
  alt: string
  items: LineItem[]
  activeItem: string | null
  onActivate: (id: string | null) => void
  delay?: number // seconds before the first box appears
  highlight?: Set<string> // if given, other boxes fade to a thin outline
}

/** A receipt photo with a box on every line the AI read, green if it fits the fund, plum if not. */
export function BoxedPhoto({ src, alt, items, activeItem, onActivate, delay = 1.9, highlight }: Props) {
  return (
    <div className="relative mx-auto w-full max-w-[400px] overflow-hidden rounded-xl shadow-[0_18px_30px_-20px_rgb(58_11_37/0.55)]">
      <img src={src} alt={alt} className="block w-full" />
      {items.map((it, i) => {
        if (!it.box) return null
        const [y0, x0, y1, x1] = it.box
        const ok = it.verdict === 'fits'
        const active = activeItem === it.id
        const faded = highlight && !highlight.has(it.id)
        return (
          <motion.button
            key={it.id}
            type="button"
            aria-label={`${it.label}: ${ok ? 'fits the fund' : 'not allowed'}`}
            onMouseEnter={() => onActivate(it.id)}
            onMouseLeave={() => onActivate(null)}
            onFocus={() => onActivate(it.id)}
            onBlur={() => onActivate(null)}
            initial={{ opacity: 0, scale: 1.08 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: delay + i * 0.15, duration: 0.3, ease: 'easeOut' }}
            className={[
              'absolute cursor-default rounded-[6px] border-[2.5px] transition-[background-color,box-shadow]',
              faded ? 'border-wine/25 bg-transparent' : ok ? 'border-mint bg-mint/10' : 'border-plum bg-plum/20',
              active ? (ok ? 'bg-mint/25 shadow-[0_0_0_4px_rgb(18_133_95/0.25)]' : 'bg-plum/35 shadow-[0_0_0_4px_rgb(91_22_64/0.3)]') : '',
            ].join(' ')}
            style={{ top: `${y0 / 10}%`, left: `${x0 / 10}%`, width: `${(x1 - x0) / 10}%`, height: `${(y1 - y0) / 10}%` }}
          />
        )
      })}
    </div>
  )
}
