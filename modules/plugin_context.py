from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatContext:
    model: Any
    user_input: Any
    chatbot: list
    use_websearch: bool = False
    files: list | None = None
    reply_language: str = "中文"
    limited_context: bool = False
    fake_input: str = ""
    display_append: str = ""
    prepared_input: Any = None
    assistant_reply: str | None = None
    status_text: str = ""
    history_file_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatErrorContext:
    model: Any
    error: Exception
    chat_context: ChatContext | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
