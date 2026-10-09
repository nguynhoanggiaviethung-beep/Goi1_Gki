"""Bộ điều phối: thu thập dữ liệu -> phân tích -> kết quả có cấu trúc cho báo cáo/giao diện."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from .analysis import fundamental as fa
from .analysis import scenarios as scn
from .analysis.evidence import EvidenceBook
from .analysis import peers as pa
from .analysis import scoring as sc
from .analysis import technical as ta
from .analysis import valuation as va
from .config import RISK_LABEL, UserProfile, ValuationParams
from .data import company, financials, news, prices
from .report import fmt as F


@dataclass
class AnalysisResult:
    ticker: str
    profile: company.CompanyProfile
    created_at: datetime
    fin: pd.DataFrame
    ratios: pd.DataFrame
    prices: pd.DataFrame
    index_prices: pd.DataFrame | None
    tech: dict
    val: dict
    fscore: int
    fscore_tests: list
    altman: tuple
    fund_score: float
    fund_notes: list
    peers: pd.DataFrame
    peer_level: str
    peer_summary: dict
    news: dict
    composite: dict
    rating: str
    rating_reason: str
    user: UserProfile
    data_sources: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    thesis: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    evidence: object = None          # EvidenceBook
    scen: object = None              # ScenarioSet
    base_rating: str = ""            # khuyến nghị theo phương pháp định giá nội tại (tham chiếu)


def analyze(ticker: str, user: UserProfile | None = None, vparams: ValuationParams | None = None,
            offline: bool = False, target_pe: float | None = None, market_pe: float = 13.0,
            shares_override: float | None = None, log=print) -> AnalysisResult:
    ticker = ticker.upper().strip()
    user = user or UserProfile()
    vparams = vparams or ValuationParams()
    warnings: list[str] = []

    log(f"[1/6] Đọc BCTC & hồ sơ doanh nghiệp {ticker} ...")
    fin = financials.get_financials(ticker)
    if fin.empty:
        raise ValueError(f"Không có đủ dữ liệu BCTC chuẩn hoá cho mã {ticker} (mã chưa có trong bộ dữ liệu hoặc thuộc nhóm "
                         f"công ty chứng khoán/bảo hiểm có cấu trúc BCTC đặc thù chưa được hỗ trợ). Dùng 'python main.py list' để xem danh sách.")
    prof = company.get_profile(ticker)
    if shares_override:
        prof.shares, prof.shares_source = float(shares_override), "Người dùng nhập"
    if not prof.exchange:
        prof.exchange = fin.attrs.get("exchange", "")
    if prof.is_financial:
        warnings.append("Doanh nghiệp thuộc nhóm tài chính/ngân hàng: dùng bộ chỉ số chuyên ngành (NIM, CIR, LDR, chi phí tín dụng); "
                        "các chỉ tiêu biên gộp, thanh khoản, EV/EBITDA, Altman Z không áp dụng - nên ưu tiên P/B và ROE.")
    ratios = fa.compute_ratios(fin)

    log("[2/6] Lấy dữ liệu giá cổ phiếu & VN-Index ...")
    px = prices.get_prices(ticker, offline=offline)
    try:
        idx = prices.get_prices("VNINDEX", offline=offline)
    except Exception as e:  # noqa: BLE001
        idx = None
        warnings.append(f"Không lấy được VN-Index: {e}")
    if px.attrs.get("errors"):
        warnings.append(f"Không kết nối được nguồn giá trực tuyến khi tạo báo cáo; dùng dữ liệu giá đã lưu "
                        f"(đến {px['date'].iloc[-1]:%d/%m/%Y}).")

    log("[3/6] Phân tích kỹ thuật ...")
    pxi = ta.add_indicators(px)
    tech = ta.summarize(pxi, idx)

    log("[4/6] Phân tích cơ bản & định giá ...")
    fscore, ftests = fa.piotroski(fin)
    z = (np.nan, "Không áp dụng") if fin.attrs.get("is_bank") else fa.altman_z(fin)
    fscore_val, fnotes = fa.fundamental_score(ratios, fscore, z[0])
    val = va.valuate(fin, ratios, px, prof.shares, tech.get("beta", np.nan), vparams,
                     target_pe=target_pe, market_pe=market_pe)
    last_fy = int(fin.index[-1])
    if datetime.now().year - last_fy >= 2:
        warnings.append(f"BCTC năm gần nhất là {last_fy} - số liệu có thể đã cũ.")

    log("[5/6] So sánh ngành & tin tức ...")
    try:
        peers_df, level, psum = pa.peer_table(ticker)
    except Exception as e:  # noqa: BLE001
        peers_df, level, psum = pd.DataFrame(), "", {}
        warnings.append(f"Không so sánh được ngành: {e}")
    nw = news.get_news(ticker, offline=offline, name_kw=prof.short_name)

    log("[6/6] Chấm điểm & khuyến nghị ...")
    scores = {
        "fundamental": fscore_val,
        "valuation": val["valuation_score"],
        "momentum": tech["momentum_score"],
        "risk": tech["risk_score"],
        "news": sc.news_score(nw["avg_sentiment"]),
    }
    comp = sc.composite(scores, user)
    rating, reason = sc.recommend(val["upside"], comp["total"], scores["news"], user.horizon, tech["momentum_score"])

    res = AnalysisResult(
        ticker=ticker, profile=prof, created_at=datetime.now(), fin=fin, ratios=ratios, prices=pxi,
        index_prices=idx, tech=tech, val=val, fscore=fscore, fscore_tests=ftests, altman=z,
        fund_score=fscore_val, fund_notes=fnotes, peers=peers_df, peer_level=level, peer_summary=psum,
        news=nw, composite=comp, rating=rating, rating_reason=reason, user=user, warnings=warnings,
        data_sources={
            "BCTC": f"BCTC hợp nhất năm {int(fin.index[0])}-{last_fy} (bộ dữ liệu vn-annual-report-miner, HSX/HNX)",
            "Giá cổ phiếu": px.attrs.get("source", ""),
            "VN-Index": idx.attrs.get("source", "") if idx is not None else "N/A",
            "Số CP lưu hành": prof.shares_source,
            "Tin tức": nw.get("source", ""),
            "Phân ngành": "ICB (FiinPro / Vietcap IQ & Sở GDCK)",
        },
    )
    res.vparams = vparams
    res.base_rating = rating
    apply_scenarios(res)
    return res


def apply_scenarios(res: AnalysisResult, overrides: dict | None = None, years: int | None = None) -> AnalysisResult:
    """(Tái) tính 3 kịch bản theo giả định người dùng -> cập nhật khuyến nghị & thẻ bằng chứng."""
    res.scen = scn.build(res, overrides, years)
    rating, reason = scn.rating_from_scenarios(res.scen)
    if res.user.horizon == "short" and res.tech["momentum_score"] < 35 and rating in ("MUA", "KHẢ QUAN"):
        rating = {"MUA": "KHẢ QUAN", "KHẢ QUAN": "NẮM GIỮ"}[rating]
        reason += f"; kỳ hạn ngắn & động lượng yếu ({res.tech['momentum_score']:.0f}/100) nên hạ 1 bậc"
    res.rating, res.rating_reason = rating, reason
    res.evidence = build_evidence(res)
    res.thesis = [e.claim for e in res.evidence.by_kind("thesis")]
    res.risks = [e.claim for e in res.evidence.by_kind("risk")]
    return res





def _pct(x, d=1, sign=False):
    return "N/A" if x is None or pd.isna(x) else F.pct(x, d, sign)


def build_evidence(r: AnalysisResult) -> EvidenceBook:
    """Sinh nhận định (luận điểm, rủi ro, giả định kịch bản) - MỖI nhận định kèm thẻ bằng chứng."""
    book = EvidenceBook()
    rt, f = r.ratios.iloc[-1], r.fin.iloc[-1]
    fy = int(r.fin.index[-1])
    fy_prev = int(r.fin.index[-2]) if len(r.fin) > 1 else fy
    src_fin = r.data_sources["BCTC"]
    src_px = r.data_sources["Giá cổ phiếu"]
    npat_p = r.fin["npat_parent"].fillna(r.fin["npat"])
    t, v, mm, ss = r.tech, r.val, r.val["multiples"], r.scen
    px_period = f"{r.prices['date'].iloc[0]:%d/%m/%Y} - {t['date']:%d/%m/%Y}"
    is_bank = r.fin.attrs.get("is_bank")
    rev_lbl = "Tổng thu nhập hoạt động" if is_bank else "Doanh thu thuần"

    # ---------------- Kịch bản (nhận định trung tâm) ----------------
    b, base, bear = ss.scenarios["bull"], ss.scenarios["base"], ss.scenarios["bear"]
    book.add(
        f"Giá trị kỳ vọng (gia quyền 3 kịch bản) {F.num(ss.expected_price)}đ, TSSL kỳ vọng "
        f"{_pct(ss.expected_return, sign=True)} trong {ss.label} ({_pct(ss.expected_annual, sign=True)}/năm); "
        f"biên độ {F.num(bear.target_price)}đ - {F.num(b.target_price)}đ.",
        "thesis" if ss.expected_annual > 0.05 else "risk",
        metrics=[(f"{s.name} (p={_pct(s.probability, 0)})", f"{F.num(s.target_price)}đ | {_pct(s.total_return, sign=True)}")
                 for s in ss.ordered()] + [("Giá hiện tại", F.num(ss.price) + "đ")],
        period=f"EPS FY{ss.fy0} tăng trưởng {ss.label}; giá đến {t['date']:%d/%m/%Y}",
        source=f"{src_fin}; {src_px}",
        formula="Giá mục tiêu = P/E mục tiêu × EPS·Π(1+g); TSSL = (Giá mục tiêu + Cổ tức)/Giá hiện tại − 1; "
                "Kỳ vọng = Σ xác suất × TSSL",
        calc=" + ".join(f"{s.probability:.2f}×{_pct(s.total_return, sign=True)}" for s in ss.ordered())
             + f" = {_pct(ss.expected_return, sign=True)}",
        tone=1 if ss.expected_annual > 0.05 else -1)
    rr = ss.risk_reward
    book.add(
        (f"Tỷ lệ lợi nhuận/rủi ro {'> 10' if rr > 10 else F.num(rr, 2)} lần: kịch bản tích cực {_pct(b.total_return, sign=True)} so với "
         f"tiêu cực {_pct(bear.total_return, sign=True)}." if np.isfinite(rr) else
         f"Kịch bản tiêu cực vẫn có TSSL dương ({_pct(bear.total_return, sign=True)}) - rủi ro giảm giá thấp."),
        "thesis" if (not np.isfinite(rr) or rr >= 1.5) else "risk",
        metrics=[("TSSL tích cực", _pct(b.total_return, sign=True)), ("TSSL tiêu cực", _pct(bear.total_return, sign=True)),
                 ("Xác suất thua lỗ", _pct(ss.prob_loss, 0))],
        period=f"Kỳ hạn {ss.label}", source="Mô hình kịch bản VNEquity",
        formula="Lợi nhuận/rủi ro = TSSL kịch bản tích cực / |TSSL kịch bản tiêu cực|",
        calc=(f"{_pct(b.total_return)} / {_pct(abs(bear.total_return))} = {F.num(rr, 2)}" if np.isfinite(rr) else "Tiêu cực ≥ 0"),
        tone=1 if (not np.isfinite(rr) or rr >= 1.5) else -1)

    # ---------------- Kết quả kinh doanh ----------------
    if pd.notna(f["revenue"]):
        book.add(f"Kết quả {fy}: {rev_lbl.lower()} {F.bil(f['revenue'])} tỷ đồng ({_pct(rt['revenue_growth'], sign=True)} YoY), "
                 f"LNST công ty mẹ {F.bil(npat_p.iloc[-1])} tỷ đồng ({_pct(rt['npat_growth'], sign=True)} YoY).",
                 "thesis" if (rt["npat_growth"] or 0) > 0 else "risk",
                 metrics=[(f"{rev_lbl} FY{fy}", F.bil(f["revenue"]) + " tỷ"), (f"{rev_lbl} FY{fy_prev}", F.bil(r.fin["revenue"].iloc[-2]) + " tỷ"),
                          (f"LNST CĐ mẹ FY{fy}", F.bil(npat_p.iloc[-1]) + " tỷ"), (f"LNST CĐ mẹ FY{fy_prev}", F.bil(npat_p.iloc[-2]) + " tỷ")],
                 period=f"FY{fy_prev} - FY{fy}", source=src_fin, formula="Tăng trưởng = Năm nay / Năm trước − 1",
                 calc=f"{F.bil(npat_p.iloc[-1])} / {F.bil(npat_p.iloc[-2])} − 1 = {_pct(rt['npat_growth'])}",
                 tone=1 if (rt["npat_growth"] or 0) > 0 else -1)
    c5 = fa.cagr(npat_p, 5)
    if pd.notna(c5):
        ok = c5 > 0.08
        book.add(f"LNST công ty mẹ tăng trưởng kép 5 năm {_pct(c5)}/năm" + (" - tăng trưởng bền vững." if ok else " - tăng trưởng chậm."),
                 "thesis" if ok else "risk",
                 metrics=[(f"FY{fy - 5}", F.bil(npat_p.loc[fy - 5]) + " tỷ" if fy - 5 in npat_p.index else "-"),
                          (f"FY{fy}", F.bil(npat_p.iloc[-1]) + " tỷ")],
                 period=f"FY{fy - 5} - FY{fy}", source=src_fin, formula="CAGR = (Cuối kỳ / Đầu kỳ)^(1/5) − 1",
                 calc=(f"({F.bil(npat_p.iloc[-1])} / {F.bil(npat_p.loc[fy - 5])})^(1/5) − 1 = {_pct(c5)}" if fy - 5 in npat_p.index else ""),
                 tone=1 if ok else -1)
    if pd.notna(rt["roe"]):
        ok = rt["roe"] >= 0.15
        eq_p = r.fin["equity"] - r.fin["minority_equity"].fillna(0)
        book.add(f"ROE {fy} đạt {_pct(rt['roe'])}, ROA {_pct(rt['roa'])}" + (" - hiệu quả sử dụng vốn cao." if ok else " - hiệu quả sử dụng vốn chưa cao."),
                 "thesis" if ok else "risk",
                 metrics=[("LNST CĐ mẹ", F.bil(npat_p.iloc[-1]) + " tỷ"), ("VCSH CĐ mẹ đầu kỳ", F.bil(eq_p.iloc[-2]) + " tỷ"),
                          ("VCSH CĐ mẹ cuối kỳ", F.bil(eq_p.iloc[-1]) + " tỷ"),
                          ("DuPont: biên × vòng quay × đòn bẩy", f"{_pct(rt['dupont_margin'])} × {F.num(rt['dupont_turnover'], 2)} × {F.num(rt['dupont_leverage'], 2)}")],
                 period=f"FY{fy}", source=src_fin, formula="ROE = LNST CĐ mẹ / VCSH CĐ mẹ bình quân (đầu kỳ + cuối kỳ)/2",
                 calc=f"{F.bil(npat_p.iloc[-1])} / (({F.bil(eq_p.iloc[-2])} + {F.bil(eq_p.iloc[-1])})/2) = {_pct(rt['roe'])}",
                 tone=1 if ok else -1)
    ps = r.peer_summary
    if ps and "ROE" in ps.get("percentile", {}):
        pct_rank = ps["percentile"]["ROE"]
        book.add(f"ROE cao hơn {pct_rank:.0f}% doanh nghiệp cùng nhóm {r.peer_level} (trung vị ngành {_pct(ps['median'].get('ROE'))}).",
                 "thesis" if pct_rank >= 50 else "risk",
                 metrics=[(row["Mã"], _pct(row["ROE"])) for _, row in r.peers.head(8).iterrows()],
                 period=f"FY{ps['year']}", source=f"{src_fin}; phân ngành ICB",
                 formula="Thứ hạng = tỷ lệ DN trong nhóm có ROE thấp hơn", calc=f"{pct_rank:.0f}%", tone=1 if pct_rank >= 50 else -1)
    if is_bank:
        book.add(f"Chỉ số ngân hàng {fy}: NIM ~{_pct(rt['nim_proxy'], 2)}, CIR {_pct(rt['cir'])}, LDR {_pct(rt['ldr'])}, "
                 f"chi phí tín dụng {_pct(rt['credit_cost'], 2)}, tăng trưởng cho vay {_pct(rt['loan_growth'])}.", "thesis",
                 metrics=[("TN lãi thuần", F.bil(f["nii"]) + " tỷ"), ("Chi phí hoạt động", F.bil(f["opex"]) + " tỷ"),
                          ("Cho vay KH", F.bil(f["loans"]) + " tỷ"), ("Tiền gửi KH", F.bil(f["deposits"]) + " tỷ")],
                 period=f"FY{fy}", source=src_fin, formula="NIM≈TN lãi thuần/TTS bq; CIR=Chi phí HĐ/TN HĐ; LDR=Cho vay/Tiền gửi",
                 calc=f"CIR = {F.bil(abs(f['opex']))}/{F.bil(f['revenue'])} = {_pct(rt['cir'])}")
        if rt["equity_to_assets"] < 0.07:
            book.add(f"VCSH/Tổng tài sản chỉ {_pct(rt['equity_to_assets'])} - đệm vốn mỏng.", "risk",
                     metrics=[("VCSH", F.bil(f["equity"]) + " tỷ"), ("Tổng tài sản", F.bil(f["total_assets"]) + " tỷ")],
                     period=f"FY{fy}", source=src_fin, formula="VCSH / Tổng tài sản", tone=-1)

    # ---------------- Định giá ----------------
    hs = v["hist_pe_stats"]
    if pd.notna(mm["pe"]):
        cheap = pd.notna(hs["avg"]) and mm["pe"] < hs["avg"]
        claim = f"P/E hiện tại {F.times(mm['pe'])}, P/B {F.times(mm['pb'])} (theo LNST {fy})"
        if pd.notna(hs["avg"]):
            claim += f"; P/E bình quân 12 tháng {F.times(hs['avg'])}, " + ("tức đang thấp hơn mức bình quân." if cheap else "tức đang cao hơn mức bình quân.")
        book.add(claim, "thesis" if cheap else "risk",
                 metrics=[("Giá hiện tại", F.num(mm["price"]) + "đ"), ("Số CP lưu hành", F.num(mm["shares"])),
                          (f"LNST CĐ mẹ FY{fy}", F.bil(npat_p.iloc[-1]) + " tỷ"), ("EPS (theo SLCP hiện tại)", F.num(mm["eps"]) + "đ"),
                          ("P/E thấp / BQ / cao 12T", f"{F.times(hs['min'])} / {F.times(hs['avg'])} / {F.times(hs['max'])}")],
                 period=f"FY{fy}; giá {px_period}", source=f"{src_fin}; {src_px}; {r.data_sources['Số CP lưu hành']}",
                 formula="P/E = Giá / EPS; EPS = LNST CĐ mẹ / SLCP lưu hành hiện tại",
                 calc=f"{F.num(mm['price'])} / {F.num(mm['eps'])} = {F.times(mm['pe'])}", tone=1 if cheap else -1)

    # ---------------- Sức khỏe tài chính ----------------
    if pd.notna(rt["debt_to_equity"]):
        debt = (f["st_debt"] or 0) + (f["lt_debt"] or 0)
        if rt["debt_to_equity"] > 1.5:
            book.add(f"Đòn bẩy tài chính cao: Nợ vay/VCSH {F.num(rt['debt_to_equity'], 2)} lần.", "risk",
                     metrics=[("Nợ vay", F.bil(debt) + " tỷ"), ("VCSH", F.bil(f["equity"]) + " tỷ")], period=f"FY{fy}",
                     source=src_fin, formula="(Vay ngắn hạn + Vay dài hạn) / VCSH",
                     calc=f"{F.bil(debt)} / {F.bil(f['equity'])} = {F.num(rt['debt_to_equity'], 2)}", tone=-1)
        elif rt["debt_to_equity"] < 0.6:
            book.add(f"Cấu trúc tài chính an toàn: Nợ vay/VCSH {F.num(rt['debt_to_equity'], 2)} lần, EBIT/lãi vay {F.num(rt['interest_coverage'], 1)} lần.",
                     "thesis", metrics=[("Nợ vay", F.bil(debt) + " tỷ"), ("VCSH", F.bil(f["equity"]) + " tỷ"),
                                        ("EBIT", F.bil(f["ebit"]) + " tỷ"), ("Chi phí lãi vay", F.bil(f["interest_exp"]) + " tỷ")],
                     period=f"FY{fy}", source=src_fin, formula="Nợ vay/VCSH; EBIT / |Chi phí lãi vay|",
                     calc=f"{F.bil(debt)} / {F.bil(f['equity'])} = {F.num(rt['debt_to_equity'], 2)}", tone=1)
    if pd.notna(rt["cfo_to_npat"]):
        ok = rt["cfo_to_npat"] >= 0.6
        book.add(f"Dòng tiền HĐKD {'tốt' if ok else 'yếu'}: CFO/LNST {F.num(rt['cfo_to_npat'], 2)} lần, FCF {F.bil(rt['fcf'])} tỷ đồng.",
                 "thesis" if ok else "risk",
                 metrics=[("CFO", F.bil(f["cfo"]) + " tỷ"), ("LNST", F.bil(f["npat"]) + " tỷ"), ("Capex", F.bil(f["capex"]) + " tỷ")],
                 period=f"FY{fy}", source=src_fin, formula="CFO/LNST; FCF = CFO + Capex (Capex mang dấu âm)",
                 calc=f"{F.bil(f['cfo'])} / {F.bil(f['npat'])} = {F.num(rt['cfo_to_npat'], 2)}; FCF = {F.bil(f['cfo'])} + ({F.bil(f['capex'])}) = {F.bil(rt['fcf'])}",
                 tone=1 if ok else -1)
    z, zone = r.altman
    if zone not in ("An toàn", "Không áp dụng"):
        book.add(f"Altman Z'' = {F.num(z, 2)} ({zone}) - cần theo dõi sức khỏe tài chính.", "risk", period=f"FY{fy}", source=src_fin,
                 formula="Z'' = 6,56·VLĐ/TTS + 3,26·LNGL/TTS + 6,72·EBIT/TTS + 1,05·VCSH/Nợ", calc=F.num(z, 2), tone=-1)

    # ---------------- Kỹ thuật & thị trường ----------------
    up = t["trend"] == "Tăng"
    book.add(f"Xu hướng kỹ thuật: {t['trend'].lower()}; RSI {t['rsi14']:.0f}, hiệu suất 3 tháng {_pct(t['ret_3m'], sign=True)}"
             + (f" (VN-Index {_pct(t.get('index_ret_3m'), sign=True)})." if pd.notna(t.get("index_ret_3m", np.nan)) else "."),
             "thesis" if up else "risk",
             metrics=[("Giá đóng cửa", F.num(t["close"], 2) + " nghìn đ")] +
                     [(f"MA{n}", F.num(t.get(f"ma{n}"), 2)) for n in (20, 50, 200)] +
                     [("RSI14", F.num(t["rsi14"], 1)), ("MACD / Signal", f"{F.num(t['macd'], 2)} / {F.num(t['macd_signal'], 2)}")],
             period=px_period, source=src_px, formula="Xu hướng: số đường MA (20/50/100/200) giá nằm trên trừ số nằm dưới; RSI Wilder 14 phiên",
             calc="; ".join(s for s, _ in t["signals"][:4]), tone=1 if up else -1)
    if t["drawdown_now"] < -0.25:
        book.add(f"Giá thấp hơn {_pct(abs(t['drawdown_now']), 0)} so với đỉnh 52 tuần - tâm lý thị trường còn yếu.", "risk",
                 metrics=[("Đỉnh 52 tuần", F.num(t["high_52w"], 2)), ("Giá hiện tại", F.num(t["close"], 2))], period=px_period,
                 source=src_px, formula="Giá hiện tại / Giá đóng cửa cao nhất 52 tuần − 1", calc=_pct(t["drawdown_now"]), tone=-1)
    if pd.notna(t.get("beta")) and t["beta"] > 1.2:
        book.add(f"Beta {F.num(t['beta'], 2)} - biến động mạnh hơn thị trường.", "risk", period=px_period,
                 source=f"{src_px}; {r.data_sources['VN-Index']}", formula="β = Cov(r_cp, r_VNI) / Var(r_VNI), lợi suất ngày",
                 calc=F.num(t["beta"], 2), tone=-1)
    nw = r.news
    if nw["items"]:
        neg = nw["n_neg"] > nw["n_pos"]
        book.add(f"Dòng tin gần đây {'nghiêng tiêu cực' if neg else 'tích cực'}: {nw['n_pos']} tích cực / {nw['n_neg']} tiêu cực / {nw['n_neu']} trung tính.",
                 "risk" if neg else "thesis",
                 metrics=[(it["date"][:10], f"{it['sentiment']:+.2f} | {it['title'][:70]}") for it in nw["items"][:5]],
                 period=f"{nw['items'][-1]['date'][:10]} - {nw['items'][0]['date'][:10]}", source=nw.get("source", ""),
                 formula="Điểm tin = (số từ khoá tích cực − tiêu cực)/(tổng); trung bình trên các tin",
                 calc=f"TB = {nw['avg_sentiment']:+.2f}", tone=-1 if neg else 1)
    book.add("Rủi ro thị trường chung: biến động vĩ mô, lãi suất, tỷ giá và dòng vốn khối ngoại.", "risk",
             source="Nhận định định tính", formula="-", tone=-1)

    # ---------------- Giả định kịch bản (vì sao có con số mặc định) ----------------
    d = ss.defaults_info
    gd = v["growth_detail"]
    book.add(f"Tăng trưởng EPS cơ sở mặc định {_pct(d['g_base'])}/năm.", "scenario",
             metrics=[("CAGR LNST 3 năm", _pct(gd["g_npat_3y"])), ("CAGR doanh thu 3 năm", _pct(gd["g_rev_3y"])),
                      ("ROE × (1 − tỷ lệ chi trả)", _pct(gd["g_sustainable"]))],
             period=f"FY{fy - 3} - FY{fy}", source=src_fin, formula="g cơ sở = trung vị 3 thước đo, chặn trong [−5%; 25%]",
             calc=f"median({_pct(gd['g_npat_3y'])}, {_pct(gd['g_rev_3y'])}, {_pct(gd['g_sustainable'])}) = {_pct(d['g_base'])}")
    rk = d["risk"]
    book.add(f"Biên độ tăng trưởng: σ = {_pct(d['sigma'])}; tích cực +{F.num(rk['bull_sigma'], 2)}σ, tiêu cực −{F.num(rk['bear_sigma'], 2)}σ "
             f"(khẩu vị {RISK_LABEL[r.user.risk].lower()}). Tăng trưởng giảm dần về mức dài hạn vào năm thứ 5 (tích cực {_pct(scn.LONG_TERM_ANCHOR["bull"], 0)}, cơ sở {_pct(scn.LONG_TERM_ANCHOR["base"], 0)}, tiêu cực {_pct(scn.LONG_TERM_ANCHOR["bear"], 0)}).", "scenario",
             metrics=[(f"Tăng trưởng LNST năm", " ; ".join(_pct(x) for x in d["yoy"]))] + [("Độ lệch chuẩn thực tế", _pct(d["sigma_raw"]))],
             period="5 năm gần nhất", source=src_fin,
             formula="σ = độ lệch chuẩn tăng trưởng LNST hằng năm, chặn [8%; 20%]; khẩu vị thận trọng đào sâu kịch bản tiêu cực hơn",
             calc=f"Tích cực {_pct(d['g_base'])} + {F.num(rk['bull_sigma'], 2)} × {_pct(d['sigma'])} = {_pct(d['bull']['eps_growth'])}; "
                  f"Tiêu cực {_pct(d['g_base'])} − {F.num(rk['bear_sigma'], 2)} × {_pct(d['sigma'])} = {_pct(d['bear']['eps_growth'])}")
    tg = d["pe_targets"]
    book.add(f"P/E cuối kỳ ({ss.label}): cơ sở {F.times(d['base']['exit_pe'])}, tích cực {F.times(d['bull']['exit_pe'])}, "
             f"tiêu cực {F.times(d['bear']['exit_pe'])} - định giá hội tụ dần từ P/E hiện tại về P/E đích.", "scenario",
             metrics=[("P/E hiện tại", F.times(d["cur_pe"])), (d["ref_src"], F.times(d["hist_avg"])),
                      ("P/E đích: cơ sở / tích cực / tiêu cực", f"{F.times(tg['base'])} / {F.times(tg['bull'])} / {F.times(tg['bear'])}"),
                      (f"Tỷ lệ hội tụ sau {ss.label}", _pct(d["converge"], 0))],
             period=px_period, source=f"{src_px}; {src_fin}",
             formula=f"P/E cuối kỳ = P/E hiện tại + (1 − 0,5^(T/2)) × (P/E đích − P/E hiện tại), T = số năm nắm giữ. Đích: cơ sở = {d['ref_src']}; "
                     f"tích cực = {F.num(d['risk']['bull_pe'], 2)} × mức cao hơn; tiêu cực = {F.num(d['risk']['bear_pe'], 2)} × mức thấp hơn",
             calc=f"Cơ sở: {F.num(d['cur_pe'], 1)} + {F.num(d['converge'], 2)} × hệ số xác nhận {F.num(d['market']['factor'], 2)} × "
                  f"({F.num(tg['base'], 1)} − {F.num(d['cur_pe'], 1)}) = {F.num(d['base']['exit_pe'], 1)} (chặn trong 0,6 - 1,6 lần P/E hiện tại)")
    mc = d["market"]
    yn = lambda x: "chưa đủ dữ liệu" if x is None else ("đạt" if x else "không đạt")  # noqa: E731
    msg = {1.0: "thị trường xác nhận: P/E được phép tăng về mức đích",
           0.5: "thị trường xác nhận một phần: P/E chỉ tăng một nửa mức bình thường",
           0.0: "thị trường chưa xác nhận: kịch bản cơ sở không giả định P/E tăng"}.get(mc["factor"], "")
    book.add(f"Xác nhận thị trường cho việc định giá lại: xu hướng {yn(mc['trend_ok'])}, sức mạnh so với VN-Index {yn(mc['rs_ok'])} - {msg}.",
             "scenario" if mc["factor"] else "risk",
             metrics=[("Giá / EMA20 / EMA50", f"{F.num(mc['close'] * 1000)} / {F.num(mc['ema20'] * 1000)} / {F.num(mc['ema50'] * 1000)}"),
                      ("SMA200", F.num(mc["sma200"] * 1000))]
                     + [(f"Vượt VN-Index {n} phiên", _pct(x, 1, sign=True)) for n, x in mc["excess"].items()]
                     + [("Khoảng cách tới EMA20", f"{F.num(mc['anti'], 2)} ATR14")],
             period=px_period, source=f"{src_px}; {r.data_sources.get('VN-Index', '')}",
             formula="Xu hướng: EMA20 > EMA50 và giá > SMA200. Sức mạnh: bình quân lợi suất vượt VN-Index 63/126/252 phiên "
                     "(bỏ 5 phiên gần nhất) > 0. Hệ số = số điều kiện đạt / số điều kiện xét; áp vào phần P/E TĂNG",
             calc=f"Hệ số xác nhận = {F.num(mc['factor'], 2)}", tone=1 if mc["factor"] == 1 else (-1 if mc["factor"] == 0 else 0))
    if pd.notna(mc["anti"]) and mc["anti"] > 3:
        book.add(f"Giá đang cách EMA20 {F.num(mc['anti'], 1)} lần ATR14 (> 3): đã tăng nóng, rủi ro điều chỉnh ngắn hạn.", "risk",
                 period=px_period, source=src_px, formula="(Giá − EMA20) / ATR14 > 3", tone=-1)
    if d.get("eps_note"):
        book.add(f"EPS cơ sở cho mô hình kịch bản: {F.num(ss.eps0)}đ (chuẩn hoá).", "scenario",
                 source=src_fin, formula=d["eps_note"], calc=f"EPS chuẩn hoá = {F.num(ss.eps0)}đ", tone=-1)
    pr = d["risk"]["prob"]
    book.add(f"Tỷ lệ chi trả cổ tức mặc định {_pct(d['payout'])}; xác suất {pr[0]:.0%} / {pr[1]:.0%} / {pr[2]:.0%} theo khẩu vị {RISK_LABEL[r.user.risk].lower()}.", "scenario",
             metrics=[("Cổ tức tiền mặt đã trả FY" + str(fy), F.bil(f["dividends_paid"]) + " tỷ")], period=f"FY{fy - 2} - FY{fy}",
             source=src_fin, formula="Payout = |Cổ tức đã trả| / LNST CĐ mẹ, bình quân 3 năm", calc=_pct(d["payout"]))
    changes = []
    tot = sum(d[k]["probability"] for k in ("bull", "base", "bear"))
    for sc_ in ss.ordered():
        dd = d[sc_.key]
        for fld, lbl, fm in (("eps_growth", "tăng trưởng EPS", _pct), ("exit_pe", "P/E mục tiêu", F.times),
                             ("payout", "tỷ lệ chi trả", _pct)):
            if abs(getattr(sc_, fld) - dd[fld]) > 1e-6:
                changes.append((f"{sc_.name}: {lbl}", f"{fm(dd[fld])} thành {fm(getattr(sc_, fld))}"))
        if abs(sc_.probability - dd["probability"] / tot) > 1e-6:
            changes.append((f"{sc_.name}: xác suất", f"{_pct(dd['probability'] / tot, 0)} thành {_pct(sc_.probability, 0)}"))
    if changes or ss.years != scn.default_years(r.user.horizon):
        book.add((f"Người dùng đã điều chỉnh {len(changes)} giả định so với mặc định" if changes else "Giả định mặc định")
                 + (f"; kỳ hạn phân tích {ss.label}" if ss.years != scn.default_years(r.user.horizon) else "") + ".",
                 "scenario", metrics=changes, source="Thiết lập của người dùng",
                 formula="Kết quả kịch bản được tính lại với giả định mới")
    book.add(f"Khuyến nghị {r.rating}: {r.rating_reason}.", "info",
             metrics=[("TSSL kỳ vọng/năm", _pct(ss.expected_annual, sign=True)), ("Lợi nhuận/rủi ro", F.num(ss.risk_reward, 2)),
                      ("Điểm tổng hợp đa yếu tố", f"{r.composite['total']:.0f}/100"),
                      ("Định giá nội tại (DCF/P-E/P-B)", f"{F.num(v['target_price'])}đ ({_pct(v['upside'], sign=True)})")],
             source="Mô hình VNEquity", formula="≥20%: MUA; 10-20%: KHẢ QUAN; ±10%: NẮM GIỮ; −10..−20%: KÉM KHẢ QUAN; <−20%: BÁN; "
                                                 "hạ 1 bậc nếu lợi nhuận/rủi ro < 1, nâng 1 bậc nếu kịch bản tiêu cực vẫn lãi")
    return book