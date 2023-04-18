<div align="right">
  <!-- Language: -->
  <a title="Chinese" href="../README.md">简体中文</a> | English | <a title="Japanese" href="README_ja.md">日本語</a>
</div>

<h1 align="center">川虎 Chat 🐯 Chuanhu Chat</h1>
<div align="center">
  <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT">
    <img src="https://user-images.githubusercontent.com/70903329/227087087-93b37d64-7dc3-4738-a518-c1cf05591c8a.png" alt="Logo" height="156">
  </a>

<p align="center">
    <h3>Lightweight and User-friendly Web-UI for LLMs including ChatGPT/ChatGLM/LLaMA</h3>
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
        Streaming / Unlimited conversations / Save history / Preset prompts / Chat with files / Web search <br />
        LaTeX rendering / Table rendering / Code highlighting <br />
        Auto dark mode / Adaptive web interface / WeChat-like theme <br />
        Multi-parameters tuning / Multi-API-Key support / Multi-user support <br />
        Compatible with GPT-4 / Local deployment for LLMs
      </p>
      <a href="https://www.youtube.com/watch?v=MtxS4XZWbJE"><strong>Video Tutorial</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=77nw7iimYDE"><strong>2.0 Introduction</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=x-O1jjBqgu4"><strong>3.0 Introduction & Tutorial</strong></a>
	||
      <a href="https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT"><strong>Online trial</strong></a>
      	·
      <a href="https://huggingface.co/login?next=%2Fspaces%2FJohnSmith9982%2FChuanhuChatGPT%3Fduplicate%3Dtrue"><strong>One-Click deployment</strong></a>
    </p>
    <p align="center">
      <img alt="Animation Demo" src="https://user-images.githubusercontent.com/51039745/226255695-6b17ff1f-ea8d-464f-b69b-a7b6b68fffe8.gif" />
    </p>
  </p>
</div>

## Usage Tips

- To better control the ChatGPT, use System Prompt.
- To use a Prompt Template, select the Prompt Template Collection file first, and then choose certain prompt from the drop-down menu.
- To try again if the response is unsatisfactory, use `🔄 Regenerate` button.
- To start a new line in the input box, press <kbd>Shift</kbd> + <kbd>Enter</kbd> keys.
- To quickly switch between input history, press <kbd>↑</kbd> and <kbd>↓</kbd> key in the input box.
- To deploy the program onto a server, change the last line of the program to `demo.launch(server_name="0.0.0.0", server_port=<your port number>)`.
- To get a public shared link, change the last line of the program to `demo.launch(share=True)`. Please be noted that the program must be running in order to be accessed via a public link.
- To use it in Hugging Face Spaces: It is recommended to **Duplicate Space** and run the program in your own Space for a faster and more secure experience.

## Installation

```shell
git clone https://github.com/GaiZhenbiao/ChuanhuChatGPT.git
cd ChuanhuChatGPT
pip install -r requirements.txt
```

Then make a copy of `config_example.json`, rename it to `config.json`, and then fill in your API-Key and other settings in the file.

```shell
python ChuanhuChatbot.py
```

A browser window will open and you will be able to chat with ChatGPT.

> **Note**
>
> Please check our [wiki page](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程) for detailed instructions.

## Troubleshooting

When you encounter problems, you should try manually pulling the latest changes of this project first. The steps are as follows:

1. Download the latest code archive by clicking on `Download ZIP` on the webpage, or
   ```shell
   git pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f
   ```
2. Try installing the dependencies again (as this project may have introduced new dependencies)
   ```
   pip install -r requirements.txt
   ```
3. Update Gradio
   ```
   pip install gradio --upgrade --force-reinstall
   ```

Generally, you can solve most problems by following these steps.

If the problem still exists, please refer to this page: [Frequently Asked Questions (FAQ)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题)

This page lists almost all the possible problems and solutions. Please read it carefully.

## More Information

More information could be found in our [wiki](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki):

- [How to contribute a translation](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/Localization)
- [How to make a contribution](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/贡献指南)
- [How to cite the project](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可#如何引用该项目)
- [Project changelog](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/更新日志)
- [Project license](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可)

## Starchart

[![Star History Chart](https://api.star-history.com/svg?repos=GaiZhenbiao/ChuanhuChatGPT&type=Date)](https://star-history.com/#GaiZhenbiao/ChuanhuChatGPT&Date)

## Contributors

<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=GaiZhenbiao/ChuanhuChatGPT" />
</a>

## Sponsor

🐯 If you find this project helpful, feel free to buy me a coke or a cup of coffee~

<a href="https://www.buymeacoffee.com/ChuanhuChat" ><img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=ChuanhuChat&button_colour=219d53&font_colour=ffffff&font_family=Poppins&outline_colour=ffffff&coffee_colour=FFDD00" alt="Buy Me A Coffee" width="250"></a>

<img width="250" alt="image" src="https://user-images.githubusercontent.com/51039745/226920291-e8ec0b0a-400f-4c20-ac13-dafac0c3aeeb.JPG">
