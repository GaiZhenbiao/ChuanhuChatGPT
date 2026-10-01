from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import hashlib
from types import ModuleType
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import re
import tempfile
from threading import RLock
from functools import wraps
from html import escape

import gradio as gr

from . import plugin_callbacks
from . import shared
from .presets import i18n


EXTENSIONS_DIR = Path(shared.chuanhu_path) / "extensions"
STATE_FILE = Path(shared.chuanhu_path) / "extension_state.json"
_lock = RLock()


def synchronized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _lock:
            return function(*args, **kwargs)
    return wrapped


def _read_state():
    if not STATE_FILE.exists():
        return {}
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Unsupported extension_state.json format")
    values = data.get("enabled")
    if not isinstance(values, dict) or any(type(v) is not bool for v in values.values()):
        raise ValueError("Invalid extension enabled state")
    return values


def _save_enabled(extension_id, enabled):
    values = _read_state()
    values[extension_id] = enabled
    # Separate state avoids rewriting config.json (which may contain secrets
    # and comments). Replace atomically; failed writes leave runtime unchanged.
    fd, temporary = tempfile.mkstemp(prefix=".extension-state-", dir=STATE_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump({"version": 1, "enabled": values}, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, STATE_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


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
    module_names: list[str] = field(default_factory=list)
    restart_required: bool = False


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
        metadata = json.load(f)
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    extension_id = metadata.get("id", path.name)
    if not isinstance(extension_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", extension_id):
        raise ValueError("id must be 1–64 ASCII letters, digits, underscores or hyphens; start with a letter")
    for key in ("name", "version", "description", "author"):
        if key in metadata and not isinstance(metadata[key], str):
            raise ValueError(f"{key} must be a string")
    if "enabled" in metadata and type(metadata["enabled"]) is not bool:
        raise ValueError("enabled must be a boolean")
    if "priority" in metadata and type(metadata["priority"]) is not int:
        raise ValueError("priority must be an integer")
    for key in ("name_i18n", "description_i18n"):
        if key in metadata and (not isinstance(metadata[key], dict) or
                                any(not isinstance(v, str) for v in metadata[key].values())):
            raise ValueError(f"{key} must map languages to strings")
    return metadata


def _extension_from_path(path: Path, disabled_extensions: set[str]) -> Extension:
    metadata = _read_metadata(path)
    extension_id = metadata.get("id") or path.name
    if not isinstance(extension_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", extension_id) or extension_id == "core":
        raise ValueError("Invalid or reserved extension id")
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
    try:
        overrides = _read_state()
    except (OSError, ValueError) as exc:
        # Fail closed instead of re-enabling plugins when state is corrupted.
        logging.error("Cannot read extension state: %s", exc)
        overrides = None
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir() and not child.is_symlink() and not child.name.startswith("."):
            if not (child / "metadata.json").exists() and not _script_paths(Extension(id=child.name, path=child, name=child.name)):
                continue
            try:
                extension = _extension_from_path(child, disabled)
                if overrides is None:
                    extension.enabled = False
                    extension.error = "Cannot read extension_state.json; repair it before loading plugins"
                else:
                    extension.enabled = overrides.get(extension.id, extension.enabled)
                extensions.append(extension)
            except Exception as exc:
                extension = Extension(id=child.name, path=child, name=child.name, enabled=False)
                extension.error = i18n("ui.settings.extensions.metadata_error") + str(exc)
                extensions.append(extension)
    groups = {}
    for extension in extensions:
        groups.setdefault(extension.id, []).append(extension)
    for extension_id, matches in groups.items():
        if len(matches) > 1:
            for extension in matches:
                extension.enabled = False
                extension.error = f"Duplicate plugin id: {extension_id}"
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
    namespace = "chuanhu_extension_" + hashlib.sha256(str(extension.path.resolve()).encode()).hexdigest()
    if namespace not in sys.modules:
        package = ModuleType(namespace)
        package.__path__ = [str(extension.path)]
        package.__package__ = namespace
        sys.modules[namespace] = package
        extension.module_names.append(namespace)
    if script_path.parent.name == "scripts":
        scripts_namespace = namespace + ".scripts"
        if scripts_namespace not in sys.modules:
            package = ModuleType(scripts_namespace)
            package.__path__ = [str(script_path.parent)]
            package.__package__ = scripts_namespace
            sys.modules[scripts_namespace] = package
            extension.module_names.append(scripts_namespace)
        module_name = scripts_namespace + "." + script_path.stem
    else:
        module_name = namespace + "." + script_path.stem
    # Legacy bare imports remain supported when unambiguous. Never silently
    # bind a plugin's helper to another plugin/library's cached module.
    for local in extension.path.iterdir():
        name = local.stem if local.suffix == ".py" else local.name
        if local.suffix != ".py" and not (local / "__init__.py").is_file():
            continue
        cached = sys.modules.get(name)
        filename = getattr(cached, "__file__", None)
        if cached is not None and (not filename or extension.path.resolve() not in Path(filename).resolve().parents):
            raise ImportError(f"Local module {name!r} conflicts with an existing module; use package-relative imports")
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(i18n("ui.settings.extensions.script_error") + str(script_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    extension.module_names.append(module_name)
    previous_path = list(sys.path)
    sys.path.insert(0, str(extension.path))
    try:
        with plugin_callbacks.extension_context(extension.id):
            # Entry scripts must reload their current source (even within one
            # filesystem timestamp tick) and must not dirty installed Git repos
            # with an untracked entry-script bytecode cache.
            exec(compile(script_path.read_bytes(), str(script_path), "exec"), module.__dict__)
    finally:
        sys.path = previous_path
        # Capture imported helpers even when an entry script fails halfway.
        for name, imported in list(sys.modules.items()):
            filename = getattr(imported, "__file__", None)
            if (name.startswith(namespace + ".") or
                    (filename and extension.path.resolve() in Path(filename).resolve().parents)):
                if name not in extension.module_names:
                    extension.module_names.append(name)
    extension.loaded_scripts.append(str(script_path.relative_to(extension.path)))


@synchronized
def load_extensions(disabled_extensions: list[str] | None = None, force: bool = False):
    global _loaded, _loaded_extensions, _configured_disabled_extensions
    if _loaded and not force:
        return get_loaded_extensions()
    if disabled_extensions is not None:
        _configured_disabled_extensions = list(disabled_extensions)
    else:
        disabled_extensions = _configured_disabled_extensions
    for previous in _loaded_extensions:
        _unload_extension(previous)
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
                _unload_extension(extension)
                plugin_callbacks.set_extension_enabled(extension.id, False)
                plugin_callbacks.register_error(extension.id, extension.error)
                break
    _loaded = True
    logging.info(i18n("ui.settings.extensions.loaded").format(count=len([x for x in _loaded_extensions if x.enabled and not x.error])))
    return get_loaded_extensions()


def _unload_extension(extension):
    plugin_callbacks.unregister_extension(extension.id)
    for name in extension.module_names:
        sys.modules.pop(name, None)
    extension.module_names.clear()
    extension.loaded_scripts.clear()


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
                with plugin_callbacks.extension_context(record.extension_id):
                    record.callback()
            except Exception as exc:
                message = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                plugin_callbacks.register_error(record.extension_id, f"{record.name}: {message}")
                gr.Markdown(i18n("ui.settings.extensions.ui_error") + f"`{message}`")


def render_extension_tabs():
    _render_callback_tabs("extension_controls")


def _extension_status(extension: Extension):
    if extension.error:
        return i18n("ui.settings.extensions.error")
    if extension.restart_required:
        return i18n("ui.settings.extensions.restart_required")
    if not extension.enabled:
        return i18n("ui.settings.extensions.disabled")
    return i18n("ui.settings.extensions.enabled")


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
            timeout=15,
        )
        result = subprocess.run(
            ["git", "-C", str(extension.path), "rev-list", "--count", "HEAD..@{u}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="ignore",
            timeout=15,
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


@synchronized
def _set_extension_enabled(extension_id: str, enabled: bool):
    extension = _find_extension(extension_id)
    if extension is None:
        return i18n("ui.settings.extensions.not_found") + extension_id
    if extension.error and enabled:
        return i18n("ui.settings.extensions.enable_error") + extension.error
    try:
        _save_enabled(extension_id, bool(enabled))
    except (OSError, ValueError) as exc:
        return i18n("ui.settings.extensions.save_error") + str(exc)
    disabled = set(_configured_disabled_extensions)
    disabled.discard(extension_id) if enabled else disabled.add(extension_id)
    _configured_disabled_extensions[:] = sorted(disabled)
    extension.enabled = bool(enabled)
    if enabled and not extension.loaded_scripts and not extension.error and not extension.restart_required:
        for script_path in _script_paths(extension):
            try:
                _load_script(extension, script_path)
            except Exception as exc:
                traceback.print_exc()
                extension.error = f"{script_path.name}: {exc}"
                _unload_extension(extension)
                plugin_callbacks.register_error(extension.id, extension.error)
                break
    plugin_callbacks.set_extension_enabled(extension.id, extension.enabled and not extension.error and not extension.restart_required)
    if extension.error:
        return i18n("ui.settings.extensions.enable_error") + extension.error
    if extension.enabled:
        return i18n("ui.settings.extensions.enabled_saved")
    return i18n("ui.settings.extensions.disabled_saved")


@synchronized
def install_extension(source: str):
    source = (source or "").strip()
    if not source:
        return i18n("ui.settings.extensions.source_required")
    target_name = _safe_extension_name(source)
    if target_name.startswith("."):
        return i18n("ui.settings.extensions.invalid_directory")
    target_path = extensions_dir() / target_name
    if target_path.exists():
        return i18n("ui.settings.extensions.directory_exists") + str(target_path)
    try:
        # Hidden staging prevents discovery of a partially copied installation.
        with tempfile.TemporaryDirectory(prefix=".install-", dir=extensions_dir()) as staging:
            candidate = Path(staging) / target_name
            if source.startswith(("http://", "https://", "git@")) or source.endswith(".git"):
                subprocess.run(
                    ["git", "clone", "--depth", "1", "--", source, str(candidate)],
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    encoding="utf-8", errors="replace", timeout=120,
                )
            else:
                source_path = Path(source).expanduser().resolve()
                if not source_path.is_dir():
                    raise ValueError("Local plugin directory does not exist")
                if source_path == extensions_dir().resolve() or source_path in target_path.resolve().parents:
                    raise ValueError("Cannot install a parent of the extension directory")
                shutil.copytree(source_path, candidate, symlinks=True)
            if any(p.is_symlink() for p in candidate.rglob("*")):
                raise ValueError("Plugin installation must not contain symlinks")
            extension = _extension_from_path(candidate, set())
            if not (candidate / "metadata.json").is_file():
                raise ValueError("Installed plugins must include metadata.json")
            if any(item.id == extension.id for item in discover_extensions()):
                raise ValueError("Duplicate plugin id: " + extension.id)
            # Installation is not permission to execute third-party Python.
            _save_enabled(extension.id, False)
            candidate.rename(target_path)
        refresh_extension_list()
        return i18n("ui.settings.extensions.installed_disabled")
    except subprocess.CalledProcessError:
        return i18n("ui.settings.extensions.install_git_error")
    except Exception as exc:
        return i18n("ui.settings.extensions.install_error") + str(exc)


@synchronized
def update_extension(extension_id: str):
    extension = _find_extension(extension_id)
    if extension is None:
        return i18n("ui.settings.extensions.not_found") + extension_id
    if not _is_git_extension(extension):
        return i18n("ui.settings.extensions.not_git")
    try:
        status = subprocess.run(
            ["git", "-C", str(extension.path), "status", "--porcelain"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        if status.stdout.strip():
            return i18n("ui.settings.extensions.dirty_update")
        subprocess.run(
            ["git", "-C", str(extension.path), "pull", "--ff-only"],
            check=True, capture_output=True, text=True, timeout=120,
        )
        # Existing Gradio components retain old function objects. Suspend hooks
        # and require restart instead of mixing two versions in one process.
        _unload_extension(extension)
        extension.restart_required = True
        plugin_callbacks.set_extension_enabled(extension.id, False)
        return i18n("ui.settings.extensions.updated")
    except subprocess.CalledProcessError:
        return i18n("ui.settings.extensions.update_git_error")
    except Exception as exc:
        return i18n("ui.settings.extensions.update_error") + str(exc)


def update_all_extensions():
    messages = []
    for extension in get_loaded_extensions():
        if _is_git_extension(extension):
            messages.append(f"{extension.name}: {update_extension(extension.id)}")
    if not messages:
        return i18n("ui.settings.extensions.no_updates")
    return "\n\n".join(messages)


@synchronized
def refresh_extension_list():
    global _loaded_extensions
    previous = {item.path: item for item in _loaded_extensions}
    found = discover_extensions(_configured_disabled_extensions)
    for item in found:
        old = previous.pop(item.path, None)
        if old and old.id == item.id and not item.error:
            item.loaded_scripts = old.loaded_scripts
            item.module_names = old.module_names
            item.error = old.error
            item.restart_required = old.restart_required
            if item.metadata != old.metadata:
                _unload_extension(old)
                item.loaded_scripts = []
                item.module_names = []
                item.restart_required = True
        else:
            if old:
                _unload_extension(old)
            item.restart_required = True
        plugin_callbacks.set_extension_enabled(item.id, item.enabled and not item.error and not item.restart_required)
    for removed in previous.values():
        _unload_extension(removed)
    _loaded_extensions = found
    return i18n("ui.settings.extensions.refreshed")


@synchronized
def check_extension_updates():
    messages = []
    for extension in get_loaded_extensions():
        if not _is_git_extension(extension):
            continue
        try:
            subprocess.run(
                ["git", "-C", str(extension.path), "fetch", "--prune"],
                check=True, capture_output=True, timeout=60,
            )
            messages.append(extension.id + ": " + i18n("ui.settings.extensions.update_available" if _git_extension_has_updates(extension) else "ui.settings.extensions.up_to_date"))
        except (subprocess.SubprocessError, OSError):
            messages.append(extension.id + ": " + i18n("ui.settings.extensions.check_error"))
    return "\n\n".join(messages) or i18n("ui.settings.extensions.no_git")


def check_extension_updates_from_ui():
    return check_extension_updates(), extension_manager_html()


def extension_manager_html():
    extensions = get_loaded_extensions()
    if not extensions:
        return f'<div class="extension-muted">{escape(i18n("ui.settings.extensions.empty"))}</div>'

    rows = []
    for extension in extensions:
        checked = "checked" if extension.enabled else ""
        disabled = ""
        description = _extension_description(extension)
        version = extension.version or "-"
        status = _extension_status(extension)
        update_link = ""
        if _git_extension_has_updates(extension):
            update_link = (
                f'<button type="button" class="extension-inline-update" '
                f'data-extension-action="update" data-extension-id="{escape(extension.id)}">'
                f'{escape(i18n("ui.settings.extensions.update"))}</button>'
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
                <div class="extension-meta">{escape(extension.id)} · {escape(version)} · {escape(status)}</div>
                {f'<div class="extension-error">{escape(i18n("ui.settings.extensions.error_prefix") + extension.error)}</div>' if extension.error else ''}
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
        return i18n("ui.settings.extensions.invalid_action"), extension_manager_html()

    if not isinstance(action, dict) or not isinstance(action.get("id", ""), str):
        return i18n("ui.settings.extensions.invalid_action"), extension_manager_html()
    extension_id = action.get("id", "")
    action_type = action.get("action", "")
    if action_type == "toggle":
        if type(action.get("enabled")) is not bool:
            return i18n("ui.settings.extensions.invalid_action"), extension_manager_html()
        message = _set_extension_enabled(extension_id, action["enabled"])
    elif action_type == "update":
        message = update_extension(extension_id)
    else:
        message = i18n("ui.settings.extensions.unknown_action")
    return message, extension_manager_html()


def install_extension_from_ui(source: str):
    return install_extension(source), extension_manager_html()


def refresh_extension_list_from_ui():
    return refresh_extension_list(), extension_manager_html()


def update_all_extensions_from_ui():
    return update_all_extensions(), extension_manager_html()


def render_extension_manager():
    gr.Markdown(i18n("ui.settings.extensions.trust_notice"))
    status_box = gr.Markdown("", elem_classes="extension-status")
    action_payload = gr.Textbox(value="", visible=False, elem_id="extension-action-payload")
    action_btn = gr.Button(value="", visible=False, elem_id="extension-action-btn")

    source = gr.Textbox(
        label=i18n("ui.settings.extensions.source"),
        placeholder="https://github.com/user/chuanhu-extension-example.git",
        lines=1,
        elem_classes="no-container extension-install-source",
    )
    install_btn = gr.Button(i18n("ui.settings.extensions.install"), variant="primary", elem_classes="extension-action-button extension-install-button")

    gr.Markdown(i18n("ui.settings.extensions.installed"), elem_classes="extension-section-label extension-installed-title")
    list_html = gr.HTML(extension_manager_html(), elem_id="extension-manager-list")

    install_btn.click(install_extension_from_ui, inputs=[source], outputs=[status_box, list_html], show_progress=True)
    action_btn.click(handle_extension_action, inputs=[action_payload], outputs=[status_box, list_html], show_progress=True)

    with gr.Row():
        refresh_btn = gr.Button(i18n("ui.settings.extensions.refresh"))
        check_btn = gr.Button(i18n("ui.settings.extensions.check_updates"))
        update_btn = gr.Button(i18n("ui.settings.extensions.update_all"))
    refresh_btn.click(refresh_extension_list_from_ui, outputs=[status_box, list_html])
    check_btn.click(check_extension_updates_from_ui, outputs=[status_box, list_html])
    update_btn.click(update_all_extensions_from_ui, outputs=[status_box, list_html])

    errors = plugin_callbacks.get_errors()
    if errors:
        gr.Markdown(i18n("ui.settings.extensions.errors"), elem_classes="extension-section-label")
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
