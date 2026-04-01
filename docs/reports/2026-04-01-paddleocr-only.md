# Báo Cáo 2026-04-01: PaddleOCR-Only OCR

## Phạm vi

Báo cáo này tổng kết trạng thái sau khi loại bỏ `RapidOCR` khỏi app và test workspace, đồng thời chuẩn hóa OCR sang `PaddleOCR`.

## Thay đổi chính

- Loại bỏ `RapidOCRProvider` và logic chọn runtime theo `rapidocr`
- Chuẩn hóa cả realtime OCR và deep mode OCR sang `PaddleOCR`
- Giữ deep mode layout analysis trên Paddle layout detection với `PP-DocLayout-S`
- Cố định startup setting `OCR Provider` thành `paddleocr`
- Loại bỏ dependency `rapidocr_onnxruntime`
- Dọn benchmark/debug script cũ chỉ phục vụ RapidOCR
- Viết lại benchmark subtitle runtime theo hướng Paddle-only

## Hành vi model

- Realtime và deep mode cùng khởi tạo qua `PaddleOCRProvider` trong `src/autotrans/services/ocr.py`
- Recognition model ưu tiên là `latin_PP-OCRv5_rec_mobile`
- Nếu máy chỉ còn local cache cũ như `en_PP-OCRv5_mobile_rec`, provider vẫn có thể resolve để giữ tương thích
- Nếu cache chưa có model và môi trường có mạng, Paddle có thể tự tải model cần thiết

## Benchmark OCR realtime

Nguồn: `tests/ocr_test/subtitle_runtime_benchmark.json`

Tập test:
- 11 ảnh subtitle từ `tests/ocr_test/sub*.png`

Kết quả từ lần chạy gần nhất trong `./.venv`:
- `paddleocr/runtime-default`: `avg_ocr=226.85ms`, `avg_total=228.53ms`
- `paddleocr/runtime-no-crop`: `avg_ocr=1000.25ms`, `avg_total=1000.50ms`
- `paddleocr/runtime-det-640`: `avg_ocr=1765.92ms`, `avg_total=1766.18ms`
- `paddleocr/runtime-latin-rec`: `avg_ocr=204.32ms`, `avg_total=204.52ms`

## Nhận định từ benchmark

- Subtitle crop vẫn là tối ưu quan trọng nhất cho realtime OCR
- Detection size `640` chậm hơn rõ rệt trên luồng runtime hiện tại
- Cấu hình Paddle-only mặc định hiện vẫn phù hợp cho subtitle OCR realtime

## Deep mode OCR preview

Nguồn script: `tests/sample-screenshot/render_deepmode_ocr_preview.py`

Tóm tắt từ lần chạy gần nhất:
- `quest1.png`: `47` line boxes, `42` grouped deep boxes
- `quest2.png`: `45` line boxes, `39` grouped deep boxes

## Đánh giá hiện tại

- Repo đơn giản hơn đáng kể vì OCR chỉ còn một stack
- Realtime OCR vẫn đủ nhanh khi subtitle crop được bật
- Deep mode OCR vẫn hoạt động tốt với Paddle layout grouping
- Cơ hội dọn tiếp tiếp theo là xóa cache model cũ khi local machine đã có đủ model mục tiêu

