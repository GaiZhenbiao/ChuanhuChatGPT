# 插件系统验证记录

验证日期：2026-10-01。开发工作树为 `codex/extension-system`，起点为原 `extension` 分支的 `fe06e88669041768bdbcf3e6c47bfb3fd9dc10a0`。原工作目录没有修改配置或工作区文件。

## 可复现的离线检查

使用 Python 3.11 建立隔离环境，安装 `requirements_tests.txt`，然后执行：

```sh
.venv/bin/python -m pytest -q tests
.venv/bin/python tests/ui_smoke.py
.venv/bin/python tests/project_ui_mock.py --build-only
.venv/bin/python tests/project_ui_mock.py --build-only --language en_US
```

当前合并后共 **58 项测试通过**。单元与集成测试覆盖配置原子持久化、损坏状态关闭插件、manifest 校验、重复 ID、失败导入回滚、相对 helper 导入与旧裸模块冲突、回调归属与生成器关闭、禁用后事件防护、暂存安装默认关闭、真实临时 Git 仓库 fetch/脏更新拒绝，以及用户数据隔离。

Agent 模拟 SDK 测试覆盖目标 root turn、重放事件、断流未知结局、继续排除旧 turn、显式函数白名单、恢复、取消、产物限制、专用凭据来源与创建不明时对账。真实 Gradio HTTP 验收覆盖任务、继续、两个浏览器、下载、恢复、清理、双击和远程取消。首个 yield 后关闭生成器必须恢复未提交状态、释放 owner 锁，允许重新发送；继续任务关闭则保留上一个已完成 turn。

真实项目布局离线入口成功构建 247 个组件，使用项目主题、CSS、JS 和真实插件。它通过 AST 提取主入口布局，使用合成聊天/Agent 数据，不读取配置、密钥或导入 provider。历史、训练、计费、更新操作没有绑定。可用 `tests/project_ui_mock.py --port 8773` 打开浏览器验收，但不代表完整应用启动和全部 provider 已验证。

## 实际 API 验证范围

仅执行过一次用户授权的合成付费任务：1 个 session、1 次初始任务、0 次继续、0 次自动重试。目标 turn 完成，托管沙箱报告创建并读回测试文件；随后删除了该测试 session。没有保存 usage/token 金额，不报告实际费用。

最终 UI 的继续、函数工具、取消、恢复、产物下载和后来补充的网络/子 Agent 禁用 payload 经过离线与模拟验证，未逐项再次付费验证。验证脚本默认不发送请求；不要未经授权执行 `optional/agents/probe.py --execute`。

## 上游兼容状态

2026-10-01 fetch 后的上游 `main` 是 `2c7d5304c215520dbc6077f185fc45d8e0c8d919`；共同祖先为 `c020b2ddc0fc230ef4f2398152a89d8a2d907f0a`。在隔离分支中合并了当前上游，保留此前实现基线 `cdb5ec2c4f910feffc424f64dc708d541c806c57`，没有改原工作目录或远端 extension 分支。

主入口冲突保留插件工具箱/管理入口，并使用上游分层 locale ID；英文 locale 使用上游完整树，再增补插件管理文案；base_model 保留上游生成状态提示与全部既有 hook。config 自动合并成功，相对上游只保留旧 disabled_extensions 的两处兼容增量。没有回退上游其他 provider、配置或翻译重构。

合并后重跑全部测试、真实 Gradio HTTP 工作流、中英文真实项目布局构建和源码编译。另有四项测试直接执行合并后真实 `BaseLLMModel.predict` 方法，使用合成 provider 验证流式/非流式成功和错误路径、hook 顺序、改写后的历史保存。这不会导入付费 provider，也不能代替所有 provider 的在线测试。

本地提交现在包含该上游祖先，可作为 PR1200 的后续集成提交；旧远端 PR 尚未更新，所以网站仍可能显示旧冲突状态。完整主入口连同全部模型依赖未启动，普通 provider、生产部署与不同版本 Gradio 不作已验收承诺。官方 beta 接口仍需按文档范围理解。

当前上游没有插件基础设施。本轮生命周期修复依赖 PR1200；直接拆成上游小 PR 会隐含引入整个插件系统，不符合独立小修复的范围。本轮不强拆或发布未验收主功能。
