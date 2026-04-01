 # Changelog

## 2026-04-01

### Repo

- Chuẩn hóa repo theo hướng chạy từ source bằng `venv` hoặc build `.exe`.
- Gom tài liệu dự án về thư mục `docs/` để dễ tra cứu và bảo trì.

### OCR

- Chuẩn hóa cả realtime OCR và deep mode OCR sang `PaddleOCR`.
- Chuyển recognition model mặc định sang `en_PP-OCRv5_mobile_rec`.
- Giữ fallback cho cache model cũ như `latin_PP-OCRv5_rec_mobile` và `latin_PP-OCRv5_mobile_rec`.
- Sửa retry vô hạn khi `PaddleOCR` init fail: lazy OCR provider giờ giữ lại lỗi gốc và không khởi tạo lặp lại mỗi tick.
- Warm up OCR ngay sau startup ở background để giảm độ trễ ở lần OCR đầu tiên.
- Khi bật deep mode, realtime pipeline sẽ tạm pause trong pha `prepare_deep_translation` để giảm tranh chấp tài nguyên.
- Sửa parser layout region để xử lý đúng `numpy.ndarray` từ `LayoutDetection`.

### Translation

- Realtime chỉ dùng local `ctranslate2`.
- Deep mode giữ luồng `Gemini -> fallback ctranslate2`.

### UI

- Khi pipeline OCR runtime gặp lỗi, UI tự dừng realtime thay vì tiếp tục retry với log spam.
- Giữ các trạng thái deep mode, overlay và tooltip đồng bộ với flow runtime hiện tại.

### Test Và Tài Liệu

- Cập nhật benchmark/documentation theo model `en_PP-OCRv5_mobile_rec`.
- Cập nhật script retest cho `ocr realtime` và `ocr deepmode` trên Windows PowerShell.
- Làm mới baseline benchmark realtime và deepmode preview.
- Bổ sung test cho warmup OCR, cache lỗi init OCR và pause realtime trong pha prepare của deep mode.

## 2026-03-31

### Realtime OCR

- Thêm `PaddleOCR` vào luồng OCR realtime để đánh giá hiệu năng.
- Tối ưu OCR realtime cho workload subtitle crop.
- Bổ sung benchmark subtitle runtime với bộ 11 ảnh mẫu.

### Startup Và Logging

- Đưa việc khởi tạo OCR/translator nặng về lazy initialization.
- Bổ sung log runtime chi tiết cho OCR, cache và translation để thuận tiện benchmark.

### UI

- Thêm tooltip mô tả chi tiết cho các setting runtime và deep translation.
