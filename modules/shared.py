from modules.presets import COMPLETION_URL, BALANCE_API_URL, USAGE_API_URL, API_HOST
import os
class State:
    interrupted = False
    completion_url = COMPLETION_URL
    balance_api_url = BALANCE_API_URL
    usage_api_url = USAGE_API_URL

    def interrupt(self):
        self.interrupted = True

    def recover(self):
        self.interrupted = False

    def set_api_host(self, api_host):
        self.completion_url = f"https://{api_host}/v1/chat/completions"
        self.balance_api_url = f"https://{api_host}/dashboard/billing/credit_grants"
        self.usage_api_url = f"https://{api_host}/dashboard/billing/usage"
        os.environ["OPENAI_API_BASE"] = f"https://{api_host}/v1"

    def reset_api_host(self):
        self.completion_url = COMPLETION_URL
        self.balance_api_url = BALANCE_API_URL
        self.usage_api_url = USAGE_API_URL
        os.environ["OPENAI_API_BASE"] = f"https://{API_HOST}/v1"
        return API_HOST

    def reset_all(self):
        self.interrupted = False
        self.completion_url = COMPLETION_URL

state = State()
