"""API cho giao diện VNEquity Research (frontend/app.py).

Mọi số liệu giao diện hiển thị đều lấy qua các endpoint dưới đây; frontend không import trực tiếp engine.

    GET  /api/engine/options                 nhãn, mục đích báo cáo, danh sách mã
    POST /api/engine/analyze                 phân tích + 3 kịch bản theo giả định người dùng
    POST /api/engine/report.pdf              báo cáo PDF tuỳ chỉnh theo mục đích
    GET  /api/engine/financials/{ticker}     BCTC + chỉ số theo năm (biểu đồ so sánh)
    POST /api/engine/screen                  sàng lọc toàn bộ doanh nghiệp
    POST /api/engine/screen.pdf              PDF danh sách sàng lọc
"""
from __future__ import annotations

import copy
import math
import os
import tempfile
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.vnequity import engine
from backend.vnequity.analysis import scenarios as scn
from backend.vnequity.analysis.fundamental import compute_ratios
from backend.vnequity.analysis.scoring import RATING_COLOR
from backend.vnequity.config import (CHART_LABEL, DETAIL_LABEL, HORIZON_LABEL, METRIC_GROUPS, PURPOSE_PRESETS,
                                     RISK_LABEL, SECTION_LABEL, UserProfile, preset_options)
from backend.vnequity.data.company import get_profile
from backend.vnequity.data.financials import available_tickers, get_financials
from backend.vnequity.report.pdf_report import build_pdf

router = APIRouter(prefix="/engine", tags=["VNEquity engine"])

OFFLINE_ENV = os.getenv("VNEQUITY_OFFLINE", "0") == "1"
CACHE_TTL = int(os.getenv("VNEQUITY_CACHE_SECONDS", "900"))
_cache: dict = {}
_lock = threading.Lock()
_pdf_lock = threading.Lock()   # matplotlib/reportlab không an toàn đa luồng


# ---------------------------------------------------------------------------------------------- tiện ích
def clean(x):
    """Đổi kiểu numpy/pandas sang JSON; NaN/inf -> None."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (pd.Timestamp,)):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def _analysis(ticker: str, horizon: str, risk: str, offline: bool):
    key = (ticker.upper(), horizon, risk, offline)
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return copy.copy(hit[1])
    try:
        res = engine.analyze(ticker, user=UserProfile(horizon=horizon, risk=risk), offline=offline,
                             log=lambda *a, **k: None)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    with _lock:
        _cache[key] = (now, res)
    return copy.copy(res)


class Assumption(BaseModel):
    eps_growth: float | None = Field(default=None, description="Tăng trưởng EPS/năm, dạng thập phân (0.15 = 15%)")
    exit_pe: float | None = Field(default=None, gt=0)
    probability: float | None = Field(default=None, ge=0, le=1)
    payout: float | None = Field(default=None, ge=0, le=1.5)


class AnalyzeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    horizon: Literal["short", "medium", "long"] = "medium"
    risk: Literal["conservative", "balanced", "aggressive"] = "balanced"
    years: float | None = Field(default=None, ge=0.25, le=10, description="Kỳ hạn (năm): 0.25 = 3 tháng")
    overrides: dict[Literal["bull", "base", "bear"], Assumption] = Field(default_factory=dict)
    offline: bool = False


def _run(req: AnalyzeRequest):
    res = _analysis(req.ticker, req.horizon, req.risk, req.offline or OFFLINE_ENV)
    ov = {k: {f: v for f, v in a.model_dump().items() if v is not None} for k, a in req.overrides.items()}
    ov = {k: v for k, v in ov.items() if v} or None
    try:
        engine.apply_scenarios(res, ov, req.years or scn.default_years(req.horizon))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return res


def _ev(e) -> dict:
    return {"id": e.id, "claim": e.claim, "kind": e.kind, "metrics": [list(m) for m in e.metrics], "period": e.period,
            "source": e.source, "formula": e.formula, "calc": e.calc, "tone": e.tone}


def _payload(res) -> dict:
    ss, mm, d = res.scen, res.val["multiples"], res.scen.defaults_info
    px = res.prices.tail(260)
    cols = [c for c in ("date", "open", "high", "low", "close", "volume", "ma20", "ma50", "ma200") if c in px]
    sens = ss.sensitivity
    return clean({
        "ticker": res.ticker,
        "profile": {"name": res.profile.name, "exchange": res.profile.exchange, "icb1": res.profile.icb1,
                    "icb3": res.profile.icb3, "shares": res.profile.shares, "shares_source": res.profile.shares_source},
        "price_date": res.tech["date"],
        "price_change": res.prices["close"].pct_change().iloc[-1],
        "multiples": {k: mm.get(k) for k in ("price", "eps", "pe", "pb", "market_cap", "bvps", "fiscal_year")},
        "rating": res.rating, "rating_reason": res.rating_reason, "rating_color": RATING_COLOR.get(res.rating, "#1E3A8A"),
        "warnings": res.warnings,
        "scen": {
            "price": ss.price, "eps0": ss.eps0, "fy0": ss.fy0, "years": ss.years, "label": ss.label, "growth_years": ss.growth_years,
            "current_pe": ss.current_pe, "expected_price": ss.expected_price, "expected_return": ss.expected_return,
            "expected_annual": ss.expected_annual, "risk_reward": ss.risk_reward, "prob_loss": ss.prob_loss,
            "items": [{"key": s.key, "name": s.name, "color": scn.SCEN_META[s.key]["color"], "tint": scn.SCEN_META[s.key]["tint"],
                       "eps_growth": s.eps_growth, "exit_pe": s.exit_pe, "payout": s.payout, "probability": s.probability,
                       "eps_end": s.eps_path[-1], "target_price": s.target_price, "dividends": s.dividends,
                       "total_return": s.total_return, "annual_return": s.annual_return, "dcf_value": s.dcf_value}
                      for s in ss.ordered()],
            "sensitivity": {"growth": list(sens.index), "pe": list(sens.columns), "values": sens.values.tolist()},
        },
        "defaults": {k: {f: d[k][f] for f in ("eps_growth", "exit_pe", "probability", "payout")} for k in ("bull", "base", "bear")},
        "model": {"pe_targets": d["pe_targets"], "converge": d["converge"], "current_pe": d["cur_pe"], "reference_pe": d["hist_avg"],
                  "sigma": d["sigma"], "g_base": d["g_base"], "risk": d["risk"], "g_long_term": scn.LONG_TERM_ANCHOR,
                  "pe_half_life": scn.PE_HALF_LIFE,
                  "market": {k: d["market"][k] for k in ("trend_ok", "rs_ok", "factor", "rs_excess", "anti")}},
        "default_years": scn.default_years(res.user.horizon),
        "prices": {c: (px[c].dt.strftime("%Y-%m-%d").tolist() if c == "date" else px[c].tolist()) for c in cols},
        "composite": res.composite,
        "evidence": [_ev(e) for e in res.evidence.items],
        "data_sources": res.data_sources,
    })


# ---------------------------------------------------------------------------------------------- endpoint
@router.get("/options")
def options():
    return {"tickers": available_tickers(), "horizon": HORIZON_LABEL, "risk": RISK_LABEL, "sections": SECTION_LABEL,
            "charts": CHART_LABEL, "metric_groups": METRIC_GROUPS, "detail": DETAIL_LABEL,
            "purposes": {k: {"label": v["label"], "desc": v["desc"],
                             "options": clean(preset_options(k).__dict__)} for k, v in PURPOSE_PRESETS.items()}}


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    return _payload(_run(req))


class PdfOptions(BaseModel):
    purpose: str = "full"
    sections: list[str] | None = None
    charts: list[str] | None = None
    metric_groups: list[str] | None = None
    detail: Literal["brief", "standard", "detailed"] | None = None
    years: int | None = Field(default=None, ge=3, le=10)


class ReportRequest(AnalyzeRequest):
    options: PdfOptions = Field(default_factory=PdfOptions)


@router.post("/report.pdf", response_class=StreamingResponse)
def report(req: ReportRequest):
    res = _run(req)
    o = req.options
    order = [s for s in SECTION_LABEL if o.sections is None or s in o.sections]
    opts = preset_options(o.purpose, sections=tuple(order) if o.sections is not None else None,
                          charts=tuple(o.charts) if o.charts is not None else None,
                          metric_groups=tuple(o.metric_groups) if o.metric_groups is not None else None,
                          detail=o.detail, years=o.years)
    if o.charts is not None and not o.charts:
        opts.charts = ()
    if o.metric_groups is not None and not o.metric_groups:
        opts.metric_groups = ()
    with _pdf_lock, tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"{res.ticker}.pdf"
        build_pdf(res, out, options=opts)
        data = out.read_bytes()
    name = f"{res.ticker}_BaoCaoPhanTich_{res.created_at:%Y%m%d_%H%M}.pdf"
    return StreamingResponse(BytesIO(data), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/financials/{ticker}")
def financials(ticker: str, years: int = Query(default=10, ge=1, le=20)):
    f = get_financials(ticker.upper())
    if f.empty:
        raise HTTPException(status_code=404, detail=f"Không có BCTC chuẩn hoá cho {ticker.upper()}")
    df = pd.concat([f, compute_ratios(f)], axis=1).tail(years)
    df = df.loc[:, ~df.columns.duplicated()]
    return clean({"ticker": ticker.upper(), "name": get_profile(ticker.upper()).name, "years": [int(y) for y in df.index],
                  "data": {c: df[c].tolist() for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}})


STATEMENT_LAYOUT = {
    "Kết quả kinh doanh": ["revenue", "cogs", "gross_profit", "fin_income", "fin_exp", "interest_exp", "selling_exp", "admin_exp",
                           "nii", "fee_income", "opex", "ppop", "provision", "ebit", "ebitda", "pbt", "npat", "npat_parent",
                           "eps_reported"],
    "Cân đối kế toán": ["total_assets", "current_assets", "cash", "st_investments", "receivables", "inventory", "loans",
                        "loan_reserve", "fixed_assets", "liabilities", "current_liab", "st_debt", "lt_liab", "lt_debt", "deposits",
                        "equity", "share_capital", "retained_earnings", "minority_equity"],
    "Lưu chuyển tiền tệ": ["cfo", "depreciation", "capex", "cfi", "debt_raised", "debt_repaid", "dividends_paid", "cff"],
}
RAW_NAME = {"balance_sheet": "Cân đối kế toán", "income_statement": "Kết quả kinh doanh", "cash_flow": "Lưu chuyển tiền tệ"}


@router.get("/statements/{ticker}")
def statements(ticker: str, years: int = Query(default=5, ge=1, le=15)):
    """BCTC năm hợp nhất đã chuẩn hoá: các chỉ tiêu chính theo đúng thứ tự báo cáo + toàn bộ chỉ tiêu gốc (khác 0)."""
    from backend.vnequity.data.financials import FIELD_LABEL_VI, raw_items

    t = ticker.upper()
    f = get_financials(t)
    if f.empty:
        raise HTTPException(status_code=404, detail=f"Chưa có BCTC chuẩn hoá cho {t} (ngoài 716 mã HSX/HNX của bộ dữ liệu).")
    f = f.tail(years)
    yrs = [int(y) for y in f.index]
    main = {}
    for name, fields in STATEMENT_LAYOUT.items():
        rows = []
        for k in fields:
            if k in f and f[k].notna().any() and (f[k].fillna(0) != 0).any():
                rows.append({"item": FIELD_LABEL_VI.get(k, k), "unit": "đồng" if k == "eps_reported" else "tỷ đồng",
                             "values": {str(y): (f.at[y, k] if k == "eps_reported" else f.at[y, k] / 1e9) for y in f.index}})
        main[name] = rows
    raw = {}
    r = raw_items(t)
    if not r.empty:
        r = r[[c for c in r.columns if int(c) in yrs]]
        for (st_, code, item), vals in r.iterrows():
            if vals.fillna(0).abs().sum() == 0:
                continue
            raw.setdefault(RAW_NAME.get(st_, st_), []).append(
                {"item": item, "code": code, "values": {str(int(y)): vals[y] / 1e9 for y in r.columns}})
    return clean({"ticker": t, "name": get_profile(t).name, "years": yrs, "main": main, "raw": raw,
                  "source": "BCTC hợp nhất năm đã kiểm toán, bộ dữ liệu vn-annual-report-miner (HSX, HNX), chuẩn hoá bởi VNEquity"})


class ScreenRequest(BaseModel):
    min_revenue_bil: float = Field(default=1000, ge=0)
    exchange: Literal["HSX", "HNX"] | None = None
    top: int = Field(default=30, ge=5, le=200)
    with_prices: bool = False
    offline: bool = False


_screen_cache: dict = {}


def _screen(req: ScreenRequest) -> pd.DataFrame:
    from backend.vnequity.analysis.screener import enrich_with_prices, screen
    key = (req.min_revenue_bil, req.exchange)
    if key not in _screen_cache:
        _screen_cache[key] = screen(min_revenue_bil=req.min_revenue_bil, exchange=req.exchange, log=None)
    df = _screen_cache[key]
    if req.with_prices:
        df = enrich_with_prices(df, top=req.top, offline=req.offline or OFFLINE_ENV, log=lambda *a: None)
    return df


@router.post("/screen")
def run_screen(req: ScreenRequest):
    df = _screen(req)
    return clean({"total": len(df), "columns": list(df.columns), "rows": df.head(req.top).to_dict(orient="records")})


@router.post("/screen.pdf", response_class=StreamingResponse)
def screen_pdf(req: ScreenRequest):
    from backend.vnequity.report.screener_pdf import build_screener_pdf
    df = _screen(req)
    with _pdf_lock, tempfile.TemporaryDirectory() as tmp:
        out = build_screener_pdf(df, {"Doanh thu tối thiểu": f"{req.min_revenue_bil:,.0f} tỷ".replace(",", "."),
                                      "Sàn": req.exchange or "Tất cả"}, out=Path(tmp) / "screen.pdf", top=req.top)
        data = Path(out).read_bytes()
    return StreamingResponse(BytesIO(data), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="SangLocCoHoi.pdf"'})