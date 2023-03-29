<h1 align="center">川虎 ChatGPT 🐯 Chuanhu ChatGPT</h1>
<div align="center">
  <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT">
    <img src="https://user-images.githubusercontent.com/70903329/227087087-93b37d64-7dc3-4738-a518-c1cf05591c8a.png" alt="Logo" height="156">
  </a>

  <p align="center">
    <h3>为ChatGPT API提供了一个轻快好用的Web图形界面</h3>
    <p align="center">
      <a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/blob/main/LICENSE">
        <img alt="Tests Passing" src="https://img.shields.io/github/license/GaiZhenbiao/ChuanhuChatGPT" />
      </a>
      <a href="https://gradio.app/">
        <img alt="GitHub Contributors" src="https://img.shields.io/badge/Base-Gradio-fb7d1a?style=flat" />
      </a>
      <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT/graphs/contributors">
        <img alt="GitHub Contributors" src="https://img.shields.io/github/contributors/GaiZhenBiao/ChuanhuChatGPT" />
      </a>
      <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT/issues">
        <img alt="Issues" src="https://img.shields.io/github/issues/GaiZhenBiao/ChuanhuChatGPT?color=0088ff" />
      </a>
      <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT/pulls">
        <img alt="GitHub pull requests" src="https://img.shields.io/github/issues-pr/GaiZhenBiao/ChuanhuChatGPT?color=0088ff" />
      </a>
      <p>
      	实时回复 / 无限对话 / 保存对话记录 / 预设Prompt集 / 联网搜索 / 根据文件回答
      	<br/>
      	渲染LaTex / 渲染表格 / 渲染代码 / 代码高亮 / 自定义api-URL / “小而美”的体验 / Ready for GPT-4
      </p>
      <a href="https://www.bilibili.com/video/BV1mo4y1r7eE"><strong>视频教程</strong></a>
        ·
      <a href="https://www.bilibili.com/video/BV1184y1w7aP"><strong>2.0介绍视频</strong></a>
	||
      <a href="https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT"><strong>在线体验</strong></a>
      	·
      <a href="https://huggingface.co/login?next=%2Fspaces%2FJohnSmith9982%2FChuanhuChatGPT%3Fduplicate%3Dtrue"><strong>一键部署</strong></a>
    </p>
    <p align="center">
      <img alt="Animation Demo" src="https://user-images.githubusercontent.com/51039745/226255695-6b17ff1f-ea8d-464f-b69b-a7b6b68fffe8.gif" />
    </p>
  </p>
</div>

## 目录
|[使用技巧](#使用技巧)|[安装方式](#安装方式)|[疑难杂症解决](#疑难杂症解决)| [给作者买可乐🥤](#捐款) |
|  ----  | ----  | ----  | --- |

## 使用技巧

- 使用System Prompt可以很有效地设定前提条件。
- 使用Prompt模板功能时，选择Prompt模板集合文件，然后从下拉菜单中选择想要的prompt。
- 如果回答不满意，可以使用`重新生成`按钮再试一次
- 对于长对话，可以使用`优化Tokens`按钮减少Tokens占用。
- 输入框支持换行，按`shift enter`即可。
- 部署到服务器：将程序最后一句改成`demo.launch(server_name="0.0.0.0", server_port=<你的端口号>)`。
- 获取公共链接：将程序最后一句改成`demo.launch(share=True)`。注意程序必须在运行，才能通过公共链接访问。
- 在Hugging Face上使用：建议在右上角 **复制Space** 再使用，这样App反应可能会快一点。


## 安装方式

### 直接在Hugging Face上部署

访问[本项目的Hugging Face页面](https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT)，点击右上角的 **Duplicate Space** （复制空间），新建一个私人空间。然后就直接可以开始使用啦！放心，这是免费的。

您可以直接使用我的空间，这样能实时享受到最新功能。您也可以将项目复制为私人空间里使用，这样App反应可能会快一点。

 <img width="300" alt="image" src="https://user-images.githubusercontent.com/51039745/223447310-e098a1f2-0dcf-48d6-bcc5-49472dd7ca0d.png">

 Hugging Face的优点：免费，无需配置代理，部署容易（甚至不需要电脑）。

 Hugging Face的缺点：不支持某些界面样式。

### 手动本地部署

1. **下载本项目**

	```shell
	git clone https://github.com/GaiZhenbiao/ChuanhuChatGPT.git
	cd ChuanhuChatGPT
	```
	或者，点击网页右上角的 `Download ZIP`，下载并解压完成后进入文件夹，进入`终端`或`命令提示符`。

	如果你使用Windows，应该在文件夹里按住`shift`右键，选择“在终端中打开”。如果没有这个选项，选择“在此处打开Powershell窗口”。如果你使用macOS，可以在Finder底部的路径栏中右键当前文件夹，选择`服务-新建位于文件夹位置的终端标签页`。

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

	在`auth.json`中填写你的用户名和密码，支持多用户。格式如下：

	```
	{
		"user1": {
			"username": "用户名",
			"password": "密码"
		}
	}
	```

	</details>

3. **安装依赖**

	在终端中输入下面的命令，然后回车。

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

	请使用下面的命令。

	```shell
	python ChuanhuChatbot.py
	```

	如果报错，试试

	```shell
	python3 ChuanhuChatbot.py
	```

	如果还是不行，请先[安装Python](https://www.runoob.com/python/python-install.html)。
<br />

5. **（可选）填写自定义的API地址**

	只需要填写到域名，例如：`https://yourdomain.com`（此地址仅作举例，并非真实地址，请勿使用！）。

	同样，以下3种方法任选其一：

	<details><summary>1. 在图形界面中填写你的API地址</summary>

	这样设置的API地址会在页面刷新后被清除。

	在`川虎ChatGPT网页`->`高级`->`网络参数`->`API地址中填写`

	</details>

	<details><summary>2. 在直接代码中填入你的代理地址</summary>

	这样设置的API地址会成为默认地址，修改代码中的`my_api_url`变量，将其改为你自己的地址。

	</details>

	<details><summary>3. 在文件中设定默认代理地址</summary>

	这样设置的API地址可以在拉取项目更新之后保留。

	在项目文件夹中新建文件：`api_url.txt`。

	在`api_url.txt`中填写你的自定义API地址，注意不要填写任何无关内容。

	**重要！！！**：不要使用别人提供的第三方API地址，他人可以在代理服务器上获取你的API Key！

	这里提供一些搭建自定义API地址的建议：

	- 在服务器上使用Nginx做反向代理
	- 使用Cloud Flare的Worker功能反向代理，参考[这篇文章](https://github.com/noobnooc/noobnooc/discussions/9)。

	</details>


6. **（可选）填写自定义的代理地址**

	同样，以下3种方法任选其一：

	<details><summary>1. 在图形界面中填写你的代理地址</summary>

	这样设置的代理地址会在页面刷新后被清除。

	在`川虎ChatGPT网页`->`高级`->`网络参数`->`代理地址中填写`

	</details>

	<details><summary>2. 在直接代码中填入你的API地址</summary>

	这样设置的代理地址会成为默认地址，修改代码中的`my_proxy_url`变量，将其改为你自己的地址。

	</details>

	<details><summary>3. 在文件中设定默认API地址</summary>

	这样设置的API地址可以在拉取项目更新之后保留。

	在项目文件夹中新建文件：`proxy.txt`。

	在`proxy.txt`中填写你的自定义代理地址，注意不要填写任何无关内容。

	</details>

如果一切顺利，现在，你应该已经可以在浏览器地址栏中输入 [`http://localhost:7860`](http://localhost:7860) 查看并使用 ChuanhuChatGPT 了。

**如果你在安装过程中碰到了问题，请先查看[疑难杂症解决](#疑难杂症解决)部分。**

### 自动更新

你可以通过本项目提供的脚本检测仓库是否有更新，如果有，则拉取最新脚本、安装依赖、重启服务器。此功能支持`Linux`和`macOS`系统。

如果你想运行，只需要运行`run_Linux.sh`或者`run_macOS.command`。如果你还想保持最新版本，只需要定时运行脚本。例如，在crontab中加入下面的内容：

```
*/20 * * * * /path/to/ChuanhuChatGPT/run_Linux.sh
```
就可以每20分钟检查一次脚本更新，如果有更新，则自动拉取并重启服务器。

### 使用Docker运行

<details><summary>如果觉得以上方法比较麻烦，我们提供了Docker镜像</summary>

#### 拉取镜像

```shell
docker pull tuchuanhuhuhu/chuanhuchatgpt:latest
```

#### 运行

```shell
docker run -d --name chatgpt \
	-e my_api_key="替换成API" \
	-e USERNAME="替换成用户名" \
	-e PASSWORD="替换成密码" \
	-v ~/chatGPThistory:/app/history \
	-p 7860:7860 \
	tuchuanhuhuhu/chuanhuchatgpt:latest
```

注：`USERNAME` 和 `PASSWORD` 两行可省略。若省略则不会启用认证。

#### 查看运行状态
```shell
docker logs chatgpt
```

#### 也可修改脚本后手动构建镜像

```shell
docker build -t chuanhuchatgpt:latest .
```
</details>


### 远程部署

<details><summary>如果需要在公网服务器部署本项目，请阅读该部分</summary>

#### 部署到公网服务器

将最后一句修改为

```
demo.queue().launch(server_name="0.0.0.0", server_port=7860, share=False) # 可自定义端口
```
#### 用账号密码保护页面

将最后一句修改为

```
demo.queue().launch(server_name="0.0.0.0", server_port=7860,auth=("在这里填写用户名", "在这里填写密码")) # 可设置用户名与密码
```

#### 配置 Nginx 反向代理

注意：配置反向代理不是必须的。如果需要使用域名，则需要配置 Nginx 反向代理。

又及：目前配置认证后，Nginx 必须配置 SSL，否则会出现 [Cookie 不匹配问题](https://github.com/GaiZhenbiao/ChuanhuChatGPT/issues/89)。

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

为了同时配置域名访问和身份认证，需要配置SSL的证书，可以参考[这篇博客](https://www.gzblog.tech/2020/12/25/how-to-config-hexo/#%E9%85%8D%E7%BD%AEHTTPS)一键配置


#### 全程使用Docker 为ChuanhuChatGPT 开启HTTPS

如果你的VPS 80端口与443端口没有被占用，则可以考虑如下的方法，只需要将你的域名提前绑定到你的VPS 的IP即可。此方法由[@iskoldt-X](https://github.com/iskoldt-X) 提供。

首先，运行[nginx-proxy](https://github.com/nginx-proxy/nginx-proxy)

```
docker run --detach \
    --name nginx-proxy \
    --publish 80:80 \
    --publish 443:443 \
    --volume certs:/etc/nginx/certs \
    --volume vhost:/etc/nginx/vhost.d \
    --volume html:/usr/share/nginx/html \
    --volume /var/run/docker.sock:/tmp/docker.sock:ro \
    nginxproxy/nginx-proxy
```
接着，运行[acme-companion](https://github.com/nginx-proxy/acme-companion)，这是用来自动申请TLS 证书的容器

```
docker run --detach \
    --name nginx-proxy-acme \
    --volumes-from nginx-proxy \
    --volume /var/run/docker.sock:/var/run/docker.sock:ro \
    --volume acme:/etc/acme.sh \
    --env "DEFAULT_EMAIL=你的邮箱（用于申请TLS 证书）" \
    nginxproxy/acme-companion
```

最后，可以运行ChuanhuChatGPT
```
docker run -d --name chatgpt \
	-e my_api_key="你的API" \
	-e USERNAME="替换成用户名" \
	-e PASSWORD="替换成密码" \
	-v ~/chatGPThistory:/app/history \
	-e VIRTUAL_HOST=你的域名 \
	-e VIRTUAL_PORT=7860 \
	-e LETSENCRYPT_HOST=你的域名 \
	tuchuanhuhuhu/chuanhuchatgpt:latest
```
如此即可为ChuanhuChatGPT实现自动申请TLS证书并且开启HTTPS
</details>

---

## 疑难杂症解决

在遇到各种问题查阅相关信息前，您可以先尝试手动拉取本项目的最新更改并更新 gradio，然后重试。步骤为：

1. 点击网页上的 `Download ZIP` 下载最新代码，或
   ```shell
   git pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f
   ```
2. 尝试再次安装依赖（可能本项目引入了新的依赖）
   ```
   pip install -r requirements.txt
   ```
3. 更新gradio
   ```
   pip install gradio --upgrade --force-reinstall
   ```

很多时候，这样就可以解决问题。

如果问题仍然存在，请查阅该页面：[常见问题](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题)

该页面列出了**几乎所有**您可能遇到的各种问题，包括如何配置代理，以及遇到问题后您该采取的措施，**请务必认真阅读**。

## Starchart

[![Star History Chart](https://api.star-history.com/svg?repos=GaiZhenbiao/ChuanhuChatGPT&type=Date)](https://star-history.com/#GaiZhenbiao/ChuanhuChatGPT&Date)

## Contributors

<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=GaiZhenbiao/ChuanhuChatGPT" />
</a>

## 捐款

🐯如果觉得这个软件对你有所帮助，欢迎请作者喝可乐、喝咖啡～

<img width="250" alt="image" src="https://user-images.githubusercontent.com/51039745/226920291-e8ec0b0a-400f-4c20-ac13-dafac0c3aeeb.JPG">
