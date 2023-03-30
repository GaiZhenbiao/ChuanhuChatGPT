from modules.presets import BASE_API_URL, API_URL, USAGE_API_URL, BALANCE_API_URL

class State:
    interrupted = False
    def __init__(self) -> None:
        self.base_url = BASE_API_URL

    def interrupt(self):
        self.interrupted = True

    def recover(self):
        self.interrupted = False

    def set_base_url(self, api_url):
        self.base_url = api_url

    # API URL 相关
    def get_api_url(self):
        return self.base_url + API_URL

    # USAGE URL相关
    def get_usage_url(self):
        return self.base_url + USAGE_API_URL

    # BALANCE URL相关
    def get_balance_url(self):
        return self.base_url + BALANCE_API_URL

    def reset(self):
        self.interrupted = False
        self.base_url = BASE_API_URL

state = State()
