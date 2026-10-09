"""Cấu hình chung: đường dẫn, tham số thị trường, tham số định giá."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
BCTC_DIR = DATA_DIR / "bctc"
REF_DIR = DATA_DIR / "reference"
CACHE_DIR = DATA_DIR / "cache"
RAW_PRICE_DIR = DATA_DIR / "raw_prices"
REPORT_DIR = ROOT / "reports"
FONT_DIR = ROOT / "assets" / "fonts"

for _d in (CACHE_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}
HTTP_TIMEOUT = 15

PAR_VALUE = 10_000  # Mệnh giá cổ phiếu VN (đồng)


@dataclass
class ValuationParams:
    """Tham số định giá — có thể chỉnh từ CLI / giao diện web."""

    risk_free: float = 0.040        # Lợi suất TPCP 10 năm (xấp xỉ)
    equity_risk_premium: float = 0.090  # Phần bù rủi ro thị trường VN (thị trường cận biên/mới nổi)
    beta_floor: float = 0.8         # Chặn dưới beta khi tính chi phí vốn (thận trọng)
    beta_cap: float = 1.6
    terminal_growth: float = 0.03
    forecast_years: int = 5
    max_growth: float = 0.25        # Trần tăng trưởng giả định
    min_growth: float = -0.05
    tax_rate: float = 0.20
    weights: dict = field(default_factory=lambda: {"dcf": 0.4, "pe": 0.35, "pb": 0.25})


@dataclass
class UserProfile:
    """Nhu cầu người dùng -> trọng số chấm điểm và nội dung báo cáo."""

    horizon: str = "medium"   # short | medium | long
    risk: str = "balanced"    # conservative | balanced | aggressive
    sections: tuple = ("summary", "company", "financial", "valuation", "technical",
                       "peers", "news", "risk", "appendix")

    def score_weights(self) -> dict:
        base = {
            "short":  {"fundamental": 0.15, "valuation": 0.15, "momentum": 0.40, "risk": 0.15, "news": 0.15},
            "medium": {"fundamental": 0.30, "valuation": 0.25, "momentum": 0.20, "risk": 0.15, "news": 0.10},
            "long":   {"fundamental": 0.40, "valuation": 0.35, "momentum": 0.05, "risk": 0.15, "news": 0.05},
        }[self.horizon]
        adj = dict(base)
        if self.risk == "conservative":
            adj["risk"] += 0.10
            adj["momentum"] = max(0.0, adj["momentum"] - 0.10)
        elif self.risk == "aggressive":
            adj["momentum"] += 0.10
            adj["risk"] = max(0.0, adj["risk"] - 0.10)
        s = sum(adj.values())
        return {k: v / s for k, v in adj.items()}


HORIZON_LABEL = {"short": "Ngắn hạn (< 3 tháng)", "medium": "Trung hạn (3-12 tháng)", "long": "Dài hạn (> 1 năm)"}
RISK_LABEL = {"conservative": "Thận trọng", "balanced": "Cân bằng", "aggressive": "Chấp nhận rủi ro"}
SECTION_LABEL = {
    "summary": "Tóm tắt khuyến nghị",
    "company": "Tổng quan doanh nghiệp",
    "financial": "Phân tích tài chính",
    "valuation": "Định giá",
    "technical": "Phân tích kỹ thuật",
    "peers": "So sánh ngành",
    "news": "Tin tức & cảm xúc thị trường",
    "risk": "Rủi ro",
    "appendix": "Phụ lục BCTC",
}


# ======================= TUỲ CHỌN XUẤT PDF THEO MỤC ĐÍCH =======================
SECTION_LABEL.update({"scenario": "Phân tích kịch bản đầu tư", "evidence": "Thẻ bằng chứng"})
ALL_SECTIONS = ("summary", "scenario", "company", "financial", "valuation", "technical", "peers", "news", "risk",
                "evidence", "appendix")
METRIC_GROUPS = {"profitability": "Sinh lời", "growth": "Tăng trưởng", "liquidity": "Thanh khoản, đòn bẩy & an toàn vốn",
                 "efficiency": "Hiệu quả hoạt động & dòng tiền"}
CHART_LABEL = {
    "scenario_fan": "Quạt kịch bản giá", "scenario_bars": "TSSL theo kịch bản", "sensitivity": "Ma trận độ nhạy",
    "rev_profit": "Doanh thu & lợi nhuận", "profitability": "Khả năng sinh lời", "cashflow": "Dòng tiền",
    "capital": "Cơ cấu nguồn vốn", "football": "Khoảng định giá", "pe_band": "Dải P/E lịch sử",
    "price_tech": "Giá & chỉ báo kỹ thuật", "relative": "Hiệu suất vs VN-Index", "score": "Điểm đa yếu tố",
    "peers": "So sánh ngành", "news": "Cảm xúc tin tức",
}
DETAIL_LABEL = {"brief": "Tóm lược", "standard": "Tiêu chuẩn", "detailed": "Chi tiết"}


@dataclass
class ReportOptions:
    purpose: str = "full"
    sections: tuple = ALL_SECTIONS
    metric_groups: tuple = tuple(METRIC_GROUPS)
    charts: tuple = tuple(CHART_LABEL)
    detail: str = "standard"
    years: int = 5           # số năm tài chính hiển thị trong bảng/biểu đồ


PURPOSE_PRESETS = {
    "full": {"label": "Báo cáo đầy đủ", "desc": "Toàn bộ phân tích - phù hợp lưu hồ sơ / trình bày",
             "opts": dict(sections=ALL_SECTIONS, detail="standard", years=5)},
    "long_term": {"label": "Nhà đầu tư dài hạn", "desc": "Kịch bản, tài chính, định giá, ngành, bằng chứng",
                  "opts": dict(sections=("summary", "scenario", "company", "financial", "valuation", "peers", "risk", "evidence"),
                               charts=("scenario_fan", "scenario_bars", "sensitivity", "rev_profit", "profitability", "cashflow",
                                       "capital", "football", "pe_band", "relative", "score", "peers"),
                               detail="detailed", years=7)},
    "trader": {"label": "Giao dịch ngắn hạn", "desc": "Kịch bản 1 năm, kỹ thuật, tin tức",
               "opts": dict(sections=("summary", "scenario", "technical", "news", "risk", "evidence"),
                            charts=("scenario_fan", "scenario_bars", "price_tech", "relative", "score", "news"),
                            metric_groups=("growth",), detail="brief", years=3)},
    "one_pager": {"label": "Tóm tắt nhanh (2-3 trang)", "desc": "Trang khuyến nghị + kịch bản cho người bận rộn",
                  "opts": dict(sections=("summary", "scenario"), charts=("scenario_fan", "scenario_bars", "relative", "score"),
                               detail="brief", years=3)},
    "committee": {"label": "Hội đồng đầu tư (chi tiết)", "desc": "Mọi mục + DCF chi tiết + phụ lục BCTC",
                  "opts": dict(sections=ALL_SECTIONS, detail="detailed", years=7)},
}


def preset_options(purpose: str, **overrides) -> ReportOptions:
    base = dict(PURPOSE_PRESETS.get(purpose, PURPOSE_PRESETS["full"])["opts"])
    base.update({k: v for k, v in overrides.items() if v})
    return ReportOptions(purpose=purpose, **base)
