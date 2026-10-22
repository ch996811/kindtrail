// Client for the FastAPI backend. Money arrives in integer cents; the UI model uses dollars.
import type { Gift, ReviewRequest } from './model'

export type RequestStatus = 'reviewed' | 'paying' | 'paid' | 'returned'

export interface RequestDetail {
  id: string
  status: RequestStatus
  purpose: string
  submitted_at: string
  approved_by: string | null
  partner: { id: string; name: string; region: string }
  fund: { code: string; name: string; donor_words: string; rules: { kind: ReviewRequest['rules'][number]['kind']; value: string }[] }
  shop: { name: string; branch: string; printed_at: string; region: string }
  receipt_url: string | null
  items: { key: string; receipt_text: string; label: string; qty: number; unit_cents: number; total_cents: number; category: string | null; box: [number, number, number, number] | null; verdict: 'fits' | 'blocked'; reason: string }[]
  flags: { kind: string; severity: 'block' | 'check'; message: string }[]
  ai: { model: string; cached: boolean; seconds?: number } | null
  requested_cents: number
  payable_cents: number
  funding: { gift_id: number; donor: string; date: string; given_cents: number; used_here_cents: number; left_cents: number }[]
  shortfall_cents: number
  checks: { month_spent_cents: number; month_cap_cents: number }
  payout: { status: string; amount_cents: number; fee_cents: number | null; transaction_id: string | null } | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new ApiError(r.status, data.message ?? `Request failed (${r.status})`)
  return data as T
}

export interface FundSummary {
  code: string
  name: string
  donor_words: string
  rules: { kind: string; value: string }[]
  received_cents: number
  spent_cents: number
  available_cents: number
  gifts: { gift_id: number; donor: string }[]
}

export interface DemoReceipt {
  name: string
  url: string
}

export interface Policy {
  region: string | null
  allowed: string[]
  never: string[]
  beneficiaries: string | null
  until: string | null // YYYY-MM-DD
}

export interface ParsedLimits {
  policy: Policy
  rules: { kind: string; value: string }[]
  model: string
  cached: boolean
  seconds: number
}

export interface Categories {
  categories: { key: string; label: string }[]
  always_never: string[]
}

export interface PreviewRow {
  name: string
  shop: string
  region: string
  lines: number
  fits: number
  requested_cents: number
  payable_cents: number
  blocked: { label: string; reason: string }[]
  flags: { kind: string; severity: string; message: string }[]
}

export const parseLimits = (donorWords: string) => call<ParsedLimits>('POST', '/api/limits/parse', { donor_words: donorWords })
export const getCategories = () => call<Categories>('GET', '/api/limits/categories')
export const previewPolicy = (policy: Policy) => call<PreviewRow[]>('POST', '/api/limits/preview', policy)
export const listFunds = () => call<{ code: string; name: string }[]>('GET', '/api/funds')
export const createFund = (body: { name: string; donor_words: string; policy: Policy }) => call<FundSummary>('POST', '/api/funds', body)

export interface GiftImpact {
  gift: { id: number; donor: string; amount_cents: number; given_at: string; source: 'paypal' | 'seed'; paypal_capture_id: string | null }
  fund: { code: string; name: string; rules: { kind: string; value: string }[] }
  used_cents: number
  left_cents: number
  spends: {
    request_id: string
    status: RequestStatus
    partner: string
    purpose: string
    shop: { name: string; branch: string; printed_at: string; region: string }
    receipt_url: string | null
    approved_by: string | null
    approved_at: string | null
    paid_at: string | null
    payout_transaction_id: string | null
    payable_cents: number
    your_cents: number
    items: { key: string; label: string; total_cents: number; yours_cents: number; box: [number, number, number, number] | null }[]
    donors: { donor: string; cents: number; you: boolean }[]
    submitted_at: string
    refused: { label: string; total_cents: number; reason: string }[]
  }[]
}

export const getGiftImpact = (id: string | number) => call<GiftImpact>('GET', `/api/gifts/${id}/impact`)
export const getConfig = () => call<{ paypal_client_id: string; paypal_env: string }>('GET', '/api/config')
export const createGift = (body: { fund_code: string; donor_name: string; amount_cents: number }) =>
  call<{ gift_id: number; order_id: string; approve_url: string | null }>('POST', '/api/gifts', body)
export const captureGift = (orderId: string) =>
  call<{ id: number; amount_cents: number; donor_name: string; paypal_capture_id: string; fund_code: string }>('POST', `/api/gifts/${orderId}/capture`)

export const getRequest = (id: string) => call<RequestDetail>('GET', `/api/requests/${id}`)
export const getFund = (code: string) => call<FundSummary>('GET', `/api/funds/${code}`)
export const listDemoReceipts = () => call<DemoReceipt[]>('GET', '/api/demo/receipts')

/** Upload a receipt photo; the backend reads it with the AI and judges every line. */
export async function submitReceipt(form: { fundCode: string; partnerId: string; purpose: string; photo: File }) {
  const body = new FormData()
  body.append('fund_code', form.fundCode)
  body.append('partner_id', form.partnerId)
  body.append('purpose', form.purpose)
  body.append('receipt', form.photo)
  const r = await fetch('/api/requests', { method: 'POST', body })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new ApiError(r.status, data.message ?? `Upload failed (${r.status})`)
  return data as RequestDetail
}
export const approveRequest = (id: string, approver: string) => call<RequestDetail>('POST', `/api/requests/${id}/approve`, { approver })
export const refreshRequest = (id: string) => call<RequestDetail>('POST', `/api/requests/${id}/refresh`)

const TONES: Gift['tone'][] = ['pink', 'sun', 'mint']
const shortDate = (iso: string) => new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

/** Shape the API response into the model the review desk components draw. */
export function toReviewModel(d: RequestDetail): ReviewRequest {
  return {
    id: d.id,
    partner: d.partner.name,
    fund: d.fund.name,
    purpose: d.purpose,
    submitted: shortDate(d.submitted_at),
    shop: { name: d.shop.name, branch: d.shop.branch, printedAt: d.shop.printed_at },
    receiptUrl: d.receipt_url ?? undefined,
    flags: d.flags,
    aiModel: d.ai?.model,
    items: d.items.map((i) => ({
      id: i.key,
      receiptText: i.receipt_text,
      label: i.label,
      qty: i.qty,
      unitPrice: i.unit_cents / 100,
      verdict: i.verdict,
      reason: i.reason,
      box: i.box ?? undefined,
    })),
    donorWords: d.fund.donor_words,
    rules: d.fund.rules,
    gifts: d.funding.map((f, n) => ({
      donor: f.donor,
      initial: f.donor === 'Anonymous' ? '?' : f.donor.charAt(0).toUpperCase(),
      date: shortDate(f.date),
      given: f.given_cents / 100,
      usedHere: f.used_here_cents / 100,
      left: f.left_cents / 100,
      tone: TONES[n % TONES.length],
    })),
    checks: {
      duplicateReceipt: false, // TODO(W2): receipt fingerprinting
      shopInRegion: d.shop.branch.replace(/ branch$/, ''),
      monthSpent: d.checks.month_spent_cents / 100,
      monthCap: d.checks.month_cap_cents / 100,
    },
  }
}
