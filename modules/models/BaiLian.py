from openai import OpenAI

from .base_model import BaseLLMModel

think_start = "> <small>----think start----\n"
think_end = "\n> ----think end----</small>\n\n"


class BaiLian_Client(BaseLLMModel):
    def __init__(self, model_name, api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name, temperature=0.6)
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

    def _remove_think_from_content(self, content: str):
        if content.startswith(think_start):
            end_pos = content.find(think_end)
            if end_pos != -1:
                return content[end_pos + len(think_end):]
            else:
                return content[len(think_start):]
        return content

    def _organized_history(self):
        clean_history = []
        if self.system_prompt.strip() != "":
            clean_history.append({"role": "system", "content": self.system_prompt})
        for message in self.history:
            if message["role"] == "assistant":
                clean_history.append({"role": "assistant", "content": self._remove_think_from_content(message["content"])})
            else:
                clean_history.append(message)
        return clean_history

    def _assemble_thinking(self, reasoning_content: str, content: str):
        return '''{think_start}> {think}{think_end}{reply}'''.format(
            think_start=think_start,
            think="\n> ".join(reasoning_content.split("\n")),
            reply=content,
            think_end=think_end
        )

    def get_answer_at_once(self):
        completion = self._client.chat.completions.create(
            model=self.model_name,  # 此处以 deepseek-r1 为例，可按需更换模型名称。
            messages=self._organized_history(),
        )
        msg = f'''{think_start}{completion.choices[0].message.reasoning_content}{think_end}{completion.choices[0].message.content}'''
        return msg, completion.usage.total_tokens

    def get_answer_stream_iter(self):
        completion = self._client.chat.completions.create(
            model=self.model_name,  # 此处以 deepseek-r1 为例，可按需更换模型名称。
            messages=self._organized_history(),
            temperature=self.temperature,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            logit_bias=self.logit_bias,
            user=self.user_identifier,
            stream=True
        )
        reasoning_content = ''
        content = ''
        total_tokens = 0
        is_answering = False
        for chunk in completion:
            # 如果chunk.choices为空，则打印usage
            if not chunk.choices:
                total_tokens = chunk.usage.total_tokens
            else:
                delta = chunk.choices[0].delta
                # 打印思考过程
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content != '':
                    reasoning_content += delta.reasoning_content
                    yield self._assemble_thinking(reasoning_content, content)
                if hasattr(delta, 'content') and delta.content != '':
                    if delta.content != "" and not is_answering:
                        is_answering = True
                        yield self._assemble_thinking(reasoning_content, content)
                    # 打印回复过程
                    content += delta.content
                    yield self._assemble_thinking(reasoning_content, content)
