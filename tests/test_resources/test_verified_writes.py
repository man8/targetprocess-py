"""Tests for verified writes: ``update``/``update_many`` with ``verify=True``.

Each scenario runs a real client over an ``httpx.MockTransport`` whose write
echo deliberately differs from the independent re-read, so a test can tell
which of the two a method returned.
"""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from targetprocess import TargetProcessClient
from targetprocess.exceptions import ReadOnlyViolation, VerificationError
from targetprocess.resources._verify import (
    compare_fields,
    custom_field_mismatch,
    describe,
    values_match,
)
from targetprocess.types import ClientMode

_STORY = "/api/v1/UserStory/123"
_ABSENT = VerificationError.ABSENT

Responder = dict[str, Any] | Callable[[httpx.Request], dict[str, Any]]


def _client(
    routes: dict[tuple[str, str], Responder], *, mode: ClientMode = ClientMode.READWRITE
) -> tuple[TargetProcessClient, list[httpx.Request]]:
    """A client whose transport answers ``routes`` by method and path, logging each request."""
    log: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        log.append(request)
        route = routes.get((request.method, request.url.path))
        if route is None:
            raise AssertionError(f"unexpected request {request.method} {request.url.path}")
        body = route(request) if callable(route) else route
        return httpx.Response(200, json=body)

    client = TargetProcessClient(domain="example.tpondemand.com", token="test-token", mode=mode)
    client._transport._client._transport = httpx.MockTransport(handle)
    return client, log


def _story(**fields: Any) -> dict[str, Any]:
    return {"ResourceType": "UserStory", "Id": 123, **fields}


# --- update(): the default path -------------------------------------------------------------


async def test_default_update_posts_once_and_returns_the_echo() -> None:
    client, log = _client(
        {
            ("POST", _STORY): _story(Effort=1.0),
            ("GET", _STORY): _story(Effort=3.0),
        }
    )

    story = await client.user_stories.update(123, Effort=3.0)

    assert [request.method for request in log] == ["POST"]
    assert json.loads(log[0].content) == {"Effort": 3.0}
    assert story.effort == 1.0  # the echo, unverified, exactly as before


# --- update(verify=True) ---------------------------------------------------------------------


async def test_verified_update_rereads_narrowed_to_the_requested_keys() -> None:
    client, log = _client(
        {
            ("POST", _STORY): _story(Effort=1.0),
            ("GET", _STORY): _story(Effort=3.0, EntityState={"Id": 52, "Name": "Sanitised Name"}),
        }
    )

    story = await client.user_stories.update(123, Effort=3.0, EntityState={"Id": 52}, verify=True)

    assert [request.method for request in log] == ["POST", "GET"]
    assert json.loads(log[0].content) == {"Effort": 3.0, "EntityState": {"Id": 52}}
    assert log[1].url.params["include"] == "[Effort,EntityState]"
    # The re-read model, never the echo.
    assert story.effort == 3.0
    assert story.entity_state is not None
    assert story.entity_state.id == 52


async def test_verified_update_raises_on_a_mismatch() -> None:
    client, _ = _client(
        {
            ("POST", _STORY): _story(Effort=3.0),
            ("GET", _STORY): _story(Effort=2.0),
        }
    )

    with pytest.raises(VerificationError) as caught:
        await client.user_stories.update(123, Effort=3.0, verify=True)

    error = caught.value
    assert error.entity_type == "UserStory"
    assert error.entity_id == 123
    assert error.mismatches == {123: {"Effort": (3.0, 2.0)}}
    assert error.verified_ids == []
    assert "UserStory 123" in str(error)
    assert "Effort: requested 3.0, observed 2.0" in str(error)


async def test_verified_update_reports_a_key_the_reread_does_not_carry() -> None:
    client, _ = _client(
        {
            ("POST", _STORY): _story(),
            ("GET", _STORY): _story(),
        }
    )

    with pytest.raises(VerificationError) as caught:
        await client.user_stories.update(123, Password="invented", verify=True)

    assert caught.value.mismatches == {123: {"Password": ("invented", _ABSENT)}}
    assert "Password: requested 'invented', observed <absent>" in str(caught.value)


@pytest.mark.parametrize(
    ("requested", "observed", "verifies"),
    [
        (None, None, True),
        (None, "Still set", False),
        ({"Id": 52}, {"Id": 52, "Name": "Sanitised Name", "NumericPriority": 2.0}, True),
        ({"Id": 52}, {"Id": 53, "Name": "Sanitised Name"}, False),
        (3, 3.0, True),
        ("  Padded  ", "Padded", True),
        ("/Date(1790000000000+0200)/", "/Date(1790000000000+0000)/", True),
        ("/Date(1790000000000+0200)/", "/Date(1790000060000+0200)/", False),
    ],
)
async def test_verified_update_applies_the_comparison_rules(
    requested: Any, observed: Any, verifies: bool
) -> None:
    client, log = _client(
        {
            ("POST", _STORY): _story(),
            ("GET", _STORY): _story(Field=observed),
        }
    )

    if verifies:
        story = await client.user_stories.update(123, Field=requested, verify=True)
        assert story.id == 123
    else:
        with pytest.raises(VerificationError):
            await client.user_stories.update(123, Field=requested, verify=True)
    # A verdict either way is the comparison's only when the entity was re-read.
    assert [request.method for request in log] == ["POST", "GET"]


async def test_verified_update_on_a_readonly_client_sends_nothing() -> None:
    client, log = _client({}, mode=ClientMode.READONLY)

    with pytest.raises(ReadOnlyViolation):
        await client.user_stories.update(123, Effort=3.0, verify=True)

    assert log == []


async def test_verified_update_refuses_an_unhydratable_include_before_the_write() -> None:
    client, log = _client({})

    with pytest.raises(ValueError, match="CustomFields"):
        await client.processes.update(
            7, CustomFields=[{"Name": "Deadline", "Value": None}], verify=True
        )

    assert log == []


_UNCHECKABLE_ENTRIES = pytest.mark.parametrize(
    "entry",
    [{"Value": "v"}, {"Name": 5, "Value": "v"}, "junk"],
    ids=["nameless", "non-string-name", "not-a-mapping"],
)


@_UNCHECKABLE_ENTRIES
async def test_verified_update_refuses_a_custom_field_entry_without_a_string_name(
    entry: object,
) -> None:
    client, log = _client({})

    with pytest.raises(ValueError, match=r"CustomFields entry 1 .*a verified write cannot check"):
        await client.user_stories.update(
            123, CustomFields=[{"Name": "Ticket", "Value": "v"}, entry], verify=True
        )

    assert log == []


async def test_unverified_update_sends_a_custom_field_entry_without_a_string_name() -> None:
    client, log = _client({("POST", _STORY): _story(Effort=1.0)})

    story = await client.user_stories.update(123, CustomFields=[{"Value": "v"}])

    assert [request.method for request in log] == ["POST"]
    assert json.loads(log[0].content) == {"CustomFields": [{"Value": "v"}]}
    assert story.effort == 1.0  # the echo


@pytest.mark.parametrize(
    ("key", "entries", "refused"),
    [
        ("customfields", [{"Value": "v"}], "customfields entry 0 "),
        (
            "CustomFields",
            ({"Name": "Ticket", "Value": "v"}, {"Value": "v"}),
            "CustomFields entry 1 ",
        ),
    ],
    ids=["lower-case-key", "tuple"],
)
async def test_verified_update_refuses_an_uncheckable_entry_under_any_key_casing_or_sequence(
    key: str, entries: object, refused: str
) -> None:
    client, log = _client({})

    with pytest.raises(ValueError, match=refused):
        await client.user_stories.update(123, verify=True, **{key: entries})

    assert log == []


def _ticket_routes() -> dict[tuple[str, str], Responder]:
    """A write echo with no custom fields, and a re-read carrying ``Ticket`` = ``"v"``."""
    ticket = {"Name": "Ticket", "Type": "Text", "Value": "v"}
    return {("POST", _STORY): _story(), ("GET", _STORY): _story(CustomFields=[ticket])}


async def test_verified_update_verifies_a_custom_fields_tuple() -> None:
    client, log = _client(_ticket_routes())

    story = await client.user_stories.update(
        123, CustomFields=({"Name": "Ticket", "Value": "v"},), verify=True
    )

    assert [request.method for request in log] == ["POST", "GET"]
    assert json.loads(log[0].content) == {"CustomFields": [{"Name": "Ticket", "Value": "v"}]}
    # The re-read model, never the echo.
    assert story.custom_fields is not None
    assert [(field.name, field.value) for field in story.custom_fields] == [("Ticket", "v")]


async def test_verified_update_finds_an_entry_whose_keys_are_in_any_casing() -> None:
    client, log = _client(_ticket_routes())

    await client.user_stories.update(
        123, CustomFields=[{"name": "Ticket", "value": "v"}], verify=True
    )

    assert [request.method for request in log] == ["POST", "GET"]


async def test_verified_update_sends_a_custom_fields_mapping_and_compares_it_whole() -> None:
    client, log = _client(_ticket_routes())

    mapping = {"Name": "Ticket", "Value": "v"}

    with pytest.raises(VerificationError) as caught:
        await client.user_stories.update(123, CustomFields=mapping, verify=True)

    assert [request.method for request in log] == ["POST", "GET"]
    assert json.loads(log[0].content) == {"CustomFields": mapping}
    assert caught.value.mismatches == {
        123: {"CustomFields": (mapping, [{"Name": "Ticket", "Type": "Text", "Value": "v"}])}
    }


# --- update_many(verify=True) ----------------------------------------------------------------


def _reread(efforts: dict[int, float | None]) -> Callable[[httpx.Request], dict[str, Any]]:
    def respond(request: httpx.Request) -> dict[str, Any]:
        entity_id = int(request.url.path.rsplit("/", 1)[1])
        effort = efforts[entity_id]
        body: dict[str, Any] = {"ResourceType": "UserStory", "Id": entity_id}
        if effort is not None:
            body["Effort"] = effort
        return body

    return respond


def _many_routes(efforts: dict[int, float | None]) -> dict[tuple[str, str], Responder]:
    routes: dict[tuple[str, str], Responder] = {
        ("POST", "/api/v1/UserStory/bulk"): {
            "Items": [{"ResourceType": "UserStory", "Id": i, "Effort": 1.0} for i in efforts]
        },
    }
    for entity_id in efforts:
        routes[("GET", f"/api/v1/UserStory/{entity_id}")] = _reread(efforts)
    return routes


async def test_default_update_many_posts_once_and_returns_the_echo() -> None:
    client, log = _client(_many_routes({5: 3.0, 6: 3.0}))

    stories = await client.user_stories.update_many(
        [{"Id": 5, "Effort": 3.0}, {"Id": 6, "Effort": 3.0}]
    )

    assert [request.method for request in log] == ["POST"]
    assert [story.effort for story in stories] == [1.0, 1.0]


async def test_verified_update_many_rereads_each_item_after_the_batch() -> None:
    client, log = _client(_many_routes({5: 3.0, 6: 4.0}))

    stories = await client.user_stories.update_many(
        [{"Id": 5, "Effort": 3.0}, {"id": 6, "Effort": 4.0}], verify=True
    )

    assert [(request.method, request.url.path) for request in log] == [
        ("POST", "/api/v1/UserStory/bulk"),
        ("GET", "/api/v1/UserStory/5"),
        ("GET", "/api/v1/UserStory/6"),
    ]
    assert [request.url.params["include"] for request in log[1:]] == ["[Effort]", "[Effort]"]
    assert [(story.id, story.effort) for story in stories] == [(5, 3.0), (6, 4.0)]


async def test_verified_update_many_checks_every_item_before_raising() -> None:
    client, log = _client(_many_routes({5: 2.0, 6: 3.0, 7: None}))

    with pytest.raises(VerificationError) as caught:
        await client.user_stories.update_many(
            [{"Id": 5, "Effort": 3.0}, {"Id": 6, "Effort": 3.0}, {"Id": 7, "Effort": 3.0}],
            verify=True,
        )

    assert len(log) == 4
    error = caught.value
    assert error.entity_type == "UserStory"
    assert error.entity_id is None
    assert error.mismatches == {5: {"Effort": (3.0, 2.0)}, 7: {"Effort": (3.0, _ABSENT)}}
    assert error.verified_ids == [6]
    assert "UserStory 5: Effort: requested 3.0, observed 2.0" in str(error)
    assert "UserStory 7: Effort: requested 3.0, observed <absent>" in str(error)


async def test_verified_update_many_keys_mismatches_and_verified_ids_by_integer_id() -> None:
    client, log = _client(_many_routes({5: 2.0, 6: 3.0}))

    with pytest.raises(VerificationError) as caught:
        await client.user_stories.update_many(
            [{"Id": "5", "Effort": 3.0}, {"Id": 6, "Effort": 3.0}], verify=True
        )

    assert [request.url.path for request in log[1:]] == [
        "/api/v1/UserStory/5",
        "/api/v1/UserStory/6",
    ]
    error = caught.value
    assert error.mismatches == {5: {"Effort": (3.0, 2.0)}}
    assert [type(key) for key in error.mismatches] == [int]
    assert error.verified_ids == [6]


@pytest.mark.parametrize("second_id", [5, "5"])
async def test_verified_update_many_refuses_an_entity_named_twice_before_the_write(
    second_id: int | str,
) -> None:
    client, log = _client({})

    with pytest.raises(ValueError, match="items 0 and 1 both name Id 5"):
        await client.user_stories.update_many(
            [{"Id": 5, "Effort": 3.0}, {"Id": second_id, "Name": "Invented"}], verify=True
        )

    assert log == []


@pytest.mark.parametrize("entity_id", ["five", " 5 ", "\uff15", True, 5.5, None])
async def test_verified_update_many_refuses_a_non_integer_id_before_the_write(
    entity_id: object,
) -> None:
    client, log = _client({})

    with pytest.raises(ValueError, match="verify=True needs an integer Id"):
        await client.user_stories.update_many([{"Id": entity_id, "Effort": 3.0}], verify=True)

    assert log == []


async def test_verified_update_many_on_a_readonly_client_sends_nothing() -> None:
    client, log = _client({}, mode=ClientMode.READONLY)

    with pytest.raises(ReadOnlyViolation):
        await client.user_stories.update_many([{"Id": 5, "Effort": 3.0}], verify=True)

    assert log == []


async def test_verified_update_many_refuses_an_unhydratable_include_before_the_write() -> None:
    client, log = _client({})

    with pytest.raises(ValueError, match="CustomFields"):
        await client.processes.update_many(
            [{"Id": 7, "CustomFields": [{"Name": "Deadline", "Value": None}]}], verify=True
        )

    assert log == []


async def test_verified_update_many_refuses_a_custom_field_entry_naming_item_and_entry() -> None:
    client, log = _client({})

    with pytest.raises(
        ValueError, match=r"^update_many item 1: CustomFields entry 0 .*cannot check"
    ):
        await client.user_stories.update_many(
            [
                {"Id": 5, "CustomFields": [{"Name": "Ticket", "Value": "v"}]},
                {"Id": 6, "CustomFields": [{"Value": "v"}]},
            ],
            verify=True,
        )

    assert log == []


# --- the comparison, directly -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "observed", "matches"),
    [
        ("3", 3, False),
        (3, "3", False),
        ("3", 3.0, False),
        (5, 5.0, True),
        (" x ", "x", True),
        (True, 1, False),
    ],
    ids=["str-int", "int-str", "str-float", "int-float", "padded-str", "bool-int"],
)
def test_values_match_applies_the_scalar_rules(
    requested: object, observed: object, matches: bool
) -> None:
    assert values_match(requested, observed) is matches


def test_compare_fields_matches_keys_case_insensitively() -> None:
    assert compare_fields({"effort": 3.0}, {"Id": 1, "Effort": 3.0}) == {}


def test_compare_fields_treats_a_requested_none_as_null_or_absent() -> None:
    assert compare_fields({"Release": None}, {"Release": None}) == {}
    assert compare_fields({"Release": None}, {"Id": 1}) == {}
    assert compare_fields({"Release": None}, {"Release": {"Id": 9}}) == {
        "Release": (None, {"Id": 9})
    }


def test_compare_fields_reports_an_absent_key() -> None:
    assert compare_fields({"Effort": 3.0}, {"Id": 1}) == {"Effort": (3.0, _ABSENT)}


def test_compare_fields_matches_a_reference_by_id_alone() -> None:
    assert compare_fields({"Team": {"id": 4}}, {"Team": {"Id": 4, "Name": "Sanitised Name"}}) == {}
    assert compare_fields({"Team": {"Id": 4}}, {"Team": None}) == {"Team": ({"Id": 4}, None)}
    assert compare_fields({"Team": {"Id": 4}}, {"Team": "4"}) == {"Team": ({"Id": 4}, "4")}


def test_compare_fields_compares_numbers_numerically_but_not_booleans() -> None:
    assert compare_fields({"Effort": 3}, {"Effort": 3.0}) == {}
    assert compare_fields({"Effort": 3}, {"Effort": 3.5}) == {"Effort": (3, 3.5)}
    assert compare_fields({"IsPrivate": True}, {"IsPrivate": 1}) == {"IsPrivate": (True, 1)}
    assert compare_fields({"Effort": 1}, {"Effort": True}) == {"Effort": (1, True)}
    assert compare_fields({"IsPrivate": False}, {"IsPrivate": False}) == {}


def test_compare_fields_strips_strings() -> None:
    assert compare_fields({"Name": " Example "}, {"Name": "Example"}) == {}
    assert compare_fields({"Name": "Example"}, {"Name": "Other"}) == {"Name": ("Example", "Other")}


def test_compare_fields_compares_wire_dates_on_the_instant() -> None:
    assert (
        compare_fields(
            {"PlannedEndDate": "/Date(1790000000000+0200)/"},
            {"PlannedEndDate": "/Date(1790000000000-0500)/"},
        )
        == {}
    )
    # A wire date against a plain string that is not one compares as text.
    assert compare_fields({"Note": "/Date(1790000000000)/"}, {"Note": "soon"}) == {
        "Note": ("/Date(1790000000000)/", "soon")
    }


def test_compare_fields_compares_other_values_by_equality() -> None:
    assert compare_fields({"Tags": ["a", "b"]}, {"Tags": ["a", "b"]}) == {}
    assert compare_fields({"Tags": ["a", "b"]}, {"Tags": ["b", "a"]}) == {
        "Tags": (["a", "b"], ["b", "a"])
    }
    assert compare_fields({"Shape": {"Kind": "x"}}, {"Shape": {"Kind": "x"}}) == {}


def test_compare_fields_matches_custom_fields_entry_by_entry() -> None:
    observed = {
        "CustomFields": [
            {"Name": "Deadline", "Type": "Date", "Value": "/Date(1790805600000+0200)/"},
            {"Name": "Ticket", "Type": "Text", "Value": "Kept"},
        ]
    }
    sent = {"CustomFields": [{"Name": "deadline", "Value": "/Date(1790805600000+0000)/"}]}
    assert compare_fields(sent, observed) == {}
    assert compare_fields(
        {"CustomFields": [{"Name": "Ticket", "Value": None}, {"Name": "Missing", "Value": 1}]},
        observed,
    ) == {
        "CustomFields[Ticket]": (None, "Kept"),
        "CustomFields[Missing]": (1, _ABSENT),
    }


def test_compare_fields_matches_a_custom_fields_tuple_entry_by_entry() -> None:
    observed = {"CustomFields": [{"Name": "Ticket", "Type": "Text", "Value": "Kept"}]}

    assert compare_fields({"CustomFields": ({"Name": "ticket", "Value": "Kept"},)}, observed) == {}
    assert compare_fields({"CustomFields": ({"Name": "Ticket", "Value": "Other"},)}, observed) == {
        "CustomFields[Ticket]": ("Other", "Kept")
    }


@pytest.mark.parametrize(
    "value",
    ["Ticket", b"Ticket", bytearray(b"Ticket"), {"Name": "Ticket", "Value": "v"}],
    ids=["str", "bytes", "bytearray", "mapping"],
)
def test_compare_fields_compares_a_custom_fields_string_bytes_or_mapping_whole(
    value: object,
) -> None:
    assert compare_fields({"CustomFields": value}, {"CustomFields": value}) == {}
    assert compare_fields({"CustomFields": value}, {"CustomFields": []}) == {
        "CustomFields": (value, [])
    }


@_UNCHECKABLE_ENTRIES
def test_compare_fields_reports_a_custom_field_entry_without_a_string_name(entry: object) -> None:
    observed = {"CustomFields": [{"Name": "Ticket", "Type": "Text", "Value": "v"}]}

    assert compare_fields(
        {"CustomFields": [{"Name": "Ticket", "Value": "v"}, entry]}, observed
    ) == {"CustomFields[#1]": (entry, _ABSENT)}
    assert compare_fields({"CustomFields": [entry]}, {"CustomFields": []}) == {
        "CustomFields[#0]": (entry, _ABSENT)
    }


def test_custom_field_mismatch_accepts_null_or_empty_as_cleared() -> None:
    assert custom_field_mismatch("Ticket", None, [{"Name": "Ticket", "Value": None}]) is None
    assert custom_field_mismatch("Ticket", None, [{"Name": "Ticket", "Value": ""}]) is None
    assert custom_field_mismatch("Ticket", None, [{"Name": "Ticket"}]) is None
    assert custom_field_mismatch("Ticket", None, [{"Name": "Ticket", "Value": "x"}]) == (None, "x")


def test_custom_field_mismatch_reports_an_absent_entry() -> None:
    assert custom_field_mismatch("Ticket", "x", []) == ("x", _ABSENT)
    assert custom_field_mismatch("Ticket", "x", None) == ("x", _ABSENT)
    assert custom_field_mismatch("Ticket", None, [{"Name": "Other", "Value": None}]) == (
        None,
        _ABSENT,
    )


def test_custom_field_mismatch_does_not_equate_an_iso_date_with_the_wire_form() -> None:
    # A date-typed value reads back as a wire date; an ISO string sent for it is
    # not normalised, so it cannot verify - the documented limit.
    wire = "/Date(1790805600000+0200)/"
    entries = [{"Name": "Deadline", "Type": "Date", "Value": wire}]

    assert custom_field_mismatch("Deadline", "2026-10-01", entries) == ("2026-10-01", wire)
    assert custom_field_mismatch("Deadline", "2026-09-30T22:00:00Z", entries) == (
        "2026-09-30T22:00:00Z",
        wire,
    )
    assert custom_field_mismatch("Deadline", wire, entries) is None


def test_custom_field_mismatch_applies_the_scalar_rules() -> None:
    entries = [{"name": " Points ", "value": 3.0}]
    assert custom_field_mismatch("points", 3, entries) is None
    assert custom_field_mismatch("Points", 4, entries) == (4, 3.0)


def test_describe_lists_each_field_per_entity() -> None:
    text = describe("Bug", {9: {"Effort": (3.0, _ABSENT), "Name": ("a", "b")}})

    assert (
        text == "Bug 9: Effort: requested 3.0, observed <absent>; Name: requested 'a', observed 'b'"
    )
