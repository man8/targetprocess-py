"""Recorded, read-only integration tests against a real TargetProcess instance.

Recorded once with ``ALLOW_PROD_RECORDING=1`` (see conftest.py); every other
run replays the token-filtered cassettes under ``tests/integration/cassettes/``
offline. Only list/get calls are made here - never create/update/delete.
"""

import pytest

from targetprocess import ClientMode, TargetProcessClient

pytestmark = [pytest.mark.vcr, pytest.mark.integration]

# Assignable/User are references, so they need an explicit include to arrive.
_TIME_INCLUDE = ["Id", "Date", "Spent", "Assignable", "User"]


@pytest.mark.asyncio
async def test_list_user_stories_parses(live_credentials) -> None:
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READONLY) as client:
        stories = [s async for s in client.user_stories.list(limit=3)]
    assert 0 < len(stories) <= 3
    assert all(s.id > 0 for s in stories)


@pytest.mark.asyncio
async def test_pagination_crosses_page_boundary(live_credentials) -> None:
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READONLY) as client:
        items = [s async for s in client.user_stories.list(limit=30, page_size=10)]
    assert len(items) == 30  # 3 pages followed via Next


@pytest.mark.asyncio
async def test_get_single_with_include(live_credentials) -> None:
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READONLY) as client:
        first = [s async for s in client.user_stories.list(limit=1)][0]
        story = await client.user_stories.get(first.id, include=["Id", "Name"])
    assert story.id == first.id


@pytest.mark.asyncio
async def test_generic_entities_comment(live_credentials) -> None:
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READONLY) as client:
        comments = [c async for c in client.entities.list("Comments", limit=2)]
    assert len(comments) > 0  # guard against all() vacuously passing on an empty collection
    assert all(c.id > 0 for c in comments)


@pytest.mark.asyncio
async def test_find_for_day_matches_a_real_entry(live_credentials) -> None:
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READONLY) as client:
        seed = [t async for t in client.times.list(limit=1, include=_TIME_INCLUDE)][0]
        assert seed.date is not None
        assert seed.assignable is not None and seed.user is not None
        tz = seed.date.tzinfo
        assert tz is not None
        day = seed.date.astimezone(tz).date()
        found = await client.times.find_for_day(
            assignable_id=seed.assignable.id,
            user_id=seed.user.id,
            day=day,
            tz=tz,
        )
    assert found  # guard against all() vacuously passing on an empty result
    assert any(t.id == seed.id for t in found)
    assert all(t.date is not None and t.date.astimezone(tz).date() == day for t in found)


@pytest.mark.asyncio
async def test_priorities_scoped_to_an_entity_type(live_credentials) -> None:
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READONLY) as client:
        priorities = await client.priorities.for_entity_type("UserStory")
    # Names are scrubbed out of cassettes, so assert on structure only: TP
    # accepted the EntityType filter and every record came back scoped to the
    # one entity type (Id 4 = UserStory).
    assert len(priorities) > 0
    assert all(p.id > 0 for p in priorities)
    assert all(p.entity_type is not None for p in priorities)
    assert {p.entity_type.id for p in priorities if p.entity_type} == {4}


@pytest.mark.asyncio
async def test_entity_types_catalogue_parses(live_credentials) -> None:
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READONLY) as client:
        types = [
            t
            async for t in client.entity_types.list(
                include=["Id", "Name", "IsAssignable", "IsExtendable"]
            )
        ]
    # Names are scrubbed out of cassettes, so assert on structure: every
    # record parsed as an EntityType with its flags hydrated, and the
    # catalogue holds both work-item and non-work-item types.
    assert len(types) > 0
    assert all(t.id > 0 and t.resource_type == "EntityType" for t in types)
    assert {t.is_assignable for t in types} == {True, False}
    assert all(t.is_extendable is not None for t in types)


@pytest.mark.asyncio
async def test_severities_rank_the_bug_set(live_credentials) -> None:
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READONLY) as client:
        severities = [
            s
            async for s in client.severities.list(include=["Id", "Name", "Importance", "IsDefault"])
        ]
    assert len(severities) > 0
    assert all(s.id > 0 and s.resource_type == "Severity" for s in severities)
    # Importance ranks the set; every record carries one and the ranks are distinct.
    ranks = [s.importance for s in severities]
    assert all(rank is not None and rank >= 1 for rank in ranks)
    assert len(set(ranks)) == len(ranks)
