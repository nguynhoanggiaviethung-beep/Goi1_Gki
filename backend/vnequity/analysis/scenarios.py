"""PHÂN TÍCH KỊCH BẢN ĐẦU TƯ - chức năng trung tâm của hệ thống.

Thay vì một giá mục tiêu duy nhất, xây dựng 3 kịch bản Tích cực / Cơ sở / Tiêu cực với các giả định
minh bạch, người dùng chỉnh được:
    - Tăng trưởng EPS mỗi năm (g)
    - P/E mục tiêu tại thời điểm cuối kỳ đầu tư
    - Tỷ lệ chi trả cổ tức
    - Xác suất xảy ra kịch bản
    - Kỳ hạn đầu tư (năm) - dùng chung

Mô hình (giá trị theo đồng/cổ phiếu):
    EPS_cuối kỳ  = EPS_FY0 × Π(1 + g)               (số năm tăng trưởng = số BCTC năm sẽ công bố thêm đến cuối kỳ)
    Giá mục tiêu = P/E mục tiêu × EPS_cuối kỳ
    Cổ tức nhận  = Σ (payout × EPS_t)  trong kỳ hạn
    TSSL tổng    = (Giá mục tiêu + Cổ tức) / Giá hiện tại − 1
    TSSL/năm     = (1 + TSSL tổng)^(1/N) − 1
    Kỳ vọng      = Σ xác suất × kết quả từng kịch bản
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

import numpy as np
import pandas as pd

SCEN_META = {
    "bull": {"name": "Tích cực", "color": "#15803D", "tint": "#F0FDF4"},
    "base": {"name": "Cơ sở", "color": "#1E3A8A", "tint": "#EFF6FF"},
    "bear": {"name": "Tiêu cực", "color": "#B91C1C", "tint": "#FEF2F2"},
}


@dataclass
class Scenario:
    key: str
    eps_growth: float
    exit_pe: float
    payout: float
    probability: float
    # --- kết quả ---
    eps_path: list = field(default_factory=list)
    target_price: float = np.nan
    dividends: float = np.nan
    total_return: float = np.nan
    annual_return: float = np.nan
    dcf_value: float = np.nan
    rationale: dict = field(default_factory=dict)   # giải thích nguồn gốc giả định mặc định

    @property
    def name(self) -> str:
        return SCEN_META[self.key]["name"]

    @property
    def color(self) -> str:
        return SCEN_META[self.key]["color"]


@dataclass
class ScenarioSet:
    price: float              # giá hiện tại (đồng)
    eps0: float               # EPS năm tài chính gần nhất (đồng, theo SLCP hiện tại)
    fy0: int
    years: int                # kỳ hạn đầu tư (năm)
    growth_years: int         # số năm EPS tăng trưởng đến cuối kỳ
    current_pe: float
    scenarios: dict           # key -> Scenario
    expected_price: float = np.nan
    expected_return: float = np.nan
    expected_annual: float = np.nan
    risk_reward: float = np.nan
    prob_loss: float = np.nan
    sensitivity: pd.DataFrame | None = None
    defaults_info: dict = field(default_factory=dict)

    def ordered(self):
        return [self.scenarios[k] for k in ("bull", "base", "bear")]


def growth_years_for(fy0: int, years: int, today: datetime | None = None) -> int:
    """Số BCTC năm mới sẽ được công bố đến cuối kỳ (BCTC năm Y coi như công bố từ 01/04 năm Y+1)."""
    today = today or datetime.now()
    end_year, end_month = today.year + years, today.month
    last_fy_at_end = end_year - 1 if end_month >= 4 else end_year - 2
    return max(1, last_fy_at_end - fy0)


def default_assumptions(res) -> dict:
    """Giả định mặc định suy ra từ dữ liệu - mọi con số đều có giải thích (rationale)."""
    v = res.val
    mm = v["multiples"]
    gd = v["growth_detail"]
    npat = res.fin["npat_parent"].fillna(res.fin["npat"])
    yoy = npat.pct_change(fill_method=None)
    yoy[npat.shift(1) <= 0] = np.nan
    yoy = yoy.tail(5).dropna()
    sigma_raw = float(yoy.std()) if len(yoy) >= 3 else 0.10
    sigma = float(np.clip(sigma_raw, 0.08, 0.20))
    g_base = float(v["g"])

    cur_pe = mm["pe"] if pd.notna(mm["pe"]) else np.nan
    hs = v["hist_pe_stats"]
    hist_avg = hs["avg"] if pd.notna(hs.get("avg")) else v["methods"].get("pe", {}).get("growth_adj_pe", 13.0)
    if pd.isna(hist_avg):
        hist_avg = 13.0
    ref_src = "P/E bình quân 12 tháng" if pd.notna(hs.get("avg")) else "P/E thị trường điều chỉnh theo tăng trưởng"
    if pd.isna(cur_pe):
        cur_pe = hist_avg
    pe_base = (cur_pe + hist_avg) / 2
    pe_bull = 1.1 * max(cur_pe, hist_avg)
    pe_bear = 0.9 * min(cur_pe, hist_avg)
    payout = gd.get("payout_3y")
    payout = float(np.clip(payout, 0, 1)) if pd.notna(payout) else 0.3

    return {
        "sigma": sigma, "sigma_raw": sigma_raw, "yoy": yoy, "g_base": g_base, "cur_pe": cur_pe, "hist_avg": hist_avg,
        "ref_src": ref_src, "payout": payout,
        "bull": {"eps_growth": g_base + sigma, "exit_pe": pe_bull, "payout": payout, "probability": 0.25},
        "base": {"eps_growth": g_base, "exit_pe": pe_base, "payout": payout, "probability": 0.50},
        "bear": {"eps_growth": g_base - 1.5 * sigma, "exit_pe": pe_bear, "payout": payout, "probability": 0.25},
    }


def default_years(horizon: str) -> int:
    return {"short": 1, "medium": 1, "long": 3}.get(horizon, 1)


def _run_one(s: Scenario, eps0: float, price: float, years: int, gyears: int, roe: float, ke: float, vparams) -> Scenario:
    from .valuation import fcfe_dcf

    eps = eps0
    path = []
    for _ in range(gyears):
        eps *= 1 + s.eps_growth
        path.append(eps)
    s.eps_path = path
    s.target_price = s.exit_pe * path[-1]
    # Cổ tức: mỗi năm trong kỳ hạn nhận payout × EPS năm gần nhất đã công bố (xấp xỉ)
    pay_eps = [eps0] + path
    s.dividends = float(sum(s.payout * pay_eps[min(i, len(pay_eps) - 1)] for i in range(years)))
    s.total_return = (s.target_price + s.dividends) / price - 1
    s.annual_return = (1 + s.total_return) ** (1 / years) - 1 if s.total_return > -1 else -1.0
    try:
        s.dcf_value = float(fcfe_dcf(eps0, s.eps_growth, roe, ke, vparams)[0])
    except Exception:  # noqa: BLE001
        s.dcf_value = np.nan
    return s


def build(res, overrides: dict | None = None, years: int | None = None) -> ScenarioSet:
    """Dựng bộ 3 kịch bản. overrides = {"bull": {"eps_growth": .., "exit_pe": .., "payout": .., "probability": ..}, ...}"""
    d = default_assumptions(res)
    v = res.val
    mm = v["multiples"]
    price, eps0 = float(mm["price"]), float(mm["eps"])
    fy0 = int(mm["fiscal_year"])
    years = int(years or default_years(res.user.horizon))
    gyears = growth_years_for(fy0, years, res.created_at)
    roe = v["growth_detail"]["roe_3y"]
    vparams = getattr(res, "vparams", None)
    if vparams is None:
        from ..config import ValuationParams
        vparams = ValuationParams()

    scen = {}
    for k in ("bull", "base", "bear"):
        a = dict(d[k])
        if overrides and k in overrides:
            a.update({kk: float(vv) for kk, vv in overrides[k].items() if vv is not None})
        scen[k] = Scenario(key=k, **a)
    # chuẩn hoá xác suất
    tot = sum(s.probability for s in scen.values()) or 1.0
    for s in scen.values():
        s.probability = s.probability / tot

    eps_note = ""
    if eps0 <= 0:   # DN thua lỗ năm gần nhất -> dùng EPS chuẩn hoá (minh bạch trong thẻ bằng chứng)
        npat = res.fin["npat_parent"].fillna(res.fin["npat"]).tail(5)
        norm = npat[npat > 0].mean() / mm["shares"] if (npat > 0).any() else np.nan
        if pd.isna(norm):
            norm = 0.10 * mm["bvps"]
            eps_note = "EPS FY gần nhất ≤ 0 và không có năm lãi trong 5 năm: dùng EPS chuẩn hoá = 10% × BVPS"
        else:
            eps_note = "EPS FY gần nhất ≤ 0: dùng EPS chuẩn hoá = bình quân LNST các năm có lãi trong 5 năm / SLCP"
        eps0 = float(norm)
        if eps0 <= 0:
            raise ValueError("Không xác định được EPS chuẩn hoá dương cho mô hình kịch bản.")
    for s in scen.values():
        _run_one(s, eps0, price, years, gyears, roe, v["ke"], vparams)

    d["eps_note"] = eps_note
    ss = ScenarioSet(price=price, eps0=eps0, fy0=fy0, years=years, growth_years=gyears, current_pe=d["cur_pe"],
                     scenarios=scen, defaults_info=d)
    ss.expected_price = sum(s.probability * s.target_price for s in scen.values())
    ss.expected_return = sum(s.probability * s.total_return for s in scen.values())
    ss.expected_annual = (1 + ss.expected_return) ** (1 / years) - 1 if ss.expected_return > -1 else -1.0
    up, down = scen["bull"].total_return, scen["bear"].total_return
    ss.risk_reward = up / abs(down) if down < 0 else np.inf
    ss.prob_loss = sum(s.probability for s in scen.values() if s.total_return < 0)

    # Ma trận độ nhạy: tăng trưởng EPS × P/E mục tiêu -> TSSL tổng
    base = scen["base"]
    step = max(0.02, round((scen["bull"].eps_growth - scen["bear"].eps_growth) / 6, 3))
    gs = base.eps_growth + np.arange(-3, 4) * step                    # lưới đối xứng quanh kịch bản cơ sở
    pes = base.exit_pe * np.array([0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3])
    mat = {}
    for pe in pes:
        col = {}
        for g in gs:
            s = _run_one(replace(base, eps_growth=g, exit_pe=pe), eps0, price, years, gyears, roe, v["ke"], vparams)
            col[round(g, 4)] = s.total_return
        mat[round(pe, 2)] = col
    ss.sensitivity = pd.DataFrame(mat)  # index = g, columns = P/E
    return ss


def rating_from_scenarios(ss: ScenarioSet) -> tuple[str, str]:
    """Khuyến nghị dựa trên TSSL kỳ vọng/năm (gia quyền xác suất) & tỷ lệ lợi nhuận/rủi ro."""
    from .scoring import RATINGS, rating_from_upside

    base = rating_from_upside(ss.expected_annual)
    idx = RATINGS.index(base)
    reason = (f"TSSL kỳ vọng {ss.expected_annual * 100:+.1f}%/năm (gia quyền xác suất 3 kịch bản), tương ứng mức {base}").replace(".", ",")
    if np.isfinite(ss.risk_reward) and ss.risk_reward < 1.0 and idx > 0:
        idx -= 1
        reason += f"; tỷ lệ lợi nhuận/rủi ro {ss.risk_reward:.2f} < 1 nên hạ 1 bậc".replace(".", ",")
    elif ss.scenarios["bear"].total_return > 0 and idx < 4:
        idx += 1
        reason += "; ngay cả kịch bản tiêu cực vẫn có lãi nên nâng 1 bậc"
    return RATINGS[idx], reason
