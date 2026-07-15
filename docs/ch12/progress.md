# Hook 生命周期挂钩系统 - 开发进度

> 最后更新: 2026-07-14

## 已完成

### 阶段一：permission Matcher 扩展（T1-T5）
- [x] `permission/matcher.py` — Matcher Protocol + ExactMatcher / GlobMatcher / RegexMatcher / NotMatcher + `compile_matcher` 工厂
- [x] `permission/__init__.py` — `Rule` 从 `pattern: str` 改为 `matcher: Matcher | None`，新增 `parse_rule` / `match_rule`
- [x] `permission/settings.py` — `to_rule_set` 失败时 stderr 打印错误，其余规则不受影响
- [x] `tests/test_permission_matcher.py` — 4 种类型 × 命中/不命中 + 边界条件，表驱动
- [x] `tests/test_permission_rule.py` — exact/regex/not/glob/backwards-compat 测试
- [x] `tests/test_permission_settings.py` — stderr `parse failed` 验证
- **验证：** `pytest ... -q` → 25 passed

### 阶段二：hook 包基础（T6-T11）
- [x] `hook/__init__.py` — 包标识 + re-export `Engine / Event / load / DispatchResult`
- [x] `hook/event.py` — 11 个 Event 枚举 + `is_blocking` / `parse_event`
- [x] `hook/rule.py` — Rule / Condition / AtomCondition / Action 系列 dataclass / 枚举
- [x] `hook/matcher.py` — `get_by_path` / `eval_condition`（字段路径求值 + all_of/any_of 组合）
- [x] `hook/loader.py` — YAML 解析、双层合并、字段校验、async/拦截冲突检测
- [x] `hook/engine.py` — Engine + dispatch 主流程 + only_once + 锁
- [x] `hook/executor.py` — 四类动作执行器（shell/http/prompt/subagent）
- [ ] 对应测试文件尚未创建/运行（T9/T12/T13 待补）

### 阶段三：agent + runtime 接入（T14-T17，进行中）
- [x] `runtime.py` — `SessionRuntime` 新增 `pending_reminders`、`hook_engine`、`reset_for_new_session`/`append_reminders`/`take_reminders`
- [x] `agent.py` — `__init__` 加 `hook_engine` 参数、`_dispatch_hook`/`_build_reminder`/`_base_payload`/`_pre_tool_hook_result`/`_post_tool_hook`
- [x] `agent.py` — `_stream_once` 接入 `PreUserMessage`、`_execute_batched` 接入 `PreToolUse`/`PostToolUse`、`run` 末尾接入 `Stop`
- [x] `agent.py` — reminder 注入路径：`_build_reminder` 取 `take_reminders()` 拼到 plan reminder 后
- [ ] `tests/test_hook_engine.py` / `tests/test_hook_executor.py` 尚未创建
- [ ] `test_agent.py` 中 hook 拦截路径测试尚未编写

### 阶段四：TUI + CLI wiring（T18-T22，进行中）
- [x] `cli.py` — `CowcodeApp` 新增 `hook_engine` 参数、`hook_sources`/`hook_rules` 方法
- [x] `cli.py` — `on_mount()` 末尾派发 `SessionStart`
- [x] `cli.py` — `_handle_send()` 中 `UserPromptSubmit` 拦截
- [x] `cli.py` — `clear_and_new_session()` 内 `SessionEnd` → reset → `SessionStart`
- [x] `cli.py` — `_amain()` 中 `hook.load(root)` + `hook_engine` 透传 + 退出兜底 `SessionEnd`
- [x] `command/builtins.py` — `/hooks` 命令注册
- [x] `command/builtin_hooks.py` — `/hooks` handler（按 event 分组输出）
- [x] `command/ui.py` — `UI` 协议新增 `hook_sources`/`hook_rules` + `clear_and_new_session` 改为 async
- [x] `command/builtin_ui.py` — `handle_clear` 改为 await
- [ ] TUI 测试尚未编写

## 待完成

### 测试补全
- [ ] `tests/test_hook_loader.py` — 合法 YAML、字段缺失、async+拦截冲突、跨文件同名、非法正则
- [ ] `tests/test_hook_engine.py` — 多 rule 顺序、拦截中断、non-blocking 不拦截、only_once、reset
- [ ] `tests/test_hook_executor.py` — shell exit 0/1/2、timeout、prompt、http block、subagent stub
- [ ] `tests/test_agent.py` — hook 拦截路径、reminder 注入验证

### 整体验证
- [ ] `pytest` 全量通过（当前只跑了 permission + runtime）
- [ ] `ruff check` 通过
- [ ] 修复 ch08/ch11 老测试回归（T24）
- [ ] tmux 端到端实跑（T25）

### 已知问题
1. `agent.py` 中有重复的 `_build_reminder`/`_dispatch_hook`/`_base_payload` 方法（编辑时重复插入），需清理
2. `cli.py` 中有重复的 `_dispatch_session_start`/`_dispatch_session_end`/`_dispatch_hook` 方法，需清理
3. `cli.py` 中有重复的 `_dispatch_user_prompt_submit` 方法，需清理
4. `SessionContext` 无 `.id` 属性，全部改为 `.session_id`
5. `SessionRuntime.reset_for_new_session` 从同步改为异步，但 `clear_and_new_session` 已改为 await，需确认所有调用方都已 await
