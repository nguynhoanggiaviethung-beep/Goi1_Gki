"""Thu thập tin tức doanh nghiệp & chấm điểm cảm xúc (sentiment) tiếng Việt bằng từ điển.

Nguồn: CafeF (trang Tin doanh nghiệp theo mã + API AJAX), VnExpress RSS Kinh doanh.
Có cache tại data/cache/news_<MÃ>.json để chạy offline.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import requests

from ..config import CACHE_DIR, HTTP_HEADERS, HTTP_TIMEOUT

POSITIVE = [
    "kỷ lục", "tăng trưởng", "tăng mạnh", "lãi lớn", "lãi kỷ lục", "vượt kế hoạch", "vượt", "bứt phá", "dẫn đầu",
    "hợp đồng mới", "ký kết", "mở rộng", "thâu tóm", "mua lại", "cổ tức", "thưởng", "khả quan", "tích cực",
    "thăng hoa", "nâng hạng", "khuyến nghị mua", "mua vào", "tăng vốn", "đột phá", "lợi nhuận tăng", "doanh thu tăng",
    "top", "giải thưởng", "hợp tác", "bắt tay", "cổ đông mới", "tạo việc làm", "tái sinh", "đóng góp",
]
NEGATIVE = [
    "giảm", "sụt", "lỗ", "thua lỗ", "hạ nhiệt", "lao dốc", "bán tháo", "bán ra", "thoái vốn", "phạt", "vi phạm",
    "khởi tố", "điều tra", "nợ xấu", "cảnh báo", "kiểm soát", "đình chỉ", "hủy niêm yết", "cắt giảm", "rời",
    "từ nhiệm", "chậm", "khó khăn", "rủi ro", "áp lực", "ngược dòng", "chỉ tăng", "suy giảm", "tiêu cực", "kiện",
]
EVENT_RULES = [
    ("Sự kiện quyền / cổ tức", ["cổ tức", "thưởng", "gdkhq", "phát hành", "phcp", "tăng vốn", "niêm yết bổ sung", "esop"]),
    ("Quản trị / nhân sự", ["hđqt", "nghị quyết", "điều lệ", "tgđ", "ghế nóng", "chủ tịch", "quản trị", "bổ nhiệm", "từ nhiệm"]),
    ("Kinh doanh / M&A", ["hợp đồng", "thâu tóm", "mua lại", "chuyển nhượng", "dự án", "khách hàng", "doanh thu", "lợi nhuận", "bắt tay", "hợp tác"]),
    ("Thị trường / cổ phiếu", ["cổ phiếu", "cổ đông", "giao dịch", "khối ngoại", "định giá", "khuyến nghị"]),
]


def score_sentiment(text: str) -> float:
    """Điểm cảm xúc trong [-1, 1] dựa trên số từ khoá tích cực/tiêu cực."""
    t = text.lower()
    pos = sum(1 for w in POSITIVE if w in t)
    neg = sum(1 for w in NEGATIVE if w in t)
    if pos == neg == 0:
        return 0.0
    return round((pos - neg) / (pos + neg), 2)


def classify_event(text: str) -> str:
    t = text.lower()
    for label, kws in EVENT_RULES:
        if any(k in t for k in kws):
            return label
    return "Khác"


def _parse_cafef_html(html: str) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        if len(title) < 15:
            continue
        href = a["href"]
        if not href.endswith(".chn"):
            continue
        if href.startswith("/"):
            href = "https://cafef.vn" + href
        # tìm ngày ở phần tử cha gần nhất
        date = ""
        par = a.find_parent(["li", "div", "tr"])
        if par:
            m = re.search(r"(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)", par.get_text(" ", strip=True))
            if m:
                date = m.group(1)
        items.append({"title": title, "date": date, "link": href.split("?")[0]})
    seen, out = set(), []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            out.append(it)
    return out


def _from_cafef(ticker: str) -> list[dict]:
    urls = [
        f"https://cafef.vn/du-lieu/Ajax/Events_RelatedNews_New.aspx?symbol={ticker}&floorID=0&configID=0&PageIndex=1&PageSize=30&Type=2",
        f"https://cafef.vn/du-lieu/tin-doanh-nghiep/{ticker.lower()}/event.chn",
    ]
    for u in urls:
        try:
            r = requests.get(u, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            if r.ok:
                items = _parse_cafef_html(r.text)
                if items:
                    return items
        except Exception:  # noqa: BLE001
            continue
    return []


def _from_vnexpress(ticker: str, name_kw: str = "") -> list[dict]:
    try:
        r = requests.get("https://vnexpress.net/rss/kinh-doanh.rss", headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for m in re.finditer(r"<item>(.*?)</item>", r.text, re.S):
        block = m.group(1)
        title = re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"<title>(.*?)</title>", block, re.S) or [None, ""])[1]).strip()
        link = (re.search(r"<link>(.*?)</link>", block, re.S) or [None, ""])[1].strip()
        date = (re.search(r"<pubDate>(.*?)</pubDate>", block, re.S) or [None, ""])[1].strip()
        if re.search(rf"\b{ticker}\b", title) or (name_kw and name_kw.lower() in title.lower()):
            out.append({"title": title, "date": date, "link": link})
    return out


def get_news(ticker: str, offline: bool = False, limit: int = 25, name_kw: str = "") -> dict:
    ticker = ticker.upper()
    cache = CACHE_DIR / f"news_{ticker}.json"
    data = None
    if not offline:
        items = _from_cafef(ticker) + _from_vnexpress(ticker, name_kw)
        if items:
            data = {"ticker": ticker, "source": "CafeF + VnExpress (trực tuyến)",
                    "fetched_at": datetime.now().isoformat(timespec="minutes"), "items": items}
            cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if data is None and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        data["source"] = data.get("source", "") + " — cache cục bộ"
    if data is None:
        data = {"ticker": ticker, "source": "Không có dữ liệu tin tức", "fetched_at": "", "items": []}

    items = data["items"][:limit]
    for it in items:
        it["sentiment"] = score_sentiment(it["title"])
        it["event"] = classify_event(it["title"])
    data["items"] = items
    scores = [it["sentiment"] for it in items]
    data["avg_sentiment"] = round(sum(scores) / len(scores), 3) if scores else 0.0
    data["n_pos"] = sum(1 for s in scores if s > 0)
    data["n_neg"] = sum(1 for s in scores if s < 0)
    data["n_neu"] = sum(1 for s in scores if s == 0)
    return data
