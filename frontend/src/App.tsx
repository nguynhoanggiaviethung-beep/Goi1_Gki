import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import { api, formatNumber } from './lib/api'
import type { LiveScenario, ScenarioPayload } from './lib/api'

type Page = 'analysis' | 'peers' | 'screener' | 'reports' | 'about'
type Profile = 'conservative' | 'balanced' | 'aggressive'
const profiles: { id: Profile; name: string; note: string }[] = [
  { id: 'conservative', name: 'Thận trọng', note: 'Ưu tiên kiểm soát mức giảm' },
  { id: 'balanced', name: 'Cân bằng', note: 'Cân đối lợi suất và biến động' },
  { id: 'aggressive', name: 'Chấp nhận rủi ro', note: 'Chấp nhận mức dao động cao hơn' },
]
const sectionOptions = [
  ['executive_summary', 'Tóm tắt khuyến nghị'], ['valuation', 'Định giá'], ['scenario', 'Kịch bản'],
  ['sensitivity', 'Độ nhạy'], ['financial_analysis', 'Phân tích tài chính'], ['risk', 'Rủi ro doanh nghiệp'],
  ['market_risk', 'Rủi ro thị trường'], ['evidence', 'Thẻ bằng chứng'], ['charts', 'Biểu đồ'], ['final_assessment', 'Đánh giá cuối'],
]
const purposeSections = {
  full: ['executive_summary', 'valuation', 'scenario', 'sensitivity', 'financial_analysis', 'risk', 'market_risk', 'evidence', 'charts', 'final_assessment'],
  long_term: ['executive_summary', 'scenario', 'financial_analysis', 'valuation', 'risk', 'evidence', 'final_assessment'],
  trader: ['executive_summary', 'scenario', 'valuation', 'market_risk', 'risk', 'charts', 'final_assessment'],
  one_pager: ['executive_summary', 'valuation', 'scenario', 'final_assessment'],
  committee: ['executive_summary', 'scenario', 'valuation', 'sensitivity', 'financial_analysis', 'risk', 'market_risk', 'evidence', 'charts', 'final_assessment'],
}

function App() {
  const [page, setPage] = useState<Page>('analysis')
  const [apiOnline, setApiOnline] = useState(false)
  const [ticker, setTicker] = useState('FPT')
  const [industry, setIndustry] = useState('Công nghệ thông tin')
  const [horizon, setHorizon] = useState<3 | 6 | 12>(12)
  const growthBasis = 'annualized' as const
  const [horizonThresholds, setHorizonThresholds] = useState<Record<number, { buy: number; sell: number }>>({ 3: { buy: 5, sell: -5 }, 6: { buy: 8, sell: -8 }, 12: { buy: 12, sell: -10 } })
  const [profile, setProfile] = useState<Profile>('balanced')
  const [growth, setGrowth] = useState('')
  const [targetPe, setTargetPe] = useState('')
  const [dividendYield, setDividendYield] = useState('0')
  const [bullGrowth, setBullGrowth] = useState('')
  const [bullPe, setBullPe] = useState('')
  const [baseGrowth, setBaseGrowth] = useState('')
  const [basePe, setBasePe] = useState('')
  const [bearGrowth, setBearGrowth] = useState('')
  const [bearPe, setBearPe] = useState('')
  const [probabilityOn, setProbabilityOn] = useState(false)
  const [probBull, setProbBull] = useState('25')
  const [probBase, setProbBase] = useState('50')
  const [probBear, setProbBear] = useState('25')
  const [sensitivityGrowth, setSensitivityGrowth] = useState('0,10,20')
  const [sensitivityPe, setSensitivityPe] = useState('10,15,20')
  const [reportSections, setReportSections] = useState(['executive_summary', 'valuation', 'scenario', 'sensitivity', 'evidence', 'final_assessment'])
  const [reportPurpose, setReportPurpose] = useState<'full' | 'long_term' | 'trader' | 'one_pager' | 'committee'>('full')
  const [detail, setDetail] = useState('standard')
  const [includeChart, setIncludeChart] = useState(true)
  const [result, setResult] = useState<LiveScenario | null>(null)
  const [profileResult, setProfileResult] = useState<Record<string, unknown> | null>(null)
  const [busy, setBusy] = useState(false)
  const [pdfBusy, setPdfBusy] = useState(false)
  const [peerCodes, setPeerCodes] = useState('FPT, CMG, ELC')
  const [peerResult, setPeerResult] = useState<Record<string, unknown> | null>(null)
  const [peerBusy, setPeerBusy] = useState(false)
  const [screenerCodes, setScreenerCodes] = useState('FPT, ACB, VNM, HPG, MWG')
  const [screenerRows, setScreenerRows] = useState<{ ticker: string; price?: number; returnPct?: number; assessment?: string; error?: string }[]>([])
  const [screenerBusy, setScreenerBusy] = useState(false)
  const [reportTicker, setReportTicker] = useState('FPT')
  const [companyName, setCompanyName] = useState('')
  const [companyWebsite, setCompanyWebsite] = useState('')
  const [annualInfo, setAnnualInfo] = useState<{ years: { year: number; file_name: string; size_mb: string; cached: boolean }[]; warning: string; dataset_doi: string } | null>(null)
  const [selectedReportYears, setSelectedReportYears] = useState<number[]>([])
  const [languageResult, setLanguageResult] = useState<Record<string, unknown> | null>(null)
  const [financialResult, setFinancialResult] = useState<Record<string, unknown> | null>(null)
  const [newsResult, setNewsResult] = useState<Record<string, unknown> | null>(null)
  const [reportBusy, setReportBusy] = useState(false)
  const [reportError, setReportError] = useState('')
  const [error, setError] = useState('')
  const [peerError, setPeerError] = useState('')
  const [activeTab, setActiveTab] = useState('Tóm tắt')
  const scenarioInputs: { label: string; growth: string; setGrowth: (value: string) => void; pe: string; setPe: (value: string) => void }[] = [
    { label: 'Tích cực', growth: bullGrowth, setGrowth: setBullGrowth, pe: bullPe, setPe: setBullPe },
    { label: 'Cơ sở', growth: baseGrowth, setGrowth: setBaseGrowth, pe: basePe, setPe: setBasePe },
    { label: 'Tiêu cực', growth: bearGrowth, setGrowth: setBearGrowth, pe: bearPe, setPe: setBearPe },
  ]

  useEffect(() => { api.health().then(() => setApiOnline(true)).catch(() => setApiOnline(false)) }, [])

  const payload = useMemo<ScenarioPayload>(() => {
    const overrides: ScenarioPayload['overrides'] = {}
    const cases = [
      ['bullish', bullGrowth, bullPe], ['base', baseGrowth, basePe], ['bearish', bearGrowth, bearPe],
    ] as const
    for (const [key, g, pe] of cases) {
      const data: { earnings_growth_pct?: number; target_pe?: number } = {}
      if (g.trim()) data.earnings_growth_pct = Number(g)
      if (pe.trim()) data.target_pe = Number(pe)
      if (Object.keys(data).length) overrides[key] = data
    }
    const sensitivities = (value: string) => value.split(',').map((item) => Number(item.trim())).filter(Number.isFinite)
    return {
      ticker: ticker.trim().toUpperCase(),
      ...(growth.trim() ? { earnings_growth_pct: Number(growth) } : {}),
      ...(targetPe.trim() ? { target_pe: Number(targetPe) } : {}),
      horizon_months: horizon,
      earnings_growth_basis: growthBasis,
      overrides,
      ...(probabilityOn ? { probabilities_pct: { bullish: Number(probBull), base: Number(probBase), bearish: Number(probBear) } } : {}),
      dividend_yield_pct: Number(dividendYield) || 0,
      buy_threshold_pct: horizonThresholds[horizon].buy,
      sell_threshold_pct: horizonThresholds[horizon].sell,
      horizon_thresholds_pct: horizonThresholds,
      sensitivity_growth_pct: sensitivities(sensitivityGrowth),
      sensitivity_pe: sensitivities(sensitivityPe),
    }
  }, [ticker, growth, targetPe, horizon, growthBasis, horizonThresholds, bullGrowth, bullPe, baseGrowth, basePe, bearGrowth, bearPe, probabilityOn, probBull, probBase, probBear, dividendYield, sensitivityGrowth, sensitivityPe])

  async function analyze(event?: FormEvent) {
    event?.preventDefault()
    setError(''); setBusy(true); setProfileResult(null)
    try {
      const data = await api.liveScenario(payload)
      setResult(data)
      const cases = Object.fromEntries(data.scenarios.map((item) => [item.key, item.expected_return_pct]))
      const risk = await api.profile({
        ticker: data.ticker, risk_profile: profile,
        bullish_return_pct: cases.bullish, base_return_pct: cases.base, bearish_return_pct: cases.bearish,
        data_quality_score: null,
      })
      setProfileResult(risk)
      setActiveTab('Tóm tắt')
    } catch (err) { setError(err instanceof Error ? err.message : 'Không thể phân tích mã này.') }
    finally { setBusy(false) }
  }

  async function downloadPdf() {
    setPdfBusy(true); setError('')
    try {
      const blob = await api.scenarioPdf(payload, reportSections, detail, includeChart, reportPurpose)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a'); link.href = url; link.download = `scenario_${payload.ticker}.pdf`; link.click()
      URL.revokeObjectURL(url)
    } catch (err) { setError(err instanceof Error ? err.message : 'Không thể tạo PDF.') }
    finally { setPdfBusy(false) }
  }

  async function comparePeers(event: FormEvent) {
    event.preventDefault(); setPeerBusy(true); setPeerError(''); setPeerResult(null)
    try {
      const peer_tickers = peerCodes.split(/[\s,;]+/).map((code) => code.trim().toUpperCase()).filter(Boolean)
      const data = await api.livePeers({ ticker: ticker.trim().toUpperCase(), industry, peer_tickers })
      setPeerResult(data)
    } catch (err) { setPeerError(err instanceof Error ? err.message : 'Không thể so sánh các mã.') }
    finally { setPeerBusy(false) }
  }

  async function scanTickers(event: FormEvent) {
    event.preventDefault()
    const symbols = [...new Set(screenerCodes.split(/[\s,;]+/).map((value) => value.trim().toUpperCase()).filter(Boolean))]
    if (symbols.length < 2 || symbols.length > 8) { setError('Hãy nhập từ 2 đến 8 mã để sàng lọc.'); return }
    setScreenerBusy(true); setError(''); setScreenerRows([])
    const rows: typeof screenerRows = []
    // Query serially to reduce provider throttling and make each failure visible.
    for (const symbol of symbols) {
      try {
        const analysis = await api.liveScenario({ ...payload, ticker: symbol })
        const base = analysis.scenarios.find((item) => item.key === 'base')!
        rows.push({ ticker: symbol, price: analysis.current_price, returnPct: base.expected_return_pct, assessment: base.assessment })
      } catch (err) { rows.push({ ticker: symbol, error: err instanceof Error ? err.message : 'Không lấy được dữ liệu' }) }
      setScreenerRows([...rows])
    }
    setScreenerBusy(false)
  }

  async function lookupAnnual(event?: FormEvent) {
    event?.preventDefault(); setReportBusy(true); setReportError(''); setAnnualInfo(null); setLanguageResult(null)
    try { const data = await api.annualAvailability(reportTicker.trim().toUpperCase()); setAnnualInfo(data); setSelectedReportYears(data.years.slice(0, 2).map((item) => item.year)) }
    catch (err) { setReportError(err instanceof Error ? err.message : 'Không tra cứu được danh mục BCTN.') }
    finally { setReportBusy(false) }
  }

  async function compareAnnual() {
    if (selectedReportYears.length < 2) { setReportError('Chọn tối thiểu hai năm có báo cáo để so sánh.'); return }
    setReportBusy(true); setReportError(''); setLanguageResult(null)
    try { setLanguageResult(await api.compareAnnualReports({ ticker: reportTicker.trim().toUpperCase(), years: selectedReportYears })) }
    catch (err) { setReportError(err instanceof Error ? err.message : 'Không so sánh được báo cáo.') }
    finally { setReportBusy(false) }
  }

  async function loadFinancial() {
    setReportBusy(true); setReportError(''); setFinancialResult(null)
    try { setFinancialResult(await api.financialReports(reportTicker.trim().toUpperCase())) }
    catch (err) { setReportError(err instanceof Error ? err.message : 'Không lấy được BCTC.') }
    finally { setReportBusy(false) }
  }

  async function loadCompanyNews() {
    setReportBusy(true); setReportError(''); setNewsResult(null)
    try { setNewsResult(await api.companyNews(reportTicker.trim().toUpperCase(), companyName, companyWebsite)) }
    catch (err) { setReportError(err instanceof Error ? err.message : 'Không lấy được tin doanh nghiệp.') }
    finally { setReportBusy(false) }
  }

  const menu: { id: Page; icon: string; label: string }[] = [
    { id: 'analysis', icon: '◈', label: 'Phân tích một mã' },
    { id: 'peers', icon: '⇄', label: 'So sánh cùng ngành' },
    { id: 'screener', icon: '⌕', label: 'Sàng lọc thị trường' },
    { id: 'reports', icon: '▤', label: 'Báo cáo & tin tức' },
    { id: 'about', icon: 'ⓘ', label: 'Phương pháp & nguồn' },
  ]

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">V</div><div><b>VietScope</b><span>STOCK INTELLIGENCE</span></div></div>
      <div className="sidebar-caption">WORKSPACE</div>
      <nav>{menu.map((item) => <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => setPage(item.id)}><span className="nav-icon">{item.icon}</span>{item.label}</button>)}</nav>
      <div className="sidebar-bottom"><div className="connection"><i className={apiOnline ? 'online' : ''} /><span>{apiOnline ? 'Backend đang kết nối' : 'Backend chưa kết nối'}</span></div><small>FastAPI · vnstock</small></div>
    </aside>

    <main className="main-area">
      <header className="topbar"><div className="breadcrumb">Workspace <span>/</span> {menu.find((item) => item.id === page)?.label}</div><div className="top-actions"><span className="market-status"><i /> Dữ liệu theo yêu cầu</span><div className="avatar">G2</div></div></header>

      {page === 'analysis' && <>
        <section className="page-heading"><div><div className="eyebrow">EQUITY RESEARCH</div><h1>Phân tích cổ phiếu</h1><p>Định giá theo kịch bản, minh bạch giả định và kiểm tra bằng chứng dữ liệu.</p></div><button className="button button-quiet" onClick={() => setPage('about')}>ⓘ Hướng dẫn</button></section>
        <div className="analysis-layout">
          <section className="panel form-panel">
            <div className="panel-heading"><div><h2>Thiết lập phân tích</h2><p>Nhập mã và điều chỉnh các giả định đầu tư.</p></div><span className="step-badge">01</span></div>
            <form onSubmit={analyze}>
              <label className="field-label">MÃ CỔ PHIẾU</label><div className="ticker-input"><input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} maxLength={16} required placeholder="Ví dụ: FPT"/><span>HOSE / HNX</span></div>
              <label className="field-label space-top">KỲ HẠN KỊCH BẢN</label><div className="segmented">{([3, 6, 12] as const).map((value) => <button type="button" key={value} className={horizon === value ? 'selected' : ''} onClick={() => setHorizon(value)}>{value} tháng</button>)}</div>
              <label className="field-label space-top">KHẨU VỊ RỦI RO</label><div className="profile-options">{profiles.map((item) => <button type="button" key={item.id} className={`profile-option ${profile === item.id ? 'chosen' : ''}`} onClick={() => setProfile(item.id)}><span className="radio-dot"/><span><b>{item.name}</b><small>{item.note}</small></span></button>)}</div>
              <details className="assumption-details"><summary>Giả định định giá <span>Tùy chọn</span></summary><div className="two-fields"><label>Tăng trưởng EPS cơ sở (%)<input type="number" step="0.1" value={growth} onChange={(e) => setGrowth(e.target.value)} placeholder="Tự tính từ EPS khả dụng"/></label><label>P/E mục tiêu<input type="number" step="0.1" value={targetPe} onChange={(e) => setTargetPe(e.target.value)} placeholder="Dùng P/E nguồn nếu có"/></label><label>Lợi suất cổ tức dự kiến (%)<input type="number" min="0" step="0.1" value={dividendYield} onChange={(e) => setDividendYield(e.target.value)}/></label></div><p className="help-text">Giá mục tiêu luôn dựa trên EPS dự phóng 12 tháng (EPS × (1+g)). Kỳ hạn 3/6/12 tháng chỉ dùng để theo dõi mức sinh lời và ngưỡng mua/bán riêng theo kỳ.</p><div className="threshold-editor"><b>Ngưỡng đánh giá theo kỳ hạn (%)</b>{([3, 6, 12] as const).map((months) => <div key={months}><span>{months} tháng</span><label>Mua ≥ <input type="number" value={horizonThresholds[months].buy} onChange={(e) => setHorizonThresholds((old) => ({ ...old, [months]: { ...old[months], buy: Number(e.target.value) }}))}/></label><label>Bán ≤ <input type="number" value={horizonThresholds[months].sell} onChange={(e) => setHorizonThresholds((old) => ({ ...old, [months]: { ...old[months], sell: Number(e.target.value) }}))}/></label></div>)}</div><p className="help-text">Ngưỡng khởi tạo chỉ là cấu hình minh họa của nhóm, không phải chuẩn khuyến nghị đầu tư; có thể chỉnh theo phương pháp của nhóm.</p></details>
              <details className="assumption-details"><summary>Chỉnh riêng từng kịch bản <span>Không bắt buộc</span></summary><div className="scenario-input-grid">{scenarioInputs.map((item) => <div className="case-input" key={item.label}><b>{item.label}</b><input aria-label={`Tăng trưởng EPS ${item.label}`} type="number" step="0.1" placeholder="EPS %" value={item.growth} onChange={(e) => item.setGrowth(e.target.value)}/><input aria-label={`P/E ${item.label}`} type="number" step="0.1" placeholder="P/E" value={item.pe} onChange={(e) => item.setPe(e.target.value)}/></div>)}</div></details>
              <details className="assumption-details"><summary>Xác suất và độ nhạy <span>Thêm phân tích</span></summary><label className="checkline"><input type="checkbox" checked={probabilityOn} onChange={(e) => setProbabilityOn(e.target.checked)}/>Tính giá trị có trọng số xác suất</label>{probabilityOn && <div className="probability-fields">{[['Tích cực', probBull, setProbBull], ['Cơ sở', probBase, setProbBase], ['Tiêu cực', probBear, setProbBear]].map(([label, value, setter]) => <label key={String(label)}>{String(label)} %<input type="number" min="0" max="100" value={String(value)} onChange={(e) => (setter as (v: string) => void)(e.target.value)}/></label>)}</div>}<div className="two-fields"><label>Tăng trưởng cho lưới (%)<input value={sensitivityGrowth} onChange={(e) => setSensitivityGrowth(e.target.value)} placeholder="0,10,20"/></label><label>P/E cho lưới<input value={sensitivityPe} onChange={(e) => setSensitivityPe(e.target.value)} placeholder="10,15,20"/></label></div><p className="help-text">Nhập danh sách phân cách bằng dấu phẩy. Xác suất phải cộng đúng 100%.</p></details>
              <button className="button button-primary full-width" type="submit" disabled={busy || !apiOnline}>{busy ? <><span className="spinner"/> Đang lấy dữ liệu và phân tích…</> : 'Chạy phân tích'}<span>→</span></button>
              {!apiOnline && <p className="help-text">Khởi động backend để bật phân tích trực tiếp.</p>}
            </form>
          </section>

          <section className="results-column">
            {error && <div className="alert alert-error">⚠ {error}</div>}
            {!result && <div className="empty-state panel"><div className="empty-graphic"><div className="empty-line line-a"/><div className="empty-line line-b"/><div className="empty-line line-c"/><span>↗</span></div><h2>Sẵn sàng phân tích</h2><p>Nhập mã cổ phiếu để lấy giá và chỉ số tài chính khả dụng, sau đó so sánh ba kịch bản đầu tư.</p><div className="empty-tags"><span>Giá & EPS</span><span>Kịch bản P/E</span><span>Thẻ bằng chứng</span></div></div>}
            {result && <ResultView result={result} activeTab={activeTab} setActiveTab={setActiveTab} profileResult={profileResult} profile={profile} onPdf={downloadPdf} pdfBusy={pdfBusy} reportSections={reportSections} setReportSections={setReportSections} reportPurpose={reportPurpose} setReportPurpose={setReportPurpose} detail={detail} setDetail={setDetail} includeChart={includeChart} setIncludeChart={setIncludeChart} error={error}/>}
          </section>
        </div>
      </>}

      {page === 'peers' && <section className="content-page"><div className="page-heading"><div><div className="eyebrow">RELATIVE VALUATION</div><h1>So sánh cùng ngành</h1><p>Đối chiếu định giá trực tiếp cho mã mục tiêu và 3–5 mã peer.</p></div></div><div className="panel peer-form-panel"><form onSubmit={comparePeers}><div className="two-fields"><label>Mã mục tiêu<input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())}/></label><label>Ngành/nhóm ICB do bạn chọn<input value={industry} onChange={(e) => setIndustry(e.target.value)}/></label><label className="wide-field">Mã so sánh<input value={peerCodes} onChange={(e) => setPeerCodes(e.target.value.toUpperCase())}/><small>Nhập 3–5 mã, chọn cùng nhóm ICB gần nhất và quy mô vốn hóa tương đồng. Ứng dụng hiện chưa tự kiểm chứng mã ngành/vốn hóa; cần ghi tiêu chí chọn peer trong báo cáo.</small></label></div><button className="button button-primary" disabled={peerBusy || !apiOnline}>{peerBusy ? 'Đang truy vấn vnstock…' : 'Tải dữ liệu và so sánh'} →</button></form></div>{peerError && <div className="alert alert-error">⚠ {peerError}</div>}{peerResult && <PeerResults result={peerResult}/>}</section>}

      {page === 'screener' && <section className="content-page"><div className="page-heading"><div><div className="eyebrow">MARKET DISCOVERY</div><h1>Sàng lọc danh sách mã</h1><p>Chạy cùng một kỳ hạn, giả định và ngưỡng trên danh sách bạn nhập; mỗi mã được truy vấn trực tiếp qua vnstock.</p></div></div><div className="panel peer-form-panel"><form onSubmit={scanTickers}><label className="wide-field">Mã cổ phiếu<input value={screenerCodes} onChange={(e) => setScreenerCodes(e.target.value.toUpperCase())}/><small>Nhập 2–8 mã, phân tách bằng dấu phẩy. Đây là sàng lọc danh sách tự chọn, chưa quét toàn bộ thị trường.</small></label><button className="button button-primary" disabled={screenerBusy || !apiOnline}>{screenerBusy ? 'Đang truy vấn tuần tự…' : 'Phân tích danh sách'} →</button></form></div>{error && <div className="alert alert-error">⚠ {error}</div>}{screenerRows.length > 0 && <div className="panel peer-results"><div className="table-scroll"><table className="data-table"><thead><tr><th>Mã</th><th>Giá</th><th>Lợi suất cơ sở ({horizon} tháng)</th><th>Kết quả ngưỡng</th><th>Trạng thái dữ liệu</th></tr></thead><tbody>{screenerRows.map((row) => <tr key={row.ticker}><th>{row.ticker}</th><td>{row.price == null ? '—' : `${formatNumber(row.price)} ₫`}</td><td>{row.returnPct == null ? '—' : `${row.returnPct >= 0 ? '+' : ''}${formatNumber(row.returnPct, 2)}%`}</td><td>{row.assessment ?? '—'}</td><td>{row.error ? <span title={row.error}>Lỗi truy vấn</span> : 'Đã lấy dữ liệu'}</td></tr>)}</tbody></table></div><p className="soft-note">Các mã lỗi được giữ trong bảng để bạn thấy phạm vi dữ liệu thực tế. Kết quả phụ thuộc cùng giả định kịch bản, không phải xếp hạng khuyến nghị.</p></div>}</section>}

      {page === 'reports' && <section className="content-page"><div className="page-heading"><div><div className="eyebrow">CORPORATE DISCLOSURE</div><h1>Báo cáo & tin doanh nghiệp</h1><p>Tra cứu BCTN PDF, BCTC theo kỳ và tin RSS theo mã. Tệp báo cáo tải theo yêu cầu.</p></div></div>
        <div className="panel peer-form-panel"><div className="two-fields"><label>Mã cổ phiếu<input value={reportTicker} onChange={(e) => setReportTicker(e.target.value.toUpperCase())}/></label><label>Tên doanh nghiệp (tùy chọn, lọc tin)<input value={companyName} onChange={(e) => setCompanyName(e.target.value)}/></label><label className="wide-field">Website/Trang tin chính thức (tùy chọn)<input value={companyWebsite} onChange={(e) => setCompanyWebsite(e.target.value)} placeholder="https://cong-ty.vn/tin-tuc"/><small>Chỉ nhập domain công khai, chính thức của doanh nghiệp. Ứng dụng chỉ đọc trang đó và các liên kết tin cùng domain.</small></label></div><div className="report-actions"><button className="button button-primary" onClick={() => void lookupAnnual()} disabled={reportBusy}>{reportBusy ? 'Đang tra cứu…' : 'Tra cứu BCTN trên Zenodo'}</button><button className="button button-quiet" onClick={() => void loadFinancial()} disabled={reportBusy}>Lấy BCTC</button><button className="button button-quiet" onClick={() => void loadCompanyNews()} disabled={reportBusy}>Tìm tin mới</button></div></div>
        {reportError && <div className="alert alert-error">⚠ {reportError}</div>}
        {annualInfo && <div className="panel peer-results"><div className="panel-heading"><div><h2>Báo cáo thường niên PDF · {reportTicker}</h2><p>Nguồn: Zenodo · DOI {annualInfo.dataset_doi}. Chọn báo cáo để so sánh ngôn ngữ.</p></div><button className="button button-primary" disabled={reportBusy || selectedReportYears.length < 2} onClick={() => void compareAnnual()}>{reportBusy ? 'Đang tải và trích xuất…' : 'So sánh các năm đã chọn'}</button></div><div className="report-year-grid">{annualInfo.years.map((item) => <div className="report-year" key={item.year}><label><input type="checkbox" checked={selectedReportYears.includes(item.year)} onChange={(e) => setSelectedReportYears((old) => e.target.checked ? [...old, item.year].sort() : old.filter((year) => year !== item.year))}/><b>{item.year}</b><small>{item.file_name} · {item.size_mb} MB {item.cached ? '· đã lưu cache' : ''}</small></label><a className="button button-quiet" href={api.annualDownloadUrl(reportTicker, item.year)} target="_blank" rel="noreferrer">Tải PDF ↗</a></div>)}</div><p className="soft-note">{annualInfo.warning} Bộ dữ liệu lớn, backend chỉ lấy PDF được chọn bằng HTTP Range và lưu cache cục bộ.</p></div>}
        {languageResult && <div className="panel peer-results"><h2>Thay đổi ngôn ngữ giữa các báo cáo</h2>{(languageResult.comparisons as Record<string, unknown>[] | undefined)?.map((comparison, index) => <div className="language-result" key={index}><b>{String(comparison.from_year)} → {String(comparison.to_year)}</b><span>Độ tương đồng từ vựng: {formatNumber(Number(comparison.cosine_similarity) * 100, 1)}%</span><span>Lexical drift: {formatNumber(Number(comparison.lexical_drift_pct), 1)}%</span></div>)}<p className="soft-note">{String(languageResult.warning ?? '')}</p></div>}
        {financialResult && <div className="panel peer-results"><div className="panel-heading"><div><h2>Báo cáo tài chính · {reportTicker}</h2><p>Nguồn: vnfinancialdata / Hugging Face · số dòng theo bảng</p></div></div>{Object.entries((financialResult.statements ?? {}) as Record<string, Record<string, unknown>[]>).map(([statement, rows]) => <details className="financial-table" key={statement}><summary>{statement.replaceAll('_', ' ')} · {rows.length} dòng</summary><div className="table-scroll"><table className="data-table"><thead><tr><th>Năm</th><th>Chỉ tiêu</th><th>Giá trị</th><th>Đơn vị</th></tr></thead><tbody>{rows.slice(0, 80).map((row, i) => <tr key={`${String(row.year)}-${i}`}><td>{String(row.year ?? '—')}</td><td>{String(row.item_name ?? row.item_code ?? '—')}</td><td>{formatNumber(Number(row.value), 2)}</td><td>{String(row.unit ?? '—')}</td></tr>)}</tbody></table></div>{rows.length > 80 && <small>Đang hiển thị 80/{rows.length} dòng.</small>}</details>)}<p className="soft-note">{String(financialResult.coverage_note ?? '')}</p></div>}
        {newsResult && <div className="panel peer-results"><div className="panel-heading"><div><h2>Tin doanh nghiệp · {reportTicker}</h2><p>Kết quả RSS · nguồn truy cập và lỗi từng feed được ghi nhận</p></div></div>{(newsResult.articles as Record<string, unknown>[] | undefined)?.map((article, index) => <article className="news-item" key={`${String(article.url)}-${index}`}><small>{String(article.source)} · {String(article.published_at ?? '')}</small><a href={String(article.url)} target="_blank" rel="noreferrer">{String(article.title)} ↗</a><p>{String(article.summary ?? '')}</p></article>)}<p className="soft-note">{String(newsResult.warning ?? '')}</p></div>}
      </section>}

      {page === 'about' && <section className="content-page"><div className="page-heading"><div><div className="eyebrow">METHODOLOGY</div><h1>Phương pháp & dữ liệu</h1><p>Các giá trị hiển thị cần được xem cùng kỳ dữ liệu, nguồn và giả định.</p></div></div><div className="about-grid"><article className="panel"><div className="about-icon">⌁</div><h2>Định giá theo kịch bản</h2><p>EPS dự phóng × P/E mục tiêu. Giá trị ước tính, lợi suất và ngưỡng BUY/HOLD/SELL là đầu ra của công thức, không phải cam kết sinh lời.</p></article><article className="panel"><div className="about-icon">◎</div><h2>Nguồn dữ liệu</h2><p>Backend lấy giá và chỉ số tài chính khả dụng theo yêu cầu qua vnstock. Độ trễ, phạm vi và kỳ dữ liệu phụ thuộc nhà cung cấp.</p></article><article className="panel"><div className="about-icon">≋</div><h2>Giả định có thể chỉnh</h2><p>Tăng trưởng, P/E mục tiêu, cổ tức, xác suất, kỳ hạn và độ nhạy được hiển thị trong kết quả. Xác suất chỉ dùng khi người dùng nhập đủ ba giá trị tổng 100%.</p></article><article className="panel"><div className="about-icon">↗</div><h2>Phân tích theo khẩu vị</h2><p>Cùng lợi suất kịch bản được đánh giá qua quy tắc an toàn/cân bằng/chấp nhận rủi ro. Ngưỡng là cấu hình minh bạch của nhóm, không phải chuẩn học thuật.</p></article></div><div className="panel api-card"><div><span className={`api-light ${apiOnline ? 'ready' : ''}`}/><b>{apiOnline ? 'Backend FastAPI đang hoạt động' : 'Backend chưa phản hồi'}</b><p>API: {import.meta.env.VITE_API_BASE_URL || 'cùng host (Vite proxy → localhost:8000)'}</p></div><a className="button button-quiet" href={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/docs`} target="_blank" rel="noreferrer">Mở tài liệu API ↗</a></div></section>}
      <footer className="footer">VietScope · Công cụ nghiên cứu học tập · Không phải lời khuyên đầu tư</footer>
    </main>
  </div>
}

function ResultView({ result, activeTab, setActiveTab, profileResult, profile, onPdf, pdfBusy, reportSections, setReportSections, reportPurpose, setReportPurpose, detail, setDetail, includeChart, setIncludeChart, error }: {
  result: LiveScenario; activeTab: string; setActiveTab: (tab: string) => void; profileResult: Record<string, unknown> | null; profile: Profile
  onPdf: () => void; pdfBusy: boolean; reportSections: string[]; setReportSections: (value: string[]) => void
  reportPurpose: 'full' | 'long_term' | 'trader' | 'one_pager' | 'committee'; setReportPurpose: (value: 'full' | 'long_term' | 'trader' | 'one_pager' | 'committee') => void
  detail: string; setDetail: (value: string) => void; includeChart: boolean; setIncludeChart: (value: boolean) => void; error: string
}) {
  const base = result.scenarios.find((item) => item.key === 'base')!
  const sorted = result.scenarios
  const maxPrice = Math.max(...sorted.map((item) => item.estimated_price), 1)
  const tabs = ['Tóm tắt', 'Kịch bản & độ nhạy', 'Rủi ro', 'Nguồn dữ liệu']
  return <>
    <div className="result-heading"><div><div className="eyebrow">LIVE ANALYSIS · {result.horizon_months} THÁNG</div><h2>{result.ticker}<span className="exchange-tag">THỊ TRƯỜNG VIỆT NAM</span></h2></div><button className="button button-quiet" onClick={onPdf} disabled={pdfBusy}>{pdfBusy ? 'Đang tạo PDF…' : '⇩  Xuất PDF'}</button></div>
    <div className="kpi-grid"><div className="kpi-card"><span>Giá hiện tại</span><b>{formatNumber(result.current_price)} <small>₫</small></b><small>{result.data_status?.price_period ?? 'Kỳ giá do nguồn trả về'}</small></div><div className="kpi-card accent-kpi"><span>Giá ước tính cơ sở</span><b>{formatNumber(base.estimated_price)} <small>₫</small></b><small>{base.expected_return_pct >= 0 ? '+' : ''}{formatNumber(base.expected_return_pct, 2)}% theo giả định cơ sở</small></div><div className="kpi-card"><span>P/E mục tiêu cơ sở</span><b>{formatNumber(base.target_pe, 2)}<small>×</small></b><small>Giả định hiển thị trong kịch bản</small></div></div>
    {result.data_confidence && <div className={`alert ${result.data_confidence.label === 'Thấp' ? 'alert-warn' : ''}`}><b>Độ phủ dữ liệu: {result.data_confidence.score}/100 · {result.data_confidence.label}</b><span> · {result.scenario_method?.growth_observations ?? 0} quan sát tăng trưởng, {result.scenario_method?.pe_observations ?? 0} P/E cùng kỳ EPS. Đây là điểm độ phủ, không phải xác suất đúng.</span></div>}
    <div className="panel chart-panel"><div className="panel-heading"><div><h3>So sánh kịch bản</h3><p>Giá hiện tại và giá ước tính theo từng bộ giả định.</p></div><span className="chart-legend"><i/> Giá ước tính</span></div><div className="scenario-bars">{sorted.map((item) => <div className="bar-row" key={item.key}><div className="bar-label"><b>{item.label}</b><small>{item.expected_return_pct >= 0 ? '+' : ''}{formatNumber(item.expected_return_pct, 2)}%</small></div><div className="bar-track"><div className={`bar-fill ${item.key}`} style={{ width: `${Math.max(3, item.estimated_price / maxPrice * 100)}%` }}/></div><b className="bar-value">{formatNumber(item.estimated_price)}</b></div>)}</div><div className="current-price-marker">Giá hiện tại: <b>{formatNumber(result.current_price)} ₫</b></div></div>
    <div className="scenario-cards">{sorted.map((item) => <details className={`scenario-card ${item.key}`} key={item.key}><summary><span className="case-label"><i/>{item.label}</span><b>{formatNumber(item.estimated_price)} ₫</b><span className={item.expected_return_pct >= 0 ? 'positive' : 'negative'}>{item.expected_return_pct >= 0 ? '+' : ''}{formatNumber(item.expected_return_pct, 2)}%</span><span className="expand-mark">⌄</span></summary><div className="case-details"><div><span>Tăng trưởng EPS</span><b>{formatNumber(item.earnings_growth_pct, 2)}%</b></div><div><span>P/E mục tiêu</span><b>{formatNumber(item.target_pe, 2)}×</b></div><div><span>EPS dự phóng</span><b>{formatNumber(item.projected_eps, 2)}</b></div><p>{item.assumption_basis}</p><Evidence cards={item.evidence}/></div></details>)}</div>
    {error && <div className="alert alert-error compact-alert">⚠ {error}</div>}
    <div className="panel results-tabs"><div className="tab-bar">{tabs.map((tab) => <button key={tab} onClick={() => setActiveTab(tab)} className={activeTab === tab ? 'on' : ''}>{tab}</button>)}</div>
      {activeTab === 'Tóm tắt' && <div className="tab-content"><div className="profile-result"><div className="profile-symbol">◎</div><div><span className="eyebrow">ĐÁNH GIÁ THEO KHẨU VỊ · {profiles.find((item) => item.id === profile)?.name}</span><h3>{String(profileResult?.assessment ?? 'Chưa có đánh giá')}</h3><p>{Array.isArray(profileResult?.reasons) ? (profileResult.reasons as string[]).join(' · ') : 'Đánh giá sẽ xuất hiện sau khi chạy phân tích.'}</p></div></div>{result.probability_weighted_value != null && <div className="weighted-value"><span>Giá trị kịch bản có trọng số xác suất</span><b>{formatNumber(result.probability_weighted_value)} ₫</b></div>}<p className="soft-note">Ngưỡng khẩu vị là quy tắc cấu hình của nhóm. Kết quả không phải khuyến nghị cá nhân hóa.</p></div>}
      {activeTab === 'Kịch bản & độ nhạy' && <div className="tab-content"><h3>Lưới độ nhạy EPS growth × P/E</h3>{result.sensitivity_grid?.cells?.length ? <div className="sensitivity-table-wrap"><table className="data-table"><thead><tr><th>Tăng trưởng \ P/E</th>{result.sensitivity_grid.target_pe.map((pe) => <th key={pe}>{formatNumber(pe, 1)}×</th>)}</tr></thead><tbody>{result.sensitivity_grid.cells.map((row) => <tr key={row.growth_pct}><th>{formatNumber(row.growth_pct, 1)}%</th>{row.prices.map((cell) => <td key={cell.target_pe}>{formatNumber(cell.estimated_price)}</td>)}</tr>)}</tbody></table></div> : <p>Nhập danh sách tăng trưởng và P/E ở phần giả định để tạo lưới độ nhạy.</p>}{result.probability_weighted_value == null ? <p className="soft-note">Chưa gán xác suất cho các kịch bản.</p> : <p className="soft-note">Xác suất: Tích cực {formatNumber(result.probabilities_pct?.bullish)}% · Cơ sở {formatNumber(result.probabilities_pct?.base)}% · Tiêu cực {formatNumber(result.probabilities_pct?.bearish)}%</p>}{result.configuration_warnings.map((warning) => <div className="alert alert-warn" key={warning}>{warning}</div>)}</div>}
      {activeTab === 'Rủi ro' && <div className="tab-content"><div className="risk-notice"><b>Giới hạn mô hình</b><ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div><p>Đánh giá hiện tại dùng lợi suất ba kịch bản và bộ quy tắc khẩu vị đã chọn. Biến động lịch sử, beta, drawdown và chỉ tiêu nợ cần dữ liệu chuỗi giá/BCTC riêng; chưa được tự suy diễn từ báo giá đơn lẻ.</p></div>}
      {activeTab === 'Nguồn dữ liệu' && <div className="tab-content">{result.data_status ? <div className="source-grid">{Object.entries(result.data_status).map(([key, value]) => <div className="source-item" key={key}><span>{key.replaceAll('_', ' ')}</span><b>{String(value)}</b></div>)}</div> : <p>Nguồn/kỳ dữ liệu chưa được trả về.</p>}<p className="soft-note">Dữ liệu giá và chỉ số từ vnstock có thể trễ hoặc thiếu tùy nguồn cung cấp.</p></div>}
    </div>
    <div className="panel pdf-options"><div className="panel-heading"><div><h3>Tùy chỉnh PDF</h3><p>Chọn mục đích, nội dung và mức chi tiết trước khi xuất báo cáo.</p></div><span className="pdf-icon">PDF</span></div><div className="pdf-controls"><label>Mục đích báo cáo<select value={reportPurpose} onChange={(e) => { const purpose = e.target.value as typeof reportPurpose; setReportPurpose(purpose); setReportSections(purposeSections[purpose]) }}><option value="full">Báo cáo đầy đủ</option><option value="long_term">Nhà đầu tư dài hạn</option><option value="trader">Theo dõi giao dịch</option><option value="one_pager">Tóm tắt một trang</option><option value="committee">Trình bày hội đồng</option></select></label><label>Mức chi tiết<select value={detail} onChange={(e) => setDetail(e.target.value)}><option value="summary">Tóm tắt</option><option value="standard">Tiêu chuẩn</option><option value="detailed">Chi tiết</option></select></label><label className="checkline"><input type="checkbox" checked={includeChart} onChange={(e) => setIncludeChart(e.target.checked)}/>Bao gồm biểu đồ</label></div><div className="section-checks">{sectionOptions.map(([id, label]) => <label key={id}><input type="checkbox" checked={reportSections.includes(id)} onChange={(e) => setReportSections(e.target.checked ? [...reportSections, id] : reportSections.filter((item) => item !== id))}/>{label}</label>)}</div><div className="soft-note">Giá mục tiêu luôn dùng EPS dự phóng 12 tháng; 3/6/12 tháng là kỳ theo dõi và dùng ngưỡng riêng. Phần tài chính/rủi ro chỉ có nội dung khi dữ liệu bổ sung được gửi cùng yêu cầu PDF.</div></div>
  </>
}

function Evidence({ cards }: { cards: LiveScenario['scenarios'][number]['evidence'] }) {
  return <details className="evidence-details"><summary>Xem thẻ bằng chứng <span>{cards.length} phép tính</span></summary>{cards.map((card) => <div className="evidence-card" key={card.claim}><b>{card.claim}: {formatNumber(card.value, 2)} {card.unit}</b><p>Công thức: {card.formula}</p><small>Nguồn: {card.source} · Kỳ: {card.period}{card.retrieved_at ? ` · Lấy lúc ${card.retrieved_at}` : ''}</small></div>)}</details>
}

function PeerResults({ result }: { result: Record<string, unknown> }) {
  const snapshots = Array.isArray(result.live_snapshots) ? result.live_snapshots as Record<string, unknown>[] : []
  const medians = result.medians as Record<string, number | null> | undefined
  return <div className="panel peer-results"><div className="panel-heading"><div><h2>Bảng so sánh</h2><p>{String(result.industry)} · {String(result.note)}</p></div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Mã</th><th>Giá gần nhất</th><th>EPS</th><th>P/E</th><th>Kỳ giá</th></tr></thead><tbody>{snapshots.map((row) => <tr key={String(row.ticker)}><th>{String(row.ticker)}</th><td>{formatNumber(Number(row.current_price))} ₫</td><td>{formatNumber(Number(row.eps), 2)}</td><td>{formatNumber(Number(row.pe), 2)}×</td><td>{String(row.price_period)}</td></tr>)}<tr className="median-row"><th>Trung vị peer</th><td>—</td><td>—</td><td>{formatNumber(medians?.pe, 2)}×</td><td>—</td></tr></tbody></table></div>{result.target_price_at_peer_median_pe != null && <p className="peer-implied">Giá hàm ý theo EPS hiện tại × P/E trung vị peer: <b>{formatNumber(Number(result.target_price_at_peer_median_pe))} ₫</b> ({formatNumber(Number(result.implied_return_at_peer_median_pe_pct), 2)}%)</p>}<p className="soft-note">{String(result.percentile_note)}</p></div>
}

export default App
