"""
Task Manager module for Manus MCP.

Provides a local in-memory cache of task states and a high-level interface
for creating, monitoring, and retrieving Manus tasks. This module sits
between the MCP tool layer and the Manus API client.

Supports four task modes:
- web_search: Quick search engine answers
- plan: Deep research and structured planning
- coding: Code creation / git repo modification
- simple_task: Raw prompt pass-through for custom workflows

All modes support multi-turn conversation via task_id continuation.
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from app.manus_api_client import (
    ManusAPIClient,
    ManusAPIError,
    TaskResult,
    TaskMode,
    AgentProfile,
    CONNECTOR_GITHUB,
)
from app.prompt_builder import (
    build_web_search_prompt,
    build_plan_prompt,
    build_coding_prompt,
)

logger = logging.getLogger("manus-mcp")


@dataclass
class LocalTaskRecord:
    """Local record that enriches the remote TaskResult with MCP-specific metadata."""
    task_id: str
    mode: str  # web_search, plan, coding, simple_task
    original_input: str
    use_local_browser: bool
    turn_count: int = 1
    created_at: float = field(default_factory=time.time)
    last_polled: float = 0.0
    remote: Optional[TaskResult] = None

    def to_summary(self) -> Dict[str, Any]:
        """Return a concise summary suitable for MCP tool responses."""
        summary: Dict[str, Any] = {
            "task_id": self.task_id,
            "mode": self.mode,
            "use_local_browser": self.use_local_browser,
            "turn_count": self.turn_count,
            "created_at": self.created_at,
        }
        if self.remote:
            summary["status"] = self.remote.status
            summary["title"] = self.remote.title
            summary["task_url"] = self.remote.task_url
            summary["error"] = self.remote.error
            summary["credit_usage"] = self.remote.credit_usage
        else:
            summary["status"] = "submitted"
        return summary


class TaskManager:
    """
    High-level task manager that bridges MCP tools and the Manus API.

    Maintains a local cache of tasks and provides convenience methods
    for the four task modes (web_search, plan, coding, simple_task).
    All modes support multi-turn conversation via the task_id parameter.
    """

    def __init__(self, api_client: Optional[ManusAPIClient] = None):
        self._client = api_client or ManusAPIClient()
        self._tasks: Dict[str, LocalTaskRecord] = {}

    async def close(self):
        """Shutdown the API client."""
        await self._client.close()

    # ------------------------------------------------------------------
    # Internal: shared task creation logic
    # ------------------------------------------------------------------

    async def _create_or_continue_task(
        self,
        mode: str,
        prompt: str,
        original_input: str,
        use_local_browser: bool,
        agent_profile: str,
        task_id: Optional[str] = None,
        connectors: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        interactive_mode: bool = False,
        task_mode: str = TaskMode.AGENT,
    ) -> Dict[str, Any]:
        """
        Shared logic for creating a new task or continuing an existing one.

        When task_id is provided, the Manus API appends the new prompt as a
        follow-up message to the existing conversation, enabling multi-turn
        interaction within the same task context.
        """
        is_continuation = bool(task_id)

        result = await self._client.create_task(
            prompt=prompt,
            agent_profile=agent_profile,
            task_mode=task_mode,
            use_local_browser=use_local_browser,
            connectors=connectors,
            attachments=attachments,
            interactive_mode=interactive_mode,
            task_id=task_id,
        )

        # For continuations, update the existing record
        if is_continuation and task_id in self._tasks:
            record = self._tasks[task_id]
            record.turn_count += 1
            record.remote = result
            record.last_polled = 0.0
            # The API may return the same task_id or a new one
            actual_id = result.task_id or task_id
            if actual_id != task_id:
                # API returned a new task_id for the continuation
                self._tasks[actual_id] = record
                record.task_id = actual_id
        else:
            actual_id = result.task_id
            record = LocalTaskRecord(
                task_id=actual_id,
                mode=mode,
                original_input=original_input,
                use_local_browser=use_local_browser,
                remote=result,
            )
            self._tasks[actual_id] = record

        summary = record.to_summary()
        summary["is_continuation"] = is_continuation
        return summary

    # ------------------------------------------------------------------
    # Task Creation: web_search
    # ------------------------------------------------------------------

    async def create_web_search(
        self,
        query: str,
        use_local_browser: bool = False,
        agent_profile: str = AgentProfile.LITE,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a web_search task, or continue an existing one.

        Uses the LITE profile by default for speed, since this mode
        only needs to return search results, not perform complex reasoning.

        Args:
            query: The search query.
            use_local_browser: Enable local browser connector.
            agent_profile: Agent capability level.
            task_id: If provided, continues the conversation in the existing task.
        """
        prompt = build_web_search_prompt(query)

        return await self._create_or_continue_task(
            mode="web_search",
            prompt=prompt,
            original_input=query,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
            task_id=task_id,
        )

    # ------------------------------------------------------------------
    # Task Creation: plan
    # ------------------------------------------------------------------

    async def create_plan(
        self,
        topic: str,
        context: Optional[str] = None,
        use_local_browser: bool = False,
        agent_profile: str = AgentProfile.STANDARD,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a plan task, or continue an existing one.

        Uses the STANDARD profile for balanced research and planning capability.

        Args:
            topic: The subject to research and plan for.
            context: Additional constraints or requirements.
            use_local_browser: Enable local browser connector.
            agent_profile: Agent capability level.
            task_id: If provided, continues the conversation in the existing task.
        """
        prompt = build_plan_prompt(topic, context)

        return await self._create_or_continue_task(
            mode="plan",
            prompt=prompt,
            original_input=topic,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
            task_id=task_id,
        )

    # ------------------------------------------------------------------
    # Task Creation: coding
    # ------------------------------------------------------------------

    async def create_coding(
        self,
        prompt: str,
        git_repo_url: Optional[str] = None,
        language: Optional[str] = None,
        use_local_browser: bool = False,
        agent_profile: str = AgentProfile.STANDARD,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a coding task, or continue an existing one.

        If a git_repo_url is provided, the GitHub connector is automatically
        added and the URL is included in the prompt context.

        Args:
            prompt: What to build or change.
            git_repo_url: Existing repo URL to clone and modify.
            language: Preferred language/framework.
            use_local_browser: Enable local browser connector.
            agent_profile: Agent capability level.
            task_id: If provided, continues the conversation in the existing task.
        """
        full_prompt = build_coding_prompt(prompt, git_repo_url, language)

        connectors = []
        if git_repo_url:
            connectors.append(CONNECTOR_GITHUB)

        attachments = None
        if git_repo_url:
            attachments = [{"type": "url", "url": git_repo_url}]

        return await self._create_or_continue_task(
            mode="coding",
            prompt=full_prompt,
            original_input=prompt,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
            task_id=task_id,
            connectors=connectors if connectors else None,
            attachments=attachments,
        )

    # ------------------------------------------------------------------
    # Task Creation: simple_task (raw prompt pass-through)
    # ------------------------------------------------------------------

    async def create_simple_task(
        self,
        prompt: str,
        use_local_browser: bool = False,
        agent_profile: str = AgentProfile.STANDARD,
        task_id: Optional[str] = None,
        connectors: Optional[List[str]] = None,
        task_mode: str = TaskMode.AGENT,
    ) -> Dict[str, Any]:
        """
        Create a simple_task with a raw, unmodified prompt.

        Unlike the other modes, simple_task does NOT wrap the prompt in any
        template. The prompt is sent to Manus exactly as provided by the caller.
        This is ideal for:
        - Custom workflows where codex/client controls the prompt entirely
        - Multi-turn interactive sessions for iterative refinement
        - Any task that doesn't fit the web_search/plan/coding categories

        Args:
            prompt: The raw prompt to send to Manus, exactly as-is.
            use_local_browser: Enable local browser connector.
            agent_profile: Agent capability level.
            task_id: If provided, continues the conversation in the existing task.
            connectors: Additional connector UUIDs to enable.
            task_mode: Manus task mode (default: agent).
        """
        return await self._create_or_continue_task(
            mode="simple_task",
            prompt=prompt,
            original_input=prompt,
            use_local_browser=use_local_browser,
            agent_profile=agent_profile,
            task_id=task_id,
            connectors=connectors,
            interactive_mode=True,  # simple_task enables interactive by default
            task_mode=task_mode,
        )

    # ------------------------------------------------------------------
    # Task Status & Monitoring
    # ------------------------------------------------------------------

    async def get_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the current status of a task.

        Fetches the latest state from the Manus API and updates the local cache.
        Returns a structured summary including status, output text, and attachments.
        """
        try:
            result = await self._client.get_task(task_id)
        except ManusAPIError as e:
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e),
            }

        # Update local cache
        if task_id in self._tasks:
            self._tasks[task_id].remote = result
            self._tasks[task_id].last_polled = time.time()

        response: Dict[str, Any] = {
            "task_id": result.task_id,
            "status": result.status,
            "title": result.title,
            "task_url": result.task_url,
            "error": result.error,
            "credit_usage": result.credit_usage,
            "is_complete": result.is_terminal,
        }

        # Include output details for terminal states
        if result.is_terminal:
            response["final_text"] = result.final_text
            response["attachments"] = result.attachments

        # Include mode info and multi-turn metadata from local cache
        if task_id in self._tasks:
            response["mode"] = self._tasks[task_id].mode
            response["use_local_browser"] = self._tasks[task_id].use_local_browser
            response["turn_count"] = self._tasks[task_id].turn_count

        # Hint for multi-turn: if task is complete, client can continue
        if result.is_terminal and result.status == "completed":
            response["can_continue"] = True
            response["continue_hint"] = (
                f"To continue this conversation, pass task_id='{task_id}' "
                f"to any task creation tool."
            )

        return response

    async def wait_for_completion(
        self,
        task_id: str,
        poll_interval: float = 5.0,
        max_wait: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Block until a task completes, then return the full result.

        This is a convenience method for synchronous-style usage.
        For MCP tools, prefer get_status with client-side polling.
        """
        try:
            result = await self._client.wait_for_task(
                task_id, poll_interval, max_wait
            )
        except ManusAPIError as e:
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e),
            }

        if task_id in self._tasks:
            self._tasks[task_id].remote = result
            self._tasks[task_id].last_polled = time.time()

        return {
            "task_id": result.task_id,
            "status": result.status,
            "title": result.title,
            "task_url": result.task_url,
            "final_text": result.final_text,
            "attachments": result.attachments,
            "credit_usage": result.credit_usage,
            "is_complete": result.is_terminal,
        }

    # ------------------------------------------------------------------
    # Task Management
    # ------------------------------------------------------------------

    async def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """Delete/cancel a Manus task."""
        try:
            await self._client.delete_task(task_id)
            if task_id in self._tasks:
                del self._tasks[task_id]
            return {"task_id": task_id, "status": "deleted", "success": True}
        except ManusAPIError as e:
            return {"task_id": task_id, "status": "error", "error": str(e)}

    async def list_tasks(self, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List tasks, optionally filtered by mode.

        Combines local cache with remote API data.
        """
        # First, try to get from local cache
        if self._tasks:
            results = []
            for record in self._tasks.values():
                if mode and record.mode != mode:
                    continue
                results.append(record.to_summary())
            return results

        # Fallback: fetch from API
        try:
            remote_tasks = await self._client.list_tasks(limit=50)
            return [
                {
                    "task_id": t.task_id,
                    "status": t.status,
                    "title": t.title,
                    "task_url": t.task_url,
                }
                for t in remote_tasks
            ]
        except ManusAPIError as e:
            return [{"error": str(e)}]
