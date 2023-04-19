import os
import locale
import commentjson as json

class I18nAuto:
    def __init__(self):
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}
        lang_config = config.get("language", "auto")
        language = os.environ.get("LANGUAGE", lang_config)
        if language == "auto":
            language = locale.getdefaultlocale()[0] # get the language code of the system (ex. zh_CN)
        self.language_map = {}
        self.file_is_exists = os.path.isfile(f"./locale/{language}.json")
        if self.file_is_exists:
            with open(f"./locale/{language}.json", "r", encoding="utf-8") as f:
                self.language_map.update(json.load(f))

    def __call__(self, key):
        if self.file_is_exists and key in self.language_map:
            return self.language_map[key]
        else:
            return key
