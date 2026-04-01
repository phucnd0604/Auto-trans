# Maintain Và Test Plan

## Mục tiêu

Tài liệu này giúp maintain project sau khi sửa OCR, deepmode, translator hoặc UI runtime.

## Nguyên tắc maintain

- Giữ realtime và deepmode tách biệt về mục tiêu tối ưu
- Bất kỳ thay đổi nào ở deepmode phải kiểm tra lại xem realtime có bị ảnh hưởng không
- Nếu thay đổi OCR stack, luôn benchmark lại trên cùng bộ sample trước khi kết luận
- Nếu thay đổi prompt Gemini, luôn render lại deepmode runtime preview

## Checklist theo loại thay đổi

### 1. Sửa realtime OCR

Phải kiểm tra:
- benchmark 11 ảnh subtitle
- số box sau selection
- latency trung bình
- chất lượng subtitle crop

Chạy:
- `tests/ocr_test/benchmark_subtitle_runtime.py`

### 2. Sửa deepmode OCR/layout

Phải kiểm tra:
- số line box
- số grouped deep boxes
- chất lượng map line -> region
- block quest có còn được merge đúng không

Chạy:
- `tests/sample-screenshot/render_deepmode_ocr_preview.py`

### 3. Sửa translator/prompt

Phải kiểm tra:
- deepmode runtime preview với `ctranslate2`
- deepmode runtime preview với Gemini
- fallback `Gemini -> ctranslate2`

Chạy:
- `tests/sample-screenshot/render_deepmode_runtime_preview.py`

### 4. Sửa UI/runtime state

Phải kiểm tra:
- Start/Stop pipeline
- toggle overlay
- toggle deepmode
- timeout deepmode
- status message

## Bộ test và script quan trọng

### Unit / integration tests

- `tests/test_deep_mode.py`
- `tests/test_ocr_runtime_providers.py`

### Benchmark / preview scripts

- `tests/ocr_test/benchmark_subtitle_runtime.py`
- `tests/sample-screenshot/render_deepmode_ocr_preview.py`
- `tests/sample-screenshot/render_deepmode_runtime_preview.py`

## Kết quả benchmark hiện là baseline

Baseline hiện tại của realtime OCR:
- `runtime-default`: khoảng `226.85ms`
- `runtime-no-crop`: khoảng `1000.25ms`
- `runtime-det-640`: khoảng `1765.92ms`
- `runtime-latin-rec`: khoảng `204.32ms`

Các số này là mốc tham chiếu để phát hiện regression, không phải SLA cứng.

## Regression dễ gặp

### OCR

- tăng detection size quá lớn
- bỏ subtitle crop
- thay model nhận dạng làm OCR chậm hoặc bẩn hơn

### Deepmode

- layout model không load được
- paragraph merge vỡ block quest
- tăng số block HUD/menu quá nhiều

### Translation

- prompt Gemini khiến menu label bị văn vẻ quá mức
- local translator output unusable và bị drop nhiều
- cloud fallback không kích hoạt khi quota/lỗi mạng

## Quy trình xác nhận sau thay đổi lớn

1. `py_compile`
2. benchmark realtime OCR
3. render deepmode OCR preview
4. render deepmode runtime preview với `ctranslate2`
5. nếu có key và mạng, render lại với Gemini
6. rà log trong `.runtime/logs/autotrans.log`

## Tài liệu liên quan

- [Kiến trúc hệ thống](./architecture.md)
- [Flow realtime](./runtime-flow.md)
- [Flow deep mode](./deepmode-flow.md)
- [Cấu hình và biến môi trường](./configuration-and-env.md)
- [Hướng dẫn benchmark OCR và test deepmode](./ocr-benchmark-and-deepmode.md)

