# CLI Agent Implementation Specification

This document contains all gathered context from the codebase needed to implement the plan in `plans/cli-agent-plan.md`. Each step references exact file locations, current code patterns, and specific changes required.

---

## Step 1: Add `--feed` domain filter to database layer

**File:** `database.py`

### 1a. Modify `get_all_feeds()` (line 142)

**Current signature:**
```python
def get_all_feeds(db_path: Path) -> list[dict]:
```

**Current SQL:**
```sql
SELECT * FROM feeds
```

**Change:** Add optional `feed_domain: str | None = None` parameter. When provided, add `WHERE url LIKE '%' || ? || '%'` clause. Use parameterized query (not string interpolation) to prevent SQL injection.

**New signature:**
```python
def get_all_feeds(db_path: Path, feed_domain: str | None = None) -> list[dict]:
```

### 1b. Modify `get_empty_articles()` (line 559)

**Current signature:**
```python
def get_empty_articles(db_path: Path, limit: int = 50) -> list[dict]:
```

**Current SQL:**
```sql
SELECT a.*, f.url as feed_url
FROM articles a JOIN feeds f ON a.feed_id = f.id
WHERE a.content IS NULL AND a.download_failed = 0
ORDER BY a.created_at ASC LIMIT ?
```

**Change:** Add `feed_domain: str | None = None`. When provided, add `AND f.url LIKE '%' || ? || '%'` before `ORDER BY`.

### 1c. Modify `get_unparsed_articles()` (line 505)

**Current signature:**
```python
def get_unparsed_articles(db_path: Path, limit: int = 50) -> list[dict]:
```

**Change:** Same pattern as 1b — add `feed_domain` parameter and conditional WHERE clause.

### 1d. Modify `get_parse_failed_articles()` (line 533)

**Current signature:**
```python
def get_parse_failed_articles(db_path: Path, limit: int = 50) -> list[dict]:
```

**Change:** Same pattern — add `feed_domain` parameter and conditional WHERE clause.

### Domain matching precision

The plan notes a risk about LIKE matching unintended feeds. Use `'%://' || ? || '/%'` pattern for more precise matching (matches `https://domain/...` but not `https://other-domain.com/domain`). Alternatively, extract domain from URL in Python and compare. The simpler `LIKE '%' || ? || '%'` approach is fine for now since feed URLs are curated in `newsfeeds.seed.txt`.

---

## Step 2: Add `--feed` domain filter to CLI commands

### 2a. Add `resolve_feed_ids()` to `commands/_common.py`

**New function:**
```python
def resolve_feed_domain(db_path: Path, domain: str) -> list[int]:
    """Find all feed IDs matching a domain. Returns empty list if none match."""
```

This queries `SELECT id FROM feeds WHERE url LIKE '%' || ? || '%'` and returns the list of IDs. Used for validation — if the list is empty, warn the user.

### 2b. Modify `commands/fetch.py`

**Current `fetch()` signature (line 91):**
```python
def fetch(
    delay: float = typer.Option(DEFAULT_DELAY, "--delay", "-d", ...),
) -> None:
```

**Add:**
```python
feed: str = typer.Option(None, "--feed", help="Filter by feed domain"),
output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
```

**In `_fetch()`:** Pass `feed_domain` to `get_all_feeds()`. If no feeds match the domain, print warning and return.

### 2c. Modify `commands/download.py`

**Current `download()` signature (line 231):**
```python
def download(
    limit: int = typer.Option(10, "--limit", "-l", ...),
    delay: float = typer.Option(1.0, "--delay", "-d", ...),
) -> None:
```

**Add:**
```python
feed: str = typer.Option(None, "--feed", help="Filter by feed domain"),
```

**In `_download()`:** Pass `feed_domain` to `get_empty_articles()`.

### 2d. Modify `commands/parse.py`

**Current `parse()` signature (line 187):**
```python
def parse(
    limit: int = typer.Option(10, "--limit", "-l", ...),
    delay: float = typer.Option(1.0, "--delay", "-d", ...),
    retry: bool = typer.Option(False, "--retry", "-r", ...),
) -> None:
```

**Add:**
```python
feed: str = typer.Option(None, "--feed", help="Filter by feed domain"),
```

**In `_parse()`:** Pass `feed_domain` to both `get_unparsed_articles()` and `get_parse_failed_articles()`.

---

## Step 3: Add `--retry` to download command

**File:** `commands/download.py`

### 3a. Add `--retry` flag to `download()` function

```python
retry: bool = typer.Option(False, "--retry", "-r", help="Retry failed downloads"),
```

### 3b. Add new database functions in `database.py`

**`get_download_failed_articles()`** — new function, mirrors `get_parse_failed_articles()` at line 533:
```python
def get_download_failed_articles(
    db_path: Path, limit: int = 50, feed_domain: str | None = None
) -> list[dict]:
    """Get articles where download_failed = 1."""
```

SQL:
```sql
SELECT a.*, f.url as feed_url
FROM articles a JOIN feeds f ON a.feed_id = f.id
WHERE a.download_failed = 1
[AND f.url LIKE '%' || ? || '%']
ORDER BY a.created_at ASC LIMIT ?
```

**`reset_article_download()`** — new function, mirrors `reset_article_parse()` at line 660:
```python
def reset_article_download(db_path: Path, article_id: int) -> None:
    """Reset download_failed flag and clear download_error for an article."""
```

SQL:
```sql
UPDATE articles
SET download_failed = 0, download_error = NULL
WHERE id = ?
```

### 3c. Modify `_download()` in `commands/download.py`

When `retry=True`, call `get_download_failed_articles()` instead of `get_empty_articles()`. Before processing each article, call `reset_article_download()` (same pattern as `reset_article_parse()` in `commands/parse.py` line 90).

---

## Step 4: Create `articles` command group

**New file:** `commands/articles.py`

### 4a. `articles list` subcommand

```python
articles_app = typer.Typer(help="Manage articles in the database.")

@articles_app.command(name="list")
def list_articles(
    feed: str = typer.Option(None, "--feed", help="Filter by feed domain"),
    status: str = typer.Option(None, "--status", help="Filter: empty|downloaded|parsed|download-failed|parse-failed"),
    limit: int = typer.Option(20, "--limit", "-l"),
    offset: int = typer.Option(0, "--offset", "-o"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
```

**Status filter mapping** (from plan):
| Status | SQL condition |
|--------|---------------|
| `empty` | `content IS NULL AND download_failed = 0` |
| `downloaded` | `content IS NOT NULL AND parsed_at IS NULL AND parse_failed = 0` |
| `parsed` | `parsed_at IS NOT NULL` |
| `download-failed` | `download_failed = 1` |
| `parse-failed` | `parse_failed = 1` |

### 4b. `articles info` subcommand

```python
@articles_app.command(name="info")
def article_info(
    identifier: str = typer.Argument(..., help="Article ID or URL"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
```

Returns `content_length` (NOT content itself). Uses `get_article_by_id()` or `get_article_by_url()` from `database.py`.

### 4c. New database function: `get_articles_paginated()`

```python
def get_articles_paginated(
    db_path: Path,
    limit: int = 20,
    offset: int = 0,
    feed_domain: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    """Return filtered, paginated articles and total count."""
```

Returns `(articles, total_count)` tuple. The total count query runs separately without LIMIT/OFFSET.

### 4d. Register in `main.py`

Add to `main.py` (currently at line 29):
```python
from commands.articles import articles_app
app.add_typer(articles_app, name="articles")
```

---

## Step 5: Simplify CLI output — dual mode (text + `--json`)

### Pattern for every command

Each command follows this pattern:
1. `_impl()` function does the work and returns a `dict`
2. The public `typer` function calls `_impl()`, then either:
   - `--json`: `json.dump(data, sys.stdout, default=str, indent=2)`
   - default: print clean text to stdout
3. Progress/status messages go to `stderr` via `print(..., file=sys.stderr)`

### Files to modify

**`commands/_common.py`** (34 lines currently):
- Remove `from rich.console import Console` and `console = Console(width=120)` at lines 7, 14
- Add JSON output helper:
  ```python
  import json
  import sys
  
  def output_json(data: dict) -> None:
      json.dump(data, sys.stdout, default=str, indent=2)
      print()  # trailing newline
  ```
- Keep `_fmt_date()` and `require_db()` (but update `require_db()` to not use `console.print`)

**`commands/seed.py`** (47 lines):
- Remove Rich `Progress` import and usage
- `_seed()` returns `dict` instead of `None`
- Add `--json` flag
- Progress to stderr: `print(f"Seeding {len(urls)} feed URLs...", file=sys.stderr)`

**`commands/fetch.py`** (108 lines):
- Remove Rich `Progress`, `Table` imports
- `_fetch()` returns `dict` with `{feed_filter, feeds_fetched, entries, valid, success_rate, successful, failed}`
- Add `--json` flag
- Progress to stderr

**`commands/download.py`** (256 lines):
- Remove Rich `Progress` imports
- `_download()` returns `dict` with `{feed_filter, downloaded, failed, total, retry}`
- Add `--json` flag
- Progress to stderr: `print(f"Downloading {i+1}/{len(articles)}...", file=sys.stderr)`

**`commands/parse.py`** (219 lines):
- Remove Rich console usage
- `_parse()` returns `dict` with `{feed_filter, parsed, failed, total, retry, results}`
- Add `--json` flag
- Progress to stderr

**`commands/stats.py`** (306 lines):
- Already has `--json` at line 276 and `_collect_stats()` returns dict
- Replace `_render_rich()` with simple text output
- Change JSON output from `console.print_json()` to `json.dump()` on stdout

**`commands/feeds.py`** (225 lines):
- Remove Rich `Table` imports
- Each `_impl()` returns a dict
- Add `--json` flag to all 4 subcommands
- Keep `typer.confirm()` at line 149 but document `--force` for agent use

### Important: Rich dependency

Rich is NOT listed in `pyproject.toml` dependencies. It is likely pulled in transitively by `typer`. After removing all Rich usage from commands, check if Rich is still needed elsewhere. If not, it can be removed from the project. However, `typer` may still depend on it internally, so leave it unless there is a reason to remove it.

---

## Step 6: Merge file tools into single `read_file`

**File:** `agents/tools/files.py` (490 lines currently)

### Current functions to merge:
1. `get_file_info()` (line 12) — file metadata
2. `get_file_content()` (line 118) — full file read
3. `list_directory()` (line 223) — directory listing
4. `read_file_chunk()` (line 358) — partial file read

### New merged function:

```python
def read_file(
    reason: str,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    metadata_only: bool = False,
) -> str:
    """Read file contents, metadata, or a chunk of a file.
    
    ## Parameters
    - `reason` (str): Why you need to read this file
    - `file_path` (str): Path to the file
    - `offset` (int | None): Line offset for partial reads (default: None = start)
    - `limit` (int | None): Max lines for partial reads (default: None = all)
    - `metadata_only` (bool): Return only file metadata (default: False)
    
    ## Behavior
    - metadata_only=True: Returns file size, type, timestamps (replaces get_file_info)
    - offset=None and limit=None: Read entire file (replaces get_file_content)
    - offset and limit provided: Read chunk (replaces read_file_chunk)
    """
```

### Functions to remove:
- `get_file_info` — merged into `read_file(metadata_only=True)`
- `get_file_content` — merged into `read_file()`
- `read_file_chunk` — merged into `read_file(offset=, limit=)`
- `list_directory` — removed entirely (use `run_shell_command` with `ls`)

### Response format

Keep the same `_safe_json()` response pattern used by all existing tools. The `result` field changes based on mode:
- `metadata_only=True`: `{"name", "size_bytes", "size_mb", "modified", "created", "is_file", "is_directory"}`
- Full read: `{"content": "...", "line_count": N, "size_bytes": N}`
- Chunk read: `{"content": "...", "offset": N, "lines": N, "total_lines": N}`

---

## Step 7: Improve `get_system_info`

**File:** `agents/tools/system.py` (86 lines currently)

### Current return fields:
```python
{
    "working_directory", "python_executable", "python_version",
    "python_version_tuple", "platform", "platform_release",
    "default_shell", "home_directory", "current_datetime",
    "local_datetime", "architecture", "processor"
}
```

### Add news48-specific fields:
```python
{
    # ... existing fields ...
    "news48": {
        "database_path": str,          # from config.Database.path
        "database_exists": bool,
        "database_size_mb": float,     # os.path.getsize if exists
        "env_configured": bool,        # check if .env file exists
        "byparr_configured": bool,     # check if BYPARR_API_URL is set
        "searxng_configured": bool,    # check if SEARXNG_URL is set
        "api_base_configured": bool,   # check if API_BASE is set
    }
}
```

Import `config.Database` and `config.Services` to read configured values. Wrap in try/except since these raise `ValueError` if not configured.

---

## Step 8: Rewrite planner with file-based persistence

**File:** `agents/tools/planner.py` (848 lines currently → replace entirely)

### Current state:
- 7 functions: `create_execution_plan`, `get_execution_plan`, `update_plan_step`, `add_plan_step`, `remove_plan_step`, `replace_plan_step`, `reorder_plan_steps`
- In-memory storage: `_plans: dict[str, Plan] = {}` at line 59
- Uses `Plan` and `PlanStep` dataclasses (lines 27-55)

### New state: 2 functions

**`create_plan()`:**
```python
def create_plan(reason: str, task: str, steps: list[str]) -> str:
    """Create a new execution plan, persist to .plans/{id}.json, return plan JSON."""
```

- Generate UUID for plan ID
- Create `.plans/` directory if not exists
- Write plan JSON to `.plans/{plan_id}.json`
- Return `_safe_json()` response with plan data

**`update_plan()`:**
```python
def update_plan(
    reason: str,
    plan_id: str,
    step_id: str,
    status: str,  # pending | in_progress | completed | failed
    result: str = "",
    add_steps: list[str] | None = None,
    remove_steps: list[str] | None = None,
) -> str:
    """Update a step status and optionally add/remove steps. Returns updated plan JSON."""
```

- Read plan from `.plans/{plan_id}.json`
- Update step status/result
- Optionally add/remove steps
- Write back to file
- Return updated plan JSON

### Plan file schema:
```json
{
    "id": "uuid",
    "task": "description",
    "status": "in_progress",
    "created_at": "ISO8601",
    "updated_at": "ISO8601",
    "steps": [
        {
            "id": "step-N",
            "description": "...",
            "status": "pending|in_progress|completed|failed",
            "result": null,
            "created_at": "ISO8601",
            "updated_at": "ISO8601"
        }
    ]
}
```

### Functions to remove (all 7 old planner functions):
- `create_execution_plan`
- `get_execution_plan`
- `update_plan_step`
- `add_plan_step`
- `remove_plan_step`
- `replace_plan_step`
- `reorder_plan_steps`

### Dataclasses to remove:
- `StepStatus` enum
- `PlanStep` dataclass
- `Plan` dataclass
- `_plans` global dict
- All helper functions: `_update_timestamp`, `_no_active_plan_error`, `_serialize_step`, `_serialize_plan`, `_get_current_plan`, `_requires_plan`

---

## Step 9: Create CLI reference document

**New file:** `agents/instructions/cli-reference.md`

Content should include:
- Complete CLI command reference with all flags
- Pipeline stage descriptions and ordering
- JSON output schemas for each command (from plan Section 3)
- Article statuses and `--status` filter values
- Per-feed operations with `--feed` domain filter
- Common workflows organized by role (Pipeline Operator, System Monitor, Troubleshooter, Fact Checker)
- Note about `--force` flag for delete (no interactive prompts)
- Background process spawning pattern with `.logs/` directory

---

## Step 10: Create CLI agent instructions

**New file:** `agents/instructions/cli-operator.md`

Based on the existing `agents/instructions/operator.md` (136 lines) but adapted for the CLI agent role:

Key differences from current operator instructions:
- **4 roles** instead of general-purpose: Pipeline Operator, System Monitor, Troubleshooter, Fact Checker
- **Critical rule**: never run the full pipeline at once — always stage by stage
- Always pass `--json` flag for machine-readable output
- `articles info` returns metadata only — use `read_file` on temp files for content
- Planning is mandatory for multi-step tasks (same as current operator)
- Uses `create_plan` / `update_plan` (new 2-tool planner) instead of 7-tool planner
- References `cli-reference.md` for command details
- Teaches background process spawning pattern with `.logs/` directory
- Teaches `perform_web_search` → `fetch_webpage_content` workflow for fact-checking

---

## Step 11: Create CLI agent entry point

**New file:** `agents/cli_operator.py`

Based on existing `agents/operator.py` (109 lines):

```python
async def main(user_prompt: str):
    load_dotenv()
    
    from agents.tools import (
        run_shell_command,
        read_file,
        perform_web_search,
        fetch_webpage_content,
        get_system_info,
        create_plan,
        update_plan,
    )
    
    agent = FunctionAgent(
        name="CLI Operator",
        description="A news48 pipeline worker agent...",
        llm=OpenAILike(...),
        tools=[
            run_shell_command,
            read_file,
            perform_web_search,
            fetch_webpage_content,
            get_system_info,
            create_plan,
            update_plan,
        ],
        system_prompt=load_agent_instructions("cli-operator"),
        verbose=False,
        streaming=True,
    )
    # ... streaming event handling (same pattern as operator.py)
```

**Key differences from `agents/operator.py`:**
- 7 tools instead of 15
- Uses `cli-operator` instructions instead of `operator`
- Different agent name and description
- Same streaming event handling pattern

---

## Step 12: Update `agents/tools/__init__.py`

**Current exports (38 lines):**
```python
from .bypass import fetch_webpage_content
from .files import (get_file_content, get_file_info, list_directory, read_file_chunk)
from .planner import (add_plan_step, create_execution_plan, get_execution_plan,
                      remove_plan_step, reorder_plan_steps, replace_plan_step,
                      update_plan_step)
from .searxng import perform_web_search
from .shell import run_shell_command
from .system import get_system_info
```

**New exports:**
```python
from .bypass import fetch_webpage_content
from .files import read_file
from .planner import create_plan, update_plan
from .searxng import perform_web_search
from .shell import run_shell_command
from .system import get_system_info
```

**Removed exports:**
- `get_file_content`, `get_file_info`, `list_directory`, `read_file_chunk` (merged into `read_file`)
- `add_plan_step`, `create_execution_plan`, `get_execution_plan`, `remove_plan_step`, `reorder_plan_steps`, `replace_plan_step`, `update_plan_step` (replaced by `create_plan`, `update_plan`)

---

## Step 13: Update `.gitignore`

**Current `.gitignore`** (19 lines). Add:
```
.plans/
.logs/
```

---

## Step 14: Update `docs/agents-tools-inventory.md`

Update the tools inventory document to reflect:
- Merged `read_file` tool (replacing 4 file tools)
- New `create_plan` and `update_plan` tools (replacing 7 planner tools)
- Updated `get_system_info` with news48-specific fields
- Removed tools: `get_file_content`, `get_file_info`, `list_directory`, `read_file_chunk`, all 7 old planner tools
- Final tool count: 7 tools (down from 15)

---

## Implementation Order

The steps have dependencies. Recommended execution order:

1. **Database layer first** (Steps 1, 3b, 4c) — all new/modified DB functions
2. **Shared utilities** (Step 2a, Step 5 `_common.py` changes) — `resolve_feed_domain()`, JSON helpers
3. **CLI commands** (Steps 2b-2d, 3a/3c, 4a-4d, Step 5 command changes) — all command modifications
4. **Agent tools** (Steps 6, 7, 8) — file tools merge, system info, planner rewrite
5. **Agent instructions and entry point** (Steps 9, 10, 11) — new markdown files and cli_operator.py
6. **Wiring** (Steps 12, 13, 14) — exports, gitignore, docs

---

## Key Patterns to Follow

### Tool response format
All tools use `_safe_json()` from `agents/tools/_helpers.py`. Every tool returns a JSON string with:
```python
{
    "result": ...,       # The actual data
    "error": "",         # Empty on success
    "metadata": {
        "timestamp": "...",
        "reason": "...",
        "params": {...},
        "operation": "function_name",
        "success": True/False
    }
}
```

### CLI output pattern
Every command follows:
```python
def _impl(...) -> dict:
    """Do the work, return data dict. Print progress to stderr."""
    ...

def command(..., output_json: bool = False):
    data = asyncio.run(_impl(...))
    if output_json:
        json.dump(data, sys.stdout, default=str, indent=2)
        print()
    else:
        print(f"Human readable: {data['key']}")
```

### Database function pattern
All DB functions use `get_connection()` context manager and return `list[dict]` or `dict | None`:
```python
def get_xxx(db_path: Path, ...) -> list[dict]:
    with get_connection(db_path) as db:
        cursor = db.execute("SELECT ...", (...))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
```

### Agent instructions loading
Instructions are loaded via `load_agent_instructions("cli-operator")` from `agents/instructions/__init__.py`, which reads `agents/instructions/cli-operator.md` and resolves template variables `{{PYTHON_BIN}}` and `{{SCRIPT_DIR}}`.
