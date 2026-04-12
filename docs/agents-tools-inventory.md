# Agents Tools Inventory

This document provides an inventory of all tools available to agents in the news48 system.

## Overview

Tools are organized into the following modules:

| Module | File |
|--------|------|
| [`bypass`](../agents/tools/bypass.py) | Webpage content fetching with anti-bot bypass |
| [`email`](../agents/tools/email.py) | Email delivery for monitoring reports |
| [`files`](../agents/tools/files.py) | Unified file reading (content, metadata, chunks) |
| [`planner`](../agents/tools/planner.py) | Persistent execution plan management |
| [`searxng`](../agents/tools/searxng.py) | Web search via SearXNG |
| [`shell`](../agents/tools/shell.py) | Shell command execution |
| [`system`](../agents/tools/system.py) | System and news48 environment information |
| [`_helpers`](../agents/tools/_helpers.py) | Shared utility functions |

---

## Tool Specifications

### 1. Bypass Module

#### `fetch_webpage_content`

Fetches webpage content from a list of URLs using bypass solutions to handle anti-bot protection.

**Signature:**
```python
async def fetch_webpage_content(
    reason: str, urls: list[str], markdown: bool = True
) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Explanation of why the URLs need to be fetched |
| `urls` | `list[str]` | Required | List of webpage URLs to fetch |
| `markdown` | `bool` | `True` | Convert content to markdown |

**Returns:** JSON string containing:
- `result.results`: List of successful fetches with URL and content
- `result.errors`: List of failed fetches with error details
- `error`: Empty on success, or summary message on failure

---

### 2. Email Module

#### `send_email`

Send an email report. Used by the Monitor agent for delivering alerts.

**Signature:**
```python
def send_email(
    reason: str,
    to: str = "",
    subject: str = "",
    body: str = "",
) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Why you are sending this email |
| `to` | `str` | `""` | Recipient email (defaults to `MONITOR_EMAIL_TO` env var) |
| `subject` | `str` | `""` | Email subject line |
| `body` | `str` | `""` | Plain-text email body |

**Returns:** JSON string with:
- `result`: `"sent"` on success
- `error`: Empty on success, or error description

**Requires:** `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, and either `to` param or `MONITOR_EMAIL_TO` env var.

---

### 3. Files Module

#### `read_file`

Unified file reading tool that replaces the previous `get_file_info`, `get_file_content`, `read_file_chunk`, and `list_directory` tools.

**Signature:**
```python
def read_file(
    reason: str,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    metadata_only: bool = False,
) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Explanation of why you need to read this file |
| `file_path` | `str` | Required | Path to the file |
| `offset` | `int \| None` | `None` | Line offset for partial reads |
| `limit` | `int \| None` | `None` | Max lines for partial reads |
| `metadata_only` | `bool` | `False` | Return only file metadata |

**Behavior:**
- `metadata_only=True`: Returns file size, type, timestamps
- `offset=None, limit=None`: Read entire file
- `offset` and `limit` provided: Read a chunk of lines

**Returns:** JSON string with:
- `result`: File content dict, metadata dict, or chunk dict depending on mode
- `error`: Empty on success, or error description

---

### 4. Planner Module

#### `create_plan`

Create a new execution plan, persisted to `.plans/{id}.json`. Includes built-in duplicate detection and pipeline dependency inference.

**Signature:**
```python
def create_plan(
    reason: str,
    task: str,
    steps: list[str],
    success_conditions: list[str],
    parent_id: str = "",
    plan_kind: str = "execution",
    scope_type: str = "",
    scope_value: str = "",
    campaign_id: str = "",
) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Why planning is needed |
| `task` | `str` | Required | Overall task description (non-empty) |
| `steps` | `list[str]` | Required | Ordered list of step descriptions |
| `success_conditions` | `list[str]` | Required | Non-empty list of verifiable outcome statements |
| `parent_id` | `str` | `""` | Optional parent plan ID for sequencing |
| `plan_kind` | `str` | `"execution"` | Plan type: `execution` or `campaign` |
| `scope_type` | `str` | `""` | Optional scope key (e.g., `feed`) |
| `scope_value` | `str` | `""` | Optional scope value (e.g., a feed domain) |
| `campaign_id` | `str` | `""` | Optional grouping plan ID for related child plans |

**Validation:**
- `task` must be a non-empty string (whitespace-only is rejected)
- `success_conditions` must be a non-empty list with all non-blank entries
- Duplicate detection prevents creating plans with the same family, scope, and parent

**Returns:** JSON string with:
- `result`: Plan object with id, task, success_conditions, steps, progress
- `error`: Empty on success, or validation error message

#### `update_plan`

Update a step status and optionally add/remove steps or change the plan status.

**Signature:**
```python
def update_plan(
    reason: str,
    plan_id: str,
    step_id: str,
    status: str,
    result: str = "",
    add_steps: list[str] | None = None,
    remove_steps: list[str] | None = None,
    plan_status: str = "",
) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Why you are updating this step |
| `plan_id` | `str` | Required | ID from `create_plan` response |
| `step_id` | `str` | Required | ID of the step to update (e.g., "step-1") |
| `status` | `str` | Required | One of: `pending`, `executing`, `completed`, `failed` |
| `result` | `str` | `""` | Optional outcome message |
| `add_steps` | `list[str] \| None` | `None` | Optional steps to append |
| `remove_steps` | `list[str] \| None` | `None` | Optional step IDs to remove |
| `plan_status` | `str` | `""` | Optional explicit plan status override |

**Step status transitions:**
- `pending` → `pending`, `executing`, `completed`, `failed`
- `executing` → `executing`, `completed`, `failed`
- `completed` → `completed` (idempotent only)
- `failed` → `failed` (idempotent only)

**Returns:** JSON string with:
- `result`: Updated plan with all steps and progress
- `error`: Empty on success, or error description

#### `claim_plan`

Find and claim the oldest eligible pending plan. Atomically selects and claims one plan so no other executor can grab the same plan.

**Signature:**
```python
def claim_plan(reason: str) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Why you are claiming a plan |

**Eligibility rules:**
- Plan status must be `pending`
- Plan kind must not be `campaign`
- No `parent_id`, or parent plan status is `completed`
- Stale executing plans are automatically requeued before claiming

**Returns:** JSON string with:
- `result`: The claimed plan object (status set to `executing`), or `{"status": "no_eligible_plans", "message": "..."}` when nothing can be claimed
- `error`: Empty on success

#### `list_plans`

List all plans, optionally filtered by status. Used by the Planner to check for existing work before creating new plans.

**Signature:**
```python
def list_plans(reason: str, status: str = "") -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Why you are listing plans |
| `status` | `str` | `""` | Optional filter: `pending`, `executing`, `completed`, `failed`, or comma-separated |

**Returns:** JSON string with:
- `result`: List of plan summaries (plan_id, task, status, parent_id, total_steps, created_at, updated_at, stale, requeue_count)
- `error`: Empty on success

---

### 5. SearXNG Module

#### `perform_web_search`

Search the web via SearXNG and return normalized results.

**Signature:**
```python
def perform_web_search(
    reason: str,
    query: str,
    category: str = "general",
    time_range: str = "",
    pages: int = 3,
) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Why you need these search results |
| `query` | `str` | Required | Search query text |
| `category` | `str` | `"general"` | Result type: general, news, images, videos, files |
| `time_range` | `str` | `""` | Freshness filter: day, week, month, year, or "" |
| `pages` | `int` | `3` | Number of result pages to fetch |

**Returns:** JSON string with:
- `result.count`: Number of results
- `result.findings`: Array of normalized results
- `result.page_stats`: Requested/succeeded/failed page counts

**Note:** Requires `SEARXNG_URL` environment variable.

---

### 6. Shell Module

#### `run_shell_command`

Execute a shell command and return its output. All `news48` invocations are automatically resolved to use the current Python interpreter.

**Signature:**
```python
def run_shell_command(
    reason: str, command: str, timeout: Optional[int] = 120
) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Why you need to run this command |
| `command` | `str` | Required | Shell command to execute |
| `timeout` | `int` | `120` | Max seconds to wait |

**Returns:** JSON string with:
- `result.working_dir`: Current directory
- `result.stdout`: Standard output
- `result.stderr`: Standard error
- `result.return_code`: Exit code (0 = success)
- `result.execution_time`: Time taken in seconds

---

### 7. System Module

#### `get_system_info`

Get system and runtime environment information, including news48-specific configuration status.

**Signature:**
```python
def get_system_info() -> str
```

**Returns:** JSON string with:
- `result.working_directory`: Current working directory
- `result.python_executable`: Path to Python interpreter
- `result.python_version`: Version string
- `result.platform`: OS name
- `result.platform_release`: OS release version
- `result.default_shell`: Default shell path
- `result.home_directory`: Home directory path
- `result.current_datetime`: UTC timestamp
- `result.local_datetime`: Local timestamp
- `result.architecture`: Machine architecture
- `result.news48.database_path`: Configured database path
- `result.news48.database_exists`: Whether the database file exists
- `result.news48.database_size_mb`: Database file size in MB
- `result.news48.env_configured`: Whether `.env` file exists
- `result.news48.byparr_configured`: Whether `BYPARR_API_URL` is set
- `result.news48.searxng_configured`: Whether `SEARXNG_URL` is set
- `result.news48.api_base_configured`: Whether `API_BASE` is set

---

## Tool Count Summary

| Category | Tools |
|----------|-------|
| Pipeline control | `run_shell_command` |
| File access | `read_file` |
| Web access | `perform_web_search`, `fetch_webpage_content` |
| System | `get_system_info` |
| Planning | `create_plan`, `update_plan`, `claim_plan`, `list_plans` |
| Communication | `send_email` |
| **Total** | **10 tools** |

---

## Agent-Tool Assignments

Each active runtime agent uses a specific subset of tools:

| Agent | Tools | Purpose |
|-------|-------|---------|
| **Planner** | `run_shell_command`, `read_file`, `get_system_info`, `create_plan`, `update_plan`, `list_plans` | Gather evidence, detect gaps, create minimal executable plans, avoid duplicate work |
| **Executor** | `claim_plan`, `update_plan`, `run_shell_command`, `read_file`, `get_system_info`, `perform_web_search`, `fetch_webpage_content` | Claim and execute one pending plan, verify success conditions, perform fact-check evidence lookups |
| **Monitor** | `run_shell_command`, `read_file`, `get_system_info`, `send_email` | Gather metrics, classify alerts, and deliver reports when email is configured |
| **Parser** | `run_shell_command`, `read_file` | Parse one claimed article at a time, update the article record, and release the processing claim |

### Design Notes

- **Planner is plan-authoring only**: it never claims or executes plans; it focuses on evidence-driven plan creation and sequencing.
- **Executor is execution-only**: it does not create plans directly; it claims pending plans and drives steps to completion or failure with verification evidence.
- **Monitor is read-only for system state**: it does not create or update plans, and sends email only when configuration is available and the current status requires it.
- **Fact-checking is executed by Executor**: fact-check work is produced by Planner plans and executed through Executor tool access to search and page fetch tools.
- **Parser is autonomous and DB-claim based**: it is scheduler-driven, does not use plan files, and prevents duplicate parse work by claiming articles in the database before parsing.
