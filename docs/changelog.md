# Changelog

## 2026-04-02

### Runtime va Moi truong

- Chuan hoa `run.ps1` de co the tu tao `.venv`, sync dependency, sync model runtime va chay app trong cung mot flow.
- Bo sung che do `-SyncEnv`, `-SyncModels`, `-RecreateVenv`, `-SkipRun` cho script runtime.
- Them buoc bootstrap model runtime de local translator model va Paddle models duoc tai/kiem tra truoc khi mo app.
- Chuan hoa duong dan cache Paddle/PaddleX ve `.runtime/paddle` thay vi de phan tan ra thu muc home cua user.

### Translation va Deep Mode

- Them logging startup ro hon cho cloud translator: provider, model, tinh trang API key, va traceback day du khi fallback.
- Deep mode Groq da duoc giu dung provider/model sau khi sua settings va flow khoi tao.
- Khoi phuc grouping OCR block trong deep mode de overlay dung block da gom thay vi box OCR tho.

### Subtitle va Overlay

- Bo filter `uppercase_label` trong subtitle detector de subtitle viet toan chu hoa khong bi loai oan.
- Bo penalty cham diem rieng cho subtitle all-caps trong subtitle mode.

### Tai lieu

- Cap nhat `README` va huong dan khoi dong de phan anh flow sync env/model moi.
- Cap nhat tai lieu benchmark/deepmode de dung `PADDLE_HOME` va `PADDLE_PDX_CACHE_HOME` tro ve `.runtime/paddle`.

## 2026-04-01

### Repo

- Chuan hoa repo theo huong chay tu source bang `venv` hoac build `.exe`.
- Gom tai lieu du an ve thu muc `docs/` de de tra cuu va bao tri.

### OCR

- Chuan hoa ca realtime OCR va deep mode OCR sang `PaddleOCR`.
- Chuyen recognition model mac dinh sang `en_PP-OCRv5_mobile_rec`.
- Giu fallback cho cache model cu nhu `latin_PP-OCRv5_rec_mobile` va `latin_PP-OCRv5_mobile_rec`.
- Sua retry vo han khi `PaddleOCR` init fail: lazy OCR provider gio giu lai loi goc va khong khoi tao lap lai moi tick.
- Warm up OCR ngay sau startup o background de giam do tre o lan OCR dau tien.
- Khi bat deep mode, realtime pipeline se tam pause trong pha `prepare_deep_translation` de giam tranh chap tai nguyen.
- Sua parser layout region de xu ly dung `numpy.ndarray` tu `LayoutDetection`.

### Translation

- Realtime chi dung local `ctranslate2`.
- Deep mode giu luong `Gemini -> fallback ctranslate2`.
- Them benchmark local translator tach rieng khoi OCR, co JSON/Markdown report va tap cau subtitle/quest/UI dai dien.
- Sua logging cua `CTranslate2Translator` de khong crash tren Windows console codepage khi in tieng Viet.
- Benchmark thuc te cho thay `quickmt/quickmt-en-vi` van la default tot nhat trong shortlist da test.

### UI

- Khi pipeline OCR runtime gap loi, UI tu dung realtime thay vi tiep tuc retry voi log spam.
- Giu cac trang thai deep mode, overlay va tooltip dong bo voi flow runtime hien tai.

### Test va Tai lieu

- Cap nhat benchmark/documentation theo model `en_PP-OCRv5_mobile_rec`.
- Cap nhat script retest cho `ocr realtime` va `ocr deepmode` tren Windows PowerShell.
- Lam moi baseline benchmark realtime va deep mode preview.
- Bo sung test cho warmup OCR, cache loi init OCR, pause realtime trong pha prepare cua deep mode, va benchmark local translator.

## 2026-03-31

### Realtime OCR

- Them `PaddleOCR` vao luong OCR realtime de danh gia hieu nang.
- Toi uu OCR realtime cho workload subtitle crop.
- Bo sung benchmark subtitle runtime voi bo 11 anh mau.

### Startup va Logging

- Dua viec khoi tao OCR/translator nang ve lazy initialization.
- Bo sung log runtime chi tiet cho OCR, cache va translation de thuan tien benchmark.

### UI

- Them tooltip mo ta chi tiet cho cac setting runtime va deep translation.
