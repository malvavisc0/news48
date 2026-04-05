# Agents Tools Inventory

This document provides an inventory of all tools available to agents in the news48 system.

## Overview

Tools are organized into the following modules:

| Module | File |
|--------|------|
| [`bypass`](../agents/tools/bypass.py) | Webpage content fetching with anti-bot bypass |
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
- `metadata`: Timestamp, reason, success flags

---

### 2. Files Module

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

### 3. Planner Module

#### `create_plan`

Create a new execution plan, persisted to `.plans/{id}.json`.

**Signature:**
```python
def create_plan(reason: str, task: str, steps: list[str]) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Why planning is needed |
| `task` | `str` | Required | Overall task description |
| `steps` | `list[str]` | Required | Ordered list of step descriptions |

**Returns:** JSON string with:
- `result`: Plan object with id, task, steps, progress
- `metadata.plan_id`: The plan ID for subsequent `update_plan` calls

#### `update_plan`

Update a step status and optionally add/remove steps.

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
) -> str
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `reason` | `str` | Required | Why you are updating this step |
| `plan_id` | `str` | Required | ID from `create_plan` response |
| `step_id` | `str` | Required | ID of the step to update (e.g., "step-1") |
| `status` | `str` | Required | One of: pending, in_progress, completed, failed |
| `result` | `str` | `""` | Optional outcome message |
| `add_steps` | `list[str] \| None` | `None` | Optional steps to append |
| `remove_steps` | `list[str] \| None` | `None` | Optional step IDs to remove |

**Returns:** JSON string with:
- `result`: Updated plan with all steps and progress
- `error`: Empty on success, or error description

---

### 4. SearXNG Module

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
- `metadata.page_stats`: Requested/succeeded/failed page counts

**Note:** Requires `SEARXNG_URL` environment variable.

---

### 5. Shell Module

#### `run_shell_command`

Execute a shell command and return its output.

**Signature:**
```python
def run_shell_command(
    reason: str, command: str, timeout: int = 120
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

### 6. System Module

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
| Planning | `create_plan`, `update_plan` |
| **Total** | **7 tools** |

---

## Agent-Tool Assignments

Each active runtime agent uses a specific subset of tools:

| Agent | Tools | Purpose |
|-------|-------|---------|
| **Planner** | `run_shell_command`, `read_file`, `get_system_info`, `create_plan`, `update_plan`, `list_plans` | Gather evidence, detect gaps, create minimal executable plans, avoid duplicate work |
| **Executor** | `claim_plan`, `update_plan`, `run_shell_command`, `read_file`, `get_system_info`, `perform_web_search`, `fetch_webpage_content` | Claim and execute one pending plan, verify success conditions, perform fact-check evidence lookups |
| **Monitor** | `run_shell_command`, `read_file`, `get_system_info`, `send_email` | Gather metrics, classify alerts, and deliver WARNING or CRITICAL monitoring reports |
| **Parser** *(sub-agent)* | `run_shell_command` (own), `read_file` (own) | Parse HTML article input and update article metadata and content |

### Design Notes

- **Planner is plan-authoring only**: it never claims or executes plans; it focuses on evidence-driven plan creation and sequencing.
- **Executor is execution-only**: it does not create plans directly; it claims pending plans and drives steps to completion or failure with verification evidence.
- **Monitor is read-only for system state**: it does not create or update plans, and sends email only when policy requires it.
- **Fact-checking is executed by Executor**: fact-check work is produced by Planner plans and executed through Executor tool access to search and page fetch tools.
- **Parser remains a sub-agent**: it is used by parse flows and is not an orchestrator-scheduled top-level agent.
