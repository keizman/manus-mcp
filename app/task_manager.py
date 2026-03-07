"""
Task Manager module for Manus MCP.

Provides a local in-memory cache of task states and a high-level interface
for creating, monitoring, and retrieving Manus tasks. This module sits
between the MCP tool layer and the Manus API client.
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
    mode: str  # web_search, plan, coding
    original_input: str
    use_local_browser: bool
    created_at: float = field(default_factory=time.time)
    last_polled: float = 0.0
    remote: Optional[TaskResult] = None

    def to_summary(self) -> Dict[str, Any]:
        """Return a concise summary suitable for MCP tool responses."""
        summary: Dict[str, Any] = {
            "task_id": self.task_id,
            "mode": self.mode,
            "use_local_browser": self.use_local_browser,
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
    for the three task modes (web_search, plan, coding).
    """

    def __init__(self, api_client: Optional[ManusAPIClient] = None):
        self._client = api_client or ManusAPIClient()
        self._tasks: Dict[str, LocalTaskRecord] = {}

    async def close(self):
        """Shutdown the API client."""
        await self._client.close()

    # ------------------------------------------------------------------
    # Task Creation (three modes)
    # ------------------------------------------------------------------

    async def create_web_search(
        self,
        query: str,
        use_local_browser: bool = False,
        agent_profile: str = AgentProfile.LITE,
    ) -> Dict[str, Any]:
        """
        Create a web_search task.

        Uses the LITE profile by default for speed, since this mode
        only needs to return search results, not perform complex reasoning.
        """
        prompt = build_web_search_prompt(query)

        result = await self._client.create_task(
            prompt=prompt,
            agent_profile=agent_profile,
            task_mode=TaskMode.AGENT,
            use_local_browser=use_local_browser,
            interactive_mode=False,
        )

        record = LocalTaskRecord(
            task_id=result.task_id,
            mode="web_search",
            original_input=query,
            use_local_browser=use_local_browser,
            remote=result,
        )
        self._tasks[result.task_id] = record

        return record.to_summary()

    async def create_plan(
        self,
        topic: str,
        context: Optional[str] = None,
        use_local_browser: bool = False,
        agent_profile: str = AgentProfile.STANDARD,
    ) -> Dict[str, Any]:
        """
        Create a plan task.

        Uses the STANDARD profile for balanced research and planning capability.
        """
        prompt = build_plan_prompt(topic, context)

        result = await self._client.create_task(
            prompt=prompt,
            agent_profile=agent_profile,
            task_mode=TaskMode.AGENT,
            use_local_browser=use_local_browser,
            interactive_mode=False,
        )

        record = LocalTaskRecord(
            task_id=result.task_id,
            mode="plan",
            original_input=topic,
            use_local_browser=use_local_browser,
            remote=result,
        )
        self._tasks[result.task_id] = record

        return record.to_summary()

    async def create_coding(
        self,
        prompt: str,
        git_repo_url: Optional[str] = None,
        language: Optional[str] = None,
        use_local_browser: bool = False,
        agent_profile: str = AgentProfile.STANDARD,
    ) -> Dict[str, Any]:
        """
        Create a coding task.

        If a git_repo_url is provided, the GitHub connector is automatically
        added and the URL is included in the prompt context.
        """
        full_prompt = build_coding_prompt(prompt, git_repo_url, language)

        connectors = []
        if git_repo_url:
            connectors.append(CONNECTOR_GITHUB)

        attachments = None
        if git_repo_url:
            attachments = [{"type": "url", "url": git_repo_url}]

        result = await self._client.create_task(
            prompt=full_prompt,
            agent_profile=agent_profile,
            task_mode=TaskMode.AGENT,
            use_local_browser=use_local_browser,
            connectors=connectors if connectors else None,
            attachments=attachments,
            interactive_mode=False,
        )

        record = LocalTaskRecord(
            task_id=result.task_id,
            mode="coding",
            original_input=prompt,
            use_local_browser=use_local_browser,
            remote=result,
        )
        self._tasks[result.task_id] = record

        return record.to_summary()

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

        # Include mode info from local cache
        if task_id in self._tasks:
            response["mode"] = self._tasks[task_id].mode
            response["use_local_browser"] = self._tasks[task_id].use_local_browser

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
