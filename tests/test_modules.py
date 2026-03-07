"""
Unit tests for the Manus MCP enhanced modules.

Tests cover:
- Prompt builder output format and content
- ManusAPIClient initialization and configuration
- TaskManager creation methods and status handling
- TaskResult data class behavior
"""

import os
import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Test: prompt_builder
# ---------------------------------------------------------------------------

from app.prompt_builder import (
    build_web_search_prompt,
    build_plan_prompt,
    build_coding_prompt,
)


class TestPromptBuilder:
    """Tests for the prompt_builder module."""

    def test_web_search_prompt_contains_query(self):
        prompt = build_web_search_prompt("latest Python release")
        assert "latest Python release" in prompt
        assert "search" in prompt.lower()
        assert "Query:" in prompt

    def test_web_search_prompt_no_coding_instructions(self):
        prompt = build_web_search_prompt("test query")
        assert "Do NOT perform any planning, coding" in prompt

    def test_plan_prompt_contains_topic(self):
        prompt = build_plan_prompt("AI startup business plan")
        assert "AI startup business plan" in prompt
        assert "research" in prompt.lower()
        assert "plan" in prompt.lower()

    def test_plan_prompt_with_context(self):
        prompt = build_plan_prompt("migration plan", context="Budget is $50k")
        assert "migration plan" in prompt
        assert "Budget is $50k" in prompt

    def test_plan_prompt_without_context(self):
        prompt = build_plan_prompt("test topic")
        assert "Additional Context" not in prompt

    def test_coding_prompt_contains_requirements(self):
        prompt = build_coding_prompt("Build a REST API")
        assert "Build a REST API" in prompt
        assert "code" in prompt.lower() or "software" in prompt.lower()

    def test_coding_prompt_with_repo(self):
        prompt = build_coding_prompt(
            "Add tests",
            git_repo_url="https://github.com/user/repo"
        )
        assert "https://github.com/user/repo" in prompt
        assert "clone" in prompt.lower()

    def test_coding_prompt_with_language(self):
        prompt = build_coding_prompt("Build API", language="Python/FastAPI")
        assert "Python/FastAPI" in prompt

    def test_coding_prompt_without_optionals(self):
        prompt = build_coding_prompt("Build something")
        assert "Existing Repository" not in prompt
        assert "Preferred Language" not in prompt


# ---------------------------------------------------------------------------
# Test: manus_api_client
# ---------------------------------------------------------------------------

from app.manus_api_client import (
    ManusAPIClient,
    ManusAPIError,
    TaskResult,
    TaskStatus,
    TaskMode,
    AgentProfile,
    CONNECTOR_MY_BROWSER,
    CONNECTOR_GITHUB,
)


class TestTaskResult:
    """Tests for the TaskResult data class."""

    def test_is_terminal_completed(self):
        result = TaskResult(task_id="t1", status=TaskStatus.COMPLETED)
        assert result.is_terminal is True

    def test_is_terminal_failed(self):
        result = TaskResult(task_id="t1", status=TaskStatus.FAILED)
        assert result.is_terminal is True

    def test_is_terminal_running(self):
        result = TaskResult(task_id="t1", status=TaskStatus.RUNNING)
        assert result.is_terminal is False

    def test_is_terminal_pending(self):
        result = TaskResult(task_id="t1", status=TaskStatus.PENDING)
        assert result.is_terminal is False

    def test_final_text_extraction(self):
        result = TaskResult(
            task_id="t1",
            status="completed",
            output=[
                {"role": "user", "content": [{"type": "output_text", "text": "Hello"}]},
                {"role": "assistant", "content": [
                    {"type": "output_text", "text": "Here is the answer."},
                    {"type": "output_text", "text": "More details here."},
                ]},
            ],
        )
        assert "Here is the answer." in result.final_text
        assert "More details here." in result.final_text

    def test_final_text_empty(self):
        result = TaskResult(task_id="t1", status="completed", output=[])
        assert result.final_text == ""

    def test_attachments_extraction(self):
        result = TaskResult(
            task_id="t1",
            status="completed",
            output=[
                {"role": "assistant", "content": [
                    {
                        "type": "output_file",
                        "fileUrl": "https://example.com/file.py",
                        "fileName": "main.py",
                        "mimeType": "text/x-python",
                    },
                ]},
            ],
        )
        assert len(result.attachments) == 1
        assert result.attachments[0]["file_name"] == "main.py"
        assert result.attachments[0]["url"] == "https://example.com/file.py"

    def test_to_json(self):
        result = TaskResult(task_id="t1", status="running")
        parsed = json.loads(result.to_json())
        assert parsed["task_id"] == "t1"
        assert parsed["status"] == "running"


class TestManusAPIClient:
    """Tests for ManusAPIClient initialization and configuration."""

    def test_default_initialization(self):
        with patch.dict(os.environ, {"MANUS_API_KEY": "test-key-123"}):
            client = ManusAPIClient()
            assert client.api_key == "test-key-123"
            assert "api.manus.ai" in client.base_url

    def test_custom_initialization(self):
        client = ManusAPIClient(
            api_key="custom-key",
            base_url="https://custom.api.com"
        )
        assert client.api_key == "custom-key"
        assert client.base_url == "https://custom.api.com"

    def test_missing_api_key_warning(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MANUS_API_KEY", None)
            # Should not raise, just warn
            client = ManusAPIClient(api_key="")
            assert client.api_key == ""

    def test_check_response_success(self):
        client = ManusAPIClient(api_key="test")
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Should not raise
        client._check_response(mock_response)

    def test_check_response_error(self):
        client = ManusAPIClient(api_key="test")
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        with pytest.raises(ManusAPIError) as exc_info:
            client._check_response(mock_response)
        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test: task_manager
# ---------------------------------------------------------------------------

from app.task_manager import TaskManager, LocalTaskRecord


class TestLocalTaskRecord:
    """Tests for LocalTaskRecord."""

    def test_summary_without_remote(self):
        record = LocalTaskRecord(
            task_id="t1",
            mode="web_search",
            original_input="test query",
            use_local_browser=False,
        )
        summary = record.to_summary()
        assert summary["task_id"] == "t1"
        assert summary["mode"] == "web_search"
        assert summary["status"] == "submitted"

    def test_summary_with_remote(self):
        remote = TaskResult(
            task_id="t1",
            status="running",
            title="Test Task",
            task_url="https://manus.im/app/t1",
        )
        record = LocalTaskRecord(
            task_id="t1",
            mode="plan",
            original_input="test topic",
            use_local_browser=True,
            remote=remote,
        )
        summary = record.to_summary()
        assert summary["status"] == "running"
        assert summary["title"] == "Test Task"
        assert summary["use_local_browser"] is True


class TestTaskManager:
    """Tests for TaskManager with mocked API client."""

    @pytest.fixture
    def mock_client(self):
        client = AsyncMock(spec=ManusAPIClient)
        return client

    @pytest.fixture
    def manager(self, mock_client):
        mgr = TaskManager(api_client=mock_client)
        return mgr

    @pytest.mark.asyncio
    async def test_create_web_search(self, manager, mock_client):
        mock_client.create_task.return_value = TaskResult(
            task_id="ws-001",
            status="running",
            title="Web Search",
            task_url="https://manus.im/app/ws-001",
        )

        result = await manager.create_web_search("Python 3.13 features")
        assert result["task_id"] == "ws-001"
        assert result["mode"] == "web_search"
        assert result["status"] == "running"

        # Verify API was called correctly
        mock_client.create_task.assert_called_once()
        call_kwargs = mock_client.create_task.call_args.kwargs
        assert "search" in call_kwargs["prompt"].lower()
        assert call_kwargs["use_local_browser"] is False

    @pytest.mark.asyncio
    async def test_create_plan(self, manager, mock_client):
        mock_client.create_task.return_value = TaskResult(
            task_id="pl-001",
            status="running",
            title="Plan Task",
            task_url="https://manus.im/app/pl-001",
        )

        result = await manager.create_plan(
            "AI startup business plan",
            context="Budget: $100k",
            use_local_browser=True,
        )
        assert result["task_id"] == "pl-001"
        assert result["mode"] == "plan"
        assert result["use_local_browser"] is True

        call_kwargs = mock_client.create_task.call_args.kwargs
        assert call_kwargs["use_local_browser"] is True

    @pytest.mark.asyncio
    async def test_create_coding(self, manager, mock_client):
        mock_client.create_task.return_value = TaskResult(
            task_id="cd-001",
            status="running",
            title="Coding Task",
            task_url="https://manus.im/app/cd-001",
        )

        result = await manager.create_coding(
            "Build a REST API",
            git_repo_url="https://github.com/user/repo",
            language="Python",
        )
        assert result["task_id"] == "cd-001"
        assert result["mode"] == "coding"

        call_kwargs = mock_client.create_task.call_args.kwargs
        assert CONNECTOR_GITHUB in (call_kwargs.get("connectors") or [])

    @pytest.mark.asyncio
    async def test_create_coding_no_repo(self, manager, mock_client):
        mock_client.create_task.return_value = TaskResult(
            task_id="cd-002",
            status="running",
            title="Coding Task",
            task_url="https://manus.im/app/cd-002",
        )

        result = await manager.create_coding("Build a CLI tool")
        assert result["task_id"] == "cd-002"

        call_kwargs = mock_client.create_task.call_args.kwargs
        # No GitHub connector when no repo URL
        assert not call_kwargs.get("connectors")

    @pytest.mark.asyncio
    async def test_get_status(self, manager, mock_client):
        # First create a task to populate local cache
        mock_client.create_task.return_value = TaskResult(
            task_id="t-001", status="running", title="Test",
            task_url="https://manus.im/app/t-001",
        )
        await manager.create_web_search("test")

        # Now check status
        mock_client.get_task.return_value = TaskResult(
            task_id="t-001",
            status="completed",
            title="Test",
            task_url="https://manus.im/app/t-001",
            output=[
                {"role": "assistant", "content": [
                    {"type": "output_text", "text": "The answer is 42."}
                ]}
            ],
        )

        status = await manager.get_status("t-001")
        assert status["status"] == "completed"
        assert status["is_complete"] is True
        assert "42" in status["final_text"]
        assert status["mode"] == "web_search"

    @pytest.mark.asyncio
    async def test_get_status_api_error(self, manager, mock_client):
        mock_client.get_task.side_effect = ManusAPIError("Not found", status_code=404)

        status = await manager.get_status("nonexistent")
        assert status["status"] == "error"
        assert "Not found" in status["error"]

    @pytest.mark.asyncio
    async def test_cancel_task(self, manager, mock_client):
        mock_client.delete_task.return_value = True

        result = await manager.cancel_task("t-001")
        assert result["success"] is True
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, manager, mock_client):
        mock_client.list_tasks.return_value = []

        results = await manager.list_tasks()
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Test: Constants and Enums
# ---------------------------------------------------------------------------

class TestConstants:
    """Tests for module constants and enums."""

    def test_task_mode_values(self):
        assert TaskMode.CHAT == "chat"
        assert TaskMode.ADAPTIVE == "adaptive"
        assert TaskMode.AGENT == "agent"

    def test_agent_profile_values(self):
        assert AgentProfile.STANDARD == "manus-1.6"
        assert AgentProfile.LITE == "manus-1.6-lite"
        assert AgentProfile.MAX == "manus-1.6-max"

    def test_task_status_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"

    def test_connector_uuids(self):
        assert CONNECTOR_MY_BROWSER == "be268223-40b2-4f3c-a907-c12eb1699283"
        assert CONNECTOR_GITHUB == "bbb0df76-66bd-4a24-ae4f-2aac4750d90b"
