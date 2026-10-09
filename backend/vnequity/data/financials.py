"""Đọc Báo cáo tài chính (BCTC) năm của doanh nghiệp niêm yết HSX/HNX.

Nguồn dữ liệu: bộ BCTC hợp nhất dạng panel (702 chỉ tiêu) được đóng gói trong
repo tham khảo `vn-annual-report-miner` (Tumiqa, MIT License), lưu ở `data/bctc/`.
Mỗi file parquet có dạng dài: ticker | year | exchange | statement | item_code | item_name | value.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import BCTC_DIR

STATEMENTS = ("income_statement", "balance_sheet", "cash_flow")

# Ánh xạ trường chuẩn -> danh sách item_code ứng viên (ưu tiên từ trái sang phải)
FIELD_MAP: dict[str, list[str]] = {
    # --- Kết quả kinh doanh ---
    "revenue": ["is_doanh_so_thuan", "is_doanh_so", "is_tong_thu_nhap_hoat_dong"],
    "gross_revenue": ["is_doanh_so"],
    "cogs": ["is_gia_von_hang_ban"],
    "gross_profit": ["is_lai_gop"],
    "selling_exp": ["is_chi_phi_ban_hang"],
    "admin_exp": ["is_chi_phi_quan_ly_doanh_nghiep"],
    "fin_income": ["is_thu_nhap_tai_chinh"],
    "fin_exp": ["is_chi_phi_tai_chinh"],
    "interest_exp": ["is_trong_do_chi_phi_lai_vay"],
    "operating_profit": ["is_lai_lo_tu_hoat_dong_kinh_doanh"],
    "ebit": ["is_ebit"],
    "ebitda": ["is_ebitda"],
    "pbt": ["is_lai_lo_rong_truoc_thue", "is_tong_loi_nhuan_truoc_thue"],
    "tax": ["is_chi_phi_thue_thu_nhap_doanh_nghiep"],
    "npat": ["is_lai_lo_thuan_sau_thue", "is_loi_nhuan_sau_thue"],
    "minority_pl": ["is_loi_ich_cua_co_dong_thieu_so"],
    "npat_parent": ["is_loi_nhuan_cua_co_dong_cua_cong_ty_me", "is_co_dong_cua_cong_ty_me"],
    "eps_reported": ["is_lai_co_ban_tren_co_phieu"],
    # --- Cân đối kế toán ---
    "total_assets": ["bs_tong_tai_san", "bs_tong_cong_nguon_von"],
    "current_assets": ["bs_tai_san_ngan_han"],
    "cash": ["bs_tien_va_tuong_duong_tien"],
    "st_investments": ["bs_gia_tri_thuan_dau_tu_ngan_han", "bs_dau_tu_ngan_han"],
    "receivables": ["bs_cac_khoan_phai_thu"],
    "inventory": ["bs_hang_ton_kho_rong_746c904f", "bs_hang_ton_kho"],
    "noncurrent_assets": ["bs_tai_san_dai_han"],
    "fixed_assets": ["bs_tai_san_co_dinh"],
    "liabilities": ["bs_no_phai_tra", "bs_tong_no_phai_tra"],
    "current_liab": ["bs_no_ngan_han"],
    "lt_liab": ["bs_no_dai_han"],
    "st_debt": ["bs_vay_ngan_han"],
    "lt_debt": ["bs_vay_dai_han"],
    "equity": ["bs_von_chu_so_huu_4d280b22", "bs_von_va_cac_quy", "bs_von_chu_so_huu_6cda78ae"],
    "minority_equity": ["bs_loi_ich_co_dong_khong_kiem_soat", "bs_loi_ich_cua_co_dong_thieu_so"],
    "share_capital": ["bs_co_phieu_pho_thong", "bs_von_gop", "bs_von_dieu_le"],
    "retained_earnings": ["bs_lai_chua_phan_phoi", "bs_loi_nhuan_chua_phan_phoi"],
    "treasury": ["bs_co_phieu_quy_48ebf932"],
    # --- Lưu chuyển tiền tệ ---
    "cfo": ["cf_luu_chuyen_tien_thuan_tu_cac_hoat_dong_san_xuat_kinh_doanh"],
    "cfi": ["cf_luu_chuyen_tien_te_rong_tu_hoat_dong_dau_tu", "cf_luu_chuyen_tien_thuan_tu_hoat_dong_dau_tu"],
    "cff": ["cf_luu_chuyen_tien_te_tu_hoat_dong_tai_chinh", "cf_luu_chuyen_tien_tu_hoat_dong_tai_chinh"],
    "capex": ["cf_tien_mua_tai_san_co_dinh_va_cac_tai_san_dai_han_khac"],
    "depreciation": ["cf_khau_hao_tscd"],
    "dividends_paid": ["cf_co_tuc_da_tra"],
    "debt_raised": ["cf_tien_thu_duoc_cac_khoan_di_vay"],
    "debt_repaid": ["cf_tien_tra_cac_khoan_di_vay"],
    # --- Riêng ngân hàng ---
    "nii": ["is_thu_nhap_lai_thuan"],
    "fee_income": ["is_lai_thuan_tu_hoat_dong_dich_vu"],
    "opex": ["is_chi_phi_hoat_dong"],
    "ppop": ["is_ln_thuan_tu_hoat_dong_kinh_doanh_truoc_cf_du_phong_rui_ro"],
    "provision": ["is_chi_phi_du_phong_rui_ro_tin_dung"],
    "loans": ["bs_cho_vay_khach_hang"],
    "loan_reserve": ["bs_du_phong_rui_ro_cho_vay_khach_hang"],
    "deposits": ["bs_tien_gui_cua_khach_hang"],
}

FIELD_LABEL_VI = {
    "revenue": "Doanh thu thuần", "gross_profit": "Lợi nhuận gộp", "cogs": "Giá vốn hàng bán",
    "selling_exp": "Chi phí bán hàng", "admin_exp": "Chi phí quản lý DN", "fin_income": "Doanh thu tài chính",
    "fin_exp": "Chi phí tài chính", "interest_exp": "Chi phí lãi vay", "ebit": "EBIT", "ebitda": "EBITDA",
    "pbt": "Lợi nhuận trước thuế", "npat": "Lợi nhuận sau thuế", "npat_parent": "LNST cổ đông công ty mẹ",
    "eps_reported": "EPS cơ bản (đồng)", "total_assets": "Tổng tài sản", "current_assets": "Tài sản ngắn hạn",
    "cash": "Tiền & tương đương tiền", "st_investments": "Đầu tư tài chính ngắn hạn", "receivables": "Phải thu",
    "inventory": "Hàng tồn kho", "fixed_assets": "Tài sản cố định", "liabilities": "Nợ phải trả",
    "current_liab": "Nợ ngắn hạn", "lt_liab": "Nợ dài hạn", "st_debt": "Vay ngắn hạn", "lt_debt": "Vay dài hạn",
    "equity": "Vốn chủ sở hữu", "minority_equity": "Lợi ích CĐ không kiểm soát", "share_capital": "Vốn cổ phần",
    "retained_earnings": "LN chưa phân phối", "cfo": "LCTT từ HĐKD", "cfi": "LCTT từ HĐ đầu tư",
    "cff": "LCTT từ HĐ tài chính", "capex": "Chi mua sắm TSCĐ (Capex)", "depreciation": "Khấu hao",
    "dividends_paid": "Cổ tức đã trả", "nii": "Thu nhập lãi thuần", "fee_income": "Lãi thuần hoạt động dịch vụ",
    "opex": "Chi phí hoạt động", "ppop": "LN trước dự phòng", "provision": "Chi phí dự phòng tín dụng",
    "loans": "Cho vay khách hàng", "loan_reserve": "Dự phòng rủi ro cho vay", "deposits": "Tiền gửi khách hàng",
}


@lru_cache(maxsize=1)
def _load_all() -> pd.DataFrame:
    frames = []
    for st in STATEMENTS:
        for p in sorted((BCTC_DIR / st).glob("*.parquet")):
            df = pd.read_parquet(p, columns=["ticker", "year", "exchange", "statement", "item_code", "item_name", "value"])
            frames.append(df)
    if not frames:
        raise FileNotFoundError(f"Không tìm thấy dữ liệu BCTC trong {BCTC_DIR}")
    df = pd.concat(frames, ignore_index=True)
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    return df


def available_tickers() -> list[str]:
    return sorted(_load_all()["ticker"].unique().tolist())


def raw_items(ticker: str) -> pd.DataFrame:
    """Bảng chỉ tiêu gốc dạng rộng: index = (statement, item_code, item_name), cột = năm."""
    df = _load_all()
    sub = df[df["ticker"] == ticker.upper()]
    if sub.empty:
        return pd.DataFrame()
    wide = sub.pivot_table(index=["statement", "item_code", "item_name"], columns="year",
                           values="value", aggfunc="first")
    return wide.sort_index(axis=1)


@lru_cache(maxsize=256)
def get_financials(ticker: str) -> pd.DataFrame:
    """Trả về bảng chỉ tiêu chuẩn hoá: index = năm, cột = các trường trong FIELD_MAP (đơn vị: đồng)."""
    df = _load_all()
    sub = df[df["ticker"] == ticker.upper()]
    if sub.empty:
        return pd.DataFrame()
    wide = sub.pivot_table(index="year", columns="item_code", values="value", aggfunc="first").sort_index()
    out = pd.DataFrame(index=wide.index)
    for fld, codes in FIELD_MAP.items():
        series = None
        for c in codes:
            if c in wide.columns:
                s = wide[c]
                series = s if series is None else series.fillna(s)
        out[fld] = series if series is not None else np.nan
    # Bỏ các năm gần như trống (ít hơn 3 chỉ tiêu cốt lõi)
    core = out[["revenue", "npat", "total_assets", "equity"]].notna().sum(axis=1)
    out = out[(core >= 3) & out["npat"].notna() & out["total_assets"].notna()]
    out.index = out.index.astype(int)
    # Loại các năm bị trùng lặp nguyên khối với năm trước (lỗi nguồn dữ liệu)
    dup = out[["revenue", "npat", "total_assets", "equity"]].eq(out[["revenue", "npat", "total_assets", "equity"]].shift(1)).all(axis=1)
    out = out[~dup]
    out.attrs["is_bank"] = bool(out["nii"].notna().any())
    out.attrs["exchange"] = sub["exchange"].iloc[0]
    return out


def exchange_of(ticker: str) -> str | None:
    df = _load_all()
    sub = df.loc[df["ticker"] == ticker.upper(), "exchange"]
    return None if sub.empty else str(sub.iloc[0])
