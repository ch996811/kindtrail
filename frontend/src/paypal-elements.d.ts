// The PayPal SDK v6 registers <paypal-button> as a custom element.
import type { DetailedHTMLProps, HTMLAttributes } from 'react'

declare module 'react' {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      'paypal-button': DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & { type?: string }
    }
  }
}
