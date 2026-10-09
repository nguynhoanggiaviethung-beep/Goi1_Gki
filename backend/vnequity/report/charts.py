"""Biểu đồ cho báo cáo PDF (matplotlib -> PNG).

Quy ước trình bày:
  - Mọi biểu đồ có tên ở góc trên bên trái.
  - Chú thích (legend) đặt thành một hàng riêng bên dưới vùng vẽ, không đè lên dữ liệu.
  - Chữ dùng một tông xanh than; không dùng màu xám.
  - Màu ý nghĩa: xanh dương đậm = chuỗi chính / kịch bản cơ sở, xanh lá = tích cực / tăng,
    đỏ = tiêu cực / giảm, nâu vàng = điểm nhấn, xanh thép = chuỗi phụ.
"""
from __future__ import annotations

import math
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

INK = "#0F2A4A"        # chữ chính
INK2 = "#2C4A6E"       # chữ phụ (nhãn trục, số trên trục)
NAVY = "#1E3A8A"       # chuỗi chính / kịch bản cơ sở
TEAL = "#5B8BD0"       # chuỗi phụ (xanh dương vừa)
ORANGE = "#B45309"     # điểm nhấn (nâu vàng)
GREEN = "#15803D"      # tích cực
RED = "#B91C1C"        # tiêu cực
GREY = "#7E9BC0"       # chuỗi thứ ba (xanh thép) - thay cho màu xám
LIGHT = "#E6EEF8"      # nền nhạt
RULE = "#C9D6E8"       # đường kẻ

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 7.5, "text.color": INK,
    "axes.titlesize": 8.5, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlepad": 8,
    "axes.edgecolor": RULE, "axes.linewidth": 0.7, "axes.labelcolor": INK2, "axes.labelsize": 7,
    "axes.grid": True, "grid.color": "#EDF2F9", "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "xtick.color": INK2, "ytick.color": INK2, "xtick.labelsize": 6.8, "ytick.labelsize": 6.8,
    "legend.frameon": False, "legend.fontsize": 6.8, "legend.labelcolor": INK, "legend.handlelength": 1.8,
    "legend.handletextpad": 0.6, "legend.columnspacing": 1.8, "figure.dpi": 100,
})


def _vn(x, d=0):
    return f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _thousands(ax, axis="y"):
    f = FuncFormatter(lambda x, _: _vn(x))
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def _legend(fig, axes, ncol=None):
    """Gom chú thích của các trục thành một hàng (hoặc vài hàng) riêng ở đáy hình."""
    handles, labels = [], []
    for ax in axes:
        h, l_ = ax.get_legend_handles_labels()
        for hh, ll in zip(h, l_):
            if ll and not ll.startswith("_") and ll not in labels:
                handles.append(hh)
                labels.append(ll)
    if not handles:
        return
    ncol = ncol or len(handles)
    rows = math.ceil(len(handles) / ncol)
    fig.legend(handles, labels, loc="lower center", ncol=ncol, bbox_to_anchor=(0.5, 0.005))
    fig._legend_frac = (0.17 + 0.16 * rows) / fig.get_figheight()


def _save(fig, path: Path, top=None) -> Path:
    bottom = getattr(fig, "_legend_frac", 0.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            fig.tight_layout(pad=0.5, rect=[0, bottom, 1, top or 1])
        except Exception:  # noqa: BLE001
            pass
    fig.savefig(path, dpi=200, facecolor="white")
    plt.close(fig)
    return path


# ============================== GIÁ & KỸ THUẬT ==============================
def price_technical(d: pd.DataFrame, ticker: str, path: Path, levels=None) -> Path:
    d = d.tail(250)
    fig = plt.figure(figsize=(7.6, 5.8))
    gs = fig.add_gridspec(4, 1, height_ratios=[3.2, 0.9, 0.9, 0.9], hspace=0.12)
    ax = fig.add_subplot(gs[0])
    ax.fill_between(d["date"], d["bb_low"], d["bb_up"], color=LIGHT, label="Dải Bollinger (20, 2)")
    ax.plot(d["date"], d["close"], color=INK, lw=1.3, label="Giá đóng cửa")
    for n, col in ((20, ORANGE), (50, TEAL), (200, NAVY)):
        if d[f"ma{n}"].notna().any():
            ax.plot(d["date"], d[f"ma{n}"], color=col, lw=1.0, label=f"MA{n}")
    if levels:
        x0 = d["date"].iloc[3]
        for v in levels[0][:2]:
            ax.axhline(v, color=GREEN, ls="--", lw=0.8)
            ax.text(x0, v, f"Hỗ trợ {_vn(v, 1)}", color=GREEN, va="bottom", fontsize=6.5, fontweight="bold")
        for v in levels[1][:2]:
            ax.axhline(v, color=RED, ls="--", lw=0.8)
            ax.text(x0, v, f"Kháng cự {_vn(v, 1)}", color=RED, va="bottom", fontsize=6.5, fontweight="bold")
    ax.set_ylabel("Nghìn đồng")
    ax.tick_params(labelbottom=False)

    av = fig.add_subplot(gs[1], sharex=ax)
    av.bar(d["date"], d["volume"] / 1e6, color=np.where(d["close"].diff().fillna(0) >= 0, GREEN, RED), width=1.0, alpha=0.65)
    av.plot(d["date"], d["vol_ma20"] / 1e6, color=NAVY, lw=0.9, label="KL bình quân 20 phiên")
    av.set_ylabel("KL (triệu cp)")
    av.tick_params(labelbottom=False)

    ar = fig.add_subplot(gs[2], sharex=ax)
    ar.plot(d["date"], d["rsi14"], color=NAVY, lw=0.9, label="RSI 14")
    ar.axhspan(70, 100, color=RED, alpha=0.07)
    ar.axhspan(0, 30, color=GREEN, alpha=0.07)
    ar.set_ylim(0, 100)
    ar.set_ylabel("RSI 14")
    ar.tick_params(labelbottom=False)

    am = fig.add_subplot(gs[3], sharex=ax)
    am.bar(d["date"], d["macd_hist"], color=np.where(d["macd_hist"] >= 0, GREEN, RED), width=1.0, alpha=0.55)
    am.plot(d["date"], d["macd"], color=NAVY, lw=0.9, label="MACD")
    am.plot(d["date"], d["macd_signal"], color=ORANGE, lw=0.9, label="Đường tín hiệu MACD")
    am.set_ylabel("MACD")
    am.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    fig.suptitle(f"Diễn biến giá và chỉ báo kỹ thuật {ticker} (giá điều chỉnh)", x=0.01, ha="left",
                 fontsize=8.5, fontweight="bold", color=INK)
    _legend(fig, [ax, av, am], ncol=5)
    return _save(fig, path, top=0.95)


def relative_perf(d: pd.DataFrame, idx: pd.DataFrame | None, ticker: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    d = d.tail(250)
    ax.plot(d["date"], d["close"] / d["close"].iloc[0] * 100, color=NAVY, lw=1.3, label=ticker)
    if idx is not None:
        m = idx[idx["date"] >= d["date"].iloc[0]]
        if len(m):
            ax.plot(m["date"], m["close"] / m["close"].iloc[0] * 100, color=ORANGE, lw=1.1, label="VN-Index")
    ax.axhline(100, color=RULE, lw=0.8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.set_title("Hiệu suất 12 tháng so với VN-Index (gốc = 100)", loc="left", fontsize=7.5)
    _legend(fig, [ax])
    return _save(fig, path)


# ============================== TÀI CHÍNH ==============================
def revenue_profit(fin: pd.DataFrame, ratios: pd.DataFrame, path: Path, years: int = 7, rev_label: str = "Doanh thu thuần") -> Path:
    f = fin.tail(years)
    r = ratios.loc[f.index]
    fig, ax = plt.subplots(figsize=(3.7, 2.7))
    x = np.arange(len(f))
    npat = f["npat_parent"].fillna(f["npat"])
    bars = ax.bar(x - 0.2, f["revenue"] / 1e9, 0.4, color=NAVY, label=rev_label)
    for rect, val in zip(bars, f["revenue"] / 1e9):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(), _vn(val), ha="center", va="bottom",
                fontsize=5.3, color=INK)
    ax.bar(x + 0.2, npat / 1e9, 0.4, color=TEAL, label="LNST CĐ mẹ")
    ax.set_xticks(x, f.index.astype(str))
    ax.set_ylabel("Tỷ đồng")
    ax.margins(y=0.12)
    ax2 = ax.twinx()
    ax2.plot(x, r["net_margin"] * 100, color=ORANGE, marker="o", ms=3, lw=1.3, label="Biên LN ròng (trục phải)")
    ax2.grid(False)
    ax2.spines["right"].set_visible(False)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{_vn(v, 1)}%"))
    ax.set_title("Doanh thu, lợi nhuận và biên lợi nhuận ròng", loc="left")
    _thousands(ax)
    _legend(fig, [ax, ax2], ncol=3)
    return _save(fig, path)


def profitability(ratios: pd.DataFrame, path: Path, years: int = 7) -> Path:
    r = ratios.tail(years) * 100
    fig, ax = plt.subplots(figsize=(3.7, 2.7))
    for col, lbl, c in (("gross_margin", "Biên gộp", NAVY), ("ebit_margin", "Biên EBIT", TEAL),
                        ("roe", "ROE", ORANGE), ("roa", "ROA", GREEN)):
        if r[col].notna().any():
            ax.plot(r.index.astype(str), r[col], marker="o", ms=3, lw=1.3, color=c, label=lbl)
    if "cir" in r and r["cir"].notna().any():
        ax.plot(r.index.astype(str), r["cir"], marker="s", ms=3, lw=1.3, color=RED, label="CIR")
        ax.plot(r.index.astype(str), r["nim_proxy"], marker="^", ms=3, lw=1.3, color=TEAL, label="NIM (xấp xỉ)")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{_vn(v, 0)}%"))
    ax.set_title("Khả năng sinh lời", loc="left")
    _legend(fig, [ax], ncol=4)
    return _save(fig, path)


def cashflow(fin: pd.DataFrame, ratios: pd.DataFrame, path: Path, years: int = 7) -> Path:
    f = fin.tail(years)
    fig, ax = plt.subplots(figsize=(3.7, 2.7))
    x = np.arange(len(f))
    w = 0.2
    ax.bar(x - 1.5 * w, f["cfo"] / 1e9, w, color=GREEN, label="Kinh doanh")
    ax.bar(x - 0.5 * w, f["cfi"] / 1e9, w, color=RED, label="Đầu tư")
    ax.bar(x + 0.5 * w, f["cff"] / 1e9, w, color=GREY, label="Tài chính")
    if ratios.loc[f.index, "fcf"].notna().any():
        ax.bar(x + 1.5 * w, ratios.loc[f.index, "fcf"] / 1e9, w, color=NAVY, label="Dòng tiền tự do")
    ax.axhline(0, color=INK2, lw=0.6)
    ax.set_xticks(x, f.index.astype(str))
    ax.set_ylabel("Tỷ đồng")
    ax.set_title("Lưu chuyển tiền tệ theo hoạt động", loc="left")
    _thousands(ax)
    _legend(fig, [ax], ncol=4)
    return _save(fig, path)


def capital_structure(fin: pd.DataFrame, ratios: pd.DataFrame, path: Path, years: int = 7) -> Path:
    f = fin.tail(years)
    fig, ax = plt.subplots(figsize=(3.7, 2.7))
    x = np.arange(len(f))
    bank = f["deposits"].notna().any()
    debt = (f["deposits"].fillna(0) if bank else (f["st_debt"].fillna(0) + f["lt_debt"].fillna(0))) / 1e9
    other = f["liabilities"] / 1e9 - debt
    eq = f["equity"] / 1e9
    ax.bar(x, eq, color=NAVY, label="Vốn chủ sở hữu")
    ax.bar(x, debt, bottom=eq, color=ORANGE, label="Tiền gửi KH" if bank else "Nợ vay")
    ax.bar(x, other, bottom=eq + debt, color=LIGHT, edgecolor=RULE, lw=0.5, label="Nợ khác")
    ax.set_xticks(x, f.index.astype(str))
    ax.set_ylabel("Tỷ đồng")
    ax2 = ax.twinx()
    lev = ratios.loc[f.index, "dupont_leverage" if bank else "debt_to_equity"]
    ax2.plot(x, lev, color=RED, marker="o", ms=3, lw=1.3,
             label=("TTS/VCSH" if bank else "Nợ vay/VCSH") + " (trục phải)")
    ax2.grid(False)
    ax2.spines["right"].set_visible(False)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _vn(v, 1)))
    ax.set_title("Cơ cấu nguồn vốn", loc="left")
    _thousands(ax)
    _legend(fig, [ax, ax2], ncol=2)
    return _save(fig, path)


# ============================== ĐỊNH GIÁ ==============================
def pe_band(hpe: pd.DataFrame, current_pe: float, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(3.7, 2.7))
    if len(hpe):
        m, s = hpe["pe"].mean(), hpe["pe"].std()
        ax.plot(hpe["date"], hpe["pe"], color=NAVY, lw=1.2, label="P/E")
        ax.axhline(m, color=ORANGE, lw=1.0, label=f"Bình quân {_vn(m, 1)}x")
        ax.axhline(m + s, color=GREY, ls="--", lw=0.8, label="±1 độ lệch chuẩn")
        ax.axhline(m - s, color=GREY, ls="--", lw=0.8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{_vn(v, 0)}x"))
    ax.set_title(f"Diễn biến P/E 12 tháng (hiện tại {_vn(current_pe, 1)}x)", loc="left")
    _legend(fig, [ax], ncol=3)
    return _save(fig, path)


def football_field(val: dict, path: Path) -> Path:
    price = val["multiples"]["price"]
    items = []
    for m in val["methods"].values():
        v = m["value"]
        items.append((m["label"].split(" (")[0].split(" ×")[0], v * 0.9, v * 1.1, v))
    if "sensitivity" in val:
        s = val["sensitivity"].values
        items.append(("Độ nhạy DCF (ke, g ±1%)", float(np.min(s)), float(np.max(s)), float(np.median(s))))
    hs = val["hist_pe_stats"]
    eps = val["multiples"]["eps"]
    if pd.notna(hs.get("min")) and eps > 0:
        items.append(("Dải P/E 12 tháng", hs["min"] * eps, hs["max"] * eps, hs["avg"] * eps))
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(items) + 1.2))
    for i, (lbl, lo, hi, mid) in enumerate(items):
        ax.barh(i, (hi - lo) / 1000, left=lo / 1000, color=TEAL, alpha=0.8, height=0.5)
        ax.plot(mid / 1000, i, "o", color=NAVY, ms=4)
        ax.text(hi / 1000, i, f"  {_vn(lo / 1000, 1)} - {_vn(hi / 1000, 1)}", va="center", fontsize=6.6, color=INK)
    ax.axvline(price / 1000, color=RED, lw=1.3, label=f"Thị giá {_vn(price / 1000, 1)}")
    ax.axvline(val["target_price"] / 1000, color=GREEN, lw=1.3, ls="--", label=f"Giá trị hợp lý {_vn(val['target_price'] / 1000, 1)}")
    ax.set_yticks(range(len(items)), [i[0] for i in items])
    ax.set_xlabel("Nghìn đồng/cổ phiếu")
    ax.set_title("Khoảng định giá theo từng phương pháp", loc="left")
    ax.set_xlim(0, max(max(i[2] for i in items), price) / 1000 * 1.22)
    _legend(fig, [ax], ncol=2)
    return _save(fig, path)


def score_bars(comp: dict, path: Path) -> Path:
    labels = {"fundamental": "Cơ bản", "valuation": "Định giá", "momentum": "Động lượng", "risk": "An toàn", "news": "Tin tức"}
    keys = list(labels)
    vals = [comp["components"][k] for k in keys]
    fig, ax = plt.subplots(figsize=(3.4, 1.9))
    cols = [GREEN if v >= 65 else (ORANGE if v >= 40 else RED) for v in vals]
    ax.barh(range(len(keys)), vals, color=cols, height=0.55)
    for i, (v, k) in enumerate(zip(vals, keys)):
        ax.text(v + 2, i, f"{v:.0f}  (trọng số {comp['weights'][k]:.0%})", va="center", fontsize=6.4, color=INK)
    ax.set_yticks(range(len(keys)), [labels[k] for k in keys])
    ax.set_xlim(0, 135)
    ax.invert_yaxis()
    ax.set_title(f"Điểm đánh giá đa yếu tố (tổng {comp['total']:.0f}/100)", loc="left", fontsize=7.5)
    return _save(fig, path)


def peer_bars(peers: pd.DataFrame, ticker: str, path: Path) -> Path:
    p = peers.dropna(subset=["ROE"]).head(8)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6))
    for ax, col, title in ((axes[0], "ROE", "ROE"), (axes[1], "Biên LN ròng", "Biên lợi nhuận ròng")):
        q = p.sort_values(col, ascending=True)
        ax.barh(q["Mã"], q[col] * 100, color=[ORANGE if t == ticker else NAVY for t in q["Mã"]], height=0.6)
        ax.set_title(title, loc="left", fontsize=7.5)
        ax.axvline(0, color=INK2, lw=0.5)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{_vn(v, 0)}%"))
    fig.suptitle(f"So sánh {ticker} với doanh nghiệp cùng ngành (năm tài chính gần nhất)", x=0.01, ha="left",
                 fontsize=8.5, fontweight="bold", color=INK)
    return _save(fig, path, top=0.9)


def news_sentiment(news: dict, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(3.4, 2.0))
    vals = [news["n_pos"], news["n_neu"], news["n_neg"]]
    ax.bar(["Tích cực", "Trung tính", "Tiêu cực"], vals, color=[GREEN, GREY, RED], width=0.55)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.2, str(v), ha="center", fontsize=7, color=INK, fontweight="bold")
    ax.set_ylabel("Số tin")
    ax.margins(y=0.15)
    ax.set_title(f"Phân bố cảm xúc tin tức (điểm TB {news['avg_sentiment']:+.2f})".replace(".", ","), loc="left", fontsize=7.5)
    return _save(fig, path)


# ============================== KỊCH BẢN ==============================
SCEN_COLORS = {"bull": GREEN, "base": NAVY, "bear": RED}


def scenario_fan(prices: pd.DataFrame, ss, path: Path, ticker: str = "") -> Path:
    """Giá lịch sử và đường dẫn tới giá mục tiêu của 3 kịch bản (nghìn đồng)."""
    d = prices.tail(250)
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    ax.plot(d["date"], d["close"], color=INK, lw=1.2, label="Giá lịch sử")
    t0, p0 = d["date"].iloc[-1], ss.price / 1000
    t1 = t0 + pd.DateOffset(months=int(round(ss.years * 12)))
    ys = [s.target_price / 1000 for s in ss.ordered()]
    ax.fill_between([t0, t1], [p0, p0], [p0, max(ys)], color=GREEN, alpha=0.06)
    ax.fill_between([t0, t1], [p0, p0], [p0, min(ys)], color=RED, alpha=0.06)
    for s in ss.ordered():
        tp = s.target_price / 1000
        c = SCEN_COLORS[s.key]
        ax.plot([t0, t1], [p0, tp], color=c, lw=1.6, ls="--", label=f"Kịch bản {s.name.lower()}")
        ax.scatter([t1], [tp], color=c, s=26, zorder=5)
        ax.annotate(f"{_vn(tp, 1)} ({s.total_return * 100:+.0f}%)", (t1, tp), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=7, color=c, fontweight="bold")
    ax.axhline(ss.expected_price / 1000, color=ORANGE, lw=1.0, ls=":", label=f"Giá trị kỳ vọng {_vn(ss.expected_price / 1000, 1)}")
    ax.scatter([t0], [p0], color=INK, s=20, zorder=5)
    ax.set_xlim(d["date"].iloc[0], t1 + pd.DateOffset(months=int(3 * ss.years) + 2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    ax.set_ylabel("Nghìn đồng")
    ax.set_title(f"Giá lịch sử và giá mục tiêu theo 3 kịch bản sau {ss.label}", loc="left")
    _legend(fig, [ax], ncol=5)
    return _save(fig, path)


def scenario_bars(ss, path: Path) -> Path:
    """Tỷ suất sinh lời tổng của từng kịch bản, tách phần thay đổi giá và cổ tức."""
    fig, ax = plt.subplots(figsize=(3.5, 2.5))
    names, cap, div = [], [], []
    for s in ss.ordered():
        names.append(f"{s.name}\n(xác suất {s.probability:.0%})")
        cap.append((s.target_price / ss.price - 1) * 100)
        div.append(s.dividends / ss.price * 100)
    x = np.arange(3)
    ax.bar(x, cap, color=[SCEN_COLORS[k] for k in ("bull", "base", "bear")], width=0.55, label="Thay đổi giá")
    ax.bar(x, div, bottom=cap, color="#BFD0E6", width=0.55, label="Cổ tức")
    for i in range(3):
        tot = cap[i] + div[i]
        ax.text(i, tot + (2 if tot >= 0 else -7), f"{tot:+.1f}%".replace(".", ","), ha="center", fontsize=7.2,
                fontweight="bold", color=INK)
    ax.axhline(0, color=INK2, lw=0.6)
    ax.axhline(ss.expected_return * 100, color=ORANGE, lw=1, ls=":", label=f"Kỳ vọng {ss.expected_return * 100:+.1f}%".replace(".", ","))
    ax.set_xticks(x, names, fontsize=6.5)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{_vn(v, 0)}%"))
    ax.margins(y=0.12)
    ax.set_title("Tỷ suất sinh lời theo kịch bản", loc="left")
    _legend(fig, [ax], ncol=3)
    return _save(fig, path)


def sensitivity_heatmap(ss, path: Path) -> Path:
    m = ss.sensitivity * 100
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    lim = max(abs(np.nanmin(m.values)), abs(np.nanmax(m.values)), 1)
    im = ax.imshow(m.values, cmap="RdYlGn", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(m.shape[1]), [f"{_vn(c, 1)}x" for c in m.columns])
    ax.set_yticks(range(m.shape[0]), [f"{_vn(g * 100, 1)}%" for g in m.index])
    ax.set_xlabel("P/E mục tiêu")
    ax.set_ylabel("Tăng trưởng EPS mỗi năm")
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            ax.text(j, i, f"{m.values[i, j]:+.0f}%", ha="center", va="center", fontsize=6.5,
                    color="white" if abs(m.values[i, j]) > lim * 0.6 else INK)
    base = ss.scenarios["base"]
    gi = int(np.argmin(np.abs(m.index.values - base.eps_growth)))
    pj = int(np.argmin(np.abs(m.columns.values - base.exit_pe)))
    ax.add_patch(plt.Rectangle((pj - 0.5, gi - 0.5), 1, 1, fill=False, ec=INK, lw=1.8))
    ax.grid(False)
    ax.set_title(f"Ma trận độ nhạy tỷ suất sinh lời {ss.label} (ô viền đậm: kịch bản cơ sở)", loc="left")
    cb = plt.colorbar(im, ax=ax, pad=0.01, fraction=0.03)
    cb.ax.tick_params(labelsize=6.3, colors=INK2)
    cb.outline.set_edgecolor(RULE)
    return _save(fig, path)