# Cowcode

Cowcode 是一个用 Python 实现的终端 AI 编程助手，目标是提供类似 Claude Code / Codex CLI 的交互体验：在 TUI 中对话，让模型读取项目、调用工具、运行命令、编辑文件，并通过 SubAgent、Worktree 和 Agent Team 支持更复杂的协作式开发任务。

> 当前项目处于开发阶段，功能仍在按 `docs/ch*/` 的 spec / plan / task / checklist 迭代。

## 功能概览

- **终端 TUI**：基于 Textual / Rich 的对话界面，支持状态栏、命令面板、权限提示和工具调用展示。
- **多 Provider**：支持 Anthropic Messages API 与 OpenAI Chat Completions 协议，也可配置兼容 OpenAI 协议的第三方网关。
- **工具调用**：内置 `read_file`、`write_file`、`edit_file`、`bash`、`glob`、`grep`、`AskUserQuestion` 等工具。
- **权限系统**：支持默认模式、计划模式、工具权限规则、黑名单和持久化权限设置。
- **会话管理**：支持历史会话恢复、token 估算、自动 / 手动上下文压缩。
- **Hooks**：支持通过配置在工具调用前后挂载自动化行为。
- **MCP**：可从用户级与项目级配置加载 MCP server，并把 MCP 工具注册进 Cowcode。
- **Skills**：支持本地 Skill 发现、加载、执行和 `/skill` 相关命令。
- **SubAgent**：支持启动独立上下文的子 Agent，可后台运行，也可使用指定角色定义。
- **Worktree 隔离**：可为 Agent 创建独立 Git worktree，降低并发修改冲突。
- **Agent Team**：支持持久化 Team、队员邮箱、共享任务列表、`tmux` / `iTerm2` / `in-process` 后端和 `SendMessage` 协作。
- **Coordinator Mode**：可选的协调者模式，用于让 Lead Agent 调度队员、汇总结果并做最终收敛。

## 项目结构

```text
.
├── cowcode/                  # Python 包与项目配置
│   ├── cowcode/              # 源码
│   ├── tests/                # 单元测试
│   └── pyproject.toml
├── docs/                     # 分章节开发文档与验收清单
│   └── ch*/                  # spec / plan / task / checklist
├── CLAUDE.md                 # 项目内 Claude Code 工作说明
├── AGENTS.md                 # Agent 工作说明
└── README.md
```

## 环境要求

- Python 3.11+
- Git
- 可选：`tmux` 或 iTerm2，用于 Agent Team 的 pane 后端；没有时会回退到 `in-process` 后端

## 安装

从仓库根目录执行：

```bash
python -m venv cowcode/.venv
source cowcode/.venv/bin/activate
python -m pip install -e "cowcode[dev]"
```

Windows Git Bash / PowerShell 下也可以直接使用已有 Python 环境：

```bash
python -m pip install -e "cowcode[dev]"
```

## 配置

Cowcode 默认读取 `config.yaml`。项目中的 `cowcode/config.yaml` 被 `.gitignore` 忽略，适合放本地密钥；不要把真实 API Key 提交到仓库。

示例配置：

```yaml
providers:
  - name: Anthropic
    protocol: anthropic
    model: claude-opus-4-8
    api_key: env:ANTHROPIC_API_KEY

# 或使用 OpenAI / OpenAI-compatible 协议
# providers:
#   - name: OpenAI
#     protocol: openai
#     model: gpt-5.4
#     base_url: https://api.openai.com/v1
#     api_key: env:OPENAI_API_KEY

system_prompt: ""

enableSubAgentBackground: true

features:
  coordinator_mode: false
  fork_teammate: false
```

启动前设置环境变量：

```bash
export ANTHROPIC_API_KEY="sk-..."
# 或
export OPENAI_API_KEY="sk-..."
```

## 启动

```bash
cd cowcode
python -m cowcode
```

如果已安装 editable 包，也可以使用脚本入口：

```bash
cowcode
```

查看命令行帮助：

```bash
python -m cowcode --help
```

## 常用 slash 命令

| 命令 | 说明 |
| --- | --- |
| `/help` | 显示可用命令 |
| `/status` | 显示当前运行状态 |
| `/plan` | 切换到计划模式 |
| `/do` | 批准计划并开始执行 |
| `/compact` | 手动压缩当前上下文 |
| `/resume` | 恢复历史会话 |
| `/session` | 显示当前会话信息 |
| `/memory` | 显示已加载记忆文件 |
| `/hooks` | 列出已加载 hooks |
| `/skill` | 列出已加载 Skills |
| `/team list` | 查看 Agent Team |
| `/team info <name>` | 查看 Team 详情 |
| `/team delete <name> [--force]` | 删除 Team |
| `/team kill <member>` | 终止 Team 队员 |

## Agent Team 简介

Agent Team 用于把一个任务拆给多个长期存在的队员 Agent：

1. Lead Agent 创建 Team。
2. Lead 通过 `Agent(team_name="...")` 启动队员。
3. 队员拥有独立会话和 worktree。
4. 队员通过共享任务列表与邮箱通信。
5. Lead 汇总队员结果，必要时用 Git merge 收敛改动。

后端自动检测优先级：

1. 当前在 `$TMUX` 内：使用 `tmux`
2. iTerm2 且存在 `it2`：使用 `iterm2`
3. 系统存在 `tmux`：使用 `tmux`
4. 否则使用 `in-process`

启用 Coordinator Mode 需要同时打开配置和环境变量：

```yaml
features:
  coordinator_mode: true
```

```bash
export MEWCODE_COORDINATOR_MODE=1
```

> 历史文档里可能出现 `mewcode` 命名；当前项目名和 Python 包名是 `cowcode`。

## MCP 配置

Cowcode 会合并用户级和项目级 MCP 配置。配置格式示例：

```yaml
mcp_servers:
  local-tool:
    type: stdio
    command: python
    args: ["-m", "your_mcp_server"]
    env:
      API_KEY: "${YOUR_API_KEY}"
```

HTTP MCP server 示例：

```yaml
mcp_servers:
  remote-tool:
    type: http
    url: https://example.com/mcp
    headers:
      Authorization: "Bearer ${MCP_TOKEN}"
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

- `spec.md`：需求与验收标准
- `plan.md`：实现计划
- `task.md`：任务拆解
- `checklist.md`：验收清单

## 安全注意事项

- 不要提交 `config.yaml`、`.env`、token、证书或任何真实密钥。
- 运行 `bash` / 文件写入类工具前应确认权限规则符合预期。
- Team / Worktree 会在本地创建额外目录，删除前先确认没有未保存改动。

## 许可证

当前仓库尚未声明许可证。发布或对外复用前请先补充 LICENSE。
