---
name: example
description: Demonstrates the Agent Skills format — summarize a text file in the project.
---

# Example skill

Use this skill when the user asks you to summarize a file or explain what a file does.

## Workflow

1. Confirm which file the user wants summarized (or use the path they gave).
2. Call `search_file` if you need to locate symbols or sections quickly.
3. Call `read_file` with a reasonable line window — do not read huge files in one shot.
4. Write a concise summary covering:
   - Purpose of the file
   - Main exports, classes, or entry points
   - Notable dependencies or side effects
5. If the file is too large, summarize by section and offer to drill into a specific part.

## Notes

- Skills live in `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`).
- Add your own skills under `skills/` or set `LM_STUDIO_SKILLS_DIRS` for extra directories.
