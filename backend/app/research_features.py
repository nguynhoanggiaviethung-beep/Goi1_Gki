"""Explainable research utilities: data-quality score, risk profiles, peers, text drift and validation."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import math
import random
import re
import statistics
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

router = APIRouter(tags=["research features"])


class DataQualityInput(BaseModel):
    ticker: str
    accounting_difference_pct: float | None = Field(default=None, ge=0)
    accounting_tolerance_pct: float = Field(default=1.0, gt=0)
    cross_source_max_difference_pct: float | None = Field(default=None, ge=0)
    cross_source_tolerance_pct: float = Field(default=5.0, gt=0, description="Ngưỡng do nhóm cấu hình")
    missing_periods: int = Field(default=0, ge=0)
    unexplained_price_limit_move: bool = False
    price_adjustment_unknown: bool = False
    data_age_days: int = Field(default=0, ge=0)
    stale_after_days: int = Field(default=5, ge=0, description="Ngưỡng do nhóm cấu hình")
    missing_critical_pct: float = Field(default=0, ge=0, le=100)
    missing_tolerance_pct: float = Field(default=10, ge=0, le=100, description="Ngưỡng do nhóm cấu hình")
    illiquid_sessions: int = Field(default=0, ge=0)
    illiquid_tolerance_sessions: int = Field(default=5, ge=0, description="Ngưỡng do nhóm cấu hình")
    unhandled_regime_change: bool = False


QUALITY_DEDUCTIONS = {
    "accounting_equation": 20,
    "source_disagreement": 15,
    "missing_period": 10,
    "unexplained_price_move": 8,
    "unknown_adjustment": 8,
    "stale_data": 5,
    "missing_critical_data": 5,
    "illiquidity": 5,
    "unhandled_market_change": 5,
}


@router.post("/quality/score")
def score_data_quality(request: DataQualityInput):
    """Apply the team's explicit penalty table; the score is a rubric, not a universal standard."""
    issues = []

    def issue(code: str, label: str, observed: str, threshold: str):
        issues.append({"code": code, "check": label, "observed": observed, "threshold": threshold,
                       "deduction": QUALITY_DEDUCTIONS[code], "basis": "Ngưỡng/điểm trừ do nhóm đề xuất"})

    if request.accounting_difference_pct is not None and request.accounting_difference_pct >= request.accounting_tolerance_pct:
        issue("accounting_equation", "Sai lệch đẳng thức kế toán", f"{request.accounting_difference_pct:.3f}%", f"< {request.accounting_tolerance_pct:.3f}%")
    if request.cross_source_max_difference_pct is not None and request.cross_source_max_difference_pct > request.cross_source_tolerance_pct:
        issue("source_disagreement", "Chênh lệch giữa các nguồn", f"{request.cross_source_max_difference_pct:.3f}%", f"≤ {request.cross_source_tolerance_pct:.3f}%")
    if request.missing_periods > 0:
        issue("missing_period", "Thiếu kỳ báo cáo", str(request.missing_periods), "0 kỳ")
    if request.unexplained_price_limit_move:
        issue("unexplained_price_move", "Biến động chạm biên chưa giải thích", "Có", "Cần kiểm tra corporate action / quy chế lịch sử")
    if request.price_adjustment_unknown:
        issue("unknown_adjustment", "Không xác định trạng thái điều chỉnh giá", "Chưa rõ", "Phải biết đã điều chỉnh cổ tức/chia tách")
    if request.data_age_days > request.stale_after_days:
        issue("stale_data", "Dữ liệu quá cũ", f"{request.data_age_days} ngày", f"≤ {request.stale_after_days} ngày")
    if request.missing_critical_pct > request.missing_tolerance_pct:
        issue("missing_critical_data", "Thiếu chỉ tiêu trọng yếu", f"{request.missing_critical_pct:.2f}%", f"≤ {request.missing_tolerance_pct:.2f}%")
    if request.illiquid_sessions > request.illiquid_tolerance_sessions:
        issue("illiquidity", "Phiên không thanh khoản", str(request.illiquid_sessions), f"≤ {request.illiquid_tolerance_sessions} phiên")
    if request.unhandled_regime_change:
        issue("unhandled_market_change", "Thay đổi quy chế/sàn chưa xử lý", "Có", "Cần hiệu chỉnh theo quy tắc có hiệu lực tại ngày dữ liệu")

    score = max(0, 100 - sum(item["deduction"] for item in issues))
    grade = "cao" if score >= 90 else "trung bình" if score >= 70 else "thấp"
    warnings = [item["check"] for item in issues]
    return {
        "ticker": request.ticker.upper(), "score": score, "grade": grade,
        "warnings": warnings, "deduction_details": issues,
        "method": "100 − tổng điểm trừ cố định của các cờ lỗi; mỗi lỗi chỉ trừ một lần.",
        "method_status": "Rubric nội bộ của nhóm; các khoản trừ không phải trọng số được ước lượng từ nghiên cứu.",
        "thresholds": {"accounting_tolerance_pct": request.accounting_tolerance_pct,
                       "cross_source_tolerance_pct": request.cross_source_tolerance_pct,
                       "stale_after_days": request.stale_after_days,
                       "missing_tolerance_pct": request.missing_tolerance_pct,
                       "illiquid_tolerance_sessions": request.illiquid_tolerance_sessions},
    }


class ProfileRequest(BaseModel):
    ticker: str
    risk_profile: Literal["conservative", "balanced", "aggressive"]
    bearish_return_pct: float
    base_return_pct: float
    bullish_return_pct: float
    annual_volatility_pct: float | None = Field(default=None, ge=0)
    data_quality_score: int | None = Field(default=None, ge=0, le=100)


PROFILE_RULES = {
    "conservative": {"label": "An toàn", "max_bear_case_loss_pct": 10, "max_volatility_pct": 25, "min_base_return_pct": 8},
    "balanced": {"label": "Cân bằng", "max_bear_case_loss_pct": 25, "max_volatility_pct": 45, "min_base_return_pct": 0},
    "aggressive": {"label": "Chấp nhận rủi ro", "max_bear_case_loss_pct": 50, "max_volatility_pct": 70, "min_base_return_pct": 0},
}


@router.post("/recommendation/profile")
def evaluate_risk_profile(request: ProfileRequest):
    rules = PROFILE_RULES[request.risk_profile]
    breaches = []
    if request.data_quality_score is not None and request.data_quality_score < 70:
        label = "Chưa đủ độ tin cậy dữ liệu"
        breaches.append("Điểm tin cậy dữ liệu dưới 70/100")
    else:
        if request.bearish_return_pct < -rules["max_bear_case_loss_pct"]:
            breaches.append(f"Kịch bản tiêu cực giảm {abs(request.bearish_return_pct):.2f}%, vượt mức chịu lỗ {rules['max_bear_case_loss_pct']}%")
        if request.annual_volatility_pct is not None and request.annual_volatility_pct > rules["max_volatility_pct"]:
            breaches.append(f"Biến động năm {request.annual_volatility_pct:.2f}% vượt ngưỡng nhóm đặt {rules['max_volatility_pct']}%")
        if request.base_return_pct < rules["min_base_return_pct"]:
            breaches.append(f"Lợi suất cơ sở {request.base_return_pct:.2f}% thấp hơn ngưỡng {rules['min_base_return_pct']}%")
        label = "Theo dõi / không phù hợp với bộ quy tắc khẩu vị" if breaches else "Phù hợp có điều kiện với bộ quy tắc khẩu vị"

    return {
        "ticker": request.ticker.upper(), "risk_profile": request.risk_profile,
        "assessment": label, "reasons": breaches or ["Các giả định đầu vào đạt các ngưỡng khẩu vị đã cấu hình."],
        "inputs": {"bearish_return_pct": request.bearish_return_pct, "base_return_pct": request.base_return_pct,
                   "bullish_return_pct": request.bullish_return_pct, "annual_volatility_pct": request.annual_volatility_pct,
                   "data_quality_score": request.data_quality_score},
        "rules": rules,
        "method_status": "Ngưỡng khẩu vị là quy tắc minh bạch do nhóm cấu hình, không phải chuẩn học thuật hoặc tư vấn đầu tư cá nhân hóa.",
    }


class PillarWeights(BaseModel):
    quality: float = Field(ge=0, le=1)
    valuation: float = Field(ge=0, le=1)
    momentum: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def weights_sum_to_one(self):
        if not math.isclose(self.quality + self.valuation + self.momentum + self.risk, 1.0, abs_tol=1e-6):
            raise ValueError("Tổng trọng số bốn trụ cột phải bằng 1.")
        return self


class CompositeScoreRequest(BaseModel):
    ticker: str
    quality: float = Field(ge=0, le=100)
    valuation: float = Field(ge=0, le=100)
    momentum: float = Field(ge=0, le=100)
    risk: float = Field(ge=0, le=100)
    weights_by_profile: dict[Literal["conservative", "balanced", "aggressive"], PillarWeights]

    @model_validator(mode="after")
    def require_all_profiles(self):
        if set(self.weights_by_profile) != {"conservative", "balanced", "aggressive"}:
            raise ValueError("Cần cấu hình trọng số cho cả ba khẩu vị để so độ nhạy.")
        return self


@router.post("/score/composite")
def calculate_composite_scores(request: CompositeScoreRequest):
    pillar_scores = {key: getattr(request, key) for key in ("quality", "valuation", "momentum", "risk")}
    outputs = {}
    for profile, weights in request.weights_by_profile.items():
        weight_map = weights.model_dump()
        outputs[profile] = {
            "score": round(sum(pillar_scores[key] * weight_map[key] for key in pillar_scores), 2),
            "weights": weight_map,
            "contributions": {key: round(pillar_scores[key] * weight_map[key], 2) for key in pillar_scores},
        }
    return {"ticker": request.ticker.upper(), "pillar_scores": pillar_scores,
            "profiles": outputs,
            "formula": "Điểm tổng = Σ (điểm trụ cột × trọng số trụ cột); trọng số mỗi khẩu vị bắt buộc tổng bằng 1.",
            "weight_basis": "Bảng nhóm nêu 25/25/25/25 là điểm khởi đầu cân bằng và yêu cầu weight sensitivity; trọng số khác là lựa chọn của nhóm, chưa có chuẩn công nhận.",
            "sensitivity_range": round(max(item["score"] for item in outputs.values()) - min(item["score"] for item in outputs.values()), 2) if outputs else 0}


class HistoricalReturnsRequest(BaseModel):
    ticker: str
    daily_returns_pct: list[float] = Field(min_length=60, max_length=5000)
    tail_probability: Literal[0.01, 0.025, 0.05] = 0.05


@router.post("/risk/var-es")
def calculate_historical_var_es(request: HistoricalReturnsRequest):
    """Historical one-day VaR and Expected Shortfall; return inputs must be adjusted returns."""
    values = sorted(request.daily_returns_pct)
    tail_count = max(1, math.ceil(len(values) * request.tail_probability))
    tail = values[:tail_count]
    quantile = values[max(0, math.ceil(len(values) * request.tail_probability) - 1)]
    return {
        "ticker": request.ticker.upper(),
        "observations": len(values),
        "tail_probability": request.tail_probability,
        "confidence_level_pct": (1 - request.tail_probability) * 100,
        "historical_var_loss_pct": round(-quantile, 4),
        "expected_shortfall_loss_pct": round(-statistics.mean(tail), 4),
        "horizon": "1 ngày giao dịch",
        "method": "VaR = −phân vị alpha của lợi suất; ES = −trung bình lợi suất ở đuôi alpha.",
        "limitations": ["Lịch sử không đảm bảo mô tả tổn thất tương lai.",
                        "Cần kiểm tra giá đã điều chỉnh hành động doanh nghiệp và ngày không giao dịch.",
                        "ES 97.5% chỉ có ít quan sát đuôi ở mẫu ngắn; dùng kết quả thận trọng."],
    }


class PeerMetrics(BaseModel):
    ticker: str
    industry: str
    current_price: float | None = Field(default=None, gt=0)
    eps: float | None = Field(default=None, gt=0)
    pe: float | None = Field(default=None, gt=0)
    roe_pct: float | None = None
    earnings_growth_pct: float | None = None
    debt_to_equity: float | None = None


class PeerComparisonRequest(BaseModel):
    target: PeerMetrics
    peers: list[PeerMetrics] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def validate_peer_scope(self):
        if any(peer.industry.strip().casefold() != self.target.industry.strip().casefold() for peer in self.peers):
            raise ValueError("Mã so sánh phải thuộc cùng nhóm ngành đã khai báo với mã mục tiêu.")
        all_tickers = [self.target.ticker.upper(), *(peer.ticker.upper() for peer in self.peers)]
        if len(set(all_tickers)) != len(all_tickers):
            raise ValueError("Danh sách peer không được lặp mã.")
        return self


@router.post("/peers/compare")
def compare_peers(request: PeerComparisonRequest):
    metrics = ("current_price", "eps", "pe", "roe_pct", "earnings_growth_pct", "debt_to_equity")
    group = [request.target, *request.peers]
    comparison = []
    medians = {}
    for metric in metrics:
        available = [(firm.ticker.upper(), getattr(firm, metric)) for firm in request.peers if getattr(firm, metric) is not None]
        if not available:
            medians[metric] = None
            continue
        vals = [value for _, value in available]
        medians[metric] = round(statistics.median(vals), 4)
        for firm in group:
            value = getattr(firm, metric)
            comparison.append({"ticker": firm.ticker.upper(), "metric": metric, "value": value,
                               "peer_group_median": medians[metric],
                               "difference_from_median": round(value - medians[metric], 4) if value is not None else None,
                               "industry": request.target.industry})
    return {"target": request.target.ticker.upper(), "industry": request.target.industry,
            "peer_count": len(request.peers), "peer_tickers": [peer.ticker.upper() for peer in request.peers],
            "rows": comparison, "medians": medians,
            "note": "Tính toán và xếp bảng tự động từ dữ liệu đã gửi; hệ thống chưa tự xác nhận ngành hoặc truy vấn hồ sơ mã. Chỉ so sánh các peer cùng kỳ và cùng đơn vị.",
            "percentile_note": "Peer comparison chỉ có 3–5 mã theo đầu vào; không suy luận phân vị ngành rộng."}


class LivePeerComparisonRequest(BaseModel):
    ticker: str
    peer_tickers: list[str] = Field(min_length=3, max_length=5)
    industry: str = Field(min_length=2, description="Nhóm ngành do client xác định")

    @model_validator(mode="after")
    def validate_tickers(self):
        codes = [self.ticker.upper(), *(code.upper() for code in self.peer_tickers)]
        if len(set(codes)) != len(codes):
            raise ValueError("Mã mục tiêu và peer phải khác nhau, không được trùng.")
        return self


@router.post("/peers/live-compare")
def compare_live_peers(request: LivePeerComparisonRequest):
    """Retrieve latest quote and P/E snapshots, then create a peer comparison table."""
    from backend.app.market_data import fetch_live_inputs

    symbols = [request.ticker.upper(), *(code.upper() for code in request.peer_tickers)]
    snapshots = []
    for symbol in symbols:
        live = fetch_live_inputs(symbol, growth_override=0)
        snapshots.append({"ticker": symbol, "industry": request.industry,
                          "current_price": live["current_price"], "eps": live["eps"], "pe": live["target_pe"],
                          "price_period": live["price_period"], "eps_period": live["eps_period"],
                          "retrieved_at": live["retrieved_at"]})
    target, peers = snapshots[0], snapshots[1:]
    peer_pes = [row["pe"] for row in peers if row["pe"] is not None and row["pe"] > 0]
    median_pe = statistics.median(peer_pes) if peer_pes else None
    result = compare_peers(PeerComparisonRequest(
        target=PeerMetrics(**target), peers=[PeerMetrics(**row) for row in peers]))
    result["live_snapshots"] = snapshots
    result["target_price_at_peer_median_pe"] = round(target["eps"] * median_pe, 2) if median_pe else None
    result["implied_return_at_peer_median_pe_pct"] = round((target["eps"] * median_pe / target["current_price"] - 1) * 100, 2) if median_pe and target["current_price"] else None
    result["note"] = "Giá/P-E lấy qua vnstock khi gọi API. Danh sách peer/ngành do client cung cấp, backend chưa xác thực phân ngành; P/E trung vị không tự nó là giá mục tiêu hợp lý."
    return result


class AnnualReportText(BaseModel):
    year: int = Field(ge=1900, le=2100)
    text: str = Field(min_length=200)
    section: str = Field(default="same_section", description="Nên truyền cùng chương/phần giữa các năm")


class LanguageChangeRequest(BaseModel):
    ticker: str
    reports: list[AnnualReportText] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def require_consistent_sections(self):
        if len({report.section.strip().casefold() for report in self.reports}) != 1:
            raise ValueError("Cần so sánh cùng một chương/phần qua các năm để kết quả có ý nghĩa.")
        return self


STOPWORDS = set("và của là có được trong các những với cho từ này đó khi đã một một số tại theo về công ty doanh nghiệp năm báo cáo chúng tôi hoạt động kinh doanh tài chính hội đồng cổ đông".split())


def _tokens(text: str) -> list[str]:
    return [word for word in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE) if len(word) >= 3 and word not in STOPWORDS and not word.isdigit()]


@router.post("/reports/language-change")
def compare_report_language(request: LanguageChangeRequest):
    reports = sorted(request.reports, key=lambda report: report.year)
    if len({report.year for report in reports}) != len(reports):
        raise HTTPException(status_code=422, detail="Mỗi báo cáo cần một năm khác nhau.")
    baseline = reports[0]
    base_tokens = _tokens(baseline.text)
    base_counts = Counter(base_tokens)
    results = []
    for report in reports[1:]:
        current_tokens = _tokens(report.text)
        current_counts = Counter(current_tokens)
        vocabulary = set(base_counts) | set(current_counts)
        dot = sum(base_counts[word] * current_counts[word] for word in vocabulary)
        norm_base = math.sqrt(sum(value * value for value in base_counts.values()))
        norm_current = math.sqrt(sum(value * value for value in current_counts.values()))
        cosine = dot / (norm_base * norm_current) if norm_base and norm_current else 0.0
        total_base, total_current = max(1, len(base_tokens)), max(1, len(current_tokens))
        rate_delta = {word: current_counts[word] / total_current * 1000 - base_counts[word] / total_base * 1000 for word in vocabulary}
        gained = sorted((word for word in vocabulary if rate_delta[word] > 0), key=lambda word: rate_delta[word], reverse=True)[:15]
        declined = sorted((word for word in vocabulary if rate_delta[word] < 0), key=lambda word: rate_delta[word])[:15]
        results.append({"from_year": baseline.year, "to_year": report.year, "from_section": baseline.section,
                        "to_section": report.section, "cosine_similarity": round(cosine, 4),
                        "lexical_drift_pct": round((1 - cosine) * 100, 2),
                        "token_counts": {str(baseline.year): len(base_tokens), str(report.year): len(current_tokens)},
                        "terms_more_used_per_1000_words": [{"term": w, "change": round(rate_delta[w], 3)} for w in gained],
                        "terms_less_used_per_1000_words": [{"term": w, "change": round(rate_delta[w], 3)} for w in declined]})
    return {"ticker": request.ticker.upper(), "comparisons": results,
            "interpretation_limit": "Đo thay đổi phân bố từ vựng, không tự kết luận sắc thái tích cực/tiêu cực. So sánh chỉ có ý nghĩa khi dùng cùng phần báo cáo, ngôn ngữ, OCR và tiền xử lý.",
            "method": "Cosine similarity tren tan suat token; lexical drift = (1 - cosine similarity) * 100."}


class ExplanationRequest(BaseModel):
    analysis: dict


@router.post("/explanation/numeric")
def numeric_explanation(request: ExplanationRequest):
    """Render fixed text from server-computed scenario results, without accepting free-form numbers."""
    from backend.app.scenarios import ScenarioRequest, analyze_scenarios

    try:
        analysis = analyze_scenarios(ScenarioRequest.model_validate(request.analysis))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Dữ liệu phân tích không hợp lệ: {exc}") from exc
    facts = []
    for scenario in analysis["scenarios"]:
        facts.extend([
            {"scenario": scenario["label"], "name": "Giá ước tính", "value": scenario["estimated_price"],
             "unit": analysis["currency"] + "/cổ phiếu"},
            {"scenario": scenario["label"], "name": "Lợi suất", "value": scenario["expected_return_pct"], "unit": "%"},
        ])
    statements = [f"{fact['scenario']}: {fact['name']} {fact['value']:g} {fact['unit']}." for fact in facts]
    return {"ticker": analysis["ticker"], "statements": statements,
            "facts_used": facts,
            "generation": "Mẫu câu xác định, không gọi LLM và không tự tạo số liệu.",
            "llm_contract": "Endpoint chỉ dùng facts đã tính; LLM nếu bổ sung chỉ được diễn đạt facts_used."}


class BacktestObservation(BaseModel):
    signal_date: date
    data_available_at: date
    forward_period_end: date
    ticker: str
    industry: str
    score: float = Field(ge=0, le=100)
    forward_return_pct: float
    benchmark_return_pct: float
    adjusted_prices: bool = True

    @model_validator(mode="after")
    def prevent_lookahead(self):
        if self.data_available_at > self.signal_date:
            raise ValueError("Không được dùng dữ liệu công bố sau ngày lập tín hiệu (look-ahead).")
        if self.forward_period_end <= self.signal_date:
            raise ValueError("Kỳ tính lợi suất phải kết thúc sau ngày tín hiệu.")
        return self


class BacktestRequest(BaseModel):
    observations: list[BacktestObservation] = Field(min_length=10, max_length=5000)
    permutation_iterations: int = Field(default=1000, ge=100, le=5000)
    random_seed: int = 7
    transaction_cost_pct_per_side: float = Field(default=0.0, ge=0, le=10)
    @model_validator(mode="after")
    def require_adjusted_prices(self):
        if any(not observation.adjusted_prices for observation in self.observations):
            raise ValueError("Backtest yêu cầu giá đã điều chỉnh cổ tức/chia tách hoặc phải chuẩn hóa trước.")
        keys = [(row.signal_date, row.ticker.upper()) for row in self.observations]
        if len(set(keys)) != len(keys):
            raise ValueError("Mỗi ngày tín hiệu chỉ được có một quan sát cho mỗi mã.")
        return self


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[i]] == values[order[j]]:
            j += 1
        average = (i + 1 + j) / 2
        for k in range(i, j):
            ranks[order[k]] = average
        i = j
    return ranks


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 3:
        return None
    a, b = _rank(left), _rank(right)
    mean_a, mean_b = statistics.mean(a), statistics.mean(b)
    denom = math.sqrt(sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b))
    return sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / denom if denom else 0.0


@router.post("/backtest/evaluate")
def evaluate_backtest(request: BacktestRequest):
    by_date = defaultdict(list)
    for row in request.observations:
        by_date[row.signal_date].append(row)
    valid_periods = []
    cost_per_round_trip = 2 * request.transaction_cost_pct_per_side
    for formed, rows in by_date.items():
        if len(rows) >= 3:
            ic = _correlation([r.score for r in rows], [r.forward_return_pct - r.benchmark_return_pct - cost_per_round_trip for r in rows])
            if ic is not None:
                valid_periods.append((formed, rows, ic))
    if not valid_periods:
        raise HTTPException(status_code=422, detail="Cần ít nhất một ngày tín hiệu có từ ba mã trở lên để tính rank IC.")
    valid_periods.sort(key=lambda item: item[0])
    ics = [item[2] for item in valid_periods]
    mean_ic = statistics.mean(ics)
    t_stat = mean_ic / (statistics.stdev(ics) / math.sqrt(len(ics))) if len(ics) > 1 and statistics.stdev(ics) else None
    spreads, top_excesses = [], []
    for _, rows, _ in valid_periods:
        ordered = sorted(rows, key=lambda row: row.score)
        width = max(1, math.ceil(len(ordered) * 0.2))
        bottom_gross = statistics.mean(row.forward_return_pct - row.benchmark_return_pct for row in ordered[:width])
        top_gross = statistics.mean(row.forward_return_pct - row.benchmark_return_pct for row in ordered[-width:])
        spreads.append(top_gross - bottom_gross - 2 * cost_per_round_trip)
        top = top_gross - cost_per_round_trip
        top_excesses.append(top)
    rng = random.Random(request.random_seed)
    extreme = 0
    for _ in range(request.permutation_iterations):
        permuted_ics = []
        for _, rows, _ in valid_periods:
            outcomes = [row.forward_return_pct - row.benchmark_return_pct - cost_per_round_trip for row in rows]
            rng.shuffle(outcomes)
            permuted = _correlation([row.score for row in rows], outcomes)
            if permuted is not None:
                permuted_ics.append(permuted)
        if permuted_ics and abs(statistics.mean(permuted_ics)) >= abs(mean_ic):
            extreme += 1
    p_value = (extreme + 1) / (request.permutation_iterations + 1)
    dates = len(valid_periods)
    warnings = []
    if dates < 30:
        warnings.append(f"Chỉ có {dates} kỳ hình thành hợp lệ; kết quả thống kê còn yếu (ngưỡng 30 là quy tắc tối thiểu nhóm đặt).")
    if any(len(rows) < 8 for _, rows, _ in valid_periods):
        warnings.append("Một số kỳ có ít hơn 8 mã; phân vị/nhóm cao-thấp kém ổn định.")
    if request.transaction_cost_pct_per_side == 0:
        warnings.append("Lợi suất chưa trừ chi phí giao dịch, thuế và trượt giá.")
    if len({row.ticker for row in request.observations}) < 8:
        warnings.append("Danh mục lịch sử nhỏ; cần đưa cả mã hủy niêm yết/đình chỉ để giảm survivorship bias.")
    horizons = [(rows[0].forward_period_end - formed).days for formed, rows, _ in valid_periods]
    max_horizon = max(horizons)
    if any((later[0] - earlier[0]).days < max_horizon for earlier, later in zip(valid_periods, valid_periods[1:])):
        warnings.append("Các kỳ lợi suất forward có thể chồng lấn; t-stat thường và permutation theo từng ngày không hiệu chỉnh đầy đủ phụ thuộc chuỗi thời gian.")
    return {
        "observations": len(request.observations), "formation_dates": dates,
        "mean_rank_ic": round(mean_ic, 4), "rank_ic_t_stat_iid": round(t_stat, 3) if t_stat is not None else None,
        "permutation_p_value": round(p_value, 4), "mean_top_minus_bottom_excess_return_pct": round(statistics.mean(spreads), 4),
        "top_group_excess_hit_rate_pct": round(sum(value > 0 for value in top_excesses) / len(top_excesses) * 100, 2),
        "verdict": "Tín hiệu đạt ngưỡng thử nghiệm do nhóm đặt; vẫn cần xác nhận trên mẫu holdout ngoài thời gian" if mean_ic > 0.03 and t_stat is not None and t_stat > 2 and p_value < 0.05 and dates >= 30 else "Chưa đủ bằng chứng theo ngưỡng thử nghiệm của nhóm để kết luận điểm số dự báo được lợi suất",
        "warnings": warnings,
        "required_method": ["Dùng dữ liệu point-in-time đã công bố tại ngày tín hiệu", "Lợi suất forward bắt đầu sau signal_date",
                            "Điều chỉnh cổ tức/chia tách và ghi chi phí giao dịch", "Bao gồm mã hủy niêm yết để hạn chế survivorship bias",
                            "Giữ giai đoạn cuối làm holdout; không chọn trọng số bằng chính holdout"],
        "permutation": {"iterations": request.permutation_iterations, "seed": request.random_seed,
                        "null": "Hoán vị lợi suất giữa các mã trong từng kỳ hình thành", "alpha": 0.05},
        "threshold_note": "IC > 0.03 và t-stat > 2 trong bảng phương pháp là ngưỡng kinh nghiệm của nhóm, không phải chuẩn phổ quát; p-value hoán vị và độ nhạy cần được báo cáo cùng kết quả.",
    }


# Metrics explicitly required by the project brief. Inputs retain period/source
# metadata so the API never silently invents financial-statement observations.
class DuPontRequest(BaseModel):
    ticker: str
    period: str
    revenue: float = Field(gt=0)
    net_income: float
    average_total_assets: float = Field(gt=0)
    average_equity: float = Field(gt=0)
    source: str


@router.post("/metrics/dupont")
def calculate_dupont(request: DuPontRequest):
    margin = request.net_income / request.revenue
    turnover = request.revenue / request.average_total_assets
    multiplier = request.average_total_assets / request.average_equity
    roe = margin * turnover * multiplier
    return {"ticker": request.ticker.upper(), "period": request.period, "roe_pct": round(roe * 100, 4),
            "components": {"net_profit_margin_pct": round(margin * 100, 4), "asset_turnover": round(turnover, 4), "equity_multiplier": round(multiplier, 4)},
            "formula": "ROE = (Net income / Revenue) × (Revenue / Average assets) × (Average assets / Average equity)",
            "source": request.source, "type": "calculated metric"}


class FScorePeriod(BaseModel):
    roa: float
    cfo: float
    net_income: float
    total_assets: float = Field(gt=0)
    long_term_debt: float = Field(ge=0)
    current_assets: float = Field(ge=0)
    current_liabilities: float = Field(gt=0)
    shares_outstanding: float = Field(gt=0)
    gross_margin: float
    asset_turnover: float
    period: str


class PiotroskiRequest(BaseModel):
    ticker: str
    current: FScorePeriod
    previous: FScorePeriod
    source: str


@router.post("/metrics/piotroski")
def calculate_piotroski(request: PiotroskiRequest):
    c, p = request.current, request.previous
    tests = [
        (c.roa > 0, "ROA dương", f"{c.roa} > 0"),
        (c.cfo > 0, "CFO dương", f"{c.cfo} > 0"),
        (c.roa > p.roa, "ROA cải thiện", f"{c.roa} > {p.roa}"),
        (c.cfo / c.total_assets > c.roa, "CFO lớn hơn ROA", f"{c.cfo}/{c.total_assets} > {c.roa}"),
        (c.long_term_debt / c.total_assets < p.long_term_debt / p.total_assets, "Đòn bẩy dài hạn giảm", f"{c.long_term_debt}/{c.total_assets} < {p.long_term_debt}/{p.total_assets}"),
        (c.current_assets / c.current_liabilities > p.current_assets / p.current_liabilities, "Thanh khoản cải thiện", "Current ratio hiện tại > kỳ trước"),
        (c.shares_outstanding <= p.shares_outstanding, "Không phát hành thêm cổ phiếu", f"{c.shares_outstanding} ≤ {p.shares_outstanding}"),
        (c.gross_margin > p.gross_margin, "Biên lợi nhuận gộp cải thiện", f"{c.gross_margin} > {p.gross_margin}"),
        (c.asset_turnover > p.asset_turnover, "Vòng quay tài sản cải thiện", f"{c.asset_turnover} > {p.asset_turnover}"),
    ]
    criteria = [{"criterion": label, "passed": bool(passed), "evidence": evidence} for passed, label, evidence in tests]
    return {"ticker": request.ticker.upper(), "score": sum(x["passed"] for x in criteria), "max_score": 9, "criteria": criteria,
            "periods": [p.period, c.period], "source": request.source,
            "limitation": "Piotroski F-Score được thiết kế cho dữ liệu kế toán phù hợp và cần thận trọng khi áp dụng ngoài nhóm doanh nghiệp phi tài chính; không áp dụng ngân hàng ở phiên bản đầu."}


class DebtRequest(BaseModel):
    ticker: str
    net_debt: float
    ebitda: float
    ebit: float
    interest_expense: float = Field(ge=0)
    period: str
    source: str


@router.post("/metrics/debt-risk")
def debt_risk(request: DebtRequest):
    leverage = request.net_debt / request.ebitda if request.ebitda > 0 else None
    coverage = request.ebit / request.interest_expense if request.interest_expense > 0 else None
    warnings = []
    if leverage is None: warnings.append("EBITDA không dương; không thể diễn giải Net Debt/EBITDA.")
    elif leverage > 3: warnings.append("Net Debt/EBITDA > 3×; cần xem xét trong kịch bản tiêu cực.")
    if coverage is None: warnings.append("Không thể tính interest coverage do chi phí lãi vay bằng 0 hoặc chưa có.")
    elif coverage < 2: warnings.append("EBIT/chi phí lãi vay < 2×; khả năng trả lãi cần theo dõi.")
    return {"ticker": request.ticker.upper(), "period": request.period, "net_debt_ebitda": round(leverage, 4) if leverage is not None else None,
            "interest_coverage": round(coverage, 4) if coverage is not None else None, "warnings": warnings,
            "source": request.source, "thresholds": {"leverage_warning_x": 3, "coverage_warning_x": 2, "status": "ngưỡng cảnh báo minh họa do nhóm cấu hình"}}


class PEReferenceRequest(BaseModel):
    ticker: str
    historical_pe: list[float] = Field(min_length=4)
    peer_pe: list[float] = Field(min_length=1)
    peer_tickers: list[str] = Field(default_factory=list)
    period: str
    source: str


@router.post("/valuation/pe-references")
def pe_references(request: PEReferenceRequest):
    hist = sorted(x for x in request.historical_pe if x > 0 and math.isfinite(x))
    peers = sorted(x for x in request.peer_pe if x > 0 and math.isfinite(x))
    if len(hist) < 4 or not peers:
        raise HTTPException(status_code=422, detail="Cần tối thiểu 4 P/E lịch sử dương và ít nhất một P/E peer dương.")
    def quantile(values, p):
        position = (len(values) - 1) * p
        low = math.floor(position); high = math.ceil(position)
        return values[low] if low == high else values[low] * (high - position) + values[high] * (position - low)
    return {"ticker": request.ticker.upper(), "period": request.period,
            "company_historical": {"p25": round(quantile(hist, .25), 4), "median": round(statistics.median(hist), 4), "p75": round(quantile(hist, .75), 4), "observations": len(hist)},
            "peer_group": {"median": round(statistics.median(peers), 4), "observations": len(peers), "tickers": request.peer_tickers},
            "evidence": {"source": request.source, "method": "Historical empirical percentile and cross-sectional peer median; excludes non-positive multiples."},
            "warning": "Peer coverage and common period/industry must be verified. Use historical P25/median/P75 and peer median as evidence when selecting scenario target P/E; selection remains an assumption."}


class PricePoint(BaseModel):
    date: date
    close: float = Field(gt=0)


class MarketRiskRequest(BaseModel):
    ticker: str
    prices: list[PricePoint] = Field(min_length=30)
    benchmark: list[PricePoint] = Field(min_length=30)
    annualization_days: int = Field(default=252, ge=1)


@router.post("/risk/market")
def calculate_market_risk(request: MarketRiskRequest):
    stock = sorted(request.prices, key=lambda x: x.date)
    index = sorted(request.benchmark, key=lambda x: x.date)
    if len({x.date for x in stock}) != len(stock) or len({x.date for x in index}) != len(index):
        raise HTTPException(status_code=422, detail="Chuỗi giá có ngày trùng lặp.")
    smap, imap = {x.date: x.close for x in stock}, {x.date: x.close for x in index}
    dates = sorted(set(smap) & set(imap))
    sr = [(smap[b] / smap[a] - 1) for a, b in zip(dates, dates[1:])]
    ir = [(imap[b] / imap[a] - 1) for a, b in zip(dates, dates[1:])]
    if len(sr) < 20: raise HTTPException(status_code=422, detail="Cần ít nhất 21 ngày giá trùng nhau.")
    vol = statistics.stdev(sr) * math.sqrt(request.annualization_days)
    mean_s, mean_i = statistics.mean(sr), statistics.mean(ir)
    variance_i = sum((x - mean_i) ** 2 for x in ir) / (len(ir) - 1)
    beta = sum((x - mean_s) * (y - mean_i) for x, y in zip(sr, ir)) / (len(sr) - 1) / variance_i if variance_i else None
    peak, max_dd = stock[0].close, 0.0
    for point in stock:
        peak = max(peak, point.close)
        max_dd = min(max_dd, point.close / peak - 1)
    return {"ticker": request.ticker.upper(), "annualized_volatility_pct": round(vol * 100, 4), "max_drawdown_pct": round(max_dd * 100, 4),
            "beta_vs_vnindex": round(beta, 4) if beta is not None else None, "overlap_return_observations": len(sr),
            "method": f"Vol = sample stdev(daily returns) × sqrt({request.annualization_days}); beta dùng ngày trùng; MDD từ chuỗi giá cung cấp.",
            "warning": "Cần chuỗi giá điều chỉnh cổ tức/chia tách, cùng tần suất và kỳ; MDD tính theo giá đầu vào."}


class CoverageObservation(BaseModel):
    signal_date: date
    future_date: date
    bear_price: float = Field(gt=0)
    bull_price: float = Field(gt=0)
    actual_future_price: float = Field(gt=0)
    horizon_months: Literal[3, 6, 12] | None = None

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.future_date <= self.signal_date: raise ValueError("Ngày giá tương lai phải sau ngày tín hiệu.")
        if self.bull_price < self.bear_price: raise ValueError("Giá tích cực phải lớn hơn hoặc bằng giá tiêu cực.")
        return self


class CoverageBacktestRequest(BaseModel):
    ticker: str
    observations: list[CoverageObservation] = Field(min_length=1)


@router.post("/backtest/scenario-coverage")
def scenario_coverage_backtest(request: CoverageBacktestRequest):
    covered = [x for x in request.observations if x.bear_price <= x.actual_future_price <= x.bull_price]
    by_horizon = {}
    for horizon in (3, 6, 12):
        group = [x for x in request.observations if x.horizon_months == horizon]
        if group:
            inside = sum(x.bear_price <= x.actual_future_price <= x.bull_price for x in group)
            by_horizon[str(horizon)] = {"observations": len(group), "covered": inside, "coverage_rate_pct": round(inside / len(group) * 100, 2)}
    return {"ticker": request.ticker.upper(), "observations": len(request.observations), "covered": len(covered),
            "coverage_rate_pct": round(len(covered) / len(request.observations) * 100, 2),
            "by_horizon_months": by_horizon,
            "method": "Coverage = actual future price nằm trong [bear price, bull price].",
            "warning": "Đây là kiểm định độ bao phủ, không chứng minh dự báo chính xác hay sinh lời; cần point-in-time, giá điều chỉnh và mẫu ngoài thời gian. Báo cáo riêng theo kỳ hạn; nếu mỗi nhóm ít quan sát, kết quả chỉ mang tính mô tả và chưa đủ kết luận."}


class Observation(BaseModel):
    ticker: str
    period: str | None = None
    metric: str
    value: float | None = None
    unit: str | None = None
    source: str


class DataValidationRequest(BaseModel):
    observations: list[Observation]
    required_metrics: list[str] = Field(default_factory=list)


@router.post("/data/validate")
def validate_financial_observations(request: DataValidationRequest):
    issues = []
    keys = [(x.ticker.upper(), x.period, x.metric.lower(), x.source) for x in request.observations]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates: issues.append({"type": "duplicate", "items": [list(x) for x in duplicates]})
    for i, item in enumerate(request.observations):
        if item.value is None: issues.append({"type": "missing_value", "row": i, "metric": item.metric})
        if not item.period: issues.append({"type": "missing_period", "row": i, "metric": item.metric})
        if not item.unit: issues.append({"type": "missing_unit", "row": i, "metric": item.metric})
    available = {x.metric for x in request.observations if x.value is not None}
    for metric in request.required_metrics:
        if metric not in available: issues.append({"type": "required_metric_missing", "metric": metric})
    by_metric = defaultdict(list)
    for item in request.observations:
        if item.value is not None: by_metric[item.metric.lower()].append(item.value)
    for metric, values in by_metric.items():
        if len(values) >= 4:
            q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
            spread = q3 - q1
            outliers = [v for v in values if v < q1 - 3 * spread or v > q3 + 3 * spread]
            if outliers: issues.append({"type": "possible_outlier", "metric": metric, "values": outliers, "rule": "outside 3×IQR; requires review"})
    return {"rows": len(request.observations), "valid": not issues, "issues": issues,
            "limitations": ["Không thể phát hiện sai đơn vị nếu nhãn unit bị khai báo sai.", "Outlier là cảnh báo thống kê, không tự động xóa dữ liệu.", "Sai khác giữa nguồn chỉ đánh giá được khi gửi các quan sát đối chiếu cùng metric/kỳ/đơn vị."]}
