"""VNStockAI Streamlit UI. This layer calls the Goi1_Gki FastAPI backend."""
from __future__ import annotations

import os
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


API_BASE = os.getenv("VNEQUITY_API_URL", "http://127.0.0.1:8000").rstrip("/")
PAGES = [
    "🎯  Kịch bản đầu tư",
    "🔍  Luận điểm & bằng chứng",
    "📊  So sánh mã",
    "🏆  Sàng lọc cơ hội",
    "📄  Xuất báo cáo PDF",
    "📰  Báo cáo & tin doanh nghiệp",
]
HORIZONS = {3: "3 tháng", 6: "6 tháng", 12: "12 tháng"}
RISKS = {"conservative": "Thận trọng", "balanced": "Cân bằng", "aggressive": "Chấp nhận rủi ro"}
PURPOSES = {
    "full": "Báo cáo đầy đủ",
    "long_term": "Nhà đầu tư dài hạn",
    "trader": "Giao dịch ngắn hạn",
    "one_pager": "Tóm tắt nhanh",
    "committee": "Hội đồng đầu tư",
}
SECTIONS = {
    "executive_summary": "Tóm tắt",
    "scenario": "Kịch bản",
    "valuation": "Định giá",
    "sensitivity": "Độ nhạy",
    "financial_analysis": "Phân tích tài chính",
    "risk": "Rủi ro doanh nghiệp",
    "market_risk": "Rủi ro thị trường",
    "evidence": "Thẻ bằng chứng",
    "charts": "Biểu đồ",
    "final_assessment": "Đánh giá cuối",
    "assumptions": "Giả định",
}
DEFAULT_SECTIONS = {
    "full": list(SECTIONS),
    "long_term": ["executive_summary", "scenario", "financial_analysis", "valuation", "risk", "evidence", "final_assessment"],
    "trader": ["executive_summary", "scenario", "valuation", "market_risk", "risk", "charts", "final_assessment"],
    "one_pager": ["executive_summary", "scenario", "valuation", "final_assessment"],
    "committee": list(SECTIONS),
}

st.set_page_config(page_title="VNStockAI · Kịch bản đầu tư", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:Inter,'Segoe UI',sans-serif}
.stApp{background:#F8FAFC}.block-container{padding-top:1.8rem;padding-bottom:2rem;max-width:1450px}
section[data-testid="stSidebar"]{background:#fff;border-right:1px solid #E2E8F0}
div[data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border-radius:14px!important;border:1px solid #E2E8F0!important;box-shadow:0 1px 3px #0f172a0a}
.brand{display:flex;align-items:center;gap:10px;margin:4px 0 18px}.brand-logo{height:36px;width:36px;border-radius:10px;background:#1D4ED8;color:#fff;display:grid;place-items:center;font-weight:800;font-size:19px}.brand-name{font-weight:800;font-size:18px;color:#0F172A}.brand-ver{font-size:10px;color:#94A3B8}
.page-title{font-size:28px;font-weight:800;letter-spacing:-.7px;color:#0F172A;margin:0}.muted{color:#64748B;font-size:12px}.kpi{height:100%;padding:12px 14px;border:1px solid #E2E8F0;border-radius:12px;background:#fff}.kpi-label{font-size:11px;color:#64748B}.kpi-value{font-size:21px;font-weight:800;color:#0F172A;margin:3px 0}.kpi-sub{font-size:10px;color:#64748B}
.case-title{padding:8px 11px;color:white;border-radius:9px;font-weight:700}.case-price{font-size:22px;font-weight:800;margin:7px 0}.stButton>button[kind="primary"]{background:#1D4ED8;border-color:#1D4ED8}.stButton>button[kind="primary"]:hover{background:#1E40AF;border-color:#1E40AF}
</style>""", unsafe_allow_html=True)


def api(method: str, path: str, *, json: dict | None = None, params: dict | None = None, timeout: int = 120) -> Any:
    try:
        response = requests.request(method, f"{API_BASE}{path}", json=json, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"Không kết nối được FastAPI tại {API_BASE}. Hãy khởi động backend trước. Chi tiết: {exc}") from exc
    if not response.ok:
        try:
            body = response.json()
            detail = body.get("detail", body)
        except ValueError:
            detail = response.text[:500]
        raise RuntimeError(f"Backend trả lỗi {response.status_code}: {detail}")
    return response.content if "application/pdf" in response.headers.get("content-type", "") else response.json()


def money(value: Any, digits: int = 0) -> str:
    try:
        return f"{float(value):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def percent(value: Any, digits: int = 1) -> str:
    try:
        val = float(value)
        return f"{'+' if val > 0 else ''}{money(val, digits)}%"
    except (TypeError, ValueError):
        return "—"


def base_payload(ticker: str, horizon: int, risk: str) -> dict:
    return {
        "ticker": ticker.upper().strip(),
        "horizon_months": horizon,
        "horizon_thresholds_pct": {"3": {"buy": 5, "sell": -5}, "6": {"buy": 8, "sell": -8}, "12": {"buy": 12, "sell": -10}},
        "buy_threshold_pct": 12,
        "sell_threshold_pct": -10,
        "dividend_yield_pct": 0,
        "probabilities_pct": {"bullish": 25, "base": 50, "bearish": 25},
        "sensitivity_growth_pct": [0, 10, 20],
        "sensitivity_pe": [10, 15, 20],
    }


def run_analysis(payload: dict) -> dict:
    result = api("POST", "/api/scenario/live", json=payload)
    keys = {row["key"]: row["expected_return_pct"] for row in result["scenarios"]}
    risk_profile = st.session_state.get("risk", "balanced")
    result["profile_result"] = api("POST", "/api/recommendation/profile", json={
        "ticker": result["ticker"], "risk_profile": risk_profile,
        "bullish_return_pct": keys["bullish"], "base_return_pct": keys["base"],
        "bearish_return_pct": keys["bearish"], "data_quality_score": result.get("data_confidence", {}).get("score"),
    })
    return result


<<<<<<< HEAD
def show_evidence(cards: list[dict], nested: bool = False) -> None:
    for index, card in enumerate(cards, 1):
        title = f"E{index} · {card.get('claim', 'Bằng chứng')}"
        if nested:  # Streamlit không cho expander lồng nhau
            st.markdown(f"**{title}: {money(card.get('value'), 2)} {card.get('unit', '')}**")
            st.caption(f"Công thức: {card.get('formula', '—')}  \nKỳ: {card.get('period', '—')} · Nguồn: {card.get('source', '—')}")
            continue
        with st.expander(title):
=======
def show_evidence(cards: list[dict]) -> None:
    for index, card in enumerate(cards, 1):
        with st.expander(f"E{index} · {card.get('claim', 'Bằng chứng')}"):
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
            st.metric("Giá trị tính được", f"{money(card.get('value'), 2)} {card.get('unit', '')}")
            st.write("**Công thức:**", card.get("formula", "—"))
            st.write("**Kỳ:**", card.get("period", "—"), " · **Nguồn:**", card.get("source", "—"))
            if card.get("inputs"):
                st.json(card["inputs"])


<<<<<<< HEAD
def show_claims(items: list[dict]) -> None:
    """Luận điểm/rủi ro của engine VNEquity: mỗi nhận định kèm thẻ bằng chứng (số liệu, phép tính, kỳ, nguồn)."""
    for item in items:
        with st.expander(f"{item.get('id', '')} · {item.get('claim', '')}"):
            for name, value in item.get("metrics", []):
                st.write(f"- {name}: **{value}**")
            if item.get("calc"):
                st.write("**Phép tính:**", item["calc"])
            if item.get("formula"):
                st.write("**Công thức:**", item["formula"])
            st.caption(f"Kỳ dữ liệu: {item.get('period') or '—'} · Nguồn: {item.get('source') or '—'}")


=======
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
def render_result(result: dict) -> None:
    st.markdown(f"### {result['ticker']} · Báo giá {result.get('data_status', {}).get('price_period', 'gần nhất')}")
    scenarios = {row["key"]: row for row in result["scenarios"]}
    base = scenarios["base"]
    kpis = st.columns(5)
    values = [
        ("Giá hiện tại", f"{money(result['current_price'])} ₫", result.get("data_status", {}).get("price_period", "")),
        ("Giá cơ sở 12 tháng", f"{money(base['estimated_price'])} ₫", percent(base["expected_return_pct"])),
        ("Tăng trưởng EPS cơ sở", percent(base["earnings_growth_pct"]), "Phân vị lịch sử / giả định"),
        ("P/E cơ sở", f"{money(base['target_pe'], 2)}×", "Cùng kỳ EPS lịch sử"),
        ("Độ phủ dữ liệu", f"{result.get('data_confidence', {}).get('score', '—')}/100", result.get("data_confidence", {}).get("label", "")),
    ]
    for col, (label, value, sub) in zip(kpis, values):
        col.markdown(f"<div class='kpi'><div class='kpi-label'>{label}</div><div class='kpi-value'>{value}</div><div class='kpi-sub'>{sub}</div></div>", unsafe_allow_html=True)

<<<<<<< HEAD
    if result.get("rating"):
        st.markdown(f"**Khuyến nghị mô hình: {result['rating']}** · {result.get('rating_reason', '')}")
=======
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
    if result.get("configuration_warnings"):
        for warning in result["configuration_warnings"]:
            st.warning(warning)
    if result.get("data_confidence"):
        st.caption(result["data_confidence"].get("basis", ""))

    with st.container(border=True):
        st.markdown("#### Ba kịch bản · điều chỉnh giả định")
        cols = st.columns(3)
        edited: dict[str, dict] = {}
        default_prob = result.get("probabilities_pct") or {"bullish": 25, "base": 50, "bearish": 25}
        probabilities: dict[str, int] = {}
        for col, key in zip(cols, ("bullish", "base", "bearish")):
            row = scenarios[key]
            with col:
                st.markdown(f"**{row['label']}**")
                growth_value = float(row["earnings_growth_pct"])
                growth_min, growth_max = min(-99.0, growth_value - 10), max(100.0, growth_value + 10)
                pe_value = float(row["target_pe"])
                growth = st.slider("Tăng trưởng EPS (%)", float(growth_min), float(growth_max), growth_value, 0.5, key=f"growth_{result['ticker']}_{key}")
                pe = st.slider("P/E mục tiêu (×)", 0.1, max(60.0, pe_value + 10), pe_value, 0.1, key=f"pe_{result['ticker']}_{key}")
                probabilities[key] = st.slider("Xác suất (%)", 0, 100, int(default_prob[key]), 5, key=f"prob_{result['ticker']}_{key}")
<<<<<<< HEAD
                # Chỉ gửi giá trị người dùng thực sự thay đổi (thanh trượt làm tròn theo bước)
                change = {}
                if abs(growth - growth_value) > 0.25:
                    change["earnings_growth_pct"] = growth
                if abs(pe - pe_value) > 0.05:
                    change["target_pe"] = pe
                if change:
                    edited[key] = change
=======
                edited[key] = {"earnings_growth_pct": growth, "target_pe": pe}
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
        if st.button("Cập nhật kịch bản", type="primary", key=f"recalc_{result['ticker']}"):
            if sum(probabilities.values()) != 100:
                st.error("Tổng xác suất ba kịch bản cần bằng 100%.")
            else:
                payload = dict(st.session_state.get("analysis_payload", base_payload(result["ticker"], result["horizon_months"], st.session_state.get("risk", "balanced"))))
                payload["overrides"] = edited
                payload["probabilities_pct"] = probabilities
                with st.spinner("Đang tính lại các kịch bản…"):
                    try:
                        updated = run_analysis(payload)
                        st.session_state["result"] = updated
                        st.session_state["analysis_payload"] = payload
                        st.rerun()
                    except RuntimeError as exc:
                        st.error(str(exc))

    colors = {"bullish": "#10B981", "base": "#1D4ED8", "bearish": "#EF4444"}
    cols = st.columns(3)
    for col, key in zip(cols, ("bullish", "base", "bearish")):
        row = scenarios[key]
        with col.container(border=True):
            col.markdown(f"<div class='case-title' style='background:{colors[key]}'>{row['label'].upper()} · P/E {money(row['target_pe'], 2)}×</div><div class='case-price' style='color:{colors[key]}'>{money(row['estimated_price'])} ₫</div><div class='muted'>Lợi suất hàm ý: <b>{percent(row['expected_return_pct'])}</b> · EPS forward: {money(row['projected_eps'], 2)}</div>", unsafe_allow_html=True)
            col.write(row.get("assessment", ""))
            with col.expander("Giả định & bằng chứng"):
                col.write(row.get("assumption_basis", ""))
<<<<<<< HEAD
                show_evidence(row.get("evidence", []), nested=True)
=======
                show_evidence(row.get("evidence", []))
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590

    chart_col, evidence_col = st.columns([3, 2])
    with chart_col.container(border=True):
        st.markdown("**Giá hiện tại và ước tính theo kịch bản**")
        fig = go.Figure()
        fig.add_bar(x=[scenarios[k]["estimated_price"] for k in ("bullish", "base", "bearish")], y=[scenarios[k]["label"] for k in ("bullish", "base", "bearish")], orientation="h", marker_color=[colors[k] for k in ("bullish", "base", "bearish")])
        fig.add_vline(x=result["current_price"], line_dash="dash", line_color="#475569", annotation_text="Giá hiện tại")
        fig.update_layout(height=270, margin=dict(l=5, r=10, t=5, b=5), xaxis_title="VND/cổ phiếu", yaxis_title=None, showlegend=False, paper_bgcolor="white", plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with evidence_col.container(border=True):
        st.markdown("**Đánh giá theo khẩu vị**")
        profile = result.get("profile_result", {})
        st.subheader(profile.get("assessment", "Chưa có đánh giá"))
        for reason in profile.get("reasons", []):
            st.write("•", reason)
        st.caption(profile.get("method_status", ""))
        if result.get("probability_weighted_value") is not None:
            st.metric("Giá trị kỳ vọng theo xác suất", f"{money(result['probability_weighted_value'])} ₫")

    st.markdown("**Phân vị và dấu vết phương pháp**")
    details = result.get("scenario_method", {})
    st.json(details)
    with st.expander("Độ nhạy tăng trưởng EPS × P/E"):
        grid = result.get("sensitivity_grid", {})
        cells = grid.get("cells", [])
        if cells:
<<<<<<< HEAD
            st.dataframe(pd.DataFrame({f"P/E {money(pe, 1)}×": [money(cell["estimated_price"]) for row in cells for cell in row["prices"] if cell["target_pe"] == pe] for pe in grid.get("target_pe", [])}, index=[f"Growth {money(row['growth_pct'], 1)}%" for row in cells]), use_container_width=True)
=======
            st.dataframe(pd.DataFrame({f"P/E {money(cell['target_pe'], 1)}×": [money(cell["estimated_price"]) for row in cells for cell in row["prices"] if cell["target_pe"] == pe] for pe in grid.get("target_pe", [])}, index=[f"Growth {money(row['growth_pct'], 1)}%" for row in cells]), use_container_width=True)
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
        else:
            st.info("Chưa có dữ liệu độ nhạy.")
    with st.expander("Giới hạn mô hình"):
        for limitation in result.get("limitations", []):
            st.write("•", limitation)


with st.sidebar:
    st.markdown("<div class='brand'><div class='brand-logo'>V</div><div><div class='brand-name'>VNStockAI</div><div class='brand-ver'>KỊCH BẢN ĐẦU TƯ · FASTAPI</div></div></div>", unsafe_allow_html=True)
    page = st.radio("Điều hướng", PAGES, label_visibility="collapsed")
    st.divider()
    st.caption("NHU CẦU ĐẦU TƯ")
    horizon = st.selectbox("Kỳ theo dõi", list(HORIZONS), index=2, format_func=HORIZONS.get)
    risk = st.selectbox("Khẩu vị rủi ro", list(RISKS), index=1, format_func=RISKS.get)
    st.session_state["risk"] = risk
    st.divider()
    try:
        api("GET", "/api/health", timeout=4)
        st.success("Backend FastAPI đang kết nối")
    except RuntimeError:
        st.error("Backend chưa phản hồi")
    st.caption(f"API: {API_BASE}\n\nGiá/BCTC khả dụng truy vấn theo yêu cầu. Chỉ phục vụ nghiên cứu, không phải tư vấn đầu tư.")


st.markdown("<div class='brand'><div><div class='muted'>VN EQUITY RESEARCH</div><h1 class='page-title'>Phân tích cổ phiếu</h1><div class='muted'>Ba kịch bản, giả định minh bạch và bằng chứng có thể truy xuất.</div></div></div>", unsafe_allow_html=True)
top1, top2, top3 = st.columns([4, 1, 2])
ticker = top1.text_input("Mã cổ phiếu", value=st.session_state.get("ticker", "FPT"), max_chars=10, label_visibility="collapsed", placeholder="Nhập mã: FPT, HPG, VNM…").strip().upper()
st.session_state["ticker"] = ticker
run_clicked = top2.button("Phân tích mã", type="primary", use_container_width=True)
top3.markdown(f"<div class='muted' style='padding-top:12px'>Kỳ theo dõi: <b>{HORIZONS[horizon]}</b> · {RISKS[risk]}</div>", unsafe_allow_html=True)

if run_clicked:
    if not ticker:
        st.error("Nhập mã cổ phiếu trước khi phân tích.")
    else:
        payload = base_payload(ticker, horizon, risk)
        with st.spinner(f"Đang lấy dữ liệu và phân tích {ticker}…"):
            try:
                st.session_state["result"] = run_analysis(payload)
                st.session_state["analysis_payload"] = payload
                st.session_state.pop("analysis_error", None)
            except RuntimeError as exc:
                st.session_state["analysis_error"] = str(exc)


if page == PAGES[0]:
    if st.session_state.get("analysis_error"):
        st.error(st.session_state["analysis_error"])
    result = st.session_state.get("result")
    if result:
        if result.get("ticker") != ticker or result.get("horizon_months") != horizon:
            st.info("Mã hoặc kỳ hạn đã thay đổi. Bấm **Phân tích mã** để lấy kết quả mới.")
        render_result(result)
    else:
        st.info("Nhập mã cổ phiếu và bấm **Phân tích mã** để bắt đầu.")

elif page == PAGES[1]:
    st.subheader("Luận điểm & thẻ bằng chứng")
    result = st.session_state.get("result")
    if not result:
        st.info("Hãy phân tích một mã trước.")
    else:
        for scenario in result["scenarios"]:
            with st.container(border=True):
                st.markdown(f"#### {scenario['label']} · {money(scenario['estimated_price'])} ₫ · {percent(scenario['expected_return_pct'])}")
                st.write(scenario.get("assumption_basis", ""))
                show_evidence(scenario.get("evidence", []))
<<<<<<< HEAD
        if result.get("thesis") or result.get("risks"):
            left, right = st.columns(2)
            with left:
                st.markdown("#### Luận điểm đầu tư")
                show_claims(result.get("thesis", []))
            with right:
                st.markdown("#### Rủi ro cần theo dõi")
                show_claims(result.get("risks", []))
=======
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
        st.markdown("**Nguồn và kỳ dữ liệu**")
        st.json(result.get("data_status", {}))

elif page == PAGES[2]:
    st.subheader("So sánh mã cùng nhóm")
    with st.form("peer_form"):
        industry = st.text_input("Ngành/nhóm so sánh", "Nhóm do người dùng xác định")
        peers_text = st.text_input("3–5 mã so sánh, phân cách bằng dấu phẩy", "CMG, ELC, CTR")
        submitted = st.form_submit_button("Tải dữ liệu và so sánh", type="primary")
    if submitted:
        peers = [x.strip().upper() for x in peers_text.replace(";", ",").split(",") if x.strip()]
        try:
            st.session_state["peers"] = api("POST", "/api/peers/live-compare", json={"ticker": ticker, "peer_tickers": peers, "industry": industry})
        except RuntimeError as exc:
            st.error(str(exc))
    if st.session_state.get("peers"):
        peer_result = st.session_state["peers"]
        st.dataframe(pd.DataFrame(peer_result.get("live_snapshots", [])), use_container_width=True, hide_index=True)
        st.caption(peer_result.get("percentile_note", peer_result.get("note", "")))

elif page == PAGES[3]:
    st.subheader("Sàng lọc danh sách cổ phiếu")
    st.caption("Sàng lọc qua API live cho các mã bạn nhập; đây chưa phải quét tự động toàn thị trường.")
    codes = st.text_input("Mã, từ 2 đến 8 mã", "FPT, HPG, VNM, MWG")
    if st.button("Chạy sàng lọc", type="primary"):
        symbols = list(dict.fromkeys(x.strip().upper() for x in codes.replace(";", ",").split(",") if x.strip()))
        if not 2 <= len(symbols) <= 8:
            st.error("Nhập từ 2 đến 8 mã.")
        else:
            rows = []
            progress = st.progress(0)
            for i, symbol in enumerate(symbols, 1):
                try:
                    response = api("POST", "/api/scenario/live", json=base_payload(symbol, horizon, risk))
                    base = next(row for row in response["scenarios"] if row["key"] == "base")
                    rows.append({"Mã": symbol, "Giá": response["current_price"], "Giá cơ sở": base["estimated_price"], "Lợi suất": base["expected_return_pct"], "Độ phủ": response.get("data_confidence", {}).get("score")})
                except RuntimeError as exc:
                    rows.append({"Mã": symbol, "Lỗi dữ liệu": str(exc)})
                progress.progress(i / len(symbols))
            st.session_state["screen_rows"] = rows
    if st.session_state.get("screen_rows"):
        st.dataframe(pd.DataFrame(st.session_state["screen_rows"]), use_container_width=True, hide_index=True)

elif page == PAGES[4]:
    st.subheader("Thiết kế báo cáo PDF theo mục đích")
    result = st.session_state.get("result")
    if not result:
        st.info("Chạy phân tích trước để tạo báo cáo theo đúng mã và dữ liệu vừa lấy.")
    else:
        purpose = st.radio("Mục đích báo cáo", list(PURPOSES), horizontal=True, format_func=PURPOSES.get)
        section_ids = st.multiselect("Các mục trong báo cáo", list(SECTIONS), default=DEFAULT_SECTIONS[purpose], format_func=SECTIONS.get)
        detail = st.select_slider("Mức chi tiết", ["summary", "standard", "detailed"], value="standard", format_func={"summary": "Tóm tắt", "standard": "Tiêu chuẩn", "detailed": "Chi tiết"}.get)
        include_chart = st.checkbox("Bao gồm biểu đồ", True)
        if st.button("Tạo báo cáo PDF", type="primary"):
            try:
                request = dict(st.session_state.get("analysis_payload", base_payload(ticker, horizon, risk)))
                request["report"] = {"purpose": purpose, "metric_groups": section_ids, "detail_level": detail, "include_chart": include_chart, "horizon_months": horizon}
                st.session_state["pdf_bytes"] = api("POST", "/api/scenario/live/report.pdf", json=request)
            except RuntimeError as exc:
                st.error(str(exc))
        if st.session_state.get("pdf_bytes"):
            st.download_button("Tải báo cáo PDF", st.session_state["pdf_bytes"], file_name=f"VNStockAI_{ticker}.pdf", mime="application/pdf", type="primary")

elif page == PAGES[5]:
    st.subheader("Báo cáo thường niên, BCTC và tin doanh nghiệp")
    report_ticker = st.text_input("Mã cổ phiếu cần tra cứu", ticker, key="report_ticker").strip().upper()
    cols = st.columns(3)
    if cols[0].button("Tra cứu BCTN PDF (Zenodo)"):
        try:
            st.session_state["annual"] = api("GET", "/api/reports/annual/available", params={"ticker": report_ticker})
        except RuntimeError as exc:
            st.error(str(exc))
    if cols[1].button("Lấy BCTC"):
        try:
            st.session_state["financial"] = api("GET", f"/api/reports/financial/{report_ticker}", params={"years": 5})
        except RuntimeError as exc:
            st.error(str(exc))
    if cols[2].button("Tìm tin doanh nghiệp"):
        try:
            st.session_state["news"] = api("GET", f"/api/news/company/{report_ticker}")
        except RuntimeError as exc:
            st.error(str(exc))
    annual = st.session_state.get("annual")
    if annual:
        st.caption(annual.get("warning", ""))
        for report in annual.get("years", []):
            url = f"{API_BASE}/api/reports/annual/{report_ticker}/{report['year']}/download"
            st.link_button(f"Tải BCTN {report['year']} · {report.get('file_name', '')}", url)
    financial = st.session_state.get("financial")
    if financial:
        for statement, records in financial.get("statements", {}).items():
            with st.expander(statement.replace("_", " ").title()):
                st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
    news = st.session_state.get("news")
    if news:
        for item in news.get("articles", []):
            st.markdown(f"- [{item.get('title','Tin doanh nghiệp')}]({item.get('url','#')}) · {item.get('source','')}")
        st.caption(news.get("warning", ""))

st.divider()
st.caption("VNStockAI · Công cụ nghiên cứu học tập · Không phải khuyến nghị đầu tư")
