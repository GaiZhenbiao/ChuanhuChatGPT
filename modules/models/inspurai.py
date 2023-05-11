# 代码主要来源于 https://github.com/Shawn-Inspur/Yuan-1.0/blob/main/yuan_api/inspurai.py

import hashlib
import json
import os
import time
import uuid
from datetime import datetime

import pytz
import requests

from modules.presets import NO_APIKEY_MSG
from modules.models.base_model import BaseLLMModel


class Example:
    """ store some examples(input, output pairs and formats) for few-shots to prime the model."""

    def __init__(self, inp, out):
        self.input = inp
        self.output = out
        self.id = uuid.uuid4().hex

    def get_input(self):
        """return the input of the example."""
        return self.input

    def get_output(self):
        """Return the output of the example."""
        return self.output

    def get_id(self):
        """Returns the unique ID of the example."""
        return self.id

    def as_dict(self):
        return {
            "input": self.get_input(),
            "output": self.get_output(),
            "id": self.get_id(),
        }


class Yuan:
    """The main class for a user to interface with the Inspur Yuan API.
    A user can set account info and add examples of the API request.
    """

    def __init__(self,
                 engine='base_10B',
                 temperature=0.9,
                 max_tokens=100,
                 input_prefix='',
                 input_suffix='\n',
                 output_prefix='答:',
                 output_suffix='\n\n',
                 append_output_prefix_to_query=False,
                 topK=1,
                 topP=0.9,
                 frequencyPenalty=1.2,
                 responsePenalty=1.2,
                 noRepeatNgramSize=2):

        self.examples = {}
        self.engine = engine
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.topK = topK
        self.topP = topP
        self.frequencyPenalty = frequencyPenalty
        self.responsePenalty = responsePenalty
        self.noRepeatNgramSize = noRepeatNgramSize
        self.input_prefix = input_prefix
        self.input_suffix = input_suffix
        self.output_prefix = output_prefix
        self.output_suffix = output_suffix
        self.append_output_prefix_to_query = append_output_prefix_to_query
        self.stop = (output_suffix + input_prefix).strip()
        self.api = None

        # if self.engine not in ['base_10B','translate','dialog']:
        #     raise Exception('engine must be one of [\'base_10B\',\'translate\',\'dialog\'] ')
    def set_account(self, api_key):
        account = api_key.split('||')
        self.api = YuanAPI(user=account[0], phone=account[1])

    def add_example(self, ex):
        """Add an example to the object.
        Example must be an instance of the Example class."""
        assert isinstance(ex, Example), "Please create an Example object."
        self.examples[ex.get_id()] = ex

    def delete_example(self, id):
        """Delete example with the specific id."""
        if id in self.examples:
            del self.examples[id]

    def get_example(self, id):
        """Get a single example."""
        return self.examples.get(id, None)

    def get_all_examples(self):
        """Returns all examples as a list of dicts."""
        return {k: v.as_dict() for k, v in self.examples.items()}

    def get_prime_text(self):
        """Formats all examples to prime the model."""
        return "".join(
            [self.format_example(ex) for ex in self.examples.values()])

    def get_engine(self):
        """Returns the engine specified for the API."""
        return self.engine

    def get_temperature(self):
        """Returns the temperature specified for the API."""
        return self.temperature

    def get_max_tokens(self):
        """Returns the max tokens specified for the API."""
        return self.max_tokens

    def craft_query(self, prompt):
        """Creates the query for the API request."""
        q = self.get_prime_text(
        ) + self.input_prefix + prompt + self.input_suffix
        if self.append_output_prefix_to_query:
            q = q + self.output_prefix

        return q

    def format_example(self, ex):
        """Formats the input, output pair."""
        return self.input_prefix + ex.get_input(
        ) + self.input_suffix + self.output_prefix + ex.get_output(
        ) + self.output_suffix

    def response(self,
                 query,
                 engine='base_10B',
                 max_tokens=20,
                 temperature=0.9,
                 topP=0.1,
                 topK=1,
                 frequencyPenalty=1.0,
                 responsePenalty=1.0,
                 noRepeatNgramSize=0):
        """Obtains the original result returned by the API."""

        if self.api is None:
            return NO_APIKEY_MSG
        try:
            # requestId = submit_request(query,temperature,topP,topK,max_tokens, engine)
            requestId = self.api.submit_request(query, temperature, topP, topK, max_tokens, engine, frequencyPenalty,
                                       responsePenalty, noRepeatNgramSize)
            response_text = self.api.reply_request(requestId)
        except Exception as e:
            raise e

        return response_text

    def del_special_chars(self, msg):
        special_chars = ['<unk>', '<eod>', '#', '▃', '▁', '▂', '　']
        for char in special_chars:
            msg = msg.replace(char, '')
        return msg

    def submit_API(self, prompt, trun=[]):
        """Submit prompt to yuan API interface and obtain an pure text reply.
        :prompt: Question or any content a user may input.
        :return: pure text response."""
        query = self.craft_query(prompt)
        res = self.response(query, engine=self.engine,
                            max_tokens=self.max_tokens,
                            temperature=self.temperature,
                            topP=self.topP,
                            topK=self.topK,
                            frequencyPenalty=self.frequencyPenalty,
                            responsePenalty=self.responsePenalty,
                            noRepeatNgramSize=self.noRepeatNgramSize)
        if 'resData' in res and res['resData'] != None:
            txt = res['resData']
        else:
            txt = '模型返回为空，请尝试修改输入'
        # 单独针对翻译模型的后处理
        if self.engine == 'translate':
            txt = txt.replace(' ##', '').replace(' "', '"').replace(": ", ":").replace(" ,", ",") \
                .replace('英文：', '').replace('文：', '').replace("( ", "(").replace(" )", ")")
        else:
            txt = txt.replace(' ', '')
        txt = self.del_special_chars(txt)

        # trun多结束符截断模型输出
        if isinstance(trun, str):
            trun = [trun]
        try:
            if trun != None and isinstance(trun, list) and trun != []:
                for tr in trun:
                    if tr in txt and tr != "":
                        txt = txt[:txt.index(tr)]
                    else:
                        continue
        except:
            return txt
        return txt


class YuanAPI:
    ACCOUNT = ''
    PHONE = ''

    SUBMIT_URL = "http://api.airyuan.cn:32102/v1/interface/api/infer/getRequestId?"
    REPLY_URL = "http://api.airyuan.cn:32102/v1/interface/api/result?"

    def __init__(self, user, phone):
        self.ACCOUNT = user
        self.PHONE = phone

    @staticmethod
    def code_md5(str):
        code = str.encode("utf-8")
        m = hashlib.md5()
        m.update(code)
        result = m.hexdigest()
        return result

    @staticmethod
    def rest_get(url, header, timeout, show_error=False):
        '''Call rest get method'''
        try:
            response = requests.get(url, headers=header, timeout=timeout, verify=False)
            return response
        except Exception as exception:
            if show_error:
                print(exception)
            return None

    def header_generation(self):
        """Generate header for API request."""
        t = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d")
        token = self.code_md5(self.ACCOUNT + self.PHONE + t)
        headers = {'token': token}
        return headers

    def submit_request(self, query, temperature, topP, topK, max_tokens, engine, frequencyPenalty, responsePenalty,
                       noRepeatNgramSize):
        """Submit query to the backend server and get requestID."""
        headers = self.header_generation()
        # url=SUBMIT_URL + "account={0}&data={1}&temperature={2}&topP={3}&topK={4}&tokensToGenerate={5}&type={6}".format(ACCOUNT,query,temperature,topP,topK,max_tokens,"api")
        # url=SUBMIT_URL + "engine={0}&account={1}&data={2}&temperature={3}&topP={4}&topK={5}&tokensToGenerate={6}" \
        #                  "&type={7}".format(engine,ACCOUNT,query,temperature,topP,topK, max_tokens,"api")
        url = self.SUBMIT_URL + "engine={0}&account={1}&data={2}&temperature={3}&topP={4}&topK={5}&tokensToGenerate={6}" \
                                "&type={7}&frequencyPenalty={8}&responsePenalty={9}&noRepeatNgramSize={10}". \
            format(engine, self.ACCOUNT, query, temperature, topP, topK, max_tokens, "api", frequencyPenalty,
                   responsePenalty, noRepeatNgramSize)
        response = self.rest_get(url, headers, 30)
        response_text = json.loads(response.text)
        if response_text["flag"]:
            requestId = response_text["resData"]
            return requestId
        else:
            raise RuntimeWarning(response_text)

    def reply_request(self, requestId, cycle_count=5):
        """Check reply API to get the inference response."""
        url = self.REPLY_URL + "account={0}&requestId={1}".format(self.ACCOUNT, requestId)
        headers = self.header_generation()
        response_text = {"flag": True, "resData": None}
        for i in range(cycle_count):
            response = self.rest_get(url, headers, 30, show_error=True)
            response_text = json.loads(response.text)
            if response_text["resData"] is not None:
                return response_text
            if response_text["flag"] is False and i == cycle_count - 1:
                raise RuntimeWarning(response_text)
            time.sleep(3)
        return response_text


class Yuan_Client(BaseLLMModel):

    def __init__(self, model_name, api_key, user_name="", system_prompt=None):
        super().__init__(model_name=model_name, user=user_name)
        self.history = []
        self.api_key = api_key
        self.system_prompt = system_prompt

        self.input_prefix = ""
        self.output_prefix = ""

    def set_text_prefix(self, option, value):
        if option == 'input_prefix':
            self.input_prefix = value
        elif option == 'output_prefix':
            self.output_prefix = value

    def get_answer_at_once(self):
        # yuan temperature is (0,1] and base model temperature is [0,2], and yuan 0.9 == base 1 so need to convert
        temperature = self.temperature if self.temperature <= 1 else 0.9 + (self.temperature - 1) / 10
        topP = self.top_p
        topK = self.n_choices
        # max_tokens should be in [1,200]
        max_tokens = self.max_generation_token if self.max_generation_token is not None else 50
        if max_tokens > 200:
            max_tokens = 200
        stop = self.stop_sequence if self.stop_sequence is not None else []
        examples = []
        system_prompt = self.system_prompt
        if system_prompt is not None:
            lines = system_prompt.splitlines()
            # TODO: support prefixes in system prompt or settings
            """
            if lines[0].startswith('-'):
                prefixes = lines.pop()[1:].split('|')
                self.input_prefix = prefixes[0]
                if len(prefixes) > 1:
                    self.output_prefix = prefixes[1]
                if len(prefixes) > 2:
                    stop = prefixes[2].split(',')
            """
            for i in range(0, len(lines), 2):
                in_line = lines[i]
                out_line = lines[i + 1] if i + 1 < len(lines) else ""
                examples.append((in_line, out_line))
        yuan = Yuan(engine=self.model_name.replace('yuanai-1.0-', ''),
                    temperature=temperature,
                    max_tokens=max_tokens,
                    topK=topK,
                    topP=topP,
                    input_prefix=self.input_prefix,
                    input_suffix="",
                    output_prefix=self.output_prefix,
                    output_suffix="".join(stop),
                    )
        if not self.api_key:
            return NO_APIKEY_MSG, 0
        yuan.set_account(self.api_key)

        for in_line, out_line in examples:
            yuan.add_example(Example(inp=in_line, out=out_line))

        prompt = self.history[-1]["content"]
        answer = yuan.submit_API(prompt, trun=stop)
        return answer, len(answer)
