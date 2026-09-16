"""Keep the locale files in sync with the identifiers used in the code.

Strings live in the locale files, never in the code: a call site only names a
string (``i18n("ui.chat.model_select")``), and ``locale/zh_CN.json`` holds the
source wording for every identifier. This script reports identifiers that are
used but not yet translated, and identifiers a locale still carries that the
code no longer references.

    python locale/extract_locale.py           # sync keys only
    python locale/extract_locale.py --auto    # also machine-translate the gaps
"""
import asyncio
import logging
import os
import re
import sys

import aiohttp
import commentjson as json

asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

SOURCE_LANGUAGE = "zh_CN"
LOCALE_DIR = "locale"
UNTRANSLATED = ""
NOT_USED = "(🔴NOT USED)"
REVIEW_NEEDED = "(🟡REVIEW NEEDED)"

# any quoted string that looks like a dotted identifier
IDENTIFIER = re.compile(r"""["']([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)["']""", re.IGNORECASE)


def flatten(tree, prefix=""):
    flat = {}
    for key, value in tree.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten(value, dotted))
        else:
            flat[dotted] = value
    return flat


def nest(flat):
    root = {}
    for key in sorted(flat):
        parts = key.split(".")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = flat[key]
    return root


def load_locale(language):
    path = os.path.join(LOCALE_DIR, f"{language}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return flatten(json.load(f))
    except FileNotFoundError:
        return {}


def save_locale(language, strings):
    path = os.path.join(LOCALE_DIR, f"{language}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nest(strings), f, ensure_ascii=False, indent=4, sort_keys=True)


def identifiers_in_code(known):
    """Identifiers referenced from the code, whether through i18n() or a table.

    Model metadata names its strings indirectly (``"description": "model.gpt4.description"``),
    so any quoted identifier that the source language defines counts as in use.
    """
    used = set()
    for dirpath, dirnames, filenames in os.walk("."):
        if ".git" in dirpath or dirpath.startswith("./" + LOCALE_DIR):
            continue
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            with open(os.path.join(dirpath, filename), "r", encoding="utf-8") as f:
                contents = f.read()
            for match in IDENTIFIER.findall(contents):
                if match in known:
                    used.add(match)
            for match in re.findall(r'i18n\s*\(\s*["\']([^"\']+)["\']\s*\)', contents):
                used.add(match)
    return used


def sort_strings(strings):
    """Untranslated first, then unused, then the rest - so gaps are easy to find."""
    def rank(item):
        value = item[1]
        if value == UNTRANSLATED:
            return 0
        if NOT_USED in value:
            return 1
        return 2
    return dict(sorted(strings.items(), key=lambda kv: (rank(kv), kv[0])))


async def auto_translate(session, url, headers, text, language):
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    f"You are a translation program;\n"
                    f"Your job is to translate user input into {language};\n"
                    f"The content you are translating is a string in an app;\n"
                    f"Keep any {{placeholder}} and markdown syntax exactly as-is;\n"
                    f"Do not explain emoji; if the input is only an emoji, return it unchanged;\n"
                    f"Please ensure that the translation is concise and easy to understand."
                ),
            },
            {"role": "user", "content": text},
        ],
    }
    async with session.post(url, headers=headers, json=payload) as response:
        data = await response.json()
        return data["choices"][0]["message"]["content"]


async def main(auto=False):
    source = load_locale(SOURCE_LANGUAGE)
    if not source:
        logging.error(f"{SOURCE_LANGUAGE}.json is missing or empty; nothing to sync.")
        return

    used = identifiers_in_code(set(source))
    undefined = sorted(i for i in used if i not in source)
    if undefined:
        print(f"⚠️  used in code but not defined in {SOURCE_LANGUAGE}.json:")
        for identifier in undefined:
            print(f"      {identifier}")

    api_key = url = None
    if auto:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        api_key = config["openai_api_key"]
        base = config.get("openai_api_base", "https://api.openai.com")
        url = base.rstrip("/") + "/v1/chat/completions"

    for filename in sorted(os.listdir(LOCALE_DIR)):
        if not filename.endswith(".json"):
            continue
        language = filename[:-5]
        if language == SOURCE_LANGUAGE:
            continue
        try:
            strings = load_locale(language)
        except json.JSONLibraryException:
            logging.error(f"Error decoding {filename}")
            continue

        new_keys = [i for i in sorted(used) if i not in strings]
        for identifier in new_keys:
            strings[identifier] = UNTRANSLATED
        stale = [i for i in strings if i not in used and i in source]
        for identifier in stale:
            if NOT_USED not in strings[identifier]:
                strings[identifier] = NOT_USED + strings[identifier]
        print(f"{language}: {len(new_keys)} new, {len(stale)} no longer used")

        if auto and new_keys:
            headers = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {api_key}"}
            async with aiohttp.ClientSession() as session:
                results = await asyncio.gather(*[
                    auto_translate(session, url, headers, source[i], language)
                    for i in new_keys
                ])
            for identifier, result in zip(new_keys, results):
                strings[identifier] = REVIEW_NEEDED + result
            print(f"{language}: {len(new_keys)} auto-translated, review needed")

        save_locale(language, sort_strings(strings))


if __name__ == "__main__":
    asyncio.run(main(auto=len(sys.argv) > 1 and sys.argv[1] == "--auto"))
