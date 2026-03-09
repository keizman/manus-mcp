"""
Manus MCP Server - Enhanced Edition

A Model Context Protocol (MCP) server that bridges local CLI tools (like codex)
with the Manus cloud AI agent platform. Supports four task modes:

1. web_search    - Quick web search answers (search engine mode)
2. plan          - Deep research, fact-checking, and structured planning
3. coding        - Code creation from scratch or using existing git repos
4. simple_task   - Raw prompt pass-through for custom/interactive workflows

All modes support:
- Optional local browser integration (use_local_browser)
- Multi-turn conversation (task_id continuation)
- Task status monitoring (get_task_status polling)
"""

from typing import Any, Dict, List, Optional
import asyncio
import logging
import os
import json
import sys
import atexit
from dotenv import load_dotenv
from mcp.server import FastMCP

from app.task_manager import TaskManager
from app.manus_api_client import AgentProfile

# ---------------------------------------------------------------------------
# Environment & Logging
# ---------------------------------------------------------------------------

load_dotenv()

log_dir = os.path.expanduser("~/manus-mcp-logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "manus-mcp.log")

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=log_file,
    filemode="a",
)
logger = logging.getLogger("manus-mcp")
logger.info("Starting Manus MCP server (Enhanced Edition v0.3)")

# Suppress noisy library loggers
for lib_name in ["httpx", "httpcore", "asyncio"]:
    lib_log = logging.getLogger(lib_name)
    lib_log.handlers = []
    lib_log.addHandler(logging.FileHandler(log_file))
    lib_log.setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# MCP Server & Task Manager
# ---------------------------------------------------------------------------

mcp = FastMCP("manus-mcp")
task_manager = TaskManager()

# ---------------------------------------------------------------------------
# Identity Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def manus_identity() -> str:
    """
    Provides identity information about Manus MCP and its available tools.
    Call this at the start of a conversation to understand what capabilities are available.

    Returns:
        A description of Manus MCP's identity and available tools.
    """
    logger.info("Invoking manus_identity tool")
    return """
You are connected to Manus MCP (Enhanced Edition v0.3), a bridge between your local environment
and the Manus cloud AI agent platform.

Available tools:

1. **manus_web_search** - Search the web and get direct answers with source citations.
   Best for: quick factual queries, finding URLs, checking current information.

2. **manus_plan** - Deep research and structured planning on any topic.
   Best for: project planning, market research, technical architecture, feasibility studies.

3. **manus_code** - Create code from scratch or work with existing git repositories.
   Best for: building new projects, modifying existing repos, code generation.

4. **manus_simple_task** - Send a raw prompt directly to Manus without any template wrapping.
   Best for: custom workflows, interactive multi-turn sessions, tasks that don't fit other modes.

5. **get_task_status** - Check the status and results of any running or completed task.
   Use this to poll for results after creating a task.

6. **list_manus_tasks** - List all tasks created in this session.

7. **cancel_task** - Cancel a running task.

All task creation tools support:
- `use_local_browser` (bool): Enable your local browser for tasks requiring login or local network access.
- `agent_profile` (str): Choose "manus-1.6" (standard), "manus-1.6-lite" (fast), or "manus-1.6-max" (powerful).
- `task_id` (str): Pass an existing task_id to continue the conversation (multi-turn).

Multi-turn workflow:
1. Create a task -> receive task_id
2. Poll with get_task_status(task_id) until completed
3. To follow up, call any tool again with the same task_id
4. The agent retains full context from previous turns

Single-turn workflow:
1. Create a task -> receive task_id
2. Poll with get_task_status(task_id) until completed
3. Read final_text and attachments from the response
"""

# ---------------------------------------------------------------------------
# Web Search Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def manus_web_search(
    query: str,
    use_local_browser: bool = False,
    agent_profile: str = "manus-1.6-lite",
    task_id: str = "",
) -> str:
    """
    Search the web using Manus AI and get a direct, cited answer.

    This tool dispatches a search task to the Manus cloud agent, which performs
    real web searches, reads pages, and synthesizes a concise answer with sources.
    It acts purely as a search engine - no planning or coding.

    Supports multi-turn: pass a previous task_id to ask follow-up search questions
    within the same conversation context.

    Args:
        query: The search query or question to answer.
        use_local_browser: If True, enables the Manus agent to use your local
            browser session (useful for sites requiring login). Default: False.
        agent_profile: The Manus agent profile to use.
            "manus-1.6-lite" (default, fast), "manus-1.6" (standard), "manus-1.6-max" (powerful).
        task_id: Optional. Pass an existing task_id to continue the conversation.
            The agent will retain context from previous turns.

    Returns:
        JSON string with task_id, status, and task_url. Use get_task_status(task_id)
        to retrieve the search results once the task completes.
    """
    logger.info(f"manus_web_search: query='{query}', browser={use_local_browser}, continue={task_id}")

    try:
        result = await task_manager.create_web_search(
            query=query,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
            task_id=task_id if task_id else None,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"manus_web_search failed: {e}")
        return json.dumps({"error": str(e), "status": "failed"})

# ---------------------------------------------------------------------------
# Plan Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def manus_plan(
    topic: str,
    context: str = "",
    use_local_browser: bool = False,
    agent_profile: str = "manus-1.6",
    task_id: str = "",
) -> str:
    """
    Create a research-backed professional plan on any topic using Manus AI.

    The Manus agent will conduct deep web research, cross-reference multiple sources,
    and produce a structured plan with phases, milestones, and cited findings.

    Supports multi-turn: pass a previous task_id to refine or expand the plan
    with additional instructions.

    Args:
        topic: The subject or problem to research and plan for.
        context: Optional additional context, constraints, or requirements.
        use_local_browser: If True, enables the Manus agent to use your local
            browser session. Default: False.
        agent_profile: The Manus agent profile to use.
            "manus-1.6" (default, standard), "manus-1.6-lite" (fast), "manus-1.6-max" (powerful).
        task_id: Optional. Pass an existing task_id to continue the conversation.

    Returns:
        JSON string with task_id, status, and task_url. Use get_task_status(task_id)
        to retrieve the plan once the task completes.
    """
    logger.info(f"manus_plan: topic='{topic}', browser={use_local_browser}, continue={task_id}")

    try:
        result = await task_manager.create_plan(
            topic=topic,
            context=context if context else None,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
            task_id=task_id if task_id else None,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"manus_plan failed: {e}")
        return json.dumps({"error": str(e), "status": "failed"})

# ---------------------------------------------------------------------------
# Coding Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def manus_code(
    prompt: str,
    git_repo_url: str = "",
    language: str = "",
    use_local_browser: bool = False,
    agent_profile: str = "manus-1.6",
    task_id: str = "",
) -> str:
    """
    Create or modify code using Manus AI.

    The Manus agent can build projects from scratch or clone and modify existing
    git repositories. It writes clean, documented, production-quality code.

    Supports multi-turn: pass a previous task_id to iterate on code with
    additional instructions (e.g., "add tests", "fix the bug in line 42").

    Args:
        prompt: Description of what code to create or what changes to make.
        git_repo_url: Optional URL of an existing git repository to work with.
            If provided, the agent will clone it and make changes.
        language: Optional preferred programming language or framework.
        use_local_browser: If True, enables the Manus agent to use your local
            browser session. Default: False.
        agent_profile: The Manus agent profile to use.
            "manus-1.6" (default, standard), "manus-1.6-lite" (fast), "manus-1.6-max" (powerful).
        task_id: Optional. Pass an existing task_id to continue the conversation.

    Returns:
        JSON string with task_id, status, and task_url. Use get_task_status(task_id)
        to retrieve the code and results once the task completes.
    """
    logger.info(f"manus_code: prompt='{prompt[:80]}...', repo={git_repo_url}, continue={task_id}")

    try:
        result = await task_manager.create_coding(
            prompt=prompt,
            git_repo_url=git_repo_url if git_repo_url else None,
            language=language if language else None,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
            task_id=task_id if task_id else None,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"manus_code failed: {e}")
        return json.dumps({"error": str(e), "status": "failed"})

# ---------------------------------------------------------------------------
# Simple Task Tool (raw prompt pass-through)
# ---------------------------------------------------------------------------

@mcp.tool()
async def manus_simple_task(
    prompt: str,
    use_local_browser: bool = False,
    agent_profile: str = "manus-1.6",
    task_id: str = "",
) -> str:
    """
    Send a raw prompt directly to Manus AI without any template wrapping.

    Unlike web_search/plan/code, this tool passes your prompt to Manus exactly
    as-is, with no pre-built instructions or formatting. This gives you full
    control over what the Manus agent does.

    Ideal for:
    - Custom workflows where you (or codex) control the prompt entirely
    - Multi-turn interactive sessions: create a task, get results, then send
      follow-up instructions to iteratively refine the output
    - Tasks that don't fit the web_search/plan/coding categories
    - Asking Manus to perform specific operations (e.g., "go to this URL and
      fill out the form", "analyze this data and create a chart")

    Multi-turn example:
    1. manus_simple_task(prompt="Build a Python CLI for managing TODOs")
       -> returns task_id="abc123"
    2. get_task_status("abc123") -> completed, read the code
    3. manus_simple_task(prompt="Add unit tests for the delete command", task_id="abc123")
       -> continues in the same context, agent remembers the code it wrote
    4. manus_simple_task(prompt="Now add a --verbose flag", task_id="abc123")
       -> further iteration in the same session

    Args:
        prompt: The raw prompt to send to Manus, exactly as-is. No template
            wrapping or modification will be applied.
        use_local_browser: If True, enables the Manus agent to use your local
            browser session. Default: False.
        agent_profile: The Manus agent profile to use.
            "manus-1.6" (default, standard), "manus-1.6-lite" (fast), "manus-1.6-max" (powerful).
        task_id: Optional. Pass an existing task_id to continue the conversation.
            The agent retains full context from all previous turns.

    Returns:
        JSON string with task_id, status, and task_url. Use get_task_status(task_id)
        to retrieve results once the task completes.
    """
    logger.info(f"manus_simple_task: prompt='{prompt[:80]}...', browser={use_local_browser}, continue={task_id}")

    try:
        result = await task_manager.create_simple_task(
            prompt=prompt,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
            task_id=task_id if task_id else None,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"manus_simple_task failed: {e}")
        return json.dumps({"error": str(e), "status": "failed"})

# ---------------------------------------------------------------------------
# Task Status Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_task_status(task_id: str) -> str:
    """
    Check the status and results of a Manus task.

    Use this tool to poll for progress after creating a task with any of the
    task creation tools. When the task is complete, the response will include
    the full output text, any file attachments, and a hint for multi-turn continuation.

    Typical workflow:
    1. Create a task -> receive task_id
    2. Call get_task_status(task_id) periodically
    3. When status is "completed", read the final_text and attachments
    4. To continue the conversation, pass the task_id to any creation tool

    Status values:
    - "running": Task is actively being processed
    - "pending": Task is waiting for input
    - "completed": Task finished successfully (can_continue=True)
    - "failed": Task encountered an error

    Args:
        task_id: The unique identifier of the task to check.

    Returns:
        JSON string with the task's current status, output, metadata,
        and multi-turn continuation hints.
    """
    logger.info(f"get_task_status: task_id={task_id}")

    try:
        result = await task_manager.get_status(task_id)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"get_task_status failed: {e}")
        return json.dumps({"task_id": task_id, "error": str(e), "status": "error"})

# ---------------------------------------------------------------------------
# List Tasks Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_manus_tasks(mode: str = "") -> str:
    """
    List all Manus tasks created in this session.

    Args:
        mode: Optional filter by task mode ("web_search", "plan", "coding", "simple_task").
            Leave empty to list all tasks.

    Returns:
        JSON array of task summaries including turn_count for multi-turn tasks.
    """
    logger.info(f"list_manus_tasks: mode={mode}")

    try:
        results = await task_manager.list_tasks(mode=mode if mode else None)
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"list_manus_tasks failed: {e}")
        return json.dumps([{"error": str(e)}])

# ---------------------------------------------------------------------------
# Cancel Task Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def cancel_task(task_id: str) -> str:
    """
    Cancel a running Manus task.

    Args:
        task_id: The unique identifier of the task to cancel.

    Returns:
        JSON string confirming the cancellation or reporting an error.
    """
    logger.info(f"cancel_task: task_id={task_id}")

    try:
        result = await task_manager.cancel_task(task_id)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"cancel_task failed: {e}")
        return json.dumps({"task_id": task_id, "error": str(e), "status": "error"})


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
