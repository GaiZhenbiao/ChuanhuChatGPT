<div align="right">
  <!-- Language: -->
  <a title="Chinese" href="../README.md">简体中文</a> | <a title="English" href="README_en.md">English</a> |  <a title="Japanese" href="README_ja.md">日本語</a> |  Russian
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
        Потоковое вещание / Неограниченное количество разговоров / Сохранение истории / <br /> Предустановленные подсказки / Чат с файлами / Поиск в Интернете <br />
        Рендеринг LaTeX/Рендеринг таблиц/Подсветка кода <br />
        Автоматический темный режим / Адаптивный веб-интерфейс / Тема в стиле WeChat <br />
        Многопараметрическая настройка / Поддержка нескольких ключей API / Многопользовательская поддержка <br />
        Совместимость с GPT-4/локальное развертывание для LLM.
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

[![Video Title](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7.jpg)](https://github.com/GaiZhenbiao/ChuanhuChatGPT/assets/51039745/0eee1598-c2fd-41c6-bda9-7b059a3ce6e7?autoplay=1)

## Поддерживаемые модели LLM

**Модели LLM через API**:

- [ChatGPT](https://chat.openai.com) ([GPT-4](https://openai.com/product/gpt-4))
- [Google PaLM](https://developers.generativeai.google/products/palm)
- [Inspur Yuan 1.0](https://air.inspur.com/home)
- [MiniMax](https://api.minimax.chat/)
- [XMChat](https://github.com/MILVLG/xmchat)

**Модели LLM через локальное развертывание**:

- [ChatGLM](https://github.com/THUDM/ChatGLM-6B) ([ChatGLM2](https://github.com/THUDM/ChatGLM2-6B))
- [LLaMA](https://github.com/facebookresearch/llama)
- [StableLM](https://github.com/Stability-AI/StableLM)
- [MOSS](https://github.com/OpenLMLab/MOSS)

## Советы по использованию

- Чтобы лучше контролировать ChatGPT, используйте системную подсказку.
- Чтобы использовать шаблон подсказки, сначала выберите файл коллекции шаблонов подсказок, а затем выберите конкретную подсказку в раскрывающемся меню.
- Чтобы повторить попытку, если ответ неудовлетворительный, используйте кнопку «🔄 Восстановить».
- Чтобы начать новую строку в поле ввода, нажмите клавиши <kbd>Shift </kbd> + <kbd>Enter </kbd>.
- Чтобы быстро переключиться между историей ввода, нажмите клавиши <kbd>↑</kbd> и <kbd>↓</kbd> в поле ввода.
- Чтобы развернуть программу на сервере, установите `"server_name": "0.0.0.0", "server_port" <номер вашего порта>` в `config.json` .
- Чтобы получить общедоступную ссылку, установите `"share": true` в `config.json`. Обратите внимание, что для доступа по общедоступной ссылке программа должна быть запущена.
- Чтобы использовать его в пространстве с обнимающим лицом: рекомендуется **Дублировать пространство** и запустить программу в своем собственном пространстве для более быстрой и безопасной работы.

## Быстрый старт

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
- [Как цитировать проект](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可#如何引用该项目)
- [Журнал изменений проекта](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/更新日志)
- [Лицензия проекта](https://github.com/GaiZhenbiao/ChuanhuChatGPT/wiki/使用许可)

## Starchart

[![Star History Chart](https://api.star-history.com/svg?repos=GaiZhenbiao/ChuanhuChatGPT&type=Date)](https://star-history.com/#GaiZhenbiao/ChuanhuChatGPT&Date)

## Помощники

<a href="https://github.com/GaiZhenbiao/ChuanhuChatGPT/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=GaiZhenbiao/ChuanhuChatGPT" />
</a>

## Спонсорство

🐯 Если этот проект будет вам полезен, не стесняйтесь угостить меня колой или чашкой кофе~.

<a href="https://www.buymeacoffee.com/ChuanhuChat" ><img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=ChuanhuChat&button_colour=219d53&font_colour=ffffff&font_family=Poppins&outline_colour=ffffff&coffee_colour=FFDD00" alt="Buy Me A Coffee" width="250"></a>

<img width="250" alt="image" src="https://user-images.githubusercontent.com/51039745/226920291-e8ec0b0a-400f-4c20-ac13-dafac0c3aeeb.JPG">
