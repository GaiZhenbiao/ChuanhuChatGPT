from langchain.chat_models import AzureChatOpenAI, ChatOpenAI
import os

from .base_model import Base_Chat_Langchain_Client

# load_config_to_environ(["azure_openai_api_key", "azure_api_base_url", "azure_openai_api_version", "azure_deployment_name"])

class Azure_OpenAI_Client(Base_Chat_Langchain_Client):
    def setup_model(self):
        # inplement this to setup the model then return it
        return AzureChatOpenAI(
            openai_api_base=os.environ["AZURE_OPENAI_API_BASE_URL"],
            openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            deployment_name=os.environ["AZURE_DEPLOYMENT_NAME"],
            openai_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            openai_api_type="azure",
            streaming=True
        )
