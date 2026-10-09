# Goi1_Gki

Ứng dụng phân tích cổ phiếu Việt Nam: giao diện Streamlit theo VNStockAI và API FastAPI.

## Chạy trên Windows PowerShell
Mở hai terminal tại thư mục repo. Streamlit là giao diện người dùng; nó gọi API FastAPI ở terminal còn lại. React/Vite không dùng trong luồng chạy hiện tại.

Cài gói giao diện một lần:
```powershell
.\.venv\Scripts\python.exe -m pip install -r frontend\requirements.txt
```

Terminal 1:
```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload --port 8000
```

Terminal 2:
```powershell
streamlit run frontend\app.py
```

Frontend: http://localhost:8501
API docs: http://localhost:8000/docs

Mặc định Streamlit gọi backend tại `http://127.0.0.1:8000`. Nếu backend ở máy/host khác, đặt biến môi trường `VNEQUITY_API_URL` trước khi chạy Streamlit.

<<<<<<< HEAD
## Engine phân tích VNEquity (đã ghép vào backend)

Backend hiện dùng engine `backend/vnequity` làm nguồn chính cho các endpoint mà giao diện gọi; schema trả về giữ nguyên nên `frontend/app.py` (và React `frontend/src`) không cần đổi cách gọi.

| Endpoint | Xử lý |
|---|---|
| `POST /api/scenario/live` | BCTC chuẩn hoá 716 mã HSX/HNX (2011-2025) + giá ngày → 3 kịch bản `bullish/base/bearish`. Tăng trưởng EPS cơ sở = trung vị (CAGR LNST 3 năm, CAGR doanh thu 3 năm, ROE × (1 − tỷ lệ chi trả)); tích cực +1σ, tiêu cực −1,5σ (σ = độ lệch chuẩn tăng trưởng LNST, chặn 8-20%). P/E cơ sở = (P/E hiện tại + P/E bình quân 12 tháng)/2; tích cực 1,1 × max, tiêu cực 0,9 × min. Mỗi kịch bản có 6 thẻ bằng chứng (EPS gốc, tăng trưởng, EPS dự phóng, P/E, giá, lợi suất). Trả thêm `rating`, `thesis`, `risks`, `evidence_book`, `data_confidence`. |
| `POST /api/scenario/live/report.pdf` | PDF của engine (bìa khuyến nghị, kịch bản, định giá, tài chính, kỹ thuật, tin tức, thẻ bằng chứng, nguồn). `report.purpose`, `metric_groups`, `detail_level`, `include_chart` được ánh xạ sang mục báo cáo tương ứng. |
| `POST /api/peers/live-compare` | Giá/EPS/P-E lấy từ engine. |
| `GET /api/engine/tickers` | Danh sách mã có BCTC chuẩn hoá. |

Nguồn giá: VNDirect → TCBS → vnstock → cache trong `data/cache`. Mã không có trong bộ BCTC (công ty chứng khoán, bảo hiểm, UPCoM) tự chuyển sang luồng vnstock cũ.

Biến môi trường: `VNEQUITY_OFFLINE=1` chỉ dùng dữ liệu giá đã lưu (mẫu có sẵn: FPT, VN-Index); `VNEQUITY_CACHE_SECONDS` (mặc định 900) thời gian lưu đệm kết quả phân tích.

Kiểm thử: `python -m pytest tests -q`.

=======
>>>>>>> 4e651f5185c7e2c0052350c6c51df51f4fc0f590
## API phân tích kịch bản đầu tư

- `POST /api/scenario/analyze` nhận mã cổ phiếu, giá hiện tại, EPS dương, tăng trưởng EPS, P/E mục tiêu và nguồn/kỳ dữ liệu; trả về ba kịch bản cùng thẻ bằng chứng cho từng phép tính.
- `POST /api/scenario/report.pdf` nhận cùng dữ liệu phân tích kèm lựa chọn kỳ hạn, nhóm nội dung, biểu đồ và mức chi tiết; trả về PDF.
- `POST /api/scenario/live` tự truy vấn giá gần nhất cùng tỷ số tài chính/EPS khả dụng qua vnstock rồi chạy mô phỏng. Gửi `ticker`; có thể thêm `earnings_growth_pct` để nhập tăng trưởng giả định và `target_pe` để thay P/E mặc định.
- `POST /api/scenario/live/report.pdf` thực hiện truy vấn tương tự và trả PDF tùy chỉnh.

Engine kịch bản dùng EPS Growth YoY năm liền kề, loại quan sát EPS không dương/đổi dấu, winsorize chuỗi tăng trưởng tại P5/P95, rồi ghép P25/median/P75 của tăng trưởng với P25/median/P75 của P/E lịch sử cùng kỳ EPS. Cần tối thiểu 4 quan sát hợp lệ cho mỗi chuỗi; nếu thiếu, hệ thống cảnh báo và không tự tạo khoảng tăng/giảm. Có thể ghi đè từng kịch bản qua `overrides`; đó là giả định người dùng và cần căn cứ riêng. Phạm vi phương pháp hiện tại là doanh nghiệp phi tài chính có EPS dương; không tự chuyển phương pháp khi P/E không phù hợp.

Giá mục tiêu sử dụng EPS forward 12 tháng. 3/6 tháng là kỳ theo dõi, không chia nhỏ tăng trưởng EPS theo thời gian. Báo cáo PDF có năm mục đích (đầy đủ, dài hạn, giao dịch, một trang, hội đồng), phần nội dung, biểu đồ và mức chi tiết tùy chỉnh. Các phần tài chính/rủi ro/peer/tin chỉ được trình bày khi có dữ liệu bổ sung; không tự điền số liệu còn thiếu.

vnstock là bộ kết nối tới nguồn dữ liệu bên thứ ba. Giá trong phiên có thể trễ theo nhà cung cấp và độ phủ có thể thay đổi. Cài đặt dependency qua `python -m pip install -r backend\requirements.txt`. Nếu tự triển khai, hãy kiểm tra điều khoản của nguồn dữ liệu; có thể cấu hình `VNSTOCK_API_KEY` theo hướng dẫn vnstock khi cần. Tăng trưởng EPS chỉ tự tính khi nguồn trả đủ ít nhất hai kỳ EPS dương; nếu không, gửi `earnings_growth_pct` làm giả định của người dùng.

Ví dụ body cho `/api/scenario/live`:

```json
{
  "ticker": "FPT",
  "earnings_growth_pct": 15,
  "horizon_years": 2,
  "overrides": {"bullish": {"earnings_growth_pct": 22, "target_pe": 21}}
}
```

## Các tính năng nghiên cứu bổ sung

| Endpoint | Chức năng và dữ liệu cần gửi |
|---|---|
| `POST /api/quality/score` | Tính điểm tin cậy 0–100 từ chín kiểm tra V01–V09; body là các mức sai lệch, số kỳ thiếu, độ cũ dữ liệu và cờ cảnh báo. Trả về từng khoản trừ và cảnh báo. |
| `POST /api/score/composite` | Ghép điểm Chất lượng/Định giá/Động lượng/Rủi ro theo trọng số riêng cho ba khẩu vị; mọi trọng số phải cộng thành 1. |
| `POST /api/recommendation/profile` | Đánh giá cùng ba lợi suất kịch bản theo khẩu vị an toàn/cân bằng/chấp nhận rủi ro. Các ngưỡng là cấu hình minh bạch của nhóm. |
| `POST /api/risk/var-es` | Tính VaR lịch sử và Expected Shortfall một ngày từ chuỗi lợi suất ngày đã điều chỉnh. Cần tối thiểu 60 quan sát. |
| `POST /api/peers/live-compare` | Tự lấy giá/P-E qua vnstock cho mã mục tiêu và 3–5 peer; client cung cấp mã peer và nhãn ngành. Trả bảng chỉ số, trung vị peer và giá hàm ý theo P/E trung vị. |
| `POST /api/reports/language-change` | So sánh văn bản trích xuất từ ít nhất hai báo cáo thường niên cùng chương/phần; trả lexical drift và các từ tăng/giảm tần suất. |
| `POST /api/explanation/numeric` | Tạo câu giải thích mẫu chỉ từ danh sách số đã tính, kèm nguồn/kỳ. Endpoint hiện không gọi LLM. |
| `POST /api/backtest/evaluate` | Nhận lịch sử ngày tín hiệu, ngày dữ liệu đã công bố, điểm số và lợi suất forward đã điều chỉnh; trả rank IC, t-stat, kiểm định hoán vị và chênh lệch nhóm cao/thấp. |
| `GET /api/reports/annual/available?ticker=FPT` | Tra cứu danh mục BCTN theo mã và năm trên Zenodo; chỉ tải CSV danh mục nhỏ khi tra cứu. |
| `GET /api/reports/annual/{ticker}/{year}/download` | Tải một PDF bằng HTTP Range từ ZIP Zenodo lớn, kiểm tra SHA-256, lưu cache vào `backend/data/company_reports/`. |
| `GET /api/reports/annual/{ticker}/{year}/text` | Tải theo yêu cầu và trích xuất lớp text của PDF bằng pypdf; chưa OCR PDF scan. |
| `POST /api/reports/annual/compare-language` | Chọn nhiều năm BCTN có trong danh mục; tải/trích xuất PDF và so sánh lexical drift toàn văn. |
| `GET /api/reports/financial/{ticker}?exchange=AUTO&years=5` | Lấy các bảng cân đối, kết quả kinh doanh và lưu chuyển tiền tệ từ vnfinancialdata/Hugging Face theo phạm vi dataset có sẵn. |
| `GET /api/news/company/{ticker}?company_name=...&company_website=...` | Lọc tiêu đề/tóm tắt RSS của CafeF, CafeBiz, VnExpress, VietnamNet, Tin Nhanh Chứng Khoán và VnEconomy; tùy chọn dò liên kết cùng domain từ trang doanh nghiệp do người dùng nhập; trả trạng thái từng nguồn. |

### Cơ sở và giới hạn phương pháp

- Điểm tin cậy dùng bảng trừ V01–V09 trong workbook nhóm: các khoản trừ lần lượt là 20/15/10/8/8/5/5/5/5. Các mức 1% sai lệch kế toán, 5% đối chiếu nguồn, 5 ngày dữ liệu cũ và 10% thiếu dữ liệu là ngưỡng khởi đầu có thể chỉnh trong request; chúng không phải chuẩn phổ quát.
- Điểm tổng hợp dùng bốn trụ cột. Workbook ghi 25/25/25/25 là điểm xuất phát cân bằng, còn trọng số theo khẩu vị và ngưỡng khuyến nghị là lựa chọn của nhóm; endpoint buộc trả cả ba bộ trọng số để xem độ nhạy.
- Endpoint ngôn ngữ đo cosine similarity của phân bố từ trong **cùng chương báo cáo**. Đây là thay đổi từ vựng, không phải kết luận cảm xúc hay chất lượng quản trị.
- Backtest yêu cầu dữ liệu point-in-time và lợi suất tương lai sau ngày tín hiệu; hàm kiểm tra ngày khả dụng, điều chỉnh giá, rank IC và p-value hoán vị. T-stat báo cáo là dạng iid đơn giản và cảnh báo nếu kỳ forward chồng lấn; chưa hiệu chỉnh HAC. Hệ thống chưa tự dựng lịch sử điểm số từ BCTC cũ. Cần tự cung cấp cả mã hủy niêm yết, benchmark, chi phí và giai đoạn holdout; nếu không, kết quả không đủ để khẳng định dự báo.
- So sánh peer live tự lấy dữ liệu qua vnstock nhưng chưa tự xác minh phân ngành. Nhóm cần chọn mã cùng ICB, cùng kỳ và đơn vị; bảng từ 3–5 mã chỉ cho trung vị tham khảo, chưa đủ để khẳng định phân vị thị trường.
- Các phương pháp Piotroski, Beneish và momentum có nghiên cứu nền tảng, nhưng mẫu và thị trường gốc không tự động chứng minh hiệu quả tại Việt Nam. Bảng nhóm cũng đánh dấu nhiều ngưỡng/trọng số là tự chọn; cần giữ chúng dưới dạng giả thuyết cho backtest ngoài mẫu, không trình bày như kết quả đã được xác nhận.

Nguồn nền tảng nên ghi trong thuyết minh phương pháp: [Piotroski (2000), bản bài báo](https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf); [Beneish (1999), DOI](https://doi.org/10.2469/FAJ.V55.N5.2296); [Jegadeesh & Titman (1993), DOI](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x); [Basel Committee, market-risk framework](https://www.bis.org/bcbs/publ/d457.htm). Đây là cơ sở nghiên cứu/khung giám sát; không phải xác nhận hiệu quả trên thị trường Việt Nam hoặc khuyến nghị đầu tư.

Ví dụ body cho `/api/scenario/analyze`:

```json
{
  "ticker": "FPT",
  "current_price": 120000,
  "eps": 6500,
  "earnings_growth_pct": 15,
  "target_pe": 18,
  "horizon_years": 2,
  "currency": "VND",
  "price_data": {"source": "Nguồn giá", "period": "2026-10-09", "retrieved_at": "2026-10-09"},
  "eps_data": {"source": "BCTC công bố", "period": "FY2025"},
  "overrides": {"bullish": {"earnings_growth_pct": 22, "target_pe": 21}}
}
```

Cài lại backend deps: python -m pip install -r backend\requirements.txt
Cài lại frontend deps: cd frontend; npm install


## Đối chiếu yêu cầu PDF và API bổ sung

Kịch bản nhận kỳ theo dõi `horizon_months` (3/6/12), xác suất tự nhập tổng 100%, lợi suất cổ tức giả định, ngưỡng BUY/HOLD/SELL và lưới độ nhạy (`sensitivity_growth_pct`, `sensitivity_pe`). Output có số quan sát hợp lệ, ngưỡng winsorization, số quan sát bị winsorize và điểm độ phủ dữ liệu (không phải xác suất đúng). Có thể cấu hình mục đích PDF, `metric_groups`, bật/tắt biểu đồ và chọn mức chi tiết. Các nhóm phân tích chưa được gửi dữ liệu chỉ được ghi rõ là chưa có, không tự điền số.

API bổ sung:

| Endpoint | Tính năng | Dữ liệu cần gửi |
|---|---|---|
| `POST /api/metrics/piotroski` | Tính F-Score 0–9 và trả từng tiêu chí | Hai kỳ BCTC có ROA, CFO, lợi nhuận, tài sản, nợ dài hạn, tài sản/nợ ngắn hạn, cổ phiếu lưu hành, biên gộp, vòng quay tài sản |
| `POST /api/metrics/dupont` | Phân rã ROE thành biên ròng × vòng quay tài sản × hệ số vốn chủ | Doanh thu, lợi nhuận ròng, tài sản bình quân, vốn chủ bình quân; kỳ và nguồn |
| `POST /api/metrics/debt-risk` | Net Debt/EBITDA, EBIT/chi phí lãi và cảnh báo | Số liệu nợ/EBITDA/EBIT/lãi vay; kỳ và nguồn |
| `POST /api/risk/market` | Biến động năm, drawdown tối đa, beta so với chỉ số benchmark | Chuỗi ngày giá cổ phiếu và VN-Index đã điều chỉnh, cùng ngày |
| `POST /api/backtest/scenario-coverage` | Đếm tỷ lệ giá tương lai nằm trong biên tiêu cực–tích cực | Các mức biên và giá thực tế sau ngày tín hiệu |
| `POST /api/data/validate` | Cảnh báo thiếu dữ liệu, kỳ/đơn vị, trùng lặp, ngoại lệ IQR | Quan sát đã chuẩn hóa, required_metrics tùy chọn |

Các endpoint Piotroski/DuPont/debt-risk và risk/market vẫn yêu cầu dữ liệu đầu vào; API BCTC riêng bên trên lấy bảng dữ liệu khả dụng từ vnfinancialdata nhưng chưa tự ghép/chọn chỉ tiêu cho mọi phép tính. Bộ BCTN có 134.8 GB theo Zenodo; API không tải nguyên kho, chỉ tải PDF được chọn, cần máy có kết nối Internet và hỗ trợ HTTP Range. Dataset bao phủ 2000–2025 theo metadata của Zenodo; báo cáo từng mã/năm có thể thiếu hoặc cần kiểm tra. BCTN scan có thể không trích xuất được text nếu không OCR. So sánh ngôn ngữ hiện so sánh toàn văn, chưa tự xác định cùng chương. RSS chỉ cho tiêu đề/tóm tắt và feed có thể thay đổi; chưa tải bài toàn văn hoặc quét toàn bộ website doanh nghiệp. Cài backend dependencies lại sau khi cập nhật `backend/requirements.txt`: `python -m pip install -r backend\requirements.txt`.
| `POST /api/valuation/pe-references` | Thống kê P25/trung vị/P75 P/E lịch sử và trung vị peer để làm bằng chứng chọn P/E mục tiêu | Danh sách P/E lịch sử/peer dương, kỳ, nguồn |
