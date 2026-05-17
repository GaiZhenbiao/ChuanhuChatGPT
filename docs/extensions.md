# 插件开发指南

这份文档面向第三方插件开发者，也面向协助开发插件的 AI。插件系统的目标是让扩展代码在不改动主程序核心文件的情况下，为侧边栏、设置页和对话流程增加轻量能力。

当前文档以仓库内可见的插件 API 为准：插件通过 `metadata.json` 声明基本信息，通过 Python 脚本注册回调，通过 CSS / JavaScript 静态资源增强界面。

## 快速开始

一个最小插件目录如下：

```text
extensions/
└── my_extension/
    ├── metadata.json
    └── scripts/
        └── main.py
```

`metadata.json`：

```json
{
  "id": "my_extension",
  "name": "我的插件",
  "version": "0.1.0",
  "description": "演示如何注册一个最小插件。",
  "enabled": true,
  "priority": 100
}
```

`scripts/main.py`：

```python
from modules.plugin_callbacks import on_before_chat
from modules.plugin_context import ChatContext


@on_before_chat
def add_marker(context: ChatContext):
    if isinstance(context.user_input, str):
        context.user_input = f"[来自插件] {context.user_input}"
```

插件脚本被加载时会执行模块顶层代码。使用装饰器注册回调即可，不需要手动调用加载器。

## 目录结构

推荐结构：

```text
extensions/<extension_id>/
├── metadata.json
├── extension.py              # 可选：根级插件脚本
├── scripts/                  # 可选：多个 Python 脚本
│   ├── main.py
│   └── other.py
├── style.css                 # 可选：根级样式文件，会自动加载
├── stylesheet/               # 可选：多个 CSS 文件
│   └── panel.css
└── javascript/               # 可选：多个 JS / MJS 文件
    └── main.js
```

当前加载约定：

- 插件根目录位于 `extensions/<extension_id>/`。
- 加载器会读取每个插件目录下的 `metadata.json`。
- Python 脚本支持根级 `extension.py`，以及 `scripts/*.py`。
- 根级 `style.css` 会自动收集，`stylesheet/*.css` 也会自动收集。
- `javascript/*.js` 和 `javascript/*.mjs` 会自动收集。
- 插件按 `priority` 从小到大加载；相同优先级下按插件 ID 排序。
- 插件可以向侧边栏工具箱注册自己的功能 Tab，也可以向设置页注册自己的设置 Tab。

建议把主要逻辑放在 `scripts/main.py`，把界面样式放在 `style.css`，把少量前端增强放在 `javascript/main.js`。不要依赖插件之间的加载顺序，除非你明确控制了 `priority` 且能接受耦合。

## metadata.json

推荐字段：

```json
{
  "id": "prompt_tools",
  "name": "提示词工具箱",
  "name_i18n": {
    "en_US": "Prompt toolbox"
  },
  "version": "0.1.0",
  "description": "演示侧边栏功能 Tab，点选模板后把提示词插入当前输入框。",
  "description_i18n": {
    "en_US": "Demonstrates a toolbox tab that inserts selected prompt templates into the current input box."
  },
  "author": "ChuanhuChatGPT",
  "enabled": true,
  "priority": 100,
  "tags": ["prompt", "productivity"]
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 推荐 | 插件 ID。未提供时通常会使用目录名。建议只使用小写字母、数字、下划线或短横线。 |
| `name` | string | 推荐 | 展示给用户的插件名称。 |
| `name_i18n` | object | 可选 | 插件自己提供的名称翻译表，例如 `{"en_US": "Prompt toolbox"}`。 |
| `version` | string | 推荐 | 插件版本，例如 `0.1.0`。 |
| `description` | string | 推荐 | 一句话说明插件用途。 |
| `description_i18n` | object | 可选 | 插件自己提供的描述翻译表。 |
| `author` | string | 可选 | 作者或组织。 |
| `enabled` | boolean | 可选 | 是否默认启用。默认通常视为启用。 |
| `priority` | number | 可选 | 加载优先级，数字越小越早加载。 |
| `tags` | array | 可选 | 便于后续管理和检索的标签。 |

`metadata.json` 必须是合法 JSON。不要写注释，不要使用尾随逗号。

## 前端资源自动加载

插件可以提供 CSS 和 JavaScript 资源：

- `style.css`
- `stylesheet/*.css`
- `javascript/*.js`
- `javascript/*.mjs`

这些资源由核心加载器收集并注入页面，适合做以下事情：

- 为插件自己的 Gradio 组件补充样式。
- 为插件区域增加少量交互增强。
- 给插件生成的 DOM 添加无侵入的视觉提示。

建议：

- CSS 选择器尽量加插件专属前缀，例如 `.prompt-prefix-demo ...`，避免影响主界面和其他插件。
- JavaScript 不要假设页面内部 DOM 结构长期稳定。
- 前端脚本应当可重复执行且无副作用；如果需要绑定事件，先检查是否已经绑定。
- 不要在前端脚本里保存敏感数据。

### 前端脚本钩子

插件前端脚本可以使用 `window.ChuanhuApp`，避免自己重复监听 `DOMContentLoaded` 或直接穿透 Gradio 的 Shadow DOM：

```js
(function () {
  function bind() {
    const root = window.ChuanhuApp.root();
    root.querySelectorAll("[data-my-extension-button]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "true";
      button.addEventListener("click", () => {
        const input = window.ChuanhuApp.userInput();
        if (!input) return;
        window.ChuanhuApp.setInputValue(input, "插入到输入框的内容\n\n" + input.value);
      });
    });
  }

  window.ChuanhuApp.onReady(bind);
  window.ChuanhuApp.onMutation(bind);
})();
```

可用接口：

| 接口 | 说明 |
| --- | --- |
| `root()` / `gradioApp()` | 返回当前 Gradio 根节点，兼容 Shadow DOM。 |
| `onReady(callback)` | 主界面初始化完成后执行；如果已经初始化，会立即执行。 |
| `onRender(callback)` | Gradio render 后执行；适合读取主界面已缓存的 DOM。 |
| `onMutation(callback)` | Gradio 根节点内容变化时执行；适合给动态生成的插件 DOM 绑定事件。 |
| `userInput()` | 返回主输入框的 `textarea/input`。 |
| `setInputValue(input, value)` | 设置输入框值并派发 `input/change` 事件。 |

## 侧边栏功能 Tab

插件可以向侧边栏工具箱注册自己的 Tab，用于放置对当前聊天流程影响较大的开关、输入框或按钮。通过 `on_toolbox_tab` 注册：

```python
import gradio as gr

from modules.plugin_callbacks import on_toolbox_tab

STATE = {"enabled": True}
TEXT = {
    "zh_CN": {"enable": "启用我的插件"},
    "en_US": {"enable": "Enable my extension"},
}


def tr(key, language="zh_CN"):
    return TEXT.get(language, TEXT["zh_CN"]).get(key, key)


def set_enabled(value):
    STATE["enabled"] = bool(value)


@on_toolbox_tab
def render_controls():
    with gr.Group(elem_classes="my-extension-controls"):
        enabled = gr.Checkbox(label=tr("enable"), value=STATE["enabled"])
    enabled.change(set_enabled, inputs=enabled)
```

核心会自动用插件名称创建 Tab，回调只负责渲染 Tab 内部内容。示例里通过 Gradio 组件事件把值写入插件模块内的 `STATE`，后续对话 hook 再读取这个状态。

## 设置页设置 Tab

插件可以向设置页注册自己的设置 Tab，用于放置不需要频繁修改的选项。通过 `on_settings_tab` 注册：

```python
import gradio as gr

from modules.plugin_callbacks import on_settings_tab

CONFIG = {"footer": "由插件追加"}
TEXT = {
    "zh_CN": {"footer": "追加文本"},
    "en_US": {"footer": "Footer text"},
}


def tr(key, language="zh_CN"):
    return TEXT.get(language, TEXT["zh_CN"]).get(key, key)


def set_footer(value):
    CONFIG["footer"] = value or ""


@on_settings_tab
def render_settings():
    with gr.Group(elem_classes="my-extension-settings"):
        footer = gr.Textbox(label=tr("footer"), value=CONFIG["footer"])
    footer.change(set_footer, inputs=footer)
```

核心会自动用插件名称创建设置 Tab。设置页 UI 和侧边栏 UI 的写法一致，区别主要是放置位置和使用场景。

## 插件与插件设置

设置页里的“插件”标签页只用于管理插件生命周期，不承载插件自己的业务设置。当前内置能力包括：

- 查看已发现插件的名称、ID、版本、状态、路径和错误信息。
- 使用开关启用或禁用插件。运行时禁用会立即停止该插件已注册的 Python hooks。
- 从 Git URL 或本地目录安装插件。
- 刷新插件列表。
- 对 Git 仓库形式安装的插件执行更新。

插件自己的设置项由 `on_settings_tab` 注册，并显示为设置页里的插件专属 Tab。这一点参考 SD WebUI 的分工：Extensions 页面负责安装、启用、更新等管理；扩展自己的配置通过 settings/options 机制进入全局设置区域，而不是混在 Extensions 管理页里。

注意：

- 新安装插件或更新插件后，Python hooks 会尝试重新加载；CSS / JavaScript 等前端静态资源仍建议刷新页面或重启应用后生效。
- 启用 / 禁用开关当前是运行时状态；如需默认禁用某插件，可在 `config.json` 中配置 `disabled_extensions`。
- 插件安装和更新会执行本地文件复制或 `git clone` / `git pull`。只安装可信来源的插件。

## 对话生命周期 Hooks

当前插件 API 包含这些对话 hook：

| Hook | 注册函数 | 典型用途 |
| --- | --- | --- |
| 对话开始前 | `on_before_chat` | 修改用户输入、记录元数据、根据插件设置调整上下文。 |
| 输入准备后 | `on_after_prepare` | 查看或调整 RAG / 联网搜索处理后的输入、展示附加内容。 |
| 模型调用前 | `on_before_model_call` | 在模型请求前观察最终上下文，或做轻量参数调整。 |
| 模型完整回答后 | `on_after_chat` | 修改最终回复、追加说明、写入插件处理结果。 |
| 对话异常时 | `on_chat_error` | 记录插件自己的错误状态或做降级提示。 |
| 历史保存后 | `on_after_history_saved` | 同步导出、写日志、通知外部系统。 |

导入方式：

```python
from modules.plugin_callbacks import on_before_chat, on_after_chat
from modules.plugin_context import ChatContext
```

推荐把 hook 写成接收一个 `ChatContext` 参数，并就地修改上下文对象：

```python
@on_before_chat
def before_chat(context: ChatContext):
    context.metadata["my_extension_enabled"] = True


@on_after_chat
def after_chat(context: ChatContext):
    if context.assistant_reply:
        context.assistant_reply += "\n\n由插件处理。"
```

不要依赖 hook 的返回值，除非核心 API 明确说明某个返回值会被消费。

## ChatContext 字段

`ChatContext` 表示一次对话流程中传递给插件的上下文。当前字段如下：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `model` | `Any` | 当前模型或模型配置对象。 |
| `user_input` | `Any` | 用户原始输入或当前输入。插件修改输入时应先判断类型。 |
| `chatbot` | `list` | 当前聊天记录 / UI 消息列表。 |
| `use_websearch` | `bool` | 当前是否启用联网搜索。 |
| `files` | `list | None` | 当前消息关联文件。 |
| `reply_language` | `str` | 回复语言，默认 `中文`。 |
| `limited_context` | `bool` | 是否使用有限上下文。 |
| `fake_input` | `str` | 展示或替代输入相关字段，按核心流程解释使用。 |
| `display_append` | `str` | 用于追加展示内容的字段，按核心流程解释使用。 |
| `prepared_input` | `Any` | 预处理后的输入。 |
| `assistant_reply` | `str | None` | 模型完整回复。`after_chat` 常用。 |
| `status_text` | `str` | 当前状态文本。 |
| `history_file_path` | `str | None` | 历史记录文件路径。 |
| `metadata` | `dict[str, Any]` | 插件之间或插件内部传递轻量元数据的字典。 |

使用建议：

- 修改 `user_input`、`assistant_reply` 前先判断类型。
- 插件自定义数据放在 `metadata` 里，并使用唯一 key，例如 `metadata["prompt_tools"]`。
- 不要把大文件、模型对象副本或不可序列化的大对象塞进 `metadata`。
- 不确定字段语义时，优先只读，不要写入。

## 错误处理

插件脚本加载失败或回调执行异常时，核心会记录插件错误，并尽量不影响其他插件继续运行。插件自身仍应主动处理可预期错误：

```python
@on_after_chat
def after_chat(context: ChatContext):
    try:
        if isinstance(context.assistant_reply, str):
            context.assistant_reply += "\n\n插件追加内容。"
    except Exception as exc:
        context.metadata["my_extension_error"] = str(exc)
```

建议：

- 对用户输入、文件列表、模型返回值做类型检查。
- 网络请求、文件读写、第三方库调用必须捕获异常。
- 错误信息尽量写入 `metadata` 或日志，不要把 Python traceback 原样展示给普通用户。
- 插件失败时应降级为“不处理”，避免阻断主对话。

## 推荐实践

开发原则：

- 只在自己的插件目录内放置文件，不修改主程序核心文件。
- 插件 ID、CSS class、metadata key 使用统一前缀。
- hook 逻辑保持短小，耗时任务应谨慎处理，避免拖慢聊天响应。
- 不要在模块顶层执行耗时操作；模块顶层只注册回调和初始化轻量默认值。
- 使用 `gr.Group`、`gr.Accordion` 等容器组织插件 UI，避免界面过散。
- 默认配置应安全、可撤销、容易理解。

协作原则：

- 示例和文档应说明依赖的核心 API，不要暗示未确认的能力已经存在。
- 对尚未实现的能力，只描述当前边界，不要写成已经支持。
- 修改插件时只改插件目录和对应文档，避免顺手改核心模块。
- 示例插件应小而完整：一个插件演示一个主要能力。

安全原则：

- 不要在插件中硬编码 API Key、访问令牌或用户隐私数据。
- 不要默认上传用户输入、聊天记录或文件。
- 如需访问外部网络，应提供清晰开关和说明。
- 对插入 HTML / Markdown 的内容进行最小化处理，避免意外注入。

## 示例插件

仓库内提供两个默认插件，它们既可以直接使用，也可以作为开发参考：

- `extensions/prompt_tools`：提示词工具箱。它在侧边栏提供润色、翻译、总结、解释代码、提取待办、起草邮件等常用模板按钮，点击后把提示词插入当前输入框，不在发送阶段隐式改写内容。
- `extensions/auto_notes`：自动笔记。它在侧边栏提供记录开关、标题和标签，在设置页提供保存文件名和完整回答选项，并通过 `after_chat` 把问答追加到 Markdown 笔记。

这两个插件主要依赖：

```python
from modules.plugin_callbacks import (
    on_toolbox_tab,
    on_settings_tab,
    on_after_chat,
)
from modules.plugin_context import ChatContext
```
