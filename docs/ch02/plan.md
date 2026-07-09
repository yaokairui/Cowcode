# Cowcode Plan

## 架构概览
Cowcode 由五个模块组成：

**1. config 模块** — 负责读取 YAML 配置文件，校验字段，返回 ProviderConfig 列表。支持单 provider（直进）和多 provider（启动列表选择）。

**2. provider 模块** — 抽象层。定义统一的 Provider 接口。Anthropic 和 OpenAI 各实现一个 Provider，新增后端只需实现同一接口。Provider 内部使用 httpx 异步客户端发起 SSE 请求。

**3. session 模块** — 对话上下文管理器。维护一个消息列表（system/user/assistant 交替），每轮对话追加新消息并传给 Provider。会话生命周期绑定到单次进程运行。

**4. cli 模块** — TUI 交互入口。使用 textual 库（替代 rich，textual 是 rich 作者开发的现代 TUI 框架）渲染终端界面：banner、对话历史区、输入框、状态栏、响应计时器。

**5. prompt 模块** — 内置 system prompt 管理，提供默认的 system message 文本。

依赖方向：cli → session + provider + prompt，provider → config，config 无依赖。

## 核心数据结构

### ProviderConfig
- `name: str` — provider 显示名称
- `protocol: str` — 取值 "anthropic" 或 "openai"
- `model: str` — 模型名称
- `base_url: str` — API 端点 URL
- `api_key: str` — 认证密钥
- `thinking: bool` — 是否启用 extended thinking（仅 anthropic）

### Message
- `role: str` — "system"、"user"、"assistant" 或 "thinking"
- `content: str` — 消息文本内容

### Session
内部维护 Message 列表，提供 append(role, content)、get_history()、add_system_prompt() 方法。

### Provider 接口
`async def stream(self, session: Session) -> AsyncIterator[str]` — 返回逐词的异步迭代器。

### Config
- `providers: list[ProviderConfig]` — 配置的 provider 列表
- `system_prompt: str` — 可选的自定义 system prompt

## 模块设计

### config 模块
**职责：** 读取 YAML 文件，校验字段，返回 ProviderConfig 列表
**对外接口：** `load_configs(path: str) -> tuple[Config, list[ProviderConfig]]`
**依赖：** 无（std + pyyaml）

### provider 模块
**职责：** 抽象接口 + Anthropic/OpenAI 两种实现
**对外接口：** `create_provider(config: ProviderConfig) -> Provider`（工厂函数）
**依赖：** ProviderConfig
**Provider 抽象类：** 定义 `async def stream(self, session: Session) -> AsyncIterator[str]`
**AnthropicProvider：** 调用 `/messages` 端点，处理 `content_block_delta` 和 `thinking_block_delta` 事件（thinking 内容后台处理，不暴露）
**OpenAIProvider：** 调用 `/chat/completions` 端点，处理 `content` delta 事件

### session 模块
**职责：** 维护对话历史
**对外接口：** `Session.append(role, content)`、`Session.get_history() -> list[Message]`、`Session.add_system_prompt(text)`
**依赖：** 无

### prompt 模块
**职责：** 内置 system prompt 管理
**对外接口：** `get_default_system_prompt() -> str`
**依赖：** 无

### cli 模块
**职责：** TUI 交互入口，渲染界面，接收输入，调用其他模块
**对外接口：** `main()` 入口函数
**依赖：** Config, ProviderConfig, Session, Provider, prompt
**实现：** 使用 textual 构建 TUI 应用：
- `CowcodeApp` 继承 `App`，管理 banner、对话区（RichLog）、输入框、状态栏
- 多 provider 时使用 `OptionList` 选择
- 单 provider 时直接进入对话
- 响应计时器实时更新
- Markdown 渲染在回复结束后触发

## 模块交互
```
用户启动 cowcode
       │
       ▼
cli.main()
   │ 加载 config.load_configs("config.yaml") → Config, providers
   │ 单 provider → 直接使用；多 provider → OptionList 选择
   │ 创建 session = Session()
   │ session.add_system_prompt(get_default_system_prompt())
   │ 创建 provider = create_provider(selected_config)
   │
   ▼ TUI 循环：
   1. 显示 banner + 对话历史 + 输入框 + 状态栏
   2. 用户输入（Enter 提交，Alt+Enter 换行）
   3. session.append("user", text)
   4. 显示 "Imagining... (Ns)" 计时器
   5. 遍历 await provider.stream(session):
        - 逐字追加到对话区（纯文本流式）
   6. 流式结束 → 将回复以 markdown 渲染
   7. session.append("assistant", full_response)
   8. 隐藏计时器
   9. 回到步骤 2
```

## 文件组织
```
cowcode/
├── pyproject.toml          — 项目配置、依赖声明
├── config.yaml             — 示例配置文件
└── cowcode/
    ├── __init__.py
    ├── __main__.py         — 入口：调用 cli.main()
    ├── config.py           — ProviderConfig 数据类 + load_configs()
    ├── session.py          — Session 类 + Message 数据类
    ├── prompt.py           — 内置 system prompt
    ├── provider/
    │   ├── __init__.py     — Provider 抽象基类 + create_provider 工厂
    │   ├── base.py         — Provider 抽象接口定义
    │   ├── anthropic.py    — AnthropicProvider 实现
    │   └── openai.py       — OpenAIProvider 实现
    └── cli.py              — Textual TUI 应用 + main()
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 异步还是同步 | 异步（asyncio + httpx.AsyncClient） | SSE 流式需要非阻塞读取 |
| TUI 框架 | textual | rich 作者开发，专为终端 TUI 设计，支持 RichLog、OptionList、Markdown 渲染、窗口自适应 |
| SSE 客户端 | httpx.AsyncClient + iter_lines() | 官方维护、async 原生支持 |
| 配置解析 | pyyaml + dataclass | dataclass 类型安全，pyyaml 事实标准 |
| 并发运行 | anyio.run() | 统一 asyncio 入口 |
| Markdown 渲染 | textual.markdown.Markdown | 原生支持，回复结束后自动格式化 |
| 错误处理 | 自定义异常类 + rich 彩色输出 | 网络错误、认证错误、格式错误各有明确提示 |
| 多 provider 选择 | textual.widgets.OptionList | 方向键导航，Enter 确认 |
