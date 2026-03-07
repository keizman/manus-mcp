# Manus MCP (Enhanced Edition)

> A Model Context Protocol (MCP) server that bridges local CLI tools (Codex, Claude Desktop, etc.) with the **Manus cloud AI agent platform**.

Manus MCP lets you dispatch powerful cloud-based AI tasks — web search, research planning, and code generation — directly from your terminal or any MCP-compatible client. All tasks support optional **local browser integration** and real-time **status monitoring**.

## Features

| Mode | Tool Name | Description | Default Profile |
|------|-----------|-------------|-----------------|
| **Web Search** | `manus_web_search` | Quick, cited web search answers. Acts as an AI-powered search engine. | `manus-1.6-lite` |
| **Plan** | `manus_plan` | Deep research, fact-checking, and structured professional planning. | `manus-1.6` |
| **Coding** | `manus_code` | Create code from scratch or modify existing git repositories. | `manus-1.6` |

### Additional Tools

| Tool Name | Description |
|-----------|-------------|
| `get_task_status` | Poll task status and retrieve results (text + file attachments). |
| `list_manus_tasks` | List all tasks created in the current session. |
| `cancel_task` | Cancel a running task. |
| `manus_identity` | Describe available capabilities (auto-invoked by some clients). |

### Cross-Cutting Features

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
> Search the web for the latest Python 3.13 features
> Create a plan for migrating our app from React to Next.js
> Build a REST API with FastAPI that manages a todo list
```

## Workflow

The typical interaction pattern is **create → poll → retrieve**:

```
1. Client calls manus_web_search("latest AI news")
   → Returns: {"task_id": "abc123", "status": "running", ...}

2. Client calls get_task_status("abc123")
   → Returns: {"status": "running", ...}

3. Client calls get_task_status("abc123") again
   → Returns: {"status": "completed", "final_text": "...", "attachments": [...]}
```

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

### `manus_web_search(query, use_local_browser?, agent_profile?)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | *(required)* | The search query or question |
| `use_local_browser` | `bool` | `False` | Use your local browser session |
| `agent_profile` | `str` | `"manus-1.6-lite"` | Agent capability level |

### `manus_plan(topic, context?, use_local_browser?, agent_profile?)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `topic` | `str` | *(required)* | Subject to research and plan for |
| `context` | `str` | `""` | Additional constraints or requirements |
| `use_local_browser` | `bool` | `False` | Use your local browser session |
| `agent_profile` | `str` | `"manus-1.6"` | Agent capability level |

### `manus_code(prompt, git_repo_url?, language?, use_local_browser?, agent_profile?)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | `str` | *(required)* | What to build or change |
| `git_repo_url` | `str` | `""` | Existing repo to clone and modify |
| `language` | `str` | `""` | Preferred language/framework |
| `use_local_browser` | `bool` | `False` | Use your local browser session |
| `agent_profile` | `str` | `"manus-1.6"` | Agent capability level |

### `get_task_status(task_id)`

Returns a JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Task identifier |
| `status` | `str` | `"running"`, `"pending"`, `"completed"`, or `"failed"` |
| `is_complete` | `bool` | Whether the task has finished |
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
