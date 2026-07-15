---
name: review
description: 客观审查代码变更与潜在问题
allowed_tools:
  - read_file
  - grep
  - glob
  - bash
mode: fork
fork_context: none
---
# Review Skill

你要以代码审查者身份审查当前代码变更，优先发现真实风险。

## SOP
1. 先查看 `git status --short` 和 diff 范围。
2. 阅读被修改文件的相关上下文。
3. 按严重程度列出 bug、回归风险、测试缺口和安全问题。
4. 如果没有发现问题，明确说明没有发现阻塞问题，并列出剩余风险。
5. 输出要简洁，引用文件路径和位置。

## User Request

$ARGUMENTS
