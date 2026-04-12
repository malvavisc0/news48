# Skill: require JSON command output

## Trigger
Always active — all agents must use structured JSON output.

## Rules
1. Pass `--json` flag to every `news48` CLI command.
2. Parse JSON output before using any value in decisions.
3. Never assume a command succeeded without checking JSON result.
