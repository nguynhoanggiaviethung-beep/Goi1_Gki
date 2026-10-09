"""Transparent scenario valuation and customized PDF report endpoints."""

from __future__ import annotations

from io import BytesIO
import json
from typing import Literal

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.app.market_data import fetch_live_inputs
<<<<<<< HEAD
from backend.app import vnequity_bridge as bridge
=======
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590

router = APIRouter(tags=["scenario analysis"])


class DataProvenance(BaseModel):
    source: str = Field(min_length=1, description="Nguồn dữ liệu hoặc URL")
    period: str = Field(min_length=1, description="Kỳ dữ liệu, ví dụ FY2025")
    retrieved_at: str | None = Field(default=None, description="Ngày lấy dữ liệu")


class ScenarioOverride(BaseModel):
    earnings_growth_pct: float | None = Field(default=None, ge=-99.9, le=500)
    target_pe: float | None = Field(default=None, gt=0, le=500)


class ScenarioRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    current_price: float = Field(gt=0, description="Giá hiện tại trên mỗi cổ phiếu")
    eps: float = Field(gt=0, description="EPS cơ sở dương trên mỗi cổ phiếu")
    earnings_growth_pct: float = Field(ge=-99.9, le=500, description="Tăng trưởng EPS hằng năm, phần trăm")
    target_pe: float = Field(gt=0, le=500)
    horizon_years: int = Field(default=1, ge=1, le=10)
    horizon_months: int | None = Field(default=None, ge=1, le=120)
    earnings_growth_basis: Literal["annualized", "holding_period"] = "annualized"
    pe_basis: str = "P/E mục tiêu áp dụng cho EPS cơ sở cùng kỳ"
    currency: str = Field(default="VND", min_length=1, max_length=8)
    price_data: DataProvenance
    eps_data: DataProvenance
    overrides: dict[Literal["bullish", "base", "bearish"], ScenarioOverride] = Field(default_factory=dict)
    probabilities_pct: dict[Literal["bullish", "base", "bearish"], float] | None = None
    dividend_yield_pct: float = Field(default=0, ge=0, le=100)
    buy_threshold_pct: float = 10
    sell_threshold_pct: float = -10
<<<<<<< HEAD
    horizon_thresholds_pct: dict[int, dict[Literal["buy", "sell"], float]] = Field(default_factory=dict)
=======
    horizon_thresholds_pct: dict[Literal[3, 6, 12], dict[Literal["buy", "sell"], float]] = Field(default_factory=dict)
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
    sensitivity_growth_pct: list[float] = Field(default_factory=list, max_length=15)
    sensitivity_pe: list[float] = Field(default_factory=list, max_length=15)
    growth_history: list[dict] = Field(default_factory=list)
    pe_history: list[dict] = Field(default_factory=list)
    growth_history_source: str = ""
    use_base_inputs_as_overrides: bool = True

    @model_validator(mode="after")
    def validate_probabilities(self):
        if self.probabilities_pct is not None and (set(self.probabilities_pct) != {"bullish", "base", "bearish"} or not abs(sum(self.probabilities_pct.values()) - 100) < 1e-6):
            raise ValueError("Xác suất cần đủ ba kịch bản và tổng bằng 100%.")
        if self.sell_threshold_pct >= self.buy_threshold_pct:
            raise ValueError("Ngưỡng bán phải nhỏ hơn ngưỡng mua.")
        if self.horizon_months is not None and self.horizon_months not in {3, 6, 12}:
            raise ValueError("Kỳ hạn kịch bản hỗ trợ 3, 6 hoặc 12 tháng.")
        return self


class ReportOptions(BaseModel):
    purpose: Literal["full", "long_term", "trader", "one_pager", "committee"] = "full"
    years_shown: int = Field(default=5, ge=1, le=10)
    horizon_years: int | None = Field(default=None, ge=1, le=10)
    horizon_months: Literal[3, 6, 12] | None = None
    metric_groups: list[Literal["executive_summary", "financial_analysis", "valuation", "scenario", "sensitivity", "risk", "market_risk", "evidence", "charts", "final_assessment", "assumptions"]] = Field(default_factory=list)
    include_chart: bool = True
    detail_level: Literal["summary", "standard", "detailed"] = "standard"


class ScenarioReportRequest(BaseModel):
    analysis: ScenarioRequest
    report: ReportOptions = Field(default_factory=ReportOptions)
    supplemental_sections: dict[str, dict] = Field(default_factory=dict)

    @model_validator(mode="after")
    def apply_report_horizon(self):
        if self.report.horizon_months is not None:
            self.analysis.horizon_months = self.report.horizon_months
        if self.report.horizon_years is not None:
            self.analysis.horizon_years = self.report.horizon_years
        return self


class LiveScenarioRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    earnings_growth_pct: float | None = Field(default=None, ge=-99.9, le=500, description="Để trống để tính CAGR từ lịch sử EPS khả dụng")
    target_pe: float | None = Field(default=None, gt=0, le=500, description="Để trống để dùng P/E mới nhất từ vnstock")
    horizon_years: int = Field(default=1, ge=1, le=10)
    horizon_months: Literal[3, 6, 12] | None = None
    earnings_growth_basis: Literal["annualized", "holding_period"] = "annualized"
    overrides: dict[Literal["bullish", "base", "bearish"], ScenarioOverride] = Field(default_factory=dict)
    probabilities_pct: dict[Literal["bullish", "base", "bearish"], float] | None = None
    dividend_yield_pct: float = Field(default=0, ge=0, le=100)
    buy_threshold_pct: float = 10
    sell_threshold_pct: float = -10
<<<<<<< HEAD
    horizon_thresholds_pct: dict[int, dict[Literal["buy", "sell"], float]] = Field(default_factory=dict)
=======
    horizon_thresholds_pct: dict[Literal[3, 6, 12], dict[Literal["buy", "sell"], float]] = Field(default_factory=dict)
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
    sensitivity_growth_pct: list[float] = Field(default_factory=list, max_length=15)
    sensitivity_pe: list[float] = Field(default_factory=list, max_length=15)
    purpose: str | None = None

    @model_validator(mode="after")
    def validate_live_options(self):
        if self.probabilities_pct is not None and (set(self.probabilities_pct) != {"bullish", "base", "bearish"} or not abs(sum(self.probabilities_pct.values()) - 100) < 1e-6):
            raise ValueError("Xác suất cần đủ ba kịch bản và tổng bằng 100%.")
        if self.sell_threshold_pct >= self.buy_threshold_pct:
            raise ValueError("Ngưỡng bán phải nhỏ hơn ngưỡng mua.")
        for months, bounds in self.horizon_thresholds_pct.items():
<<<<<<< HEAD
            if months not in (3, 6, 12):
                raise ValueError("Ngưỡng theo kỳ hạn chỉ hỗ trợ 3, 6 hoặc 12 tháng.")
            if not {"buy", "sell"} <= set(bounds):
                raise ValueError(f"Ngưỡng kỳ hạn {months} tháng cần đủ buy và sell.")
=======
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
            if bounds["sell"] >= bounds["buy"]:
                raise ValueError(f"Ngưỡng bán phải nhỏ hơn ngưỡng mua ở kỳ hạn {months} tháng.")
        return self


class LiveScenarioReportRequest(LiveScenarioRequest):
    report: ReportOptions = Field(default_factory=ReportOptions)

    @model_validator(mode="after")
    def apply_report_horizon(self):
        if self.report.horizon_months is not None:
            self.horizon_months = self.report.horizon_months
        if self.report.horizon_years is not None:
            self.horizon_years = self.report.horizon_years
        return self


def analyze_scenarios(request: ScenarioRequest) -> dict:
    """Compute EPS × target P/E estimates and attach auditable evidence cards."""
    labels = {
        "bullish": "Tích cực",
        "base": "Cơ sở",
        "bearish": "Tiêu cực",
    }
    growth_values = [float(row["growth_pct"]) for row in request.growth_history if row.get("growth_pct") is not None and float(row["growth_pct"]) > -100]
    pe_values = [float(row["pe"]) for row in request.pe_history if row.get("pe") is not None and float(row["pe"]) > 0]
    def percentile(values: list[float], p: float) -> float:
        ordered = sorted(values)
        position = (len(ordered) - 1) * p
        low = int(position); high = min(low + 1, len(ordered) - 1)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    growth_clipped = 0
    growth_quantiles = None
    growth_norm = []
    if len(growth_values) >= 4:
        lo, hi = percentile(growth_values, .05), percentile(growth_values, .95)
        growth_norm = [min(hi, max(lo, value)) for value in growth_values]
        growth_clipped = sum(a != b for a, b in zip(growth_values, growth_norm))
        growth_quantiles = {"bearish": percentile(growth_norm, .25), "base": percentile(growth_norm, .50), "bullish": percentile(growth_norm, .75), "p5": lo, "p95": hi}
    pe_quantiles = {"bearish": percentile(pe_values, .25), "base": percentile(pe_values, .50), "bullish": percentile(pe_values, .75)} if len(pe_values) >= 4 else None
    has_quantiles = growth_quantiles is not None and pe_quantiles is not None
    defaults = {
        key: ((growth_quantiles or {}).get(key, request.earnings_growth_pct), (pe_quantiles or {}).get(key, request.target_pe))
        for key in ("bullish", "base", "bearish")
    }
    if request.use_base_inputs_as_overrides and has_quantiles:
        defaults["base"] = (request.earnings_growth_pct, request.target_pe)
    scenarios = []
    horizon_year_fraction = (request.horizon_months / 12) if request.horizon_months is not None else request.horizon_years
    # Annual forward EPS is the valuation denominator for every tracking horizon.
    growth_exponent = 1.0
    thresholds = request.horizon_thresholds_pct.get(request.horizon_months, {}) if request.horizon_months else {}
    buy_threshold = thresholds.get("buy", request.buy_threshold_pct)
    sell_threshold = thresholds.get("sell", request.sell_threshold_pct)
    for key in ("bullish", "base", "bearish"):
        override = request.overrides.get(key, ScenarioOverride())
        growth, pe = defaults[key]
        growth = override.earnings_growth_pct if override.earnings_growth_pct is not None else growth
        pe = override.target_pe if override.target_pe is not None else pe
        if pe <= 0:
            # Keep the default multiple positive when the base multiple is very low.
            pe = 0.1

        projected_eps = request.eps * (1 + growth / 100) ** growth_exponent
        estimated_price = projected_eps * pe
        estimated_dividends = request.current_price * (request.dividend_yield_pct / 100) * horizon_year_fraction
        return_pct = ((estimated_price + estimated_dividends) / request.current_price - 1) * 100
        evidence = [
            {
                "claim": "EPS dự phóng",
                "value": round(projected_eps, 4),
                "unit": f"{request.currency}/cổ phiếu",
                "formula": f"{request.eps} × (1 + {growth}/100)^{growth_exponent}",
                "inputs": {"base_eps": request.eps, "growth_pct": growth, "growth_exponent": growth_exponent, "growth_basis": request.earnings_growth_basis, "horizon_year_fraction": horizon_year_fraction},
                "source": request.eps_data.source,
                "period": request.eps_data.period,
                "retrieved_at": request.eps_data.retrieved_at,
            },
            {
                "claim": "Cơ sở P/E mục tiêu",
                "value": round(pe, 4), "unit": "×",
                "formula": "P/E mục tiêu × EPS dự phóng cùng cơ sở kỳ",
                "inputs": {"target_pe": round(pe, 4), "eps_period": request.eps_data.period, "pe_basis": request.pe_basis},
                "source": request.pe_basis, "period": request.eps_data.period, "retrieved_at": request.eps_data.retrieved_at,
            },
            {
                "claim": "Giá ước tính theo P/E",
                "value": round(estimated_price, 2),
                "unit": f"{request.currency}/cổ phiếu",
                "formula": f"EPS dự phóng {round(projected_eps, 4)} × P/E mục tiêu {round(pe, 4)}",
                "inputs": {"projected_eps": round(projected_eps, 4), "target_pe": round(pe, 4)},
                "source": "Công thức định giá P/E; P/E mục tiêu là giả định người dùng/hệ thống",
                "period": f"Kỳ dự phóng {request.horizon_months} tháng" if request.horizon_months else f"Kỳ dự phóng {request.horizon_years} năm",
                "retrieved_at": None,
            },
            {
                "claim": "Tỷ suất sinh lời theo kịch bản",
                "value": round(return_pct, 2),
                "unit": "%",
                "formula": f"(({round(estimated_price, 2)} + {request.current_price} × {request.dividend_yield_pct}/100 × {horizon_year_fraction}) / {request.current_price} − 1) × 100",
                "inputs": {"estimated_price": round(estimated_price, 2), "current_price": request.current_price, "dividend_yield_pct": request.dividend_yield_pct, "horizon_year_fraction": horizon_year_fraction, "dividend_method": "lợi suất cổ tức năm × thời gian nắm giữ × giá hiện tại; không giả định tái đầu tư"},
                "source": request.price_data.source,
                "period": request.price_data.period,
                "retrieved_at": request.price_data.retrieved_at,
            },
        ]
        if has_quantiles:
            growth_index = {"bearish": .25, "base": .50, "bullish": .75}[key]
            pe_index = growth_index
            evidence.extend([
                {"claim": "Cơ sở phân vị tăng trưởng EPS", "value": round((growth_quantiles or {})[key], 4), "unit": "%", "formula": f"P{int(growth_index * 100)} của Growth_norm; Growth_norm = clip(Growth, P5, P95)", "inputs": {"raw_observations": request.growth_history, "winsorized_observations_pct": [round(value, 4) for value in growth_norm], "p5_pct": round(growth_quantiles["p5"], 4), "p95_pct": round(growth_quantiles["p95"], 4), "n": len(growth_values), "winsorized_count": growth_clipped}, "source": request.growth_history_source or "Nguồn dữ liệu chuỗi EPS do request cung cấp", "period": "Các năm tài chính liền kề hợp lệ"},
                {"claim": "Cơ sở phân vị P/E lịch sử", "value": round((pe_quantiles or {})[key], 4), "unit": "×", "formula": f"P{int(pe_index * 100)} của Historical P/E dương, đồng kỳ EPS", "inputs": {"observations": request.pe_history, "n": len(pe_values), "period_alignment": "lọc theo đúng các kỳ EPS khả dụng"}, "source": request.growth_history_source or "Nguồn dữ liệu chuỗi P/E do request cung cấp", "period": "Các kỳ EPS lịch sử trùng khớp"},
            ])
        scenarios.append({
            "key": key,
            "label": labels[key],
            "earnings_growth_pct": round(growth, 2),
            "target_pe": round(pe, 4),
            "projected_eps": round(projected_eps, 4),
            "estimated_price": round(estimated_price, 2),
            "expected_return_pct": round(return_pct, 2),
            "assessment": "BUY" if return_pct >= buy_threshold else "SELL" if return_pct <= sell_threshold else "HOLD",
            "assumption_basis": ("Điều chỉnh thủ công theo đầu vào người dùng; thay thế phân vị của kịch bản này." if request.overrides.get(key) and (request.overrides[key].earnings_growth_pct is not None or request.overrides[key].target_pe is not None) else "Phân vị lịch sử: tăng trưởng EPS P25/P50/P75 sau winsor hóa P5/P95 và P/E lịch sử P25/P50/P75; chỉ báo cáo độ tin cậy khi đủ ít nhất 4 quan sát mỗi chuỗi." if has_quantiles else "Lịch sử chưa đủ 4 quan sát hợp lệ cho cả tăng trưởng EPS và P/E; dùng giá trị cơ sở đồng nhất, không tạo chênh lệch giả định. Hãy nhập override cả ba kịch bản hoặc bổ sung lịch sử."),
            "evidence": evidence,
        })

    probabilities = request.probabilities_pct
    expected_value = None
    if probabilities is not None:
        expected_value = round(sum(item["estimated_price"] * probabilities[item["key"]] / 100 for item in scenarios), 2)
    sensitivity = []
    for g in request.sensitivity_growth_pct:
        sensitivity.append({"growth_pct": g, "prices": [{"target_pe": pe, "estimated_price": round(request.eps * (1 + g / 100) ** horizon_year_fraction * pe, 2)} for pe in request.sensitivity_pe]})
    order_warnings = []
    by_key = {row["key"]: row for row in scenarios}
    if not has_quantiles:
        order_warnings.append("Chưa đủ tối thiểu 4 quan sát cho cả hai chuỗi phân vị; các kịch bản mặc định dùng cùng giá trị cơ sở, độ tin cậy thấp.")
    if not (by_key["bullish"]["estimated_price"] >= by_key["base"]["estimated_price"] >= by_key["bearish"]["estimated_price"]):
        order_warnings.append("Giá kịch bản chưa theo thứ tự Tích cực > Cơ sở > Tiêu cực; hãy kiểm tra giả định.")
    return {
        "ticker": request.ticker.strip().upper(),
        "currency": request.currency,
        "horizon_years": request.horizon_years,
        "horizon_months": request.horizon_months if request.horizon_months is not None else request.horizon_years * 12,
        "current_price": request.current_price,
        "method": "Phân vị lịch sử: tăng trưởng EPS P25/P50/P75 (winsor hóa P5/P95) × P/E lịch sử P25/P50/P75",
        "earnings_growth_basis": request.earnings_growth_basis,
        "pe_basis": request.pe_basis,
        "scenarios": scenarios,
        "probabilities_pct": probabilities,
        "probability_weighted_value": expected_value,
        "recommendation_thresholds_pct": {"buy": buy_threshold, "sell": sell_threshold, "horizon_months": request.horizon_months, "configured_by_horizon": bool(request.horizon_thresholds_pct)},
        "growth_formula": f"EPS × (1 + g)^{growth_exponent}; growth basis: {request.earnings_growth_basis}",
        "sensitivity_grid": {"growth_pct": request.sensitivity_growth_pct, "target_pe": request.sensitivity_pe, "cells": sensitivity},
        "configuration_warnings": order_warnings,
        "data_types": {"market_inputs": "actual data", "scenario_parameters": "user/system assumptions", "prices_and_returns": "calculated metrics"},
        "interpretation": "Các kịch bản là phân tích độ nhạy theo giả định; không phải xác suất hoặc khuyến nghị đầu tư.",
        "scenario_method": {"growth_observations": len(growth_values), "growth_winsorized_count": growth_clipped, "growth_winsor_bounds_pct": [round(growth_quantiles["p5"], 2), round(growth_quantiles["p95"], 2)] if growth_quantiles else None, "growth_quantiles_pct": {k: round(v, 2) for k, v in growth_quantiles.items() if k in {"bearish", "base", "bullish"}} if growth_quantiles else None, "pe_observations": len(pe_values), "pe_quantiles": {k: round(v, 4) for k, v in pe_quantiles.items()} if pe_quantiles else None, "status": "historical_quantiles" if has_quantiles else "insufficient_history", "minimum_observations": 4, "eps_history_source": request.growth_history_source, "horizon_note": "Giá mục tiêu dùng EPS dự phóng 12 tháng cho mọi kỳ; 3/6/12 tháng là kỳ theo dõi/đánh giá lợi suất và ngưỡng khuyến nghị."},
        "data_confidence": {"score": round(min(len(growth_values), 8) * 4 + min(len(pe_values), 8) * 4 + (18 if has_quantiles else 0) + (18 if request.growth_history_source else 0)), "label": "Cao" if has_quantiles and len(growth_values) >= 8 and len(pe_values) >= 8 else "Trung bình" if has_quantiles else "Thấp", "basis": "Điểm độ phủ: số quan sát tăng trưởng (tối đa 32), P/E (tối đa 32), đủ phân vị (18), có khai báo nguồn chuỗi lịch sử (18). Đây là thang kiểm tra độ phủ dữ liệu, không phải xác suất đúng; mức tối đa trong từng báo cáo phụ thuộc lịch sử khả dụng."},
        "limitations": [
            "Phương pháp P/E chỉ phù hợp khi EPS dương và có ý nghĩa; không xử lý tốt doanh nghiệp lỗ hoặc lợi nhuận bất thường.",
            "Nếu lịch sử hợp lệ dưới 4 quan sát cho tăng trưởng hoặc P/E, các phân vị không được ước lượng; kịch bản đồng nhất theo đầu vào cơ sở cho đến khi có đủ dữ liệu hoặc người dùng nhập giả định riêng.",
            "Giá trị xác suất có trọng số chỉ được tính khi người dùng cung cấp xác suất tổng 100%; không phải giá mục tiêu duy nhất.",
        ],
    }


@router.post("/scenario/analyze")
def scenario_analyze(request: ScenarioRequest):
    """Run a three-case valuation and return evidence cards for every calculated claim."""
    return analyze_scenarios(request)


def _analyze_live(request: LiveScenarioRequest) -> dict:
<<<<<<< HEAD
    """Ưu tiên engine VNEquity (BCTC chuẩn hoá + giá ngày); mã ngoài bộ dữ liệu -> luồng vnstock gốc."""
    try:
        res = bridge.run(request)
    except bridge.EngineUnavailable:
        return _analyze_live_vnstock(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return bridge.to_live(res, request)


def _analyze_live_vnstock(request: LiveScenarioRequest) -> dict:
=======
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
    live = fetch_live_inputs(
        ticker=request.ticker,
        growth_override=request.earnings_growth_pct,
        pe_override=request.target_pe,
    )
    overrides = dict(request.overrides)
    base_override = overrides.get("base", ScenarioOverride())
    if request.earnings_growth_pct is not None and base_override.earnings_growth_pct is None:
        base_override.earnings_growth_pct = request.earnings_growth_pct
    if request.target_pe is not None and base_override.target_pe is None:
        base_override.target_pe = request.target_pe
    if base_override.earnings_growth_pct is not None or base_override.target_pe is not None:
        overrides["base"] = base_override
    analysis = ScenarioRequest(
        ticker=live["ticker"],
        current_price=live["current_price"],
        eps=live["eps"],
        earnings_growth_pct=live["earnings_growth_pct"],
        target_pe=live["target_pe"],
        horizon_years=request.horizon_years,
        horizon_months=request.horizon_months,
        earnings_growth_basis=request.earnings_growth_basis,
        pe_basis=live["pe_basis"],
        price_data=DataProvenance(
            source=live["source"], period=live["price_period"], retrieved_at=live["retrieved_at"]
        ),
        eps_data=DataProvenance(
            source=f"{live['source']}; {live['eps_basis']}", period=live["eps_period"], retrieved_at=live["retrieved_at"]
        ),
        overrides=overrides,
        probabilities_pct=request.probabilities_pct,
        dividend_yield_pct=request.dividend_yield_pct,
        buy_threshold_pct=request.buy_threshold_pct,
        sell_threshold_pct=request.sell_threshold_pct,
        horizon_thresholds_pct=request.horizon_thresholds_pct,
        sensitivity_growth_pct=request.sensitivity_growth_pct,
        sensitivity_pe=request.sensitivity_pe,
        growth_history=live["growth_history"],
        pe_history=live["pe_history"],
        growth_history_source=live["source"],
        use_base_inputs_as_overrides=False,
    )
    result = analyze_scenarios(analysis)
    result["data_status"] = {
        "provider": "vnstock",
        "retrieved_at": live["retrieved_at"],
        "freshness": live["freshness"],
        "price_period": live["price_period"],
        "eps_period": live["eps_period"],
        "eps_basis": live["eps_basis"],
        "growth_basis": live["growth_period"],
        "pe_basis": live["pe_basis"],
        "growth_observations": len(live["growth_history"]),
        "pe_observations_same_eps_periods": len(live["pe_history"]),
    }
    return result


@router.post("/scenario/live")
def scenario_analyze_live(request: LiveScenarioRequest):
    """Fetch a delayed latest quote and latest available fundamentals, then analyze."""
    return _analyze_live(request)


def _build_pdf(result: dict, options: ReportOptions, supplemental_sections: dict | None = None) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=f"Phân tích kịch bản {result['ticker']}",
        author="Goi1_Gki",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCentered", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#12345a")))
    purpose_names = {"full": "Báo cáo đầy đủ", "long_term": "Nhà đầu tư dài hạn", "trader": "Theo dõi giao dịch", "one_pager": "Tóm tắt một trang", "committee": "Trình bày hội đồng"}
    purpose_groups = {
        "full": ["executive_summary", "valuation", "scenario", "sensitivity", "financial_analysis", "risk", "market_risk", "evidence", "charts", "final_assessment", "assumptions"],
        "long_term": ["executive_summary", "scenario", "financial_analysis", "valuation", "risk", "evidence", "final_assessment", "assumptions"],
        "trader": ["executive_summary", "scenario", "valuation", "market_risk", "risk", "charts", "final_assessment"],
        "one_pager": ["executive_summary", "valuation", "scenario", "final_assessment"],
        "committee": ["executive_summary", "scenario", "valuation", "sensitivity", "financial_analysis", "risk", "market_risk", "evidence", "charts", "final_assessment", "assumptions"],
    }
    groups = set(options.metric_groups or purpose_groups[options.purpose])
    story = [
        Paragraph("VNEQUITY RESEARCH · " + purpose_names[options.purpose].upper(), styles["Heading3"]),
        Paragraph(f"Báo cáo phân tích cổ phiếu {escape(str(result['ticker']))}", styles["TitleCentered"]),
        Paragraph(f"Giá hiện tại: {result['current_price']:,.2f} {escape(str(result['currency']))} | Kỳ theo dõi: {result['horizon_months']} tháng | Giá mục tiêu sử dụng EPS dự phóng 12 tháng", styles["Normal"]),
        Spacer(1, 5 * mm),
    ]

    if "executive_summary" in groups:
        ret_text = " · ".join(f"{x['label']}: {x['expected_return_pct']:.2f}%" for x in result["scenarios"])
        story.extend([Paragraph("TÓM TẮT ĐẦU TƯ", styles["Heading2"]), Paragraph(f"Giá thị trường {result['current_price']:,.0f} {result['currency']}. Lợi suất theo ba kịch bản: {escape(ret_text)}. Kết quả phụ thuộc vào giả định và chất lượng lịch sử khả dụng.", styles["BodyText"]), Spacer(1, 3 * mm)])

    if "valuation" in groups or "scenario" in groups:
        rows = [["Kịch bản", "Tăng trưởng EPS", "P/E mục tiêu", "Giá ước tính", "Lợi suất"]]
        for item in result["scenarios"]:
            rows.append([
                item["label"], f"{item['earnings_growth_pct']:.2f}%", f"{item['target_pe']:.2f}×",
                f"{item['estimated_price']:,.2f}", f"{item['expected_return_pct']:.2f}%",
            ])
        table = Table(rows, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F2A4A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 7),
            ("TEXTCOLOR", (0, 1), (0, 1), colors.HexColor("#15803D")),
            ("TEXTCOLOR", (0, 2), (0, 2), colors.HexColor("#1E3A8A")),
            ("TEXTCOLOR", (0, 3), (0, 3), colors.HexColor("#B91C1C")),
        ]))
        story.extend([Paragraph("Kết quả theo kịch bản", styles["Heading2"]), table, Spacer(1, 4 * mm)])

    if options.include_chart and ("valuation" in groups or "charts" in groups):
        chart = Drawing(170 * mm, 48 * mm)
        bars = HorizontalBarChart()
        bars.x = 35 * mm
        bars.y = 4 * mm
        bars.width = 120 * mm
        bars.height = 38 * mm
        bars.data = [[item["estimated_price"] for item in result["scenarios"]]]
        bars.categoryAxis.categoryNames = [item["label"] for item in result["scenarios"]]
        bars.categoryAxis.labels.fontName = "Helvetica"
        bars.categoryAxis.labels.fontSize = 8
        bars.valueAxis.valueMin = min(0, min(item["estimated_price"] for item in result["scenarios"]))
        bars.valueAxis.valueMax = max(1, max(item["estimated_price"] for item in result["scenarios"]) * 1.15)
        bars.valueAxis.labels.fontName = "Helvetica"
        bars.valueAxis.labels.fontSize = 7
        bars.bars[0].fillColor = colors.HexColor("#2563eb")
        bars.barWidth = 7 * mm
        bars.groupSpacing = 4 * mm
        chart.add(bars)
        story.extend([Paragraph("So sánh giá ước tính", styles["Heading2"]), chart, Spacer(1, 4 * mm)])

    if "assumptions" in groups or "scenario" in groups:
        story.extend([Paragraph("Giả định", styles["Heading2"]), Paragraph(
            f"EPS cơ sở: {result['scenarios'][1]['evidence'][0]['inputs']['base_eps']} {result['currency']}/cổ phiếu. "
            f"Cách quy đổi tăng trưởng: {escape(str(result['growth_formula']))}. Cơ sở P/E: {escape(str(result['pe_basis']))}. "
            f"Tăng trưởng và P/E mục tiêu được hiển thị riêng cho từng kịch bản. Các giá trị mặc định là giả định minh họa và phải được kiểm tra/cập nhật theo bằng chứng.",
            styles["BodyText"]), Spacer(1, 3 * mm)])
        method = result.get("scenario_method", {})
        story.append(Paragraph(f"Phương pháp: lấy tăng trưởng EPS năm liền kề, loại EPS không dương/đổi dấu, winsor hóa P5–P95 rồi dùng P25/P50/P75; P/E lịch sử dùng cùng các kỳ EPS và phân vị P25/P50/P75. Số quan sát hợp lệ: tăng trưởng {method.get('growth_observations', 0)}, P/E {method.get('pe_observations', 0)}; số tăng trưởng winsor hóa: {method.get('growth_winsorized_count', 0)}. Trạng thái: {escape(str(method.get('status', 'chưa có chuỗi lịch sử')))}. {escape(str(method.get('horizon_note', '')))}", styles["BodyText"]))

    if "evidence" in groups:
        story.append(Paragraph("Thẻ bằng chứng và nguồn dữ liệu", styles["Heading2"]))
        selected = result["scenarios"] if options.detail_level == "detailed" else [result["scenarios"][1]]
        for item in selected:
            story.append(Paragraph(item["label"], styles["Heading3"]))
            for card in item["evidence"]:
                story.append(Paragraph(
                    f"<b>{escape(str(card['claim']))}: {card['value']} {escape(str(card['unit']))}</b><br/>"
                    f"Công thức: {escape(str(card['formula']))}<br/>Nguồn: {escape(str(card['source']))} | Kỳ: {escape(str(card['period']))}"
                    + (f"<br/>Đầu vào: {escape(json.dumps(card.get('inputs', {}), ensure_ascii=False, default=str))}" if options.detail_level == "detailed" else "")
                    + (f" | Ngày lấy: {escape(str(card['retrieved_at']))}" if card.get("retrieved_at") else ""),
                    styles["BodyText"],
                ))
                story.append(Spacer(1, 2 * mm))

    if "sensitivity" in groups:
        story.append(Paragraph("Độ nhạy theo giả định", styles["Heading2"]))
        grid = result.get("sensitivity_grid", {})
        if grid.get("cells") and grid.get("target_pe"):
            sensitivities = [["Tăng trưởng \\ P/E", *[f"{v:g}×" for v in grid["target_pe"]]]]
            for row in grid["cells"]:
                sensitivities.append([f"{row['growth_pct']:g}%", *[f"{cell['estimated_price']:,.2f}" for cell in row["prices"]]])
            sens_table = Table(sensitivities, repeatRows=1, hAlign="LEFT")
            sens_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")), ("PADDING", (0, 0), (-1, -1), 6)]))
            story.extend([sens_table, Spacer(1, 4 * mm)])
        else:
            story.append(Paragraph("Chưa có lưới độ nhạy: gửi sensitivity_growth_pct và sensitivity_pe trong dữ liệu phân tích để tạo bảng.", styles["BodyText"]))

    if result.get("probability_weighted_value") is not None and "scenario" in groups:
        story.append(Paragraph(f"Giá trị xác suất có trọng số (riêng, không thay thế các mức kịch bản): {result['probability_weighted_value']:,.2f} {result['currency']}", styles["BodyText"]))
    if "final_assessment" in groups:
        story.append(Paragraph("Đánh giá theo ngưỡng đã cấu hình", styles["Heading2"]))
        story.append(Paragraph("; ".join(f"{x['label']}: {x['assessment']} ({x['expected_return_pct']:.2f}%)" for x in result["scenarios"]), styles["BodyText"]))
        story.append(Paragraph(f"BUY ≥ {result['recommendation_thresholds_pct']['buy']:g}%; SELL ≤ {result['recommendation_thresholds_pct']['sell']:g}%; các mức còn lại HOLD. Đây là ngưỡng do người dùng/nhóm cấu hình.", styles["BodyText"]))

    supplemental_sections = supplemental_sections or {}
    section_titles = {"financial_analysis": "Phân tích tài chính", "risk": "Rủi ro doanh nghiệp", "market_risk": "Rủi ro thị trường"}
    for section in ("financial_analysis", "risk", "market_risk"):
        if section in groups:
            payload = supplemental_sections.get(section)
            story.append(Paragraph(section_titles[section], styles["Heading2"]))
            if payload:
                for key, value in payload.items():
                    story.append(Paragraph(f"<b>{escape(str(key))}:</b> {escape(str(value))}", styles["BodyText"]))
            else:
                story.append(Paragraph("Chưa có dữ liệu cho phần này trong yêu cầu báo cáo; hãy đính kèm kết quả API tương ứng sau khi kiểm tra kỳ và nguồn.", styles["BodyText"]))

    if options.detail_level != "summary":
        story.append(Paragraph("Diễn giải và giới hạn", styles["Heading2"]))
        story.append(Paragraph(result["interpretation"], styles["BodyText"]))
        for limitation in result["limitations"]:
            story.append(Paragraph(f"• {limitation}", styles["BodyText"]))

    story.append(Paragraph("Nguồn và lưu ý", styles["Heading2"]))
    story.append(Paragraph(f"Nguồn dữ liệu thị trường: vnstock (nhà cung cấp bên thứ ba). Thời điểm truy xuất: {escape(str(result.get('data_status', {}).get('retrieved_at', 'không có trong dữ liệu nhập')))}. Kỳ giá: {escape(str(result.get('data_status', {}).get('price_period', 'không rõ')))}; kỳ EPS: {escape(str(result.get('data_status', {}).get('eps_period', 'không rõ')))}. Báo cáo phục vụ nghiên cứu học tập, không phải tư vấn đầu tư hay lời mời mua bán chứng khoán.", styles["BodyText"]))

    doc.build(story)
    return buffer.getvalue()


@router.post("/scenario/report.pdf", response_class=StreamingResponse)
def scenario_report(request: ScenarioReportRequest):
    """Create a purpose-specific PDF, with selected content and detail level."""
    result = analyze_scenarios(request.analysis)
    pdf = _build_pdf(result, request.report, request.supplemental_sections)
    filename = f"scenario_{result['ticker']}.pdf"
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/scenario/live/report.pdf", response_class=StreamingResponse)
def scenario_live_report(request: LiveScenarioReportRequest):
    """Fetch current available source data and create a customized scenario PDF."""
<<<<<<< HEAD
    try:
        res = bridge.run(request)
        pdf = bridge.pdf_bytes(res, request.report)
        filename = f"BaoCao_{res.ticker}_{res.created_at:%Y%m%d}.pdf"
        return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except bridge.EngineUnavailable:
        pass
    result = _analyze_live_vnstock(request)
=======
    result = _analyze_live(request)
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
    pdf = _build_pdf(result, request.report)
    filename = f"scenario_{result['ticker']}_live.pdf"
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
