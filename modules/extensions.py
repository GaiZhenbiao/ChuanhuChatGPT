from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from html import escape

import gradio as gr

from . import plugin_callbacks
from . import shared
from .presets import i18n


EXTENSIONS_DIR = Path(shared.chuanhu_path) / "extensions"


@dataclass
class Extension:
    id: str
    path: Path
    name: str
    version: str = ""
    enabled: bool = True
    priority: int = 100
    metadata: dict = field(default_factory=dict)
    loaded_scripts: list[str] = field(default_factory=list)
    error: str | None = None


_loaded_extensions: list[Extension] = []
_loaded = False
_configured_disabled_extensions: list[str] = []


def extensions_dir() -> Path:
    EXTENSIONS_DIR.mkdir(exist_ok=True)
    return EXTENSIONS_DIR


def get_loaded_extensions() -> list[Extension]:
    return list(_loaded_extensions)


def _read_metadata(path: Path) -> dict:
    metadata_path = path / "metadata.json"
    if not metadata_path.exists():
        return {}
    with metadata_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extension_from_path(path: Path, disabled_extensions: set[str]) -> Extension:
    metadata = _read_metadata(path)
    extension_id = metadata.get("id") or path.name
    enabled = bool(metadata.get("enabled", True)) and extension_id not in disabled_extensions
    return Extension(
        id=extension_id,
        path=path,
        name=metadata.get("name") or extension_id,
        version=metadata.get("version", ""),
        enabled=enabled,
        priority=int(metadata.get("priority", 100)),
        metadata=metadata,
    )


def discover_extensions(disabled_extensions: list[str] | None = None) -> list[Extension]:
    disabled = set(disabled_extensions or [])
    root = extensions_dir()
    extensions = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir() and not child.name.startswith("."):
            if not (child / "metadata.json").exists() and not _script_paths(Extension(id=child.name, path=child, name=child.name)):
                continue
            try:
                extensions.append(_extension_from_path(child, disabled))
            except Exception as exc:
                extension = Extension(id=child.name, path=child, name=child.name, enabled=False)
                extension.error = i18n("读取 metadata.json 失败：") + str(exc)
                extensions.append(extension)
    return sorted(extensions, key=lambda item: (item.priority, item.id.lower()))


def _script_paths(extension: Extension) -> list[Path]:
    paths = []
    root_script = extension.path / "extension.py"
    if root_script.exists():
        paths.append(root_script)
    scripts_dir = extension.path / "scripts"
    if scripts_dir.exists():
        paths.extend(sorted(scripts_dir.glob("*.py"), key=lambda p: p.name.lower()))
    return paths


def _load_script(extension: Extension, script_path: Path):
    module_name = f"chuanhu_extension_{extension.id}_{script_path.stem}".replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(i18n("无法加载插件脚本：") + str(script_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    previous_path = list(sys.path)
    sys.path.insert(0, str(extension.path))
    try:
        with plugin_callbacks.extension_context(extension.id):
            spec.loader.exec_module(module)
    finally:
        sys.path = previous_path
    extension.loaded_scripts.append(str(script_path.relative_to(extension.path)))


def load_extensions(disabled_extensions: list[str] | None = None, force: bool = False):
    global _loaded, _loaded_extensions, _configured_disabled_extensions
    if _loaded and not force:
        return get_loaded_extensions()
    if disabled_extensions is not None:
        _configured_disabled_extensions = list(disabled_extensions)
    else:
        disabled_extensions = _configured_disabled_extensions
    plugin_callbacks.clear_callbacks()
    _loaded_extensions = discover_extensions(disabled_extensions)
    for extension in _loaded_extensions:
        plugin_callbacks.set_extension_enabled(extension.id, extension.enabled and not extension.error)
    for extension in _loaded_extensions:
        if not extension.enabled or extension.error:
            continue
        for script_path in _script_paths(extension):
            try:
                _load_script(extension, script_path)
            except Exception as exc:
                traceback.print_exc()
                extension.error = f"{script_path.name}: {exc}"
                plugin_callbacks.set_extension_enabled(extension.id, False)
                plugin_callbacks.register_error(extension.id, extension.error)
                break
    _loaded = True
    logging.info(i18n("已加载 {count} 个插件").format(count=len([x for x in _loaded_extensions if x.enabled and not x.error])))
    return get_loaded_extensions()


def _collect_files(extension: Extension, relative_dirs: list[str], suffixes: tuple[str, ...]) -> list[Path]:
    files = []
    for relative_dir in relative_dirs:
        folder = extension.path / relative_dir
        if folder.exists():
            files.extend(path for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()) if path.suffix.lower() in suffixes)
    return files


def javascript_files() -> list[Path]:
    load_extensions()
    files = []
    for extension in _loaded_extensions:
        if extension.enabled and not extension.error:
            files.extend(_collect_files(extension, ["javascript"], (".js", ".mjs")))
    return files


def stylesheet_files() -> list[Path]:
    load_extensions()
    files = []
    for extension in _loaded_extensions:
        if extension.enabled and not extension.error:
            style = extension.path / "style.css"
            if style.exists():
                files.append(style)
            files.extend(_collect_files(extension, ["stylesheet"], (".css",)))
    return files


def _metadata_text(extension: Extension, key: str, fallback: str = ""):
    value = extension.metadata.get(key) or fallback
    translations = extension.metadata.get(f"{key}_i18n")
    if not isinstance(translations, dict):
        return value
    language = getattr(i18n, "language", "zh_CN") or "zh_CN"
    candidates = [language, language.split("_", 1)[0], "en_US", "en"]
    for candidate in candidates:
        translated = translations.get(candidate)
        if translated:
            return translated
    return value


def _extension_title(extension_id: str):
    extension = _find_extension(extension_id)
    if extension is None:
        return extension_id
    return _metadata_text(extension, "name", extension.name)


def _extension_description(extension: Extension):
    return _metadata_text(extension, "description", "")


def _render_callback_tabs(kind: str):
    for record in plugin_callbacks.iter_callbacks(kind):
        title = _extension_title(record.extension_id)
        tab_classes = "extension-generated-tab"
        if kind == "extension_settings":
            tab_classes += " extension-settings-generated-tab"
        with gr.Tab(label=title, elem_classes=tab_classes):
            try:
                record.callback()
            except Exception as exc:
                message = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                plugin_callbacks.register_error(record.extension_id, f"{record.name}: {message}")
                gr.Markdown(i18n("加载插件界面失败：") + f"`{message}`")


def render_extension_tabs():
    _render_callback_tabs("extension_controls")


def _extension_status(extension: Extension):
    if extension.error:
        return i18n("错误")
    if not extension.enabled:
        return i18n("已禁用")
    return i18n("已启用")


def _is_git_extension(extension: Extension):
    return (extension.path / ".git").exists()


def _git_extension_has_updates(extension: Extension):
    if not _is_git_extension(extension):
        return False
    try:
        subprocess.run(
            ["git", "-C", str(extension.path), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="ignore",
        )
        result = subprocess.run(
            ["git", "-C", str(extension.path), "rev-list", "--count", "HEAD..@{u}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="ignore",
        )
        return int((result.stdout or "0").strip() or "0") > 0
    except Exception:
        return False


def _safe_extension_name(source: str):
    name = source.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    return name or "new_extension"


def _find_extension(extension_id: str):
    for extension in _loaded_extensions:
        if extension.id == extension_id:
            return extension
    return None


def _set_extension_enabled(extension_id: str, enabled: bool):
    extension = _find_extension(extension_id)
    if extension is None:
        return i18n("未找到插件：") + extension_id
    extension.enabled = bool(enabled)
    if enabled and not extension.loaded_scripts and not extension.error:
        for script_path in _script_paths(extension):
            try:
                _load_script(extension, script_path)
            except Exception as exc:
                traceback.print_exc()
                extension.error = f"{script_path.name}: {exc}"
                plugin_callbacks.register_error(extension.id, extension.error)
                break
    plugin_callbacks.set_extension_enabled(extension.id, extension.enabled and not extension.error)
    if extension.error:
        return i18n("插件启用失败：") + extension.error
    if extension.enabled:
        return i18n("插件已启用，前端静态资源变化需要刷新页面后生效。")
    return i18n("插件已禁用，已注册的 Python 钩子会立即停止执行。")


def install_extension(source: str):
    source = (source or "").strip()
    if not source:
        return i18n("请输入 Git URL 或本地插件目录。")
    target_name = _safe_extension_name(source)
    target_path = extensions_dir() / target_name
    if target_path.exists():
        return i18n("目标插件目录已存在：") + str(target_path)
    try:
        if source.startswith(("http://", "https://", "git@")) or source.endswith(".git"):
            subprocess.run(
                ["git", "clone", "--depth", "1", source, str(target_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="ignore",
            )
        else:
            source_path = Path(source).expanduser().resolve()
            if not source_path.is_dir():
                return i18n("本地插件目录不存在：") + str(source_path)
            shutil.copytree(source_path, target_path)
        load_extensions(force=True)
        return i18n("插件已安装，请刷新页面或重启应用以加载新的前端资源。")
    except subprocess.CalledProcessError as exc:
        return i18n("插件安装失败：") + (exc.stderr or str(exc))
    except Exception as exc:
        return i18n("插件安装失败：") + str(exc)


def update_extension(extension_id: str):
    extension = _find_extension(extension_id)
    if extension is None:
        return i18n("未找到插件：") + extension_id
    if not _is_git_extension(extension):
        return i18n("该插件不是 Git 仓库，无法自动更新。")
    try:
        subprocess.run(
            ["git", "-C", str(extension.path), "pull", "--ff-only"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="ignore",
        )
        load_extensions(force=True)
        return i18n("插件已更新，请刷新页面或重启应用以加载新的前端资源。")
    except subprocess.CalledProcessError as exc:
        return i18n("插件更新失败：") + (exc.stderr or str(exc))
    except Exception as exc:
        return i18n("插件更新失败：") + str(exc)


def update_all_extensions():
    messages = []
    for extension in get_loaded_extensions():
        if _is_git_extension(extension):
            messages.append(f"{extension.name}: {update_extension(extension.id)}")
    if not messages:
        return i18n("没有可自动更新的 Git 插件。")
    return "\n\n".join(messages)


def refresh_extension_list():
    load_extensions(force=True)
    return i18n("插件列表已刷新。")


def extension_manager_html():
    extensions = get_loaded_extensions()
    if not extensions:
        return f'<div class="extension-muted">{escape(i18n("未发现插件。"))}</div>'

    rows = []
    for extension in extensions:
        checked = "checked" if extension.enabled and not extension.error else ""
        disabled = "disabled" if extension.error else ""
        description = _extension_description(extension)
        version = extension.version or "-"
        status = _extension_status(extension)
        update_link = ""
        if _git_extension_has_updates(extension):
            update_link = (
                f'<button type="button" class="extension-inline-update" '
                f'data-extension-action="update" data-extension-id="{escape(extension.id)}">'
                f'{escape(i18n("更新"))}</button>'
            )
        rows.append(
            f"""
            <div class="extension-list-row" data-extension-id="{escape(extension.id)}">
              <div class="extension-info">
                <div class="extension-title-line">
                  <span class="extension-title">{escape(_extension_title(extension.id))}</span>
                  {update_link}
                </div>
                <div class="extension-desc">{escape(description)}</div>
                <div class="extension-meta">{escape(version)} · {escape(status)}</div>
                {f'<div class="extension-error">{escape(i18n("错误：") + extension.error)}</div>' if extension.error else ''}
              </div>
              <label class="extension-native-switch" title="{escape(status)}">
                <input class="extension-native-input" type="checkbox" data-extension-action="toggle" data-extension-id="{escape(extension.id)}" {checked} {disabled}>
                <span class="extension-native-slider"></span>
              </label>
            </div>
            """
        )
    return "\n".join(rows)


def handle_extension_action(action_json: str):
    try:
        action = json.loads(action_json or "{}")
    except Exception:
        return i18n("插件操作参数无效。"), extension_manager_html()

    extension_id = action.get("id", "")
    action_type = action.get("action", "")
    if action_type == "toggle":
        message = _set_extension_enabled(extension_id, bool(action.get("enabled", False)))
    elif action_type == "update":
        message = update_extension(extension_id)
    else:
        message = i18n("未知插件操作。")
    return message, extension_manager_html()


def install_extension_from_ui(source: str):
    return install_extension(source), extension_manager_html()


def refresh_extension_list_from_ui():
    return refresh_extension_list(), extension_manager_html()


def update_all_extensions_from_ui():
    return update_all_extensions(), extension_manager_html()


def render_extension_manager():
    status_box = gr.Markdown("", elem_classes="extension-status")
    action_payload = gr.Textbox(value="", visible=False, elem_id="extension-action-payload")
    action_btn = gr.Button(value="", visible=False, elem_id="extension-action-btn")

    source = gr.Textbox(
        label=i18n("Git URL 或本地插件目录"),
        placeholder="https://github.com/user/chuanhu-extension-example.git",
        lines=1,
        elem_classes="no-container extension-install-source",
    )
    install_btn = gr.Button(i18n("安装"), variant="primary", elem_classes="extension-action-button extension-install-button")

    gr.Markdown(i18n("已安装插件"), elem_classes="extension-section-label extension-installed-title")
    list_html = gr.HTML(extension_manager_html(), elem_id="extension-manager-list")

    install_btn.click(install_extension_from_ui, inputs=[source], outputs=[status_box, list_html], show_progress=True)
    action_btn.click(handle_extension_action, inputs=[action_payload], outputs=[status_box, list_html], show_progress=True)

    errors = plugin_callbacks.get_errors()
    if errors:
        gr.Markdown(i18n("插件错误"), elem_classes="extension-section-label")
        for item in errors:
            gr.Markdown(f"- `{item['extension']}`：{item['message']}", elem_classes="extension-error")


def render_extension_settings():
    labels = [
        _extension_title(record.extension_id)
        for record in plugin_callbacks.iter_callbacks("extension_settings")
    ]
    if labels:
        gr.HTML(
            '<span id="extension-settings-tab-labels" style="display:none" '
            f'data-labels="{escape(json.dumps(labels, ensure_ascii=False))}"></span>'
        )
    _render_callback_tabs("extension_settings")
