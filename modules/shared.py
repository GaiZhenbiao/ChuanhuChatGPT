from modules.presets import CHAT_COMPLETION_URL, BALANCE_API_URL, USAGE_API_URL, API_HOST, OPENAI_API_BASE, IMAGES_COMPLETION_URL
import os
import queue
import openai

def format_openai_host(api_host: str):
    api_host = api_host.rstrip("/")
    if not api_host.startswith("http"):
        api_host = f"https://{api_host}"
    if api_host.endswith("/v1"):
        api_host = api_host[:-3]
    chat_completion_url = f"{api_host}/v1/chat/completions"
    images_completion_url = f"{api_host}/v1/images/generations"
    openai_api_base = f"{api_host}/v1"
    balance_api_url = f"{api_host}/dashboard/billing/credit_grants"
    usage_api_url = f"{api_host}/dashboard/billing/usage"
    return chat_completion_url, images_completion_url, openai_api_base, balance_api_url, usage_api_url

class State:
    interrupted = False
    multi_api_key = False
    chat_completion_url = CHAT_COMPLETION_URL
    balance_api_url = BALANCE_API_URL
    usage_api_url = USAGE_API_URL
    openai_api_base = OPENAI_API_BASE
    images_completion_url = IMAGES_COMPLETION_URL
    api_host = API_HOST

    def interrupt(self):
        self.interrupted = True

    def recover(self):
        self.interrupted = False

    def set_api_host(self, api_host: str):
        self.api_host = api_host
        self.chat_completion_url, self.images_completion_url, self.openai_api_base, self.balance_api_url, self.usage_api_url = format_openai_host(api_host)
        os.environ["OPENAI_API_BASE"] = self.openai_api_base

    def reset_api_host(self):
        self.chat_completion_url = CHAT_COMPLETION_URL
        self.images_completion_url = IMAGES_COMPLETION_URL
        self.balance_api_url = BALANCE_API_URL
        self.usage_api_url = USAGE_API_URL
        self.api_host = API_HOST
        os.environ["OPENAI_API_BASE"] = f"https://{API_HOST}"
        return API_HOST

    def reset_all(self):
        self.interrupted = False
        self.chat_completion_url = CHAT_COMPLETION_URL

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
assets_path = os.path.join(chuanhu_path, "web_assets")