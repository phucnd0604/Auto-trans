from pathlib import Path
import cv2
from autotrans.config import AppConfig
from autotrans.models import Frame, Rect
from autotrans.services.ocr import RapidOCRProvider
from autotrans.services.subtitle import SubtitleDetector

config = AppConfig()
config.ocr_provider = 'rapidocr'
config.subtitle_mode = True
provider = RapidOCRProvider(config)
detector = SubtitleDetector(config)

for image_path in sorted(Path('tests/sample-screenshot').glob('*.png')):
    image = cv2.imread(str(image_path))
    if image is None:
        print(f'FAILED to read {image_path}')
        continue
    frame = Frame(image=image, timestamp=0.0, window_rect=Rect(0, 0, image.shape[1], image.shape[0]))
    boxes = provider.recognize(frame)
    selected = detector.select(frame, boxes)
    print(f'=== {image_path.name} ===')
    print(f'OCR boxes: {len(boxes)}')
    for i, box in enumerate(boxes):
        print(f"OCR[{i}] text={box.source_text!r} bbox=({box.bbox.x},{box.bbox.y},{box.bbox.width},{box.bbox.height})")
    print(f'Selected boxes: {len(selected)}')
    for i, box in enumerate(selected):
        print(f"SELECTED[{i}] text={box.source_text!r} bbox=({box.bbox.x},{box.bbox.y},{box.bbox.width},{box.bbox.height})")
    print()
