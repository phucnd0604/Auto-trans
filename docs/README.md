# Tài Liệu AutoTrans

Thư mục này là nơi lưu trữ tài liệu chính thức của dự án.

## Mục lục

- [Bắt đầu nhanh](./getting-started.md)
- [Kiến trúc hệ thống](./architecture.md)
- [Flow realtime](./runtime-flow.md)
- [Flow deep mode](./deepmode-flow.md)
- [Cấu hình và biến môi trường](./configuration-and-env.md)
- [Maintain và test plan](./maintenance-and-test-plan.md)
- [Hướng dẫn benchmark OCR và test deepmode](./ocr-benchmark-and-deepmode.md)
- [Changelog](./changelog.md)
- Báo cáo:
  - [2026-03-31: PaddleOCR realtime runtime](./reports/2026-03-31-paddleocr-runtime.md)
  - [2026-04-01: PaddleOCR-only OCR](./reports/2026-04-01-paddleocr-only.md)

## Phạm vi tài liệu

- Chạy dự án từ source bằng `venv`
- Build file `.exe`
- Nắm kiến trúc, flow runtime và điểm nối giữa các service
- Hiểu cách realtime và deepmode vận hành độc lập
- Theo dõi cấu hình/env ảnh hưởng tới OCR, cache và translator
- Benchmark OCR realtime trên bộ 11 ảnh subtitle mẫu
- Test deepmode OCR và deepmode runtime preview
- Theo dõi các thay đổi lớn của OCR/runtime qua changelog và report

## Gợi ý đọc theo nhu cầu

- Nếu mới clone project: đọc [Bắt đầu nhanh](./getting-started.md)
- Nếu cần hiểu codebase: đọc [Kiến trúc hệ thống](./architecture.md)
- Nếu cần sửa pipeline: đọc [Flow realtime](./runtime-flow.md) và [Flow deep mode](./deepmode-flow.md)
- Nếu cần chỉnh env/config: đọc [Cấu hình và biến môi trường](./configuration-and-env.md)
- Nếu cần kiểm tra hiệu năng OCR: đọc [Hướng dẫn benchmark OCR và test deepmode](./ocr-benchmark-and-deepmode.md)
- Nếu cần nắm bối cảnh kỹ thuật gần đây: đọc các file trong [reports](./reports)
