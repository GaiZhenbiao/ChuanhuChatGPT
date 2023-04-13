<div align="right">
  <!-- Language: -->
  <a title="Chinese" href="README.md">简体中文</a> | English
</div>

<h1 align="center">川虎 Chat 🐯 Chuanhu Chat</h1>
<div align="center">
  <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT">
    <img src="https://user-images.githubusercontent.com/70903329/227087087-93b37d64-7dc3-4738-a518-c1cf05591c8a.png" alt="Logo" height="156">
  </a>

  <p align="center">
    <h3>Provides a lightweight and easy-to-use web interface for multiple LLMs such as ChatGPT/ChatGLM/LLaMA
</h3>
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
        Real-time replies / Unlimited conversations / Saved conversations / Preset prompts / Online searching / Answering based on files <br />
        Render LaTeX / Render tables / Code highlighting / Automatic light/dark mode switching / Adaptive interface / “Clean & Simplicity” experience <br />
        Customaizable api-Host / Adjustable multiple parameters / Balanced load distribution  for multiple API Key / multiple user display / Compatible with GPT-4 / Supports local deployment of LLMs
      </p>
      <a href="https://www.bilibili.com/video/BV1mo4y1r7eE"><strong>Video tutorials</strong></a>
        ·
      <a href="https://www.bilibili.com/video/BV1184y1w7aP"><strong>Video tutorials 2.0</strong></a>
	||
      <a href="https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT"><strong>Online experience</strong></a>
      	·
      <a href="https://huggingface.co/login?next=%2Fspaces%2FJohnSmith9982%2FChuanhuChatGPT%3Fduplicate%3Dtrue"><strong>One-click deployment</strong></a>
    </p>
    <p align="center">
      <img alt="Animation Demo" src="https://user-images.githubusercontent.com/51039745/226255695-6b17ff1f-ea8d-464f-b69b-a7b6b68fffe8.gif" />
    </p>
  </p>
</div>

## Table of Contents
|[Usage tips](#使用技巧)|[Installation](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程)|[Frequently  asked questions](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题)| [Buy the author a coke 🥤](#捐款) |
|  ----  | ----  | ----  | --- |

## Tips for Usage
- Using System Prompt can effectively set the premise conditions.
- When using the Prompt template function, select the Prompt template collection file, and then choose the desired prompt from the drop-down menu.
- If the answer is unsatisfactory, you can use the `Regenerate` button to try again.
- The input box supports line breaks, press `Shift + Enter` to use.
- You can use the up and down arrows in the input box to switch between input history.
- Deploying to a server: Change the last line of the program to `demo.launch(server_name="0.0.0.0", server_port=<your port number>)`.
- To get a public link: Change the last line of the program to `demo.launch(share=True)`. Note that the program must be running before accessing the public link.
- Using on Hugging Face: It is recommended to **copy the Space** in the upper right corner before use, so that the app may respond faster.


## Installation and Usage Instructions

Please check the [wiki page](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程).

## Troubleshooting

Before looking up relevant information for various problems, you can try manually pulling the latest changes for this project and updating Gradio, then try again. The steps are as follows:

1. Click on Download ZIP on the webpage to download the latest code, or
   ```shell
   git pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f
   ```
2. Try installing the dependencies again (as this project may have introduced new dependencies)
   ```
   pip install -r requirements.txt
   pip install -r requirements_advanced.txt
   ```
3. Update gradio
   ```
   pip install gradio --upgrade --force-reinstall
   ```

Usually, this can solve the problem.

If the problem still exists, please refer to this page: [Frequently Asked Questions (FAQ)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题)

This page lists almost all the various issues you may encounter, including how to configure proxies and the steps you should take when encountering issues. Please be sure to read it carefully.

## More information

If you need more information, please see our [wiki](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki)：

- [Want to make a contribution?](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/贡献指南)
- [Project update status?](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/更新日志)
- [Secondary development license?](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可)
- [How to cite the project?](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可#如何引用该项目)

## Starchart

[![Star History Chart](https://api.star-history.com/svg?repos=GaiZhenbiao/ChuanhuChatGPT&type=Date)](https://star-history.com/#GaiZhenbiao/ChuanhuChatGPT&Date)

## Contributors

<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=GaiZhenbiao/ChuanhuChatGPT" />
</a>

## Donation

🐯 If you find this software helpful, please feel free to buy the author a coke or a cup of coffee~

<img width="250" alt="image" src="https://user-images.githubusercontent.com/51039745/226920291-e8ec0b0a-400f-4c20-ac13-dafac0c3aeeb.JPG">