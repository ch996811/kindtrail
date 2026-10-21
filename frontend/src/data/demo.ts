// Demo data for the review desk until the FastAPI backend serves real requests.

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

export const demoRequest: ReviewRequest = {
  id: 'KT-0142',
  partner: 'Hualien Mountain Kitchen',
  fund: 'Hualien Kids Typhoon Fund',
  purpose: 'typhoon families',
  submitted: 'Oct 24',
  shop: { name: 'HUALIEN HOME MART', branch: "Ji'an branch", printedAt: '2026-10-24 14:32' },
  items: [
    { id: 'tarp', receiptText: 'Waterproof tarp 3x4m', label: '4 waterproof tarps', qty: 4, unitPrice: 8, verdict: 'fits', reason: 'Shelter, an allowed use' },
    { id: 'rice', receiptText: 'Rice 10 kg', label: '2 bags of rice, 10 kg', qty: 2, unitPrice: 12, verdict: 'fits', reason: 'Food, an allowed use' },
    { id: 'coat', receiptText: 'Kids raincoat', label: "6 kids' raincoats", qty: 6, unitPrice: 3.6, verdict: 'fits', reason: 'For children, exactly who the fund serves' },
    { id: 'card', receiptText: 'Prepaid gift card', label: '1 prepaid gift card', qty: 1, unitPrice: 8.8, verdict: 'blocked', reason: "Cash equivalents break the donors' limits. The partner can pay this from general funds." },
  ],
  donorWords: 'Please use my gift only for kids in Hualien who lost their homes in the typhoon. Not for staff costs.',
  rules: [
    { kind: 'Where', value: 'Hualien County' },
    { kind: 'For', value: "shelter, food, kids' supplies" },
    { kind: 'Who', value: 'families with children' },
    { kind: 'Never', value: 'staff, cash equivalents' },
    { kind: 'Until', value: 'Dec 31' },
  ],
  gifts: [
    { donor: 'Mei L.', initial: 'M', date: 'Oct 21', given: 50, usedHere: 50, tone: 'pink' },
    { donor: 'Jordan P.', initial: 'J', date: 'Oct 22', given: 20, usedHere: 20, tone: 'sun' },
    { donor: 'Anonymous', initial: '?', date: 'Oct 23', given: 25, usedHere: 7.6, tone: 'mint' },
  ],
  checks: { duplicateReceipt: false, shopInRegion: "Ji'an", monthSpent: 480, monthCap: 2000 },
}

export const lineTotal = (item: LineItem) => Math.round(item.qty * item.unitPrice * 100) / 100

export const usd = (n: number) => `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
