# Cấu Hình Và Biến Môi Trường

## Nguồn cấu hình

App hiện nhận cấu hình từ 3 lớp:

1. `AppConfig` trong `src/autotrans/config.py`
2. `ui-settings.json` do `SettingsDialog` lưu
3. biến môi trường `AUTOTRANS_*`

Trong runtime thực tế:
- `SettingsDialog` là nguồn cấu hình người dùng chính
- một số path/runtime behavior vẫn lấy từ env

## Các nhóm cấu hình quan trọng

### Runtime paths

- `AUTOTRANS_RUNTIME_ROOT_DIR`
- `AUTOTRANS_LOCAL_MODEL_DIR`
- `AUTOTRANS_CACHE_ROOT_DIR`
- `AUTOTRANS_XDG_DATA_HOME`
- `AUTOTRANS_XDG_CACHE_HOME`
- `AUTOTRANS_XDG_CONFIG_HOME`
- `AUTOTRANS_HF_HOME`
- `AUTOTRANS_LOG_DIR`

Các path này được normalize về app root trong `AppConfig.__post_init__()`.

### Capture

- `AUTOTRANS_CAPTURE_BACKEND`
- `AUTOTRANS_CAPTURE_FPS`

### Overlay

- `AUTOTRANS_OVERLAY_FPS`
- `AUTOTRANS_FONT_SIZE`
- `AUTOTRANS_OVERLAY_BG_OPACITY`
- `AUTOTRANS_OVERLAY_BOX_PADDING`
- `AUTOTRANS_OVERLAY_TTL_SECONDS`
- `AUTOTRANS_OVERLAY_MAX_GROUPS`
- `AUTOTRANS_OVERLAY_SOURCE_TEXT`

### Subtitle selection

- `AUTOTRANS_SUBTITLE_MODE`
- `AUTOTRANS_SUBTITLE_REGION_TOP_RATIO`
- `AUTOTRANS_SUBTITLE_CENTER_TOLERANCE_PX`
- `AUTOTRANS_SUBTITLE_MIN_WIDTH_RATIO`
- `AUTOTRANS_SUBTITLE_MIN_CHARS`
- `AUTOTRANS_SUBTITLE_MAX_CANDIDATES`
- `AUTOTRANS_SUBTITLE_HOLD_FRAMES`
- `AUTOTRANS_DEBOUNCE_FRAMES`

### OCR

- `AUTOTRANS_OCR_PROVIDER`
- `AUTOTRANS_OCR_LANGUAGES`
- `AUTOTRANS_OCR_MIN_CONFIDENCE`
- `AUTOTRANS_OCR_PREPROCESS`
- `AUTOTRANS_OCR_MAX_SIDE`
- `AUTOTRANS_OCR_MAX_BOXES`
- `AUTOTRANS_OCR_CROP_SUBTITLE_ONLY`

Lưu ý:
- code hiện chỉ hỗ trợ `paddleocr`
- `ocr_languages` tồn tại ở config nhưng `PaddleOCRProvider` hiện cố định dùng recognition model Latin-script

### Local translator

- `AUTOTRANS_LOCAL_MODEL_PATH`
- `AUTOTRANS_LOCAL_MODEL_REPO`
- `AUTOTRANS_LOCAL_MODEL_DEVICE`
- `AUTOTRANS_LOCAL_MODEL_COMPUTE_TYPE`
- `AUTOTRANS_LOCAL_INTER_THREADS`
- `AUTOTRANS_LOCAL_INTRA_THREADS`
- `AUTOTRANS_LOCAL_TARGET_PREFIX`

### Deep translation

- `AUTOTRANS_DEEP_TRANSLATION_API_KEY`
- `AUTOTRANS_DEEP_TRANSLATION_MODEL`
- `AUTOTRANS_DEEP_TRANSLATION_TRANSPORT`
- `AUTOTRANS_DEEP_TRANSLATION_TIMEOUT_MS`
- `AUTOTRANS_CLOUD_TIMEOUT_MS`

### Game profile cho Gemini

- `AUTOTRANS_GAME_PROFILE_TITLE`
- `AUTOTRANS_GAME_PROFILE_WORLD`
- `AUTOTRANS_GAME_PROFILE_FACTIONS`
- `AUTOTRANS_GAME_PROFILE_CHARACTERS_HONORIFICS`
- `AUTOTRANS_GAME_PROFILE_TERMS_ITEMS_SKILLS`

Các field này được đưa vào system instruction của deep mode Gemini.

## Runtime directories mặc định

Mặc định app dùng thư mục `.runtime/` tại root repo hoặc cạnh file executable khi build.

Các nhánh dữ liệu chính:
- `.runtime/paddlex-cache`
- `.runtime/models`
- `.runtime/translation-cache`
- `.runtime/logs`
- `.runtime/xdg`
- `.runtime/huggingface`

## Cache và model

### OCR model

Paddle model được tìm trong:
- `PADDLE_PDX_CACHE_HOME/official_models/...`
- `~/.paddlex/official_models/...` nếu app không tìm thấy model trong runtime cache

Ưu tiên recognition model:
- `en_PP-OCRv5_mobile_rec`

Alias vẫn được resolve nếu máy còn cache cũ:
- `latin_PP-OCRv5_rec_mobile`
- `latin_PP-OCRv5_mobile_rec`
- `en_PP-OCRv5_mobile_rec`

### Local translation model

`CTranslate2Translator` dùng:
- local dir từ `local_model_dir`
- hoặc tự tải từ `local_model_repo` nếu thư mục model đang rỗng

## Cấu hình nào nhạy cảm nhất

Khi maintain, chú ý đặc biệt:
- `ocr_crop_subtitle_only`
- `subtitle_region_top_ratio`
- `capture_backend`
- `deep_translation_model`
- `overlay_max_groups`
- `local_model_compute_type`

