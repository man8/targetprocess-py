"""Recorded write-path integration tests against a real TargetProcess instance.

The read-only counterpart is ``test_live_readonly.py``; this module and
``test_live_readwrite_surfaces.py`` are the only two in the *integration*
suite that build a ``READWRITE`` client, and so the only places in the
repository that send ``create``/``update``/``delete`` to a real instance
(the unit suite builds one against a mock transport). Cassettes live in
their own directory (``cassettes/test_live_readwrite/``) so a write-path
re-recording never disturbs a read-only one, or the other write module's.

Recording rules, which the tests below carry structurally rather than by
convention:

- **Sandbox only.** Every entity is created in ``_SANDBOX_PROJECT_ID``, a
  throwaway project that exists for exactly this purpose. No test here writes
  to any other project, and none touches an entity it did not create.
- **Every created entity is deleted by the test that created it**, in a
  ``finally`` so a mid-test failure still cleans up. The delete is not
  bookkeeping bolted on afterwards - it is the recorded ``delete``
  interaction, which is why it belongs in the test body rather than in a
  fixture teardown that a later refactor could quietly move out of the
  cassette.
- **Everything sent is synthetic.** ``_scrub_response`` replaces free-text and
  identity fields in a *response*, but ``_scrub_request`` scrubs only the host,
  the token and a custom field's name (the tenant's configuration) out of a
  *request* - a request body is otherwise recorded as sent. So a write-path
  test may only ever send text it invented (see ``_NAME_PREFIX``), never a
  value copied off the live instance.

Assertions are structural for the same reason the read-only ones are: by the
time an interaction reaches a cassette every ``Name``/``Description`` is the
placeholder ``Sanitised <Field>``, so a test cannot assert on the text it
sent. What survives the scrubber and still proves a write landed is the
echoed structure - the entity's own ``Id`` and ``ResourceType``, the
``Project``/``UserStory`` reference the request asked for, and
``EntityVersion``, which TP advances on every accepted change and which is
therefore the load-bearing evidence that an *update* did something.
"""

import pytest

from targetprocess import ClientMode, TargetProcessClient
from targetprocess.exceptions import NotFoundError

pytestmark = [pytest.mark.vcr, pytest.mark.integration]

# The throwaway project every entity below is created in. A module-level
# constant rather than configuration: which project a recording writes to is
# not a knob, and an environment-driven value could point a live recording at
# a real backlog.
_SANDBOX_PROJECT_ID = 49938

# Prefix on every entity name these tests create, so anything a failed
# recording strands on the live instance is findable in one search. It is
# invented text and nothing else. Scrubbed out of the response side of a
# cassette, recorded verbatim on the request side.
_NAME_PREFIX = "Synthetic recording"

_CREATED_DESCRIPTION = "Synthetic record created by an integration recording run."
_UPDATED_DESCRIPTION = "Synthetic record updated by an integration recording run."

# Sent on every update so each one can assert TP *applied* it, not merely
# accepted it. A numeric field is the only kind that can do that job here:
# the scrubber replaces the Name and Description an update sent, so reading
# either back would compare a placeholder with itself.
_UPDATED_EFFORT = 3.0


@pytest.mark.asyncio
async def test_user_story_create_update_delete_round_trip(live_credentials) -> None:
    """The full write path on the representative assignable, as TP answers it."""
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        story = await client.user_stories.create(
            Name=f"{_NAME_PREFIX} user story",
            Description=_CREATED_DESCRIPTION,
            Project={"Id": _SANDBOX_PROJECT_ID},
        )
        try:
            # The create echo is a fully hydrated entity, not a bare Id: TP
            # answers with the record it built, including the fields it
            # defaulted (state, priority, effort roll-up) rather than only
            # the ones the request sent.
            assert story.id > 0
            assert story.resource_type == "UserStory"
            assert story.project is not None
            assert story.project.id == _SANDBOX_PROJECT_ID
            assert story.entity_state is not None
            assert story.create_date is not None
            assert story.entity_version is not None

            updated = await client.user_stories.update(
                story.id,
                Name=f"{_NAME_PREFIX} user story (updated)",
                Description=_UPDATED_DESCRIPTION,
                Effort=_UPDATED_EFFORT,
            )

            # Same entity back, and TP advanced EntityVersion - the evidence
            # that the update was accepted, since the text it changed is a
            # placeholder by the time it reaches disk. ModifyDate cannot
            # serve: TP records it to the second, so a create and an
            # immediately following update share one.
            assert updated.id == story.id
            assert updated.resource_type == "UserStory"
            assert updated.entity_version is not None
            assert updated.entity_version > story.entity_version
            # Accepted is weaker than applied, and Effort closes the gap:
            # a numeric field is recorded verbatim by design, so it is the
            # one thing a test can send and then read back unchanged.
            assert updated.effort == _UPDATED_EFFORT
        finally:
            await client.user_stories.delete(story.id)

        # A success status on DELETE is not proof the entity is gone; the
        # read back is.
        with pytest.raises(NotFoundError):
            await client.user_stories.get(story.id)


@pytest.mark.asyncio
async def test_request_create_update_delete_round_trip(live_credentials) -> None:
    """A second entity class, whose response shape genuinely diverges.

    Warranted rather than duplicative: a Request comes back under its own
    ``EntityType`` and carries fields no assignable has - ``RequestType``,
    ``SourceType``, ``IsReplied``, ``IsPrivate``, ``VotesCount`` - so it
    exercises parsing the UserStory round trip above cannot reach.
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        request = await client.requests.create(
            Name=f"{_NAME_PREFIX} request",
            Description=_CREATED_DESCRIPTION,
            Project={"Id": _SANDBOX_PROJECT_ID},
        )
        try:
            assert request.id > 0
            assert request.resource_type == "Request"
            assert request.project is not None
            assert request.project.id == _SANDBOX_PROJECT_ID
            assert request.entity_state is not None
            assert request.entity_version is not None
            # The divergence this test exists for, asserted field by field
            # rather than named in the docstring and left to trust. Each is
            # declared ``| None = None`` on the model, so one that stopped
            # arriving would hydrate to None and fail nothing - which is
            # exactly the drift a re-recording is meant to catch.
            assert request.request_type is not None
            assert request.source_type is not None
            assert request.is_replied is not None
            assert request.is_private is not None
            assert request.votes_count is not None

            updated = await client.requests.update(
                request.id,
                Name=f"{_NAME_PREFIX} request (updated)",
                Description=_UPDATED_DESCRIPTION,
                Effort=_UPDATED_EFFORT,
            )

            assert updated.id == request.id
            assert updated.resource_type == "Request"
            assert updated.request_type is not None
            assert updated.entity_version is not None
            assert updated.entity_version > request.entity_version
            assert updated.effort == _UPDATED_EFFORT
        finally:
            await client.requests.delete(request.id)

        # The same read-back the UserStory round trip makes, for the same
        # reason: a success status on DELETE is not proof the entity is gone,
        # and a second entity class earns no exemption from that.
        with pytest.raises(NotFoundError):
            await client.requests.get(request.id)


@pytest.mark.asyncio
async def test_bulk_create_and_update_tasks_under_a_story(live_credentials) -> None:
    """``create_many``/``update_many`` against the real bulk endpoint.

    The bulk response envelope is undocumented by the vendor, so
    ``RequestHandler.bulk`` accepts either a bare JSON array or an
    ``Items``-wrapped object. This is the recorded evidence of which one TP
    actually sends - a fixture nobody has to take on trust.

    Note for anyone extending this: the create and the update hit the *same*
    URI, and vcrpy's default matcher ignores the body, so the two are
    distinguished only by the order they were recorded in - it replays the
    first not-yet-played match. Reordering them, or adding a third bulk
    call, would silently bind to the wrong recorded response rather than
    failing, so a change here wants the cassette re-recorded.
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        story = await client.user_stories.create(
            Name=f"{_NAME_PREFIX} bulk parent story",
            Description=_CREATED_DESCRIPTION,
            Project={"Id": _SANDBOX_PROJECT_ID},
        )
        tasks: list = []
        try:
            tasks = await client.tasks.create_many(
                [
                    {"Name": f"{_NAME_PREFIX} bulk task one", "UserStory": {"Id": story.id}},
                    {"Name": f"{_NAME_PREFIX} bulk task two", "UserStory": {"Id": story.id}},
                ]
            )

            assert len(tasks) == 2
            assert all(task.id > 0 and task.resource_type == "Task" for task in tasks)
            assert len({task.id for task in tasks}) == 2
            # Each task came back parented to the story the request named,
            # which is what makes this one bulk create rather than two
            # unrelated entities.
            assert all(task.user_story is not None for task in tasks)
            assert all(task.user_story.id == story.id for task in tasks)
            assert all(task.entity_version is not None for task in tasks)
            created_versions = {task.id: task.entity_version for task in tasks}

            updated = await client.tasks.update_many(
                [
                    {
                        "Id": task.id,
                        "Name": f"{_NAME_PREFIX} bulk task {position} (updated)",
                        "Effort": _UPDATED_EFFORT,
                    }
                    for position, task in enumerate(tasks, start=1)
                ]
            )

            assert [task.id for task in updated] == [task.id for task in tasks]
            assert all(task.entity_version is not None for task in updated)
            assert all(task.entity_version > created_versions[task.id] for task in updated)
            # The same applied-not-merely-accepted check the single-entity
            # round trips make, on the bulk path: every item in the batch
            # carried the numeric field, so every item must echo it back.
            assert all(task.effort == _UPDATED_EFFORT for task in updated)
        finally:
            # Every delete is attempted, whatever the ones before it did: a
            # loop that aborts on the first failure would strand the parent
            # story as well as the task it choked on, turning one stuck
            # record into three. Failures are collected and raised together
            # afterwards, because a cleanup that quietly swallowed them
            # would let the test pass over live residue - which is the one
            # outcome this module must never produce.
            #
            # Raising from a finally deliberately takes the headline from
            # whatever failure was already in flight; Python chains that one
            # as __context__, so it is still in the traceback. Live residue
            # is the more urgent of the two, and needs to be the line the
            # reader sees first.
            #
            # A bulk create that fails *partway* is the gap this cannot
            # close: TP does not document the endpoint as atomic, so tasks
            # it created but never named in the response are invisible here.
            # The post-recording sweep over the sandbox project is the
            # backstop for those, and finds them by the same name prefix
            # (see CONTRIBUTING.md).
            stranded = []
            for entity_type, resource, entity_id in [
                *(("Task", client.tasks, task.id) for task in tasks),
                ("UserStory", client.user_stories, story.id),
            ]:
                try:
                    await resource.delete(entity_id)
                except Exception as exc:
                    stranded.append(f"{entity_type} {entity_id}: {exc!r}")
            assert not stranded, f"recording left entities in the sandbox: {stranded}"

        # Read back every entity the test deleted, not just the parent: a
        # bulk run creates several, and a delete is evidenced by the 404, not
        # by its own success status. Checking only the story would leave the
        # tasks' deletes resting on "no exception raised".
        for task in tasks:
            with pytest.raises(NotFoundError):
                await client.tasks.get(task.id)
        with pytest.raises(NotFoundError):
            await client.user_stories.get(story.id)


@pytest.mark.asyncio
async def test_verified_update_returns_the_re_read(live_credentials) -> None:
    """``update(..., verify=True)``: the write, then an independent re-read narrowed to its keys.

    Only ``Effort`` is sent. A ``Name`` or ``Description`` would be replaced
    by a placeholder on the response side of the cassette, so the re-read
    would fail the comparison on every replay. The narrowed re-read carries
    no ``EntityVersion``, so a plain ``get`` afterwards is what shows the
    write was accepted as well as observed.
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        story = await client.user_stories.create(
            Name=f"{_NAME_PREFIX} verified update story",
            Description=_CREATED_DESCRIPTION,
            Project={"Id": _SANDBOX_PROJECT_ID},
        )
        try:
            assert story.entity_version is not None

            updated = await client.user_stories.update(
                story.id, Effort=_UPDATED_EFFORT, verify=True
            )

            assert updated.id == story.id
            assert updated.effort == _UPDATED_EFFORT
            # The re-read, not the echo: TP's update echo carries
            # EntityVersion, and a re-read narrowed to Effort does not.
            assert updated.entity_version is None

            reread = await client.user_stories.get(story.id)
            assert reread.entity_version is not None
            assert reread.entity_version > story.entity_version
        finally:
            await client.user_stories.delete(story.id)

        with pytest.raises(NotFoundError):
            await client.user_stories.get(story.id)


# Settable custom-field types in order of preference, each with the invented
# value a set sends. Text first: a string value is the plainest payload.
_CUSTOM_FIELD_VALUES: dict[str, object] = {
    "Text": f"{_NAME_PREFIX} value",
    "Number": 3.5,
    "CheckBox": True,
}


@pytest.mark.asyncio
async def test_custom_field_set_and_clear_round_trip(live_credentials) -> None:
    """``set_custom_field`` sets a value and clears it again, on a story it created.

    Verification is off on this path, deliberately. The response scrubber
    empties every ``CustomFields`` list in a cassette, so a verifying re-read
    could never observe the value on replay: it would pass while recording
    and fail on every run after. The re-read comparison is proven by the unit
    tests instead, and here each write's acceptance is evidenced by
    ``EntityVersion`` advancing. The field is chosen structurally, from the
    definitions the sandbox's process configures for UserStory, because its
    name is a placeholder on replay; the request body carries that
    placeholder too, since the request hook scrubs a custom field's name.
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        story = await client.user_stories.create(
            Name=f"{_NAME_PREFIX} custom field story",
            Description=_CREATED_DESCRIPTION,
            Project={"Id": _SANDBOX_PROJECT_ID},
        )
        try:
            assert story.entity_version is not None
            project = await client.projects.get(_SANDBOX_PROJECT_ID, include=["Process"])
            assert project.process is not None
            definitions = [
                definition
                async for definition in client.custom_fields.list(
                    where=(
                        f"(Process.Id eq {project.process.id}) and (EntityType.Name eq 'UserStory')"
                    ),
                    include=["Id", "Name", "FieldType", "EntityType", "Process"],
                )
            ]
            settable = [
                min(
                    (d for d in definitions if d.field_type == field_type),
                    key=lambda d: d.id,
                    default=None,
                )
                for field_type in _CUSTOM_FIELD_VALUES
            ]
            field = next((d for d in settable if d is not None), None)
            assert field is not None, (
                "no settable custom field for UserStory on the sandbox process"
            )
            assert field.name is not None and field.field_type is not None

            after_set = await client.user_stories.set_custom_field(
                story.id, field.name, _CUSTOM_FIELD_VALUES[field.field_type], verify=False
            )
            assert after_set.id == story.id
            assert after_set.entity_version is not None
            assert after_set.entity_version > story.entity_version

            after_clear = await client.user_stories.set_custom_field(
                story.id, field.name, None, verify=False
            )
            assert after_clear.id == story.id
            assert after_clear.entity_version is not None
            assert after_clear.entity_version > after_set.entity_version
        finally:
            await client.user_stories.delete(story.id)

        with pytest.raises(NotFoundError):
            await client.user_stories.get(story.id)
