from autotrans.config import AppConfig
from autotrans.models import OCRBox, QualityMode, Rect
from autotrans.services.translation import CTranslate2Translator

translator = CTranslate2Translator(AppConfig())
texts = [
    "Yuna's brother is finally safe, but we had to split up after our escape.",
    "I should make sure they reached the town of Komatsu Forge.",
    "If Taka's had time to recover, he may be able to make me a tool to climb the walls of my uncle's prison at Castle Kaneda.",
    "Go to the town of Komatsu Forge",
]
items = [OCRBox(id='', source_text=t, confidence=1.0, bbox=Rect(0,0,100,20)) for t in texts]
for result in translator.translate_batch(items, 'en', 'vi', QualityMode.BALANCED):
    print(result.source_text)
    print('=>', result.translated_text)
    print()
