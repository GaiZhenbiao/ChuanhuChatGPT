from __future__ import annotations

import inspect

import gradio as gr
from gradio.components.chatbot import ChatbotData, FileMessage
from gradio.data_classes import FileData
from gradio_client import utils as client_utils

from modules.utils import convert_bot_before_marked, convert_user_before_marked


def postprocess(
    self,
    value: list[list[str | tuple[str] | tuple[str, str] | None] | tuple] | None,
) -> ChatbotData:
    """
    Parameters:
        value: expects a `list[list[str | None | tuple]]`, i.e. a list of lists. The inner list should have 2 elements: the user message and the response message. The individual messages can be (1) strings in valid Markdown, (2) tuples if sending files: (a filepath or URL to a file, [optional string alt text]) -- if the file is image/video/audio, it is displayed in the Chatbot, or (3) None, in which case the message is not displayed.
    Returns:
        an object of type ChatbotData
    """
    if value is None:
        return ChatbotData(root=[])
    processed_messages = []
    for message_pair in value:
        if not isinstance(message_pair, (tuple, list)):
            raise TypeError(
                f"Expected a list of lists or list of tuples. Received: {message_pair}"
            )
        if len(message_pair) != 2:
            raise TypeError(
                f"Expected a list of lists of length 2 or list of tuples of length 2. Received: {message_pair}"
            )
        processed_messages.append(
            [
                self._postprocess_chat_messages(message_pair[0], "user"),
                self._postprocess_chat_messages(message_pair[1], "bot"),
            ]
        )
    return ChatbotData(root=processed_messages)


def postprocess_chat_messages(
    self, chat_message: str | tuple | list | None, role: str
) -> str | FileMessage | None:
    if chat_message is None:
        return None
    elif isinstance(chat_message, (tuple, list)):
        filepath = str(chat_message[0])

        mime_type = client_utils.get_mimetype(filepath)
        return FileMessage(
            file=FileData(path=filepath, mime_type=mime_type),
            alt_text=chat_message[1] if len(chat_message) > 1 else None,
        )
    elif isinstance(chat_message, str):
        # chat_message = inspect.cleandoc(chat_message)
        if role == "bot":
            # chat_message = inspect.cleandoc(chat_message)
            chat_message = convert_bot_before_marked(chat_message)
        elif role == "user":
            chat_message = convert_user_before_marked(chat_message)
        return chat_message
    else:
        raise ValueError(f"Invalid message for Chatbot component: {chat_message}")


def init_with_class_name_as_elem_classes(original_func):
    def wrapper(self, *args, **kwargs):
        if "elem_classes" in kwargs and isinstance(kwargs["elem_classes"], str):
            kwargs["elem_classes"] = [kwargs["elem_classes"]]
        else:
            kwargs["elem_classes"] = []

        kwargs["elem_classes"].append("gradio-" + self.__class__.__name__.lower())

        if kwargs.get("multiselect", False):
            kwargs["elem_classes"].append("multiselect")

        res = original_func(self, *args, **kwargs)
        return res

    return wrapper


def patch_gradio():
    gr.components.Component.__init__ = init_with_class_name_as_elem_classes(
        gr.components.Component.__init__
    )

    gr.blocks.BlockContext.__init__ = init_with_class_name_as_elem_classes(
        gr.blocks.BlockContext.__init__
    )

    gr.Chatbot._postprocess_chat_messages = postprocess_chat_messages
    gr.Chatbot.postprocess = postprocess
