# 插件开发与使用

插件用稳定 ID 注册能力，管理器只处理发现、安装、启停与更新。业务界面与设置在插件自己的 Tab 中；设置分组仍在 About 后，小屏隐藏分组标题。

## 使用与迁移

1. 启动后打开设置 → 插件，查看 ID、版本、启停和错误。
2. 安装 Git URL 或本地目录会先复制到隐藏暂存目录，验证 metadata、ID 冲突和符号链接，成功后发布目录。**新安装插件默认禁用，不会执行 Python 或 install.py，不会自动安装依赖。**
3. 检查来源和代码后启用。已加载 Python hook 可立即暂停/恢复；新增界面与静态资源需要**重启应用**。刷新列表只重新发现，不执行新代码或重建已有 UI。
4. 点击检查更新才执行 fetch；渲染列表本身不联网。Git 更新拒绝有修改或未跟踪文件的仓库，只允许 fast-forward，绝不 hard reset。更新成功后暂停该插件 hook，重启应用加载新版本。

启停保存在项目根目录 `extension_state.json`，不会改写包含密钥与注释的 `config.json`。启动优先级：持久启停覆盖 → `config.json.disabled_extensions` → metadata.enabled。该文件被 Git 忽略，写入采用原子替换，写失败不会改变运行态。损坏时所有插件停止加载并显示错误；先备份并修复状态文件，避免误删后意外启用插件。

旧 `disabled_extensions` 仍然可用。旧模块内全局 STATE 属于所有用户共享的进程状态；不要把录制开关、用户文本、运行结果或 session ID 放进去。自动笔记已改为当前模型会话独立开启；切换模型重新开启，文件保存到私有 `plugin_data/auto_notes/<随机会话目录>/`，不会迁移/删除旧插件 data 下的历史文件。

## 信任边界

Python / JavaScript 插件是**受信任代码，不是沙箱**，能够访问应用进程、文件、网络与凭据。参数校验和错误隔离不改变这一点。管理操作是全局操作，请仅向可信管理员开放应用；当前管理器没有单独的按用户授权模型。不要将无认证的应用公开给不可信用户。

插件不得默认上传用户数据，不得硬编码密钥。存储私有数据使用 `plugin_data/`，不要放在允许浏览器读取的 `extensions/` 静态资源目录。主程序禁止浏览器下载 `config.json`、`.env.agents`、`.agents-runtime`、`extension_state.json` 和 `plugin_data`。需要下载的公开/会话产物通过 Gradio File 返回临时文件。

## 可运行模板

复制 `templates/extension` 到 `extensions/my_extension`，修改 ID/名称，然后启用并重启。模板按钮会整理当前输入空白，不会发送消息、访问网络或存储对话。无需额外依赖。

```text
extensions/my_extension/
├── metadata.json
├── extension.py       # 可选根级入口
├── scripts/main.py    # scripts/*.py 入口按文件名排序
├── style.css          # 可选插件专属样式
├── stylesheet/*.css
└── javascript/*.js    # 或 .mjs
```

metadata 必须是标准 JSON 对象。ID 为 1–64 位 ASCII 字母/数字/下划线/短横线，首位为字母，`core` 保留；未提供 ID 时使用符合相同规则的目录名。重复 ID 的所有候选均拒绝加载，避免显示名或目录顺序决定行为。`name/version/description/author` 必须为字符串，`enabled` 为 boolean，`priority` 为 integer；翻译表必须为语言→字符串。目录按 priority、ID 排序。

```json
{
  "id": "my_extension",
  "name": "我的文本工具",
  "name_i18n": {"en_US": "My text tool"},
  "description": "显式整理当前输入。",
  "description_i18n": {"en_US": "Explicitly tidy the current input."},
  "version": "1.0.0",
  "enabled": false,
  "priority": 100
}
```

没有 setup(context) / entry 字段分派机制：入口执行顶层装饰器注册。metadata 中额外字段只是插件自己的描述数据，不会让加载器执行新入口、解析依赖或运行安装脚本。

## 绑定当前会话组件

```python
import gradio as gr
from modules.plugin_callbacks import on_toolbox_tab, on_app_ready, guarded_callback

@on_toolbox_tab
def render_controls():
    button = gr.Button("整理输入")

    @on_app_ready
    def bind(app):
        button.click(
            guarded_callback(lambda text: (text or "").strip()),
            inputs=app.user_input, outputs=app.user_input,
        )
```

`on_app_ready` 在完整界面构建后执行一次，收到不可变 `AppContext(chatbot, current_model, user_input)`。这些是 **Gradio 组件句柄**；只有事件执行时通过 inputs 取得当前浏览器的值，不要在构建时读取/缓存用户内容。事件的返回值通过 outputs 更新对应组件。

`guarded_callback` 在插件归属上下文内创建，禁用后阻止新事件执行；生成器在下次产出时停止并关闭资源。它无法强制中断正在执行的阻塞代码，也不能取消已经提交到远端的任务。Agent 的停止按钮会显式发出远程取消事件。

设置 Tab 用 `on_settings_tab`，内容由插件渲染；不要把业务选项塞入管理器。使用 `gr.State` 或当前模型对象保存本会话的配置。当前自动笔记展示了后者，会话导出展示了直接绑定当前聊天组件，Agent 展示了按 owner 隔离并锁定的任务状态。

## 对话 hook

| 注册函数 | 时间点 |
| --- | --- |
| on_before_chat | 对话开始，可修改 user_input |
| on_after_prepare | 输入预处理之后 |
| on_before_model_call | 调用已有模型之前 |
| on_after_chat | 完整回答之后 |
| on_chat_error | 对话异常 |
| on_after_history_saved | 历史保存之后 |

聊天 hook 接收 `ChatContext` 并就地修改，返回值不会作为回复自动消费。字段包括 model、user_input、chatbot、files、use_websearch、reply_language、prepared_input、assistant_reply、status_text、history_file_path，以及本次调用专属 metadata。异常 hook 接收 `ChatErrorContext(model, error, chat_context)`。不要把密钥或共享运行态写到 metadata。

```python
from modules.plugin_callbacks import on_after_chat

@on_after_chat
def annotate(context):
    if isinstance(context.assistant_reply, str):
        context.metadata["my_extension"] = {"characters": len(context.assistant_reply)}
```

回调归属用 ContextVar 隔离。入口失败会回滚该插件所有已注册回调及加载的模块；单个 hook 异常记录为插件错误，其他插件继续执行。错误日志最多保留最近 100 条。模块顶层只做轻量注册，不启动长任务或读取秘密。

## helper 模块

插件按独立 Python 包命名空间加载，推荐相对导入：

```python
# extension.py → extensions/my_extension/helper.py
from .helper import transform
# scripts/main.py → 同一 helper.py
from ..helper import transform
```

根级 `extension.py` 和 `scripts/*.py` 都会执行，不要重复注册同一功能。不要将可导入 helper 也放成独立 scripts/*.py 入口。旧 `import helper` 仅在没有同名缓存模块时兼容；发现与其他插件/库冲突会拒绝加载并提示改用相对导入。回滚会清理插件内 helper；已经产生的线程、文件、环境修改与其他对象引用不能撤销。更新与新 UI 一律重启，`load_extensions(force=True)` 只供启动/开发验证，不是公开热重载保证。插件自己的 Git 仓库应忽略 `__pycache__/` 和业务数据。

## 翻译、CSS 与 JavaScript

名称与描述翻译放 metadata，界面文案翻译放插件内。不要追加到核心 locale。CSS / JS 只放插件目录，CSS 使用独有前缀；本次没有更改核心全局 CSS 或插件设置分组 JS。

前端使用已有 `window.ChuanhuApp`：root/gradioApp、onReady、onRender、onMutation、userInput、setInputValue。事件绑定必须幂等：

```js
(function () {
  function bind() {
    window.ChuanhuApp.root().querySelectorAll("[data-my-tool]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "true";
      button.addEventListener("click", () => {
        const input = window.ChuanhuApp.userInput();
        if (input) window.ChuanhuApp.setInputValue(input, input.value.trim());
      });
    });
  }
  window.ChuanhuApp.onReady(bind);
  window.ChuanhuApp.onMutation(bind);
})();
```

## 内置实例与测试

- prompt_tools：点击常用提示词按钮，显式插入当前输入；沿用插件自己的 CSS / JS 与翻译。
- auto_notes：默认不记录，每个模型会话独立配置和私有输出目录。
- conversation_export：显式导出当前浏览器聊天文本为 Markdown/JSON；不读取全局历史、模型配置或附件。
- text_batch：离线读取用户选择的 UTF-8 .txt/.md，提取标题、待办与计数；逐文件进度/部分下载，支持取消。每文件 2 MiB，最多 30 个。
- openai_agents：默认禁用的真实 Agent UI，独立官方 SDK/凭据、多步沙箱任务、继续、停止、恢复与产物下载。详见 [Agents 使用指南](agents.md)。

```sh
python -m pytest -q tests
python tests/ui_smoke.py
```

UI smoke 使用真实 Gradio 服务和客户端，但所有 Agent 事件为本地合成，不读取专用密钥、不调用 OpenAI。依赖安装与已验证范围见 [验证记录](validation.md)。
