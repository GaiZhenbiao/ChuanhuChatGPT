import os
import locale
import logging
import commentjson as json

LOCALE_DIR = "./locale"
SOURCE_LANGUAGE = "zh_CN"     # the language the strings are authored in
FALLBACK_LANGUAGE = "en_US"   # tried before falling back to the source language


def _flatten(tree, prefix=""):
    """Flatten the nested locale tree into {"ui.chat.model_select": "..."}."""
    flat = {}
    for key, value in tree.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, dotted))
        else:
            flat[dotted] = value
    return flat


def _load(language):
    path = os.path.join(LOCALE_DIR, f"{language}.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return _flatten(json.load(f))


class I18nAuto:
    """Resolves hierarchical string identifiers, e.g. i18n("ui.chat.model_select").

    User-facing text is never written in the code: a call site only names a
    string, and the wording for the active language is looked up here, so the
    same identifier can be translated differently per language.
    """

    def __init__(self):
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}
        language = config.get("language", "auto")
        language = os.environ.get("LANGUAGE", language)
        language = language.replace("-", "_")
        if language == "auto":
            # get the language code of the system (ex. zh_CN)
            language = locale.getdefaultlocale()[0]
        self.fallback_map = _load(FALLBACK_LANGUAGE) or {}
        self.source_map = _load(SOURCE_LANGUAGE) or {}
        self.change_language(language)

    def change_language(self, language):
        language = language.replace("-", "_")
        self.language = language
        self.language_map = _load(language)
        if self.language_map is None:
            available = sorted(
                x[:-5] for x in os.listdir(LOCALE_DIR) if x.endswith(".json")
            )
            logging.warning(
                f"Language file for {language} does not exist. Using {FALLBACK_LANGUAGE} instead."
            )
            logging.warning(f"Available languages: {', '.join(available)}")
            self.language_map = dict(self.fallback_map)

    def __call__(self, key):
        """Look up `key`, falling back to English and then the source language.

        An empty value means "not translated yet" - the placeholder the sync
        script writes - so it falls through rather than rendering as blank text.
        """
        for table in (self.language_map, self.fallback_map, self.source_map):
            if table.get(key):
                return table[key]
        logging.debug(f"No translation for {key!r} in {self.language}")
        return key
