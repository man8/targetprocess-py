"""Tests for targetprocess exception classes."""

from datetime import date

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
