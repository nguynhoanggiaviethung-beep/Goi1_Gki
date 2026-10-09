"""On-demand listed-company report sources: Zenodo, vnfinancialdata and news RSS."""

from __future__ import annotations

import csv
import html
import hashlib
import io
import ipaddress
import json
import os
import re
import socket
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.research_features import AnnualReportText, LanguageChangeRequest, compare_report_language

router = APIRouter(tags=["company reports and news"])

ZENODO_RECORD = "20949551"
ZENODO_INDEX_URL = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files/file_index_full.csv/content"
ZENODO_FILE_API = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files"
ARCHIVES = {
    "2000_2005": "vn_bctn_2000_2005.zip", "2006_2010": "vn_bctn_2006_2010.zip",
    "2011_2015": "vn_bctn_2011_2015.zip", "2016_2020": "vn_bctn_2016_2020.zip",
    "2021_2025": "vn_bctn_2021_2025.zip",
}
ROOT = Path(__file__).resolve().parents[1] / "data" / "company_reports"
PDF_CACHE = ROOT / "annual"
INDEX_CACHE = ROOT / "file_index_full.csv"
MAX_REPORT_BYTES = 100 * 1024 * 1024
REPORT_INDEX: list[dict[str, str]] = []
REPORT_INDEX_TIME = 0.0
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "VietScope/0.1 (student research project; report lookup)"})


def _report_index(force: bool = False) -> list[dict[str, str]]:
    global REPORT_INDEX, REPORT_INDEX_TIME
    if REPORT_INDEX and not force and time.time() - REPORT_INDEX_TIME < 6 * 3600:
        return REPORT_INDEX
    try:
        if not force and INDEX_CACHE.exists() and time.time() - INDEX_CACHE.stat().st_mtime < 6 * 3600:
            raw = INDEX_CACHE.read_text(encoding="utf-8-sig")
        else:
            response = SESSION.get(ZENODO_INDEX_URL, timeout=(10, 45))
            response.raise_for_status()
            raw = response.content.decode("utf-8-sig", errors="replace")
            ROOT.mkdir(parents=True, exist_ok=True)
            INDEX_CACHE.write_text(raw, encoding="utf-8-sig")
        REPORT_INDEX = list(csv.DictReader(io.StringIO(raw)))
        REPORT_INDEX_TIME = time.time()
        return REPORT_INDEX
    except Exception as exc:
        if INDEX_CACHE.exists():
            try:
                REPORT_INDEX = list(csv.DictReader(INDEX_CACHE.open(encoding="utf-8-sig", newline="")))
                return REPORT_INDEX
            except Exception:
                pass
        raise HTTPException(status_code=502, detail=f"Không tải được danh mục báo cáo Zenodo: {exc}") from exc


def _rows(ticker: str, year: int | None = None) -> list[dict[str, str]]:
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", symbol):
        raise HTTPException(status_code=422, detail="Mã cổ phiếu không hợp lệ.")
    result = [row for row in _report_index() if row.get("ticker_file", "").upper() == symbol and row.get("document_type") == "annual_report"]
    if year is not None:
        result = [row for row in result if row.get("year_full", "") == str(year)]
    return sorted(result, key=lambda row: int(row.get("year_full") or 0), reverse=True)


class _RemoteZipReader(io.RawIOBase):
    """Seekable range reader so a single PDF can be extracted without downloading a multi-GB ZIP."""

    def __init__(self, url: str, cache_dir: Path, block_size: int = 1024 * 1024):
        self.url, self.cache_dir, self.block_size = url, cache_dir, block_size
        self.pos = 0
        self.blocks: OrderedDict[int, bytes] = OrderedDict()
        first = SESSION.get(url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"}, timeout=(10, 45))
        if first.status_code != 206 or "/" not in first.headers.get("Content-Range", ""):
            raise RuntimeError("Zenodo không hỗ trợ tải từng phần (HTTP Range) cho kho ZIP.")
        self.size = int(first.headers["Content-Range"].rsplit("/", 1)[1])

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET):
        target = offset if whence == io.SEEK_SET else self.pos + offset if whence == io.SEEK_CUR else self.size + offset
        self.pos = min(max(0, target), self.size)
        return self.pos

    def _block(self, index: int) -> bytes:
        if index in self.blocks:
            self.blocks.move_to_end(index)
            return self.blocks[index]
        cached = self.cache_dir / f"{index}.bin"
        if cached.is_file():
            data = cached.read_bytes()
        else:
            start = index * self.block_size
            end = min(start + self.block_size, self.size) - 1
            response = SESSION.get(self.url, headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}, timeout=(10, 60))
            if response.status_code != 206:
                raise RuntimeError(f"Zenodo trả HTTP {response.status_code} cho yêu cầu tải từng phần.")
            data = response.content
            if len(data) != end - start + 1:
                raise RuntimeError("Dữ liệu tải từng phần bị thiếu hoặc sai độ dài.")
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
        self.blocks[index] = data
        while len(self.blocks) > 8:
            self.blocks.popitem(last=False)
        return data

    def readinto(self, buffer):
        if self.pos >= self.size: return 0
        wanted, done = len(buffer), 0
        while done < wanted and self.pos < self.size:
            index, offset = divmod(self.pos, self.block_size)
            block = self._block(index)
            count = min(wanted - done, len(block) - offset)
            if count <= 0: break
            buffer[done:done + count] = block[offset:offset + count]
            self.pos += count; done += count
        return done


def _download_report(row: dict[str, str]) -> Path:
    ticker, year = row["ticker_file"].upper(), int(row["year_full"])
    PDF_CACHE.mkdir(parents=True, exist_ok=True)
    target = PDF_CACHE / f"{ticker}_{year}.pdf"
    expected_hash = row.get("sha256", "").lower()
    if target.exists():
        try:
            digest = hashlib.sha256()
            with target.open("rb") as cached_file:
                for chunk in iter(lambda: cached_file.read(1024 * 1024), b""): digest.update(chunk)
            if not expected_hash or digest.hexdigest() == expected_hash: return target
        except OSError: pass
    period, filename, relative = row.get("archive_period", ""), row.get("file_name", ""), row.get("relative_path", "")
    archive = ARCHIVES.get(period)
    if not archive or not relative:
        raise HTTPException(status_code=502, detail="Danh mục Zenodo thiếu vị trí lưu trữ của báo cáo.")
    try:
        # Ask the official record API for a current content URL; the large ZIP is never fully downloaded.
        rec = SESSION.get(f"https://zenodo.org/api/records/{ZENODO_RECORD}", timeout=(10, 45))
        rec.raise_for_status()
        file_meta = next((item for item in rec.json().get("files", []) if item.get("key") == archive), None)
        if not file_meta: raise RuntimeError(f"Không tìm thấy archive {archive} trong bản ghi Zenodo.")
        links = file_meta.get("links", {})
        remote = links.get("self") or f"{ZENODO_FILE_API}/{quote(archive)}/content"
        cache_dir = ROOT / "zip_ranges" / period
        reader = _RemoteZipReader(remote, cache_dir)
        with zipfile.ZipFile(reader) as zf:
            actual_name = next((name for name in zf.namelist() if name.replace("\\", "/").lstrip("/") == relative.lstrip("/")), None)
            if actual_name is None:
                actual_name = next((name for name in zf.namelist() if Path(name).name.casefold() == filename.casefold()), None)
            if actual_name is None: raise FileNotFoundError(f"{relative} không nằm trong archive {archive}.")
            info = zf.getinfo(actual_name)
            if info.file_size > MAX_REPORT_BYTES: raise RuntimeError("Báo cáo vượt giới hạn tải 100 MB.")
            digest = hashlib.sha256()
            with zf.open(actual_name) as source, tempfile.NamedTemporaryFile(dir=PDF_CACHE, suffix=".part", delete=False) as sink:
                temp_path = Path(sink.name)
                while chunk := source.read(1024 * 1024):
                    sink.write(chunk); digest.update(chunk)
            with temp_path.open("rb") as downloaded:
                signature = downloaded.read(5)
            if signature != b"%PDF-":
                temp_path.unlink(missing_ok=True); raise RuntimeError("Tệp tải về không phải PDF hợp lệ.")
            if expected_hash and digest.hexdigest().lower() != expected_hash:
                temp_path.unlink(missing_ok=True); raise RuntimeError("Checksum SHA-256 không khớp danh mục Zenodo.")
            temp_path.replace(target)
            return target
    except HTTPException: raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Không tải được báo cáo {ticker} {year} từ Zenodo: {exc}") from exc


@router.get("/reports/annual/available")
def annual_report_availability(ticker: str = Query(min_length=2, max_length=10)):
    rows = _rows(ticker)
    return {"ticker": ticker.upper(), "provider": "Zenodo", "dataset_doi": f"10.5281/zenodo.{ZENODO_RECORD}",
            "years": [{"year": int(row["year_full"]), "file_name": row["file_name"], "size_mb": row.get("file_size_mb"),
                       "sha256": row.get("sha256"), "cached": (PDF_CACHE / f"{ticker.upper()}_{row['year_full']}.pdf").exists(),
                       "dataset_source": "Zenodo Vietnam Listed Companies Annual Reports PDF Dataset"} for row in rows],
            "warning": "Kho Zenodo có báo cáo thường niên theo danh mục; phạm vi/độ chính xác phụ thuộc từng mã-năm. Tệp chỉ tải khi người dùng chọn.",
            "catalog_retrieved_at": datetime.now(timezone.utc).isoformat()}


@router.get("/reports/annual/{ticker}/{year}/download")
def download_annual_report(ticker: str, year: int):
    rows = _rows(ticker, year)
    if not rows: raise HTTPException(status_code=404, detail=f"Không thấy báo cáo thường niên {ticker.upper()} năm {year} trong danh mục Zenodo.")
    path = _download_report(rows[0])
    return FileResponse(path, media_type="application/pdf", filename=f"{ticker.upper()}_{year}_BCTN.pdf",
                        headers={"X-Report-Source": f"https://doi.org/10.5281/zenodo.{ZENODO_RECORD}", "X-Report-SHA256": rows[0].get("sha256", "")})


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Thiếu pypdf; chạy pip install -r backend/requirements.txt rồi khởi động lại backend.") from exc
    try:
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages[:500])
        if len(text.strip()) < 200:
            raise HTTPException(status_code=422, detail="PDF có ít văn bản trích xuất được (có thể là scan ảnh); hiện chưa bật OCR.")
        return text[:2_000_000]
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=422, detail=f"Không trích xuất được PDF: {exc}") from exc


@router.get("/reports/annual/{ticker}/{year}/text")
def annual_report_text(ticker: str, year: int):
    rows = _rows(ticker, year)
    if not rows: raise HTTPException(status_code=404, detail="Không có báo cáo tương ứng trong danh mục Zenodo.")
    row = rows[0]
    text = _extract_pdf_text(_download_report(row))
    return {"ticker": ticker.upper(), "year": year, "document_type": "annual_report", "section": "whole_report",
            "text": text, "characters": len(text), "pages_text_extracted": "tối đa 500 trang", "source": "Zenodo",
            "source_url": f"https://doi.org/10.5281/zenodo.{ZENODO_RECORD}", "file_name": row["file_name"], "sha256": row.get("sha256"),
            "warning": "Trích xuất text PDF không chạy OCR. Phần bảng, biểu đồ hoặc PDF scan có thể bị thiếu/sai bố cục."}


class AnnualCompareRequest(BaseModel):
    ticker: str = Field(min_length=2, max_length=10)
    years: list[int] = Field(min_length=2, max_length=8)


@router.post("/reports/annual/compare-language")
def annual_report_language_comparison(request: AnnualCompareRequest):
    if len(set(request.years)) != len(request.years): raise HTTPException(status_code=422, detail="Không nhập lặp năm.")
    available = {int(row["year_full"]): row for row in _rows(request.ticker)}
    missing = [year for year in request.years if year not in available]
    if missing: raise HTTPException(status_code=404, detail=f"Không có BCTN cho năm: {', '.join(map(str, missing))}.")
    reports = [AnnualReportText(year=year, text=_extract_pdf_text(_download_report(available[year])), section="whole_report") for year in sorted(request.years)]
    return {**compare_report_language(LanguageChangeRequest(ticker=request.ticker, reports=reports)),
            "source": "Zenodo", "source_url": f"https://doi.org/10.5281/zenodo.{ZENODO_RECORD}",
            "warning": "So sánh toàn văn, không tách riêng cùng một chương; PDF scan/bảng/biểu đồ có thể bị thiếu text. Lexical drift không tự kết luận nội dung tốt/xấu."}


FINANCIAL_STATEMENTS = ("balance_sheet", "income_statement", "cash_flow")


@router.get("/reports/financial/{ticker}")
def financial_statements(ticker: str, exchange: str = Query(default="AUTO", pattern="^(AUTO|HSX|HNX)$"), years: int = Query(default=5, ge=1, le=20)):
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", symbol): raise HTTPException(status_code=422, detail="Mã cổ phiếu không hợp lệ.")
    try:
        import vnfinancialdata as vnf
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="vnfinancialdata chưa cài. Cài lại backend dependencies theo README.") from exc
    exchanges = [exchange] if exchange != "AUTO" else ["HSX", "HNX"]
    current_year = datetime.now().year
    output, errors = {}, []
    for statement in FINANCIAL_STATEMENTS:
        combined = []
        for market in exchanges:
            try:
                frame = vnf.load(exchange=market, statement=statement)
                selected = frame[(frame["ticker"].astype(str).str.upper() == symbol) & (frame["year"].astype(int) >= current_year - years + 1)]
                combined.extend(json.loads(selected.to_json(orient="records", date_format="iso")))
            except Exception as exc:
                errors.append(f"{market}/{statement}: {exc}")
        # Use the first available exchange copy to avoid duplicate symbols in the concatenated list.
        unique = {}
        for row in combined:
            key = (str(row.get("year")), str(row.get("item_name")))
            unique.setdefault(key, row)
        output[statement] = list(unique.values())
    total_rows = sum(len(rows) for rows in output.values())
    if total_rows == 0 and errors:
        raise HTTPException(status_code=502, detail=f"Không lấy được BCTC từ vnfinancialdata/Hugging Face: {'; '.join(errors[:3])}")
    return {"ticker": symbol, "exchange_requested": exchange, "years_requested": years, "provider": "vnfinancialdata",
            "upstream": "Hugging Face dataset của vnfinancialdata", "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "statements": output, "row_counts": {key: len(value) for key, value in output.items()}, "warnings": errors,
            "coverage_note": "Độ phủ theo dataset HSX/HNX, mã, năm và chỉ tiêu có sẵn; không giả định bao phủ UPCoM/toàn bộ lịch sử. Xem từng kỳ, đơn vị và nhãn item trước khi dùng.",
            "source_url": "https://github.com/thanhnp-uel/vnfinancialdata"}


NEWS_FEEDS = {
    "CafeF": "https://cafef.vn/doanh-nghiep.rss",
    "CafeBiz": "https://cafebiz.vn/trang-chu.rss",
    "VnExpress": "https://vnexpress.net/rss/kinh-doanh.rss",
    "VietnamNet": "https://vietnamnet.vn/kinh-doanh/index.rss",
    "Tin Nhanh Chứng Khoán": "https://www.tinnhanhchungkhoan.vn/rss/home.rss",
    "VnEconomy": "https://vneconomy.vn/tai-chinh.rss",
}


class _LinksParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.alternates: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag.lower() == "a" and a.get("href"):
            self.current = {"href": a["href"], "text": ""}
        if tag.lower() == "link" and "alternate" in a.get("rel", "").lower() and ("rss" in a.get("type", "").lower() or "xml" in a.get("type", "").lower()):
            if a.get("href"): self.alternates.append(a["href"])

    def handle_data(self, data):
        if self.current is not None: self.current["text"] += data

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            self.links.append(self.current); self.current = None


def _public_web_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Website phải là URL http(s) công khai.")
    addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Từ chối host nội bộ/không công khai.")
    return url


def _get_public_page(url: str):
    current = _public_web_url(url)
    for _ in range(4):
        response = SESSION.get(current, timeout=(5, 12), allow_redirects=False, stream=True)
        if response.status_code in {301, 302, 303, 307, 308}:
            destination = response.headers.get("Location")
            response.close()
            if not destination: break
            current = _public_web_url(urljoin(current, destination))
            continue
        response.raise_for_status()
        content = response.raw.read(600_000, decode_content=True)
        content_type = response.headers.get("Content-Type", "")
        response.close()
        return current, content, content_type
    raise ValueError("Website chuyển hướng quá nhiều hoặc không hợp lệ.")


@router.get("/news/company/{ticker}")
def company_news(ticker: str, company_name: str = Query(default="", max_length=120), company_website: str = Query(default="", max_length=500), limit: int = Query(default=30, ge=1, le=100)):
    """Tin doanh nghiệp theo mã.

    1. CafeF - danh sách tin theo đúng mã (công bố thông tin + bài viết gắn mã).
    2. RSS CafeF, VnExpress, VietnamNet, Tin Nhanh Chứng Khoán, VnEconomy - chỉ giữ tin có TIÊU ĐỀ nhắc mã CK viết hoa
       đứng riêng hoặc nguyên cụm tên doanh nghiệp (không khớp từ đơn lẻ, không khớp tên doanh nghiệp niêm yết khác).
    3. Website doanh nghiệp (tuỳ chọn) - chỉ liên kết cùng domain.
    Liên kết được kiểm tra là URL tuyệt đối thuộc đúng domain nguồn; loại trùng; sắp xếp theo thời gian đăng thật.
    """
    from backend.vnequity.data.company import get_profile
    from backend.vnequity.data.news import clean_url, collect_company_news, mentions, parse_date

    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", symbol): raise HTTPException(status_code=422, detail="Mã cổ phiếu không hợp lệ.")
    prof = get_profile(symbol)
    got = collect_company_news(symbol, prof.name, prof.short_name, extra_names=company_name, limit=200)
    results = [{"ticker": symbol, "source": it["source"], "title": it["title"], "summary": it.get("summary", ""), "url": it["link"],
                "published_at": it["published_at"], "published_display": it["date"], "match": it["match"],
                "sentiment": it["sentiment"], "event": it["event"]} for it in got["items"]]
    sources = got["sources"]
    aliases, exclude = got["aliases"], got["excluded"]
    if company_website.strip():
        try:
            page_url, content, content_type = _get_public_page(company_website.strip())
            host = urlparse(page_url).hostname or ""
            dom = host[4:] if host.startswith("www.") else host
            matched = 0
            if b"<rss" in content[:1000].lower() or b"<feed" in content[:1000].lower() or "xml" in content_type.lower():
                root = ET.fromstring(content)
                for item in root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                    title = html.unescape((item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip())
                    link = item.findtext("link") or ""
                    if not link.strip():
                        node = item.find("{http://www.w3.org/2005/Atom}link")
                        link = node.attrib.get("href", "") if node is not None else ""
                    url = clean_url(link, page_url, (dom,))
                    if title and url:   # trang tin của chính doanh nghiệp: mọi bài đều liên quan
                        d = parse_date(item.findtext("pubDate") or "")
                        results.append({"ticker": symbol, "source": "Website doanh nghiệp", "title": title, "summary": "", "url": url,
                                        "published_at": d.isoformat(timespec="minutes") if d else None,
                                        "published_display": f"{d:%d/%m/%Y %H:%M}" if d else "", "match": "Website doanh nghiệp"}); matched += 1
            else:
                parser = _LinksParser()
                parser.feed(content.decode("utf-8", errors="replace"))
                for entry in parser.links[:400]:
                    title = html.unescape(re.sub(r"\s+", " ", entry["text"])).strip()
                    url = clean_url(entry["href"], page_url, (dom,))
                    if len(title) < 20 or not url or url.rstrip("/") == page_url.rstrip("/"):
                        continue
                    if not re.search(r"news|tin-|tin/|bao-chi|media|investor|quan-he-co-dong|thong-cao|cong-bo", url, re.I):
                        continue
                    results.append({"ticker": symbol, "source": "Website doanh nghiệp", "title": title, "summary": "", "url": url,
                                    "published_at": None, "published_display": "", "match": "Website doanh nghiệp"}); matched += 1
            sources["Website doanh nghiệp"] = {"status": "ok", "matches": matched, "feed": page_url}
        except Exception as exc:
            sources["Website doanh nghiệp"] = {"status": "unavailable", "matches": 0, "feed": company_website, "error": str(exc)[:220]}
    seen, unique = set(), []
    for row in results:
        if row["url"] in seen:
            continue
        seen.add(row["url"]); unique.append(row)
    unique.sort(key=lambda row: row.get("published_at") or "", reverse=True)
    return {"ticker": symbol, "company_name": prof.name or company_name or None, "aliases": aliases, "excluded_names": exclude,
            "articles": unique[:limit], "sources": sources, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Chỉ giữ tin có tiêu đề nhắc đúng mã cổ phiếu (viết hoa, đứng riêng) hoặc nguyên tên doanh nghiệp; "
                       "tin theo mã lấy từ CafeF. Liên kết dẫn tới bài gốc trên trang nguồn."}