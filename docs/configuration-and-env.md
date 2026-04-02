# Cau Hinh Va Bien Moi Truong

## Nguon cau hinh

App hien nhan cau hinh tu 3 lop:

1. `AppConfig` trong `src/autotrans/config.py`
2. `ui-settings.json` do `SettingsDialog` luu
3. bien moi truong `AUTOTRANS_*`

Trong runtime thuc te:
- `SettingsDialog` la nguon cau hinh nguoi dung chinh
- mot so path va runtime behavior van lay tu env

## Cac nhom cau hinh quan trong

### Runtime paths

- `AUTOTRANS_RUNTIME_ROOT_DIR`
- `AUTOTRANS_LOCAL_MODEL_DIR`
- `AUTOTRANS_CACHE_ROOT_DIR`
- `AUTOTRANS_XDG_DATA_HOME`
- `AUTOTRANS_XDG_CACHE_HOME`
- `AUTOTRANS_XDG_CONFIG_HOME`
- `AUTOTRANS_HF_HOME`
- `AUTOTRANS_LOG_DIR`

Cac path nay duoc normalize ve app root trong `AppConfig.__post_init__()`.

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

Luu y:
- code hien chi ho tro `paddleocr`
- `ocr_languages` ton tai o config nhung `PaddleOCRProvider` hien co dinh dung recognition model Latin-script

### Local translator

- `AUTOTRANS_LOCAL_MODEL_PATH`
- `AUTOTRANS_LOCAL_MODEL_REPO`
- `AUTOTRANS_LOCAL_MODEL_DEVICE`
- `AUTOTRANS_LOCAL_MODEL_COMPUTE_TYPE`
- `AUTOTRANS_LOCAL_INTER_THREADS`
- `AUTOTRANS_LOCAL_INTRA_THREADS`
- `AUTOTRANS_LOCAL_TARGET_PREFIX`
- `AUTOTRANS_LOCAL_BEAM_SIZE`
- `AUTOTRANS_LOCAL_REPETITION_PENALTY`
- `AUTOTRANS_LOCAL_NO_REPEAT_NGRAM_SIZE`
- `AUTOTRANS_LOCAL_MAX_DECODING_LENGTH`

Realtime local translator hien duoc tune mac dinh theo huong:
- `beam_size=2`
- `repetition_penalty=1.1`
- `no_repeat_ngram_size=3`
- `max_decoding_length=128`

Muc tieu cua bo mac dinh nay la giu latency realtime gan baseline QuickMT nhung bot literal va giam nguy co lap token.

### Deep translation

- `AUTOTRANS_DEEP_TRANSLATION_API_KEY`
- `AUTOTRANS_DEEP_TRANSLATION_PROVIDER` (`gemini` hoặc `groq`)
- `AUTOTRANS_DEEP_TRANSLATION_MODEL`
- `AUTOTRANS_DEEP_TRANSLATION_TRANSPORT`
- `AUTOTRANS_DEEP_TRANSLATION_TIMEOUT_MS`
- `AUTOTRANS_CLOUD_TIMEOUT_MS`

### Game profile cho deep cloud translation

- `AUTOTRANS_GAME_PROFILE_TITLE`
- `AUTOTRANS_GAME_PROFILE_WORLD`
- `AUTOTRANS_GAME_PROFILE_FACTIONS`
- `AUTOTRANS_GAME_PROFILE_CHARACTERS_HONORIFICS`
- `AUTOTRANS_GAME_PROFILE_TERMS_ITEMS_SKILLS`

Cac field nay duoc dua vao system instruction cua deep mode cloud provider.

## Runtime directories mac dinh

Mac dinh app dung thu muc `.runtime/` tai root repo hoac canh file executable khi build.

Cac nhanh du lieu chinh:
- `.runtime/paddlex-cache`
- `.runtime/models`
- `.runtime/translation-cache`
- `.runtime/logs`
- `.runtime/xdg`
- `.runtime/huggingface`

## Cache va model

### OCR model

Paddle model duoc tim trong:
- `PADDLE_PDX_CACHE_HOME/official_models/...`
- `~/.paddlex/official_models/...` neu app khong tim thay model trong runtime cache

Uu tien recognition model:
- `en_PP-OCRv5_mobile_rec`

Alias van duoc resolve neu may con cache cu:
- `latin_PP-OCRv5_rec_mobile`
- `latin_PP-OCRv5_mobile_rec`
- `en_PP-OCRv5_mobile_rec`

### Local translation model

`CTranslate2Translator` dung:
- local dir tu `local_model_dir`
- hoac tu tai tu `local_model_repo` neu thu muc model dang rong

## Cau hinh nao nhay cam nhat

Khi maintain, chu y dac biet:
- `ocr_crop_subtitle_only`
- `subtitle_region_top_ratio`
- `capture_backend`
- `deep_translation_model`
- `overlay_max_groups`
- `local_model_compute_type`
- `local_beam_size`
- `local_repetition_penalty`
