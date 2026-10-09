"""Thu thập tin tức doanh nghiệp & chấm điểm cảm xúc (sentiment) tiếng Việt bằng từ điển.

Nguồn: CafeF (danh sách tin theo mã) + RSS CafeF, VnExpress, VietnamNet, Tin Nhanh Chứng Khoán, VnEconomy
(chỉ giữ tin có TIÊU ĐỀ nhắc đúng mã CK viết hoa hoặc nguyên cụm tên doanh nghiệp; liên kết kiểm tra đúng domain nguồn).
Có cache tại data/cache/news_<MÃ>.json để chạy offline.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse, urlunparse

import requests

from ..config import CACHE_DIR, HTTP_HEADERS, HTTP_TIMEOUT

VN_TZ = timezone(timedelta(hours=7))

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


# ----------------------------------------------------------------------------------------- lọc & chuẩn hoá
_PREFIX = re.compile(r"^(công ty|cty|ctcp|tổng công ty|tập đoàn|ngân hàng thương mại cổ phần|ngân hàng tmcp|ngân hàng)"
                     r"(\s+(cổ phần|tnhh|trách nhiệm hữu hạn))?\s+", re.I)
_GENERIC = {"việt nam", "đầu tư", "phát triển", "xây dựng", "thương mại", "dịch vụ", "sản xuất", "chứng khoán", "tài chính",
            "bất động sản", "năng lượng", "công nghệ", "thực phẩm", "vận tải"}


def name_aliases(name: str = "", short_name: str = "") -> list[str]:
    """Cụm tên đủ đặc trưng để nhận diện doanh nghiệp trong tiêu đề (không dùng từ đơn lẻ dễ trùng)."""
    out = []
    for raw in (short_name, name, _PREFIX.sub("", name.strip())):
        a = re.sub(r"\s+", " ", raw or "").strip()
        if len(a) >= 4 and a.lower() not in _GENERIC and len(a.split()) <= 6 and not a.lower().startswith(("công ty", "ctcp")):
            out.append(a)
    return list(dict.fromkeys(out))


def other_company_phrases(ticker: str) -> list[str]:
    """Tên doanh nghiệp NIÊM YẾT KHÁC có chứa mã này (VD 'FPT Retail' là FRT, 'Chứng khoán FPT' là FTS)."""
    try:
        from .company import _companies
        df = _companies()
    except Exception:  # noqa: BLE001
        return []
    t = ticker.upper()
    pat = re.compile(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])")
    out = []
    for _, r in df[df["ticker"] != t].iterrows():
        for nm in (r.get("short_name", ""), _PREFIX.sub("", str(r.get("name", "")))):
            if nm and pat.search(nm) and nm.strip().upper() != t:
                out.append(nm.strip())
    out += EXTRA_OTHER.get(t, [])
    return sorted(set(out), key=len, reverse=True)


# Thương hiệu tiếng Anh của doanh nghiệp niêm yết khác chưa có trong danh mục tên
EXTRA_OTHER = {"FPT": ["FPT Retail", "FPT Shop", "FPT Long Châu", "FPT Securities", "FPTS"],
}


def mentions(text: str, ticker: str, aliases: list[str] = (), exclude: list[str] = ()) -> bool:
    """Tiêu đề nhắc tới doanh nghiệp: mã CK viết hoa đứng riêng (FPT, không khớp 'FPTS' hay 'fpt.com'),
    hoặc nguyên cụm tên doanh nghiệp. Cụm tên của doanh nghiệp niêm yết khác chứa mã (exclude) bị bỏ qua trước."""
    for ph in exclude:
        text = re.sub(re.escape(ph), " ", text, flags=re.I)
    if re.search(rf"(?<![A-Za-z0-9À-ỹ.]){re.escape(ticker.upper())}(?![A-Za-z0-9À-ỹ])", text):
        return True
    low = text.lower()
    return any(re.search(rf"(?<![\wÀ-ỹ]){re.escape(a.lower())}(?![\wÀ-ỹ])", low) for a in aliases)


def clean_text(x: str) -> str:
    x = re.sub(r"<!\[CDATA\[|\]\]>", "", x or "")
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", html.unescape(x)).strip()


def clean_url(url: str, base: str = "", domains: tuple = ()) -> str:
    """Liên kết tuyệt đối http(s), bỏ tham số theo dõi; nếu khai báo domain thì phải thuộc domain đó."""
    u = html.unescape(clean_text(url)).strip()
    if base:
        u = urljoin(base, u)
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        return ""
    if domains and not any(p.hostname == d or p.hostname.endswith("." + d) for d in domains):
        return ""
    q = "&".join(kv for kv in p.query.split("&") if kv and not kv.lower().startswith(("utm_", "fbclid", "zarsrc")))
    return urlunparse((p.scheme, p.netloc, p.path, "", q, ""))


def parse_date(x: str) -> datetime | None:
    x = (x or "").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(x[:25] if "T" in x else x, fmt)
            return d.replace(tzinfo=None)
        except ValueError:
            continue
    try:
        return parsedate_to_datetime(x).astimezone(VN_TZ).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return None


def _parse_cafef_html(html_text: str, ticker: str, aliases: list[str] = (), page_is_list: bool = True,
                      exclude: list[str] = ()) -> list[dict]:
    """Danh sách tin trên CafeF. Trang danh sách theo mã (AJAX) chỉ chứa tin của mã đó; với trang đầy đủ chỉ giữ
    tin công bố của đúng mã (/du-lieu/<MÃ>-...) hoặc tiêu đề nhắc tới doanh nghiệp, bỏ menu và tin nổi bật toàn trang."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_text, "html.parser")
    items, own = [], re.compile(rf"/du-lieu/{re.escape(ticker.upper())}-\d+/", re.I)
    for a in soup.find_all("a", href=True):
        title = clean_text(a.get("title") or a.get_text(" ", strip=True))
        href = clean_url(a["href"], "https://cafef.vn", ("cafef.vn",))
        if len(title) < 15 or not href or not href.endswith(".chn"):
            continue
        if not page_is_list and not (own.search(href) or mentions(title, ticker, aliases, exclude)):
            continue
        date = ""
        par = a.find_parent(["li", "div", "tr"])
        if par:
            m = re.search(r"(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)", par.get_text(" ", strip=True))
            if m:
                date = m.group(1)
        items.append({"title": title, "date": date, "link": href})
    return items


def _from_cafef(ticker: str, aliases: list[str] = (), exclude: list[str] = ()) -> list[dict]:
    t = ticker.upper()
    urls = [
        (f"https://cafef.vn/du-lieu/Ajax/Events_RelatedNews_New.aspx?symbol={t}&floorID=0&configID=0&PageIndex=1&PageSize=30&Type=2", True),
        (f"https://s.cafef.vn/Ajax/Events_RelatedNews_New.aspx?symbol={t}&floorID=0&configID=0&PageIndex=1&PageSize=30&Type=2", True),
        (f"https://cafef.vn/du-lieu/tin-doanh-nghiep/{t.lower()}/event.chn", False),
    ]
    for u, is_list in urls:
        try:
            r = requests.get(u, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            if r.ok:
                items = _parse_cafef_html(r.text, t, aliases, page_is_list=is_list, exclude=exclude)
                if items:
                    for it in items:
                        it["source"], it["match"] = "CafeF - tin theo mã", "Tin theo mã"
                    return items
        except Exception:  # noqa: BLE001
            continue
    return []


RSS_FEEDS = {   # các feed công khai (giữ nguyên danh sách nguồn của dự án)
    "CafeF": ("https://cafef.vn/doanh-nghiep.rss", ("cafef.vn",)),
    "CafeBiz": ("https://cafebiz.vn/trang-chu.rss", ("cafebiz.vn",)),
    "VnExpress": ("https://vnexpress.net/rss/kinh-doanh.rss", ("vnexpress.net",)),
    "VietnamNet": ("https://vietnamnet.vn/kinh-doanh/index.rss", ("vietnamnet.vn",)),
    "Tin Nhanh Chứng Khoán": ("https://www.tinnhanhchungkhoan.vn/rss/home.rss", ("tinnhanhchungkhoan.vn",)),
    "VnEconomy": ("https://vneconomy.vn/tai-chinh.rss", ("vneconomy.vn",)),
}


def _from_rss(name: str, url: str, domains: tuple, ticker: str, aliases: list[str], exclude: list[str] = ()) -> list[dict]:
    import xml.etree.ElementTree as ET

    r = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    atom = "{http://www.w3.org/2005/Atom}"
    out = []
    for it in root.findall(".//item") or root.findall(f".//{atom}entry"):
        title = clean_text(it.findtext("title") or it.findtext(f"{atom}title") or "")
        desc = clean_text(it.findtext("description") or it.findtext(f"{atom}summary") or "")
        link = it.findtext("link") or ""
        if not link.strip():
            node = it.find(f"{atom}link")
            link = node.attrib.get("href", "") if node is not None else ""
        link = clean_url(link, url, domains)
        # Chỉ xét TIÊU ĐỀ: tóm tắt RSS hay nhắc tên doanh nghiệp khác trong tin tổng hợp -> dễ ra tin không liên quan
        if not title or not link or not mentions(title, ticker, aliases, exclude):
            continue
        out.append({"title": title, "summary": desc[:400], "link": link, "source": name, "match": "Tiêu đề nhắc tới doanh nghiệp",
                    "date": it.findtext("pubDate") or it.findtext(f"{atom}updated") or it.findtext(f"{atom}published") or ""})
    return out


def collect_company_news(ticker: str, name: str = "", short_name: str = "", extra_names: str = "", limit: int = 30,
                         max_age_days: int = 365) -> dict:
    """Tin doanh nghiệp: tin theo mã trên CafeF + tin RSS có tiêu đề nhắc đúng mã/tên. Liên kết đã kiểm tra domain,
    loại trùng, sắp xếp theo thời gian thật (không theo chuỗi), kèm điểm cảm xúc và nhóm sự kiện."""
    t = ticker.upper()
    aliases = name_aliases(name, short_name) + [a.strip() for a in re.split(r"[,;]", extra_names or "") if len(a.strip()) >= 3]
    exclude = other_company_phrases(t)
    status, items = {}, []
    try:
        cf = _from_cafef(t, aliases, exclude)
        status["CafeF - tin theo mã"] = {"status": "ok" if cf else "empty", "matches": len(cf)}
        items += cf
    except Exception as e:  # noqa: BLE001
        status["CafeF - tin theo mã"] = {"status": "unavailable", "matches": 0, "error": str(e)[:200]}
    for nm, (url, doms) in RSS_FEEDS.items():
        try:
            got = _from_rss(nm, url, doms, t, aliases, exclude)
            status[nm] = {"status": "ok", "matches": len(got), "feed": url}
            items += got
        except Exception as e:  # noqa: BLE001
            status[nm] = {"status": "unavailable", "matches": 0, "feed": url, "error": str(e)[:200]}
    now = datetime.now()
    seen, out = set(), []
    for it in items:
        key = (re.sub(r"\W+", "", it["title"].lower())[:80], it["link"])
        if key[0] in {k[0] for k in seen} or it["link"] in {k[1] for k in seen}:
            continue
        seen.add(key)
        d = parse_date(it.get("date", ""))
        if d and (now - d).days > max_age_days:
            continue
        it["published_at"] = d.isoformat(timespec="minutes") if d else None
        it["date"] = f"{d:%d/%m/%Y %H:%M}" if d else ""
        it["sentiment"] = score_sentiment(it["title"])
        it["event"] = classify_event(it["title"])
        out.append(it)
    out.sort(key=lambda x: x["published_at"] or "", reverse=True)
    return {"ticker": t, "aliases": aliases, "excluded": exclude, "items": out[:limit], "sources": status,
            "fetched_at": now.isoformat(timespec="minutes")}


def get_news(ticker: str, offline: bool = False, limit: int = 25, name_kw: str = "") -> dict:
    ticker = ticker.upper()
    cache = CACHE_DIR / f"news_{ticker}.json"
    data = None
    if not offline:
        from .company import get_profile
        prof = get_profile(ticker)
        got = collect_company_news(ticker, prof.name, name_kw or prof.short_name, limit=limit)
        items = [{"title": i["title"], "date": i["date"], "link": i["link"], "source": i["source"]} for i in got["items"]]
        if items:
            data = {"ticker": ticker, "source": "CafeF (tin theo mã) + RSS báo kinh tế (tiêu đề nhắc đúng mã/tên)",
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