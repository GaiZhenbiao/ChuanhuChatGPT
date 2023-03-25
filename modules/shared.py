from modules.presets import API_URL

class State:
    interrupted = False
    api_url = API_URL

    def interrupt(self):
        self.interrupted = True

    def recover(self):
        self.interrupted = False

    def set_api_url(self, api_url):
        self.api_url = api_url

    def reset_api_url(self):
        self.api_url = API_URL
        return self.api_url

    def reset_all(self):
        self.interrupted = False
        self.api_url = API_URL

state = State()
