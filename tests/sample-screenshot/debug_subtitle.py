from pathlib import Path
import cv2
from autotrans.config import AppConfig
from autotrans.models import Frame, Rect
from autotrans.services.ocr import RapidOCRProvider
from autotrans.services.subtitle import SubtitleDetector

image_path = Path('tests/sample-screenshot/original.png')
image = cv2.imread(str(image_path))
if image is None:
    raise SystemExit(f'Failed to read {image_path}')
config = AppConfig()
config.ocr_provider = 'rapidocr'
config.subtitle_mode = True
provider = RapidOCRProvider(config)
detector = SubtitleDetector(config)
frame = Frame(image=image, timestamp=0.0, window_rect=Rect(0, 0, image.shape[1], image.shape[0]))
boxes = provider.recognize(frame)
print('OCR boxes:', len(boxes))
for i, box in enumerate(boxes):
    print(f"OCR[{i}] text={box.source_text!r} conf={box.confidence:.3f} bbox=({box.bbox.x},{box.bbox.y},{box.bbox.width},{box.bbox.height}) words={len(box.source_text.split())}")
selected = detector.select(frame, boxes)
print('Selected boxes:', len(selected))
for i, box in enumerate(selected):
    print(f"SELECTED[{i}] text={box.source_text!r} conf={box.confidence:.3f} bbox=({box.bbox.x},{box.bbox.y},{box.bbox.width},{box.bbox.height}) words={len(box.source_text.split())}")
