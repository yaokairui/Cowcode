# slash命令体系 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为；不依赖具体实现细节。

## 实现完整性

- [ ] /help 输出含 12 条命令名/描述(验证:`pytest -k test_register_builtins_all_registered tests/test_command_builtins.py` 绿 + tmux 场景 A2)
- [ ] /plan 不调用 `conv.add_user`、不触发 LLM 回合(验证:`pytest -k test_tui_dispatch_plan_local_only tests/test_tui.py` 绿)
- [ ] /do 触发 LLM 回合且写入会话存档(验证:`pytest -k test_tui_dispatch_do_injects_and_sends tests/test_tui.py` 绿 + tmux 场景 D2 后 `tail -3 $SESSIONS_DIR/<latest>.jsonl` 含新增 `"role":"user"` 记录)
- [ ] `register_builtins(reg)` 注册了恰好 12 条命令(验证:`pytest -k test_register_builtins_all_registered tests/test_command_builtins.py` 绿)
- [ ] 12 条命令的名字完整、命令名全小写、互不重复(验证:同上 + 看 test 断言列表)

## 注册中心行为

- [ ] 名字冲突立即 `raise RuntimeError`;异常消息含具体冲突名(验证:`pytest -k test_register_duplicate_name tests/test_command_registry.py` 绿)
- [ ] 别名冲突立即 `raise RuntimeError`;异常消息含具体冲突别名(验证:`pytest -k test_register_duplicate_alias tests/test_command_registry.py` 绿)
- [ ] `visible()` 返回按 name 字典序排序的可见命令(验证:`pytest -k test_visible_sorted tests/test_command_registry.py` 绿)
- [ ] `prefix_match("/s")` 仅命中以 "s" 开头的命令名,不含别名匹配、不含描述匹配(验证:`pytest -k test_prefix_match tests/test_command_registry.py` 绿)
- [ ] `parse("/Help")` 返回 `("help", True)`;`parse("")` 与 `parse("hello")` 返回 `("", False)`;`parse("/help xx")` 返回 `("", True)`(尾随参数让 lookup miss 走未命中分支);`parse("/ /help")` 返回 `("", True)`(验证:`pytest -k test_parse tests/test_command_dispatch.py` 绿)

## 命令分发与三类执行

- [ ] 提交 `/help` 后输出 12 行命令名/描述,且不调用 `conv.add_user`、不触发 LLM 回合(验证:`pytest -k test_tui_dispatch_help_lists_all_builtins tests/test_tui.py` 绿)
- [ ] 提交未知命令 `/foobar` 后输出文本含子串 "未知命令" 与 "/help" 两个关键字;不触发 LLM 回合(验证:`pytest -k test_tui_unknown_slash_command_friendly tests/test_tui.py` 绿)
- [ ] 提交 `/Help`(大小写混合)与 `/help` 行为一致(验证:`pytest -k test_tui_dispatch_case_insensitive tests/test_tui.py` 绿)
- [ ] 空字符串/纯空白字符提交时既不进 LLM 也不进分发器(验证:人工跑 tmux 场景"空回车"看无任何输出新增)
- [ ] /do 提交后会向 `conv.add_user` 追加文本"请按上面的计划开始执行。"且立即触发 LLM 回合(验证:`pytest -k test_tui_dispatch_do_injects_and_sends tests/test_tui.py` 绿 或 tmux 场景观察)
- [ ] /review 提交后会向 `conv.add_user` 追加文本含子串"审查"且立即触发 LLM 回合(验证:同上)
- [ ] /compact 在 `IDLE` 触发 `Agent.run_force_compact`;非 idle 状态打印"请等待当前任务完成"(验证:既有 test_tui_slash_compact_routes_to_command 迁移版 + 非 idle 情况新加用例)
- [ ] handler 抛异常时,用户看到 `error_block` 文案(验证:在单测中 mock 一个抛异常的 handler,断言 `app._pending_println` 含 `ERROR` 前缀)

## 12 条命令的具体输出

- [ ] /help 输出包含完整字符串 `/help`、`/status`、`/memory`、`/permission`、`/session`、`/clear`、`/review`、`/exit`、`/plan`、`/do`、`/compact`、`/resume` 共 12 个名字(验证:tmux 场景截屏 grep)
- [ ] /status 输出按顺序包含 6 行,每行 key 分别为 `Mode:`、`Tokens:`、`Tools:`、`Memories:`、`Model:`、`Directory:`(验证:`tmux capture-pane -p` 后按行 grep)
- [ ] /memory 输出在 `MEMORY.md` 存在时至少列出 "MEMORY.md" 这个文件名(验证:tmux 场景观察)
- [ ] /permission 输出当前 mode 的 `value`(default/plan/acceptEdits/bypassPermissions 之一)(验证:tmux 场景对照状态栏徽章)
- [ ] /session 输出至少 2 行,key 分别为 `Session:` 与 `Path:`(验证:tmux 场景截屏 grep)
- [ ] /clear 后状态栏 Tokens 区域消失或显示 0;旧会话 JSONL 文件仍在磁盘上(验证:tmux 场景 + `ls $SESSIONS_DIR/`)

## 自动补全菜单

- [ ] 输入框首字符输入 `/` 后,菜单立即激活并显示 12 条候选(验证:tmux 场景按 `/` 后 `capture-pane`)
- [ ] 继续输入 `s`(输入框为 `/s`)后,菜单只剩 /session 和 /status(验证:tmux 场景)
- [ ] 把输入框清空(全部退格)后菜单立即消失(验证:tmux 场景)
- [ ] 按 ↓ 高亮下移、↑ 高亮上移;按 ESC 菜单消失且输入框文本保留(验证:tmux 场景)
- [ ] 高亮 /status 后按回车,菜单消失、/status 立即执行、输入框清空(验证:tmux 场景)
- [ ] 高亮 /session 后按 Tab,菜单消失、/session 立即执行(验证:tmux 场景)
- [ ] 按 `/` 显示 12 条候选时,菜单可见行数 ≤ 8;按 ↓ 越过第 8 行后下方候选滚入视野
- [ ] 菜单不显示 `hidden=True` 的命令(本期没有 hidden 命令;通过单测验证机制:在 test_command_registry 中注册一条 `hidden=True` 看 `visible()` 不含它)

## 集成

- [ ] /help、未命中提示、`prompt.READY_HINT` 三处均不出现硬编码命令清单(验证:`grep -rE "/(exit|plan|do|compact|resume|help|clear|review|status|memory|permission|session)" src/mewcode/prompt.py src/mewcode/tui/commands.py` 应只在新分发器代码内出现一次类型常量)
- [ ] 状态栏左侧 mode 徽章渲染与本 spec 实施前完全一致(验证:`git diff main -- src/mewcode/tui/view.py | grep -E "(mode_label|mode_status_style|status_bar)"` 应无内部逻辑变更)
- [ ] /resume、/compact 沿用 ch09 的 `SessionState.IDLE` 限制(验证:T10 后跑既有 ch09 验收场景一遍)

## 编译与测试

- [ ] `python -m mewcode` 在合法配置下能正常启动 TUI
- [ ] `pytest -q` 全部通过
- [ ] `ruff check .` 无告警
- [ ] `ruff format --check .` 通过(或本地 `ruff format .` 已统一格式)
- [ ] (可选)`mypy src/mewcode` 通过

## 启动期冲突检测

- [ ] 在 `builtins.py` 中临时把某条命令注册两次,`python -m mewcode` 立即抛 `RuntimeError` 退出,异常文本含具体冲突的命令名(验证:人工临时改动 + 跑 mewcode + 还原)

## 完成准则

- 上面所有 checkbox 全部勾选,且每一项的"验证"步骤已实际执行并记录证据
- `git status` 无未跟踪/未提交的临时调试改动(冲突检测的 builtins.py 临时改动已还原)
```