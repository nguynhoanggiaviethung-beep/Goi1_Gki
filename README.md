# Goi1_Gki - VNEquity Research

Hệ thống phân tích cơ hội đầu tư cổ phiếu Việt Nam (HOSE, HNX). Thay vì đưa ra một giá mục tiêu duy nhất, hệ thống dựng **ba kịch bản Tích cực / Cơ sở / Tiêu cực**. Người dùng chỉnh tăng trưởng lợi nhuận, P/E mục tiêu, tỷ lệ cổ tức, xác suất và kỳ hạn để xem giá trị ước tính và tỷ suất sinh lời thay đổi ra sao. Mỗi nhận định đi kèm **thẻ bằng chứng** (chỉ số, kỳ dữ liệu, nguồn, phép tính). Báo cáo **PDF** xuất tự động, tuỳ chỉnh theo mục đích sử dụng.

Dự án gồm hai phần chạy song song:

| Phần | Công nghệ | Địa chỉ khi chạy |
|---|---|---|
| Máy chủ dữ liệu và phân tích (backend) | FastAPI + engine VNEquity | http://127.0.0.1:8000 (tài liệu API: `/docs`) |
| Giao diện người dùng (dashboard) | Streamlit + Plotly | http://localhost:8501 |

Giao diện chỉ hiển thị; mọi số liệu đều lấy qua backend. Vì vậy **phải chạy backend trước**, rồi mới mở giao diện.

---

## 1. Chuẩn bị

Cần cài sẵn:

- **Python 3.11 hoặc 3.12** (khuyến nghị 3.12). Tải tại https://www.python.org/downloads/. Khi cài trên Windows, tick ô **"Add python.exe to PATH"**.
- **Git** (nếu lấy mã nguồn từ repo): https://git-scm.com/downloads
- Kết nối Internet để tải thư viện và lấy giá cổ phiếu mới nhất. Không có mạng vẫn chạy được ở chế độ offline với mã mẫu FPT.

Kiểm tra bằng PowerShell:

```powershell
py --version        # Windows
python3 --version   # macOS / Linux
```

---

## 2. Cài đặt (làm một lần)

### Windows (PowerShell)

```powershell
# 1. Lấy mã nguồn (hoặc giải nén file zip vào C:\Goi1_Gki)
git clone <địa-chỉ-repo> C:\Goi1_Gki
cd C:\Goi1_Gki

# 2. Tạo môi trường ảo và kích hoạt
py -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Cài thư viện cho backend và giao diện
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
pip install -r frontend\requirements.txt
```

Nếu bước 2 báo lỗi *"running scripts is disabled on this system"*, chạy lệnh dưới **một lần**, rồi kích hoạt lại:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### macOS / Linux

```bash
git clone <địa-chỉ-repo> Goi1_Gki && cd Goi1_Gki
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
```

> `vnstock` được tải từ kho gói riêng của vnstock (đã khai báo trong `backend/requirements.txt`). Nếu riêng gói này cài lỗi, có thể bỏ dòng `vnstock` ra khỏi file rồi cài lại: hệ thống vẫn chạy với 716 mã có trong bộ dữ liệu, chỉ các mã ngoài bộ dữ liệu (công ty chứng khoán, bảo hiểm, UPCoM) mới cần vnstock.

---

## 3. Chạy dự án

Mở **hai cửa sổ terminal**, cả hai đều ở thư mục gốc dự án (`C:\Goi1_Gki`) và đã kích hoạt môi trường ảo (`.venv\Scripts\Activate.ps1`).

**Terminal 1 - backend**

```powershell
python -m uvicorn backend.app.main:app --port 8000
```

Chờ đến khi thấy dòng `Uvicorn running on http://127.0.0.1:8000`. Giữ nguyên cửa sổ này.

**Terminal 2 - giao diện**

```powershell
streamlit run frontend\app.py
```

Trình duyệt tự mở http://localhost:8501 (nếu không, dán địa chỉ này vào trình duyệt). Thanh bên trái hiện **"Máy chủ dữ liệu đang kết nối"** là đã chạy đúng.

Dừng chương trình: bấm `Ctrl + C` trong từng terminal.

### Chạy không cần Internet (demo)

```powershell
# Terminal 1
$env:VNEQUITY_OFFLINE="1"
python -m uvicorn backend.app.main:app --port 8000
```

Khi đó giá cổ phiếu chỉ lấy từ dữ liệu đã lưu: có sẵn **FPT** và **VN-Index**. Có thể bật thêm nút **"Chế độ offline"** trên thanh bên của giao diện.

---

## 4. Sử dụng giao diện

1. Chọn **mã cổ phiếu** ở ô trên cùng; chọn **kỳ hạn** và **khẩu vị rủi ro** ở thanh bên.
2. Các trang:

| Trang | Nội dung |
|---|---|
| Kịch bản đầu tư | Giá trị kỳ vọng, sinh lời kỳ vọng, tỷ lệ lợi nhuận/rủi ro, bảng so sánh ba kịch bản, thanh trượt chỉnh giả định, biểu đồ đường giá - ba kịch bản, ma trận độ nhạy |
| Luận điểm và bằng chứng | Luận điểm đầu tư, rủi ro, khuyến nghị, mỗi mục có nút **Chi tiết** mở thẻ bằng chứng; đánh giá theo khẩu vị; biểu đồ giá và điểm đa yếu tố |
| Biểu đồ so sánh | So sánh chỉ số tài chính nhiều năm của tối đa 4 doanh nghiệp; bảng P/E cùng ngành |
| Sàng lọc cơ hội | Quét toàn bộ doanh nghiệp theo điểm chất lượng; tải PDF và CSV (lần quét đầu khoảng 1 phút) |
| Xuất báo cáo PDF | Chọn mục đích (đầy đủ, dài hạn, giao dịch ngắn hạn, tóm tắt nhanh, hội đồng), các mục, biểu đồ, mức chi tiết rồi tải PDF. Báo cáo dùng đúng giả định đang chỉnh |
| Báo cáo và tin doanh nghiệp | Báo cáo thường niên PDF, báo cáo tài chính theo kỳ, tin tức theo mã |

---

## 5. Cấu trúc thư mục

```
Goi1_Gki/
├── backend/
│   ├── app/                    # FastAPI
│   │   ├── main.py             # điểm khởi động API
│   │   ├── engine_api.py       # API cho giao diện (phân tích, PDF, sàng lọc, BCTC)
│   │   ├── vnequity_bridge.py  # ánh xạ engine sang API kịch bản /api/scenario/*
│   │   ├── scenarios.py        # API kịch bản (schema dùng chung với bản React)
│   │   ├── research_features.py# khẩu vị rủi ro, so sánh peer, VaR, Piotroski...
│   │   ├── company_reports.py  # báo cáo thường niên, BCTC, tin doanh nghiệp
│   │   └── market_data.py      # lấy dữ liệu qua vnstock (dự phòng)
│   ├── vnequity/               # engine phân tích
│   │   ├── data/               # đọc BCTC, giá, tin tức, hồ sơ doanh nghiệp
│   │   ├── analysis/           # chỉ số tài chính, kỹ thuật, định giá, kịch bản, thẻ bằng chứng
│   │   └── report/             # biểu đồ và báo cáo PDF
│   └── requirements.txt
├── frontend/
│   ├── app.py                  # giao diện Streamlit
│   ├── figs.py                 # biểu đồ Plotly
│   ├── .streamlit/config.toml  # màu giao diện
│   ├── requirements.txt
│   └── src/                    # bản giao diện React/Vite (tuỳ chọn, xem mục 8)
├── data/
│   ├── bctc/                   # BCTC chuẩn hoá 716 mã HSX/HNX, 2011-2025 (parquet)
│   ├── reference/              # danh sách công ty, phân ngành ICB, số cổ phiếu lưu hành
│   └── cache/                  # giá đã tải (tự tạo thêm khi chạy)
├── assets/fonts/               # phông chữ tiếng Việt cho PDF
└── tests/                      # kiểm thử tự động
```

---

## 6. Dữ liệu và phương pháp

**Nguồn dữ liệu**

| Loại | Nguồn |
|---|---|
| BCTC năm 2011-2025 | Bộ dữ liệu vn-annual-report-miner (HSX, HNX), đã chuẩn hoá trong `data/bctc` |
| Giá giao dịch ngày | VNDirect, nếu lỗi chuyển sang TCBS, rồi vnstock, cuối cùng là dữ liệu đã lưu |
| Số cổ phiếu lưu hành | `data/reference/shares_outstanding.csv` (có ghi nguồn, ngày cập nhật) |
| Tin tức | CafeF, VnExpress (RSS) |

**Mô hình kịch bản**

- EPS cuối kỳ = EPS năm gần nhất × (1 + g)^n; Giá mục tiêu = P/E mục tiêu × EPS cuối kỳ.
- Tỷ suất sinh lời = (Giá mục tiêu + Cổ tức nhận trong kỳ) / Giá hiện tại − 1. Giá trị kỳ vọng = Σ xác suất × kết quả từng kịch bản.
- Tăng trưởng cơ sở g = trung vị của (CAGR lợi nhuận 3 năm, CAGR doanh thu 3 năm, ROE × (1 − tỷ lệ chi trả)). Tích cực = g + σ, Tiêu cực = g − 1,5σ (σ là độ lệch chuẩn tăng trưởng lợi nhuận, giới hạn 8-20%).
- P/E cơ sở = (P/E hiện tại + P/E bình quân 12 tháng) / 2; Tích cực = 1,1 × mức cao hơn; Tiêu cực = 0,9 × mức thấp hơn. Xác suất mặc định 25% / 50% / 25%.
- Khuyến nghị theo sinh lời kỳ vọng mỗi năm: ≥ 20% MUA; 10-20% KHẢ QUAN; ±10% NẮM GIỮ; −10 đến −20% KÉM KHẢ QUAN; < −20% BÁN. Hạ một bậc nếu tỷ lệ lợi nhuận/rủi ro < 1, nâng một bậc nếu kịch bản tiêu cực vẫn có lãi.

Mọi giả định mặc định đều có thẻ bằng chứng giải thích cách tính trong giao diện và trong PDF.

---

## 7. Biến môi trường (không bắt buộc)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `VNEQUITY_OFFLINE` | `0` | `1` = chỉ dùng giá đã lưu, không truy cập Internet |
| `VNEQUITY_CACHE_SECONDS` | `900` | Thời gian backend giữ kết quả phân tích trong bộ nhớ (giây) |
| `VNEQUITY_API_URL` | `http://127.0.0.1:8000` | Địa chỉ backend mà giao diện gọi tới (đặt trước khi chạy Streamlit) |

Đặt biến trên PowerShell: `$env:TEN_BIEN="gia_tri"`; trên macOS/Linux: `export TEN_BIEN=gia_tri`.

---

## 8. Giao diện React (tuỳ chọn)

Thư mục `frontend/src` là bản giao diện React/Vite gọi các API `/api/scenario/*`. Cần Node.js 20+:

```powershell
cd frontend
npm install
npm run dev      # mở http://localhost:5173 (backend vẫn phải chạy ở cổng 8000)
```

---

## 9. Kiểm thử

```powershell
pip install pytest httpx
python -m pytest tests -q
```

Các bài kiểm thử chạy offline với mã FPT: kiểm tra cấu trúc dữ liệu trả về, công thức Giá = EPS × P/E, áp dụng giả định người dùng, xác suất và xuất PDF theo từng mục đích.

---

## 10. Xử lý lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `running scripts is disabled on this system` khi kích hoạt `.venv` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, rồi kích hoạt lại |
| `ModuleNotFoundError: No module named 'backend'` | Chạy lệnh uvicorn **tại thư mục gốc** dự án (`C:\Goi1_Gki`), không chạy trong `backend\` |
| `ModuleNotFoundError` một thư viện bất kỳ | Chưa kích hoạt `.venv` hoặc chưa cài: `pip install -r backend\requirements.txt` và `pip install -r frontend\requirements.txt` |
| Giao diện báo "Máy chủ dữ liệu chưa phản hồi" | Backend chưa chạy hoặc đã tắt; mở Terminal 1 và chạy lại lệnh uvicorn |
| `[Errno 10048]` hoặc `address already in use` | Cổng 8000 đang bị chiếm: tắt backend cũ, hoặc chạy cổng khác `--port 8001` và đặt `$env:VNEQUITY_API_URL="http://127.0.0.1:8001"` trước khi chạy Streamlit |
| `SyntaxError` có dòng `<<<<<<<` hoặc `>>>>>>>` | File còn dấu xung đột git sau khi gộp code. Mở file, giữ đúng phiên bản cần dùng và xoá các dòng đánh dấu, hoặc lấy lại file sạch từ repo |
| "Không lấy được giá ..." | Mất mạng hoặc nguồn giá tạm lỗi; thử lại sau, hoặc bật chế độ offline và chọn FPT |
| Mã cổ phiếu không có trong danh sách | Bộ dữ liệu gồm 716 mã HSX/HNX có BCTC chuẩn hoá; công ty chứng khoán, bảo hiểm, UPCoM chưa hỗ trợ đầy đủ |
| Lỗi về `st.segmented_control` hoặc `width="stretch"` | Streamlit quá cũ: `pip install -U "streamlit>=1.46"` |

---

## 11. Lưu ý

Công cụ phục vụ nghiên cứu và học tập. Kết quả là phân tích theo giả định, **không phải khuyến nghị đầu tư** hay cam kết sinh lời. Giá trực tuyến có thể trễ theo nhà cung cấp; luôn đối chiếu nguồn và kỳ dữ liệu ghi trong báo cáo.