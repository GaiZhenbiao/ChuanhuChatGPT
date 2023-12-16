<div align="right">
  <!-- Language: -->
  <a title="Chinese" href="../README.md">简体中文</a> |  <a title="English" href="README_en.md">English</a> | <a title="Japanese" href="README_ja.md">日本語</a> | <a title="Russian" href="README_ru.md">Russian</a> | 한국어
</div>

<h1 align="center">川虎 Chat 🐯 Chuanhu Chat</h1>
<div align="center">
  <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT">
    <img src="https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/aca3a7ec-4f1d-4667-890c-a6f47bf08f63" alt="Logo" height="156">
  </a>

<p align="center">
    <h3>ChatGPT/ChatGLM/LLaMA등의 LLM을 위한 가벼운 사용자 친화적 Web-UI</h3>
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
        GPT-4 지원 · 파일에 대한 채팅 · LLMs 로컬 배포 · 웹 검색 · Chuanhu Agent ·  파인튜닝
      </p>
      <a href="https://www.youtube.com/watch?v=MtxS4XZWbJE"><strong>영상 튜토리얼</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=77nw7iimYDE"><strong>2.0 소개</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=x-O1jjBqgu4"><strong>3.0 소개 & 튜토리얼</strong></a>
	||
      <a href="https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT"><strong>온라인 테스트</strong></a>
      	·
      <a href="https://huggingface.co/login?next=%2Fspaces%2FJohnSmith9982%2FChuanhuChatGPT%3Fduplicate%3Dtrue"><strong>원클릭 배포</strong></a>
    </p>
  </p>
</div>

[![Video Title](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7.jpg)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7?autoplay=1)

## ✨ 5.0 업데이트!

![ChuanhuChat5update](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/f2c2be3a-ea93-4edf-8221-94eddd4a0178)


<sup>New!</sup> 완전히 새로운 사용자 인터페이스! 반투명 유리효과를 지원합니다!

<sup>New!</sup> 모든 모바일 장치에 적합한 UI.

<sup>New!</sup> 대화 기록이 왼쪽으로 이동하여 더 편리하게 사용할 수 있습니다. 검색, 삭제, 이름 변경이 가능합니다.

<sup>New!</sup> 자동으로 대화 기록의 이름을 설정할 수 있습니다. (설정에서 활성화 필요).

<sup>New!</sup> Chuanhu Chat는 이제 Chrome/Edge/Safari 등 브라우저를 지원하는 PWA입니다.

<sup>New!</sup> 아이콘들이 플랫폼에 맞게 조정되어, 더 자연스럽습니다.

<sup>New!</sup> GPT 3.5! 파인튜닝을 지원합니다.

## 지원 모델들

|                                      API 호출 모델들                                       | 설명                    |                                             로컬 배포 모델                                              | 설명                  |
|:-------------------------------------------------------------------------------------:|-----------------------|:-------------------------------------------------------------------------------------------------:|---------------------|
|                       [ChatGPT(GPT-4)](https://chat.openai.com)                       | gpt-3.5 파인튜닝 지원       | [ChatGLM](https://github.com/THUDM/ChatGLM-6B) ([ChatGLM2](https://github.com/THUDM/ChatGLM2-6B)) |
| [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service) |                       |                        [LLaMA](https://github.com/facebookresearch/llama)                         | Lora 모델 지원 
|          [Google PaLM](https://developers.generativeai.google/products/palm)          | 스트리밍 미지원              |                       [StableLM](https://github.com/Stability-AI/StableLM)                        
|          [iFlytek Starfire Cognition Large Model](https://xinghuo.xfyun.cn)           |                       |                             [MOSS](https://github.com/OpenLMLab/MOSS)                             
|                    [Inspur Yuan 1.0](https://air.inspur.com/home)                     |                       |                         [Qwen](https://github.com/QwenLM/Qwen/tree/main)                          
|                         [MiniMax](https://api.minimax.chat/)                          |
|                      [XMChat](https://github.com/MILVLG/xmchat)                       | 스트리밍 미지원 
|                       [Midjourney](https://www.midjourney.com/)                       | 스트리밍 미지원 
|                         [Claude](https://www.anthropic.com/)                          |

## 사용 팁

### 💪 강력한 기능
- **Chuanhu Assistant**: AutoGPT와 같이,문제를 자동으로 해결합니다.
- **온라인 검색**: ChatGPT의 데이터가 너무 오래되었나요? LLM과 인터넷의 정보를 함께 사용하세요.
- **Knowledge Base**: ChatGPT가 당신의 읽기 속도를 높여줍니다! 파일에 대해 질문하세요.
- **LLM 로컬 배포**: 원클릭 LLM 배포로 당신만의 LLM을 가지세요.

### 🤖 시스템 프롬프트
- 시스템 프롬프트를 통해 사전 조건을 설정하면 역할극을 효과적으로 할 수 있습니다.
- ChuanhuChat는 프롬프트 프리셋을 제공합니다. `프롬프트 템플릿 불러오기`탭에서 프롬프트를 불러온 후 아래 리스트에서 원하는 프롬프트를 설정하세요.

### 💬 기본 대화
- 답변이 만족스럽지 않다면 `재생성` 버튼으로 다시 시도하거나  `이 라운드의 질문과 답변 삭제` 버튼을 사용할 수 있습니다.
- 입력창은 줄 바꿈을 지원합니다. <kbd>Shift</kbd> + <kbd>Enter</kbd> 를 사용하세요.
- 입력창에서 <kbd>↑</kbd> <kbd>↓</kbd> 를 사용해 이전 전송 기록으로 이동할 수 있습니다.
- 매번 새로운 대화를 만드는 것이 귀찮다면 `단일 대화` 기능을 사용하세요;
- 답변 옆의 버튼들은 `일괄 복사`, `원본 Markdown 보기` 기능을 제공합니다.
- ChatGPT가 특정 언어로 응답할 수 있도록 답장 언어를 지정하세요.

### 📜 대화 기록
- 대화 기록은 자동으로 저장됩니다.
- 다중 사용자모드 사용시 본인 대화는 본인만 볼 수 있습니다.
- 대화 기록명을 바꿔 추후 검색을 용이하게 할 수 있습니다.
- <sup>New!</sup> LLM이 대화 기록을 요약하여 대화 기록명을 자동으로 설정하게 할 수 있습니다.
- <sup>New!</sup> 정규식을 사용하여 검색할 수 있습니다.

### 🖼️ 간단하고 아름다운 UI
- 자체 개발한 Small-and-Beautiful 테마는 간단하고 아름다운 UI를 제공합니다.
- 자동 다크/라이트 테마 전환으로 아침부터 밤까지 편안한 경험을 제공합니다.
- 완벽한 LaTeX / 표 / 소스 코드 렌더링;
- <sup>New!</sup> 비선형 애니메이션, 반투명 유리효과
- <sup>New!</sup> Windows / macOS / Linux / iOS / Android 각 플랫폼에 최적화된 경험을 제공합니다. 
- <sup>New!</sup> PWA앱 설치로 더 자연스러운 경험을 제공합니다.

### 👨‍💻 전문가용 기능
- <sup>New!</sup> gpt-3.5 파인튜닝 제공!
- LLM의 다양한 파라미터들을 조정할 수 있습니다.
- API-host 변경 지원
- 커스텀 프록시 제공
- 다중 api키 로드밸런싱 기능 제공

### ⚒️ 배포 관련
- 서버에 배포: `config.json`에서 다음 항목을 설정하세요 `"server_name": "0.0.0.0", "server_port": <your port number>,`.
- 공개 주소 가져오기: `config.json`에서 다음 항목을 설정하세요 `"share": true,`.
- Hugging Face에서 사용: 앱이 더 빠르게 반응할 수 있도록 우측 상단의 버튼에서 **Duplicate the Space** 를 사용하세요

## 빠른 시작

터미널에서 다음 명령을 실행합니다.

```shell
git clone https://github.com/GaiZhenbiao/ChuanhuChatGPT.git
cd ChuanhuChatGPT
pip install -r requirements.txt
```

`config_example.json`의 복제본을 만들고, 이름을 `config.json`로 변경합니다, 이후 파일에서 API키와 다른 세팅들을 수정합니다.

```shell
python ChuanhuChatbot.py
```

브라우저가 자동으로 열리고 **Chuanhu Chat**를 사용해 ChatGPT 또는 다른 모델들을 사용할 수 있습니다.

> **참고**
>
> [wiki page](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程) 에서 자세한 정보를 확인하세요


## 문제해결

문제가 발생하면 **최신 코드로 업데이트하고<sup>1</sup>** **종속성을 업데이트<sup>2</sup>** 한 후 재시도 해보세요. 단계는 다음과 같습니다.:

1. Github 웹 페이지의 `Download ZIP`버튼으로 최신 코드를 다운로드하거나 다음 코드를 사용하세요
   ```shell
   git pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f
   ```
2. 다음 코드로 종속성을 업데이트하세요
   ```
   pip install -r requirements.txt
   ```

보통 이 방법으로 문제가 해결됩니다.

문제가 해결되지 않는다면 다음 페이지를 확인해보세요: [Frequently Asked Questions (FAQ)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题)

이 페이지에는 거의 대부분의 문제와 해결법이 있습니다. 자세히 읽어보세요

## 더 알아보기

더 많은 정보가 [wiki](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki) 에 있습니다.

- [어떻게 번역에 기여하나요?](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/Localization)
- [어떻게 이 프로젝트에 기여하나요?](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/贡献指南)
- [어떻게 이 프로젝트를 인용하나요?](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可#如何引用该项目)
- [업데이트 기록](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/更新日志)
- [프로젝트 라이선스](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可)

## Starchart

[![Star History Chart](https://api.star-history.com/svg?repos=GaiZhenbiao/ChuanhuChatGPT&type=Date)](https://star-history.com/#GaiZhenbiao/ChuanhuChatGPT&Date)

## 기여자들

<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=GaiZhenbiao/ChuanhuChatGPT" />
</a>

## 기부

🐯 이 프로젝트가 도움이되었다면, 저에게 커피나 콜라를 사주세요~

<a href="https://www.buymeacoffee.com/ChuanhuChat" ><img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=ChuanhuChat&button_colour=219d53&font_colour=ffffff&font_family=Poppins&outline_colour=ffffff&coffee_colour=FFDD00" alt="Buy Me A Coffee" width="250"></a>

<img width="250" alt="image" src="https://user-images.githubusercontent.com/51039745/226920291-e8ec0b0a-400f-4c20-ac13-dafac0c3aeeb.JPG">
