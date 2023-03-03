<img width="200" alt="截屏2023-03-03 13 59 46" src="https://user-images.githubusercontent.com/51039745/222689546-7612df0e-e28b-4693-9f5f-4ef2be3daf48.png">

# 川虎 ChatGPT
为ChatGPT API提供了一个Web图形界面。

GUI for ChatGPT API
<img width="1204" alt="截屏2023-03-03 13 59 46" src="https://user-images.githubusercontent.com/51039745/222643242-c0b90a54-8f07-4fb6-b88e-ef338fd80f49.png">

## 安装方式

- 填入你的 OpenAI API 密钥

<img width="552" alt="SCR-20230302-sula" src="https://user-images.githubusercontent.com/51039745/222445258-248f2789-81d2-4f0a-8697-c720f588d8de.png">

- 安装依赖

```
pip install -r requirements.txt
```

如果报错，试试

```
pip3 install -r requirements.txt
```

如果还是不行，请先[安装Python](https://www.runoob.com/python/python-install.html)。

如果下载慢，建议[配置清华源](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)，或者科学上网。

- 启动

```
python ChuanhuChatbot.py
```

如果报错，试试

```
python3 ChuanhuChatbot.py
```

如果还是不行，请先[安装Python](https://www.runoob.com/python/python-install.html)。

## 使用Docker 安装与运行

构建镜像
```
docker build -t chuanhuchatgpt:latest .
```

一键运行
```
docker run -d --name chatgpt -e my_api_key="替换成API"  --network host chuanhuchatgpt:latest
```

查看本地访问地址
```
docker logs chatgpt
```




## 使用技巧

- 使用System Prompt可以很有效地设定前提条件
- 对于长对话，可以使用“优化Tokens”按钮减少Tokens占用。
