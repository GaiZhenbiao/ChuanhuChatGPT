import base64
import io
import json
import logging
import os
import pathlib
import tempfile
import time
from datetime import datetime

import requests
import tiktoken
from PIL import Image

from modules.config import retrieve_proxy
from modules.models.XMChat import XMChat

mj_proxy_api_base = os.getenv("MIDJOURNEY_PROXY_API_BASE")
mj_discord_proxy_url = os.getenv("MIDJOURNEY_DISCORD_PROXY_URL")
mj_temp_folder = os.getenv("MIDJOURNEY_TEMP_FOLDER")


class Midjourney_Client(XMChat):

    class FetchDataPack:
        """
        A class to store data for current fetching data from Midjourney API
        """

        action: str  # current action, e.g. "IMAGINE", "UPSCALE", "VARIATION"
        prefix_content: str  # prefix content, task description and process hint
        task_id: str  # task id
        start_time: float  # task start timestamp
        timeout: int  # task timeout in seconds
        finished: bool  # whether the task is finished
        prompt: str  # prompt for the task

        def __init__(self, action, prefix_content, task_id, timeout=900):
            self.action = action
            self.prefix_content = prefix_content
            self.task_id = task_id
            self.start_time = time.time()
            self.timeout = timeout
            self.finished = False

    def __init__(self, model_name, api_key, user_name=""):
        super().__init__(api_key, user_name)
        self.model_name = model_name
        self.history = []
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "mj-api-secret": f"{api_key}"
        }
        self.proxy_url = mj_proxy_api_base
        self.command_splitter = "::"

        if mj_temp_folder:
            temp = "./tmp"
            if user_name:
                temp = os.path.join(temp, user_name)
            if not os.path.exists(temp):
                os.makedirs(temp)
            self.temp_path = tempfile.mkdtemp(dir=temp)
            logging.info("mj temp folder: " + self.temp_path)
        else:
            self.temp_path = None

    def use_mj_self_proxy_url(self, img_url):
        """
        replace discord cdn url with mj self proxy url
        """
        return img_url.replace(
            "https://cdn.discordapp.com/",
            mj_discord_proxy_url and mj_discord_proxy_url or "https://cdn.discordapp.com/"
        )

    def split_image(self, image_url):
        """
        when enabling temp dir, split image into 4 parts
        """
        with retrieve_proxy():
            image_bytes = requests.get(image_url).content
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        # calculate half width and height
        half_width = width // 2
        half_height = height // 2
        # create coordinates (top-left x, top-left y, bottom-right x, bottom-right y)
        coordinates = [(0, 0, half_width, half_height),
                       (half_width, 0, width, half_height),
                       (0, half_height, half_width, height),
                       (half_width, half_height, width, height)]

        images = [img.crop(c) for c in coordinates]
        return images

    def auth_mj(self):
        """
        auth midjourney api
        """
        # TODO: check if secret is valid
        return {'status': 'ok'}

    def request_mj(self, path: str, action: str, data: str, retries=3):
        """
        request midjourney api
        """
        mj_proxy_url = self.proxy_url
        if mj_proxy_url is None or not (mj_proxy_url.startswith("http://") or mj_proxy_url.startswith("https://")):
            raise Exception('please set MIDJOURNEY_PROXY_API_BASE in ENV or in config.json')

        auth_ = self.auth_mj()
        if auth_.get('error'):
            raise Exception('auth not set')

        fetch_url = f"{mj_proxy_url}/{path}"
        # logging.info(f"[MJ Proxy] {action} {fetch_url} params: {data}")

        for _ in range(retries):
            try:
                with retrieve_proxy():
                    res = requests.request(method=action, url=fetch_url, headers=self.headers, data=data)
                break
            except Exception as e:
                print(e)

        if res.status_code != 200:
            raise Exception(f'{res.status_code} - {res.content}')

        return res

    def fetch_status(self, fetch_data: FetchDataPack):
        """
        fetch status of current task
        """
        if fetch_data.start_time + fetch_data.timeout < time.time():
            fetch_data.finished = True
            return "任务超时，请检查 dc 输出。描述：" + fetch_data.prompt

        time.sleep(3)
        status_res = self.request_mj(f"task/{fetch_data.task_id}/fetch", "GET", '')
        status_res_json = status_res.json()
        if not (200 <= status_res.status_code < 300):
            raise Exception("任务状态获取失败：" + status_res_json.get(
                'error') or status_res_json.get('description') or '未知错误')
        else:
            fetch_data.finished = False
            if status_res_json['status'] == "SUCCESS":
                content = status_res_json['imageUrl']
                fetch_data.finished = True
            elif status_res_json['status'] == "FAILED":
                content = status_res_json['failReason'] or '未知原因'
                fetch_data.finished = True
            elif status_res_json['status'] == "NOT_START":
                content = f'任务未开始，已等待 {time.time() - fetch_data.start_time:.2f} 秒'
            elif status_res_json['status'] == "IN_PROGRESS":
                content = '任务正在运行'
                if status_res_json.get('progress'):
                    content += f"，进度：{status_res_json['progress']}"
            elif status_res_json['status'] == "SUBMITTED":
                content = '任务已提交处理'
            elif status_res_json['status'] == "FAILURE":
                fetch_data.finished = True
                return "任务处理失败，原因：" + status_res_json['failReason'] or '未知原因'
            else:
                content = status_res_json['status']
            if fetch_data.finished:
                img_url = self.use_mj_self_proxy_url(status_res_json['imageUrl'])
                if fetch_data.action == "DESCRIBE":
                    return f"\n{status_res_json['prompt']}"
                time_cost_str = f"\n\n{fetch_data.action} 花费时间：{time.time() - fetch_data.start_time:.2f} 秒"
                upscale_str = ""
                variation_str = ""
                if fetch_data.action in ["IMAGINE", "UPSCALE", "VARIATION"]:
                    upscale = [f'/mj UPSCALE{self.command_splitter}{i+1}{self.command_splitter}{fetch_data.task_id}'
                               for i in range(4)]
                    upscale_str = '\n放大图片：\n\n' + '\n\n'.join(upscale)
                    variation = [f'/mj VARIATION{self.command_splitter}{i+1}{self.command_splitter}{fetch_data.task_id}'
                                 for i in range(4)]
                    variation_str = '\n图片变体：\n\n' + '\n\n'.join(variation)
                if self.temp_path and fetch_data.action in ["IMAGINE", "VARIATION"]:
                    try:
                        images = self.split_image(img_url)
                        # save images to temp path
                        for i in range(4):
                            images[i].save(pathlib.Path(self.temp_path) / f"{fetch_data.task_id}_{i}.png")
                        img_str = '\n'.join(
                            [f"![{fetch_data.task_id}](/file={self.temp_path}/{fetch_data.task_id}_{i}.png)"
                             for i in range(4)])
                        return fetch_data.prefix_content + f"{time_cost_str}\n\n{img_str}{upscale_str}{variation_str}"
                    except Exception as e:
                        logging.error(e)
                return fetch_data.prefix_content + \
                    f"{time_cost_str}[![{fetch_data.task_id}]({img_url})]({img_url}){upscale_str}{variation_str}"
            else:
                content = f"**任务状态:** [{(datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}] - {content}"
                content += f"\n\n花费时间：{time.time() - fetch_data.start_time:.2f} 秒"
                if status_res_json['status'] == 'IN_PROGRESS' and status_res_json.get('imageUrl'):
                    img_url = status_res_json.get('imageUrl')
                    return f"{content}\n[![{fetch_data.task_id}]({img_url})]({img_url})"
                return content
        return None

    def handle_file_upload(self, files, chatbot, language):
        """
        handle file upload
        """
        if files:
            for file in files:
                if file.name:
                    logging.info(f"尝试读取图像: {file.name}")
                    self.try_read_image(file.name)
            if self.image_path is not None:
                chatbot = chatbot + [((self.image_path,), None)]
            if self.image_bytes is not None:
                logging.info("使用图片作为输入")
        return None, chatbot, None

    def reset(self, remain_system_prompt=False):
        self.image_bytes = None
        self.image_path = None
        return super().reset()

    def get_answer_at_once(self):
        content = self.history[-1]['content']
        answer = self.get_help()

        if not content.lower().startswith("/mj"):
            return answer, len(content)

        prompt = content[3:].strip()
        action = "IMAGINE"
        first_split_index = prompt.find(self.command_splitter)
        if first_split_index > 0:
            action = prompt[:first_split_index]
        if action not in ["IMAGINE", "DESCRIBE", "UPSCALE",
                          # "VARIATION", "BLEND", "REROLL"
                          ]:
            raise Exception("任务提交失败：未知的任务类型")
        else:
            action_index = None
            action_use_task_id = None
            if action in ["VARIATION", "UPSCALE", "REROLL"]:
                action_index = int(prompt[first_split_index + 2:first_split_index + 3])
                action_use_task_id = prompt[first_split_index + 5:]

            try:
                res = None
                if action == "IMAGINE":
                    data = {
                        "prompt": prompt
                    }
                    if self.image_bytes is not None:
                        data["base64"] = 'data:image/png;base64,' + self.image_bytes
                    res = self.request_mj("submit/imagine", "POST",
                                          json.dumps(data))
                elif action == "DESCRIBE":
                    res = self.request_mj("submit/describe", "POST",
                                          json.dumps({"base64": 'data:image/png;base64,' + self.image_bytes}))
                elif action == "BLEND":
                    res = self.request_mj("submit/blend", "POST", json.dumps(
                        {"base64Array": [self.image_bytes, self.image_bytes]}))
                elif action in ["UPSCALE", "VARIATION", "REROLL"]:
                    res = self.request_mj(
                        "submit/change", "POST",
                        json.dumps({"action": action, "index": action_index, "taskId": action_use_task_id}))
                res_json = res.json()
                if not (200 <= res.status_code < 300) or (res_json['code'] not in [1, 22]):
                    answer = "任务提交失败：" + res_json.get('error', res_json.get('description', '未知错误'))
                else:
                    task_id = res_json['result']
                    prefix_content = f"**画面描述:** {prompt}\n**任务ID:** {task_id}\n"

                    fetch_data = Midjourney_Client.FetchDataPack(
                        action=action,
                        prefix_content=prefix_content,
                        task_id=task_id,
                    )
                    fetch_data.prompt = prompt
                    while not fetch_data.finished:
                        answer = self.fetch_status(fetch_data)
            except Exception as e:
                logging.error("submit failed", e)
                answer = "任务提交错误：" + str(e.args[0]) if e.args else '未知错误'

        return answer, tiktoken.get_encoding("cl100k_base").encode(content)

    def get_answer_stream_iter(self):
        content = self.history[-1]['content']
        answer = self.get_help()

        if not content.lower().startswith("/mj"):
            yield answer
            return

        prompt = content[3:].strip()
        action = "IMAGINE"
        first_split_index = prompt.find(self.command_splitter)
        if first_split_index > 0:
            action = prompt[:first_split_index]
        if action not in ["IMAGINE", "DESCRIBE", "UPSCALE",
                          "VARIATION", "BLEND", "REROLL"
                          ]:
            yield "任务提交失败：未知的任务类型"
            return

        action_index = None
        action_use_task_id = None
        if action in ["VARIATION", "UPSCALE", "REROLL"]:
            action_index = int(prompt[first_split_index + 2:first_split_index + 3])
            action_use_task_id = prompt[first_split_index + 5:]

        try:
            res = None
            if action == "IMAGINE":
                data = {
                    "prompt": prompt
                }
                if self.image_bytes is not None:
                    data["base64"] = 'data:image/png;base64,' + self.image_bytes
                res = self.request_mj("submit/imagine", "POST",
                                      json.dumps(data))
            elif action == "DESCRIBE":
                res = self.request_mj("submit/describe", "POST", json.dumps(
                    {"base64": 'data:image/png;base64,' + self.image_bytes}))
            elif action == "BLEND":
                res = self.request_mj("submit/blend", "POST", json.dumps(
                    {"base64Array": [self.image_bytes, self.image_bytes]}))
            elif action in ["UPSCALE", "VARIATION", "REROLL"]:
                res = self.request_mj(
                    "submit/change", "POST",
                    json.dumps({"action": action, "index": action_index, "taskId": action_use_task_id}))
            res_json = res.json()
            if not (200 <= res.status_code < 300) or (res_json['code'] not in [1, 22]):
                yield "任务提交失败：" + res_json.get('error', res_json.get('description', '未知错误'))
            else:
                task_id = res_json['result']
                prefix_content = f"**画面描述:** {prompt}\n**任务ID:** {task_id}\n"
                content = f"[{(datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}] - 任务提交成功：" + \
                    res_json.get('description') or '请稍等片刻'
                yield content

                fetch_data = Midjourney_Client.FetchDataPack(
                    action=action,
                    prefix_content=prefix_content,
                    task_id=task_id,
                )
                while not fetch_data.finished:
                    yield self.fetch_status(fetch_data)
        except Exception as e:
            logging.error('submit failed', e)
            yield "任务提交错误：" + str(e.args[0]) if e.args else '未知错误'

    def get_help(self):
        return """```
【绘图帮助】
所有命令都需要以 /mj 开头，如：/mj a dog
IMAGINE - 绘图，可以省略该命令，后面跟上绘图内容
    /mj a dog
    /mj IMAGINE::a cat
DESCRIBE - 描述图片，需要在右下角上传需要描述的图片内容
    /mj DESCRIBE::
UPSCALE - 确认后放大图片，第一个数值为需要放大的图片（1~4），第二参数为任务ID
    /mj UPSCALE::1::123456789
    请使用SD进行UPSCALE
VARIATION - 图片变体，第一个数值为需要放大的图片（1~4），第二参数为任务ID
    /mj VARIATION::1::123456789

【绘图参数】
所有命令默认会带上参数--v 5.2
其他参数参照 https://docs.midjourney.com/docs/parameter-list
长宽比 --aspect/--ar
    --ar 1:2
    --ar 16:9
负面tag --no
    --no plants
    --no hands
随机种子 --seed
    --seed 1
生成动漫风格（NijiJourney） --niji
    --niji
```
"""
