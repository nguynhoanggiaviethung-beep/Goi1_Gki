"""Small vnstock adapter for on-demand market and fundamentals retrieval."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Any

from fastapi import HTTPException


def _records(frame: Any) -> list[dict]:
    if frame is None:
        return []
    if hasattr(frame, "empty") and frame.empty:
        return []
    if hasattr(frame, "to_dict"):
        try:
            return frame.to_dict(orient="records")
        except TypeError:
            pass
    if isinstance(frame, dict):
        return [frame]
    if isinstance(frame, list):
        return frame
    return []


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _period_columns(record: dict) -> list[str]:
    ignored = {"item", "item_id", "item_en", "unit", "levels", "row_number", "ticker", "symbol"}
    columns = [str(key) for key in record if str(key).lower() not in ignored]

    def order(period: str):
        match = re.search(r"(19|20)\d{2}(?:[-_ ]?Q([1-4]))?", period, re.I)
        if not match:
            return (0, 0)
        return (int(match.group(0)[:4]), int(match.group(2) or 0))

    return sorted(columns, key=order, reverse=True)


def _find_ratio(records: list[dict], keywords: tuple[str, ...]) -> tuple[float, str] | None:
    candidates = []
    for row in records:
        labels = [str(row.get(key, "")).lower() for key in ("item_id", "item", "item_en")]
        matched = False
        for keyword in keywords:
            if keyword in {"eps", "pe"}:
                matched = any(re.search(rf"\b{re.escape(keyword)}\b", label) for label in labels)
            else:
                matched = any(keyword in label for label in labels)
            if matched:
                break
        if matched:
            for period in _period_columns(row):
                value = _number(row.get(period))
                if value is not None:
                    candidates.append((period, value))
                    break
    if not candidates:
        return None
    candidates.sort(key=lambda pair: _period_key(pair[0]), reverse=True)
    return candidates[0][1], candidates[0][0]


def _period_key(period: str) -> tuple[int, int]:
    match = re.search(r"(19|20)\d{2}(?:[-_ ]?Q([1-4]))?", period, re.I)
    return (int(match.group(0)[:4]), int(match.group(2) or 0)) if match else (0, 0)


def _eps_history(records: list[dict]) -> list[tuple[str, float]]:
    for row in records:
        label = " ".join(str(row.get(key, "")) for key in ("item_id", "item", "item_en")).lower()
        if "eps" not in label and "earnings per share" not in label and "lãi cơ bản trên cổ phiếu" not in label:
            continue
        values = []
        for period in _period_columns(row):
            value = _number(row.get(period))
            if value is not None:
                values.append((period, value))
        return sorted(values, key=lambda item: _period_key(item[0]))
    return []


def _ratio_history(records: list[dict], keywords: tuple[str, ...]) -> list[tuple[str, float]]:
    for row in records:
        labels = [str(row.get(key, "")).lower() for key in ("item_id", "item", "item_en")]
        if any((re.search(rf"\b{re.escape(word)}\b", label) if word in {"pe", "eps"} else word in label) for word in keywords for label in labels):
            return sorted([(period, value) for period in _period_columns(row) if (value := _number(row.get(period))) is not None], key=lambda item: _period_key(item[0]))
    return []


def _annual_growth_history(eps_history: list[tuple[str, float]]) -> list[dict]:
    """Year-on-year EPS growth; exclude losses, sign changes and non-adjacent years."""
    annual = { _period_key(period)[0]: value for period, value in eps_history if _period_key(period)[0] and "Q" not in period.upper() }
    result = []
    for year in sorted(annual):
        previous, current = annual.get(year - 1), annual[year]
        if previous is not None and current > 0 and previous > 0:
            result.append({"period": f"FY{year}", "growth_pct": (current / previous - 1) * 100})
    return result


def _fetch_quote(market, ticker: str) -> dict:
    methods = [
        lambda: market.quote(ticker),
        lambda: market.quote(symbol=ticker),
        lambda: market.equity.quote(symbol=ticker),
    ]
    for call in methods:
        try:
            rows = _records(call())
            if rows:
                quote = rows[0]
                price = next((_number(quote.get(key)) for key in ("close_price", "price", "close", "last_price") if _number(quote.get(key)) is not None), None)
                if price and price > 0:
                    return {"price": price, "period": str(quote.get("time") or quote.get("date") or "Phiên gần nhất")}
        except Exception:  # source/provider changes; try its documented fallback API
            pass
    try:
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=14)
        rows = _records(market.equity.ohlcv(symbol=ticker, start=start.isoformat(), end=end.isoformat()))
        rows.sort(key=lambda row: str(row.get("time") or row.get("date") or ""))
        for row in reversed(rows):
            price = _number(row.get("close"))
            if price and price > 0:
                # Unified OHLCV is commonly expressed in thousand VND; normalize
                # when the quote API is unavailable and the bar scale indicates it.
                normalized = price * 1000
                return {"price": normalized, "period": str(row.get("time") or row.get("date") or "Phiên gần nhất")}
    except Exception:
        pass
    raise HTTPException(status_code=502, detail=f"vnstock không trả được giá cho {ticker}. Kiểm tra mã, kết nối và trạng thái nguồn dữ liệu.")


def fetch_live_inputs(ticker: str, growth_override: float | None = None, pe_override: float | None = None) -> dict:
    """Fetch latest quote + annual EPS/P-E ratios; never fabricate unavailable fields."""
    try:
        from vnstock import Fundamental, Market
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Chưa cài vnstock. Cài backend theo README với kho gói vnstock được hướng dẫn.",
        ) from exc

    symbol = ticker.strip().upper()
    try:
        market = Market()
        quote = _fetch_quote(market, symbol)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Không lấy được bảng giá từ vnstock: {exc}") from exc

    try:
        fundamentals = Fundamental()
        equity_accessor = fundamentals.equity
        # vnstock 4 exposes equity as a factory: Fundamental().equity("FPT").
        # Older package revisions exposed ratios() on the unbound accessor, so
        # retain a guarded compatibility path for both API shapes.
        if callable(equity_accessor):
            equity = equity_accessor(symbol)
            ratio_method = getattr(equity, "ratio", None) or getattr(equity, "ratios", None)
            if ratio_method is None:
                raise AttributeError("vnstock Fundamental.equity(...) không có ratio()/ratios()")
            try:
                ratios = ratio_method(period="year")
            except TypeError:
                ratios = ratio_method()
        else:
            ratio_method = getattr(equity_accessor, "ratios", None) or getattr(equity_accessor, "ratio", None)
            if ratio_method is None:
                raise AttributeError("vnstock Fundamental.equity không có ratios()/ratio()")
            try:
                ratios = ratio_method(symbol=symbol, period="year")
            except TypeError:
                ratios = ratio_method(symbol=symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Không lấy được tỷ số tài chính cho {symbol}: {exc}") from exc

    rows = _records(ratios)
    pe_result = _find_ratio(rows, ("pe", "price to earnings", "p/e"))
    eps_result = _find_ratio(rows, ("eps", "earnings per share", "earnings_per_share", "earning_per_share", "lãi cơ bản trên cổ phiếu"))
    eps_history = _eps_history(rows)
    pe_history_raw = _ratio_history(rows, ("pe", "price to earnings", "p/e"))
    annual_growth_history = _annual_growth_history(eps_history)
    eps_periods = {period for period, value in eps_history if value > 0}
    pe_history = [{"period": period, "pe": value} for period, value in pe_history_raw if value > 0 and period in eps_periods]
    eps_basis = "EPS báo cáo do vnstock cung cấp"
    if eps_result is None and pe_result and pe_result[0] > 0:
        # Only fall back to a market-implied EPS when the source has no EPS row.
        eps_result = (quote["price"] / pe_result[0], pe_result[1])
        eps_basis = "EPS hàm ý = giá hiện tại / P/E nguồn; ước tính thị trường, không phải EPS báo cáo"
    if eps_result is None:
        raise HTTPException(status_code=422, detail=f"Nguồn không có EPS hoặc P/E dương cho {symbol}; chưa thể chạy định giá P/E.")
    eps, eps_period = eps_result
    if eps <= 0:
        raise HTTPException(status_code=422, detail=f"EPS mới nhất của {symbol} không dương; loại mã khỏi định giá P/E vì bội số không có ý nghĩa.")
    implied_pe_on_eps_basis = quote["price"] / eps
    if implied_pe_on_eps_basis > 500:
        raise HTTPException(status_code=422, detail=f"EPS của {symbol} quá nhỏ so với giá (P/E hàm ý {implied_pe_on_eps_basis:.1f}× > 500×); loại mã khỏi định giá P/E và kiểm tra kỳ/đơn vị EPS.")

    if growth_override is None:
        positive_history = [(period, value) for period, value in eps_history if value > 0]
        if len(positive_history) < 2:
            raise HTTPException(status_code=422, detail="Chưa đủ ít nhất hai kỳ EPS dương để tính tăng trưởng lịch sử. Gửi growth_pct trong request để nhập giả định thủ công.")
        older_period, older_eps = positive_history[-2]
        latest_period, latest_eps = positive_history[-1]
        year_gap = max(1, _period_key(latest_period)[0] - _period_key(older_period)[0])
        growth = ((latest_eps / older_eps) ** (1 / year_gap) - 1) * 100
        growth_period = f"{older_period} đến {latest_period}"
    else:
        growth = growth_override
        growth_period = "Giả định do người dùng nhập"

    if pe_override is not None:
        selected_pe = pe_override
        pe_basis = f"P/E mục tiêu do người dùng nhập; áp dụng cho EPS cùng kỳ/cơ sở {eps_period}"
        pe_period = eps_period
    elif pe_result and pe_result[0] > 0 and pe_result[1] == eps_period:
        selected_pe = pe_result[0]
        pe_basis = f"P/E nguồn cùng kỳ EPS {eps_period}; cần kiểm tra quy ước EPS của nhà cung cấp"
        pe_period = pe_result[1]
    else:
        # Align the reference multiple to the exact EPS observation used by the
        # scenario instead of multiplying a different TTM/fiscal basis.
        selected_pe = implied_pe_on_eps_basis
        pe_basis = f"P/E tham chiếu tự tính = giá hiện tại / EPS báo cáo kỳ {eps_period}; cùng cơ sở EPS"
        pe_period = eps_period

    retrieved_at = datetime.now(timezone.utc).isoformat()
    return {
        "ticker": symbol,
        "current_price": quote["price"],
        "price_period": quote["period"],
        "eps": eps,
        "eps_period": eps_period,
        "eps_basis": eps_basis,
        "growth_history": annual_growth_history,
        "pe_history": pe_history,
        "earnings_growth_pct": growth,
        "growth_period": growth_period,
        "target_pe": selected_pe,
        "pe_period": pe_period,
        "pe_basis": pe_basis,
        "retrieved_at": retrieved_at,
        "source": "vnstock connector (bảng giá/tỷ số tài chính từ nhà cung cấp bên thứ ba)",
        "freshness": "Truy vấn mới tại thời điểm gọi; giá trong phiên có thể bị trễ theo nhà cung cấp.",
    }
