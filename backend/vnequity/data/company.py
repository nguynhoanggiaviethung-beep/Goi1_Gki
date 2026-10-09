"""Thông tin doanh nghiệp: tên, sàn, phân ngành ICB, website, số cổ phiếu lưu hành."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from ..config import PAR_VALUE, REF_DIR
from .financials import get_financials


@dataclass
class CompanyProfile:
    ticker: str
    name: str = ""
    short_name: str = ""
    exchange: str = ""
    icb1: str = ""
    icb2: str = ""
    icb3: str = ""
    icb4: str = ""
    website: str = ""
    ir_url: str = ""
    shares: float = float("nan")
    shares_source: str = ""

    @property
    def is_financial(self) -> bool:
        return self.icb1 in {"Ngân hàng", "Dịch vụ tài chính", "Bảo hiểm", "Tài chính"} or \
            self.icb2 in {"Ngân hàng", "Dịch vụ tài chính", "Bảo hiểm"}


@lru_cache(maxsize=1)
def _companies() -> pd.DataFrame:
    df = pd.read_csv(REF_DIR / "companies.csv", encoding="utf-8-sig")
    df.columns = ["ticker", "name", "short_name", "exchange", "icb1", "icb2", "icb3", "icb4",
                  "icb_code", "src", "website", "ir_url"][: len(df.columns)]
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    return df.fillna("")


@lru_cache(maxsize=1)
def _shares_override() -> pd.DataFrame:
    p = REF_DIR / "shares_outstanding.csv"
    if not p.exists():
        return pd.DataFrame(columns=["ticker", "shares", "as_of", "source"])
    df = pd.read_csv(p)
    df["ticker"] = df["ticker"].str.upper()
    return df


def get_profile(ticker: str) -> CompanyProfile:
    t = ticker.upper()
    prof = CompanyProfile(ticker=t)
    comp = _companies()
    row = comp[comp["ticker"] == t]
    if not row.empty:
        r = row.iloc[0]
        prof.name, prof.short_name, prof.exchange = r["name"], r["short_name"], r["exchange"]
        prof.icb1, prof.icb2, prof.icb3, prof.icb4 = r["icb1"], r["icb2"], r["icb3"], r["icb4"]
        prof.website, prof.ir_url = r["website"], r["ir_url"]

    ov = _shares_override()
    ov = ov[ov["ticker"] == t]
    if not ov.empty:
        prof.shares = float(ov.iloc[-1]["shares"])
        prof.shares_source = f"{ov.iloc[-1]['source']} (ngày {ov.iloc[-1]['as_of']})"
    else:
        fin = get_financials(t)
        if not fin.empty and pd.notna(fin["share_capital"].iloc[-1]) and fin["share_capital"].iloc[-1] > 0:
            prof.shares = float(fin["share_capital"].iloc[-1]) / PAR_VALUE
            prof.shares_source = f"Vốn cổ phần BCTC {fin.index[-1]} / mệnh giá 10.000đ"
    return prof


def peers_of(ticker: str, min_peers: int = 4) -> tuple[list[str], str]:
    """Danh sách mã cùng ngành (ICB cấp 4 -> 3 -> 2), trả về (danh sách, mức ngành)."""
    comp = _companies()
    me = comp[comp["ticker"] == ticker.upper()]
    if me.empty:
        return [], ""
    me = me.iloc[0]
    for lvl, label in (("icb4", "ICB cấp 4"), ("icb3", "ICB cấp 3"), ("icb2", "ICB cấp 2")):
        if not me[lvl]:
            continue
        peers = comp[(comp[lvl] == me[lvl]) & (comp["ticker"] != me["ticker"])]["ticker"].tolist()
        peers = [p for p in peers if not get_financials(p).empty]
        if len(peers) >= min_peers:
            return peers, f"{label}: {me[lvl]}"
    return peers, f"ICB cấp 2: {me['icb2']}"
