import os
import commentjson as json
import openai
import time
from openai import OpenAI
from .base_model import BaseLLMModel
from .. import shared
from ..config import retrieve_proxy


class OpenAI_Assistant_Client(BaseLLMModel):
    def __init__(self, model_name, assisant_id, api_key, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)
        self.api_key = api_key
        self.assistant_id = assisant_id
        if self.assistant_id == "":
            self.assistant_id = self._get_asst_id()

    def _get_asst_id(self):
        #需要的asstname为modelname trim掉“asst_"字符
        asst_name = self.model_name[5:]
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}

        for assistant in config["openai_assistant"]:
            if asst_name == assistant["assistant_name"]:
                return assistant["assistant_id"]

        return ""

    def _get_asst_prompt(self):
        prompt = self.history[-1]["content"]
        return prompt

    def _create_thread(self, client):
        with retrieve_proxy():
            empty_thread = client.beta.threads.create()
            thread_id = empty_thread.id
            return thread_id

    @shared.state.switching_api_key
    def get_answer_at_once(self):
        with retrieve_proxy():
            client = OpenAI(api_key=openai.api_key)
            assistant_id = self.assistant_id
            assistant = client.beta.assistants.retrieve(assistant_id)

            if len(self.history) <= 1:
                thread_id = self._create_thread(client)
                self.history[-1]["thread_id"] = thread_id
                # print("### 新的thread")
            else:
                thread_id = self.history[-3]["thread_id"]
                # print("### 继续之前的thread")

            self.history[-1]["thread_id"] = thread_id
            self.history[-1]["asst_id"] = assistant_id
            thread = client.beta.threads.retrieve(thread_id)
            # print(thread)

            prompt = self._get_asst_prompt()
            thread_message = client.beta.threads.messages.create(
                thread_id,
                role="user",
                content=prompt,
            )
            message_id = thread_message.id
            self.history[-1]["message_id"] = message_id

            message = client.beta.threads.messages.retrieve(
                message_id=message_id,
                thread_id=thread_id,
            )

            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id,
            )

            def wait_on_run(run, thread):
                while run.status == "queued" or run.status == "in_progress":
                    run = client.beta.threads.runs.retrieve(
                        thread_id=thread.id,
                        run_id=run.id,
                    )
                    time.sleep(0.5)
                return run

            run = wait_on_run(run, thread)

            messages = client.beta.threads.messages.list(
                thread_id=thread.id
            )

            for message in messages.data:
                if message.role == "assistant":
                    if message.content[0].type == "text":
                        # answers.append(message.content[0].text.value + "\n\n")
                        latest_message = message.content[0].text.value
                        break
                elif message.role == "user":
                    break

        return latest_message, len(latest_message)
