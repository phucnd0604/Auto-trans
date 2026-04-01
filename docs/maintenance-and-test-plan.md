# Maintain and Test Plan

## Muc tieu

Tai lieu nay giup maintain project sau khi sua OCR, deep mode, local translator, hoac UI runtime.

## Nguyen tac maintain

- Giu realtime va deep mode tach biet ve muc tieu toi uu.
- Bat ky thay doi nao o deep mode phai kiem tra lai xem realtime co bi anh huong khong.
- Neu thay doi OCR stack, luon benchmark lai tren cung bo sample truoc khi ket luan.
- Neu thay doi local translator model, luon benchmark rieng translator truoc khi danh gia runtime.
- Neu thay doi prompt Gemini, luon render lai deep mode runtime preview.

## Checklist theo loai thay doi

### 1. Sua realtime OCR

Phai kiem tra:
- benchmark 11 anh subtitle
- so box sau selection
- latency trung binh
- chat luong subtitle crop

Chay:
- `tests/ocr_test/benchmark_subtitle_runtime.py`

### 2. Sua deep mode OCR/layout

Phai kiem tra:
- so line box
- so grouped deep boxes
- chat luong map line -> region
- block quest con duoc merge dung hay khong

Chay:
- `tests/sample-screenshot/render_deepmode_ocr_preview.py`

### 3. Sua translator/prompt

Phai kiem tra:
- local translator benchmark voi `quickmt` baseline
- local translator benchmark voi candidate `ctranslate2` model khac neu dang can nhac thay model realtime
- deep mode runtime preview voi `ctranslate2`
- deep mode runtime preview voi Gemini
- fallback `Gemini -> ctranslate2`

Chay:
- `tests/translation_test/benchmark_local_translator.py`
- `tests/sample-screenshot/render_deepmode_runtime_preview.py`

### 4. Sua UI/runtime state

Phai kiem tra:
- Start/Stop pipeline
- toggle overlay
- toggle deep mode
- timeout deep mode
- status message

## Bo test va script quan trong

### Unit / integration tests

- `tests/test_deep_mode.py`
- `tests/test_ocr_runtime_providers.py`
- `tests/test_local_translator_benchmark.py`

### Benchmark / preview scripts

- `tests/ocr_test/benchmark_subtitle_runtime.py`
- `tests/translation_test/benchmark_local_translator.py`
- `tests/sample-screenshot/render_deepmode_ocr_preview.py`
- `tests/sample-screenshot/render_deepmode_runtime_preview.py`

## Baseline hien tai

Realtime OCR baseline:
- `runtime-default`: khoang `427.77ms`
- `runtime-no-crop`: khoang `639.01ms`
- `runtime-det-640`: khoang `850.71ms`
- `runtime-en-rec`: khoang `191.43ms`

Local translator baseline:
- `quickmt-en-vi`: `cold_start=2563.88ms`, `single_avg=54.87ms`, `single_p95=83.52ms`, `throughput=42.01 items/s`
- `opus-mt-en-vi-ctranslate2`: khong dat baseline vi cham hon rat nhieu va quality bi degenerate

## Regression de gap

### OCR

- tang detection size qua lon
- bo subtitle crop
- thay model nhan dang lam OCR cham hoac ban hon

### Deep mode

- layout model khong load duoc
- paragraph merge vo block quest
- tang so block HUD/menu qua nhieu

### Translation

- prompt Gemini khien menu label bi van ve qua muc
- local translator output unusable va bi drop nhieu
- thay local model lam warm latency tang hoac throughput giam so voi `quickmt/quickmt-en-vi`
- cloud fallback khong kich hoat khi quota hoac loi mang

## Quy trinh xac nhan sau thay doi lon

1. `py_compile`
2. benchmark realtime OCR
3. benchmark local translator neu doi `AUTOTRANS_LOCAL_MODEL_REPO`
4. render deep mode OCR preview
5. render deep mode runtime preview voi `ctranslate2`
6. neu co key va mang, render lai voi Gemini
7. ra log trong `.runtime/logs/autotrans.log`

## Tai lieu lien quan

- [Kien truc he thong](./architecture.md)
- [Flow realtime](./runtime-flow.md)
- [Flow deep mode](./deepmode-flow.md)
- [Cau hinh va bien moi truong](./configuration-and-env.md)
- [Huong dan benchmark OCR va test deep mode](./ocr-benchmark-and-deepmode.md)
