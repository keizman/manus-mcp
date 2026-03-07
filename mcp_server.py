"""
Manus MCP Server - Enhanced Edition

A Model Context Protocol (MCP) server that bridges local CLI tools (like codex)
with the Manus cloud AI agent platform. Supports three task modes:

1. web_search  - Quick web search answers (search engine mode)
2. plan        - Deep research, fact-checking, and structured planning
3. coding      - Code creation from scratch or using existing git repos

All modes support optional local browser integration and task status monitoring.
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
logger.info("Starting Manus MCP server (Enhanced Edition)")

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
You are connected to Manus MCP (Enhanced Edition), a bridge between your local environment
and the Manus cloud AI agent platform.

Available tools:

1. **manus_web_search** - Search the web and get direct answers with source citations.
   Best for: quick factual queries, finding URLs, checking current information.

2. **manus_plan** - Deep research and structured planning on any topic.
   Best for: project planning, market research, technical architecture, feasibility studies.

3. **manus_code** - Create code from scratch or work with existing git repositories.
   Best for: building new projects, modifying existing repos, code generation.

4. **get_task_status** - Check the status and results of any running or completed task.
   Use this to poll for results after creating a task.

5. **list_manus_tasks** - List all tasks created in this session.

6. **cancel_task** - Cancel a running task.

All task creation tools support:
- `use_local_browser` (bool): Enable your local browser for tasks requiring login or local network access.
- `agent_profile` (str): Choose "manus-1.6" (standard), "manus-1.6-lite" (fast), or "manus-1.6-max" (powerful).

Workflow:
1. Create a task with one of the three tools above.
2. You'll receive a task_id immediately.
3. Use get_task_status(task_id) to poll for progress and results.
4. When status is "completed", the response includes the full output and any file attachments.
"""

# ---------------------------------------------------------------------------
# Web Search Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def manus_web_search(
    query: str,
    use_local_browser: bool = False,
    agent_profile: str = "manus-1.6-lite",
) -> str:
    """
    Search the web using Manus AI and get a direct, cited answer.

    This tool dispatches a search task to the Manus cloud agent, which performs
    real web searches, reads pages, and synthesizes a concise answer with sources.
    It acts purely as a search engine - no planning or coding.

    Args:
        query: The search query or question to answer.
        use_local_browser: If True, enables the Manus agent to use your local
            browser session (useful for sites requiring login). Default: False.
        agent_profile: The Manus agent profile to use.
            "manus-1.6-lite" (default, fast), "manus-1.6" (standard), "manus-1.6-max" (powerful).

    Returns:
        JSON string with task_id, status, and task_url. Use get_task_status(task_id)
        to retrieve the search results once the task completes.
    """
    logger.info(f"manus_web_search: query='{query}', browser={use_local_browser}")

    try:
        result = await task_manager.create_web_search(
            query=query,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
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
) -> str:
    """
    Create a research-backed professional plan on any topic using Manus AI.

    The Manus agent will conduct deep web research, cross-reference multiple sources,
    and produce a structured plan with phases, milestones, and cited findings.

    Args:
        topic: The subject or problem to research and plan for.
        context: Optional additional context, constraints, or requirements.
        use_local_browser: If True, enables the Manus agent to use your local
            browser session. Default: False.
        agent_profile: The Manus agent profile to use.
            "manus-1.6" (default, standard), "manus-1.6-lite" (fast), "manus-1.6-max" (powerful).

    Returns:
        JSON string with task_id, status, and task_url. Use get_task_status(task_id)
        to retrieve the plan once the task completes.
    """
    logger.info(f"manus_plan: topic='{topic}', browser={use_local_browser}")

    try:
        result = await task_manager.create_plan(
            topic=topic,
            context=context if context else None,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
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
) -> str:
    """
    Create or modify code using Manus AI.

    The Manus agent can build projects from scratch or clone and modify existing
    git repositories. It writes clean, documented, production-quality code.

    Args:
        prompt: Description of what code to create or what changes to make.
        git_repo_url: Optional URL of an existing git repository to work with.
            If provided, the agent will clone it and make changes.
        language: Optional preferred programming language or framework.
        use_local_browser: If True, enables the Manus agent to use your local
            browser session. Default: False.
        agent_profile: The Manus agent profile to use.
            "manus-1.6" (default, standard), "manus-1.6-lite" (fast), "manus-1.6-max" (powerful).

    Returns:
        JSON string with task_id, status, and task_url. Use get_task_status(task_id)
        to retrieve the code and results once the task completes.
    """
    logger.info(f"manus_code: prompt='{prompt[:80]}...', repo={git_repo_url}, browser={use_local_browser}")

    try:
        result = await task_manager.create_coding(
            prompt=prompt,
            git_repo_url=git_repo_url if git_repo_url else None,
            language=language if language else None,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"manus_code failed: {e}")
        return json.dumps({"error": str(e), "status": "failed"})

# ---------------------------------------------------------------------------
# Task Status Tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_task_status(task_id: str) -> str:
    """
    Check the status and results of a Manus task.

    Use this tool to poll for progress after creating a task with manus_web_search,
    manus_plan, or manus_code. When the task is complete, the response will include
    the full output text and any file attachments.

    Typical workflow:
    1. Create a task -> receive task_id
    2. Call get_task_status(task_id) periodically
    3. When status is "completed", read the final_text and attachments

    Status values:
    - "running": Task is actively being processed
    - "pending": Task is waiting for input
    - "completed": Task finished successfully
    - "failed": Task encountered an error

    Args:
        task_id: The unique identifier of the task to check.

    Returns:
        JSON string with the task's current status, output, and metadata.
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
        mode: Optional filter by task mode ("web_search", "plan", "coding").
            Leave empty to list all tasks.

    Returns:
        JSON array of task summaries.
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
