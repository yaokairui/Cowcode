---
name: test
description: 运行项目测试并分析失败原因
allowed_tools:
  - bash
  - read_file
  - grep
  - glob
mode: inline
---
# Test Skill

你要帮助用户运行项目测试并解释结果。

## SOP
1. 识别项目类型和可用测试命令。
2. 优先运行最相关、成本最低的测试。
3. 测试失败时读取错误上下文并定位原因。
4. 如果需要修复，先说明判断依据，再做最小改动。
5. 最后报告实际运行的命令和结果。

## User Request

$ARGUMENTS
