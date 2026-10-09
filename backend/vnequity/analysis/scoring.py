"""Tổng hợp điểm đa yếu tố & khuyến nghị đầu tư theo nhu cầu người dùng."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import UserProfile

RATINGS = ["BÁN", "KÉM KHẢ QUAN", "NẮM GIỮ", "KHẢ QUAN", "MUA"]
RATING_COLOR = {"MUA": "#15803D", "KHẢ QUAN": "#4D7C0F", "NẮM GIỮ": "#B45309", "KÉM KHẢ QUAN": "#C2410C", "BÁN": "#B91C1C"}


def rating_from_upside(up: float) -> str:
    if pd.isna(up):
        return "NẮM GIỮ"
    if up >= 0.20:
        return "MUA"
    if up >= 0.10:
        return "KHẢ QUAN"
    if up > -0.10:
        return "NẮM GIỮ"
    if up > -0.20:
        return "KÉM KHẢ QUAN"
    return "BÁN"


def composite(scores: dict, profile: UserProfile) -> dict:
    w = profile.score_weights()
    total = sum(scores[k] * w[k] for k in w)
    return {"total": float(total), "weights": w, "components": scores}


def recommend(upside: float, comp_score: float, news_score: float, horizon: str = "medium",
              momentum: float | None = None) -> tuple[str, str]:
    """Khuyến nghị = mức theo tiềm năng tăng giá, điều chỉnh ±1 bậc theo điểm tổng hợp.

    Với kỳ hạn ngắn, xu hướng giá quan trọng hơn định giá: động lượng < 35 thì hạ thêm 1 bậc.
    """
    base = rating_from_upside(upside)
    idx = RATINGS.index(base)
    reason = f"Tiềm năng tăng giá {upside * 100:+.1f}%, tương ứng mức {base}".replace(".", ",")
    if comp_score >= 70 and idx < 4:
        idx += 1
        reason += f"; điểm tổng hợp cao ({comp_score:.0f}/100) nên nâng 1 bậc"
    elif comp_score < 40 and idx > 0:
        idx -= 1
        reason += f"; điểm tổng hợp thấp ({comp_score:.0f}/100) nên hạ 1 bậc"
    if horizon == "short" and momentum is not None and momentum < 35 and idx > 0:
        idx -= 1
        reason += f"; kỳ hạn ngắn & động lượng yếu ({momentum:.0f}/100) nên hạ 1 bậc"
    return RATINGS[idx], reason


def news_score(avg_sent: float) -> float:
    return float(np.clip(50 + avg_sent * 50, 0, 100))
