"""
Integration tests for the MCP server tool layer.

These tests verify that:
- All MCP tools are properly registered
- Tools produce valid JSON output
- Error handling works correctly at the tool level
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.manus_api_client import TaskResult, ManusAPIError


class TestMCPToolRegistration:
    """Verify that all expected tools are registered in the MCP server."""

    def test_all_tools_importable(self):
        """Ensure the mcp_server module can be imported without errors."""
        import mcp_server
        assert hasattr(mcp_server, 'mcp')

    def test_manus_identity_exists(self):
        import mcp_server
        assert hasattr(mcp_server, 'manus_identity')

    def test_manus_web_search_exists(self):
        import mcp_server
        assert hasattr(mcp_server, 'manus_web_search')

    def test_manus_plan_exists(self):
        import mcp_server
        assert hasattr(mcp_server, 'manus_plan')

    def test_manus_code_exists(self):
        import mcp_server
        assert hasattr(mcp_server, 'manus_code')

    def test_get_task_status_exists(self):
        import mcp_server
        assert hasattr(mcp_server, 'get_task_status')

    def test_list_manus_tasks_exists(self):
        import mcp_server
        assert hasattr(mcp_server, 'list_manus_tasks')

    def test_cancel_task_exists(self):
        import mcp_server
        assert hasattr(mcp_server, 'cancel_task')


class TestMCPToolOutputFormat:
    """Verify that MCP tools return valid JSON strings."""

    @pytest.mark.asyncio
    async def test_manus_identity_returns_string(self):
        import mcp_server
        result = await mcp_server.manus_identity()
        assert isinstance(result, str)
        assert "manus_web_search" in result
        assert "manus_plan" in result
        assert "manus_code" in result

    @pytest.mark.asyncio
    async def test_web_search_returns_json(self):
        import mcp_server
        mock_result = {
            "task_id": "test-001",
            "mode": "web_search",
            "status": "running",
        }
        with patch.object(
            mcp_server.task_manager, 'create_web_search',
            new_callable=AsyncMock, return_value=mock_result
        ):
            result = await mcp_server.manus_web_search("test query")
            parsed = json.loads(result)
            assert parsed["task_id"] == "test-001"
            assert parsed["mode"] == "web_search"

    @pytest.mark.asyncio
    async def test_plan_returns_json(self):
        import mcp_server
        mock_result = {
            "task_id": "test-002",
            "mode": "plan",
            "status": "running",
        }
        with patch.object(
            mcp_server.task_manager, 'create_plan',
            new_callable=AsyncMock, return_value=mock_result
        ):
            result = await mcp_server.manus_plan("test topic")
            parsed = json.loads(result)
            assert parsed["task_id"] == "test-002"
            assert parsed["mode"] == "plan"

    @pytest.mark.asyncio
    async def test_code_returns_json(self):
        import mcp_server
        mock_result = {
            "task_id": "test-003",
            "mode": "coding",
            "status": "running",
        }
        with patch.object(
            mcp_server.task_manager, 'create_coding',
            new_callable=AsyncMock, return_value=mock_result
        ):
            result = await mcp_server.manus_code("build something")
            parsed = json.loads(result)
            assert parsed["task_id"] == "test-003"
            assert parsed["mode"] == "coding"

    @pytest.mark.asyncio
    async def test_get_status_returns_json(self):
        import mcp_server
        mock_result = {
            "task_id": "test-001",
            "status": "completed",
            "is_complete": True,
            "final_text": "The answer is 42.",
        }
        with patch.object(
            mcp_server.task_manager, 'get_status',
            new_callable=AsyncMock, return_value=mock_result
        ):
            result = await mcp_server.get_task_status("test-001")
            parsed = json.loads(result)
            assert parsed["status"] == "completed"
            assert parsed["is_complete"] is True

    @pytest.mark.asyncio
    async def test_list_tasks_returns_json_array(self):
        import mcp_server
        with patch.object(
            mcp_server.task_manager, 'list_tasks',
            new_callable=AsyncMock, return_value=[]
        ):
            result = await mcp_server.list_manus_tasks()
            parsed = json.loads(result)
            assert isinstance(parsed, list)

    @pytest.mark.asyncio
    async def test_cancel_returns_json(self):
        import mcp_server
        mock_result = {"task_id": "test-001", "status": "deleted", "success": True}
        with patch.object(
            mcp_server.task_manager, 'cancel_task',
            new_callable=AsyncMock, return_value=mock_result
        ):
            result = await mcp_server.cancel_task("test-001")
            parsed = json.loads(result)
            assert parsed["success"] is True


class TestMCPToolErrorHandling:
    """Verify that MCP tools handle errors gracefully."""

    @pytest.mark.asyncio
    async def test_web_search_error_returns_json(self):
        import mcp_server
        with patch.object(
            mcp_server.task_manager, 'create_web_search',
            new_callable=AsyncMock,
            side_effect=ManusAPIError("API key invalid", status_code=401)
        ):
            result = await mcp_server.manus_web_search("test")
            parsed = json.loads(result)
            assert "error" in parsed
            assert parsed["status"] == "failed"

    @pytest.mark.asyncio
    async def test_plan_error_returns_json(self):
        import mcp_server
        with patch.object(
            mcp_server.task_manager, 'create_plan',
            new_callable=AsyncMock,
            side_effect=Exception("Network error")
        ):
            result = await mcp_server.manus_plan("test")
            parsed = json.loads(result)
            assert "error" in parsed

    @pytest.mark.asyncio
    async def test_get_status_error_returns_json(self):
        import mcp_server
        with patch.object(
            mcp_server.task_manager, 'get_status',
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused")
        ):
            result = await mcp_server.get_task_status("bad-id")
            parsed = json.loads(result)
            assert parsed["status"] == "error"
            assert "error" in parsed
