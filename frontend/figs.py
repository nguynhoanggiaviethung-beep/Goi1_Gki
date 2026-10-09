"""Biểu đồ Plotly cho giao diện VNEquity Research - dựng từ JSON do FastAPI trả về, đồng bộ màu với PDF."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BLUE, ORANGE, PURPLE, GREEN, RED, INK, MUTED, GRID = ("#1E3A8A", "#B45309", "#60A5FA", "#15803D", "#B91C1C",
                                                     "#0F172A", "#64748B", "#EEF2F7")
SCEN = {"bull": GREEN, "base": BLUE, "bear": RED}
PALETTE = [BLUE, "#60A5FA", ORANGE, GREEN, "#64748B", "#0E7490", "#A16207", "#6D28D9"]


def _vn(x, d=0):
    return f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _layout(fig, h=360, title=None, legend=True):
    fig.update_layout(
        height=h, margin=dict(l=10, r=10, t=78 if title else 34, b=10), paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Inter, Segoe UI, sans-serif", size=12, color=INK),
        title=dict(text=title, x=0, y=0.98, yanchor="top", font=dict(size=14)) if title else None,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, bgcolor="rgba(0,0,0,0)") if legend else None,
        hoverlabel=dict(bgcolor="white", font_size=12), separators=",.",
    )
    fig.update_xaxes(showgrid=False, linecolor="#CBD5E1")
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def prices_df(prices: dict) -> pd.DataFrame:
    d = pd.DataFrame(prices)
    d["date"] = pd.to_datetime(d["date"])
    return d


def scenario_fan(prices: dict, sc: dict) -> go.Figure:
    d = prices_df(prices).tail(250)
    t0, p0 = d["date"].iloc[-1], sc["price"] / 1000
    t1 = t0 + pd.DateOffset(months=int(round(sc["years"] * 12)))
    fig = go.Figure()
    fig.add_scatter(x=d["date"], y=d["close"], name="Giá lịch sử", line=dict(color=INK, width=1.6),
                    hovertemplate="%{x|%d/%m/%Y}: %{y:.2f}<extra></extra>")
    tps = [s["target_price"] / 1000 for s in sc["items"]]
    fig.add_scatter(x=[t0, t1, t1, t0], y=[p0, max(tps), min(tps), p0], fill="toself", fillcolor="rgba(30,58,138,0.05)",
                    line=dict(width=0), showlegend=False, hoverinfo="skip")
    for s in sc["items"]:
        tp = s["target_price"] / 1000
        fig.add_scatter(x=[t0, t1], y=[p0, tp], name=s["name"], mode="lines+markers+text",
                        line=dict(color=SCEN[s["key"]], width=2.4, dash="dash"), marker=dict(size=[0, 11]),
                        text=["", f" {_vn(tp, 1)} ({s['total_return'] * 100:+.0f}%)"],
                        textposition="middle right", textfont=dict(color=SCEN[s["key"]], size=12),
                        hovertemplate=f"{s['name']}: %{{y:.1f}} nghìn đ<extra></extra>")
    fig.add_hline(y=sc["expected_price"] / 1000, line=dict(color=ORANGE, dash="dot", width=1.4),
                  annotation_text=f"Kỳ vọng {_vn(sc['expected_price'] / 1000, 1)}", annotation_position="top left",
                  annotation_font_color=ORANGE)
    fig.update_xaxes(range=[d["date"].iloc[0], t1 + pd.DateOffset(months=int(6 + 4 * sc["years"]))])
    fig.update_yaxes(title="Nghìn đồng")
    return _layout(fig, 400)


def scenario_returns(sc: dict) -> go.Figure:
    items = sc["items"]
    names = [f"{s['name']}<br><sub>p = {s['probability']:.0%}</sub>" for s in items]
    cap = [(s["target_price"] / sc["price"] - 1) * 100 for s in items]
    div = [s["dividends"] / sc["price"] * 100 for s in items]
    fig = go.Figure()
    fig.add_bar(x=names, y=cap, name="Thay đổi giá", marker_color=[SCEN[s["key"]] for s in items],
                marker_line_width=0, hovertemplate="%{y:.1f}%<extra>Giá</extra>")
    fig.add_bar(x=names, y=div, name="Cổ tức", marker_color="#CBD5E1", hovertemplate="%{y:.1f}%<extra>Cổ tức</extra>",
                text=[f"<b>{c + d_:+.1f}%</b>".replace(".", ",") for c, d_ in zip(cap, div)], textposition="outside")
    fig.add_hline(y=sc["expected_return"] * 100, line=dict(color=ORANGE, dash="dot"),
                  annotation_text=f"Kỳ vọng {sc['expected_return'] * 100:+.1f}%".replace(".", ","), annotation_font_color=ORANGE)
    fig.update_layout(barmode="relative", bargap=0.45)
    fig.update_yaxes(title="TSSL tổng (%)", ticksuffix="%")
    return _layout(fig, 330)


def sensitivity(sc: dict) -> go.Figure:
    m = np.array(sc["sensitivity"]["values"], dtype=float) * 100
    gs, pes = np.array(sc["sensitivity"]["growth"], dtype=float), np.array(sc["sensitivity"]["pe"], dtype=float)
    fig = go.Figure(go.Heatmap(
        z=m, x=[f"{c:.1f}x".replace(".", ",") for c in pes], y=[f"{g * 100:.1f}%".replace(".", ",") for g in gs],
        colorscale="RdYlGn", zmid=0, text=[[f"{v:+.0f}%" for v in row] for row in m], texttemplate="%{text}",
        hovertemplate="g = %{y} · P/E = %{x}<br>TSSL = %{z:.1f}%<extra></extra>", colorbar=dict(ticksuffix="%", thickness=10)))
    base = next(s for s in sc["items"] if s["key"] == "base")
    gi = int(np.argmin(np.abs(gs - base["eps_growth"])))
    pj = int(np.argmin(np.abs(pes - base["exit_pe"])))
    fig.add_shape(type="rect", x0=pj - 0.5, x1=pj + 0.5, y0=gi - 0.5, y1=gi + 0.5, line=dict(color=INK, width=3))
    fig.update_xaxes(title="P/E mục tiêu", type="category")
    fig.update_yaxes(title="Tăng trưởng EPS/năm", type="category")
    return _layout(fig, 380, legend=False)


def multi_metric(data: dict, metrics: list, labels: dict, pct_metrics: set, title: str) -> go.Figure:
    """Cột cho chỉ tiêu giá trị (tỷ đồng), đường cho chỉ tiêu % (trục phải), có nhãn số."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    i = 0
    for tk, df in data.items():
        for m in metrics:
            if m not in df:
                continue
            col = PALETTE[i % len(PALETTE)]
            i += 1
            name = f"{tk} · {labels[m]}" if len(data) > 1 else labels[m]
            x = df.index.astype(str)
            if m in pct_metrics:
                y = df[m] * 100
                fig.add_scatter(x=x, y=y, name=name, mode="lines+markers+text", line=dict(color=col, width=2.4),
                                marker=dict(size=6), text=[f"{v:.1f}%".replace(".", ",") if pd.notna(v) else "" for v in y],
                                textposition="top center", textfont=dict(size=10, color=col), secondary_y=True,
                                hovertemplate="%{x}: %{y:.1f}%<extra>" + name + "</extra>")
            else:
                y = df[m] / 1e9
                fig.add_bar(x=x, y=y, name=name, marker_color=col, marker_line_width=0,
                            text=[_vn(v) if pd.notna(v) else "" for v in y], textposition="outside", textfont=dict(size=9),
                            hovertemplate="%{x}: %{y:,.0f} tỷ<extra>" + name + "</extra>", secondary_y=False)
    fig.update_layout(barmode="group", bargap=0.25)
    fig.update_yaxes(title_text="Tỷ đồng", secondary_y=False)
    fig.update_yaxes(title_text="%", ticksuffix="%", secondary_y=True, showgrid=False)
    return _layout(fig, 430, title)


def price_chart(prices: dict, ticker: str = "") -> go.Figure:
    d = prices_df(prices).tail(250)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
    fig.add_candlestick(x=d["date"], open=d["open"], high=d["high"], low=d["low"], close=d["close"], name=ticker,
                        increasing_line_color=GREEN, decreasing_line_color=RED, row=1, col=1)
    for n, c in ((20, ORANGE), (50, PURPLE), (200, BLUE)):
        if f"ma{n}" in d and d[f"ma{n}"].notna().any():
            fig.add_scatter(x=d["date"], y=d[f"ma{n}"], name=f"MA{n}", line=dict(color=c, width=1.3), row=1, col=1)
    fig.add_bar(x=d["date"], y=d["volume"], name="Khối lượng", marker_color="#CBD5E1", row=2, col=1)
    fig.update_layout(xaxis_rangeslider_visible=False)
    return _layout(fig, 460)


def score_radar(comp: dict) -> go.Figure:
    lbl = {"fundamental": "Cơ bản", "valuation": "Định giá", "momentum": "Động lượng", "risk": "An toàn", "news": "Tin tức"}
    k = list(lbl)
    vals = [comp["components"].get(x) or 0 for x in k]
    fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=[lbl[x] for x in k] + [lbl[k[0]]], fill="toself",
                                    line=dict(color=BLUE), fillcolor="rgba(30,58,138,0.18)"))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], gridcolor=GRID), angularaxis=dict(gridcolor=GRID)))
    fig = _layout(fig, 300, legend=False)
    fig.update_layout(margin=dict(l=60, r=60, t=30, b=30))
    return fig