"""Cầu nối giữa engine phân tích VNEquity (backend/vnequity) và API của giao diện Goi1_Gki.

Engine VNEquity: BCTC chuẩn hoá 716 mã HSX/HNX (2011-2025) + giá ngày (VNDirect -> TCBS -> vnstock -> cache),
mô hình 3 kịch bản (tăng trưởng EPS × P/E mục tiêu, cổ tức, xác suất), thẻ bằng chứng và báo cáo PDF.

Module này chuyển kết quả engine sang đúng schema mà frontend (Streamlit `frontend/app.py`
và React `frontend/src/lib/api.ts`) đang đọc:  LiveScenario{ticker, current_price, scenarios[bullish|base|bearish], ...}.
"""
from __future__ import annotations

import copy
import os
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from backend.vnequity import engine
from backend.vnequity.analysis import scenarios as scn
from backend.vnequity.analysis import valuation as va
from backend.vnequity.config import ALL_SECTIONS, PURPOSE_PRESETS, ReportOptions, UserProfile
from backend.vnequity.data import company, financials, prices
from backend.vnequity.report import fmt as F
from backend.vnequity.report.pdf_report import build_pdf

KEY_IN = {"bullish": "bull", "base": "base", "bearish": "bear"}       # khoá giao diện -> khoá engine
KEY_OUT = {v: k for k, v in KEY_IN.items()}
LABEL = {"bullish": "Tích cực", "base": "Cơ sở", "bearish": "Tiêu cực"}
OFFLINE = os.getenv("VNEQUITY_OFFLINE", "0") == "1"                   # 1 = chỉ dùng dữ liệu giá đã lưu
CACHE_TTL = int(os.getenv("VNEQUITY_CACHE_SECONDS", "900"))


class EngineUnavailable(Exception):
    """Mã không có trong bộ dữ liệu của engine -> API quay về luồng vnstock gốc."""


_cache: dict = {}
_lock = threading.Lock()
_pdf_lock = threading.Lock()


def _horizon_key(months: int | None) -> str:
    return "short" if (months or 12) <= 3 else "medium"


def _analysis(ticker: str, months: int | None, risk: str = "balanced"):
    """Phân tích đầy đủ (BCTC, giá, kỹ thuật, định giá, ngành, tin tức) - lưu đệm CACHE_TTL giây."""
    key = (ticker.upper(), _horizon_key(months), risk)
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return copy.copy(hit[1])
    try:
        res = engine.analyze(ticker, user=UserProfile(horizon=key[1], risk=risk), offline=OFFLINE, log=lambda *a, **k: None)
    except ValueError as exc:            # mã ngoài bộ dữ liệu BCTC chuẩn hoá
        raise EngineUnavailable(str(exc)) from exc
    except RuntimeError as exc:          # không lấy được giá từ mọi nguồn
        raise EngineUnavailable(str(exc)) from exc
    with _lock:
        _cache[key] = (now, res)
    return copy.copy(res)


# ----------------------------------------------------------------------------------------------
# Ánh xạ giả định người dùng -> overrides của engine
# ----------------------------------------------------------------------------------------------
def _overrides(req, res) -> dict:
    ov: dict = {k: {} for k in ("bull", "base", "bear")}
    for key, o in (req.overrides or {}).items():
        k = KEY_IN[key]
        if o.earnings_growth_pct is not None:
            ov[k]["eps_growth"] = o.earnings_growth_pct / 100
        if o.target_pe is not None:
            ov[k]["exit_pe"] = o.target_pe
    if req.earnings_growth_pct is not None and "eps_growth" not in ov["base"]:
        ov["base"]["eps_growth"] = req.earnings_growth_pct / 100
    if req.target_pe is not None and "exit_pe" not in ov["base"]:
        ov["base"]["exit_pe"] = req.target_pe
    if req.probabilities_pct:
        for key, p in req.probabilities_pct.items():
            ov[KEY_IN[key]]["probability"] = p / 100
    if req.dividend_yield_pct and req.dividend_yield_pct > 0:
        mm = res.val["multiples"]
        eps0 = float(mm["eps"])
        if eps0 > 0:   # cổ tức tiền mặt = lợi suất × giá  <=>  payout = lợi suất × giá / EPS
            payout = req.dividend_yield_pct / 100 * float(mm["price"]) / eps0
            for k in ov:
                ov[k]["payout"] = payout
    return {k: v for k, v in ov.items() if v}


def run(req, risk: str = "balanced"):
    """Chạy engine với giả định trong request; trả về AnalysisResult đã áp kịch bản (kỳ dự phóng 12 tháng)."""
    res = _analysis(req.ticker, req.horizon_months, risk)
    engine.apply_scenarios(res, _overrides(req, res), years=(req.horizon_months or 12) / 12)
    return res


# ----------------------------------------------------------------------------------------------
# Kết quả -> schema LiveScenario
# ----------------------------------------------------------------------------------------------
def _f(x, d=4):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), d)


def _scenario_cards(res, s, ss, frac, src_fin, src_px, px_date, user_set: set) -> list[dict]:
    d, gd = ss.defaults_info, res.val["growth_detail"]
    fy0, n = ss.fy0, ss.growth_years
    shares = res.profile.shares
    npat = res.fin["npat_parent"].fillna(res.fin["npat"]).iloc[-1]
    eps_end = s.eps_path[-1]
    retrieved = res.created_at.strftime("%d/%m/%Y %H:%M")
    if "eps_growth" in user_set:
        g_formula = "Giả định do người dùng nhập"
    elif s.key == "base":
        g_formula = (f"trung vị(CAGR LNST 3 năm {F.pct(gd['g_npat_3y'])}; CAGR doanh thu 3 năm {F.pct(gd['g_rev_3y'])}; "
                     f"ROE × (1 − tỷ lệ chi trả) {F.pct(gd['g_sustainable'])}), chặn trong [−5%; 25%]")
    elif s.key == "bull":
        g_formula = f"g cơ sở {F.pct(d['g_base'])} + {F.num(d['risk']['bull_sigma'], 2)} × σ {F.pct(d['sigma'])} (σ = độ lệch chuẩn tăng trưởng LNST năm, chặn 8-20%)"
    else:
        g_formula = f"g cơ sở {F.pct(d['g_base'])} − {F.num(d['risk']['bear_sigma'], 2)} × σ {F.pct(d['sigma'])} (bất đối xứng, thận trọng phía giảm)"
    if "exit_pe" in user_set:
        pe_formula = "Giả định do người dùng nhập"
    else:
        tg = d["pe_targets"][s.key]
        pe_formula = (f"P/E hiện tại {F.num(d['cur_pe'], 2)} + (1 − 0,5^({F.num(ss.years, 2)}/2)) × (P/E đích {F.num(tg, 2)} − "
                      f"{F.num(d['cur_pe'], 2)}) = {F.num(s.exit_pe, 2)}; P/E đích " +
                      {"base": f"= {d['ref_src']}", "bull": f"= {F.num(d['risk']['bull_pe'], 2)} × mức cao hơn giữa P/E hiện tại và tham chiếu",
                       "bear": f"= {F.num(d['risk']['bear_pe'], 2)} × mức thấp hơn giữa P/E hiện tại và tham chiếu"}[s.key])
    div_h = s.dividends
    ret = (s.target_price + div_h) / ss.price - 1
    eps_formula = d.get("eps_note") or f"LNST công ty mẹ FY{fy0} {F.bil(npat)} tỷ / {F.num(shares)} cổ phiếu lưu hành"
    return [
        {"claim": f"EPS năm gốc FY{fy0}", "value": _f(ss.eps0, 2), "unit": "đồng/cổ phiếu", "formula": eps_formula,
         "inputs": {"npat_parent": _f(npat, 0), "shares_outstanding": _f(shares, 0), "shares_source": res.profile.shares_source},
         "source": src_fin, "period": f"FY{fy0}", "retrieved_at": retrieved},
        {"claim": "Tăng trưởng EPS giả định", "value": _f(s.eps_growth * 100, 2), "unit": "%/năm", "formula": g_formula,
         "inputs": {"g_base_pct": _f(d["g_base"] * 100, 2), "sigma_pct": _f(d["sigma"] * 100, 2),
                    "npat_growth_history_pct": [_f(x * 100, 2) for x in d["yoy"]]},
         "source": src_fin, "period": f"FY{fy0 - 3}-FY{fy0}", "retrieved_at": retrieved},
        {"claim": f"EPS cuối kỳ ({ss.label})", "value": _f(eps_end, 2), "unit": "đồng/cổ phiếu",
         "formula": f"{F.num(ss.eps0)} × (1 + {F.pct(s.eps_growth)})^{F.num(n, 2)} = {F.num(eps_end)}" + (" (từ năm thứ 2 tăng trưởng giảm dần về mức dài hạn của kịch bản)" if n > 1 else ""),
         "inputs": {"eps0": _f(ss.eps0, 2), "growth_pct": _f(s.eps_growth * 100, 2), "growth_years": n},
         "source": "Mô hình kịch bản VNEquity", "period": f"{ss.label} kể từ hiện tại", "retrieved_at": retrieved},
        {"claim": "P/E mục tiêu", "value": _f(s.exit_pe, 2), "unit": "lần", "formula": pe_formula,
         "inputs": {"current_pe": _f(d["cur_pe"], 2), "reference_pe": _f(d["hist_avg"], 2), "reference": d["ref_src"]},
         "source": f"{src_px}; {src_fin}", "period": f"Giá đến {px_date}", "retrieved_at": retrieved},
        {"claim": "Giá ước tính theo kịch bản", "value": _f(s.target_price, 0), "unit": "đồng/cổ phiếu",
         "formula": f"EPS dự phóng {F.num(eps_end)} × P/E {F.num(s.exit_pe, 2)} = {F.num(s.target_price)}",
         "inputs": {"projected_eps": _f(eps_end, 2), "target_pe": _f(s.exit_pe, 2)},
         "source": "Mô hình kịch bản VNEquity", "period": f"Cuối kỳ {ss.label}", "retrieved_at": retrieved},
        {"claim": "Tỷ suất sinh lời theo kỳ hạn", "value": _f(ret * 100, 2), "unit": "%",
         "formula": (f"({F.num(s.target_price)} + cổ tức {F.num(div_h)}) / giá hiện tại {F.num(ss.price)} − 1 = {F.pct(ret, 2)}; "
                     f"cổ tức = tỷ lệ chi trả {F.pct(s.payout)} × EPS × thời gian nắm giữ {ss.label}"),
         "inputs": {"estimated_price": _f(s.target_price, 0), "current_price": _f(ss.price, 0), "dividends": _f(div_h, 0),
                    "payout": _f(s.payout, 4), "holding_years": _f(frac, 4)},
         "source": src_px, "period": f"Giá đóng cửa {px_date}", "retrieved_at": retrieved},
    ]


def _confidence(res) -> dict:
    n_fy = len(res.fin)
    n_px = len(res.prices)
    last_px = pd.Timestamp(res.prices["date"].iloc[-1])
    age = (pd.Timestamp(datetime.now().date()) - last_px.normalize()).days
    yoy = len(res.scen.defaults_info["yoy"])
    n_pe = len(res.val.get("hist_pe", [])) if res.val.get("hist_pe") is not None else 0
    parts = {
        "Số năm BCTC (tối đa 30)": min(n_fy, 10) * 3,
        "Số phiên giá (tối đa 20)": round(min(n_px, 200) / 10),
        "Độ mới của giá (tối đa 15)": 15 if age <= 5 else 10 if age <= 15 else 5 if age <= 45 else 0,
        "Quan sát tăng trưởng LNST (tối đa 15)": min(yoy, 3) * 5,
        "Chuỗi P/E lịch sử (tối đa 10)": 10 if n_pe >= 120 else 5 if n_pe >= 30 else 0,
        "Số cổ phiếu lưu hành đã đối chiếu (tối đa 10)": 10 if "ước tính" not in str(res.profile.shares_source).lower() else 4,
    }
    score = int(sum(parts.values()))
    label = "Cao" if score >= 75 else "Trung bình" if score >= 55 else "Thấp"
    return {"score": score, "label": label, "components": parts,
            "basis": "Điểm độ phủ dữ liệu: số năm BCTC, số phiên giá, độ mới của giá, số quan sát tăng trưởng, chuỗi P/E lịch sử "
                     "và nguồn số cổ phiếu lưu hành. Đây là thang kiểm tra độ đầy đủ của dữ liệu, không phải xác suất dự báo đúng."}


def to_live(res, req) -> dict:
    ss = res.scen
    months = req.horizon_months or 12
    frac = months / 12
    th = (req.horizon_thresholds_pct or {}).get(months, {}) if req.horizon_months else {}
    buy, sell = th.get("buy", req.buy_threshold_pct), th.get("sell", req.sell_threshold_pct)
    src_fin, src_px = res.data_sources["BCTC"], res.data_sources["Giá cổ phiếu"]
    px_date = f"{res.prices['date'].iloc[-1]:%d/%m/%Y}"
    ov = _overrides(req, res)
    rows = []
    for s in ss.ordered():
        k = KEY_OUT[s.key]
        user_set = set(ov.get(s.key, {}))
        ret = s.total_return * 100
        basis = []
        basis.append("tăng trưởng EPS do người dùng nhập" if "eps_growth" in user_set else
                     {"base": "tăng trưởng EPS = trung vị CAGR LNST 3 năm, CAGR doanh thu 3 năm và ROE × (1 − tỷ lệ chi trả)",
                      "bull": "tăng trưởng EPS = cơ sở + k × σ biến động lợi nhuận lịch sử (k theo khẩu vị)",
                      "bear": "tăng trưởng EPS = cơ sở − k × σ biến động lợi nhuận lịch sử (k theo khẩu vị)"}[s.key])
        basis.append("P/E do người dùng nhập" if "exit_pe" in user_set else
                     "P/E cuối kỳ hội tụ dần từ P/E hiện tại về P/E đích của kịch bản (chu kỳ bán rã 2 năm)")
        rows.append({
            "key": k, "label": LABEL[k],
            "earnings_growth_pct": _f(s.eps_growth * 100, 2),
            "target_pe": _f(s.exit_pe, 2),
            "projected_eps": _f(s.eps_path[-1], 2),
            "estimated_price": _f(s.target_price, 0),
            "expected_return_pct": _f(ret, 2),
            "probability_pct": _f(s.probability * 100, 1),
            "dividends_per_share": _f(s.dividends, 0),
            "dcf_reference_value": _f(s.dcf_value, 0),
            "assessment": "BUY" if ret >= buy else "SELL" if ret <= sell else "HOLD",
            "assumption_basis": "Mô hình VNEquity: " + "; ".join(basis) + f". Kỳ hạn {ss.label}: EPS FY{ss.fy0} tăng trưởng theo thời gian nắm giữ; P/E hội tụ dần về mức đích.",
            "evidence": _scenario_cards(res, s, ss, frac, src_fin, src_px, px_date, user_set),
        })

    by = {r["key"]: r for r in rows}
    probs = {KEY_OUT[s.key]: round(s.probability * 100, 2) for s in ss.ordered()}
    weighted = sum(s.probability * s.target_price for s in ss.ordered())
    exp_ret = sum(s.probability * by[KEY_OUT[s.key]]["expected_return_pct"] for s in ss.ordered())

    # Lưới độ nhạy: EPS năm gốc × (1+g)^n × P/E (giá ước tính, đồng)
    g_list = list(req.sensitivity_growth_pct) or [round((ss.scenarios["base"].eps_growth + i * 0.05) * 100, 1) for i in (-2, -1, 0, 1, 2)]
    pe_list = list(req.sensitivity_pe) or [round(ss.scenarios["base"].exit_pe * m, 1) for m in (0.8, 0.9, 1.0, 1.1, 1.2)]
    cells = [{"growth_pct": g, "prices": [{"target_pe": pe, "estimated_price": round(ss.eps0 * (1 + g / 100) ** ss.growth_years * pe, 0)}
                                          for pe in pe_list]} for g in g_list]

    warnings = []
    if not (by["bullish"]["estimated_price"] >= by["base"]["estimated_price"] >= by["bearish"]["estimated_price"]):
        warnings.append("Giá kịch bản chưa theo thứ tự Tích cực ≥ Cơ sở ≥ Tiêu cực; hãy kiểm tra giả định đã nhập.")
    if req.probabilities_pct is None:
        warnings.append("Chưa nhập xác suất: dùng mặc định 25% / 50% / 25% để tính giá trị có trọng số.")
    warnings.extend(res.warnings)

    mm, d = res.val["multiples"], ss.defaults_info
    last_px = pd.Timestamp(res.prices["date"].iloc[-1])
    age = (pd.Timestamp(datetime.now().date()) - last_px.normalize()).days
    yoy = d["yoy"]
    n_pe = len(res.val["hist_pe"]) if res.val.get("hist_pe") is not None else 0
    return {
        "ticker": res.ticker,
        "company_name": res.profile.name,
        "exchange": res.profile.exchange,
        "industry": res.profile.icb3 or res.profile.icb2 or res.profile.icb1,
        "currency": "VND",
        "horizon_years": ss.years,
        "horizon_months": months,
        "current_price": _f(ss.price, 0),
        "engine": "VNEquity",
        "method": "EPS năm gốc × (1 + g)^n × P/E mục tiêu; g và P/E mặc định suy ra từ BCTC và lịch sử giá, người dùng chỉnh được",
        "earnings_growth_basis": req.earnings_growth_basis,
        "pe_basis": f"P/E trên EPS FY{ss.fy0}",
        "scenarios": rows,
        "probabilities_pct": probs,
        "probability_weighted_value": _f(weighted, 0),
        "probability_weighted_return_pct": _f(exp_ret, 2),
        "risk_reward": _f(ss.risk_reward, 2),
        "probability_of_loss_pct": _f(ss.prob_loss * 100, 1),
        "rating": res.rating,
        "rating_reason": res.rating_reason,
        "recommendation_thresholds_pct": {"buy": buy, "sell": sell, "horizon_months": months,
                                          "configured_by_horizon": bool(req.horizon_thresholds_pct)},
        "growth_formula": f"EPS × (1 + g)^{ss.growth_years:g}",
        "sensitivity_grid": {"growth_pct": g_list, "target_pe": pe_list, "cells": cells},
        "configuration_warnings": warnings,
        "data_types": {"market_inputs": "dữ liệu thực tế", "scenario_parameters": "giả định hệ thống/người dùng",
                       "prices_and_returns": "chỉ số tính toán"},
        "interpretation": "Ba kịch bản là phân tích độ nhạy theo giả định; xác suất là trọng số do người dùng chọn, không phải dự báo thống kê.",
        "scenario_method": {
            "status": "vnequity_model", "growth_observations": int(len(yoy)), "pe_observations": int(n_pe),
            "g_base_pct": _f(d["g_base"] * 100, 2), "sigma_pct": _f(d["sigma"] * 100, 2),
            "current_pe": _f(d["cur_pe"], 2), "reference_pe": _f(d["hist_avg"], 2), "reference_pe_source": d["ref_src"],
            "payout": _f(d["payout"], 4), "growth_years": ss.growth_years, "eps_fy0": ss.fy0,
            "horizon_note": "Giá mục tiêu dùng EPS dự phóng 12 tháng cho mọi kỳ; 3/6/12 tháng là kỳ theo dõi lợi suất và ngưỡng đánh giá.",
        },
        "data_confidence": _confidence(res),
        "data_status": {
            "provider": "VNEquity (BCTC chuẩn hoá + giá ngày)",
            "retrieved_at": res.created_at.strftime("%d/%m/%Y %H:%M"),
            "freshness": f"Giá đóng cửa {last_px:%d/%m/%Y} ({age} ngày trước)",
            "price_period": f"Phiên {last_px:%d/%m/%Y}",
            "price_source": res.data_sources["Giá cổ phiếu"],
            "eps_period": f"FY{ss.fy0}",
            "eps_basis": f"LNST công ty mẹ / {F.num(res.profile.shares)} cổ phiếu ({res.profile.shares_source})",
            "growth_basis": f"Tăng trưởng LNST các năm FY{ss.fy0 - len(yoy)}-FY{ss.fy0}",
            "pe_basis": f"P/E hiện tại {F.num(d['cur_pe'], 2)} lần; {d['ref_src']} {F.num(d['hist_avg'], 2)} lần",
            "financial_source": res.data_sources["BCTC"],
            "growth_observations": int(len(yoy)),
            "pe_observations_same_eps_periods": int(n_pe),
        },
        "thesis": [e.as_dict() for e in res.evidence.by_kind("thesis")],
        "risks": [e.as_dict() for e in res.evidence.by_kind("risk")],
        "evidence_book": [e.as_dict() for e in res.evidence.items],
        "limitations": [
            "Phương pháp P/E phù hợp khi EPS dương; doanh nghiệp thua lỗ năm gần nhất dùng EPS chuẩn hoá và được ghi rõ trong thẻ bằng chứng.",
            "Ngân hàng dùng bộ chỉ số chuyên ngành; công ty chứng khoán/bảo hiểm chưa có trong bộ BCTC chuẩn hoá và được chuyển sang luồng dữ liệu vnstock.",
            "Giá trị có trọng số phụ thuộc xác suất người dùng chọn; không phải giá mục tiêu duy nhất hay cam kết sinh lời.",
            "BCTC là số liệu năm đã kiểm toán; các sự kiện sau kỳ báo cáo chưa phản ánh trong EPS năm gốc.",
        ],
    }


# ----------------------------------------------------------------------------------------------
# Ảnh chụp nhanh cho so sánh peer (không chạy toàn bộ phân tích)
# ----------------------------------------------------------------------------------------------
def snapshot(ticker: str) -> dict:
    t = ticker.strip().upper()
    fin = financials.get_financials(t)
    if fin.empty:
        raise EngineUnavailable(f"{t} chưa có trong bộ BCTC chuẩn hoá")
    prof = company.get_profile(t)
    try:
        px = prices.get_prices(t, days=60, offline=OFFLINE)
    except RuntimeError as exc:
        raise EngineUnavailable(str(exc)) from exc
    mm = va.market_multiples(fin, float(px["close"].iloc[-1]), prof.shares)
    last = pd.Timestamp(px["date"].iloc[-1])
    pe = mm["pe"] if pd.notna(mm["pe"]) and mm["pe"] > 0 else None
    return {"ticker": t, "current_price": float(mm["price"]), "eps": float(mm["eps"]), "target_pe": pe,
            "price_period": f"Phiên {last:%d/%m/%Y}", "eps_period": f"FY{int(mm['fiscal_year'])}",
            "retrieved_at": datetime.now().strftime("%d/%m/%Y %H:%M"), "source": px.attrs.get("source", "")}


# ----------------------------------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------------------------------
# Nhóm nội dung của giao diện -> mục báo cáo của engine
SECTION_MAP = {
    "executive_summary": ("summary",),
    "final_assessment": ("summary",),
    "scenario": ("scenario",),
    "sensitivity": ("scenario",),
    "assumptions": ("scenario",),
    "valuation": ("valuation",),
    "financial_analysis": ("company", "financial", "appendix"),
    "risk": ("risk",),
    "market_risk": ("technical", "news"),
    "evidence": ("evidence",),
    "charts": (),
}
CONTROLLED = {s for v in SECTION_MAP.values() for s in v}
SCENARIO_CHARTS = ("scenario_fan", "scenario_bars", "sensitivity")


def report_options(report) -> ReportOptions:
    purpose = report.purpose if report.purpose in PURPOSE_PRESETS else "full"
    preset = dict(PURPOSE_PRESETS[purpose]["opts"])
    sections = list(preset.get("sections", ALL_SECTIONS))
    charts = list(preset.get("charts", ReportOptions().charts))
    groups = list(report.metric_groups or [])
    if groups:
        wanted = {s for g in groups for s in SECTION_MAP.get(g, ())}
        wanted.add("summary")
        keep = [s for s in ALL_SECTIONS if (s in wanted) or (s in sections and s not in CONTROLLED)]
        sections = keep
        if "charts" not in groups:
            charts = [c for c in charts if c in SCENARIO_CHARTS]
        if "sensitivity" not in groups:
            charts = [c for c in charts if c != "sensitivity"]
    if not report.include_chart:
        charts = []
    detail = {"summary": "brief", "standard": "standard", "detailed": "detailed"}.get(report.detail_level, "standard")
    return ReportOptions(purpose=purpose, sections=tuple(sections), metric_groups=tuple(preset.get("metric_groups", ReportOptions().metric_groups)),
                         charts=tuple(charts), detail=detail, years=int(report.years_shown or preset.get("years", 5)))


def pdf_bytes(res, report) -> bytes:
    opts = report_options(report)
    with _pdf_lock, tempfile.TemporaryDirectory() as tmp:   # matplotlib không an toàn đa luồng
        out = Path(tmp) / f"{res.ticker}.pdf"
        build_pdf(res, out, options=opts)
        return out.read_bytes()