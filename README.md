# Manus MCP (Enhanced Edition)

> A Model Context Protocol (MCP) server that bridges local CLI tools (Codex, Claude Desktop, etc.) with the **Manus cloud AI agent platform**.

Manus MCP lets you dispatch powerful cloud-based AI tasks — web search, research planning, and code generation — directly from your terminal or any MCP-compatible client. All tasks support optional **local browser integration** and **multi-turn conversations**.

## Features

| Mode | Tool Name | Description | Default Profile |
|------|-----------|-------------|-----------------|
| **Web Search** | `manus_web_search` | Quick, cited web search answers. Acts as an AI-powered search engine. | `manus-1.6-lite` |
| **Plan** | `manus_plan` | Deep research, fact-checking, and structured professional planning. | `manus-1.6` |
| **Coding** | `manus_code` | Create code from scratch or modify existing git repositories. | `manus-1.6` |
| **Simple Task** | `manus_simple_task` | Raw prompt pass-through for custom, interactive workflows. | `manus-1.6` |

### Additional Tools

| Tool Name | Description |
|-----------|-------------|
| `get_task_status` | Poll task status and retrieve results (text + file attachments). |
| `list_manus_tasks` | List all tasks created in the current session. |
| `cancel_task` | Cancel a running task. |
| `manus_identity` | Describe available capabilities (auto-invoked by some clients). |

### Cross-Cutting Features

- **Multi-Turn Conversations**: All task creation tools accept a `task_id` parameter to continue a previous conversation, allowing for iterative refinement and follow-up instructions.
- **Local Browser Support**: All task modes accept `use_local_browser=True` to let the Manus agent use your authenticated browser session (for sites requiring login).
- **Agent Profile Selection**: Choose between `manus-1.6-lite` (fast), `manus-1.6` (balanced), or `manus-1.6-max` (most capable).
- **Task Status Monitoring**: Non-blocking task creation with polling-based status checks.
- **Structured JSON Output**: All tools return well-formed JSON for easy parsing by LLM clients.

## Quick Start

### 1. Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- A [Manus API key](https://manus.im/settings)

### 2. Installation

```bash
git clone https://github.com/keizman/manus-mcp.git
cd manus-mcp
./setup.sh
```

Or manually:

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
cp .env.example .env
# Edit .env and set your MANUS_API_KEY
```

### 3. Configuration

Edit `.env` and add your Manus API key:

```env
MANUS_API_KEY=your-manus-api-key-here
```

### 4. Usage with Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "manus-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/manus-mcp",
        "run",
        "mcp_server.py"
      ],
      "env": {
        "MANUS_API_KEY": "your-manus-api-key-here"
      }
    }
  }
}
```

### 5. Usage with OpenAI Codex CLI

```bash
codex --mcp-config claude_desktop_config.json
```

Then ask Codex to use the Manus tools:

```
> Use manus_simple_task to build a Python CLI for managing TODOs.
> (After it's done) Now use manus_simple_task to add unit tests for the delete command, continuing the previous task.
> Use manus_plan to create a migration plan from React to Next.js.
```

## Workflow: Single-Turn vs. Multi-Turn

The typical interaction pattern is **create → poll → retrieve**. For multi-turn, you simply repeat the cycle with the same `task_id`.

### Single-Turn (Fire and Forget)

1.  **Client calls** `manus_web_search("latest AI news")`
    -   **Returns**: `{"task_id": "abc123", "status": "running", ...}`
2.  **Client polls** `get_task_status("abc123")` until `status` is `completed`.
3.  **Client reads** `final_text` and `attachments` from the final status response.

### Multi-Turn (Iterative Refinement)

1.  **Client calls** `manus_simple_task(prompt="Build a Python CLI for managing TODOs")`
    -   **Returns**: `{"task_id": "xyz789", "status": "running", ...}`
2.  **Client polls** `get_task_status("xyz789")` until `status` is `completed`.
3.  **Client reads** the generated code and decides on a follow-up.
4.  **Client calls** `manus_simple_task(prompt="Now add a --verbose flag", task_id="xyz789")`
    -   The agent receives this as a follow-up instruction, remembering the code it just wrote.
5.  **Client polls** `get_task_status("xyz789")` again for the new result.

All task creation is **non-blocking** — the tool returns immediately with a `task_id`, and the client polls for results at its own pace.

## Architecture

```
┌─────────────────┐     MCP (stdio)     ┌──────────────────┐     HTTPS     ┌─────────────┐
│  Codex / Claude  │ ◄──────────────────► │   manus-mcp      │ ◄────────────► │  Manus API  │
│  Desktop / etc.  │                     │   (MCP Server)    │              │  (Cloud)    │
└─────────────────┘                     └──────────────────┘              └─────────────┘
                                               │
                                        ┌──────┴──────┐
                                        │             │
                                   ┌────▼────┐  ┌────▼────────┐
                                   │ Prompt  │  │ Task        │
                                   │ Builder │  │ Manager     │
                                   └─────────┘  └─────────────┘
```

### Module Structure

```
manus-mcp/
├── mcp_server.py              # MCP tool definitions (entry point)
├── app/
│   ├── __init__.py
│   ├── manus_api_client.py    # Manus REST API client (httpx-based)
│   ├── prompt_builder.py      # Optimized prompts for each task mode
│   ├── task_manager.py        # Task lifecycle management & local cache
│   ├── code_execution.py      # (Legacy) Local code execution
│   ├── search.py              # (Legacy) Local search
│   └── web_browser.py         # (Legacy) Local browser
├── tests/
│   ├── test_modules.py        # Unit tests for all modules
│   └── test_mcp_tools.py      # Integration tests for MCP tools
├── .env.example               # Configuration template
├── claude_desktop_config.json # Example client config
├── pyproject.toml             # Project metadata & dependencies
├── setup.sh                   # Automated setup script
└── README.md                  # This file
```

## API Reference

All task creation tools (`manus_web_search`, `manus_plan`, `manus_code`, `manus_simple_task`) share these common parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `use_local_browser` | `bool` | `False` | Use your local browser session |
| `agent_profile` | `str` | (varies) | Agent capability level (`lite`, `standard`, `max`) |
| `task_id` | `str` | `""` | **Pass an existing `task_id` to continue a conversation** |

### `manus_simple_task(prompt, ...)`

Sends a raw prompt directly to Manus. This is the most flexible tool and is ideal for multi-turn interactive sessions.

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | The raw prompt to send, exactly as-is. |

### `manus_web_search(query, ...)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | `str` | The search query or question. |

### `manus_plan(topic, context?, ...)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `topic` | `str` | Subject to research and plan for. |
| `context` | `str` | Optional additional constraints. |

### `manus_code(prompt, git_repo_url?, language?, ...)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | What to build or change. |
| `git_repo_url` | `str` | Existing repo to clone and modify. |
| `language` | `str` | Preferred language/framework. |

### `get_task_status(task_id)`

Returns a JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Task identifier |
| `status` | `str` | `"running"`, `"pending"`, `"completed"`, or `"failed"` |
| `is_complete` | `bool` | Whether the task has finished |
| `can_continue` | `bool` | **If `True`, you can pass the `task_id` to another tool** |
| `turn_count` | `int` | Number of turns in this conversation |
| `final_text` | `str` | Final output text (only when completed) |
| `attachments` | `array` | Generated files with download URLs (only when completed) |
| `task_url` | `str` | Link to view the task in the Manus web app |
| `credit_usage` | `int` | Credits consumed |

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Format code
black app/ mcp_server.py tests/
isort app/ mcp_server.py tests/
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MANUS_API_KEY` | **Yes** | — | Your Manus API key |
| `MANUS_API_BASE_URL` | No | `https://api.manus.ai` | API base URL |
| `LOG_LEVEL` | No | `INFO` | Logging level |

## License

[MIT](LICENSE)
