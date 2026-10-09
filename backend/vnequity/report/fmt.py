"""Định dạng số kiểu Việt Nam: phân tách nghìn bằng '.', thập phân bằng ','."""
from __future__ import annotations

import math


def _isnan(x) -> bool:
    try:
        return x is None or math.isnan(float(x))
    except (TypeError, ValueError):
        return True


def num(x, d: int = 0) -> str:
    if _isnan(x):
        return "-"
    s = f"{float(x):,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x, d: int = 1, sign: bool = False) -> str:
    if _isnan(x):
        return "-"
    s = f"{float(x) * 100:{'+' if sign else ''},.{d}f}%"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def bil(x, d: int = 0) -> str:
    """Đồng -> tỷ đồng."""
    return "-" if _isnan(x) else num(float(x) / 1e9, d)


def times(x, d: int = 1) -> str:
    return "-" if _isnan(x) else num(x, d) + "x"
