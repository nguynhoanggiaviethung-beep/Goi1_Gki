const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export type ScenarioCase = {
  key: 'bullish' | 'base' | 'bearish'
  label: string
  earnings_growth_pct: number
  target_pe: number
  projected_eps: number
  estimated_price: number
  expected_return_pct: number
  assessment: string
  assumption_basis: string
  evidence: { claim: string; value: number; unit: string; formula: string; source: string; period: string; retrieved_at?: string | null }[]
}

export type LiveScenario = {
  ticker: string
  currency: string
  horizon_months: number
  current_price: number
  scenarios: ScenarioCase[]
  probability_weighted_value: number | null
  data_confidence?: { score: number; label: string; basis: string }
  scenario_method?: { growth_observations: number; pe_observations: number; growth_winsorized_count: number; status: string; horizon_note: string }
  probabilities_pct?: { bullish: number; base: number; bearish: number } | null
  sensitivity_grid?: { growth_pct: number[]; target_pe: number[]; cells: { growth_pct: number; prices: { target_pe: number; estimated_price: number }[] }[] }
  configuration_warnings: string[]
  limitations: string[]
  data_status?: { provider: string; retrieved_at: string; freshness: string; price_period: string; eps_period: string; eps_basis: string; growth_basis: string; pe_basis: string }
}

export type ScenarioPayload = {
  ticker: string
  earnings_growth_pct?: number
  target_pe?: number
  horizon_months: 3 | 6 | 12
  earnings_growth_basis: 'annualized' | 'holding_period'
  overrides: Record<string, { earnings_growth_pct?: number; target_pe?: number }>
  probabilities_pct?: { bullish: number; base: number; bearish: number }
  dividend_yield_pct: number
  buy_threshold_pct: number
  sell_threshold_pct: number
  horizon_thresholds_pct: Record<number, { buy: number; sell: number }>
  sensitivity_growth_pct: number[]
  sensitivity_pe: number[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
    })
  } catch {
    throw new Error('Không kết nối được backend. Hãy khởi động FastAPI tại cổng 8000.')
  }
  if (!response.ok) {
    let message = `Backend trả lỗi ${response.status}`
    try {
      const body = await response.json()
      const detail = body.detail
      message = typeof detail === 'string' ? detail : JSON.stringify(detail ?? body)
    } catch { /* use status fallback */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),
  liveScenario: (payload: ScenarioPayload) => request<LiveScenario>('/api/scenario/live', { method: 'POST', body: JSON.stringify(payload) }),
  profile: (payload: Record<string, unknown>) => request<Record<string, unknown>>('/api/recommendation/profile', { method: 'POST', body: JSON.stringify(payload) }),
  livePeers: (payload: { ticker: string; industry: string; peer_tickers: string[] }) => request<Record<string, unknown>>('/api/peers/live-compare', { method: 'POST', body: JSON.stringify(payload) }),
  annualAvailability: (ticker: string) => request<{ ticker: string; years: { year: number; file_name: string; size_mb: string; cached: boolean }[]; warning: string; dataset_doi: string }>(`/api/reports/annual/available?ticker=${encodeURIComponent(ticker)}`),
  compareAnnualReports: (payload: { ticker: string; years: number[] }) => request<Record<string, unknown>>('/api/reports/annual/compare-language', { method: 'POST', body: JSON.stringify(payload) }),
  financialReports: (ticker: string, exchange = 'AUTO', years = 5) => request<Record<string, unknown>>(`/api/reports/financial/${encodeURIComponent(ticker)}?exchange=${exchange}&years=${years}`),
  companyNews: (ticker: string, companyName = '', companyWebsite = '') => request<Record<string, unknown>>(`/api/news/company/${encodeURIComponent(ticker)}?company_name=${encodeURIComponent(companyName)}&company_website=${encodeURIComponent(companyWebsite)}`),
  annualDownloadUrl: (ticker: string, year: number) => `${API_BASE}/api/reports/annual/${encodeURIComponent(ticker)}/${year}/download`,
  async scenarioPdf(payload: ScenarioPayload, groups: string[], detail: string, includeChart: boolean, purpose: string) {
    const response = await fetch(`${API_BASE}/api/scenario/live/report.pdf`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, report: { purpose, horizon_months: payload.horizon_months, metric_groups: groups, detail_level: detail, include_chart: includeChart } }),
    })
    if (!response.ok) {
      let message = `Backend trả lỗi ${response.status}`
      try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : message } catch { /* ignore */ }
      throw new Error(message)
    }
    return response.blob()
  },
}

export function formatNumber(value: number | null | undefined, digits = 0) {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('vi-VN', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)
}
