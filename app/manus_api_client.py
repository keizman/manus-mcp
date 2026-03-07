"""
Manus API Client module for Manus MCP.

This module encapsulates all interactions with the Manus API,
including task creation, status retrieval, and result parsing.
It uses the OpenAI SDK for compatibility with the Manus Responses API.
"""

import os
import json
import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum

import httpx

logger = logging.getLogger("manus-mcp")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANUS_API_BASE_URL = os.getenv("MANUS_API_BASE_URL", "https://api.manus.ai")

# Well-known connector UUIDs
CONNECTOR_MY_BROWSER = "be268223-40b2-4f3c-a907-c12eb1699283"
CONNECTOR_GITHUB = "bbb0df76-66bd-4a24-ae4f-2aac4750d90b"
CONNECTOR_PLAYWRIGHT = "356d5bc1-fb9f-4fa1-babb-05039dc09d63"
CONNECTOR_FIRECRAWL = "abb9ed36-e693-44ab-be3d-1f5c3bb02294"


class TaskMode(str, Enum):
    """Supported Manus task modes."""
    CHAT = "chat"
    ADAPTIVE = "adaptive"
    AGENT = "agent"


class AgentProfile(str, Enum):
    """Supported Manus agent profiles."""
    STANDARD = "manus-1.6"
    LITE = "manus-1.6-lite"
    MAX = "manus-1.6-max"


class TaskStatus(str, Enum):
    """Possible Manus task statuses."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskResult:
    """Structured representation of a Manus task result."""
    task_id: str
    status: str
    title: str = ""
    task_url: str = ""
    share_url: str = ""
    error: Optional[str] = None
    output: List[Dict[str, Any]] = field(default_factory=list)
    credit_usage: Optional[int] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @property
    def is_terminal(self) -> bool:
        """Check if the task has reached a terminal state."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    @property
    def final_text(self) -> str:
        """Extract the final assistant text from the output."""
        texts = []
        for msg in reversed(self.output):
            if msg.get("role") == "assistant":
                for content in msg.get("content", []):
                    if content.get("type") == "output_text" and content.get("text"):
                        texts.append(content["text"])
                if texts:
                    break
        return "\n\n".join(reversed(texts))

    @property
    def attachments(self) -> List[Dict[str, str]]:
        """Extract file attachments from the output."""
        files = []
        for msg in self.output:
            if msg.get("role") == "assistant":
                for content in msg.get("content", []):
                    if content.get("type") == "output_file" and content.get("fileUrl"):
                        files.append({
                            "file_name": content.get("fileName", "unknown"),
                            "url": content["fileUrl"],
                            "mime_type": content.get("mimeType", ""),
                        })
        return files


class ManusAPIError(Exception):
    """Custom exception for Manus API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class ManusAPIClient:
    """
    Client for interacting with the Manus API.

    Uses the REST API directly via httpx for maximum control and reliability.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("MANUS_API_KEY", "")
        self.base_url = (base_url or MANUS_API_BASE_URL).rstrip("/")

        if not self.api_key:
            logger.warning(
                "MANUS_API_KEY is not set. Manus API calls will fail. "
                "Please set the MANUS_API_KEY environment variable."
            )

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "API_KEY": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Task Creation
    # ------------------------------------------------------------------

    async def create_task(
        self,
        prompt: str,
        agent_profile: str = AgentProfile.STANDARD,
        task_mode: str = TaskMode.AGENT,
        use_local_browser: bool = False,
        connectors: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        hide_in_task_list: bool = True,
        locale: str = "en-US",
        interactive_mode: bool = False,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> TaskResult:
        """
        Create a new Manus task.

        Args:
            prompt: The task instruction for the Manus agent.
            agent_profile: Which agent profile to use.
            task_mode: Task execution mode (chat, adaptive, agent).
            use_local_browser: Whether to enable the user's local browser connector.
            connectors: Additional connector UUIDs to enable.
            attachments: File/URL attachments for the task.
            hide_in_task_list: Whether to hide this task from the Manus webapp.
            locale: User locale string.
            interactive_mode: Allow Manus to ask follow-up questions.
            task_id: For continuing an existing task (multi-turn).
            project_id: Project ID to associate with.

        Returns:
            TaskResult with the newly created task's information.
        """
        connector_list = list(connectors or [])
        if use_local_browser and CONNECTOR_MY_BROWSER not in connector_list:
            connector_list.append(CONNECTOR_MY_BROWSER)

        body: Dict[str, Any] = {
            "prompt": prompt,
            "agentProfile": agent_profile,
            "taskMode": task_mode,
            "hideInTaskList": hide_in_task_list,
            "locale": locale,
            "interactiveMode": interactive_mode,
        }

        if connector_list:
            body["connectors"] = connector_list
        if attachments:
            body["attachments"] = attachments
        if task_id:
            body["taskId"] = task_id
        if project_id:
            body["projectId"] = project_id

        logger.info(f"Creating Manus task: mode={task_mode}, profile={agent_profile}, "
                     f"browser={use_local_browser}, connectors={connector_list}")

        response = await self._client.post("/v1/tasks", json=body)
        self._check_response(response)

        data = response.json()
        logger.info(f"Task created: id={data.get('task_id')}, url={data.get('task_url')}")

        return TaskResult(
            task_id=data.get("task_id", ""),
            status=TaskStatus.RUNNING,
            title=data.get("task_title", ""),
            task_url=data.get("task_url", ""),
            share_url=data.get("share_url", ""),
        )

    # ------------------------------------------------------------------
    # Task Retrieval
    # ------------------------------------------------------------------

    async def get_task(self, task_id: str) -> TaskResult:
        """
        Retrieve the current state of a Manus task.

        Args:
            task_id: The unique identifier of the task.

        Returns:
            TaskResult with the task's current state and output.
        """
        logger.info(f"Retrieving task: {task_id}")

        response = await self._client.get(f"/v1/tasks/{task_id}")
        self._check_response(response)

        data = response.json()
        metadata = data.get("metadata", {})

        return TaskResult(
            task_id=data.get("id", task_id),
            status=data.get("status", "unknown"),
            title=metadata.get("task_title", ""),
            task_url=metadata.get("task_url", ""),
            error=data.get("error"),
            output=data.get("output", []),
            credit_usage=data.get("credit_usage"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    # ------------------------------------------------------------------
    # Task Polling (convenience)
    # ------------------------------------------------------------------

    async def wait_for_task(
        self,
        task_id: str,
        poll_interval: float = 5.0,
        max_wait: float = 600.0,
    ) -> TaskResult:
        """
        Poll a task until it reaches a terminal state.

        Args:
            task_id: The task to wait for.
            poll_interval: Seconds between polls.
            max_wait: Maximum total seconds to wait.

        Returns:
            The final TaskResult.

        Raises:
            ManusAPIError: If max_wait is exceeded.
        """
        import asyncio

        start = time.monotonic()
        while True:
            result = await self.get_task(task_id)
            if result.is_terminal:
                return result

            elapsed = time.monotonic() - start
            if elapsed >= max_wait:
                raise ManusAPIError(
                    f"Task {task_id} did not complete within {max_wait}s "
                    f"(current status: {result.status})"
                )

            logger.info(f"Task {task_id} status: {result.status}, "
                        f"elapsed: {elapsed:.0f}s, next poll in {poll_interval}s")
            await asyncio.sleep(poll_interval)

    # ------------------------------------------------------------------
    # Task Management
    # ------------------------------------------------------------------

    async def delete_task(self, task_id: str) -> bool:
        """Delete a Manus task."""
        response = await self._client.delete(f"/v1/tasks/{task_id}")
        self._check_response(response)
        return True

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[TaskResult]:
        """List Manus tasks with optional filtering."""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        response = await self._client.get("/v1/tasks", params=params)
        self._check_response(response)

        data = response.json()
        tasks = data if isinstance(data, list) else data.get("data", data.get("tasks", []))

        results = []
        for t in tasks:
            metadata = t.get("metadata", {})
            results.append(TaskResult(
                task_id=t.get("id", ""),
                status=t.get("status", "unknown"),
                title=metadata.get("task_title", t.get("task_title", "")),
                task_url=metadata.get("task_url", t.get("task_url", "")),
                created_at=t.get("created_at"),
                updated_at=t.get("updated_at"),
            ))
        return results

    # ------------------------------------------------------------------
    # File Management
    # ------------------------------------------------------------------

    async def upload_file(self, filename: str, file_content: bytes) -> str:
        """
        Upload a file to Manus and return the file_id.

        Args:
            filename: Name for the file.
            file_content: Raw bytes of the file.

        Returns:
            The file_id that can be used in task attachments.
        """
        # Step 1: Create file record
        response = await self._client.post("/v1/files", json={"filename": filename})
        self._check_response(response)
        file_data = response.json()
        file_id = file_data["id"]
        upload_url = file_data["upload_url"]

        # Step 2: Upload to presigned URL
        async with httpx.AsyncClient() as upload_client:
            upload_resp = await upload_client.put(upload_url, content=file_content)
            if upload_resp.status_code not in (200, 201, 204):
                raise ManusAPIError(
                    f"File upload failed: {upload_resp.status_code}",
                    status_code=upload_resp.status_code,
                )

        logger.info(f"File uploaded: {filename} -> {file_id}")
        return file_id

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _check_response(self, response: httpx.Response) -> None:
        """Raise ManusAPIError if the response indicates an error."""
        if response.status_code >= 400:
            try:
                body = response.text
            except Exception:
                body = "<unreadable>"
            raise ManusAPIError(
                f"Manus API error {response.status_code}: {body}",
                status_code=response.status_code,
                response_body=body,
            )
