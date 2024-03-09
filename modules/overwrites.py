from __future__ import annotations
import logging

from typing import List, Tuple
from gradio_client import utils as client_utils
from gradio import utils
import inspect

from modules.presets import *
from modules.index_func import *


def postprocess(
        self,
        y: List[List[str | Tuple[str] | Tuple[str, str] | None] | Tuple],
    ) -> List[List[str | Dict | None]]:
        """
        Parameters:
            y: List of lists representing the message and response pairs. Each message and response should be a string, which may be in Markdown format.  It can also be a tuple whose first element is a string filepath or URL to an image/video/audio, and second (optional) element is the alt text, in which case the media file is displayed. It can also be None, in which case that message is not displayed.
        Returns:
            List of lists representing the message and response. Each message and response will be a string of HTML, or a dictionary with media information. Or None if the message is not to be displayed.
        """
        if y is None:
            return []
        processed_messages = []
        for message_pair in y:
            assert isinstance(
                message_pair, (tuple, list)
            ), f"Expected a list of lists or list of tuples. Received: {message_pair}"
            assert (
                len(message_pair) == 2
            ), f"Expected a list of lists of length 2 or list of tuples of length 2. Received: {message_pair}"

            processed_messages.append(
                [
                    self._postprocess_chat_messages(message_pair[0], "user"),
                    self._postprocess_chat_messages(message_pair[1], "bot"),
                ]
            )
        return processed_messages

def postprocess_chat_messages(
        self, chat_message: str | tuple | list | None, role: str
    ) -> str | dict | None:
        if chat_message is None:
            return None
        else:
            if isinstance(chat_message, (tuple, list)):
                if len(chat_message) > 0 and "text" in chat_message[0]:
                    chat_message = chat_message[0]["text"]
                else:
                    file_uri = chat_message[0]
                    if utils.validate_url(file_uri):
                        filepath = file_uri
                    else:
                        filepath = self.make_temp_copy_if_needed(file_uri)

                    mime_type = client_utils.get_mimetype(filepath)
                    return {
                        "name": filepath,
                        "mime_type": mime_type,
                        "alt_text": chat_message[1] if len(chat_message) > 1 else None,
                        "data": None,  # These last two fields are filled in by the frontend
                        "is_file": True,
                    }
            if isinstance(chat_message, str):
                # chat_message = inspect.cleandoc(chat_message)
                # escape html spaces
                # chat_message = chat_message.replace(" ", "&nbsp;")
                if role == "bot":
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
            kwargs["elem_classes"].append('multiselect')

        res = original_func(self, *args, **kwargs)
        return res
    return wrapper

def patch_gradio():
    original_Component_init = gr.components.Component.__init__
    gr.components.Component.__init__ = init_with_class_name_as_elem_classes(original_Component_init)
    gr.components.FormComponent.__init__ = init_with_class_name_as_elem_classes(original_Component_init)

    gr.blocks.BlockContext.__init__ = init_with_class_name_as_elem_classes(gr.blocks.BlockContext.__init__)

    # gr.Chatbot._postprocess_chat_messages = postprocess_chat_messages
    # gr.Chatbot.postprocess = postprocess
