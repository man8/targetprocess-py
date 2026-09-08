"""Tests for ResponseParser."""

import httpx
import pydantic
import pytest

from targetprocess.exceptions import (
    APIError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    ParseError,
    RateLimitError,
    RequestValidationError,
)
from targetprocess.models import Entity, NamedEntity
from targetprocess.response_parser import ResponseParser


def test_parse_single_entity() -> None:
    """Test parsing single entity response."""
    data = {
        "Id": 123,
        "Name": "Test Entity",
        "ResourceType": "UserStory",
        "CreateDate": None,
        "ModifyDate": None,
    }

    entity = ResponseParser.parse_single(data, NamedEntity)

    assert entity.id == 123
    assert entity.name == "Test Entity"
    assert entity.resource_type == "UserStory"


def test_parse_single_wraps_pydantic_validation_error() -> None:
    """A model_validate failure surfaces as ParseError, not raw pydantic."""
    data = {"Id": "not-an-int", "Name": "Bad", "ResourceType": "UserStory"}

    with pytest.raises(ParseError) as exc_info:
        ResponseParser.parse_single(data, NamedEntity)

    assert isinstance(exc_info.value.__cause__, pydantic.ValidationError)


def test_parse_collection_wraps_pydantic_validation_error() -> None:
    """A model_validate failure on a collection item surfaces as ParseError."""
    data = {"Items": [{"Id": "not-an-int"}], "Next": None}

    with pytest.raises(ParseError):
        ResponseParser.parse_collection(data, Entity)


def test_parse_collection_with_next_url() -> None:
    """Test parsing collection with pagination."""
    data = {
        "Items": [
            {
                "Id": 1,
                "Name": "First",
                "ResourceType": "UserStory",
                "CreateDate": None,
                "ModifyDate": None,
            },
            {
                "Id": 2,
                "Name": "Second",
                "ResourceType": "UserStory",
                "CreateDate": None,
                "ModifyDate": None,
            },
        ],
        "Next": "https://example.tpondemand.com/api/v1/UserStories?skip=2&take=2",
        "Prev": None,
    }

    entities, next_url = ResponseParser.parse_collection(data, Entity)

    assert len(entities) == 2
    assert entities[0].id == 1
    assert entities[1].id == 2
    assert next_url == "https://example.tpondemand.com/api/v1/UserStories?skip=2&take=2"


def test_parse_collection_last_page() -> None:
    """Test parsing collection on last page (no Next URL)."""
    data = {
        "Items": [
            {
                "Id": 99,
                "Name": "Last",
                "ResourceType": "UserStory",
                "CreateDate": None,
                "ModifyDate": None,
            },
        ],
        "Next": None,
        "Prev": "https://example.tpondemand.com/api/v1/UserStories?skip=0&take=2",
    }

    entities, next_url = ResponseParser.parse_collection(data, Entity)

    assert len(entities) == 1
    assert entities[0].id == 99
    assert next_url is None


def test_parse_collection_empty() -> None:
    """Test parsing empty collection."""
    data = {"Items": [], "Next": None, "Prev": None}

    entities, next_url = ResponseParser.parse_collection(data, Entity)

    assert len(entities) == 0
    assert next_url is None


@pytest.mark.parametrize(
    "status_code,exception_class",
    [
        (401, AuthenticationError),
        (403, ForbiddenError),
        (404, NotFoundError),
        (400, RequestValidationError),
        (429, RateLimitError),
        (500, APIError),
        (503, APIError),
    ],
)
def test_parse_error_maps_status_codes(status_code: int, exception_class: type) -> None:
    """Test error status code mapping to exception types."""
    response = httpx.Response(
        status_code,
        json={"Error": "Test error message"},
    )

    with pytest.raises(exception_class) as exc_info:
        ResponseParser.parse_error(response)

    assert "Test error message" in str(exc_info.value)


def test_parse_error_extracts_message_from_json() -> None:
    """Test error message extraction from JSON response."""
    response = httpx.Response(
        404,
        json={"Error": "Entity with Id 99999 not found"},
    )

    with pytest.raises(NotFoundError) as exc_info:
        ResponseParser.parse_error(response)

    assert "Entity with Id 99999 not found" in str(exc_info.value)


def test_parse_error_handles_non_json_response() -> None:
    """Test error handling when response is not JSON."""
    response = httpx.Response(
        500,
        text="Internal Server Error",
    )

    with pytest.raises(APIError) as exc_info:
        ResponseParser.parse_error(response)

    assert "Internal Server Error" in str(exc_info.value)
