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
  items: { key: string; receipt_text: string; label: string; qty: number; unit_cents: number; total_cents: number; verdict: 'fits' | 'blocked'; reason: string }[]
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

export const getRequest = (id: string) => call<RequestDetail>('GET', `/api/requests/${id}`)
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
    items: d.items.map((i) => ({
      id: i.key,
      receiptText: i.receipt_text,
      label: i.label,
      qty: i.qty,
      unitPrice: i.unit_cents / 100,
      verdict: i.verdict,
      reason: i.reason,
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
