"""Response parser for TargetProcess API responses."""

from typing import Any, TypeVar

import httpx
import pydantic

from targetprocess.exceptions import (
    APIError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    ParseError,
    RateLimitError,
    RequestValidationError,
)
from targetprocess.models import Entity

T = TypeVar("T", bound=Entity)


class ResponseParser:
    """Parse TargetProcess API responses into Pydantic models."""

    @staticmethod
    def parse_single(data: dict[str, Any], model_class: type[T]) -> T:
        """Parse single entity response.

        Args:
            data: Raw JSON response data from TP API
            model_class: Pydantic model class to parse into

        Returns:
            Parsed entity instance

        Raises:
            ParseError: The response body failed model validation.

        Example:
            >>> data = {"Id": 123, "Name": "Story", "ResourceType": "UserStory"}
            >>> entity = ResponseParser.parse_single(data, UserStory)
        """
        try:
            return model_class.model_validate(data)
        except pydantic.ValidationError as exc:
            raise ParseError(f"failed to parse {model_class.__name__}: {exc}") from exc

    @staticmethod
    def parse_collection(data: dict[str, Any], model_class: type[T]) -> tuple[list[T], str | None]:
        """Parse collection response with pagination info.

        Args:
            data: Raw JSON collection response from TP API
            model_class: Pydantic model class to parse items into

        Returns:
            Tuple of (list of parsed entities, next page URL or None)

        Raises:
            ParseError: An item in the response body failed model validation.

        Example:
            >>> data = {"Items": [...], "Next": "https://...?skip=10"}
            >>> entities, next_url = ResponseParser.parse_collection(data, UserStory)
            >>> print(f"Got {len(entities)} items, more: {next_url is not None}")
        """
        items = data.get("Items") or []
        entities = [ResponseParser.parse_single(item, model_class) for item in items]
        next_url = data.get("Next")

        return entities, next_url

    @staticmethod
    def parse_error(response: httpx.Response) -> None:
        """Parse error response and raise appropriate exception.

        Args:
            response: HTTP response with error status code

        Raises:
            AuthenticationError: For 401 status
            ForbiddenError: For 403 status
            NotFoundError: For 404 status
            RequestValidationError: For 400 status
            RateLimitError: For 429 status
            APIError: For 5xx and other errors

        Example:
            >>> response = httpx.Response(404, json={"Error": "Not found"})
            >>> ResponseParser.parse_error(response)  # Raises NotFoundError
        """
        status = response.status_code

        # Try to extract error message from response body
        try:
            error_data = response.json()
            message = error_data.get("Error", str(error_data))
        except Exception:
            message = response.text or f"HTTP {status}"

        # Map status code to appropriate exception
        if status == 401:
            raise AuthenticationError(message)
        elif status == 403:
            raise ForbiddenError(message)
        elif status == 404:
            raise NotFoundError(message)
        elif status == 400:
            raise RequestValidationError(message)
        elif status == 429:
            raise RateLimitError(message)
        else:
            raise APIError(message, status_code=status, details={})
