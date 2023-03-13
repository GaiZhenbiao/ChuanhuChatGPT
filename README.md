<img height="128" align="left" src="https://user-images.githubusercontent.com/51039745/222689546-7612df0e-e28b-4693-9f5f-4ef2be3daf48.png" alt="Logo">

# 川虎 ChatGPT 🐯 Chuanhu ChatGPT

[![LICENSE](https://img.shields.io/github/license/GaiZhenbiao/ChuanhuChatGPT)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/blob/main/LICENSE)
[![Base](https://img.shields.io/badge/Base-Gradio-fb7d1a?style=flat)](https://gradio.app/)
[![Bilibili](https://img.shields.io/badge/Bilibili-%E8%A7%86%E9%A2%91%E6%95%99%E7%A8%8B-ff69b4?style=flat&logo=bilibili)](https://www.bilibili.com/video/BV1mo4y1r7eE)

---

为ChatGPT API提供了一个Web图形界面。在Bilibili上[观看视频教程](https://www.bilibili.com/video/BV1mo4y1r7eE/)。也可以在Hugging Face上[在线体验](https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT)。

![Animation Demo](https://user-images.githubusercontent.com/51039745/223148794-f4fd2fcb-3e48-4cdf-a759-7aa463d3f14c.gif)


## 重大更新 🎉🎉🎉

- 像官方ChatGPT那样实时回复
- 无限长度对话
- 改进的保存/加载功能
- 从Prompt模板中选择预设
- 将大段代码显示在代码块中
- 渲染输出中的LaTex公式

## 目录
|[功能](#功能)|[使用技巧](#使用技巧)|[安装方式](#安装方式)|[疑难杂症解决](#疑难杂症解决)|
|  ----  | ----  | ----  | ----  |


## 功能
- [x] 像官方客户端那样支持实时显示回答！
- [x] 重试对话，让ChatGPT再回答一次。
- [x] 优化Tokens，减少Tokens占用，以支持更长的对话。
- [x] 设置System Prompt，有效地设定前置条件
- [x] 保存/加载对话历史记录
- [x] 在图形界面中添加API key
- [x] System Prompt模板功能，从预置的Prompt库中选择System Prompt
- [x] 实时显示Tokens用量

## 使用技巧

- 使用System Prompt可以很有效地设定前提条件
- 对于长对话，可以使用“优化Tokens”按钮减少Tokens占用。
- 如果部署到服务器，将程序最后一句改成`demo.launch(server_name="0.0.0.0", server_port=99999)`。其中`99999`是端口号，应该是1000-65535任意可用端口，请自行更改为实际端口号。
- 如果需要获取公共链接，将程序最后一句改成`demo.launch(share=True)`。注意程序必须在运行，才能通过公共链接访问
- 使用Prompt模板功能时，请先选择模板文件（`.csv`），然后点击载入按钮，然后就可以从下拉菜单中选择想要的prompt了，点击应用填入System Prmpt
- 输入框支持换行，按`shift enter`即可
- 在Hugging Face上使用时，建议在右上角**复制Space**再使用，这样能大大减少排队时间，App反应也会更加迅速。
  <img width="300" alt="image" src="https://user-images.githubusercontent.com/51039745/223447310-e098a1f2-0dcf-48d6-bcc5-49472dd7ca0d.png">

## 安装方式

### 本地部署

1. **下载本项目**

	```shell
	git clone https://github.com/GaiZhenbiao/ChuanhuChatGPT.git
	cd ChuanhuChatGPT
	```
	或者，点击网页右上角的 `Download ZIP`，下载并解压完成后进入文件夹，进入`终端`或`命令提示符`。

	<img width="200" alt="downloadZIP" src="https://user-images.githubusercontent.com/23137268/223696317-b89d2c71-c74d-4c6d-8060-a21406cfb8c8.png">

2. **填写API密钥**

	以下3种方法任选其一：

	<details><summary>1. 在图形界面中填写你的API密钥</summary>

	这样设置的密钥会在页面刷新后被清除。

	<img width="760" alt="image" src="https://user-images.githubusercontent.com/51039745/222873756-3858bb82-30b9-49bc-9019-36e378ee624d.png"></details>
	<details><summary>2. 在直接代码中填入你的 OpenAI API 密钥</summary>

	这样设置的密钥会成为默认密钥。在这里还可以选择是否在UI中隐藏密钥输入框。

	<img width="525" alt="image" src="https://user-images.githubusercontent.com/51039745/223440375-d472de4b-aa7f-4eae-9170-6dc2ed9f5480.png"></details>

	<details><summary>3. 在文件中设定默认密钥、用户名密码</summary>

	这样设置的密钥可以在拉取项目更新之后保留。
	
	在项目文件夹中新建这两个文件：`api_key.txt` 和 `auth.json`。

	在`api_key.txt`中填写你的API-Key，注意不要填写任何无关内容。

	在`auth.json`中填写你的用户名和密码。

	```
	{
    "username": "用户名",
    "password": "密码"
	}
	```

	</details>

3. **安装依赖**

	```shell
	pip install -r requirements.txt
	```

	如果报错，试试

	```shell
	pip3 install -r requirements.txt
	```

	如果还是不行，请先[安装Python](https://www.runoob.com/python/python-install.html)。

	如果下载慢，建议[配置清华源](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)，或者科学上网。

4. **启动**

	```shell
	python ChuanhuChatbot.py
	```

	如果报错，试试

	```shell
	python3 ChuanhuChatbot.py
	```

	如果还是不行，请先[安装Python](https://www.runoob.com/python/python-install.html)。
<br />

如果一切顺利，现在，你应该已经可以在浏览器地址栏中输入 [`http://localhost:7860`](http://localhost:7860) 查看并使用 ChuanhuChatGPT 了。

**如果你在安装过程中碰到了问题，请先查看[疑难杂症解决](#疑难杂症解决)部分。**

<details><summary><h3>或者，使用Docker 运行</h3></summary>

#### 拉取镜像

```shell
docker pull tuchuanhuhuhu/chuanhuchatgpt:latest
```

#### 运行

```shell
docker run -d --name chatgpt \
	-e my_api_key="替换成API" \
	-v ~/chatGPThistory:/app/history \
	-p 7860:7860 \
	tuchuanhuhuhu/chuanhuchatgpt:latest
```

#### 查看运行状态
```shell
docker logs chatgpt
```

#### 也可修改脚本后手动构建镜像

```shell
docker build -t chuanhuchatgpt:latest .
```
</details>


## 部署相关

<details><summary>如果需要在公网服务器部署本项目，可以阅读本部分。</summary>

### 部署到公网服务器

将最后一句修改为

```
demo.queue().launch(server_name="0.0.0.0", server_port=7860, share=False) # 可自定义端口
```
### 用账号密码保护页面

将最后一句修改为

```
demo.queue().launch(server_name="0.0.0.0", server_port=7860,auth=("在这里填写用户名", "在这里填写密码")) # 可设置用户名与密码
```

### 如果你想用域名访问，可以配置Nginx反向代理

添加独立配置文件：
```nginx
server {
	listen 80;
	server_name /域名/;   # 请填入你设定的域名
	access_log off;
	error_log off;
	location / {
		proxy_pass http://127.0.0.1:7860;   # 注意端口号
		proxy_redirect off;
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header Upgrade $http_upgrade;		# Websocket配置
		proxy_set_header Connection $connection_upgrade;		#Websocket配置
		proxy_max_temp_file_size 0;
		client_max_body_size 10m;
		client_body_buffer_size 128k;
		proxy_connect_timeout 90;
		proxy_send_timeout 90;
		proxy_read_timeout 90;
		proxy_buffer_size 4k;
		proxy_buffers 4 32k;
		proxy_busy_buffers_size 64k;
		proxy_temp_file_write_size 64k;
	}
}
```

修改`nginx.conf`配置文件（通常在`/etc/nginx/nginx.conf`），向http部分添加如下配置：
（这一步是为了配置websocket连接，如之前配置过可忽略）
```nginx
map $http_upgrade $connection_upgrade {
  default upgrade;
  ''      close;
  }
```

</details>

## 疑难杂症解决

首先，请尝试拉取本项目的最新更改，使用最新的代码重试。

点击网页上的 `Download ZIP` 下载最新代码，或
```shell
git pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f
```

如果还有问题，可以再尝试重装 gradio:

```
pip install gradio --upgrade --force-reinstall
```

很多时候，这样就可以解决问题。

<details><summary><h3><code>No module named '_bz2'</code></h3></summary>

> 部署在CentOS7.6,Python3.11.0上,最后报错ModuleNotFoundError: No module named '_bz2'

安装python前先下载 `bzip` 编译环境

```
sudo yum install bzip2-devel
```
</details>

<details><summary><h3><code>openai.error.APIConnectionError</code></h3></summary>

> 如果有人也出现了`openai.error.APIConnectionError`提示的报错，那可能是`urllib3`的版本导致的。`urllib3`版本大于`1.25.11`，就会出现这个问题。
>
> 解决方案是卸载`urllib3`然后重装至`1.25.11`版本再重新运行一遍就可以

参见：[#5](https://github.com/GaiZhenbiao/ChuanhuChatGPT/issues/5)

在终端或命令提示符中卸载`urllib3`

```
pip uninstall urllib3
```

然后，通过使用指定版本号的`pip install`命令来安装所需的版本：

```
pip install urllib3==1.25.11
```

参考自：
[解决OpenAI API 挂了代理还是连接不上的问题](https://zhuanlan.zhihu.com/p/611080662)
</details>

<details><summary><h3>在 Python 文件里 设定 API Key 之后验证失败</h3></summary>

> 在ChuanhuChatbot.py中设置APIkey后验证出错，提示“发生了未知错误Orz”

参见：[#26](https://github.com/GaiZhenbiao/ChuanhuChatGPT/issues/26)
</details>

<details><summary><h3>一直等待/SSL Error</h3></summary>

> 更新脚本文件后，SSLError [#49](https://github.com/GaiZhenbiao/ChuanhuChatGPT/issues/49)
>
> 跑起来之后，输入问题好像就没反应了，也没报错 [#25](https://github.com/GaiZhenbiao/ChuanhuChatGPT/issues/25)
>
> ```
> requests.exceptions.SSLError: HTTPSConnectionPool(host='api.openai.com', port=443): Max retries exceeded with url: /v1/chat/completions (Caused by SSLError(SSLEOFError(8, 'EOF occurred in violation of protocol (_ssl.c:1129)')))
> ```

请将`openai.com`加入你使用的代理App的代理规则。注意不要将`127.0.0.1`加入代理，否则会有下一个错误。

例如，在Clash配置文件中，加入：

```
rule-providers:
  private:
    type: http
    behavior: domain
    url: "https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release/lancidr.txt"
    path: ./ruleset/ads.yaml
    interval: 86400

rules:
 - RULE-SET,private,DIRECT
 - DOMAIN-SUFFIX,openai.com,你的代理规则
```

Surge：

```
[Rule]
DOMAIN-SET,https://cdn.jsdelivr.net/gh/Loyalsoldier/surge-rules@release/private.txt,DIRECT
DOMAIN-SUFFIX,openai.com,你的代理规则
```
</details>

<details><summary><h3>网页提示错误 Something went wrong</h3></summary>

> ```
> Something went wrong
> Expecting value: 1ine 1 column 1 (char o)
> ```

出现这个错误的原因是`127.0.0.1`被代理了，导致网页无法和后端通信。请设置代理软件，将`127.0.0.1`加入直连。
</details>

<details><summary><h3><code>No matching distribution found for openai>=0.27.0</code></h3></summary>

`openai`这个依赖已经被移除了。请尝试下载最新版脚本。
</details>

## Starchart

[![Star History Chart](https://api.star-history.com/svg?repos=GaiZhenbiao/ChuanhuChatGPT&type=Date)](https://star-history.com/#GaiZhenbiao/ChuanhuChatGPT&Date)

## Contributors

<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=GaiZhenbiao/ChuanhuChatGPT" />
</a>

## 捐款

🐯请作者喝可乐～

<img width="350" alt="image" src="https://user-images.githubusercontent.com/51039745/223626874-f471e5f5-8a06-43d5-aa31-9d2575b6f631.JPG">
