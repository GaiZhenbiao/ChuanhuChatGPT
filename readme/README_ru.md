<div align="right">
  <!-- Language: -->
  <a title="Chinese" href="../README.md">简体中文</a> | <a title="English" href="README_en.md">English</a> | <a title="Japanese" href="README_ja.md">日本語</a> | <a title="Korean" href="README_ko.md">한국어</a> | Русский
</div>

<h1 align="center">川虎 Chat 🐯 Chuanhu Chat</h1>
<div align="center">
  <a href="https://github.com/GaiZhenBiao/ChuanhuChatGPT">
    <img src="https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/aca3a7ec-4f1d-4667-890c-a6f47bf08f63" alt="Logo" height="156">
  </a>

<p align="center">
    <h3>Легкий и удобный веб-интерфейс для LLM, включая ChatGPT/ChatGLM/LLaMA</h3>
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
        Поддержка GPT-5 и DeepSeek R1 · Анализ файлов в чате · Локальная установка LLM · Онлайн-поиск · Помощник Agent · Поддержка Fine-tune
      </p>
      <a href="https://www.youtube.com/watch?v=MtxS4XZWbJE"><strong>Видео туториал</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=77nw7iimYDE"><strong>2.0 Введение</strong></a>
        ·
      <a href="https://www.youtube.com/watch?v=x-O1jjBqgu4"><strong>3.0 Введение и руководство</strong></a>
	||
      <a href="https://huggingface.co/spaces/JohnSmith9982/ChuanhuChatGPT"><strong>Пробная онлайн-версия</strong></a>
      	·
      <a href="https://huggingface.co/login?next=%2Fspaces%2FJohnSmith9982%2FChuanhuChatGPT%3Fduplicate%3Dtrue"><strong>Развертывание в один клик</strong></a>
    </p>
  </p>
</div>

> 📢 Новое: теперь поддерживается семейство GPT-5 (GPT-5, GPT-5-mini, GPT-5-nano): контекст 400k, до 128k токенов вывода.

[![Video Title](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7.jpg)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7?autoplay=1)

## Содержание

| [Поддерживаемые модели](#поддерживаемые-модели) | [Советы по использованию](#советы-по-использованию) | [Установка](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程) | [Частые вопросы](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题) | [Telegram-группа](https://t.me/tkdifferent) |
| --- | --- | --- | --- | --- |

## ✨ Обновление 5.0!

![ChuanhuChat5](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/70903329/f2c2be3a-ea93-4edf-8221-94eddd4a0178)

<sup>New!</sup> Совершенно новый пользовательский интерфейс! Он такой приятный, не похожий на Gradio, с новым эффектом матового стекла!

<sup>New!</sup> Адаптация для мобильных устройств (включая экраны с отверстием/выемкой под камеру), иерархия стала более четкой.

<sup>New!</sup> История перенесена в левую часть для удобства использования. Поддерживается поиск (с поддержкой регулярных выражений), удаление и переименование.

<sup>New!</sup> Теперь можно автоматически давать истории имена для больших моделей (требуется включение в настройках или в конфигурационном файле).

<sup>New!</sup> Теперь можно установить Чуаньху Чат в качестве приложения PWA, чтобы повысить нативность! Поддерживаемые браузеры: Chrome/Edge/Safari и другие.

<sup>New!</sup> Значок адаптирован для различных платформ, выглядит более комфортно.

<sup>New!</sup> Поддержка Fine-tune (микронной настройки) GPT 3.5!

## Поддерживаемые модели

| Модели через API | Примечание | Локальные модели | Примечание |
| :--- | :--- | :--- | :--- |
| [ChatGPT (GPT-5, GPT-4o, GPT-4, o1)](https://chat.openai.com) | Поддерживает дообучение gpt-3.5 | [ChatGLM](https://github.com/THUDM/ChatGLM-6B) ([ChatGLM2](https://github.com/THUDM/ChatGLM2-6B)) ([ChatGLM3](https://huggingface.co/THUDM/chatglm3-6b)) |  |
| [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service) |  | [LLaMA](https://github.com/facebookresearch/llama) | Поддерживает модели Lora |
| [Google Gemini](https://ai.google.dev/gemini-api/docs/api-key) |  | [StableLM](https://github.com/Stability-AI/StableLM) |  |
| [Claude](https://www.anthropic.com/) | Claude 3 Opus / 3.5 Sonnet / 3 Haiku | [MOSS](https://github.com/OpenLMLab/MOSS) |  |
| [DeepSeek](https://platform.deepseek.com) | DeepSeek Chat и DeepSeek R1 | [Qwen](https://github.com/QwenLM/Qwen/tree/main) |  |
| [iFlytek Spark](https://xinghuo.xfyun.cn) |  |  |  |
| [Inspur Yuan 1.0](https://air.inspur.com/home) |  |  |  |
| [MiniMax](https://api.minimax.chat/) |  |  |  |
| [XMChat](https://github.com/MILVLG/xmchat) | Без потоковой передачи |  |  |
| [Midjourney](https://www.midjourney.com/) | Без потоковой передачи |  |  |
| DALL·E 3 | Генерация изображений |  |  |

## Советы по использованию

### 💪 Мощные функции
- **Chuanhu ассистент**: подобно AutoGPT, полностью автоматизированное решение вашей проблемы;
- **Поиск в Интернете**: данные ChatGPT устарели? Дайте LLM возможность использовать сеть;
- **База знаний**: позвольте ChatGPT помочь вам быстро прочитать информацию! Ответить на вопросы в соответствии с файлами.
- **Локальная установка LLM**: одним щелчком разверните свою собственную модель языка большого размера.
- **GPT 3.5 Микронастройка**: Поддержка микронастройки GPT 3.5, чтобы сделать ChatGPT более персонализированным.
- **[Пользовательские модели](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/%E8%87%AA%E5%AE%9A%E4%B9%89%E6%A8%A1%E5%9E%8B-Custom-Models)**: Гибко настраивайте модели, например, подключите локальные сервисы вывода.

### 🤖 Системный промт
- Установка предпосылок через системное сообщение позволяет эффективно играть роль персонажа;
- Чуаньху Чат предоставляет набор системных шаблонов, нажмите "Загрузить шаблон системного сообщения", затем выберите необходимый шаблон ниже.

### 💬 Обычный диалог
- Если ответ не удовлетворяет вас, можно попробовать снова с помощью кнопки "Перегенерировать" или просто удалить этот раунд диалога;
- Поле ввода поддерживает перенос строки, нажмите <kbd>Shift</kbd> + <kbd>Enter</kbd>, чтобы сделать перенос строки;
- В поле ввода можно использовать клавиши <kbd>↑</kbd> и <kbd>↓</kbd>, чтобы быстро переключаться в истории отправки;
- Создание нового диалога слишком неудобно? Попробуйте функцию "Одиночный диалог";
- У кнопки возле пузыря с ответом можно не только "скопировать одним нажатием", но и "посмотреть исходный текст в формате Markdown";
- Укажите язык ответа, чтобы ChatGPT всегда отвечал на определенном языке.

### 📜 История чатов
- История диалогов будет сохраняться автоматически, не нужно беспокоиться о том, что после вопросов они исчезнут;
- История диалогов защищена для каждого пользователя, никто кроме вас не может ее видеть;
- Переименуйте историю диалога, чтобы было удобнее искать в будущем;
- <sup>New!</sup> Магическое автоматическое именование истории диалога: позволяет LLM понять содержание диалога и автоматически называть историю диалога!
- <sup>New!</sup> Поиск истории диалога, поддержка регулярных выражений!

### 🖼️ Красивый и компактный интерфейс
- Собственная тема Small-and-Beautiful принесет вам красивые и компактные впечатления;
- Автоматическое переключение светлой и темной темы обеспечит комфорт в любое время суток;
- Идеальное отображение LaTeX / таблиц / блоков кода, поддержка подсветки синтаксиса;
- <sup>New!</sup> Нелинейная анимация, эффект матового стекла – он такой изысканный, не похожий на Gradio!
- <sup>New!</sup> Поддержка Windows / macOS / Linux / iOS / Android, от иконки до адаптации под экраны с вырезами, предоставляет оптимальный опыт!
- <sup>New!</sup> Поддержка установки в качестве PWA-приложения, для более нативного опыта!

### 👨‍💻 Технические возможности
- <sup>New!</sup> Поддержка Fine-tune (тонкой настройки) gpt-3.5!
- Множество настраиваемых параметров для LLM;
- Поддержка изменения api-host;
- Поддержка настройки настраиваемого прокси-сервера;
- Поддержка балансировки нагрузки между несколькими ключами API.

### ⚒️ Развертывание на сервере
- Развертывание на сервере: установите `"server_name": "0.0.0.0", "server_port": <порт>",` в `config.json`.
- Получение общедоступной ссылки: установите `"share": true` в `config.json`. Обратите внимание, что программа должна быть запущена, чтобы можно было получить доступ по общедоступной ссылке.
- Использование на Hugging Face: рекомендуется скопировать **Space** в правом верхнем углу, а затем использовать его, чтобы приложение было более отзывчивым.

## Быстрый старт

Выполните в терминале следующие команды:

```shell
git clone https://github.com/GaiZhenbiao/ChuanhuChatGPT.git
cd ChuanhuChatGPT
pip install -r requirements.txt
```

Затем создайте копию `config_example.json`, переименуйте ее в `config.json`, а затем укажите в файле свой API-ключ и другие настройки.

```shell
python ChuanhuChatbot.py
```

Откроется окно браузера, и вы сможете общаться с ChatGPT.

> **Примечание**
>
> Подробные инструкции см. на нашей [wiki-странице](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用教程).

## Поиск и устранение неисправностей

При возникновении проблем следует сначала попробовать вручную подтянуть последние изменения этого проекта. Примерная инструкция:

1. Загрузите архив с последней версией кода, нажав на кнопку `Download ZIP` на веб-странице, или
   ```shell
   git pull https://github.com/GaiZhenbiao/ChuanhuChatGPT.git main -f
   ```
2. Попробуйте установить зависимости еще раз (так как в этом проекте могли появиться новые зависимости)
   ```
   pip install -r requirements.txt
   ```

Как правило, большинство проблем можно решить, выполнив следующие действия.

Если проблема сохраняется, обратитесь к этой странице: [Часто задаваемые вопросы (FAQ)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/常见问题)

На этой странице перечислены практически все возможные проблемы и способы их решения. Пожалуйста, внимательно прочитайте его.

## Дополнительная информация

Более подробную информацию можно найти в нашей [wiki](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki):

- [Как добавить перевод](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/Localization)
- [Как внести вклад](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/贡献指南)
- [Журнал изменений проекта](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/更新日志)
- [Лицензия проекта](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可)
- [Как цитировать проект](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可#如何引用该项目)

## Starchart

[![Star History Chart](https://api.star-history.com/svg?repos=GaiZhenbiao/ChuanhuChatGPT&type=Date)](https://star-history.com/#GaiZhenbiao/ChuanhuChatGPT&Date)

## Помощники

<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=GaiZhenbiao/ChuanhuChatGPT" />
</a>
