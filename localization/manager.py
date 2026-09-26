from localization.translations import TRANSLATIONS

DEFAULT_LANGUAGE = "en"


def get_text(key: str, language: str = DEFAULT_LANGUAGE, **values: object) -> str:
    """Return a translated string, falling back to English for missing entries."""
    translation = TRANSLATIONS.get(language, TRANSLATIONS[DEFAULT_LANGUAGE])
    text = translation.get(key, TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key))
    return text.format(**values)