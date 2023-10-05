import os
import json
import re

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
        if "(NOT USED)" in value:
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
    locale_strs = get_locale_strings(locale_filename)

    # Add new keys
    for key in current_strs:
        if key not in locale_strs:
            locale_strs[key] = ""
    # Add (NOT USED) to invalid keys
    for key in locale_strs:
        if key not in current_strs:
            locale_strs[key] = "(NOT USED)" + locale_strs[key]

    locale_strs = sort_strings(locale_strs)

    with open(locale_filename, 'w', encoding='utf-8') as f:
        json.dump(locale_strs, f, ensure_ascii=False, indent=4)
