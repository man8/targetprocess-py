"""Tests for targetprocess exception classes."""

import inspect
import pickle
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from targetprocess.exceptions import (
    AmbiguousMatchError,
    APIError,
    AuthenticationError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    ParseError,
    RateLimitError,
    ReadOnlyViolation,
    RequestValidationError,
    TargetProcessError,
    VerificationError,
)


def test_base_exception_hierarchy() -> None:
    """Test that all exceptions inherit from TargetProcessError."""
    assert issubclass(AuthenticationError, TargetProcessError)
    assert issubclass(ForbiddenError, TargetProcessError)
    assert issubclass(NotFoundError, TargetProcessError)
    assert issubclass(RequestValidationError, TargetProcessError)
    assert issubclass(RateLimitError, TargetProcessError)
    assert issubclass(ReadOnlyViolation, TargetProcessError)
    assert issubclass(APIError, TargetProcessError)
    assert issubclass(VerificationError, TargetProcessError)


def test_new_exception_hierarchy() -> None:
    """Test that the newly-introduced exceptions inherit from TargetProcessError."""
    for exc in (ForbiddenError, NetworkError, ParseError, RequestValidationError):
        assert issubclass(exc, TargetProcessError)


def test_old_shadowing_names_gone() -> None:
    """The pre-release rename removed the builtin-shadowing names entirely.

    No aliasing/deprecation shims - the old names must not resolve from
    either the package root or the exceptions module.
    """
    import targetprocess

    assert "PermissionError" not in targetprocess.__all__
    assert "ValidationError" not in targetprocess.__all__
    assert not hasattr(targetprocess.exceptions, "ValidationError")
    # PermissionError is still reachable from the package as the untouched
    # Python builtin (targetprocess never defines its own at module scope),
    # so this only asserts the library did not (re-)introduce a shadowing one.
    assert not hasattr(targetprocess.exceptions, "PermissionError")


def test_api_error_with_status_code() -> None:
    """Test APIError stores status code and message."""
    error = APIError("Something went wrong", status_code=500)
    assert error.status_code == 500
    assert str(error) == "Something went wrong"


def test_api_error_with_details() -> None:
    """Test APIError stores additional details."""
    details = {"endpoint": "/api/v1/users", "method": "GET"}
    error = APIError("Request failed", status_code=400, details=details)
    assert error.details == details
    assert error.status_code == 400


def test_readonly_violation_message() -> None:
    """Test ReadOnlyViolation has clear message."""
    error = ReadOnlyViolation("create", "UserStories")
    expected = "Cannot perform 'create' on 'UserStories': client is in readonly mode"
    assert str(error) == expected


def test_readonly_violation_carries_a_custom_reason() -> None:
    """Test the reason overrides the readonly-mode default in the message."""
    error = ReadOnlyViolation(
        "create", "RelationType", reason="the collection is read-only on the server"
    )
    expected = (
        "Cannot perform 'create' on 'RelationType': the collection is read-only on the server"
    )
    assert str(error) == expected
    assert error.operation == "create"
    assert error.resource == "RelationType"


def test_ambiguous_match_error_carries_the_key() -> None:
    err = AmbiguousMatchError(
        "3 Time entries already match assignable 51383 / user 1 on 2026-08-09",
        assignable_id=51383,
        user_id=1,
        day=date(2026, 8, 9),
        count=3,
    )
    assert err.assignable_id == 51383
    assert err.user_id == 1
    assert err.day == date(2026, 8, 9)
    assert err.count == 3
    assert isinstance(err, TargetProcessError)


def test_ambiguous_match_error_message_names_the_day() -> None:
    err = AmbiguousMatchError(
        "2 Time entries already match assignable 1 / user 2 on 2026-08-09",
        assignable_id=1,
        user_id=2,
        day=date(2026, 8, 9),
        count=2,
    )
    assert "2026-08-09" in str(err)
    assert "2" in str(err)


def test_ambiguous_match_error_generic_form() -> None:
    """The generic form - message only - is the contract priorities.resolve() uses."""
    err = AmbiguousMatchError("UserStory priority 'Must Have' matched 2 records (Ids: 1, 2)")
    assert str(err) == "UserStory priority 'Must Have' matched 2 records (Ids: 1, 2)"
    assert err.assignable_id is None
    assert err.user_id is None
    assert err.day is None
    assert err.count is None
    assert isinstance(err, TargetProcessError)


def test_verification_error_carries_its_context() -> None:
    import targetprocess

    error = VerificationError(
        "update_many did not verify 1 of 2 entities",
        entity_type="Task",
        mismatches={4: {"Effort": (1, VerificationError.ABSENT)}},
        verified_ids=[3],
    )

    assert str(error) == "update_many did not verify 1 of 2 entities"
    assert error.entity_type == "Task"
    assert error.entity_id is None
    assert error.mismatches == {4: {"Effort": (1, VerificationError.ABSENT)}}
    assert error.verified_ids == [3]
    assert repr(VerificationError.ABSENT) == "<absent>"
    assert "VerificationError" in targetprocess.__all__
    assert targetprocess.VerificationError is VerificationError


def test_verification_error_single_entity_form() -> None:
    error = VerificationError(
        "update did not verify",
        entity_type="UserStory",
        entity_id=123,
        mismatches={123: {"Effort": (3.0, 2.0)}},
    )

    assert error.entity_id == 123
    assert error.verified_ids == []


def test_split_transition_error_carries_both_workflows() -> None:
    import targetprocess
    from targetprocess.exceptions import SplitTransitionError

    error = SplitTransitionError(
        "UserStory 123 has a team level in workflow 9",
        entity_id=123,
        project_workflow_id=5,
        team_workflow_id=9,
    )

    assert issubclass(SplitTransitionError, TargetProcessError)
    assert str(error) == "UserStory 123 has a team level in workflow 9"
    assert (error.entity_id, error.project_workflow_id, error.team_workflow_id) == (123, 5, 9)
    assert "SplitTransitionError" in targetprocess.__all__
    assert targetprocess.SplitTransitionError is SplitTransitionError


# Every protocol this interpreter can write, so an error shipped across processes
# round-trips whichever one the sending side picks.
_PROTOCOLS = pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))


def _round_trip(value: object, protocol: int) -> Any:
    return pickle.loads(pickle.dumps(value, protocol))


@_PROTOCOLS
def test_absent_stays_the_one_absent_across_pickling(protocol: int) -> None:
    assert _round_trip(VerificationError.ABSENT, protocol) is VerificationError.ABSENT


@_PROTOCOLS
@pytest.mark.parametrize(
    ("entity_id", "verified_ids"), [(123, []), (None, [3])], ids=["single", "bulk"]
)
def test_verification_error_survives_a_pickle_round_trip(
    protocol: int, entity_id: int | None, verified_ids: list[int]
) -> None:
    error = VerificationError(
        "did not verify",
        entity_type="Task",
        entity_id=entity_id,
        mismatches={4: {"Effort": (1, VerificationError.ABSENT), "Name": ("a", "b")}},
        verified_ids=verified_ids,
    )

    loaded = _round_trip(error, protocol)

    assert type(loaded) is VerificationError
    assert str(loaded) == str(error)
    assert loaded.args == error.args
    assert loaded.entity_type == "Task"
    assert loaded.entity_id == entity_id
    assert loaded.mismatches == {4: {"Effort": (1, VerificationError.ABSENT), "Name": ("a", "b")}}
    assert loaded.mismatches[4]["Effort"][1] is VerificationError.ABSENT
    assert loaded.verified_ids == verified_ids
    assert loaded.__dict__ == error.__dict__


def _library_errors() -> dict[type[TargetProcessError], Callable[[], TargetProcessError]]:
    """One factory per exception class the module defines, each passing non-default arguments."""
    from targetprocess.exceptions import SplitTransitionError

    return {
        TargetProcessError: lambda: TargetProcessError("Something failed"),
        APIError: lambda: APIError(
            "Request failed", status_code=400, details={"endpoint": "/api/v1/Bugs", "method": "GET"}
        ),
        AuthenticationError: lambda: AuthenticationError("Invalid token"),
        ForbiddenError: lambda: ForbiddenError("Permission denied"),
        NotFoundError: lambda: NotFoundError("UserStory 123 not found"),
        RequestValidationError: lambda: RequestValidationError("Name is required"),
        RateLimitError: lambda: RateLimitError("Rate limit exceeded"),
        NetworkError: lambda: NetworkError("Connection reset"),
        ParseError: lambda: ParseError("Response failed model validation"),
        ReadOnlyViolation: lambda: ReadOnlyViolation(
            "update", "UserStory", reason="the collection is read-only on the server"
        ),
        AmbiguousMatchError: lambda: AmbiguousMatchError(
            "3 Time entries already match assignable 51383 / user 1 on 2026-08-09",
            assignable_id=51383,
            user_id=1,
            day=date(2026, 8, 9),
            count=3,
        ),
        VerificationError: lambda: VerificationError(
            "did not verify",
            entity_type="Task",
            entity_id=4,
            mismatches={4: {"Effort": (1, VerificationError.ABSENT)}},
            verified_ids=[3],
        ),
        SplitTransitionError: lambda: SplitTransitionError(
            "UserStory 123 has a team level in workflow 9",
            entity_id=123,
            project_workflow_id=5,
            team_workflow_id=9,
        ),
    }


@_PROTOCOLS
@pytest.mark.parametrize(
    "factory",
    list(_library_errors().values()),
    ids=[error_class.__name__ for error_class in _library_errors()],
)
def test_every_library_error_survives_a_pickle_round_trip(
    protocol: int, factory: Callable[[], TargetProcessError]
) -> None:
    error = factory()

    loaded = _round_trip(error, protocol)

    assert type(loaded) is type(error)
    assert str(loaded) == str(error)
    assert loaded.args == error.args
    assert loaded.__dict__ == error.__dict__


def test_the_pickle_table_covers_every_library_error() -> None:
    import targetprocess.exceptions as module

    defined = {
        member
        for _, member in inspect.getmembers(module, inspect.isclass)
        if issubclass(member, TargetProcessError) and member.__module__ == module.__name__
    }

    assert defined == set(_library_errors())
