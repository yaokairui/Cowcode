# Project Tutorial Generator

[English](#english) | [中文](#中文)

---

<a id="english"></a>

## English

A Claude Code skill that generates structured learning materials from any codebase.

### What It Does

Generates a three-tier learning material set from any project:

1. **Learning Guide** — A high-level roadmap with beginner, intermediate, and advanced phases
2. **Course Outline** — A detailed N-lesson curriculum organized into logical units
3. **Lesson Files** — Individual lesson files with structured content, code walkthroughs, and hands-on exercises

All output is written to a `Tutorial/` directory at the project root.

### Installation

#### Using skills CLI (recommended)

```bash
npx skills add yaokairui/project-tutorial-generator -g
```

#### Manual installation

```bash
git clone https://github.com/yaokairui/project-tutorial-generator.git \
  ~/.claude/skills/project-tutorial-generator
```

### Usage

Activate the skill with any of these trigger phrases:

- "make a tutorial for this project"
- "create a curriculum for this codebase"
- "generate learning materials"
- "write lesson content"

You can specify the number of lessons (default is 30):

> Generate a 15-lesson course for this codebase

Claude will then go through 4 phases:

1. Explore the project structure and source code
2. Generate a learning guide
3. Generate a course outline
4. Generate individual lesson files

**Tip:** Before generating a tutorial, you can quickly browse the project on DeepWiki to get an overview. Just replace `github` with `deepwiki` in the repo URL — for example, `https://deepwiki.com/yaokairui/project-tutorial-generator`.

#### Output Structure

```
Tutorial/
├── learning-guide.md
├── course-outline.md
├── lesson-01.md
├── lesson-02.md
└── ...
```

### How It Works

This is a pure markdown skill — no code, no dependencies. The `SKILL.md` file contains instructions that Claude Code follows, and the `references/` directory contains templates for the generated documents.

### Language

The built-in templates use Chinese section headers by default. The skill will match the target project's language — if the project is in English, the output will be in English.

### License

[MIT](LICENSE)

---

<a id="中文"></a>

## 中文

一个 Claude Code skill，能从任意代码库生成结构化学习材料。

### 功能介绍

从任意项目生成三层学习材料：

1. **学习指南** — 涵盖入门、进阶、高级三个阶段的学习路线图
2. **课程大纲** — 按逻辑单元组织的 N 节课详细课程表
3. **课程文件** — 每节课的独立文件，包含结构化内容、代码走读和动手实践

所有输出写入项目根目录的 `Tutorial/` 目录。

### 安装方式

#### 使用 skills CLI（推荐）

```bash
npx skills add yaokairui/project-tutorial-generator -g
```

#### 手动安装

```bash
git clone https://github.com/yaokairui/project-tutorial-generator.git \
  ~/.claude/skills/project-tutorial-generator
```

### 使用方法

用以下任意短语激活 skill：

- "为这个项目生成教程"
- "给这个代码库创建课程"
- "生成学习材料"
- "写课程内容"

可以指定课程数量（默认 30 节）：

> 为这个代码库生成 15 节课

Claude 会依次执行 4 个阶段：

1. 探索项目结构和源码
2. 生成学习指南
3. 生成课程大纲
4. 逐节生成课程文件

**提示：** 在生成教程之前，你可以用 DeepWiki 快速浏览项目全貌。只需把仓库地址里的 `github` 替换成 `deepwiki` 即可打开 —— 例如 `https://deepwiki.com/yaokairui/project-tutorial-generator`。

#### 输出结构

```
Tutorial/
├── learning-guide.md
├── course-outline.md
├── lesson-01.md
├── lesson-02.md
└── ...
```

### 工作原理

这是一个纯 markdown skill —— 无代码、无依赖。`SKILL.md` 包含 Claude Code 遵循的指令，`references/` 目录包含生成文档所用的模板。

### 语言说明

内置模板默认使用中文章节标题。skill 会自动匹配目标项目的语言 —— 如果项目是英文的，输出也会是英文。

### 许可证

[MIT](LICENSE)
