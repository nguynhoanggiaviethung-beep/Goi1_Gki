"""PDF danh sách cơ hội đầu tư (kết quả bộ lọc toàn thị trường)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from ..config import REPORT_DIR
from . import pdf_report as P
from .fmt import num, pct


def build_screener_pdf(df: pd.DataFrame, params: dict, out: Path | None = None, top: int = 30) -> Path:
    P._register_fonts()
    P.ST = P._styles()
    now = datetime.now()
    out = Path(out) if out else REPORT_DIR / f"SANG_LOC_CO_HOI_{now:%Y%m%d_%H%M}.pdf"
    page = landscape(A4)
    cw = page[0] - 2 * P.MARGIN
    story = [P._p("DANH SÁCH CƠ HỘI ĐẦU TƯ - SÀNG LỌC CHẤT LƯỢNG CƠ BẢN", "h1"),
             P._p(f"Ngày tạo {now:%d/%m/%Y %H:%M} | Tiêu chí: " + "; ".join(f"{k}: {v}" for k, v in params.items()) +
                  f" | {len(df)} doanh nghiệp đạt điều kiện, hiển thị top {min(top, len(df))}.", "h1sub"),
             Spacer(1, 6)]
    d = df.head(top)
    cols = ["#", "Mã", "Sàn", "Ngành", "Năm", "Doanh thu (tỷ)", "LNST CĐ mẹ (tỷ)", "ROE", "CAGR LN 3N", "Biên LN ròng",
            "Nợ vay/VCSH", "CFO/LNST", "F-Score", "Z''", "Điểm"]
    extra = [c for c in ("Giá (đ)", "P/E", "P/B", "PEG") if c in d.columns]
    cols += extra
    rows = [cols]
    for i, x in d.iterrows():
        row = [str(i), f"<b>{x['Mã']}</b>", x["Sàn"], x["Ngành"], str(x["Năm"]), num(x["Doanh thu (tỷ)"]),
               num(x["LNST CĐ mẹ (tỷ)"]), pct(x["ROE"]), pct(x["CAGR LN 3N"]), pct(x["Biên LN ròng"]),
               num(x["Nợ vay/VCSH"], 2), num(x["CFO/LNST"], 2), str(int(x["F-Score"])), num(x["Z''"], 2),
               f"<b>{num(x['Điểm chất lượng'], 0)}</b>"]
        for c in extra:
            row.append(num(x[c]) if c == "Giá (đ)" else num(x[c], 1 if c != "PEG" else 2))
        rows.append(row)
    n_extra = len(extra)
    base = [9 * mm, 13 * mm, 11 * mm, 40 * mm, 11 * mm]
    rest = (cw - sum(base)) / (len(cols) - len(base))
    story.append(P._table(rows, base + [rest] * (len(cols) - len(base)), align_right_from=4, font_size=6.6))
    story.append(Spacer(1, 6))

    import matplotlib.pyplot as plt
    from .charts import NAVY, ORANGE, _save
    fig, ax = plt.subplots(figsize=(10, 3.2))
    sc = ax.scatter(df["CAGR LN 3N"].clip(-0.3, 0.8) * 100, df["ROE"].clip(-0.1, 0.6) * 100,
                    s=(df["Doanh thu (tỷ)"].clip(upper=100000) / 400) + 6, c=df["Điểm chất lượng"], cmap="RdYlGn", alpha=0.75)
    for _, x in d.head(15).iterrows():
        ax.annotate(x["Mã"], (min(x["CAGR LN 3N"], 0.8) * 100, min(x["ROE"], 0.6) * 100), fontsize=6.5, color=NAVY,
                    xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("Tăng trưởng LNST 3 năm (CAGR, %)")
    ax.set_ylabel("ROE (%)")
    ax.set_title("Bản đồ chất lượng - tăng trưởng (kích thước = doanh thu, màu = điểm chất lượng)", loc="left")
    plt.colorbar(sc, ax=ax, pad=0.01).set_label("Điểm")
    tmp = REPORT_DIR / ".screener_map.png"
    _save(fig, tmp)
    story.append(Image(str(tmp), width=cw, height=cw * 3.2 / 10))
    story.append(Spacer(1, 4))
    story.append(P._p("Phương pháp: điểm chất lượng (0-100) là trung bình của các điểm thành phần ROE, CAGR LNST 3 năm, "
                      "biên LN ròng, đòn bẩy (nghịch), CFO/LNST, Piotroski F-Score và Altman Z''. Dữ liệu BCTC hợp nhất "
                      "năm gần nhất. Danh sách là điểm khởi đầu để phân tích sâu bằng lệnh <b>analyze</b>, không phải khuyến nghị.", "small"))

    def on_page(c, doc):
        c.saveState()
        c.setFillColor(P.NAVY)
        c.rect(0, page[1] - 11 * mm, page[0], 11 * mm, stroke=0, fill=1)
        c.setFillColor(P.colors.white)
        c.setFont("VN-B", 9.5)
        c.drawString(P.MARGIN, page[1] - 7 * mm, "VNEQUITY RESEARCH  |  SÀNG LỌC CƠ HỘI ĐẦU TƯ")
        c.setFont("VN", 6.5)
        c.setFillColor(P.INK2)
        c.drawRightString(page[0] - P.MARGIN, 7 * mm, f"Trang {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(str(out), pagesize=page, leftMargin=P.MARGIN, rightMargin=P.MARGIN,
                            topMargin=16 * mm, bottomMargin=12 * mm, title="Sàng lọc cơ hội đầu tư", author="VNEquity")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return out
