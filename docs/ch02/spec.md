# Cowcode Spec

## 背景
从零构建一个命令行 AI 对话工具 Cowcode。目前不存在任何代码或基础设施。

## 目标
- 用户在终端启动 cowcode，进入交互式 TUI 对话界面
- 支持多轮对话，AI 记住上下文
- 支持 Anthropic Claude 和 OpenAI 两种后端，通过配置文件切换
- 流式输出（SSE），逐字打印回复
- 美观的终端界面：banner、状态栏、markdown 渲染、响应计时

## 功能需求
- F1: 配置文件加载 — 读取 YAML 配置文件，支持单 provider（直进对话）和多 provider（启动时方向键选择）
- F2: Anthropic Claude 后端 — 调用 Claude API，支持流式 SSE 输出，支持 extended thinking（思考过程），thinking 内容在后台处理不暴露给用户
- F3: OpenAI 后端 — 调用 OpenAI Chat Completions API，支持流式 SSE 输出
- F4: Provider 抽象层 — 统一接口封装不同后端，新增后端只需实现该接口
- F5: TUI 交互界面 — 终端内显示对话历史（用户输入/助手回复/错误），支持多行输入（Alt+Enter 换行，Enter 提交），底部输入框带提示符
- F6: 多轮对话上下文 — 维护消息历史，每轮请求携带完整上下文
- F7: System prompt — 内置系统提示随请求发送给模型
- F8: Markdown 渲染 — 回复结束后整段以 markdown 格式渲染（代码块、列表、强调等）
- F9: 响应计时 — 提交后立即显示 "Imagining... (Ns)" 秒数递增，结束后显示总耗时
- F10: 错误恢复 — API 错误（错误 key、不存在模型等）时在对话区红色显示，不退出程序
- F11: 多 provider 选择 — 配置多个 provider 时，启动出现方向键 OptionList 供用户选择
- F12: 启动界面 — 显示猫 banner、名称版本、cwd、就绪提示行、状态栏（左 name 右 model）

## 非功能需求
- N1: 流式输出体验 — 逐字打印，打字机效果
- N2: 密钥保护 — 对话区与任何输出均不出现 api_key
- N3: 优雅退出 — Ctrl+C 和 /exit 均能安全退出，终端恢复正常
- N4: 配置校验 — 缺密钥/非法 protocol/文件缺失时给出可读错误并非零退出，无未捕获堆栈
- N5: 流式不阻塞 — 等待/流式期间界面仍响应、不冻结
- N6: 窗口自适应 — 缩放终端宽度后输入框/对话区/markdown 不错版

## 不做的事
- 不支持 tool use（调用外部工具、执行命令）
- 不支持文件操作（读写、编辑项目文件）
- 不支持代码理解或仓库级别的 agent 能力
- 不支持多模态（图片、音频等输入）
- 不支持缓存对话历史到磁盘（会话重启后上下文清空）
- 不支持自定义温度、max_tokens 等参数（固定默认值）
- 不支持其他 LLM 提供商（如 Google Gemini、Mistral 等）

## 验收标准
- AC1: 提供 YAML 配置文件，单 provider 时启动直接进入对话
- AC2: 配置缺失必填字段时，程序启动报错并提示缺少哪个字段，无 traceback
- AC3: 设置 protocol: anthropic 时，调用 Anthropic API 成功返回对话
- AC4: 设置 protocol: openai 时，调用 OpenAI API 成功返回对话
- AC5: Claude 模型的 extended thinking 在后台处理，界面不暴露思考文本
- AC6: 用户连续发送多条消息，AI 能记住之前的对话内容
- AC7: 流式输出时，回复逐字打印而非等全部生成完再一次性显示
- AC8: Provider 抽象层可通过统一接口调用，新增后端只需实现该接口
- AC9: Ctrl+C 和 /exit 均能优雅退出，终端恢复正常
- AC10: 配置多个 provider 时，启动出现方向键列表，选定后进入对话
- AC11: System prompt 随请求发送，模型能体现角色设定
- AC12: 回复以 markdown 格式渲染（代码块、列表、强调正确）
- AC13: 提交后立即显示 "Imagining... (Ns)" 秒数递增，结束后显示总耗时
- AC14: API 错误时在对话区红色显示，程序不退出
- AC15: Alt+Enter 换行，Enter 提交，提交后输入框清空
- AC16: 启动有 banner、状态栏（左 name 右 model）
- AC17: 任何输出中不出现 api_key
- AC18: 缩放终端窗口，界面不错版
