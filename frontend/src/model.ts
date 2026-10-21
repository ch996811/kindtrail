// The review desk's view model. Real data comes from the API (see api.ts toReviewModel).

export type Verdict = 'fits' | 'blocked'

export interface LineItem {
  id: string
  receiptText: string // what is printed on the receipt
  label: string // plain-language name shown in the review
  qty: number
  unitPrice: number
  verdict: Verdict
  reason: string
}

export interface Gift {
  donor: string
  initial: string
  date: string
  given: number
  usedHere: number
  left?: number // what is still unspent in this gift after every allocation
  tone: 'pink' | 'sun' | 'mint'
}

export interface FundRule {
  kind: 'Where' | 'For' | 'Who' | 'Never' | 'Until'
  value: string
}

export interface ReviewRequest {
  id: string
  partner: string
  fund: string
  purpose: string
  submitted: string
  shop: { name: string; branch: string; printedAt: string }
  items: LineItem[]
  donorWords: string
  rules: FundRule[]
  gifts: Gift[]
  checks: { duplicateReceipt: boolean; shopInRegion: string; monthSpent: number; monthCap: number }
}

export const lineTotal = (item: LineItem) => Math.round(item.qty * item.unitPrice * 100) / 100

export const usd = (n: number) => `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
