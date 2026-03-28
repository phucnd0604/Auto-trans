from autotrans.config import AppConfig
from autotrans.models import OCRBox, QualityMode, Rect
from autotrans.services.translation import CTranslate2Translator

translator = CTranslate2Translator(AppConfig())
texts = [
    'RESTARTFROMLASTCHECKPOINT',
    'EXIT TO TITLE SCREEN',
    'SAVE GAME',
    'Lord Shimura: Break my block with a heavy attack, then strike quickly.',
    'TAPTOBREAKDEFENSEAND THEN TOQUICK ATTACK 0/4 STAGGERENEMY',
    "Yuna's brother is finally safe, but we had to split up after our escape.",
]
items = [OCRBox(id='', source_text=t, confidence=1.0, bbox=Rect(0,0,100,20)) for t in texts]
for result in translator.translate_batch(items, 'en', 'vi', QualityMode.BALANCED):
    print(result.source_text)
    print('=>', result.translated_text)
    print()
