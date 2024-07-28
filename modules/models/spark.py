import _thread as thread
import base64
import datetime
import hashlib
import hmac
import json
from collections import deque
from urllib.parse import urlparse
import ssl
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time
from threading import Condition
import websocket
import logging

from .base_model import BaseLLMModel, CallbackToIterator


class Ws_Param(object):
    # 来自官方 Demo
    # 初始化
    def __init__(self, APPID, APIKey, APISecret, Spark_url):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.host = urlparse(Spark_url).netloc
        self.path = urlparse(Spark_url).path
        self.Spark_url = Spark_url

    # 生成url
    def create_url(self):
        # 生成RFC1123格式的时间戳
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        # 拼接字符串
        signature_origin = "host: " + self.host + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + self.path + " HTTP/1.1"

        # 进行hmac-sha256进行加密
        signature_sha = hmac.new(
            self.APISecret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        signature_sha_base64 = base64.b64encode(
            signature_sha).decode(encoding="utf-8")

        authorization_origin = f'api_key="{self.APIKey}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'

        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode(
            encoding="utf-8"
        )

        # 将请求的鉴权参数组合为字典
        v = {"authorization": authorization, "date": date, "host": self.host}
        # 拼接鉴权参数，生成url
        url = self.Spark_url + "?" + urlencode(v)
        # 此处打印出建立连接时候的url,参考本demo的时候可取消上方打印的注释，比对相同参数时生成的url与自己代码生成的url是否一致
        return url


class Spark_Client(BaseLLMModel):
    def __init__(self, model_name, appid, api_key, api_secret, user_name="") -> None:
        super().__init__(model_name=model_name, user=user_name)
        self.api_key = api_key
        self.appid = appid
        self.api_secret = api_secret
        if None in [self.api_key, self.appid, self.api_secret]:
            raise Exception("请在配置文件或者环境变量中设置讯飞的API Key、APP ID和API Secret")
        if "2.0" in self.model_name:
            self.spark_url = "wss://spark-api.xf-yun.com/v2.1/chat"
            self.domain = "generalv2"
        elif "3.0" in self.model_name:
            self.spark_url = "wss://spark-api.xf-yun.com/v3.1/chat"
            self.domain = "generalv3"
        elif "3.5" in self.model_name:
            self.spark_url = "wss://spark-api.xf-yun.com/v3.5/chat"
            self.domain = "generalv3.5"
        elif "4.0" in self.model_name:
            self.spark_url = "wss://spark-api.xf-yun.com/v4.0/chat"
            self.domain = "4.0Ultra"
        else:
            self.spark_url = "wss://spark-api.xf-yun.com/v1.1/chat"
            self.domain = "general"

    # 收到websocket错误的处理
    def on_error(self, ws, error):
        ws.iterator.callback("出现了错误:" + error)

    # 收到websocket关闭的处理
    def on_close(self, ws, one, two):
        pass

    # 收到websocket连接建立的处理
    def on_open(self, ws):
        thread.start_new_thread(self.run, (ws,))

    def run(self, ws, *args):
        data = json.dumps(
            self.gen_params()
        )
        ws.send(data)

    # 收到websocket消息的处理
    def on_message(self, ws, message):
        ws.iterator.callback(message)

    def gen_params(self):
        """
        通过appid和用户的提问来生成请参数
        """
        data = {
            "header": {"app_id": self.appid, "uid": "1234"},
            "parameter": {
                "chat": {
                    "domain": self.domain,
                    "random_threshold": self.temperature,
                    "max_tokens": 4096,
                    "auditing": "default",
                }
            },
            "payload": {"message": {"text": self.history}},
        }
        return data

    def get_answer_stream_iter(self):
        wsParam = Ws_Param(self.appid, self.api_key, self.api_secret, self.spark_url)
        websocket.enableTrace(False)
        wsUrl = wsParam.create_url()
        ws = websocket.WebSocketApp(
            wsUrl,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )
        ws.appid = self.appid
        ws.domain = self.domain

        # Initialize the CallbackToIterator
        ws.iterator = CallbackToIterator()

        # Start the WebSocket connection in a separate thread
        thread.start_new_thread(
            ws.run_forever, (), {"sslopt": {"cert_reqs": ssl.CERT_NONE}}
        )

        # Iterate over the CallbackToIterator instance
        answer = ""
        total_tokens = 0
        for message in ws.iterator:
            data = json.loads(message)
            code = data["header"]["code"]
            if code != 0:
                ws.close()
                raise Exception(f"请求错误: {code}, {data}")
            else:
                choices = data["payload"]["choices"]
                status = choices["status"]
                content = choices["text"][0]["content"]
                if "usage" in data["payload"]:
                    total_tokens = data["payload"]["usage"]["text"]["total_tokens"]
                answer += content
                if status == 2:
                    ws.iterator.finish()  # Finish the iterator when the status is 2
                    ws.close()
                yield answer, total_tokens
