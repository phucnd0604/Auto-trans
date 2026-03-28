from autotrans.services.cache import TranslationCache


def test_cache_key_normalizes_whitespace() -> None:
    cache = TranslationCache()
    cache.put("Hello   world", "en", "vi", "v1", "Xin chao", "local")
    entry = cache.get(" Hello world ", "en", "vi", "v1")
    assert entry is not None
    assert entry.translated_text == "Xin chao"
    assert cache.hits == 1