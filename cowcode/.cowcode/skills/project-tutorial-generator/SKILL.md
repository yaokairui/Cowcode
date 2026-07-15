---
name: project-tutorial-generator
description: Generate structured learning materials from any codebase or project. Use when the user wants to create a learning guide, course outline, or lesson content from a project; asks to "make a tutorial", "create a curriculum", "write lesson content", or "generate learning materials" for a codebase; or wants to study a project systematically with structured documentation.
---

# Project Tutorial Generator

Generate a three-tier learning material set from any project: Learning Guide → Course Outline → Lesson Content.

## Workflow

### Phase 1: Project Exploration

Thoroughly explore the target project to build a complete knowledge map. Use the Explore agent for deep analysis. Gather:

1. **Project overview** — README, package.json, setup files, entry points
2. **Architecture** — directory structure, key modules, data flow
3. **Documentation** — docs, comments, PPTs, wiki, examples
4. **Code details** — core classes, functions, patterns, APIs used
5. **Dependencies** — external libraries, frameworks, services

Output: a comprehensive list of ALL knowledge points, organized by topic.

### Phase 2: Learning Guide

Create `Tutorial/learning-guide.md` with:

- Project overview (1-2 paragraphs)
- Three-phase learning path (beginner → intermediate → advanced)
- Each phase: numbered steps with file references and key concepts
- Concrete study tips ("how to study this")
- Key code files quick-reference table
- Advanced project recommendations if applicable

See [references/learning-guide-template.md](references/learning-guide-template.md) for structure.

### Phase 3: Course Outline

Create `Tutorial/course-outline.md` with N lessons (user specifies N, default 30):

- Organize into logical units (4-6 lessons each)
- Each lesson entry: title, bullet points of concepts, hands-on tasks, file references
- Include an appendix with file index and resource links
- Ensure progressive ordering: concepts build on prior lessons

See [references/course-outline-template.md](references/course-outline-template.md) for structure.

### Phase 4: Lesson Content

Create individual lesson files `Tutorial/lesson-{NN}.md`. For each lesson:

1. Read all source materials referenced in the outline for that lesson
2. Write structured content following the lesson template
3. Save to `Tutorial/lesson-{NN}.md`

Lesson structure (7 sections):
1. **Title & metadata** — lesson title, core goal, file/PPT references
2. **Concept introduction** — explain the "why" before the "how"
3. **Environment/setup** — if needed for this lesson
4. **Core concepts** — detailed explanation with diagrams/tables
5. **Code walkthrough** — line-by-line analysis with annotated code blocks
6. **Hands-on practice** — run commands, test inputs, observation questions
7. **Key takeaways & next lesson preview** — summary table + teaser

See [references/lesson-template.md](references/lesson-template.md) for structure.

## Guidelines

- **Always read source files** before writing about them — never guess content
- Use the project's own examples, code snippets, and terminology
- Keep lessons self-contained but reference prior lessons for prerequisites
- Include `动手实践` (hands-on) sections with concrete commands to run
- Default language: match the project's language; if mixed, use Chinese for explanations
- Place all output in a `Tutorial/` directory at the project root
- Create the directory if it doesn't exist
