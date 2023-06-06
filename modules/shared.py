from modules.presets import COMPLETION_URL, BALANCE_API_URL, USAGE_API_URL, API_HOST
import os
import queue
import openai

class State:
    interrupted = False
    multi_api_key = False
    completion_url = COMPLETION_URL
    balance_api_url = BALANCE_API_URL
    usage_api_url = USAGE_API_URL

    def interrupt(self):
        self.interrupted = True

    def recover(self):
        self.interrupted = False

    def set_api_host(self, api_host: str):
        api_host = api_host.rstrip("/")
        if not api_host.startswith("http"):
            api_host = f"https://{api_host}"
        if api_host.endswith("/v1"):
            api_host = api_host[:-3]
        self.completion_url = f"{api_host}/v1/chat/completions"
        self.balance_api_url = f"{api_host}/dashboard/billing/credit_grants"
        self.usage_api_url = f"{api_host}/dashboard/billing/usage"
        os.environ["OPENAI_API_BASE"] = api_host

    def reset_api_host(self):
        self.completion_url = COMPLETION_URL
        self.balance_api_url = BALANCE_API_URL
        self.usage_api_url = USAGE_API_URL
        os.environ["OPENAI_API_BASE"] = f"https://{API_HOST}"
        return API_HOST

    def reset_all(self):
        self.interrupted = False
        self.completion_url = COMPLETION_URL

    def set_api_key_queue(self, api_key_list):
        self.multi_api_key = True
        self.api_key_queue = queue.Queue()
        for api_key in api_key_list:
            self.api_key_queue.put(api_key)

    def switching_api_key(self, func):
        if not hasattr(self, "api_key_queue"):
            return func

        def wrapped(*args, **kwargs):
            api_key = self.api_key_queue.get()
            args[0].api_key = api_key
            ret = func(*args, **kwargs)
            self.api_key_queue.put(api_key)
            return ret

        return wrapped


state = State()

modules_path = os.path.dirname(os.path.realpath(__file__))
chuanhu_path = os.path.dirname(modules_path)
