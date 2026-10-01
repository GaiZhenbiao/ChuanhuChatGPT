from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import logging
import traceback
from typing import Any, Callable

import gradio as gr


Callback = Callable[..., Any]


@dataclass
class CallbackRecord:
    extension_id: str
    name: str
    callback: Callback


_callback_map: dict[str, list[CallbackRecord]] = {
    "extension_controls": [],
    "extension_settings": [],
    "before_chat": [],
    "after_prepare": [],
    "before_model_call": [],
    "after_chat": [],
    "chat_error": [],
    "after_history_saved": [],
    "app_ready": [],
}

_current_extension_id = ContextVar("chuanhu_extension_id", default="core")
_errors: list[dict[str, str]] = []
_extension_enabled: dict[str, bool] = {}


@contextmanager
def extension_context(extension_id: str):
    token = _current_extension_id.set(extension_id)
    try:
        yield
    finally:
        _current_extension_id.reset(token)


def unregister_extension(extension_id: str):
    """Roll back all callbacks owned by an extension (including partial imports)."""
    for kind, records in _callback_map.items():
        _callback_map[kind] = [r for r in records if r.extension_id != extension_id]
    _extension_enabled.pop(extension_id, None)


def clear_callbacks():
    for records in _callback_map.values():
        records.clear()
    _errors.clear()
    _extension_enabled.clear()


def register_error(extension_id: str, message: str):
    logging.error("[extension:%s] %s", extension_id, message)
    _errors.append({"extension": extension_id, "message": message})
    del _errors[:-100]


def get_errors():
    return list(_errors)


def set_extension_enabled(extension_id: str, enabled: bool):
    _extension_enabled[extension_id] = bool(enabled)


def is_extension_enabled(extension_id: str):
    return _extension_enabled.get(extension_id, True)


def _register(kind: str, callback: Callback):
    if kind not in _callback_map:
        raise ValueError(f"Unknown plugin callback kind: {kind}")
    record = CallbackRecord(
        extension_id=_current_extension_id.get(),
        name=getattr(callback, "__name__", repr(callback)),
        callback=callback,
    )
    _callback_map[kind].append(record)
    # Gradio retains event functions after a plugin is disabled. Guard direct
    # invocations as well as lifecycle dispatch so those events stop too.
    return callback


def guarded_callback(callback: Callback):
    """Wrap a Gradio event during registration inside extension_context."""
    from functools import wraps
    from inspect import isgeneratorfunction
    extension_id = _current_extension_id.get()

    if isgeneratorfunction(callback):
        @wraps(callback)
        def guarded_generator(*args, **kwargs):
            if not is_extension_enabled(extension_id):
                raise gr.Error("Plugin is disabled; restart after enabling it.")
            iterator = callback(*args, **kwargs)
            try:
                for result in iterator:
                    if not is_extension_enabled(extension_id):
                        raise gr.Error("Plugin was disabled; the task stopped.")
                    yield result
            finally:
                iterator.close()
        return guarded_generator

    @wraps(callback)
    def guarded(*args, **kwargs):
        if not is_extension_enabled(extension_id):
            raise gr.Error("Plugin is disabled; restart after enabling it.")
        return callback(*args, **kwargs)
    return guarded


def on_extension_controls(callback: Callback):
    return _register("extension_controls", callback)


def on_app_ready(callback: Callback):
    """Bind events to core Gradio components once UI construction is complete."""
    return _register("app_ready", callback)


def on_toolbox_tab(callback: Callback):
    return on_extension_controls(callback)


def on_extension_settings(callback: Callback):
    return _register("extension_settings", callback)


def on_settings_tab(callback: Callback):
    return on_extension_settings(callback)


def on_before_chat(callback: Callback):
    return _register("before_chat", callback)


def on_after_prepare(callback: Callback):
    return _register("after_prepare", callback)


def on_before_model_call(callback: Callback):
    return _register("before_model_call", callback)


def on_after_chat(callback: Callback):
    return _register("after_chat", callback)


def on_chat_error(callback: Callback):
    return _register("chat_error", callback)


def on_after_history_saved(callback: Callback):
    return _register("after_history_saved", callback)


def iter_callbacks(kind: str):
    return [
        record
        for record in _callback_map.get(kind, [])
        if is_extension_enabled(record.extension_id)
    ]


def callback_counts():
    return {kind: len(records) for kind, records in _callback_map.items()}


def invoke(kind: str, *args, **kwargs):
    results = []
    for record in iter_callbacks(kind):
        try:
            with extension_context(record.extension_id):
                results.append(record.callback(*args, **kwargs))
        except Exception as exc:
            message = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            register_error(record.extension_id, f"{record.name}: {message}")
            logging.debug("Plugin callback traceback", exc_info=True)
    return results


def render_callbacks(kind: str, empty_text: str, separator: bool = False):
    from modules.presets import i18n

    rendered = False
    for record in iter_callbacks(kind):
        try:
            with extension_context(record.extension_id):
                record.callback()
            rendered = True
            if separator:
                gr.Markdown("---")
        except Exception as exc:
            message = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            register_error(record.extension_id, f"{record.name}: {message}")
            with gr.Accordion(f"{record.extension_id}", open=False):
                gr.Markdown(i18n("加载插件界面失败：") + f"`{message}`")
            if separator:
                gr.Markdown("---")
    if not rendered:
        gr.Markdown(empty_text)
