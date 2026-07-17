<div align="center">

# Cowcode

**一个用 Python 实现的终端 AI 编程助手。**

在命令行里和 AI 协作，让模型能够理解项目、调用工具、读写文件、执行命令，并通过 SubAgent、Worktree 与 Agent Team 支持更复杂的工程任务。

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Textual](https://img.shields.io/badge/TUI-Textual-7B61FF)](https://textual.textualize.io/)
[![Status](https://img.shields.io/badge/status-in%20development-orange)](#开发状态)
[![License](https://img.shields.io/badge/license-not%20specified-lightgrey)](#许可证)

</div>

---

## 项目简介

Cowcode 是一个类似 Claude Code / Codex CLI 的终端 AI 编程助手。它运行在本地项目目录中，通过 TUI 对话界面连接大模型，并把文件读取、代码修改、命令执行、上下文压缩、权限审批、MCP 工具、Skill 技能包和多 Agent 协作整合到同一个开发工作流里。

它的目标不是做一个简单的聊天壳，而是逐步搭建一个可扩展、可验证、可长期演进的本地 Agent 工作台。

## 开发状态

当前项目处于活跃开发阶段，功能会随着 `docs/ch*/` 下的 `spec.md`、`plan.md`、`task.md` 与 `checklist.md` 逐章迭代。README 描述的是项目当前方向与已实现能力，部分高级能力仍在持续完善中。

## 功能亮点

| 能力 | 说明 |
| --- | --- |
| 终端 TUI | 基于 Textual / Rich 构建交互式对话界面，支持状态栏、流式输出、命令面板、权限提示与工具调用展示。 |
| 多 Provider | 支持 Anthropic Messages API、OpenAI Chat Completions 协议，以及兼容 OpenAI 协议的第三方网关。 |
| 工具调用 | 内置 `read_file`、`write_file`、`edit_file`、`bash`、`glob`、`grep`、`AskUserQuestion` 等工具。 |
| 权限系统 | 支持默认模式、计划模式、工具权限规则、黑名单与本地持久化授权。 |
| 会话管理 | 支持历史会话恢复、token 估算、自动 / 手动上下文压缩与会话清理。 |
| Hooks | 支持在会话和工具生命周期事件前后挂载自动化行为。 |
| MCP | 可从用户级与项目级配置加载 MCP server，并将 MCP 工具注册到 Cowcode。 |
| Skills | 支持本地 Skill 发现、加载、执行和 `/skill` 相关命令。 |
| SubAgent | 支持启动独立上下文的子 Agent，可后台运行，也可使用指定角色定义。 |
| Worktree 隔离 | 可为 Agent 创建独立 Git worktree，降低并发开发时的修改冲突。 |
| Agent Team | 支持持久化团队、队员邮箱、共享任务列表，以及 `tmux` / `iTerm2` / `in-process` 后端。 |
| Coordinator Mode | 可选协调者模式，让 Lead Agent 调度队员、汇总结果并完成最终收敛。 |

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/yaokairui/Cowcode.git
cd Cowcode
```

### 2. 安装依赖

从仓库根目录执行：

```bash
python -m venv cowcode/.venv
source cowcode/.venv/bin/activate
python -m pip install -e "cowcode[dev]"
```

Windows PowerShell 可以使用：

```powershell
python -m venv cowcode\.venv
cowcode\.venv\Scripts\Activate.ps1
python -m pip install -e "cowcode[dev]"
```

如果你已经有可用的 Python 3.11+ 环境，也可以直接执行：

```bash
python -m pip install -e "cowcode[dev]"
```

### 3. 创建配置文件

复制示例配置：

```bash
cp cowcode/config.example.yaml cowcode/config.yaml
```

然后把 API Key 放到环境变量中，不要把真实密钥写进仓库。

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-..."
```

PowerShell 示例：

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:ANTHROPIC_API_KEY="sk-..."
```

### 4. 启动 Cowcode

```bash
cd cowcode
python -m cowcode
```

如果已经安装 editable 包，也可以直接使用入口命令：

```bash
cowcode
```

查看帮助：

```bash
python -m cowcode --help
```

## 配置示例

Cowcode 默认读取当前项目中的 `config.yaml`。推荐基于 `cowcode/config.example.yaml` 创建本地配置，并使用环境变量注入密钥。

```yaml
providers:
  - name: OpenAI
    protocol: openai
    model: gpt-5.4
    base_url: https://api.openai.com/v1
    api_key: env:OPENAI_API_KEY
    context_window: 128000

# 也可以使用 Anthropic 协议
# providers:
#   - name: Anthropic
#     protocol: anthropic
#     model: claude-opus-4-8
#     api_key: env:ANTHROPIC_API_KEY

system_prompt: ""

enableSubAgentBackground: true

features:
  coordinator_mode: false
  fork_teammate: false
```

## 常用 Slash 命令

| 命令 | 说明 |
| --- | --- |
| `/help` | 显示可用命令。 |
| `/status` | 显示当前运行状态。 |
| `/plan` | 切换到计划模式。 |
| `/do` | 批准计划并开始执行。 |
| `/compact` | 手动压缩当前上下文。 |
| `/resume` | 恢复历史会话。 |
| `/session` | 显示当前会话信息。 |
| `/memory` | 显示已加载的记忆文件。 |
| `/hooks` | 列出已加载的 hooks。 |
| `/skill` | 列出已加载的 Skills。 |
| `/team list` | 查看 Agent Team。 |
| `/team info <name>` | 查看 Team 详情。 |
| `/team delete <name> [--force]` | 删除 Team。 |
| `/team kill <member>` | 终止 Team 队员。 |

## Agent Team

Agent Team 用于把一个复杂任务拆给多个长期存在的队员 Agent：

1. Lead Agent 创建 Team。
2. Lead 通过 `Agent(team_name="...")` 启动队员。
3. 队员拥有独立会话和 worktree。
4. 队员通过共享任务列表与邮箱通信。
5. Lead 汇总队员结果，必要时使用 Git merge 收敛改动。

后端会按下面的优先级自动选择：

1. 当前位于 `$TMUX` 内时，使用 `tmux`。
2. iTerm2 可用且存在 `it2` 时，使用 `iterm2`。
3. 系统存在 `tmux` 时，使用 `tmux`。
4. 其他情况回退到 `in-process`。

启用 Coordinator Mode 需要同时打开配置和环境变量：

```yaml
features:
  coordinator_mode: true
```

```bash
export MEWCODE_COORDINATOR_MODE=1
```

历史文档里可能出现 `mewcode` 命名；当前项目名和 Python 包名是 `cowcode`。

## MCP 配置

Cowcode 会合并用户级和项目级 MCP 配置，并把 MCP server 暴露的工具注册到当前工具系统。

stdio server 示例：

```yaml
mcp_servers:
  local-tool:
    type: stdio
    command: python
    args: ["-m", "your_mcp_server"]
    env:
      API_KEY: "${YOUR_API_KEY}"
```

HTTP server 示例：

```yaml
mcp_servers:
  remote-tool:
    type: http
    url: https://example.com/mcp
    headers:
      Authorization: "Bearer ${MCP_TOKEN}"
```

## 项目结构

```text
.
├── cowcode/                  # Python 包、测试和项目配置
│   ├── cowcode/              # 源码
│   ├── tests/                # 单元测试
│   ├── config.example.yaml   # 本地配置模板
│   └── pyproject.toml
├── docs/                     # 分章节开发文档与验收清单
│   └── ch*/                  # spec / plan / task / checklist
├── 功能验证/                 # 端到端验证记录与截图资料
├── CLAUDE.md                 # Claude Code 工作说明
├── AGENTS.md                 # Agent 工作说明
└── README.md
```

## 开发与验证

进入 Python 项目目录：

```bash
cd cowcode
```

运行静态检查：

```bash
ruff check .
ruff format --check .
```

运行测试：

```bash
pytest
```

按章节验收时，优先查看对应文档：

```bash
ls ../docs/ch15
```

每个章节通常包含：

| 文件 | 用途 |
| --- | --- |
| `spec.md` | 需求与验收标准。 |
| `plan.md` | 实现计划。 |
| `task.md` | 任务拆解。 |
| `checklist.md` | 验收清单。 |

端到端验证建议使用 tmux：

1. 在 tmux 中启动 Cowcode。
2. 输入一段真实的对话请求。
3. 观察 Cowcode 是否正确调用工具、生成回复。
4. 对照对应章节的 `checklist.md` 逐项验收。

## 安全注意事项

- 不要提交 `config.yaml`、`.env`、token、证书或任何真实密钥。
- 运行 `bash`、文件写入、文件编辑类工具前，请确认权限规则符合预期。
- Team / Worktree 会在本地创建额外目录，删除前先确认没有未保存改动。
- 连接第三方模型网关时，请确认 `base_url`、模型名和计费策略。

## 许可证

当前仓库尚未声明许可证。发布或对外复用前，建议补充 `LICENSE` 文件。
