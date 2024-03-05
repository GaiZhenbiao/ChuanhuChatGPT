from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT
from ..presets import *
from ..utils import *

from .base_model import BaseLLMModel


class Claude_Client(BaseLLMModel):
    def __init__(self, model_name, api_secret) -> None:
        super().__init__(model_name=model_name)
        self.api_secret = api_secret
        if None in [self.api_secret]:
            raise Exception("请在配置文件或者环境变量中设置Claude的API Secret")
        self.claude_client = Anthropic(api_key=self.api_secret)

    def _get_claude_style_history(self):
        history = []
        image_buffer = []
        image_count = 0
        for message in self.history:
            if message["role"] == "user":
                content = []
                if image_buffer:
                    if image_count == 1:
                        content.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": f"image/{self.get_image_type(image_buffer[0])}",
                                    "data": self.get_base64_image(image_buffer[0]),
                                },
                            },
                        )
                    else:
                        image_buffer_length = len(image_buffer)
                        for idx, image in enumerate(image_buffer):
                            content.append(
                                {"type": "text", "text": f"Image {image_count - image_buffer_length + idx + 1}:"},
                            )
                            content.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": f"image/{self.get_image_type(image)}",
                                        "data": self.get_base64_image(image),
                                    },
                                },
                            )
                if content:
                    content.append({"type": "text", "text": message["content"]})
                    history.append(construct_user(content))
                    image_buffer = []
                else:
                    history.append(message)
            elif message["role"] == "assistant":
                history.append(message)
            elif message["role"] == "image":
                image_buffer.append(message["content"])
                image_count += 1
        # history with base64 data replaced with "#base64#"
        # history_for_display = history.copy()
        # for message in history_for_display:
        #     if message["role"] == "user":
        #         if type(message["content"]) == list:
        #             for content in message["content"]:
        #                 if content["type"] == "image":
        #                     content["source"]["data"] = "#base64#"
        # logging.info(f"History for Claude: {history_for_display}")
        return history

    def get_answer_stream_iter(self):
        system_prompt = self.system_prompt
        history = self._get_claude_style_history()

        try:
            with self.claude_client.messages.stream(
                model=self.model_name,
                max_tokens=self.max_generation_token,
                messages=history,
                system=system_prompt,
            ) as stream:
                partial_text = ""
                for text in stream.text_stream:
                    partial_text += text
                    yield partial_text
        except Exception as e:
            yield i18n(GENERAL_ERROR_MSG) + ": " + str(e)

    def get_answer_at_once(self):
        system_prompt = self.system_prompt
        history = self._get_claude_style_history()
        if system_prompt is not None:
            history = [construct_system(system_prompt), *history]

        response = self.claude_client.messages.create(
            model=self.model_name,
            max_tokens=self.max_generation_token,
            messages=history,
            system=system_prompt,
        )
        if response is not None:
            return response["content"][0]["text"], response["usage"]["output_tokens"]
        else:
            return i18n("获取资源错误"), 0
