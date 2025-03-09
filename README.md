<div align="right">
  <!-- 语言: -->
  简体中文 | <a title="English" href="./readme/README_en.md">English</a> | <a title="Japanese" href="./readme/README_ja.md">日本語</a> | <a title="Russian" href="./readme/README_ru.md">Russian</a> | <a title="Korean" href="./readme/README_ko.md">한국어</a>
</div>

<h1 align="center">川虎 Chat 🐯 Chuanhu Chat</h1>
<div align="center">
  <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT">
    <img src="https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/aca3a7ec-4f1d-4667-890c-a6f47bf08f63" alt="Logo" height="156">
  </a>

<p align="center">
    <h3>为ChatGPT等多种LLM提供了一个轻快好用的Web图形界面和众多附加功能</h3>
    <p align="center">
      <a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/blob/main/LICENSE">
        <img alt="Tests Passing" src="https://img.shields.io/github/license/GaiZhenbiao/ChuanhuChatGPT" />
      </a>
      <a href="https://gradio.app/">
        <img alt="GitHub Contributors" src="https://img.shields.io/badge/Base-Gradio-fb7d1a?style=flat" />
      </a>
      <a href="https://t.me/tkdifferent">
        <img alt="GitHub pull requests" src="https://img.shields.io/badge/Telegram-Group-blue.svg?logo=telegram" />
      </a>
      <p>
        支持 DeepSeek R1 & GPT 4 · 基于文件问答 · LLM本地部署 · 联网搜索 · Agent 助理 ·  支持 Fine-tune
      </p>
      <a href="https://www.bilibili.com/video/BV1mo4y1r7eE"><strong>视频教程</strong></a>
        ·
      <a href="https://www.bilibili.com/video/BV1184y1w7aP"><strong>2.0介绍视频</strong></a>
	||
      <a href="https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT"><strong>在线体验</strong></a>
      	·
      <a href="https://huggingface.co/login?next=%2Fspaces%2FJohnSmith9982%2FChuanhuChatGPT%3Fduplicate%3Dtrue"><strong>一键部署</strong></a>
    </p>
  </p>
</div>

[![Video Title](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7.jpg)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7?autoplay=1)

## 目录

| [支持模型](#支持模型) | [使用技巧](#使用技巧) | [安装方式](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程) | [常见问题](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题) | [给作者买可乐🥤](#捐款) | [加入Telegram群组](https://t.me/tkdifferent) |
| --- | --- | --- | --- | --- | --- |

## ✨ 5.0 重磅更新！

![ChuanhuChat5更新](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/f2c2be3a-ea93-4edf-8221-94eddd4a0178)


<sup>New!</sup> 全新的用户界面！精致得不像 Gradio，甚至有毛玻璃效果！

<sup>New!</sup> 适配了移动端（包括全面屏手机的挖孔/刘海），层级更加清晰。

<sup>New!</sup> 历史记录移到左侧，使用更加方便。并且支持搜索（支持正则）、删除、重命名。

<sup>New!</sup> 现在可以让大模型自动命名历史记录（需在设置或配置文件中开启）。

<sup>New!</sup> 现在可以将 川虎Chat 作为 PWA 应用程序安装，体验更加原生！支持 Chrome/Edge/Safari 等浏览器。

<sup>New!</sup> 图标适配各个平台，看起来更舒服。

<sup>New!</sup> 支持 Finetune（微调） GPT 3.5！


## 支持模型

| API 调用模型 | 备注 | 本地部署模型 | 备注 |
| :---: | --- | :---: | --- |
| [ChatGPT(GPT-4、GPT-4o、o1)](https://chat.openai.com) | 支持微调 gpt-3.5 | [ChatGLM](https://github.com/THUDM/ChatGLM-6B) ([ChatGLM2](https://github.com/THUDM/ChatGLM2-6B)) ([ChatGLM3](https://huggingface.co/THUDM/chatglm3-6b)) ||
| [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service) |  | [LLaMA](https://github.com/facebookresearch/llama) | 支持 Lora 模型 |
| [Google Gemini Pro](https://ai.google.dev/gemini-api/docs/api-key?hl=zh-cn) |  | [StableLM](https://github.com/Stability-AI/StableLM) ||
| [讯飞星火认知大模型](https://xinghuo.xfyun.cn) |  | [MOSS](https://github.com/OpenLMLab/MOSS) ||
| [Inspur Yuan 1.0](https://air.inspur.com/home) |  | [通义千问](https://github.com/QwenLM/Qwen/tree/main) ||
| [MiniMax](https://api.minimax.chat/) ||[DeepSeek](https://platform.deepseek.com)||
| [XMChat](https://github.com/MILVLG/xmchat) | 不支持流式传输|||
| [Midjourney](https://www.midjourney.com/) | 不支持流式传输|||
| [Claude](https://www.anthropic.com/) | ✨ 现已支持Claude 3 Opus、Sonnet，Haiku将会在推出后的第一时间支持|||
| DALL·E 3 ||||

## 使用技巧

### 💪 强力功能
- **川虎助理**：类似 AutoGPT，全自动解决你的问题；
- **在线搜索**：ChatGPT 的数据太旧？给 LLM 插上网络的翅膀；
- **知识库**：让 ChatGPT 帮你量子速读！根据文件回答问题。
- **本地部署LLM**：一键部署，获取属于你自己的大语言模型。
- **GPT 3.5微调**：支持微调 GPT 3.5，让 ChatGPT 更加个性化。
- **[自定义模型](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/%E8%87%AA%E5%AE%9A%E4%B9%89%E6%A8%A1%E5%9E%8B-Custom-Models)**：灵活地自定义模型，例如对接本地推理服务。

### 🤖 System Prompt
- 通过 System Prompt 设定前提条件，可以很有效地进行角色扮演；
- 川虎Chat 预设了Prompt模板，点击`加载Prompt模板`，先选择 Prompt 模板集合，然后在下方选择想要的 Prompt。

### 💬 基础对话
- 如果回答不满意，可以使用 `重新生成` 按钮再试一次，或者直接 `删除这轮对话`;
- 输入框支持换行，按 <kbd>Shift</kbd> + <kbd>Enter</kbd>即可；
- 在输入框按 <kbd>↑</kbd> <kbd>↓</kbd> 方向键，可以在发送记录中快速切换；
- 每次新建一个对话太麻烦，试试 `单论对话` 功能；
- 回答气泡旁边的小按钮，不仅能 `一键复制`，还能 `查看Markdown原文`；
- 指定回答语言，让 ChatGPT 固定以某种语言回答。

### 📜 对话历史
- 对话历史记录会被自动保存，不用担心问完之后找不到了；
- 多用户历史记录隔离，除了你都看不到；
- 重命名历史记录，方便日后查找；
- <sup>New!</sup> 魔法般自动命名历史记录，让 LLM 理解对话内容，帮你自动为历史记录命名！
- <sup>New!</sup> 搜索历史记录，支持正则表达式！

### 🖼️ 小而美的体验
- 自研 Small-and-Beautiful 主题，带给你小而美的体验；
- 自动亮暗色切换，给你从早到晚的舒适体验；
- 完美渲染 LaTeX / 表格 / 代码块，支持代码高亮；
- <sup>New!</sup> 非线性动画、毛玻璃效果，精致得不像 Gradio！
- <sup>New!</sup> 适配 Windows / macOS / Linux / iOS / Android，从图标到全面屏适配，给你最合适的体验！
- <sup>New!</sup> 支持以 PWA应用程序 安装，体验更加原生！

### 👨‍💻 极客功能
- <sup>New!</sup> 支持 Fine-tune（微调）gpt-3.5！
- 大量 LLM 参数可调；
- 支持更换 api-host；
- 支持自定义代理；
- 支持多 api-key 负载均衡。

### ⚒️ 部署相关
- 部署到服务器：在 `config.json` 中设置 `"server_name": "0.0.0.0", "server_port": <你的端口号>,`。
- 获取公共链接：在 `config.json` 中设置 `"share": true,`。注意程序必须在运行，才能通过公共链接访问。
- 在Hugging Face上使用：建议在右上角 **复制Space** 再使用，这样App反应可能会快一点。

## 快速上手

在终端执行以下命令：

```shell
git clone https://github.com/GaiZhenbiao/ChuanhuChatGPT.git
cd ChuanhuChatGPT
pip install -r requirements.txt
```

然后，在项目文件夹中复制一份 `config_example.json`，并将其重命名为 `config.json`，在其中填入 `API-Key` 等设置。

```shell
python ChuanhuChatbot.py
```

一个浏览器窗口将会自动打开，此时您将可以使用 **川虎Chat** 与ChatGPT或其他模型进行对话。

> **Note**
>
> 具体详尽的安装教程和使用教程请查看[本项目的wiki页面](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程)。

## 疑难杂症解决

在遇到各种问题查阅相关信息前，您可以先尝试 **手动拉取本项目的最新更改<sup>1</sup>** 并 **更新依赖库<sup>2</sup>**，然后重试。步骤为：

1. 点击网页上的 `Download ZIP` 按钮，下载最新代码并解压覆盖，或
   ```shell
   git pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f
   ```
2. 尝试再次安装依赖（可能本项目引入了新的依赖）
   ```
   pip install -r requirements.txt
   ```

很多时候，这样就可以解决问题。

如果问题仍然存在，请查阅该页面：[常见问题](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题)

该页面列出了**几乎所有**您可能遇到的各种问题，包括如何配置代理，以及遇到问题后您该采取的措施，**请务必认真阅读**。

## 了解更多

若需了解更多信息，请查看我们的 [wiki](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki)：

- [想要做出贡献？](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/贡献指南)
- [项目更新情况？](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/更新日志)
- [二次开发许可？](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可)
- [如何引用项目？](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可#如何引用该项目)

## Starchart

[![Star History Chart](https://api.star-history.com/svg?repos=GaiZhenbiao/ChuanhuChatGPT&type=Date)](https://star-history.com/#GaiZhenbiao/ChuanhuChatGPT&Date)

## Contributors

<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=GaiZhenbiao/ChuanhuChatGPT" />
</a>

## 捐款

🐯如果觉得这个软件对你有所帮助，欢迎请作者喝可乐、喝咖啡～

联系作者：请去[我的bilibili账号](https://space.bilibili.com/29125536)私信我。

<a href="https://www.buymeacoffee.com/ChuanhuChat" ><img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=ChuanhuChat&button_colour=219d53&font_colour=ffffff&font_family=Poppins&outline_colour=ffffff&coffee_colour=FFDD00" alt="Buy Me A Coffee" width="250"></a>

<img width="250" alt="image" src="https://user-images.githubusercontent.com/51039745/226920291-e8ec0b0a-400f-4c20-ac13-dafac0c3aeeb.JPG">
