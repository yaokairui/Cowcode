---
name: commit
description: 分析 git diff 并生成规范的 commit
allowed_tools:
  - bash
  - read_file
  - grep
mode: inline
---
# Commit Skill

你要帮助用户完成一次谨慎的 Git 提交。

## SOP
1. 运行 `git status --short` 查看工作区状态。
2. 读取相关 diff，优先使用 `git diff --stat` 和 `git diff`。
3. 总结变更意图，识别是否混入无关改动。
4. 如需要提交，先暂存相关文件，再生成简洁、准确的 commit message。
5. 遇到不确定或风险操作，先向用户确认。

## User Request

$ARGUMENTS
