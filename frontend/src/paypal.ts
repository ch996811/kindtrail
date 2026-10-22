// PayPal JavaScript SDK v6, sandbox only (https://developer.paypal.com/sdk/js/set-up).
// Flow: createInstance -> findEligibleMethods -> createPayPalOneTimePaymentSession -> session.start on click.

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    paypal?: any
  }
}

const SDK_URL = 'https://www.sandbox.paypal.com/web-sdk/v6/core'
let loading: Promise<any> | null = null

/** Load the SDK script once per page and resolve with `window.paypal`. */
export function loadPayPalSdk(): Promise<any> {
  if (window.paypal) return Promise.resolve(window.paypal)
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SDK_URL
    script.async = true
    script.onload = () => (window.paypal ? resolve(window.paypal) : reject(new Error('PayPal SDK loaded without window.paypal')))
    script.onerror = () => {
      loading = null
      reject(new Error('Could not load the PayPal SDK'))
    }
    document.head.appendChild(script)
  })
  return loading
}

export interface PayPalButtonSession {
  start: (options: { presentationMode: 'auto' | 'popup' | 'modal' | 'redirect' }, order: Promise<{ orderId: string }>) => Promise<void>
}

/** Set up a one-time PayPal payment, or report why the button can't be shown. */
export async function setUpPayPal(
  clientId: string,
  callbacks: { onApprove: (orderId: string) => void; onCancel: () => void; onError: (e: unknown) => void },
): Promise<PayPalButtonSession | null> {
  const paypal = await loadPayPalSdk()
  // English to match the rest of the UI, whatever the browser's language.
  const sdk = await paypal.createInstance({ clientId, components: ['paypal-payments'], locale: 'en-US' })
  const methods = await sdk.findEligibleMethods({ currencyCode: 'USD' })
  if (!methods.isEligible('paypal')) return null
  return sdk.createPayPalOneTimePaymentSession({
    onApprove: (data: { orderId: string }) => callbacks.onApprove(data.orderId),
    onCancel: () => callbacks.onCancel(),
    onError: (e: unknown) => callbacks.onError(e),
  })
}
