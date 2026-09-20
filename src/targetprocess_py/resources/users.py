"""User resource manager."""

from typing import TYPE_CHECKING

from targetprocess_py.models import User
from targetprocess_py.resources.base import BaseResource
from targetprocess_py.response_parser import ResponseParser

if TYPE_CHECKING:
    from targetprocess_py.client import TargetProcessClient
    from targetprocess_py.request_handler import RequestHandler


class UsersResource(BaseResource[User]):
    """Resource manager for User entities.

    Provides type-safe CRUD operations for users, and ``logged_user()`` for
    the user the client's credential authenticates as.

    Example:
        client = TargetProcessClient(...)
        user = await client.users.get(123)
        async for user in client.users.list(limit=10):
            print(user.full_name)
        me = await client.users.logged_user()
    """

    entity_type = "User"
    model_class = User

    def __init__(
        self,
        client: "TargetProcessClient",
        request_handler: "RequestHandler",
    ) -> None:
        """Initialize resource manager.

        Args:
            client: TargetProcessClient instance for permission checks
            request_handler: RequestHandler for API operations
        """
        super().__init__(client, request_handler)
        # The user the credential authenticates as, resolved by logged_user()
        self._logged_user: User | None = None

    async def logged_user(self) -> User:
        """Resolve the user the client's credential authenticates as.

        One ``GET /api/v1/Users/LoggedUser`` returns that user's ``User``
        entity, parsed as ``get`` parses one, so it raises the same
        ``ParseError``. It is a read, so it works on a ``READONLY`` client.

        The result is cached on this resource, which the client builds once,
        so it lives as long as the client and a second call makes no request:
        the credential is fixed at construction, so the answer cannot change.
        Nothing is cached when the request or the parse fails, so a later call
        asks again. There is no lock - concurrent first calls may each make
        the request, and each caches the same user.

        Returns:
            The acting user.

        Raises:
            ParseError: The response failed model validation.
            AuthenticationError: Invalid credentials.
            ForbiddenError: Insufficient permissions.
            NotFoundError: The route answered 404.
            RateLimitError: A 429 persisted after the retries a read receives.
            NetworkError: Transport-level failure.
            APIError: Other API errors.

        Example:
            user = await client.users.logged_user()
            print(user.id, user.login)
        """
        if self._logged_user is not None:
            return self._logged_user
        data = await self._request_handler.logged_user()
        user = ResponseParser.parse_single(data, self.model_class)
        self._logged_user = user
        return user
