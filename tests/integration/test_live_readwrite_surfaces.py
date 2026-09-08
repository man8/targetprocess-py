"""Recorded write-path tests for the join, content and file surfaces.

``test_live_readwrite.py`` covers the write path on the entities that carry
work - UserStory, Request, and a bulk Task batch. This module covers the
surfaces hung *off* those entities: ``comments``, ``assignments``,
``team_assignments``, ``role_efforts``, ``relations`` and ``attachments``. A second module rather
than more tests in the first, because a tracked file stops at 1000 lines
(``scripts/check_large_files.py``) and because each module owns its own
cassette directory, so re-recording one surface never disturbs another's.

Every test here reads some piece of org-level state it may not create - a
Role, a RelationType, a project membership - but ``team_assignments`` is the
one whose recording needs that state *changed* first, temporarily. TargetProcess refuses a
TeamAssignment unless the Team is assigned to the card's project, and the
sandbox carries no such link in its steady state - so re-recording
``test_team_assignment_create_and_delete`` needs a team linked to the sandbox
project for the duration of that run, made and removed by hand because the
link is instance configuration rather than a throwaway record. The test reads
the team back out of the project's own ``TeamProject`` row rather than naming
one, so it binds to whichever team is linked at record time. Every other run
replays the cassette offline and needs no link at all (CONTRIBUTING.md and
docs/testing.md say the same).

Every recording rule the write path carries is stated in
``test_live_readwrite.py``'s docstring and in ``docs/testing.md``; they apply
here unchanged - sandbox project only, every created entity deleted by the
test that created it in a ``finally``, and nothing sent that was not
invented here. Two rules this module is the first to need:

- **Org-level Ids are read, never created.** A Role, a Team and a
  RelationType already exist on the instance and are defined instance-wide,
  so creating one would be a write outside the sandbox. Each test reads the
  collection and picks a member; none of them writes to it.
- **A read inside a write-path test is scoped to what the test created.**
  ``attachments.list()`` unfiltered would record a real customer's files
  into a fixture. Every read here carries a ``where=`` naming the entity the
  test just created, except the three instance-wide lookups above, whose
  free text the scrubber replaces.

Picking a lookup member **structurally** - the lowest Id - rather than by
name is deliberate, and not merely tidiness: ``_scrub_response`` rewrites
every ``Name`` to ``Sanitised Name`` before a cassette reaches disk, so a
``resolve(<a role name>)`` recorded here would find nothing on replay. The
lowest Id is stable across a record and every replay, and it keeps the real
role and team names this ran against out of the repository entirely.
"""

from typing import Protocol

import pytest

from targetprocess import ClientMode, TargetProcessClient
from targetprocess.exceptions import NotFoundError

pytestmark = [pytest.mark.vcr, pytest.mark.integration]

# Deliberately duplicated from ``test_live_readwrite.py`` rather than
# imported: which project a recording writes to, and which reference its
# entities are named for, are properties of *this* module's recording run.
# Importing them would let a later edit to one module silently retarget the
# other's live writes.
_SANDBOX_PROJECT_ID = 49938

# One prefix for the whole module, fixed by the recording that established
# it. A re-record of a *single* cassette keeps it rather than adopting its
# own reference: the string's job is to make everything this module has ever
# created findable in one search, and a second prefix would mean the sweep
# after a partial re-record no longer covers the cassettes it did not touch.
_NAME_PREFIX = "MAN8-9036 recording"

_CREATED_DESCRIPTION = "Synthetic record created by an integration recording run."
_UPDATED_DESCRIPTION = "Synthetic record updated by an integration recording run."

# The effort a RoleEffort is created with and then updated to. Numeric, for
# the same reason the sibling module sends one: a number survives the
# scrubber verbatim, so it is the only kind of value a test can send and
# then read back as proof TP *applied* the change rather than merely
# accepting it.
_CREATED_EFFORT = 2.0
_UPDATED_EFFORT = 5.0

# The attachment this module uploads: a few bytes of text invented here, and
# a filename that is the recording reference and nothing else. Never a real
# document, and never a real filename - a request body is recorded as sent.
_UPLOAD_FILENAME = "man8-9036-recording.txt"
_UPLOAD_CONTENT = b"Synthetic attachment content for an integration recording run.\n"
_UPLOAD_MIME_TYPE = "text/plain"


class _HasId(Protocol):
    """The one attribute ``_lowest_id`` needs of a lookup record."""

    id: int


def _lowest_id[T: _HasId](items: list[T]) -> T:
    """Return the member of an instance-wide lookup with the lowest Id.

    The selection rule for every Role, Team and RelationType below. It has to
    be structural: names are placeholders by the time a cassette is replayed,
    so no test here can select by one (see the module docstring). Lowest Id
    rather than "first returned" because collection ordering is the server's
    to choose and a recording should not depend on it.
    """
    assert items, "instance-wide lookup came back empty - nothing to select from"
    return min(items, key=lambda item: item.id)


async def _sandbox_story(client: TargetProcessClient, suffix: str):
    """Create the throwaway parent every test in this module hangs work off.

    Returned rather than yielded from a fixture: the story's ``delete`` is
    one of the interactions the cassette must contain, and a fixture teardown
    is exactly the place a later refactor could move it out of the test's
    own recording (see ``test_live_readwrite.py``).
    """
    return await client.user_stories.create(
        Name=f"{_NAME_PREFIX} {suffix}",
        Description=_CREATED_DESCRIPTION,
        Project={"Id": _SANDBOX_PROJECT_ID},
    )


@pytest.mark.asyncio
async def test_comment_create_update_delete_round_trip(live_credentials) -> None:
    """The write path on a Comment, which is a General rather than an Assignable.

    A comment has no ``Name`` - its body is ``Description`` - and it is
    attached to an entity through ``General``, so the create payload is
    shaped unlike any assignable's. That is the divergence worth recording:
    the create echo names the entity the comment landed on.
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        story = await _sandbox_story(client, "comment parent story")
        try:
            comment = await client.comments.create(
                Description=f"{_NAME_PREFIX}: {_CREATED_DESCRIPTION}",
                General={"Id": story.id},
            )
            try:
                assert comment.id > 0
                assert comment.resource_type == "Comment"
                assert comment.general is not None
                assert comment.general.id == story.id
                assert comment.owner is not None
                assert comment.create_date is not None
                assert comment.entity_version is not None

                updated = await client.comments.update(
                    comment.id,
                    Description=f"{_NAME_PREFIX}: {_UPDATED_DESCRIPTION}",
                )

                assert updated.id == comment.id
                assert updated.resource_type == "Comment"
                assert updated.entity_version is not None
                assert updated.entity_version > comment.entity_version
                # A comment carries no numeric field an update can prove
                # itself by, so ``DescriptionModifyDate`` stands in: TP sets
                # it when the body is edited, and it is a date rather than
                # free text, so the scrubber leaves it alone.
                assert updated.description_modify_date is not None
            finally:
                await client.comments.delete(comment.id)

            with pytest.raises(NotFoundError):
                await client.comments.get(comment.id)
        finally:
            await client.user_stories.delete(story.id)


@pytest.mark.asyncio
async def test_assignment_create_and_delete(live_credentials) -> None:
    """Assigning a user to a work item in a role, and taking the assignment back.

    Assignment is a join entity with no fields of its own beyond the three
    references it exists to hold, so there is nothing to update - create and
    delete are its whole write surface.

    Who to assign is not free choice, and that is worth recording as much as
    the response shape: TP refuses an Assignment whose user is not a member
    of the card's project, answering ``400`` with *"Please, assign user
    '...' to the '...' Project first"*. So the user and the role both come
    from the sandbox project's own ``ProjectMember`` rows - a read of an
    existing membership, never a write creating one, since project
    membership is instance-level state this suite does not own.
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        story = await _sandbox_story(client, "assignment parent story")
        try:
            member = _lowest_id(
                [
                    m
                    async for m in client.entities.list(
                        "ProjectMember", where=f"Project.Id eq {_SANDBOX_PROJECT_ID}"
                    )
                ]
            )
            # ProjectMember is not one of the typed resources, so its
            # references arrive as raw wire dicts in ``model_extra`` under
            # their PascalCase names rather than as parsed model fields.
            member_user_id = member.User["Id"]
            member_role_id = member.Role["Id"]

            assignment = await client.assignments.create(
                Assignable={"Id": story.id},
                GeneralUser={"Id": member_user_id},
                Role={"Id": member_role_id},
            )
            try:
                assert assignment.id > 0
                assert assignment.resource_type == "Assignment"
                assert assignment.assignable is not None
                assert assignment.assignable.id == story.id
                assert assignment.general_user is not None
                assert assignment.general_user.id == member_user_id
                assert assignment.role is not None
                assert assignment.role.id == member_role_id
            finally:
                await client.assignments.delete(assignment.id)

            with pytest.raises(NotFoundError):
                await client.assignments.get(assignment.id)
        finally:
            await client.user_stories.delete(story.id)


@pytest.mark.asyncio
async def test_team_assignment_create_and_delete(live_credentials) -> None:
    """Assigning a team to a work item, and taking the assignment back.

    The team counterpart of the assignment test above, and shaped like it -
    a join entity with nothing to update, so create and delete are its whole
    write surface - but gated on a different piece of instance state. TP
    refuses a TeamAssignment whose team is not assigned to the card's
    project, answering ``400`` with *"Team needs to be assigned to
    Project"*, and that link is instance configuration rather than a record
    this suite may create (see the module docstring on what re-recording
    this test needs).

    So the team is read from the sandbox project's own ``TeamProject`` row -
    the link itself, used as the lookup - rather than from the ``Team``
    collection at large, which would pick a team the project does not carry
    and reproduce the very refusal. Selected by lowest Id like every other
    lookup here, for the same reason: a name is a placeholder by the time
    the cassette replays.
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        story = await _sandbox_story(client, "team assignment parent story")
        try:
            team_project = _lowest_id(
                [
                    tp
                    async for tp in client.entities.list(
                        "TeamProject", where=f"Project.Id eq {_SANDBOX_PROJECT_ID}"
                    )
                ]
            )
            # TeamProject is not one of the typed resources, so its
            # references arrive as raw wire dicts in ``model_extra`` under
            # their PascalCase names, exactly as ProjectMember's do above.
            team_id = team_project.Team["Id"]

            team_assignment = await client.team_assignments.create(
                Assignable={"Id": story.id},
                Team={"Id": team_id},
            )
            try:
                assert team_assignment.id > 0
                assert team_assignment.resource_type == "TeamAssignment"
                assert team_assignment.assignable is not None
                assert team_assignment.assignable.id == story.id
                assert team_assignment.team is not None
                assert team_assignment.team.id == team_id
            finally:
                await client.team_assignments.delete(team_assignment.id)

            with pytest.raises(NotFoundError):
                await client.team_assignments.get(team_assignment.id)
        finally:
            await client.user_stories.delete(story.id)

        # The parent's own read-back, outside the ``finally`` that deleted
        # it: the assignment above is gone with its own delete recorded, so
        # this is the evidence that the *story* went too and the recording
        # left nothing in the sandbox - the one thing a run against a live
        # instance must never do.
        with pytest.raises(NotFoundError):
            await client.user_stories.get(story.id)


@pytest.mark.asyncio
async def test_role_effort_create_update_delete_round_trip(live_credentials) -> None:
    """Per-role effort on a work item: the one join entity with a field to update.

    RoleEffort holds numbers rather than only references, so unlike the two
    assignment surfaces it has a genuine ``update`` - and the number it holds
    is exactly the kind of value that survives the scrubber, so the update is
    provable rather than merely accepted.
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        story = await _sandbox_story(client, "role effort parent story")
        try:
            role = _lowest_id([r async for r in client.roles.list()])

            role_effort = await client.role_efforts.create(
                Assignable={"Id": story.id},
                Role={"Id": role.id},
                Effort=_CREATED_EFFORT,
            )
            try:
                assert role_effort.id > 0
                assert role_effort.resource_type == "RoleEffort"
                assert role_effort.assignable is not None
                assert role_effort.assignable.id == story.id
                assert role_effort.role is not None
                assert role_effort.role.id == role.id
                assert role_effort.effort == _CREATED_EFFORT

                updated = await client.role_efforts.update(
                    role_effort.id,
                    Effort=_UPDATED_EFFORT,
                )

                assert updated.id == role_effort.id
                assert updated.resource_type == "RoleEffort"
                assert updated.effort == _UPDATED_EFFORT
            finally:
                await client.role_efforts.delete(role_effort.id)

            with pytest.raises(NotFoundError):
                await client.role_efforts.get(role_effort.id)
        finally:
            await client.user_stories.delete(story.id)


@pytest.mark.asyncio
async def test_relation_create_and_delete(live_credentials) -> None:
    """Linking two work items with a typed Relation, and unlinking them.

    Needs two parents rather than one, because a relation joins two entities
    - so this is also the only test here that creates two stories, and the
    only one whose cleanup has more than one thing to delete.

    Both stories are created against the same URI, and vcrpy's default
    matcher ignores the request body, so on replay the two creates are
    distinguished only by the order they were recorded in. Adding or
    reordering a create here binds to the wrong recorded response rather
    than failing, so a change to this test wants the cassette re-recorded
    (the same caveat the bulk test in the sibling module carries).
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        master = await _sandbox_story(client, "relation master story")
        slave = None
        try:
            slave = await _sandbox_story(client, "relation slave story")
            relation_type = _lowest_id([rt async for rt in client.relation_types.list()])

            relation = await client.relations.create(
                Master={"Id": master.id},
                Slave={"Id": slave.id},
                RelationType={"Id": relation_type.id},
            )
            try:
                assert relation.id > 0
                assert relation.resource_type == "Relation"
                assert relation.master is not None
                assert relation.master.id == master.id
                assert relation.slave is not None
                assert relation.slave.id == slave.id
                assert relation.relation_type is not None
                assert relation.relation_type.id == relation_type.id
            finally:
                await client.relations.delete(relation.id)

            with pytest.raises(NotFoundError):
                await client.relations.get(relation.id)
        finally:
            # Both stories are deleted whatever the other's delete did, and
            # a failure is raised rather than swallowed: a cleanup that
            # passed over live residue is the one outcome this module must
            # never produce (as the sibling module's bulk test explains at
            # length).
            stranded = []
            for entity_id in [story.id for story in (master, slave) if story is not None]:
                try:
                    await client.user_stories.delete(entity_id)
                except Exception as exc:
                    stranded.append(f"UserStory {entity_id}: {exc!r}")
            assert not stranded, f"recording left entities in the sandbox: {stranded}"


@pytest.mark.asyncio
async def test_attachment_upload_list_download_and_delete(live_credentials) -> None:
    """The file-transfer surface, which is the one the vendor does not document.

    ``upload`` POSTs ``multipart/form-data`` to ``/UploadFile.ashx``, outside
    the JSON entity API, and TargetProcess documents neither the response
    body nor whether a token-authenticated client may use the endpoint at all
    (the vendor guide says a REST API token cannot *download* an attached
    file). This is the recorded evidence for both - what the upload answers
    with, and that the transfer works under token auth after all.

    The file is a few bytes invented in this module under a filename that is
    the recording reference: a request body is recorded as sent, so a real
    document or a real filename would land in the fixture verbatim.
    """
    domain, token = live_credentials
    async with TargetProcessClient(domain=domain, token=token, mode=ClientMode.READWRITE) as client:
        story = await _sandbox_story(client, "attachment parent story")
        attachment_id = None
        try:
            uploaded = await client.attachments.upload(
                story.id,
                _UPLOAD_FILENAME,
                _UPLOAD_CONTENT,
                mime_type=_UPLOAD_MIME_TYPE,
            )
            # The endpoint answers with the created record, so the upload
            # alone identifies what it made - no re-listing needed to find
            # it. Asserted on the structural fields, since the scrubber
            # replaces the filename before the body reaches disk.
            attachment_id = uploaded.id
            assert uploaded.id > 0
            assert uploaded.resource_type == "Attachment"
            assert uploaded.general is not None
            assert uploaded.general.id == story.id
            # Numbers and booleans are recorded verbatim, so these are the
            # values that tie the response back to the bytes this test sent.
            assert uploaded.size == len(_UPLOAD_CONTENT)
            assert uploaded.persisted_size == len(_UPLOAD_CONTENT)
            assert uploaded.is_empty is False
            assert uploaded.mime_type == _UPLOAD_MIME_TYPE
            assert uploaded.date is not None
            assert uploaded.uri is not None

            # Scoped to the story this test created. An unfiltered listing
            # here would record a real customer's attachment records into a
            # committed fixture.
            attachments = [
                a async for a in client.attachments.list(where=f"General.Id eq {story.id}")
            ]
            assert [a.id for a in attachments] == [attachment_id]
            assert attachments[0].general is not None
            assert attachments[0].general.id == story.id

            # ``Uri``, ``MimeType`` and ``Size`` are not in the Attachment
            # projection TP returns by default - a plain get leaves all three
            # None - so the read side has to ask for them. That is the
            # divergence from ``upload``'s response worth recording, since
            # the two describe the same record.
            fetched = await client.attachments.get(
                attachment_id, include=["Uri", "MimeType", "Size"]
            )
            assert fetched.id == attachment_id
            assert fetched.resource_type == "Attachment"
            assert fetched.uri is not None
            assert fetched.mime_type == _UPLOAD_MIME_TYPE
            assert fetched.size == len(_UPLOAD_CONTENT)

            downloaded = await client.attachments.download(attachment_id)
            assert downloaded == _UPLOAD_CONTENT
        finally:
            # Nested rather than sequential: a failing attachment delete must
            # not take the story's delete down with it, or one stuck record
            # becomes two. ``attachment_id`` is set from the upload's own
            # response, which is parsed - so a ParseError after TP created
            # the record leaves it None, and the story delete below is what
            # removes the attachment with its parent.
            try:
                if attachment_id is not None:
                    await client.attachments.delete(attachment_id)
            finally:
                await client.user_stories.delete(story.id)

        with pytest.raises(NotFoundError):
            await client.user_stories.get(story.id)
