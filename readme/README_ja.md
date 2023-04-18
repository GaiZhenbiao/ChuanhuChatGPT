<div align="right">
  <!-- Language: -->
  <a title="Chinese" href="../README.md">简体中文</a> | <a title="English" href="README_en.md">English</a> | 日本語
</div>

<h1 align="center">川虎 Chat 🐯 Chuanhu Chat</h1>
<div align="center">
  <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT">
    <img src="https://user-images.githubusercontent.com/70903329/227087087-93b37d64-7dc3-4738-a518-c1cf05591c8a.png" alt="Logo" height="156">
  </a>

<p align="center">
    <h3>ChatGPT/ChatGLM/LLaMAなどのLLMのための軽量でユーザーフレンドリーなWeb-UI</h3>
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
        ストリーム出力／会話回数無制限／履歴保存／プリセットプロンプト／ファイルへの質問チャット<br>
        ウェブ検索／LaTeXレンダリング／表レンダリング／コードハイライト<br>
        オートダークモード／アダプティブ・ウェブ・インターフェイス／WeChatライク・テーマ<br />
        マルチパラメーターチューニング／マルチAPI-Key対応／マルチユーザー対応<br>
        GPT-4対応／LLMのローカルデプロイ可能。
      </p>
      <a href="https://www.youtube.com/watch?v=MtxS4XZWbJE"><strong>動画チュートリアル</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=77nw7iimYDE"><strong>2.0 イントロダクション</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=x-O1jjBqgu4"><strong>3.0 イントロダクション & チュートリアル</strong></a>
	||
      <a href="https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT"><strong>オンライントライアル</strong></a>
      	·
      <a href="https://huggingface.co/login?next=%2Fspaces%2FJohnSmith9982%2FChuanhuChatGPT%3Fduplicate%3Dtrue"><strong>ワンクリックデプロイ</strong></a>
    </p>
    <p align="center">
      <img alt="Animation Demo" src="https://user-images.githubusercontent.com/51039745/226255695-6b17ff1f-ea8d-464f-b69b-a7b6b68fffe8.gif" />
    </p>
  </p>
</div>

## 使う上でのTips

- ChatGPTをより適切に制御するために、システムプロンプトを使用できます。
- プロンプトテンプレートを使用するには、プロンプトテンプレートコレクションを選択し、ドロップダウンメニューから特定のプロンプトを選択。回答が不十分な場合は、`🔄再生成`ボタンを使って再試行します。
- 入力ボックスで改行するには、<kbd>Shift</kbd> + <kbd>Enter</kbd>キーを押してください。
- 入力履歴を素早く切り替えるには、入力ボックスで <kbd>↑</kbd>と<kbd>↓</kbd>キーを押す。
- プログラムをサーバにデプロイするには、プログラムの最終行を `demo.launch(server_name="0.0.0.0", server_port=<your port number>)`に変更します。
- 共有リンクを取得するには、プログラムの最後の行を `demo.launch(share=True)` に変更してください。なお、公開リンクでアクセスするためには、プログラムが実行されている必要があることに注意してください。
- Hugging Face Spacesで使用する場合： より速く、より安全に利用するために、**Duplicate Space**を使用し、自分のスペースでプログラムを実行することをお勧めします。

## インストール

```shell
git clone https://github.com/GaiZhenbiao/ChuanhuChatGPT.git
cd ChuanhuChatGPT
pip install -r requirements.txt
```

次に `config_example.json`をコピーして `config.json`にリネームし、そのファイルにAPI-Keyなどの設定を記入する。

```shell
python ChuanhuChatbot.py
```

ブラウザのウィンドウが開き、ChatGPTとチャットできるようになります。

> **Note**
>
> 詳しい手順は[wikiページ](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程)をご確認ください。

## トラブルシューティング

問題が発生した場合は、まずこのプロジェクトの最新の変更点を手動で引っ張ってみるのがよいでしょう。その手順は以下の通りです：

1. ウェブページの `Download ZIP` をクリックして最新のコードアーカイブをダウンロードするか、または
   ```shell
   git pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f
   ```
2. 新しい依存関係が導入されている可能性があるため、依存関係を再度インストールしてみてください。
   ```
   pip install -r requirements.txt
   ```
3. Gradioを更新
   ```
   pip install gradio --upgrade --force-reinstall
   ```

一般的に、以下の手順でほとんどの問題を解決することができます。

それでも問題が解決しない場合は、こちらのページをご参照ください： [よくある質問（FAQ）](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题)

このページでは、考えられるほぼすべての問題点と解決策を掲載しています。よくお読みください。

## More Information

より詳細な情報は、[wiki](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki) をご覧ください。:

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

🐯 この企画が役に立ったら、遠慮なくコーラかコーヒーでもおごってください〜。

<a href="https://www.buymeacoffee.com/ChuanhuChat" ><img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=ChuanhuChat&button_colour=219d53&font_colour=ffffff&font_family=Poppins&outline_colour=ffffff&coffee_colour=FFDD00" alt="Buy Me A Coffee" width="250"></a>

<img width="250" alt="image" src="https://user-images.githubusercontent.com/51039745/226920291-e8ec0b0a-400f-4c20-ac13-dafac0c3aeeb.JPG">
