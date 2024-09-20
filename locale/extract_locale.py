import asyncio
import logging
import os
import re
import sys

import aiohttp
import commentjson
import commentjson as json

asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

with open("config.json", "r", encoding="utf-8") as f:
    config = commentjson.load(f)
api_key = config["openai_api_key"]
url = config["openai_api_base"] + "/v1/chat/completions" if "openai_api_base" in config else "https://api.openai.com/v1/chat/completions"


def get_current_strings():
    pattern = r'i18n\s*\(\s*["\']([^"\']*(?:\)[^"\']*)?)["\']\s*\)'

    # Load the .py files
    contents = ""
    for dirpath, dirnames, filenames in os.walk("."):
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    contents += f.read()
    # Matching with regular expressions
    matches = re.findall(pattern, contents, re.DOTALL)
    data = {match.strip('()"'): '' for match in matches}
    fixed_data = {}     # fix some keys
    for key, value in data.items():
        if "](" in key and key.count("(") != key.count(")"):
                fixed_data[key+")"] = value
        else:
            fixed_data[key] = value

    return fixed_data


def get_locale_strings(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            locale_strs = json.load(f)
    except FileNotFoundError:
        locale_strs = {}
    return locale_strs


def sort_strings(existing_translations):
    # Sort the merged data
    sorted_translations = {}
    # Add entries with (NOT USED) in their values
    for key, value in sorted(existing_translations.items(), key=lambda x: x[0]):
        if "(🔴NOT USED)" in value:
            sorted_translations[key] = value
    # Add entries with empty values
    for key, value in sorted(existing_translations.items(), key=lambda x: x[0]):
        if value == "":
            sorted_translations[key] = value
    # Add the rest of the entries
    for key, value in sorted(existing_translations.items(), key=lambda x: x[0]):
        if value != "" and "(NOT USED)" not in value:
            sorted_translations[key] = value

    return sorted_translations


async def auto_translate(str, language):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "temperature": f"{0}",
    }
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {
                "role": "system",
                "content": f"You are a translation program;\nYour job is to translate user input into {language};\nThe content you are translating is a string in the App;\nDo not explain emoji;\nIf input is only a emoji, please simply return origin emoji;\nPlease ensure that the translation results are concise and easy to understand."
            },
            {"role": "user", "content": f"{str}"}
        ],
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            data = await response.json()
            return data["choices"][0]["message"]["content"]


async def main(auto=False):
    current_strs = get_current_strings()
    locale_files = []
    # 遍历locale目录下的所有json文件
    for dirpath, dirnames, filenames in os.walk("locale"):
        for filename in filenames:
            if filename.endswith(".json"):
                locale_files.append(os.path.join(dirpath, filename))


    for locale_filename in locale_files:
        if "zh_CN" in locale_filename:
            continue
        try:
            locale_strs = get_locale_strings(locale_filename)
        except json.decoder.JSONDecodeError:
            import traceback
            traceback.print_exc()
            logging.error(f"Error decoding {locale_filename}")
            continue

        # Add new keys
        new_keys = []
        for key in current_strs:
            if key not in locale_strs:
                new_keys.append(key)
                locale_strs[key] = ""
        print(f"{locale_filename[7:-5]}'s new str: {len(new_keys)}")
        # Add (NOT USED) to invalid keys
        for key in locale_strs:
            if key not in current_strs:
                locale_strs[key] = "(🔴NOT USED)" + locale_strs[key]
        print(f"{locale_filename[7:-5]}'s invalid str: {len(locale_strs) - len(current_strs)}")

        locale_strs = sort_strings(locale_strs)

        if auto:
            tasks = []
            non_translated_keys = []
            for key in locale_strs:
                if locale_strs[key] == "":
                    non_translated_keys.append(key)
                    tasks.append(auto_translate(key, locale_filename[7:-5]))
            results = await asyncio.gather(*tasks)
            for key, result in zip(non_translated_keys, results):
                locale_strs[key] = "(🟡REVIEW NEEDED)" + result
            print(f"{locale_filename[7:-5]}'s auto translated str: {len(non_translated_keys)}")

        with open(locale_filename, 'w', encoding='utf-8') as f:
            json.dump(locale_strs, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    auto = False
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        auto = True
    asyncio.run(main(auto))
