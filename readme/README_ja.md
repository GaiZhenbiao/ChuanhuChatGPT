<div align="right">
  <!-- Language: -->
  <a title="Chinese" href="../README.md">简体中文</a> | <a title="English" href="README_en.md">English</a> | 日本語 |  <a title="Russian" href="README_ru.md">Russian</a> | <a title="Korean" href="README_ko.md">한국어</a>
</div>

<h1 align="center">川虎 Chat 🐯 Chuanhu Chat</h1>
<div align="center">
  <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT">
    <img src="https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/aca3a7ec-4f1d-4667-890c-a6f47bf08f63" alt="Logo" height="156">
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
        GPT-4対応 · ファイルへの質問チャット · LLMのローカルデプロイ可能 · ウェブ検索 · エージェントアシスタント · Fine-tuneをサポートします
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
  </p>
</div>

[![Video Title](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7.jpg)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7?autoplay=1)

## ✨ 5.0の重要な更新！

![ChuanhuChat5更新](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/f2c2be3a-ea93-4edf-8221-94eddd4a0178)

<sup>新!</sup> 全く新しいユーザーインターフェース！Gradioに比べて精緻で、さらにフロストガラス効果があります！

<sup>新!</sup> モバイル端末（画面全体のスマホのパンチホール/ノッチを含む）に対応し、レイヤーがはっきりしてきました。

<sup>新!</sup> 履歴が左側に移動し、使いやすくなりました。また、検索（正規表現対応）、削除、リネームが可能です。

<sup>新!</sup> 大きなモデルによる履歴の自動命名が可能になりました（設定または設定ファイルで有効化が必要）。

<sup>新!</sup> 今では 川虎チャット を PWAアプリケーションとしてインストールすることも可能で、よりネイティブな体験ができます！Chrome/Edge/Safariなどのブラウザをサポート。

<sup>新!</sup> 各プラットフォームに適したアイコンで、見ていても気持ちがいい。

<sup>新!</sup> Finetune（微調整）GPT 3.5に対応！

## モデルのサポート

| API呼び出しモデル | 備考 | ローカルデプロイモデル | 備考 |
| :---: | --- | :---: | --- |
| [ChatGPT(GPT-4)](https://chat.openai.com) | gpt-3.5の微調整をサポート | [ChatGLM](https://github.com/THUDM/ChatGLM-6B) ([ChatGLM2](https://github.com/THUDM/ChatGLM2-6B)) |
| [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service) |  | [LLaMA](https://github.com/facebookresearch/llama) | Loraモデルのサポートあり 
| [Google PaLM](https://developers.generativeai.google/products/palm) | ストリーミング転送はサポートされていません | [StableLM](https://github.com/Stability-AI/StableLM)
| [讯飞星火认知大模型](https://xinghuo.xfyun.cn) |  | [MOSS](https://github.com/OpenLMLab/MOSS)
| [Inspur Yuan 1.0](https://air.inspur.com/home) |  | [Qwen](https://github.com/QwenLM/Qwen/tree/main)
| [MiniMax](https://api.minimax.chat/) |
| [XMChat](https://github.com/MILVLG/xmchat) | ストリーミング転送はサポートされていません
| [Midjourney](https://www.midjourney.com/) | ストリーミング転送はサポートされていません
| [Claude](https://www.anthropic.com/) |

## 使う上でのTips

### 💪 パワフルな機能
- **川虎助理**：AutoGPTに似ており、自動的に問題を解決します。
- **オンライン検索**：ChatGPTのデータが古い場合は、LLMにネットワークの翼を付けます。
- **ナレッジベース**：ChatGPTがあなたをクイックリーディングの世界へご招待！ファイルに基づいて質問に答えます。
- **LLMのローカルデプロイ**：ワンクリックであなた自身の大規模言語モデルをデプロイします。

### 🤖 システムプロンプト
- システムプロンプトを使用して前提条件を設定すると、ロールプレイが効果的に行えます。
- 川虎Chatはプロンプトテンプレートを予め設定しており、「プロンプトテンプレートを読み込む」をクリックして、まずプロンプトテンプレートコレクションを選択し、次に下部で希望のプロンプトを選択します。

### 💬 ベーシックな対話
- もし回答が満足できない場合、「再生成」ボタンを使用して再試行するか、直接「このラウンドの対話を削除」することができます。
- 入力ボックスは改行をサポートしており、 <kbd>Shift</kbd> + <kbd>Enter</kbd> を押すと改行できます。
- 入力ボックスで <kbd>↑</kbd> <kbd>↓</kbd> キーを押すと、送信履歴をスピーディに切り替えることができます。
- 各対話を新しく作成するのは面倒ですか？「単発対話」機能を試してみてください。
- 回答バブルの横の小さなボタンは「一括コピー」だけでなく、「Markdownの元のテキストを表示」もできます。
- 回答の言語を指定して、ChatGPTが特定の言語で回答するようにします。

### 📜 履歴記録
- ダイアログの履歴は自動的に保存されるので、完了後に見つけることができます。
- 複数のユーザーの履歴は分離されており、他のユーザーは閲覧できません。
- 履歴の名前を変更することで、将来的な検索を容易にします。
- <sup>新!</sup> マジカルな自動履歴名付け機能で、LLMが対話内容を理解し、履歴に自動的に名前をつけてくれます！
- <sup>新!</sup> 正規表現をサポートする履歴検索！

### 🖼️ シンプルな使いやすさ
- 独自のSmall-and-Beautifulテーマで、シンプルで美しい体験を提供します。
- 自動的な明暗の切り替えで、早朝から夜まで快適な体験ができます。
- LaTeX/テーブル/コードブロックを完璧にレンダリングし、コードハイライトがサポートされています。
- <sup>新!</sup> ノンリニアアニメーション、フロストガラスの効果など、Gradioのように洗練されています！
- <sup>新!</sup> Windows / macOS / Linux / iOS / Androidに対応し、アイコンからフルスクリーンまで、最適な体験を提供します！
- <sup>新!</sup> PWAアプリケーションのインストールがサポートされており、よりネイティブな体験ができます！

### 👨‍💻 ギーク向け機能
- <sup>新!</sup> gpt-3.5のFine-tune（微調整）がサポートされています！
- 多くのLLMパラメータをカスタマイズできます。
- api-hostの変更が可能です。
- カスタムプロキシの設定が可能です。
- 負荷分散のための複数のapiキーのサポートがあります。

### ⚒️ デプロイに関する情報
- サーバーへのデプロイ：`config.json`ファイルで`"server_name": "0.0.0.0", "server_port": <あなたのポート番号>,"`を設定します。
- 共有リンクの取得：`config.json`ファイルで`"share": true,`を設定します。ただし、プログラムが実行されている必要があります。
- Hugging Faceでの使用：右上のコーナーの「Spaceをコピー」を選択し、それから使用することをおすすめします。これにより、アプリの反応が速くなる場合があります。


## クイックスタート

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
