"""VNEquity Research - giao diện phân tích kịch bản đầu tư cổ phiếu (Streamlit + Plotly).

Toàn bộ số liệu lấy qua FastAPI backend (backend/app). Chạy:
    python -m uvicorn backend.app.main:app --port 8000
    streamlit run frontend/app.py
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

import figs

API_BASE = os.getenv("VNEQUITY_API_URL", "http://127.0.0.1:8000").rstrip("/")
st.set_page_config(page_title="VNEquity Research", layout="wide", initial_sidebar_state="expanded")

# Quy ước màu dùng thống nhất trong toàn hệ thống (giống báo cáo PDF)
BRAND, POS, NEG, NEU, MUTED = "#0F2A4A", "#15803D", "#B91C1C", "#1E3A8A", "#64748B"
KEYS = ("bull", "base", "bear")
SC = {"bull": ("#15803D", "#F0FDF4"), "base": ("#1E3A8A", "#EFF6FF"), "bear": ("#B91C1C", "#FEF2F2")}
SC_NAME = {"bull": "Tích cực", "base": "Cơ sở", "bear": "Tiêu cực"}

st.markdown(f"""
<style>
.stApp {{background:#F4F6F9;}}
header[data-testid="stHeader"] {{background:transparent;}}
.block-container {{padding-top:2.4rem; padding-bottom:2rem; max-width:1380px;}}
section[data-testid="stSidebar"] {{background:{BRAND};}}
section[data-testid="stSidebar"] * {{color:#E2E8F0;}}
section[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {{display:none;}}
section[data-testid="stSidebar"] [data-testid="stRadioOption"] {{padding:9px 12px; border-radius:4px; margin:1px 0; width:100%;
    border-left:3px solid transparent;}}
section[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover {{background:rgba(255,255,255,.08);}}
section[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {{background:rgba(255,255,255,.14);
    border-left:3px solid #D4A017;}}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="group"] {{background:rgba(255,255,255,.10) !important;
    border:1px solid rgba(255,255,255,.25) !important;}}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] input {{color:#FFFFFF !important; -webkit-text-fill-color:#FFFFFF !important;}}
section[data-testid="stSidebar"] div[role="radiogroup"] label p {{font-size:.93rem; font-weight:500;}}
.wordmark {{font-weight:800; letter-spacing:.06em; font-size:1.05rem; color:#fff !important; margin-top:6px;}}
.wordsub {{font-size:.72rem; color:#94A3B8 !important; margin-bottom:22px;}}
.sidecap {{font-size:.7rem; letter-spacing:.08em; color:#94A3B8 !important; margin:14px 0 4px 0;}}
.conn {{font-size:.74rem; margin-top:4px;}} .conn i {{display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px;}}
div[data-testid="stVerticalBlockBorderWrapper"] {{background:#fff; border-radius:8px !important; border:1px solid #E2E8F0 !important;}}
.sec {{font-size:.78rem; font-weight:700; letter-spacing:.06em; color:{BRAND}; text-transform:uppercase;
    border-bottom:2px solid {BRAND}; padding-bottom:4px; margin:6px 0 10px 0;}}
.kpi {{background:#fff; border:1px solid #E2E8F0; border-left:4px solid var(--c); border-radius:6px; padding:10px 14px; height:100%;}}
.kpi .l {{color:{MUTED}; font-size:.74rem; text-transform:uppercase; letter-spacing:.04em;}}
.kpi .v {{font-size:1.4rem; font-weight:750; color:var(--c); line-height:1.35;}}
.kpi .s {{color:{MUTED}; font-size:.74rem;}}
.co {{font-size:1.5rem; font-weight:800; color:#0F172A; margin:0;}} .co span {{color:{MUTED}; font-weight:500; font-size:1.0rem;}}
.muted {{color:{MUTED}; font-size:.82rem;}}
.rating {{display:inline-block; padding:5px 18px; border-radius:4px; color:#fff; font-weight:700; letter-spacing:.05em;}}
table.cmp {{width:100%; border-collapse:collapse; font-size:.9rem;}}
table.cmp th {{color:#fff; padding:8px 10px; text-align:right; font-weight:700;}}
table.cmp th:first-child {{background:{BRAND}; text-align:left;}}
table.cmp td {{padding:6px 10px; border-bottom:1px solid #EEF2F7; text-align:right;}}
table.cmp td:first-child {{text-align:left; color:#334155;}}
table.cmp tr.grp td {{background:#F8FAFC; font-weight:700; color:{BRAND}; font-size:.78rem; text-transform:uppercase; letter-spacing:.04em;}}
table.cmp tr.key td {{font-weight:700; font-size:.98rem;}}
.colhead {{color:#fff; font-weight:700; padding:6px 10px; border-radius:4px; text-align:center; margin-bottom:4px;}}
.claim {{padding:8px 10px; border-left:3px solid var(--c); background:#FBFCFE; margin:6px 0; font-size:.92rem;}}
.claim b {{color:var(--c); margin-right:6px; font-size:.78rem;}}
.preset {{border:1px solid #E2E8F0; border-top:3px solid {BRAND}; border-radius:6px; padding:10px 12px; background:#fff; height:100%;}}
.news {{padding:9px 0; border-bottom:1px solid #EEF2F7;}} .news a {{color:{NEU}; font-weight:600; text-decoration:none;}}
</style>""", unsafe_allow_html=True)


# ============================================================ GỌI API
def api(method: str, path: str, *, json_body: dict | None = None, params: dict | None = None, timeout: int = 180) -> Any:
    try:
        r = requests.request(method, f"{API_BASE}{path}", json=json_body, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"Không kết nối được máy chủ dữ liệu tại {API_BASE}. Hãy khởi động backend trước.") from exc
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text[:400]
        raise RuntimeError(f"Máy chủ trả lỗi {r.status_code}: {detail}")
    return r.content if "application/pdf" in r.headers.get("content-type", "") else r.json()


@st.cache_data(show_spinner=False, ttl=3600)
def get_options() -> dict:
    return api("GET", "/api/engine/options", timeout=30)


@st.cache_data(show_spinner=False, ttl=600, max_entries=200)
def get_analysis(body_json: str) -> dict:
    return api("POST", "/api/engine/analyze", json_body=json.loads(body_json))


@st.cache_data(show_spinner=False, ttl=3600, max_entries=50)
def get_financials(ticker: str) -> dict:
    return api("GET", f"/api/engine/financials/{ticker}", params={"years": 20})


def backend_online() -> bool:
    try:
        api("GET", "/api/health", timeout=4)
        return True
    except RuntimeError:
        return False


# ============================================================ ĐỊNH DẠNG SỐ (kiểu Việt Nam)
def _bad(x) -> bool:
    try:
        return x is None or not math.isfinite(float(x))
    except (TypeError, ValueError):
        return True


def num(x, d: int = 0) -> str:
    return "-" if _bad(x) else f"{float(x):,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x, d: int = 1, sign: bool = False) -> str:
    return "-" if _bad(x) else f"{float(x) * 100:{'+' if sign else ''},.{d}f}%".replace(",", "§").replace(".", ",").replace("§", ".")


def bil(x, d: int = 0) -> str:
    return "-" if _bad(x) else num(float(x) / 1e9, d)


def times(x, d: int = 1) -> str:
    return "-" if _bad(x) else num(x, d) + "x"


# ============================================================ THÀNH PHẦN GIAO DIỆN
def sec(title):
    st.markdown(f"<div class='sec'>{title}</div>", unsafe_allow_html=True)


def kpi(col, label, value, sub="", color=NEU):
    col.markdown(f"<div class='kpi' style='--c:{color}'><div class='l'>{label}</div><div class='v'>{value}</div>"
                 f"<div class='s'>{sub}</div></div>", unsafe_allow_html=True)


def sign_color(x):
    return MUTED if _bad(x) else (POS if x > 0 else (NEG if x < 0 else MUTED))


def evidence_card(e: dict):
    st.markdown(f"**{e['id']}. {e['claim']}**")
    if e.get("metrics"):
        st.dataframe(pd.DataFrame(e["metrics"], columns=["Chỉ số", "Giá trị"]), hide_index=True, width="stretch")
    for k, f in (("Kỳ dữ liệu", "period"), ("Nguồn", "source"), ("Công thức", "formula")):
        if e.get(f):
            st.markdown(f"<div class='muted'><b>{k}:</b> {e[f]}</div>", unsafe_allow_html=True)
    if e.get("calc"):
        st.markdown("<div class='muted'><b>Phép tính:</b></div>", unsafe_allow_html=True)
        st.code(e["calc"], language=None)


def claim_row(e: dict, color: str):
    c1, c2 = st.columns([7, 2])
    c1.markdown(f"<div class='claim' style='--c:{color}'><b>{e['id']}</b>{e['claim']}</div>", unsafe_allow_html=True)
    with c2.popover("Chi tiết", width="stretch", help=f"Xem bằng chứng {e['id']}: chỉ số, kỳ dữ liệu, nguồn, phép tính"):
        evidence_card(e)


# ============================================================ THANH BÊN
PAGES = ["Kịch bản đầu tư", "Luận điểm và bằng chứng", "Biểu đồ so sánh", "Sàng lọc cơ hội", "Xuất báo cáo PDF",
         "Báo cáo và tin doanh nghiệp"]
online = backend_online()
with st.sidebar:
    st.markdown("<div class='wordmark'>VNEQUITY RESEARCH</div><div class='wordsub'>Phân tích kịch bản đầu tư cổ phiếu</div>",
                unsafe_allow_html=True)
    page = st.radio("Điều hướng", PAGES, label_visibility="collapsed")
    if online:
        OPT = get_options()
    else:
        OPT = {"tickers": ["FPT"], "horizon": {"short": "Ngắn hạn (< 3 tháng)", "medium": "Trung hạn (3-12 tháng)",
                                              "long": "Dài hạn (> 1 năm)"},
               "risk": {"conservative": "Thận trọng", "balanced": "Cân bằng", "aggressive": "Chấp nhận rủi ro"}}
    st.markdown("<div class='sidecap'>NHU CẦU ĐẦU TƯ</div>", unsafe_allow_html=True)
    horizon = st.selectbox("Kỳ hạn", list(OPT["horizon"]), index=1, format_func=OPT["horizon"].get)
    risk = st.selectbox("Khẩu vị rủi ro", list(OPT["risk"]), index=1, format_func=OPT["risk"].get)
    offline = st.toggle("Chế độ offline", value=False, help="Chỉ dùng dữ liệu giá đã lưu (giá mẫu: FPT, VN-Index).")
    st.markdown("<div class='sidecap'>NGUỒN DỮ LIỆU</div><div class='wordsub' style='margin-bottom:8px'>Giá: VNDirect, TCBS, vnstock"
                "<br>BCTC 2011-2025: HSX, HNX<br>Tin tức: CafeF, VnExpress</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='conn'><i style='background:{'#22C55E' if online else '#F59E0B'}'></i>"
                f"{'Máy chủ dữ liệu đang kết nối' if online else 'Máy chủ dữ liệu chưa phản hồi'}</div>", unsafe_allow_html=True)

if not online:
    st.error(f"Chưa kết nối được máy chủ dữ liệu tại {API_BASE}.")
    st.code("python -m uvicorn backend.app.main:app --port 8000", language=None)
    st.caption("Chạy lệnh trên ở thư mục gốc dự án (terminal khác), rồi tải lại trang. "
               "Có thể đặt biến VNEQUITY_API_URL nếu máy chủ ở địa chỉ khác.")
    st.stop()

# ============================================================ CHỌN MÃ
TK = OPT["tickers"]
ticker = st.selectbox("Mã cổ phiếu", TK, index=TK.index("FPT") if "FPT" in TK else 0, label_visibility="collapsed",
                      placeholder="Nhập mã cổ phiếu, ví dụ FPT, HPG, VCB")


def sk(k, f):
    return f"{ticker}_{horizon}_{k}_{f}"


def slider_defaults(d: dict) -> dict:
    return {k: {"g": float(round(d[k]["eps_growth"] * 100, 1)), "pe": float(round(d[k]["exit_pe"], 1)),
                "p": int(round(d[k]["probability"] * 100)), "pay": int(round(d[k]["payout"] * 100))} for k in KEYS}


def scenario_inputs(d: dict) -> dict:
    """Chỉ giả định người dùng thực sự thay đổi mới được gửi đi (tránh sai lệch do làm tròn thanh trượt)."""
    sd = slider_defaults(d)
    conv = {"g": ("eps_growth", 100), "pe": ("exit_pe", 1), "p": ("probability", 100), "pay": ("payout", 100)}
    ov = {}
    for k in KEYS:
        o = {fld: st.session_state[sk(k, f)] / div for f, (fld, div) in conv.items()
             if st.session_state.get(sk(k, f)) is not None and abs(st.session_state[sk(k, f)] - sd[k][f]) > 1e-9}
        if o:
            ov[k] = o
    return ov


def analysis_body(**extra) -> dict:
    return {"ticker": ticker, "horizon": horizon, "risk": risk, "offline": offline, **extra}


R = DEF = None
if page not in ("Biểu đồ so sánh", "Sàng lọc cơ hội", "Báo cáo và tin doanh nghiệp"):
    with st.spinner(f"Đang tải dữ liệu và phân tích {ticker}..."):
        try:
            base_res = get_analysis(json.dumps(analysis_body(), sort_keys=True))
            DEF = base_res["defaults"]
            years = st.session_state.get(sk("all", "years")) or base_res["default_years"]
            ov = scenario_inputs(DEF)
            R = base_res if (not ov and years == base_res["scen"]["years"]) else \
                get_analysis(json.dumps(analysis_body(overrides=ov, years=years), sort_keys=True))
        except RuntimeError as e:
            st.error(f"Không phân tích được {ticker}: {e}")
            st.caption("Kiểm tra kết nối Internet (cần để tải giá), hoặc bật chế độ offline và chọn FPT.")
            st.stop()

if R is not None:
    ss, mm, pf = R["scen"], R["multiples"], R["profile"]
    S = {s["key"]: s for s in ss["items"]}
    with st.container(border=True):
        h1, h2, h3 = st.columns([5, 3, 2])
        h1.markdown(f"<p class='co'>{R['ticker']} <span>| {pf['name']}</span></p>"
                    f"<div class='muted'>{pf['exchange']} | {pf['icb1']} | {pf['icb3']} | "
                    f"dữ liệu giá đến {pd.Timestamp(R['price_date']):%d/%m/%Y}</div>", unsafe_allow_html=True)
        chg = R["price_change"]
        h2.markdown(f"<div style='font-size:1.45rem;font-weight:800'>{num(ss['price'])} đ "
                    f"<span style='font-size:.9rem;color:{sign_color(chg)}'>{pct(chg, 2, sign=True)}</span></div>"
                    f"<div class='muted'>P/E {times(mm['pe'])} | P/B {times(mm['pb'])} | Vốn hoá {bil(mm['market_cap'])} tỷ</div>",
                    unsafe_allow_html=True)
        h3.markdown(f"<div style='text-align:right'><div class='muted'>Khuyến nghị</div>"
                    f"<span class='rating' style='background:{R['rating_color']}'>{R['rating']}</span></div>",
                    unsafe_allow_html=True)
    for w in R["warnings"]:
        st.caption(f"Lưu ý: {w}")


def compare_table(ss: dict) -> str:
    items = ss["items"]
    head = "".join(f"<th style='background:{SC[s['key']][0]}'>{s['name'].upper()}</th>" for s in items)

    def row(label, vals, cls=""):
        tds = "".join(f"<td style='background:{SC[s['key']][1]}'>{v}</td>" if cls == "key" else f"<td>{v}</td>"
                      for s, v in zip(items, vals))
        return f"<tr class='{cls}'><td>{label}</td>{tds}</tr>"

    def colored(x, text):
        return f"<span style='color:{sign_color(x)}'>{text}</span>"

    body = ["<tr class='grp'><td colspan='4'>Giả định</td></tr>",
            row("Tăng trưởng EPS mỗi năm", [pct(s["eps_growth"]) for s in items]),
            row("P/E mục tiêu cuối kỳ", [times(s["exit_pe"]) for s in items]),
            row("Tỷ lệ chi trả cổ tức", [pct(s["payout"]) for s in items]),
            row("Xác suất", [pct(s["probability"], 0) for s in items]),
            f"<tr class='grp'><td colspan='4'>Kết quả sau {ss['years']} năm</td></tr>",
            row(f"EPS FY{ss['fy0'] + ss['growth_years']} (đ)", [num(s["eps_end"]) for s in items]),
            row("Giá mục tiêu (đ)", [num(s["target_price"]) for s in items], "key"),
            row("Cổ tức nhận trong kỳ (đ)", [num(s["dividends"]) for s in items]),
            row("Tỷ suất sinh lời tổng", [colored(s["total_return"], pct(s["total_return"], 1, sign=True)) for s in items], "key"),
            row("Tỷ suất sinh lời mỗi năm", [colored(s["annual_return"], pct(s["annual_return"], 1, sign=True)) for s in items]),
            row("Đối chiếu DCF cùng tăng trưởng (đ)", [num(s["dcf_value"]) for s in items])]
    return f"<table class='cmp'><tr><th>Chỉ tiêu</th>{head}</tr>{''.join(body)}</table>"


def evidence_of(kind: str) -> list:
    return [e for e in R["evidence"] if e["kind"] == kind]


# ============================================================ TRANG: KỊCH BẢN ĐẦU TƯ
if page == "Kịch bản đầu tư":
    SD = slider_defaults(DEF)
    c = st.columns(5)
    rr = ss["risk_reward"]
    rr_txt = "> 10" if (rr is None or rr > 10) else num(rr, 2)
    kpi(c[0], "Giá trị kỳ vọng", f"{num(ss['expected_price'])} đ", "Bình quân gia quyền theo xác suất", NEU)
    kpi(c[1], f"Sinh lời kỳ vọng {ss['years']} năm", pct(ss["expected_return"], 1, sign=True), "Gồm cổ tức tiền mặt",
        sign_color(ss["expected_return"]))
    kpi(c[2], "Sinh lời kỳ vọng mỗi năm", pct(ss["expected_annual"], 1, sign=True), "Căn cứ đưa ra khuyến nghị",
        sign_color(ss["expected_annual"]))
    kpi(c[3], "Lợi nhuận / rủi ro", f"{rr_txt} lần", "Tích cực so với tiêu cực", NEU)
    kpi(c[4], "Xác suất thua lỗ", pct(ss["prob_loss"], 0), f"Khoảng giá {num(S['bear']['target_price'])} - "
                                                         f"{num(S['bull']['target_price'])}", NEG if ss["prob_loss"] > 0 else POS)
    st.write("")

    left, right = st.columns([11, 9])
    with left:
        with st.container(border=True):
            sec("So sánh ba kịch bản")
            st.markdown(compare_table(ss), unsafe_allow_html=True)
            st.markdown(f"<div class='muted' style='margin-top:8px'><b>Khuyến nghị {R['rating']}:</b> {R['rating_reason']}.</div>",
                        unsafe_allow_html=True)
    with right:
        with st.container(border=True):
            sec("Điều chỉnh giả định")
            st.segmented_control("Kỳ hạn đầu tư", [1, 2, 3, 5], default=ss["years"], key=sk("all", "years"),
                                 format_func=lambda y: f"{y} năm")
            if st.button("Khôi phục giả định mặc định"):
                for k in list(st.session_state):
                    if k.startswith(f"{ticker}_{horizon}_"):
                        del st.session_state[k]
                st.rerun()
            hc = st.columns(3)
            for col, k in zip(hc, KEYS):
                col.markdown(f"<div class='colhead' style='background:{SC[k][0]}'>{SC_NAME[k]}</div>", unsafe_allow_html=True)
            for label, f, lo, hi, step in (("Tăng trưởng EPS (%/năm)", "g", -30.0, 60.0, 0.1),
                                           ("P/E mục tiêu (lần)", "pe", 3.0, 40.0, 0.1),
                                           ("Xác suất (%)", "p", 0, 100, 5),
                                           ("Tỷ lệ chi trả cổ tức (%)", "pay", 0, 100, 1)):
                st.markdown(f"<div class='muted' style='margin-top:6px'><b>{label}</b></div>", unsafe_allow_html=True)
                cols = st.columns(3)
                for col, k in zip(cols, KEYS):
                    v = min(max(SD[k][f], lo), hi)
                    col.slider(f"{label} - {k}", lo, hi, v, step, key=sk(k, f), label_visibility="collapsed",
                               format="%.1f" if isinstance(step, float) else "%d")
            st.markdown("<div class='muted'>Bảng bên trái và các biểu đồ bên dưới được tính lại ngay khi kéo thanh trượt. "
                        "Xác suất được tự chuẩn hoá về tổng 100%.</div>", unsafe_allow_html=True)

    with st.container(border=True):
        sec("Biểu đồ kịch bản")
        t1, t2, t3, t4 = st.tabs(["Đường giá và ba kịch bản", "Sinh lời theo kịch bản", "Ma trận độ nhạy", "Cơ sở giả định mặc định"])
        with t1:
            st.plotly_chart(figs.scenario_fan(R["prices"], ss), width="stretch", config={"displayModeBar": False})
        with t2:
            st.plotly_chart(figs.scenario_returns(ss), width="stretch", config={"displayModeBar": False})
        with t3:
            st.caption("Tỷ suất sinh lời tổng khi thay đổi tăng trưởng EPS (hàng) và P/E mục tiêu (cột). Ô viền đậm là kịch bản cơ sở.")
            st.plotly_chart(figs.sensitivity(ss), width="stretch", config={"displayModeBar": False})
        with t4:
            for e in evidence_of("scenario"):
                claim_row(e, NEU)

# ============================================================ TRANG: LUẬN ĐIỂM VÀ BẰNG CHỨNG
elif page == "Luận điểm và bằng chứng":
    a, b = st.columns(2)
    with a:
        with st.container(border=True):
            sec("Luận điểm đầu tư")
            for e in evidence_of("thesis"):
                claim_row(e, POS)
    with b:
        with st.container(border=True):
            sec("Rủi ro cần theo dõi")
            for e in evidence_of("risk"):
                claim_row(e, NEG)
        with st.container(border=True):
            sec("Khuyến nghị")
            for e in evidence_of("info"):
                claim_row(e, BRAND)
        with st.container(border=True):
            sec(f"Đánh giá theo khẩu vị {OPT['risk'][risk].lower()}")
            try:
                prof = api("POST", "/api/recommendation/profile", json_body={
                    "ticker": ticker, "risk_profile": risk, "bullish_return_pct": S["bull"]["total_return"] * 100,
                    "base_return_pct": S["base"]["total_return"] * 100, "bearish_return_pct": S["bear"]["total_return"] * 100})
                ok = "Phù hợp" in prof["assessment"]
                st.markdown(f"<div class='claim' style='--c:{POS if ok else NEG}'>{prof['assessment']}</div>", unsafe_allow_html=True)
                for reason in prof.get("reasons", []):
                    st.markdown(f"<div class='muted'>{reason}</div>", unsafe_allow_html=True)
            except RuntimeError as exc:
                st.caption(str(exc))
    c1, c2 = st.columns([3, 2])
    with c1.container(border=True):
        sec("Diễn biến giá và đường trung bình")
        st.plotly_chart(figs.price_chart(R["prices"], ticker=R["ticker"]), width="stretch", config={"displayModeBar": False})
    with c2.container(border=True):
        sec("Điểm đánh giá đa yếu tố")
        st.plotly_chart(figs.score_radar(R["composite"]), width="stretch", config={"displayModeBar": False})
    with st.container(border=True):
        sec("Nguồn dữ liệu")
        st.dataframe(pd.DataFrame(list(R["data_sources"].items()), columns=["Hạng mục", "Nguồn"]), hide_index=True, width="stretch")

# ============================================================ TRANG: BIỂU ĐỒ SO SÁNH
elif page == "Biểu đồ so sánh":
    LABELS = {"revenue": "Doanh thu", "gross_profit": "Lợi nhuận gộp", "ebitda": "EBITDA", "npat_parent": "LNST cổ đông mẹ",
              "cfo": "Dòng tiền HĐKD", "total_assets": "Tổng tài sản", "equity": "Vốn chủ sở hữu",
              "gross_margin": "Biên LN gộp", "ebitda_margin": "Biên EBITDA", "net_margin": "Biên LN ròng",
              "roe": "ROE", "roa": "ROA", "revenue_growth": "Tăng trưởng doanh thu", "npat_growth": "Tăng trưởng LNST"}
    PCT = {"gross_margin", "ebitda_margin", "net_margin", "roe", "roa", "revenue_growth", "npat_growth"}
    with st.container(border=True):
        sec("Thiết lập biểu đồ")
        c1, c2 = st.columns(2)
        sel = c1.multiselect("Doanh nghiệp", TK, default=[t for t in (ticker, "CMG") if t in TK][:2] or TK[:2], max_selections=4)
        mets = c2.multiselect("Chỉ tiêu", list(LABELS), default=["gross_margin", "revenue", "ebitda"], format_func=LABELS.get)
        c3, c4 = st.columns(2)
        rng = c3.segmented_control("Khoảng thời gian", ["3 năm", "5 năm", "10 năm", "Toàn bộ"], default="10 năm")
        mode = c4.segmented_control("Cách hiển thị", ["Gộp một biểu đồ", "Tách từng doanh nghiệp"], default="Tách từng doanh nghiệp")
        st.caption("Cột: giá trị (tỷ đồng, trục trái). Đường: tỷ lệ phần trăm (trục phải). Dữ liệu năm tài chính.")
    n = {"3 năm": 3, "5 năm": 5, "10 năm": 10, "Toàn bộ": 99}[rng or "10 năm"]
    data, names = {}, {}
    for t in sel:
        try:
            f = get_financials(t)
        except RuntimeError:
            continue
        data[t] = pd.DataFrame(f["data"], index=f["years"]).tail(n)
        names[t] = f["name"]
    if not data or not mets:
        st.info("Chọn ít nhất một doanh nghiệp và một chỉ tiêu.")
    elif mode == "Gộp một biểu đồ":
        with st.container(border=True):
            st.plotly_chart(figs.multi_metric(data, mets, LABELS, PCT, " so với ".join(data)), width="stretch")
    else:
        for t, df in data.items():
            with st.container(border=True):
                st.plotly_chart(figs.multi_metric({t: df}, mets, LABELS, PCT, f"{t} | {names[t]}"), width="stretch")
    if data:
        with st.expander("Bảng số liệu"):
            for t, df in data.items():
                show = df[[m for m in mets if m in df]].copy()
                for m in show:
                    show[m] = show[m].map(lambda x, m=m: pct(x) if m in PCT else bil(x))
                st.markdown(f"**{t}**")
                st.dataframe(show.rename(columns=LABELS).T, width="stretch")

    with st.container(border=True):
        sec("Định giá so với nhóm cùng ngành")
        c1, c2, c3 = st.columns([2, 3, 1])
        industry = c1.text_input("Nhóm ngành", "Cùng nhóm ICB")
        peers_text = c2.text_input("3 đến 5 mã so sánh, phân cách bằng dấu phẩy", "CMG, ELC, SAM")
        c3.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if c3.button("So sánh", type="primary", width="stretch"):
            peers = [x.strip().upper() for x in peers_text.replace(";", ",").split(",") if x.strip()]
            try:
                st.session_state["peers"] = api("POST", "/api/peers/live-compare",
                                                 json_body={"ticker": ticker, "peer_tickers": peers, "industry": industry})
            except RuntimeError as exc:
                st.error(str(exc))
        pr = st.session_state.get("peers")
        if pr:
            snap = pd.DataFrame(pr.get("live_snapshots", []))
            if not snap.empty:
                show = pd.DataFrame({"Mã": snap["ticker"], "Giá (đ)": snap["current_price"].map(num),
                                     "EPS (đ)": snap["eps"].map(num), "P/E": snap["pe"].map(times),
                                     "Kỳ giá": snap["price_period"], "Kỳ EPS": snap["eps_period"]})
                st.dataframe(show, hide_index=True, width="stretch")
            if pr.get("target_price_at_peer_median_pe") is not None:
                st.markdown(f"<div class='muted'>Giá hàm ý theo EPS hiện tại × P/E trung vị nhóm: "
                            f"<b>{num(pr['target_price_at_peer_median_pe'])} đ</b> "
                            f"({pct(pr['implied_return_at_peer_median_pe_pct'] / 100, 1, sign=True)})</div>", unsafe_allow_html=True)
            st.caption(pr.get("note", ""))

# ============================================================ TRANG: SÀNG LỌC
elif page == "Sàng lọc cơ hội":
    with st.container(border=True):
        sec("Tiêu chí sàng lọc")
        c1, c2, c3, c4 = st.columns(4)
        minrev = c1.number_input("Doanh thu tối thiểu (tỷ đồng)", 0, 100000, 1000, 100)
        exch = c2.selectbox("Sàn", ["Tất cả", "HSX", "HNX"])
        top = c3.number_input("Số mã hiển thị", 5, 100, 30, 5)
        with_px = c4.toggle("Bổ sung P/E, PEG (cần Internet)")
        go_ = st.button("Chạy sàng lọc", type="primary")
    body = {"min_revenue_bil": minrev, "exchange": None if exch == "Tất cả" else exch, "top": int(top),
            "with_prices": with_px, "offline": offline}
    if go_:
        with st.spinner("Đang quét toàn bộ doanh nghiệp (lần đầu khoảng 1 phút)..."):
            try:
                st.session_state["screen"] = (body, api("POST", "/api/engine/screen", json_body=body, timeout=600))
                st.session_state.pop("screen_pdf", None)
            except RuntimeError as exc:
                st.error(str(exc))
    if "screen" in st.session_state:
        sbody, res_ = st.session_state["screen"]
        df = pd.DataFrame(res_["rows"], columns=res_["columns"])
        df.index = df.index + 1
        with st.container(border=True):
            sec(f"Kết quả - {len(df)} / {res_['total']} doanh nghiệp đạt tiêu chí")
            st.dataframe(df, width="stretch", column_config={
                "ROE": st.column_config.NumberColumn(format="percent"), "CAGR LN 3N": st.column_config.NumberColumn(format="percent"),
                "Biên LN ròng": st.column_config.NumberColumn(format="percent"),
                "Điểm chất lượng": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f")})
            b1, b2, b3 = st.columns(3)
            if b1.button("Tạo PDF danh sách"):
                with st.spinner("Đang dựng PDF..."):
                    try:
                        st.session_state["screen_pdf"] = api("POST", "/api/engine/screen.pdf", json_body=sbody, timeout=600)
                    except RuntimeError as exc:
                        st.error(str(exc))
            if st.session_state.get("screen_pdf"):
                b2.download_button("Tải PDF danh sách", st.session_state["screen_pdf"], file_name="SangLocCoHoi.pdf",
                                   mime="application/pdf", type="primary")
            b3.download_button("Tải CSV", df.to_csv().encode("utf-8-sig"), file_name="sang_loc_co_hoi.csv")

# ============================================================ TRANG: XUẤT PDF
elif page == "Xuất báo cáo PDF":
    PP = OPT["purposes"]
    with st.container(border=True):
        sec("Bước 1 - Chọn mục đích báo cáo")
        keys = list(PP)
        pc = st.columns(len(keys))
        for col, k in zip(pc, keys):
            col.markdown(f"<div class='preset'><b>{PP[k]['label']}</b><div class='muted'>{PP[k]['desc']}</div></div>",
                         unsafe_allow_html=True)
        purpose = st.radio("Mục đích", keys, format_func=lambda k: PP[k]["label"], horizontal=True, label_visibility="collapsed")
    base = PP[purpose]["options"]
    with st.container(border=True):
        sec("Bước 2 - Tuỳ chỉnh nội dung")
        c1, c2 = st.columns(2)
        sections = c1.multiselect("Các mục trong báo cáo", list(OPT["sections"]), default=list(base["sections"]),
                                  format_func=OPT["sections"].get, key=f"sec_{purpose}")
        charts_ = c2.multiselect("Biểu đồ", list(OPT["charts"]), default=list(base["charts"]), format_func=OPT["charts"].get,
                                 key=f"ch_{purpose}")
        c3, c4, c5 = st.columns(3)
        groups = c3.multiselect("Nhóm chỉ số tài chính", list(OPT["metric_groups"]), default=list(base["metric_groups"]),
                                format_func=OPT["metric_groups"].get, key=f"mg_{purpose}")
        detail = c4.select_slider("Mức chi tiết", list(OPT["detail"]), value=base["detail"], format_func=OPT["detail"].get,
                                  key=f"dt_{purpose}")
        yrs = c5.slider("Số năm tài chính hiển thị", 3, 10, int(base["years"]), key=f"yr_{purpose}")
    with st.container(border=True):
        sec("Bước 3 - Tạo và tải báo cáo")
        st.caption(f"Báo cáo dùng đúng giả định kịch bản hiện tại: kỳ hạn {ss['years']} năm, "
                   f"giá trị kỳ vọng {num(ss['expected_price'])} đ.")
        if st.button("Tạo báo cáo PDF", type="primary"):
            body = analysis_body(overrides=scenario_inputs(DEF), years=ss["years"],
                                 options={"purpose": purpose, "sections": sections, "charts": charts_,
                                          "metric_groups": groups, "detail": detail, "years": yrs})
            with st.spinner("Đang dựng báo cáo..."):
                try:
                    st.session_state["pdf"] = (f"{ticker}_BaoCaoPhanTich_{purpose}.pdf",
                                               api("POST", "/api/engine/report.pdf", json_body=body, timeout=300))
                except RuntimeError as exc:
                    st.error(str(exc))
        if st.session_state.get("pdf"):
            name, data = st.session_state["pdf"]
            st.success(f"Đã tạo {name}")
            st.download_button("Tải báo cáo PDF", data, file_name=name, mime="application/pdf", type="primary")

# ============================================================ TRANG: BÁO CÁO VÀ TIN DOANH NGHIỆP
elif page == "Báo cáo và tin doanh nghiệp":
    with st.container(border=True):
        sec("Tra cứu tài liệu doanh nghiệp")
        c1, c2, c3 = st.columns([1, 2, 3])
        rt = c1.text_input("Mã cổ phiếu", ticker, key="report_ticker").strip().upper()
        cname = c2.text_input("Tên doanh nghiệp (lọc tin, không bắt buộc)", "")
        site = c3.text_input("Trang tin chính thức (không bắt buộc)", "", placeholder="https://cong-ty.vn/tin-tuc")
        b1, b2, b3 = st.columns(3)
        if b1.button("Báo cáo thường niên", width="stretch"):
            try:
                st.session_state["annual"] = (rt, api("GET", "/api/reports/annual/available", params={"ticker": rt}))
            except RuntimeError as exc:
                st.error(str(exc))
        if b2.button("Báo cáo tài chính", width="stretch"):
            try:
                st.session_state["financial"] = (rt, api("GET", f"/api/reports/financial/{rt}", params={"years": 5}))
            except RuntimeError as exc:
                st.error(str(exc))
        if b3.button("Tin doanh nghiệp", width="stretch"):
            try:
                st.session_state["news"] = (rt, api("GET", f"/api/news/company/{rt}",
                                                    params={"company_name": cname, "company_website": site}))
            except RuntimeError as exc:
                st.error(str(exc))

    if st.session_state.get("annual"):
        code, annual = st.session_state["annual"]
        with st.container(border=True):
            sec(f"Báo cáo thường niên - {code}")
            years_ = annual.get("years", [])
            if not years_:
                st.caption("Không có báo cáo thường niên trong danh mục.")
            for rep in years_:
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"<div class='muted'><b>{rep['year']}</b> | {rep.get('file_name', '')} | {rep.get('size_mb', '')} MB</div>",
                            unsafe_allow_html=True)
                c2.link_button("Tải PDF", f"{API_BASE}/api/reports/annual/{code}/{rep['year']}/download", width="stretch")
            st.caption(annual.get("warning", ""))
    if st.session_state.get("financial"):
        code, fin = st.session_state["financial"]
        with st.container(border=True):
            sec(f"Báo cáo tài chính - {code}")
            for statement, records in fin.get("statements", {}).items():
                with st.expander(f"{statement.replace('_', ' ').capitalize()} ({len(records)} dòng)"):
                    st.dataframe(pd.DataFrame(records), hide_index=True, width="stretch")
            st.caption(fin.get("coverage_note", ""))
    if st.session_state.get("news"):
        code, news = st.session_state["news"]
        with st.container(border=True):
            sec(f"Tin doanh nghiệp - {code}")
            arts = news.get("articles", [])
            if not arts:
                st.caption("Chưa tìm thấy tin phù hợp.")
            for item in arts:
                st.markdown(f"<div class='news'><div class='muted'>{item.get('source', '')} | {item.get('published_at', '') or ''}</div>"
                            f"<a href='{item.get('url', '#')}' target='_blank'>{item.get('title', '')}</a>"
                            f"<div class='muted'>{(item.get('summary') or '')[:260]}</div></div>", unsafe_allow_html=True)
            st.caption(news.get("warning", ""))

st.markdown("<div class='muted' style='text-align:center;margin-top:18px'>VNEquity Research | Công cụ nghiên cứu, "
            "không phải lời khuyên đầu tư</div>", unsafe_allow_html=True)