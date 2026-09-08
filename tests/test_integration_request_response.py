"""Integration tests for request/response handling."""

import pytest

from targetprocess import ClientMode, TargetProcessClient
from targetprocess.models import Entity
from targetprocess.request_handler import RequestHandler
from targetprocess.response_parser import ResponseParser


@pytest.mark.asyncio
async def test_end_to_end_request_response_flow() -> None:
    """Test complete request/response flow without real API.

    This demonstrates how the components work together:
    1. Client initializes transport
    2. RequestHandler wraps transport for rate-limited requests
    3. ResponseParser parses responses
    """
    from unittest.mock import AsyncMock, Mock

    import httpx

    # Create client
    async with TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    ) as client:
        # Create RequestHandler from client's transport
        request_handler = RequestHandler(client._transport)

        # Mock the transport's HTTP client
        mock_client = Mock()
        mock_client.request = AsyncMock(
            return_value=httpx.Response(
                200,
                json={
                    "Items": [
                        {
                            "Id": 1,
                            "Name": "Story 1",
                            "ResourceType": "UserStory",
                            "CreateDate": None,
                            "ModifyDate": None,
                        },
                        {
                            "Id": 2,
                            "Name": "Story 2",
                            "ResourceType": "UserStory",
                            "CreateDate": None,
                            "ModifyDate": None,
                        },
                    ],
                    "Next": None,
                },
            )
        )
        mock_client.aclose = AsyncMock()
        client._transport._client = mock_client

        # Test list operation
        items = []
        async for item in request_handler.list("UserStories"):
            items.append(item)

        assert len(items) == 2

        # Test parsing with ResponseParser
        data = {"Items": items, "Next": None}
        entities, next_url = ResponseParser.parse_collection(data, Entity)

        assert len(entities) == 2
        assert entities[0].id == 1
        assert entities[1].id == 2
        assert next_url is None


@pytest.mark.asyncio
async def test_error_handling_integration() -> None:
    """Test error handling flows through request/response."""
    from unittest.mock import AsyncMock, Mock

    import httpx

    from targetprocess.exceptions import NotFoundError

    async with TargetProcessClient(
        domain="example.tpondemand.com",
        token="test-token",
        mode=ClientMode.READONLY,
    ) as client:
        # Create RequestHandler from client's transport
        request_handler = RequestHandler(client._transport)

        # Mock 404 response
        mock_client = Mock()
        mock_client.request = AsyncMock(
            return_value=httpx.Response(404, json={"Error": "Entity not found"})
        )
        mock_client.aclose = AsyncMock()
        client._transport._client = mock_client

        # Verify error propagates correctly
        with pytest.raises(NotFoundError) as exc_info:
            await request_handler.get("UserStories", 99999)

        assert "Entity not found" in str(exc_info.value)
