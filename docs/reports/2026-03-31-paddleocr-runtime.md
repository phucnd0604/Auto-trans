# Báo Cáo 2026-03-31: PaddleOCR Realtime Runtime

## Phạm vi

Báo cáo này tóm tắt giai đoạn đánh giá `PaddleOCR` cho realtime OCR, các thay đổi liên quan tới startup, logging và kết quả benchmark thời điểm đó.

## Các thay đổi đã thực hiện tại thời điểm báo cáo

- Thêm `PaddleOCRProvider` cho luồng OCR realtime
- Giữ deep mode riêng ở nhánh khác trong giai đoạn chuyển đổi
- Bổ sung lazy initialization cho OCR và translator
- Tăng mức chi tiết của runtime logging để phân tích OCR thực tế

## Tóm tắt benchmark

Nguồn: `tests/ocr_test/subtitle_runtime_benchmark.json`

Tập test:
- 11 ảnh subtitle mẫu từ `tests/ocr_test/sub*.png`

Kết quả headline ở thời điểm báo cáo:
- `rapidocr/runtime-default`: `avg_ocr=541.12ms`, `avg_total=542.31ms`
- `paddleocr/runtime-default`: `avg_ocr=150.46ms`, `avg_total=151.62ms`
- `paddleocr/runtime-no-cls-det-640`: `avg_ocr=144.47ms`, `avg_total=145.86ms`
- `paddleocr/runtime-no-crop`: `avg_ocr=360.58ms`, `avg_total=361.94ms`

## Nhận định

- `PaddleOCR` nhanh hơn `RapidOCR` rõ rệt trên workload subtitle crop
- `ocr_crop_subtitle_only=true` là yếu tố rất quan trọng với realtime OCR
- Chi phí lớn nhất thời điểm đó nằm ở thời gian khởi tạo provider, không phải mỗi lần OCR

## Giá trị lịch sử của báo cáo

Đây là báo cáo mốc để đối chiếu trước và sau khi repo chuyển hẳn sang `PaddleOCR` cho cả realtime lẫn deep mode.

