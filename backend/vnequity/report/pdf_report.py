"""Xuất báo cáo phân tích cổ phiếu dạng PDF theo format báo cáo của công ty chứng khoán.

Bố cục:
  Trang 1  : Tóm tắt (khuyến nghị, chỉ số chính, 3 kịch bản, luận điểm, rủi ro, thông tin cổ phiếu)
  Trang 2+ : Các mục người dùng chọn (kịch bản, doanh nghiệp, tài chính, định giá, kỹ thuật, ngành, tin tức,
             rủi ro, thẻ bằng chứng, phụ lục)
  Cuối     : Nguồn dữ liệu, ghi chú phương pháp, miễn trừ trách nhiệm

Quy ước trình bày (dùng thống nhất trong toàn báo cáo):
  - Chữ một tông xanh than (INK, INK2), không dùng màu xám.
  - Khoảng cách dọc theo bội số của 4pt; đoạn văn 8,5/12,5pt; ô bảng 7,4/10pt.
  - Tiêu đề mục luôn đi cùng nội dung đầu tiên (không bị tách sang trang sau).
  - Mỗi hình có tên trong hình và dòng nguồn ở góc dưới bên phải.
"""
from __future__ import annotations

import re
import tempfile
from xml.sax.saxutils import escape
from pathlib import Path

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, HRFlowable, Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from ..analysis.scoring import RATING_COLOR
from ..config import (DETAIL_LABEL, FONT_DIR, HORIZON_LABEL, METRIC_GROUPS, PURPOSE_PRESETS, REPORT_DIR, RISK_LABEL,
                      ReportOptions)
from ..data.financials import FIELD_LABEL_VI
from . import charts
from .fmt import bil, num, pct, times

# ------------------------------------------------------------------ bảng màu (một tông xanh than)
NAVY = colors.HexColor("#0F2A4A")      # thương hiệu: dải đầu trang, tiêu đề bảng
INK = colors.HexColor("#0F2A4A")       # chữ chính
INK2 = colors.HexColor("#2C4A6E")      # chữ phụ (nhãn, chú thích)
ACCENT = colors.HexColor("#B45309")    # nâu vàng - điểm nhấn
LIGHT = colors.HexColor("#F4F7FB")     # nền dòng xen kẽ
SOFT = colors.HexColor("#E6EEF8")      # nền dòng nhóm / thẻ
RULE = colors.HexColor("#C9D6E8")      # đường kẻ
GREEN = colors.HexColor("#15803D")
RED = colors.HexColor("#B91C1C")
HEX_INK2 = "#2C4A6E"
SCEN_HEX = {"bull": "#15803D", "base": "#1E3A8A", "bear": "#B91C1C"}
SCEN_TINT = {"bull": "#F0FDF4", "base": "#EFF6FF", "bear": "#FEF2F2"}

PAGE_W, PAGE_H = A4
MARGIN = 14 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
GAP = 8  # khoảng cách chuẩn giữa các khối (pt)

SRC_FIN = "Nguồn: BCTC hợp nhất, VNEquity Research tổng hợp"
SRC_PX = "Nguồn: VNDirect, VNEquity Research tổng hợp"
SRC_EST = "Nguồn: VNEquity Research ước tính"
SRC_VAL = "Nguồn: BCTC hợp nhất, VNDirect, VNEquity Research ước tính"
SRC_PEER = "Nguồn: BCTC hợp nhất năm gần nhất, phân ngành ICB"
SRC_NEWS = "Nguồn: CafeF, VnExpress, VNEquity Research tổng hợp"


def _register_fonts():
    if "VN" in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont("VN", str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("VN-B", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("VN-I", str(FONT_DIR / "DejaVuSans-Oblique.ttf")))
    pdfmetrics.registerFont(TTFont("VN-BI", str(FONT_DIR / "DejaVuSans-BoldOblique.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("VN", normal="VN", bold="VN-B", italic="VN-I", boldItalic="VN-BI")


def _styles():
    def ps(name, **kw):
        base = dict(fontName="VN", fontSize=8.5, leading=12.5, textColor=INK)
        base.update(kw)
        return ParagraphStyle(name, **base)

    return {
        "body": ps("body"),
        "bullet": ps("bullet", leftIndent=10, bulletIndent=0, spaceAfter=3, bulletColor=NAVY, bulletFontName="VN-B"),
        "small": ps("small", fontSize=7.2, leading=10, textColor=INK2),
        "source": ps("source", fontName="VN-I", fontSize=6.6, leading=9, textColor=INK2, alignment=TA_RIGHT),
        "h1": ps("h1", fontName="VN-B", fontSize=18, leading=22),
        "h1sub": ps("h1sub", fontSize=8, leading=11, textColor=INK2),
        "h2": ps("h2", fontName="VN-B", fontSize=13, leading=17, keepWithNext=1),
        "h3": ps("h3", fontName="VN-B", fontSize=9.5, leading=13, spaceBefore=GAP, spaceAfter=4, keepWithNext=1),
        "cell": ps("cell", fontSize=7.4, leading=10),
        "cellb": ps("cellb", fontName="VN-B", fontSize=7.4, leading=10),
        "cellr": ps("cellr", fontSize=7.4, leading=10, alignment=TA_RIGHT),
        "lbl": ps("lbl", fontName="VN-B", fontSize=7, leading=10, textColor=INK2),
        "side_lbl": ps("side_lbl", fontSize=7.2, leading=10, textColor=INK2),
        "side_val": ps("side_val", fontName="VN-B", fontSize=7.4, leading=10, alignment=TA_RIGHT),
        "kpi_lbl": ps("kpi_lbl", fontSize=6.8, leading=9, textColor=INK2),
        "kpi_val": ps("kpi_val", fontName="VN-B", fontSize=13, leading=16),
        "kpi_sub": ps("kpi_sub", fontSize=6.8, leading=9, textColor=INK2),
        "white_b": ps("white_b", fontName="VN-B", fontSize=8, leading=10, textColor=colors.white),
        "pill": ps("pill", fontName="VN-B", fontSize=8, leading=10, textColor=colors.white, alignment=TA_CENTER),
        "badge": ps("badge", fontName="VN-B", fontSize=8.5, leading=11, textColor=colors.white, alignment=TA_CENTER),
        "badge_s": ps("badge_s", fontName="VN-B", fontSize=5.8, leading=8, textColor=colors.white, alignment=TA_CENTER),
        "claim": ps("claim", fontName="VN-B", fontSize=8, leading=11),
    }


ST = None


def sgn(x, text=None, d=1):
    """Tô màu theo dấu: dương = xanh lá, âm = đỏ."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    t = text if text is not None else pct(x, d, sign=True)
    c = "#15803D" if x > 0 else ("#B91C1C" if x < 0 else HEX_INK2)
    return f"<font color='{c}'>{t}</font>"


def _p(text, style="body"):
    return Paragraph(str(text), ST[style])


def _keep_next(fl):
    fl.keepWithNext = 1
    return fl


def _table(data, col_widths, header=True, zebra=True, align_right_from=1, font_size=7.4, highlight_rows=None):
    lead = font_size + 2.6
    rows = []
    for i, r in enumerate(data):
        row = []
        for j, c in enumerate(r):
            if isinstance(c, (Paragraph, Image, Table)):
                row.append(c)
                continue
            al = TA_RIGHT if j >= align_right_from else TA_LEFT
            if i == 0 and header:
                st = ParagraphStyle("th", fontName="VN-B", fontSize=font_size, leading=lead, textColor=colors.white, alignment=al)
            else:
                st = ParagraphStyle("td", fontName="VN", fontSize=font_size, leading=lead, textColor=INK, alignment=al)
            row.append(Paragraph(str(c), st))
        rows.append(row)
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    cmds = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE)]
    if header:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra:
        for i in range(1 if header else 0, len(rows)):
            if i % 2 == 0:
                cmds.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    for i in highlight_rows or []:
        cmds.append(("BACKGROUND", (0, i), (-1, i), SOFT))
    t.setStyle(TableStyle(cmds))
    return t


class ReportBuilder:
    def __init__(self, result, out_path: Path | None = None, brand: str = "VNEquity Research",
                 options: ReportOptions | None = None):
        global ST
        _register_fonts()
        ST = _styles()
        self.r = result
        self.o = options or ReportOptions()
        self.ev_on = "evidence" in self.o.sections
        self.brand = brand
        ts = result.created_at.strftime("%Y%m%d_%H%M")
        self.out = Path(out_path) if out_path else REPORT_DIR / f"{result.ticker}_BaoCaoPhanTich_{ts}.pdf"
        self.tmp = Path(tempfile.mkdtemp(prefix="vnequity_"))
        self.story = []

    # ------------------------------------------------------------------ khối dựng chung
    def _gap(self, h=GAP):
        self.story.append(Spacer(1, h))

    def _img(self, path, width):
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(str(path)).getSize()
        return Image(str(path), width=width, height=width * ih / iw)

    def _fig_flows(self, path, width, source):
        """Hình + dòng nguồn ở góc dưới bên phải (danh sách flowable, dùng được trong ô bảng)."""
        st = ParagraphStyle("src_w", parent=ST["source"])
        return [self._img(path, width), Paragraph(source, st)]

    def _fig(self, path, width, source):
        self.story.append(KeepTogether(self._fig_flows(path, width, source)))

    def _grid(self, cells, ncol=2):
        """Lưới hình (mỗi ô = danh sách flowable)."""
        if not cells:
            return
        w = CONTENT_W / ncol
        while len(cells) % ncol:
            cells.append("")
        g = Table([cells[i:i + ncol] for i in range(0, len(cells), ncol)], colWidths=[w] * ncol)
        g.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        self.story.append(g)

    def _h2(self, text):
        m = re.match(r"^\d+\.\s*(.*)$", text)
        if m:
            self._sec = getattr(self, "_sec", 0) + 1
            text = f"{self._sec}. {m.group(1)}"
        self.story.append(CondPageBreak(70 * mm))
        self.story.append(_keep_next(Spacer(1, 14)))
        self.story.append(_p(text, "h2"))
        self.story.append(_keep_next(HRFlowable(width="100%", thickness=1.4, color=NAVY, spaceBefore=2, spaceAfter=GAP)))

    def _h3(self, text, long_next=False):
        """Tiêu đề nhỏ. Nếu nội dung sau là bảng dài (được phép tách trang) thì chỉ cần đủ chỗ cho vài dòng đầu."""
        if long_next:
            self.story.append(CondPageBreak(45 * mm))
            p = Paragraph(text, ParagraphStyle("h3l", parent=ST["h3"], keepWithNext=0))
            self.story.append(p)
        else:
            self.story.append(_p(text, "h3"))

    def _bullet(self, text):
        return Paragraph(text, ST["bullet"], bulletText="•")

    def _on_page(self, canv, doc):
        r = self.r
        canv.saveState()
        band = 12 * mm
        canv.setFillColor(NAVY)
        canv.rect(0, PAGE_H - band, PAGE_W, band, stroke=0, fill=1)
        canv.setFillColor(ACCENT)
        canv.rect(0, PAGE_H - band - 0.7 * mm, PAGE_W, 0.7 * mm, stroke=0, fill=1)
        y = PAGE_H - 7.6 * mm
        canv.setFillColor(colors.white)
        canv.setFont("VN-B", 10)
        canv.drawString(MARGIN, y, "VNEQUITY RESEARCH")
        canv.setFont("VN", 7.2)
        canv.setFillColor(colors.HexColor("#C9D6E8"))
        canv.drawString(MARGIN + 46 * mm, y, "Báo cáo phân tích cổ phiếu")
        canv.setFillColor(colors.white)
        canv.setFont("VN-B", 7.5)
        canv.drawRightString(PAGE_W - MARGIN, y, f"{r.ticker}  |  {r.profile.exchange}  |  {r.created_at:%d/%m/%Y}")
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.5)
        canv.line(MARGIN, 11 * mm, PAGE_W - MARGIN, 11 * mm)
        canv.setFillColor(INK2)
        canv.setFont("VN", 6.4)
        canv.drawString(MARGIN, 7 * mm, "VNEquity Research. Báo cáo chỉ mang tính tham khảo, không phải lời mời mua hoặc bán chứng khoán.")
        canv.drawRightString(PAGE_W - MARGIN, 7 * mm, f"Trang {doc.page}")
        canv.restoreState()

    def _chart_on(self, key):
        return key in self.o.charts

    def _ev(self, e) -> str:
        tag = f"<font size=6.5 color='#1E3A8A'>[{e.id}]</font>"
        if self.ev_on:
            tag = f"<a href='#{e.id}' color='#1E3A8A'>{tag}</a>"
        return f"{e.claim} {tag}"

    def _card(self, flows, width, bg=colors.white, pad=6, border=RULE):
        t = Table([[flows]], colWidths=[width])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                               ("BOX", (0, 0), (-1, -1), 0.7, border),
                               ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                               ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    def _row(self, cells, widths, gap=4):
        t = Table([cells], colWidths=widths)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), gap), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return t

    def _kv(self, pairs, width, lw=0.58):
        kt = Table([[Paragraph(a, ST["side_lbl"]), Paragraph(b, ST["side_val"])] for a, b in pairs],
                   colWidths=[width * lw, width * (1 - lw)])
        kt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE), ("TOPPADDING", (0, 0), (-1, -1), 2),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        return kt

    def _kpi(self, label, value, sub, width, color=INK):
        st = ParagraphStyle("kv", parent=ST["kpi_val"], textColor=color)
        return self._card([Paragraph(label, ST["kpi_lbl"]), Paragraph(value, st), Paragraph(sub, ST["kpi_sub"])], width)

    def _scenario_card(self, s, width, ss):
        col = colors.HexColor(SCEN_HEX[s.key])
        inner = width - 12
        head = Table([[Paragraph(f"{s.name.upper()}   |   XÁC SUẤT {pct(s.probability, 0)}", ST["white_b"])]], colWidths=[inner])
        head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), col), ("ROUNDEDCORNERS", [3, 3, 3, 3]),
                                  ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        big = ParagraphStyle("big", parent=ST["kpi_val"], textColor=col, fontSize=14, leading=18)
        kv = [("Tăng trưởng EPS/năm", pct(s.eps_growth, 1)), ("P/E mục tiêu", times(s.exit_pe)),
              (f"EPS FY{ss.fy0 + ss.growth_years} (đ)", num(s.eps_path[-1])), ("Cổ tức nhận (đ)", num(s.dividends)),
              ("Sinh lời mỗi năm", sgn(s.annual_return))]
        flows = [head, Spacer(1, 4), Paragraph(f"{num(s.target_price)}đ", big),
                 Paragraph(f"Sinh lời tổng <b>{sgn(s.total_return)}</b> sau {ss.years} năm", ST["kpi_sub"]),
                 Spacer(1, 4), self._kv(kv, inner)]
        return self._card(flows, width, bg=colors.HexColor(SCEN_TINT[s.key]), border=col)

    # ------------------------------------------------------------------ trang 1
    def summary_page(self):
        r, v, t, mm_, ss = self.r, self.r.val, self.r.tech, self.r.val["multiples"], self.r.scen
        prof = r.profile
        pill = Table([[Paragraph(r.rating, ST["pill"])]], colWidths=[30 * mm])
        pill.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(RATING_COLOR[r.rating])),
                                  ("ROUNDEDCORNERS", [8, 8, 8, 8]), ("TOPPADDING", (0, 0), (-1, -1), 3),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        icb = " › ".join([x for x in (prof.icb1, prof.icb3) if x])
        title = [Paragraph(f"{r.ticker} <font color='{HEX_INK2}' size=12>| {prof.name or r.ticker}</font>", ST["h1"]),
                 Paragraph(f"{prof.exchange or '-'}  |  {icb or '-'}  |  Giá đến {t['date']:%d/%m/%Y}  |  "
                           f"{HORIZON_LABEL[r.user.horizon]}  |  {RISK_LABEL[r.user.risk]}", ST["h1sub"])]
        self.story.append(self._row([title, pill], [CONTENT_W - 32 * mm, 32 * mm]))
        self._gap()

        kw = (CONTENT_W - 12) / 4
        rr = "> 10" if (not np.isfinite(ss.risk_reward) or ss.risk_reward > 10) else num(ss.risk_reward, 2)
        kpis = [self._kpi("Giá hiện tại", f"{num(ss.price)}đ", f"P/E {times(mm_['pe'])}  |  P/B {times(mm_['pb'])}", kw),
                self._kpi("Giá trị kỳ vọng", f"{num(ss.expected_price)}đ",
                          f"Khoảng {num(ss.scenarios['bear'].target_price)} - {num(ss.scenarios['bull'].target_price)}", kw,
                          colors.HexColor("#1E3A8A")),
                self._kpi(f"Sinh lời kỳ vọng {ss.years} năm", pct(ss.expected_return, 1, sign=True),
                          f"{pct(ss.expected_annual, 1, sign=True)} mỗi năm, gồm cổ tức", kw,
                          GREEN if ss.expected_return >= 0 else RED),
                self._kpi("Lợi nhuận / rủi ro", f"{rr} lần", f"Xác suất thua lỗ {pct(ss.prob_loss, 0)}", kw)]
        self.story.append(self._row(kpis, [kw + 4] * 4))
        self._gap()

        self._h3("Ba kịch bản đầu tư")
        cw = (CONTENT_W - 12) / 3
        self.story.append(self._row([self._scenario_card(s, cw, ss) for s in ss.ordered()], [cw + 4] * 3))
        self._gap()

        side_w = 62 * mm
        left_w = CONTENT_W - side_w - 6 * mm
        left = [_p("Luận điểm đầu tư", "h3")]
        left += [self._bullet(self._ev(e)) for e in r.evidence.by_kind("thesis")[:5]]
        left.append(_p("Rủi ro chính", "h3"))
        left += [self._bullet(self._ev(e)) for e in r.evidence.by_kind("risk")[:3]]
        left.append(_p("Khuyến nghị và hành động", "h3"))
        info = r.evidence.by_kind("info")
        left.append(self._bullet(self._ev(info[0]) if info else r.rating_reason))
        left.append(self._bullet(self._timing_note()))

        side = [_p("Thông tin cổ phiếu", "h3")]
        kv = [("Vốn hoá (tỷ đồng)", bil(mm_["market_cap"])), ("Cổ phiếu lưu hành (triệu)", num(mm_["shares"] / 1e6, 1)),
              ("GTGD bình quân 20 phiên (tỷ)", bil(t["avg_value20"], 1)),
              ("Cao / thấp 52 tuần (nghìn đ)", f"{num(t['high_52w'], 1)} / {num(t['low_52w'], 1)}"),
              ("Beta 1 năm", num(t.get("beta"), 2)), (f"EPS FY{mm_['fiscal_year']} (đ)", num(mm_["eps"])),
              ("ROE", pct(r.ratios["roe"].iloc[-1])), ("Tỷ suất cổ tức", pct(mm_["div_yield"])),
              ("Định giá nội tại (tham chiếu)", f"{num(v['target_price'])}đ"),
              ("Điểm đa yếu tố", f"{r.composite['total']:.0f}/100")]
        side.append(self._kv(kv, side_w))
        if self._chart_on("relative"):
            side.append(Spacer(1, GAP))
            side += self._fig_flows(charts.relative_perf(r.prices, r.index_prices, r.ticker, self.tmp / "rel.png"), side_w, SRC_PX)
        self.story.append(self._row([left, side], [left_w + 6 * mm, side_w], gap=6 * mm))
        self.story.append(PageBreak())

    # ------------------------------------------------------------------ kịch bản
    def scenario_section(self):
        r, ss = self.r, self.r.scen
        self._h2("1. PHÂN TÍCH KỊCH BẢN ĐẦU TƯ")
        self.story.append(_p(
            f"Giá trị cổ phiếu được ước tính theo 3 kịch bản thay vì một giá mục tiêu duy nhất. Kỳ hạn {ss.years} năm: "
            f"EPS tăng trưởng {ss.growth_years} năm từ EPS FY{ss.fy0} = {num(ss.eps0)}đ; giá mục tiêu = P/E mục tiêu × EPS cuối kỳ; "
            f"tỷ suất sinh lời gồm cổ tức tiền mặt nhận trong kỳ."))
        self._gap()
        S = ss.ordered()
        rows = [["Giả định và kết quả"] + [s.name for s in S],
                ["<b>Giả định</b>", "", "", ""],
                ["Tăng trưởng EPS mỗi năm"] + [pct(s.eps_growth) for s in S],
                ["P/E mục tiêu cuối kỳ"] + [times(s.exit_pe) for s in S],
                ["Tỷ lệ chi trả cổ tức"] + [pct(s.payout) for s in S],
                ["Xác suất"] + [pct(s.probability, 0) for s in S],
                ["<b>Kết quả</b>", "", "", ""],
                [f"EPS FY{ss.fy0 + ss.growth_years} (đ)"] + [num(s.eps_path[-1]) for s in S],
                ["Giá mục tiêu (đ)"] + [f"<b>{num(s.target_price)}</b>" for s in S],
                ["Cổ tức nhận trong kỳ (đ)"] + [num(s.dividends) for s in S],
                [f"Sinh lời tổng ({ss.years} năm)"] + [f"<b>{sgn(s.total_return)}</b>" for s in S],
                ["Sinh lời mỗi năm"] + [sgn(s.annual_return) for s in S],
                ["Đối chiếu DCF với cùng tăng trưởng (đ)"] + [num(s.dcf_value) for s in S]]
        tbl = _table(rows, [CONTENT_W * 0.37] + [CONTENT_W * 0.21] * 3, highlight_rows=[1, 6])
        tbl.setStyle(TableStyle([("BACKGROUND", (i + 1, 0), (i + 1, 0), colors.HexColor(SCEN_HEX[s.key])) for i, s in enumerate(S)]
                                + [("BACKGROUND", (i + 1, 7), (i + 1, -1), colors.HexColor(SCEN_TINT[s.key])) for i, s in enumerate(S)]
                                + [("FONTNAME", (0, 1), (0, 1), "VN-B")]))
        self.story.append(tbl)
        self._gap()

        rr = "> 10" if (not np.isfinite(ss.risk_reward) or ss.risk_reward > 10) else num(ss.risk_reward, 2)
        summ = [["Tổng hợp theo xác suất", "Giá trị"],
                ["Giá trị kỳ vọng", f"<b>{num(ss.expected_price)}đ</b>"],
                ["Sinh lời kỳ vọng tổng", f"<b>{sgn(ss.expected_return)}</b>"],
                ["Sinh lời kỳ vọng mỗi năm", sgn(ss.expected_annual)],
                ["Lợi nhuận / rủi ro", f"{rr} lần"],
                ["Xác suất thua lỗ", pct(ss.prob_loss, 0)],
                ["Khuyến nghị", f"<b>{r.rating}</b>"]]
        tw = CONTENT_W * 0.46
        tbl2 = _table(summ, [tw * 0.6, tw * 0.4])
        if self._chart_on("scenario_bars"):
            fig = self._fig_flows(charts.scenario_bars(ss, self.tmp / "sb2.png"), CONTENT_W * 0.5, SRC_EST)
            self.story.append(self._row([tbl2, fig], [tw + 6 * mm, CONTENT_W - tw - 6 * mm], gap=0))
        else:
            self.story.append(tbl2)
        if self._chart_on("scenario_fan"):
            self._gap()
            self._fig(charts.scenario_fan(r.prices, ss, self.tmp / "fan.png", r.ticker), CONTENT_W, SRC_EST)
        if self._chart_on("sensitivity"):
            self._gap()
            self._fig(charts.sensitivity_heatmap(ss, self.tmp / "heat.png"), CONTENT_W, SRC_EST)
        self._h3("Cơ sở của giả định mặc định")
        self.story += [self._bullet(self._ev(e)) for e in r.evidence.by_kind("scenario")]

    # ------------------------------------------------------------------ thẻ bằng chứng
    def evidence_section(self):
        r = self.r
        self._h2("THẺ BẰNG CHỨNG")
        self.story.append(_p("Mỗi nhận định được gắn mã [E#]. Thẻ cho biết phép tính, số liệu sử dụng, công thức, kỳ dữ liệu và nguồn."))
        self._gap()
        kind = {"thesis": ("LUẬN ĐIỂM", "#15803D", "#F0FDF4"), "risk": ("RỦI RO", "#B91C1C", "#FEF2F2"),
                "scenario": ("GIẢ ĐỊNH", "#1E3A8A", "#EFF6FF"), "info": ("KHUYẾN NGHỊ", "#B45309", "#FFF7ED")}
        lw, w = 24 * mm, CONTENT_W
        for e in r.evidence.items:
            lbl, hexc, tint = kind.get(e.kind, ("THÔNG TIN", "#0F2A4A", "#E6EEF8"))
            col = colors.HexColor(hexc)
            badge = [Paragraph(f"<a name='{e.id}'/>{e.id}", ST["badge"]), Paragraph(lbl, ST["badge_s"])]
            rows = [[badge, Paragraph(e.claim, ST["claim"])]]
            if e.calc:
                rows.append([Paragraph("Phép tính", ST["lbl"]), Paragraph(f"<b>{e.calc}</b>", ST["cell"])])
            if e.metrics and self.o.detail != "brief":
                mt = Table([[Paragraph(a, ST["cell"]), Paragraph(str(b), ST["cellr"])] for a, b in e.metrics],
                           colWidths=[(w - lw - 10) * 0.5, (w - lw - 10) * 0.5])
                mt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                        ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
                rows.append([Paragraph("Số liệu", ST["lbl"]), mt])
            for name, val in (("Công thức", e.formula), ("Kỳ dữ liệu", e.period), ("Nguồn", e.source)):
                if val and val != "-":
                    rows.append([Paragraph(name, ST["lbl"]), Paragraph(val, ST["cell"])])
            t = Table(rows, colWidths=[lw, w - lw])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("BACKGROUND", (0, 0), (0, 0), col), ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(tint)),
                ("BOX", (0, 0), (-1, -1), 0.7, RULE), ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
                ("LINEBEFORE", (0, 1), (0, -1), 2.2, col),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]))
            self.story.append(KeepTogether([t, Spacer(1, GAP)]))

    def _timing_note(self) -> str:
        t, r = self.r.tech, self.r
        sup = t["supports"][0] if t["supports"] else None
        res = t["resistances"][0] if t["resistances"] else None
        if r.rating in ("MUA", "KHẢ QUAN"):
            if t["momentum_score"] < 40:
                return (f"Định giá hấp dẫn nhưng xu hướng ngắn hạn còn yếu (điểm động lượng {t['momentum_score']:.0f}/100): "
                        f"nên giải ngân từng phần; hỗ trợ gần nhất {num(sup, 1)} nghìn đ, gia tăng tỷ trọng khi giá vượt "
                        f"kháng cự {num(res, 1)} nghìn đ.")
            return f"Có thể tích luỹ quanh vùng giá hiện tại; hỗ trợ {num(sup, 1)}, kháng cự {num(res, 1)} nghìn đ."
        if r.rating == "NẮM GIỮ":
            return f"Tiếp tục nắm giữ, cân nhắc chốt lời từng phần khi giá tiếp cận kháng cự {num(res, 1)} nghìn đ."
        return f"Ưu tiên giảm tỷ trọng; ngưỡng cắt lỗ tham khảo dưới hỗ trợ {num(sup, 1)} nghìn đ."

    # ------------------------------------------------------------------ doanh nghiệp
    def company_section(self):
        r, p, mm_ = self.r, self.r.profile, self.r.val["multiples"]
        self._h2("1. TỔNG QUAN DOANH NGHIỆP")
        size = "lớn" if mm_["market_cap"] > 1e13 else ("vừa" if mm_["market_cap"] > 1e12 else "nhỏ")
        fin = r.fin
        rows = [["Thông tin", "Chi tiết"],
                ["Tên doanh nghiệp", p.name or "-"], ["Mã chứng khoán / Sàn", f"{r.ticker} / {p.exchange}"],
                ["Ngành ICB", " › ".join([x for x in (p.icb1, p.icb2, p.icb3, p.icb4) if x]) or "-"],
                ["Website", p.website or "-"],
                ["Số cổ phiếu lưu hành", f"{num(p.shares)} cổ phiếu"],
                ["Vốn hoá thị trường", f"{bil(mm_['market_cap'])} tỷ đồng (nhóm vốn hoá {size})"],
                ["Dữ liệu BCTC", f"{int(fin.index[0])} - {int(fin.index[-1])} ({len(fin)} năm)"]]
        self.story.append(_table(rows, [50 * mm, CONTENT_W - 50 * mm], align_right_from=9))
        rt = r.ratios.iloc[-1]
        self._h3("Phân tích DuPont: ROE = Biên LN ròng × Vòng quay tài sản × Đòn bẩy tài chính")
        dp = r.ratios[["dupont_margin", "dupont_turnover", "dupont_leverage", "roe"]].tail(self.o.years)
        rows = [["Năm", "Biên LN ròng (CĐ mẹ)", "Vòng quay tài sản", "Đòn bẩy (TS/VCSH)", "ROE"]]
        for y, x in dp.iterrows():
            rows.append([str(y), pct(x["dupont_margin"]), num(x["dupont_turnover"], 2), num(x["dupont_leverage"], 2), pct(x["roe"])])
        self.story.append(_table(rows, [CONTENT_W / 5] * 5))
        drv = "biên lợi nhuận" if rt["dupont_margin"] > 0.1 else ("đòn bẩy tài chính" if rt["dupont_leverage"] > 3 else "vòng quay tài sản")
        self._gap(6)
        self.story.append(_p(f"ROE {int(r.fin.index[-1])} đạt {pct(rt['roe'])}, động lực chính đến từ {drv}; đòn bẩy "
                             f"{num(rt['dupont_leverage'], 2)} lần, vòng quay tài sản {num(rt['dupont_turnover'], 2)} vòng/năm."))

    # ------------------------------------------------------------------ tài chính
    def financial_section(self):
        r = self.r
        self._h2("2. PHÂN TÍCH TÀI CHÍNH")
        w = CONTENT_W / 2 - 6
        n = self.o.years
        cells = []
        if self._chart_on("rev_profit"):
            cells.append(self._fig_flows(charts.revenue_profit(r.fin, r.ratios, self.tmp / "rev.png", years=n,
                                                               rev_label="Tổng TN hoạt động" if r.fin.attrs.get("is_bank") else "Doanh thu thuần"), w, SRC_FIN))
        if self._chart_on("profitability"):
            cells.append(self._fig_flows(charts.profitability(r.ratios, self.tmp / "prof.png", years=n), w, SRC_FIN))
        if self._chart_on("cashflow"):
            cells.append(self._fig_flows(charts.cashflow(r.fin, r.ratios, self.tmp / "cf.png", years=n), w, SRC_FIN))
        if self._chart_on("capital"):
            cells.append(self._fig_flows(charts.capital_structure(r.fin, r.ratios, self.tmp / "cap.png", years=n), w, SRC_FIN))
        self._grid(cells)

        self._h3("Bảng chỉ số tài chính", long_next=True)
        rt = r.ratios.tail(n)
        yrs = [str(y) for y in rt.index]
        spec = [("Sinh lời", None, None), ("Biên LN gộp", "gross_margin", "p"), ("Biên EBIT", "ebit_margin", "p"),
                ("Biên LN ròng", "net_margin", "p"), ("ROE", "roe", "p"), ("ROA", "roa", "p"), ("ROIC", "roic", "p"),
                ("Tăng trưởng", None, None), ("Doanh thu", "revenue_growth", "p"), ("LNST cổ đông mẹ", "npat_growth", "p"),
                ("Tổng tài sản", "assets_growth", "p"),
                ("Thanh khoản và đòn bẩy", None, None), ("Thanh toán hiện hành (lần)", "current_ratio", "x"),
                ("Thanh toán nhanh (lần)", "quick_ratio", "x"), ("Nợ vay/VCSH (lần)", "debt_to_equity", "x"),
                ("Nợ phải trả/Tổng tài sản", "liab_to_assets", "p"), ("Nợ ròng/EBITDA (lần)", "net_debt_to_ebitda", "x"),
                ("EBIT/Chi phí lãi vay (lần)", "interest_coverage", "x"),
                ("Hiệu quả hoạt động và dòng tiền", None, None), ("Vòng quay tài sản (lần)", "asset_turnover", "x"),
                ("Số ngày phải thu", "receivable_days", "d"), ("Số ngày tồn kho", "inventory_days", "d"),
                ("CFO/LNST (lần)", "cfo_to_npat", "x"), ("Dòng tiền tự do (tỷ đồng)", "fcf", "b")]
        grp_of = {"Sinh lời": "profitability", "Tăng trưởng": "growth", "Thanh khoản và đòn bẩy": "liquidity",
                  "Chất lượng tài sản và an toàn vốn": "liquidity", "Hiệu quả hoạt động và dòng tiền": "efficiency"}
        if r.fin.attrs.get("is_bank"):
            spec = [("Sinh lời", None, None), ("ROE", "roe", "p"), ("ROA", "roa", "p"),
                    ("NIM xấp xỉ (TN lãi thuần/TTS bình quân)", "nim_proxy", "p"), ("LNST/Tổng TN hoạt động", "net_margin", "p"),
                    ("CIR (Chi phí HĐ/TN hoạt động)", "cir", "p"),
                    ("Tăng trưởng", None, None), ("Tổng thu nhập hoạt động", "revenue_growth", "p"),
                    ("LNST cổ đông mẹ", "npat_growth", "p"), ("Cho vay khách hàng", "loan_growth", "p"),
                    ("Tiền gửi khách hàng", "deposit_growth", "p"),
                    ("Chất lượng tài sản và an toàn vốn", None, None), ("LDR (Cho vay/Tiền gửi)", "ldr", "p"),
                    ("Chi phí tín dụng", "credit_cost", "p"), ("Dự phòng/Cho vay", "llr", "p"),
                    ("VCSH/Tổng tài sản", "equity_to_assets", "p"), ("Đòn bẩy (TTS/VCSH, lần)", "dupont_leverage", "x")]
        rows = [["Chỉ tiêu"] + yrs]
        grp_rows, on = [], True
        for lbl, key, kind in spec:
            if key is None:
                on = grp_of.get(lbl, "") in self.o.metric_groups
                if on:
                    grp_rows.append(len(rows))
                    rows.append([f"<b>{lbl}</b>"] + [""] * len(yrs))
                continue
            if on:
                f = {"p": pct, "x": lambda v: num(v, 2), "d": lambda v: num(v, 0), "b": bil}[kind]
                rows.append([lbl] + [f(v) for v in rt[key]])
        self.story.append(_table(rows, [62 * mm] + [(CONTENT_W - 62 * mm) / len(yrs)] * len(yrs), highlight_rows=grp_rows))

        if r.fin.attrs.get("is_bank"):
            return
        if self.o.detail == "brief":
            self._gap(6)
            self.story.append(_p(f"Piotroski F-Score {r.fscore}/9; Altman Z'' {num(r.altman[0], 2)} ({r.altman[1].lower()})."))
            return
        self._h3(f"Sức khoẻ tài chính: Piotroski F-Score {r.fscore}/9, Altman Z'' {num(r.altman[0], 2)} ({r.altman[1].lower()})")
        rows = [[f"Tiêu chí Piotroski (năm {int(r.fin.index[-1])})", "Kết quả"]]
        rows += [[n_, "<font color='#15803D'>Đạt</font>" if ok else "<font color='#B91C1C'>Không đạt</font>"] for n_, ok in r.fscore_tests]
        self.story.append(_table(rows, [CONTENT_W * 0.75, CONTENT_W * 0.25]))

    # ------------------------------------------------------------------ định giá
    def _vp(self):
        from ..config import ValuationParams
        return getattr(self.r, "vparams", None) or ValuationParams()

    def valuation_section(self):
        r, v = self.r, self.r.val
        mm_ = v["multiples"]
        vp = self._vp()
        self._h2("3. ĐỊNH GIÁ NỘI TẠI (THAM CHIẾU)")
        self.story.append(_p("Ba phương pháp định giá nội tại dùng để đối chiếu với kết quả kịch bản."))
        self._gap()
        gd = v["growth_detail"]
        a = [["Giả định", "Giá trị", "Diễn giải"],
             ["Lãi suất phi rủi ro", pct(vp.risk_free), "Lợi suất TPCP 10 năm (xấp xỉ)"],
             ["Phần bù rủi ro thị trường", pct(vp.equity_risk_premium), "Thị trường mới nổi"],
             ["Beta áp dụng", num(v["beta_used"], 2), f"Beta đo được {num(r.tech.get('beta'), 2)}, giới hạn {num(vp.beta_floor, 1)}-{num(vp.beta_cap, 1)}"],
             ["Chi phí vốn chủ sở hữu (ke)", pct(v["ke"]), "ke = rf + β × ERP"],
             ["Tăng trưởng giai đoạn đầu (g)", pct(v["g"]), f"Trung vị: CAGR LNST {pct(gd['g_npat_3y'])}, CAGR DT {pct(gd['g_rev_3y'])}, "
                                                            f"ROE×(1-payout) {pct(gd['g_sustainable'])}"],
             ["Tăng trưởng dài hạn", pct(vp.terminal_growth), f"Giảm dần trong {vp.forecast_years} năm"]]
        self.story.append(_table(a, [55 * mm, 22 * mm, CONTENT_W - 77 * mm], align_right_from=1))
        self._h3("Kết quả theo phương pháp")
        rows = [["Phương pháp", "Giá trị (đ/cp)", "Trọng số", "Đóng góp (đ)"]]
        for m in v["methods"].values():
            rows.append([m["label"], num(m["value"]), pct(m.get("weight", 0), 0), num(m["value"] * m.get("weight", 0))])
        rows.append(["<b>Giá trị hợp lý (làm tròn)</b>", f"<b>{num(v['target_price'])}</b>", "100%", sgn(v["upside"])])
        self.story.append(_table(rows, [CONTENT_W * 0.46, CONTENT_W * 0.18, CONTENT_W * 0.14, CONTENT_W * 0.22],
                                 highlight_rows=[len(rows) - 1]))
        if v["methods"] and self._chart_on("football"):
            self._gap()
            self._fig(charts.football_field(v, self.tmp / "ff.png"), CONTENT_W, SRC_VAL)

        if "dcf" in v["methods"] and self.o.detail != "brief":
            self._h3("Chi tiết mô hình DCF (đồng/cổ phiếu)")
            tb = v["methods"]["dcf"]["table"]
            rows = [["Năm dự phóng", "Tăng trưởng", "EPS", "Tỷ lệ tái đầu tư", "FCFE/CP", "Giá trị hiện tại"]]
            for _, x in tb.iterrows():
                rows.append([f"N+{int(x['Năm'])}", pct(x["Tăng trưởng"]), num(x["EPS"]), pct(x["Tỷ lệ tái đầu tư"]),
                             num(x["FCFE/CP"]), num(x["PV"])])
            rows.append(["Giá trị cuối kỳ", "", "", "", num(tb.attrs["tv"]), num(tb.attrs["pv_tv"])])
            rows.append(["<b>Tổng giá trị nội tại</b>", "", "", "", "", f"<b>{num(v['methods']['dcf']['value'])}</b>"])
            self.story.append(_table(rows, [CONTENT_W / 6] * 6, highlight_rows=[len(rows) - 1]))
            self._h3("Độ nhạy giá trị DCF theo chi phí vốn (ke) và tăng trưởng dài hạn (g)")
            sens = v["sensitivity"]
            rows = [["ke \\ g"] + [c.replace(".", ",") for c in sens.columns]] + \
                   [[i.replace(".", ",")] + [num(x) for x in row] for i, row in sens.iterrows()]
            self.story.append(_table(rows, [CONTENT_W / 4] * 4))

        self._h3("Bội số định giá hiện tại")
        hs = v["hist_pe_stats"]
        rows = [["Bội số", "Giá trị", "Diễn giải"],
                [f"P/E (LNST {mm_['fiscal_year']})", times(mm_["pe"]), f"12 tháng: {times(hs['min'])} - {times(hs['max'])}, BQ {times(hs['avg'])}"],
                ["P/B", times(mm_["pb"]), f"BVPS {num(mm_['bvps'])}đ"],
                ["P/S", times(mm_["ps"], 2), "Vốn hoá / doanh thu"],
                ["EV/EBITDA", times(mm_["ev_ebitda"]), f"EV {bil(mm_['ev'])} tỷ đồng"],
                ["Tỷ suất lợi nhuận (1/PE)", pct(mm_["earnings_yield"]), f"So với ke {pct(v['ke'])}"],
                ["Tỷ suất cổ tức", pct(mm_["div_yield"]), "Cổ tức năm gần nhất / vốn hoá"]]
        tw = CONTENT_W * 0.52
        tbl = _table(rows, [tw * 0.38, tw * 0.17, tw * 0.45], align_right_from=1)
        if self._chart_on("pe_band"):
            fig = self._fig_flows(charts.pe_band(v["hist_pe"], mm_["pe"], self.tmp / "pe.png"), CONTENT_W - tw - 6 * mm, SRC_VAL)
            self.story.append(self._row([tbl, fig], [tw + 6 * mm, CONTENT_W - tw - 6 * mm], gap=0))
        else:
            self.story.append(tbl)

    # ------------------------------------------------------------------ kỹ thuật
    def technical_section(self):
        r, t = self.r, self.r.tech
        self._h2("4. PHÂN TÍCH KỸ THUẬT")
        if self._chart_on("price_tech"):
            self._fig(charts.price_technical(r.prices, r.ticker, self.tmp / "tech.png", (t["supports"], t["resistances"])),
                      CONTENT_W, SRC_PX)
            self._gap()
        rows = [["Tín hiệu", "Đánh giá"]]
        for s, sg in t["signals"]:
            rows.append([s, {1: "<font color='#15803D'>Tích cực</font>", -1: "<font color='#B91C1C'>Tiêu cực</font>",
                             0: f"<font color='{HEX_INK2}'>Trung tính</font>"}[sg]])
        w = CONTENT_W * 0.5
        t1 = _table(rows, [w * 0.7, w * 0.3])
        stats = [["Thống kê", "Giá trị"],
                 ["Xu hướng tổng hợp", t["trend"]],
                 ["Sinh lời 1 tháng / 3 tháng", f"{sgn(t['ret_1m'])} / {sgn(t['ret_3m'])}"],
                 ["Sinh lời 12 tháng", sgn(t["ret_1y"])],
                 ["Sức mạnh tương đối 3 tháng", sgn(t.get("rs_3m"))],
                 ["Biến động năm hoá", pct(t["volatility"])],
                 ["Mức sụt giảm tối đa 12 tháng", pct(t["max_drawdown"])],
                 ["Beta / tương quan VN-Index", f"{num(t.get('beta'), 2)} / {num(t.get('corr'), 2)}"],
                 ["Hỗ trợ (nghìn đ)", ", ".join(num(x, 1) for x in t["supports"])],
                 ["Kháng cự (nghìn đ)", ", ".join(num(x, 1) for x in t["resistances"])]]
        w2 = CONTENT_W - w - 6 * mm
        t2 = _table(stats, [w2 * 0.58, w2 * 0.42])
        self.story.append(self._row([t1, t2], [w + 6 * mm, w2], gap=0))
        self._gap()
        self.story.append(_p(f"Điểm động lượng <b>{t['momentum_score']:.0f}/100</b>, điểm an toàn <b>{t['risk_score']:.0f}/100</b>. "
                             f"{self._timing_note()}"))

    # ------------------------------------------------------------------ ngành
    def peers_section(self):
        r = self.r
        if r.peers is None or r.peers.empty:
            return
        self._h2("5. SO SÁNH VỚI DOANH NGHIỆP CÙNG NGÀNH")
        ps = r.peer_summary
        self.story.append(_p(f"Nhóm so sánh: <b>{r.peer_level}</b>, {ps.get('n_peers', 0)} doanh nghiệp có doanh thu lớn nhất, "
                             f"số liệu năm {ps.get('year')}."))
        self._gap()
        cols = list(r.peers.columns)
        two_dec = ("Nợ vay/VCSH", "Thanh toán hiện hành")
        rows = [cols]
        for _, x in r.peers.iterrows():
            rows.append([f"<b>{x[c]}</b>" if c == "Mã" and x[c] == r.ticker else (x[c] if c == "Mã" else
                        (num(x[c]) if "(tỷ)" in c else (num(x[c], 2) if c in two_dec else pct(x[c])))) for c in cols])
        med = ps.get("median")
        if med is not None:
            rows.append(["Trung vị"] + [num(med.get(c)) if "(tỷ)" in c else (num(med.get(c), 2) if c in two_dec else pct(med.get(c)))
                                         for c in cols[1:]])
        cw = [16 * mm] + [(CONTENT_W - 16 * mm) / (len(cols) - 1)] * (len(cols) - 1)
        self.story.append(_table(rows, cw, font_size=6.8, highlight_rows=[1, len(rows) - 1]))
        if self._chart_on("peers"):
            self._gap()
            self._fig(charts.peer_bars(r.peers, r.ticker, self.tmp / "peer.png"), CONTENT_W, SRC_PEER)

    # ------------------------------------------------------------------ tin tức
    def news_section(self):
        nw = self.r.news
        self._h2("6. TIN TỨC VÀ CẢM XÚC THỊ TRƯỜNG")
        evt = pd.Series([it["event"] for it in nw["items"]]).value_counts()
        erows = [["Loại sự kiện", "Số tin"]] + [[escape(k), str(v)] for k, v in evt.items()]
        tw = CONTENT_W * 0.45
        etbl = _table(erows, [tw * 0.75, tw * 0.25])
        if self._chart_on("news"):
            fig = self._fig_flows(charts.news_sentiment(nw, self.tmp / "news.png"), CONTENT_W - tw - 6 * mm, SRC_NEWS)
            self.story.append(self._row([fig, etbl], [CONTENT_W - tw, tw], gap=6 * mm))
        else:
            self.story.append(etbl)
        self._h3("Tin gần đây", long_next=True)
        rows = [["Ngày", "Tiêu đề", "Loại sự kiện", "Cảm xúc"]]
        for it in nw["items"][:{"brief": 8, "standard": 15, "detailed": 25}[self.o.detail]]:
            s = it["sentiment"]
            rows.append([it["date"][:10], f"<link href='{escape(it['link'])}'>{escape(it['title'])}</link>", escape(it["event"]),
                         sgn(s, f"{s:+.2f}".replace(".", ","))])
        self.story.append(_table(rows, [18 * mm, CONTENT_W - 18 * mm - 34 * mm - 15 * mm, 34 * mm, 15 * mm],
                                 align_right_from=3, font_size=6.9))

    # ------------------------------------------------------------------ rủi ro
    def risk_section(self):
        r = self.r
        self._h2("7. RỦI RO VÀ ĐIỂM ĐÁNH GIÁ")
        self.story += [self._bullet(self._ev(e)) for e in r.evidence.by_kind("risk")]
        self._h3("Điểm đánh giá đa yếu tố")
        lbl = {"fundamental": "Cơ bản (sinh lời, tăng trưởng, đòn bẩy, chất lượng lợi nhuận)",
               "valuation": "Định giá (tiềm năng so với giá trị hợp lý)",
               "momentum": "Động lượng (xu hướng, MACD, RSI, sức mạnh tương đối)",
               "risk": "An toàn (biến động, sụt giảm, beta, thanh khoản)",
               "news": "Tin tức (cảm xúc tiêu đề gần đây)"}
        c = r.composite
        rows = [["Yếu tố", "Điểm", "Trọng số", "Đóng góp"]]
        for k in lbl:
            rows.append([lbl[k], num(c["components"][k]), pct(c["weights"][k], 0), num(c["components"][k] * c["weights"][k], 1)])
        rows.append(["<b>Tổng điểm</b>", f"<b>{num(c['total'])}</b>", "100%", ""])
        self.story.append(_table(rows, [CONTENT_W * 0.58, CONTENT_W * 0.12, CONTENT_W * 0.14, CONTENT_W * 0.16],
                                 highlight_rows=[len(rows) - 1]))
        self._gap()
        self.story.append(_p(f"Khuyến nghị <b>{r.rating}</b>: {r.rating_reason}."))

    # ------------------------------------------------------------------ phụ lục
    def appendix_section(self):
        r = self.r
        self._h2("PHỤ LỤC: BÁO CÁO TÀI CHÍNH TÓM TẮT (TỶ ĐỒNG)")
        fin = r.fin.tail(self.o.years)
        yrs = [str(y) for y in fin.index]
        groups = [("Kết quả kinh doanh", ["revenue", "cogs", "gross_profit", "selling_exp", "admin_exp", "fin_income", "fin_exp",
                                          "interest_exp", "ebit", "ebitda", "pbt", "npat", "npat_parent"]),
                  ("Bảng cân đối kế toán", ["total_assets", "current_assets", "cash", "st_investments", "receivables", "inventory",
                                            "fixed_assets", "liabilities", "current_liab", "lt_liab", "st_debt", "lt_debt",
                                            "equity", "minority_equity", "share_capital", "retained_earnings"]),
                  ("Lưu chuyển tiền tệ", ["cfo", "cfi", "cff", "capex", "depreciation", "dividends_paid"])]
        if r.fin.attrs.get("is_bank"):
            groups = [("Kết quả kinh doanh", ["revenue", "nii", "fee_income", "opex", "ppop", "provision", "pbt", "npat", "npat_parent"]),
                      ("Bảng cân đối kế toán", ["total_assets", "loans", "loan_reserve", "deposits", "liabilities", "equity",
                                                "share_capital", "retained_earnings"]),
                      ("Lưu chuyển tiền tệ", ["cfo", "cfi", "cff", "capex", "dividends_paid"])]
        for i, (title, keys) in enumerate(groups):
            rows = [[title] + yrs]
            for k in keys:
                if fin[k].notna().any():
                    rows.append([FIELD_LABEL_VI.get(k, k)] + [bil(x) for x in fin[k]])
            if i:
                self._gap()
            self.story.append(_table(rows, [60 * mm] + [(CONTENT_W - 60 * mm) / len(yrs)] * len(yrs), font_size=7.1))

    # ------------------------------------------------------------------ nguồn & miễn trừ
    def sources_disclaimer(self):
        r = self.r
        self._h2("NGUỒN DỮ LIỆU VÀ MIỄN TRỪ TRÁCH NHIỆM")
        rows = [["Hạng mục", "Nguồn"]] + [[k, v] for k, v in r.data_sources.items()]
        self.story.append(_table(rows, [35 * mm, CONTENT_W - 35 * mm], align_right_from=9))
        self._h3("Ghi chú phương pháp")
        notes = ["Giá cổ phiếu là giá đã điều chỉnh cho cổ tức và cổ phiếu thưởng. BCTC năm Y được coi là công bố từ 01/04 năm Y+1.",
                 "EPS và BVPS tính trên số cổ phiếu lưu hành hiện tại, có thể khác EPS công bố do phát hành thêm sau kỳ báo cáo.",
                 "Định giá dùng BCTC năm; kết quả phụ thuộc giả định và cần được chuyên viên phân tích rà soát.",
                 f"Ngày lập báo cáo: {r.created_at:%d/%m/%Y}. Mẫu báo cáo: "
                 f"{PURPOSE_PRESETS.get(self.o.purpose, {}).get('label', self.o.purpose)}, mức chi tiết "
                 f"{DETAIL_LABEL.get(self.o.detail, '').lower()}."]
        notes += [f"Lưu ý dữ liệu: {w}" for w in r.warnings]
        self.story += [self._bullet(n_) for n_ in notes]
        self._h3("Miễn trừ trách nhiệm")
        self.story.append(_p("Báo cáo được lập từ các nguồn dữ liệu công khai được cho là đáng tin cậy nhưng không đảm bảo tuyệt đối "
                             "chính xác hay đầy đủ. Nội dung chỉ nhằm mục đích tham khảo, nghiên cứu và học tập; không phải lời "
                             "khuyên đầu tư hay lời mời mua hoặc bán chứng khoán. Nhà đầu tư tự chịu trách nhiệm với quyết định của mình."))

    # ------------------------------------------------------------------ dựng
    def build(self) -> Path:
        secs = self.o.sections
        if "summary" in secs:
            self.summary_page()
        mapping = [("scenario", self.scenario_section), ("company", self.company_section), ("financial", self.financial_section),
                   ("valuation", self.valuation_section), ("technical", self.technical_section),
                   ("peers", self.peers_section), ("news", self.news_section), ("risk", self.risk_section),
                   ("evidence", self.evidence_section), ("appendix", self.appendix_section)]
        for key, fn in mapping:
            if key in secs:
                fn()
        self.sources_disclaimer()
        doc = SimpleDocTemplate(str(self.out), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                                topMargin=19 * mm, bottomMargin=15 * mm,
                                title=f"Báo cáo phân tích cổ phiếu {self.r.ticker}", author="VNEquity Research",
                                subject=f"{self.r.ticker} - {self.r.rating}")
        doc.build(self.story, onFirstPage=self._on_page, onLaterPages=self._on_page)
        return self.out


def build_pdf(result, out_path=None, options: ReportOptions | None = None) -> Path:
    return ReportBuilder(result, out_path, options=options).build()
