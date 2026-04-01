# Changelog

## 2026-04-01

### Repo

- Loại bỏ toàn bộ portable/share script cũ và các Windows command wrapper không còn dùng.
- Chuẩn hóa repo theo hướng chạy từ source bằng `venv` hoặc build `.exe`.
- Gom tài liệu dự án về thư mục `docs/` để dễ tra cứu và bảo trì.

### OCR

- Deep mode chuyển sang `PaddleOCR` paragraph OCR kết hợp Paddle layout detection.
- OCR realtime mặc định là `paddleocr`.
- Loại bỏ `RapidOCR`, `rapid-layout` và các script benchmark/debug liên quan khỏi app và test workspace.
- Chuẩn hóa recognition model ưu tiên là `latin_PP-OCRv5_rec_mobile`, đồng thời vẫn hỗ trợ fallback cache cũ nếu có.

### Translation

- Bỏ nhánh dịch `word-by-word`.
- Deep mode giữ luồng `Gemini -> fallback ctranslate2`.
- Prompt Gemini được thống nhất lại để dễ hiểu và nhất quán hơn.

### UI

- Chuẩn hóa các chuỗi tiếng Việt có dấu trong phần settings, trạng thái deepmode và thông báo chờ dịch.

## 2026-03-31

### Realtime OCR

- Thêm `PaddleOCR` vào luồng OCR realtime để đánh giá hiệu năng.
- Tối ưu OCR realtime cho workload subtitle crop.
- Bổ sung benchmark subtitle runtime với bộ 11 ảnh mẫu.

### Startup và Logging

- Đưa việc khởi tạo OCR/translator nặng về lazy initialization.
- Bổ sung log runtime chi tiết cho OCR, cache và translation để thuận tiện benchmark.

### UI

- Thêm tooltip mô tả chi tiết cho các setting runtime và deep translation.

