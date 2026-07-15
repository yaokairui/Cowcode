# Agent Team Checklist

> 每一项通过运行代码或观察行为来验证,聚焦系统行为而非实现细节。

## 实现完整性

- [ ] `team.Manager` 可被实例化:`team.Manager(home, root, wt_mgr, task_mgr, name_reg)` 返回非 None(验证:`python -c "from mewcode.team import Manager"`、跑单测)
- [ ] `await team.Manager.create("demo", "")` 在 `~/.mewcode/teams/demo/config.json` 落地(验证:运行单测后检查文件存在)
- [ ] `await team.Manager.create("foo bar/baz", "")` sanitize 后路径为 `~/.mewcode/teams/foo-bar-baz/`(验证:单测)
- [ ] 同名 Team 第二次 create 自动后缀 `-2`(验证:单测)
- [ ] `team.BackendType` 三个值齐全:`TMUX` / `ITERM2` / `IN_PROCESS`(验证:`ruff check` 通过 + 单测枚举)
- [ ] `backend.detect()` 在 `$TMUX` 设置时返回 `TMUX`;两环境变量都清空时返回 `IN_PROCESS`(验证:`monkeypatch.setenv` 单测)
- [ ] `mailbox.Box.write` + `mailbox.Box.read` 一进一出消息字段一致(验证:单测)
- [ ] `mailbox` 文件锁在 stale 10 秒后能被新 writer 抢占(验证:单测制造 11 秒前的锁,断言能拿到)
- [ ] `registry.AgentNameRegistry.register("alice", "agent-123")` 后 `resolve("alice")` 返回 `"agent-123"`,`name_of("agent-123")` 返回 `"alice"`(验证:单测)
- [ ] `tasks.Store.create` 返回的 task id 形如 `task_<6 位 hex>`(验证:单测)
- [ ] `await tasks.Store.update(id_, Patch(add_blocked_by=[other]))` 同时给 other 任务的 `blocks` 加上 id(验证:单测断言双向)
- [ ] `await tasks.Store.list_(Filter(status=PENDING))` 返回结果带 `is_ready` 字段,反映 blocked_by 是否全 completed(验证:单测)
- [ ] `coordinator.is_enabled` 在 feature flag 关 + 环境变量开时返回 False(验证:单测 4 种组合)
- [ ] `coordinator.allowed_tools()` 含 `bash` 不含 `write_file` / `edit_file`(验证:单测)
- [ ] `tool.apply_agent_tool_filter(FilterParams(teammate=True, ...))` 返回值含 `TaskCreate` / `SendMessage` 等 5 个协作工具(验证:单测)
- [ ] `tool.apply_agent_tool_filter(FilterParams(teammate=False, ...))` 不含这 5 个工具(验证:单测)
- [ ] 7 个新工具注册到 registry 后,`registry.definitions()` 输出含 `TeamCreate` / `TeamDelete` / `TaskCreate` / `TaskGet` / `TaskList` / `TaskUpdate` / `SendMessage`(验证:单测或启动后 `/status`)
- [ ] `Team.add_member` 与 `Team.set_member_active` 调用前先 `reload_from_disk_locked` 重读 disk(验证:跨进程并发写 disk 时不丢更新——单测制造"Lead 在 alice 子进程读完 config 之后才 add_member"的时序,alice 走 `set_member_active(False)` 后回读 disk 应看到 `is_active=False`)

## 集成

- [ ] `Agent` 工具不带 `team_name` 时走 ch13 原路径,行为不变(验证:`pytest tests/test_agent_tool.py` 全过)
- [ ] `Agent` 工具带 `team_name="demo"` 时调 `team_hook.spawn_teammate`(验证:单测 mock team_hook,断言被调用)
- [ ] `spawn_teammate` 创建 worktree 路径为 `.mewcode/worktrees/team-demo+alice`(验证:单测/集成测试)
- [ ] `spawn_teammate` 后 `team.members` 含 alice,持久化到 `config.json`(验证:单测)
- [ ] in-process 后端的队员 ctx 含 TeammateContext,其 backend_type=in-process;该队员调用 `Agent(team_name=...)` 被拒绝并抛 `InProcessTeammateNoSpawnError`(验证:集成测试)
- [ ] 队员 `Agent.run` 头部读取 mailbox 未读消息,以 `<incoming-messages>` reminder 注入到 LLM 输入(验证:单测,fake mailbox 写消息,捕获 Agent 构造的 prompt)
- [ ] 队员收到 `plan_approval_response(approve=True)` 后 `Agent.permission_mode` 切换到 default(验证:单测 + tmux 实跑——见场景 4)
- [ ] 队员 `run_to_completion` 结束触发 `on_task_done` 回调,Team config 中该成员 `is_active=False`(验证:单测注册回调 + launch noop task)
- [ ] 队员 idle 后 Lead mailbox 收到 `summary="<name> idle"` 消息(验证:单测/集成)
- [ ] `SendMessage(to="alice", ...)` 在 alice 已 stop 且为 in-process 后端时,通过 `task_mgr.send_message` 续派(验证:集成测试,断言 task status 回到 Running);Pane 后端时通过 `backend.wake` 让子进程读 mailbox 自然续派
- [ ] 所有 Team 队员一律 `dont_ask=True`(覆盖角色 frontmatter 的 `permission_mode`),子进程没人能应答 ApprovalRequest 不会卡死(验证:用 `permission_mode: default` 的角色派队员让她调 bash,实跑断言任务正常完成,而不是卡在 Ask)
- [ ] Pane 后端 spawn 时 `initial_prompt` 通过预写入 mailbox(type=text, from=lead)送达,子进程不需要走 CLI 参数(验证:tmux 实跑,在 spawn 完检查 alice mailbox 已有一条 from=lead 的初始任务)
- [ ] Pane 后端子进程命令行含 `--agent-id <id>` 参数(验证:看 `build_member_cmd` 单测;tmux 实跑后 `ps auxww | grep team-member` 看实际命令)
- [ ] Pane 后端的 `python -m mewcode --team-member` 子进程**不启动 TUI**(不构造 Textual App),跑 `run_team_member` 自治协程——读 mailbox → run_to_completion → 通知 Lead idle → stdin Wake 等下一轮(验证:tmux 实跑看 alice pane 显示纯文本日志流而非 Textual TUI 框)
- [ ] Lead mailbox watcher 每秒轮询所有 Team 的 lead.json,把未读消息转 `<team-update>` reminder 推 `pending_reminders` + 给 `lead_mail_event` `set()`(验证:tmux 实跑后看 alice 发完 idle 通知 1 秒内 mailbox 的 unread 归零、read 累加)
- [ ] Lead 在 `SessionState.IDLE` 时收到 `LeadMailMessage`,TUI 调 `begin_autonomous_turn` 合成 user 消息自动开新轮(验证:tmux 实跑——派完队员等他完成,Lead 不需要用户输入就自动出现 `[team-update]...` 行 + Synthesis 回复)
- [ ] `/team list` 输出含 `~/.mewcode/teams/` 下所有 Team(验证:TUI 实跑)
- [ ] `/team delete demo --force` 调 `backend.kill` 杀 pane(tmux/iterm2)+ 清 worktree + 清 team 目录(验证:TUI 实跑后 `tmux list-panes` 只剩 Lead,worktree 与 team 目录都消失)
- [ ] 沙箱开放 `/tmp` 与 `/private/tmp`(macOS 真实路径)作为白名单——write_file/edit_file 可写 `/tmp/foo.txt`,但 `/etc/passwd` 仍拒(验证:单测 `test_sandbox_contains` 含两组用例)

## 编译与测试

- [ ] `python -m mewcode --help` 能正常启动且打印帮助(验证:命令退出码 0)
- [ ] `ruff check src/` 无警告(验证:命令退出码 0)
- [ ] `ruff format --check src/` 无未格式化文件(验证:命令退出码 0)
- [ ] `pytest` 全部通过(验证:命令退出码 0)
- [ ] 可选:`mypy src/mewcode/team/` 全绿
