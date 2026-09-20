"""The base of the work-item managers, and the two entity-state levels a work item carries."""

from targetprocess_py.exceptions import (
    AmbiguousMatchError,
    NotFoundError,
    ParseError,
    SplitTransitionError,
)
from targetprocess_py.models import AssignableEntity, EntityRef, EntityState, TeamAssignment
from targetprocess_py.resources.base import ASSIGNABLE_IGNORED_FILTER_PATHS, BaseResource
from targetprocess_py.resources.entity_states import _STATE_INCLUDE
from targetprocess_py.types import LevelState, StateLevels

# One level's target state: its Id, its name, or the EntityState record itself.
StateTarget = int | str | EntityState


def _state_ref(ref: EntityRef | None, *, owner: str) -> EntityRef:
    """Return the ``EntityState`` reference a record was read with, refusing its absence."""
    if ref is None:
        raise ParseError(f"{owner} was read without its EntityState")
    return ref


def _level(state: EntityState) -> LevelState:
    """Describe one level from a state record read with its ``Workflow``."""
    if state.workflow is None:
        raise ParseError(f"EntityState {state.id} was read without its Workflow")
    return LevelState(state_id=state.id, state_name=state.name, workflow_id=state.workflow.id)


def _observed(ref: EntityRef | None, *, owner: str, workflow_id: int) -> LevelState:
    """Describe one level from the state a verifying re-read observed."""
    state = _state_ref(ref, owner=owner)
    return LevelState(state_id=state.id, state_name=state.name, workflow_id=workflow_id)


class AssignableResource[T: AssignableEntity](BaseResource[T]):
    """Base class of the managers whose entities are work items (TP's ``Assignable``).

    A work item carries two entity states that move independently: the
    project-workflow state on the item itself (``EntityState``), and the
    team-workflow state on its team assignment (``TeamAssignment.EntityState``)
    - the lane a team board shows. Whether the two are distinct is a property
    of the process and the team, and each state's ``Workflow`` reference says
    which: where the team has no workflow of its own, the team assignment
    carries the item's own state object, both levels share one workflow, and
    one write moves both. Where they are distinct, a write to the item's state
    alone leaves the item split behind a success status. ``entity_state_levels``
    reads the pair, and ``advance_state`` moves it as one transition.

    A ``where=`` on the ``Assignments`` collection is refused before any
    request on every work-item manager, since TargetProcess ignores it.

    Example:
        client = TargetProcessClient(...)
        levels = await client.user_stories.entity_state_levels(123)
        if levels.team is None or levels.collapsed:
            await client.user_stories.advance_state(123, to="Done")
        else:
            await client.user_stories.advance_state(123, to="Done", team_to="Released")
    """

    ignored_filter_paths = ASSIGNABLE_IGNORED_FILTER_PATHS

    async def entity_state_levels(self, id: int) -> StateLevels:
        """Read a work item's project and team entity-state levels.

        Reads the item's state, that state's record for its workflow, and the
        item's team assignments by ``Assignable.Id``. With one team assignment
        its state's record is read too, unless it is the item's own state
        object. The levels are collapsed when both states belong to one
        workflow.

        Args:
            id: The work item's Id

        Returns:
            Both levels; ``team`` is ``None`` when the item has no team
            assignment.

        Raises:
            AmbiguousMatchError: The item carries more than one team
                assignment, so it has no single team level.
            ParseError: A record came back without its ``EntityState`` or
                ``Workflow``, or failed model validation.
            NotFoundError: Item not found
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            APIError: Other API errors
        """
        item = await self.get(id, include=["EntityState"])
        states = self._client.entity_states
        item_ref = _state_ref(item.entity_state, owner=f"{self.entity_type} {id}")
        item_state = await states.get(item_ref.id, include=_STATE_INCLUDE)
        project = _level(item_state)
        assignment = await self._team_assignment(id)
        if assignment is None:
            return StateLevels(project=project, team=None, team_assignment_id=None, collapsed=False)
        team_ref = _state_ref(assignment.entity_state, owner=f"TeamAssignment {assignment.id}")
        if team_ref.id == item_state.id:
            team = project
        else:
            team = _level(await states.get(team_ref.id, include=_STATE_INCLUDE))
        return StateLevels(
            project=project,
            team=team,
            team_assignment_id=assignment.id,
            collapsed=team.workflow_id == project.workflow_id,
        )

    async def _team_assignment(self, id: int) -> TeamAssignment | None:
        """Return the work item's one team assignment, ``None`` without one, refusing several.

        Raises:
            AmbiguousMatchError: The item carries more than one team assignment.
        """
        assignments = [
            assignment
            async for assignment in self._client.team_assignments.list(
                where=f"Assignable.Id eq {int(id)}", include=["EntityState", "Team"]
            )
        ]
        if len(assignments) > 1:
            raise AmbiguousMatchError(
                f"{self.entity_type} {id} carries {len(assignments)} team assignments, so it has "
                "no single team level; move each through team_assignments.update",
                assignable_id=id,
                count=len(assignments),
            )
        return assignments[0] if assignments else None

    async def advance_state(
        self,
        id: int,
        *,
        to: StateTarget,
        team_to: StateTarget | None = None,
        verify: bool = True,
    ) -> StateLevels:
        """Move a work item's entity state, both levels as one transition.

        Reads the levels, then resolves each level's target within that
        level's own workflow: a state Id must be a member of it, a name
        resolves through ``entity_states.resolve``, and an ``EntityState``
        must carry that workflow. Then it writes the item's state and, where
        the team level is distinct, the team assignment's, in that order.
        Where the levels are collapsed one write moves both, so ``team_to``
        may be left out and, if given, must resolve to the same state as
        ``to``.

        A single-level advance is refused rather than sent: with a distinct
        team level and no ``team_to``, the error names both workflows before
        any write.

        ``verify=True`` re-reads each level as it is written, in order: the
        item after its write, then the team assignment after its own write
        or, collapsed, after the item's write moved it. A level not showing
        its target raises ``VerificationError``, so a transition TP answered
        with a success status and did not apply is not silent, and an item
        write that did not apply raises before the team level is written,
        leaving both levels where they were. Nothing locks the two writes
        together, so a failure after the item's write - the team write, or a
        re-read - leaves the item moved and its team level not. The levels
        returned are those re-reads. With ``verify=False`` both writes are
        sent and the levels are read again afterwards.

        Args:
            id: The work item's Id
            to: The project-level target: a state Id, a state name, or an
                ``EntityState`` read with its ``Workflow``
            team_to: The team-level target, in the same forms; required when
                the team level is in a workflow of its own
            verify: Re-read each level after its own write and raise when it
                does not show its target (default True)

        Returns:
            The levels as read back once written.

        Raises:
            SplitTransitionError: The team level is distinct and ``team_to``
                is absent, or the levels are collapsed and ``team_to``
                resolves to another state than ``to`` (before any write).
            ValueError: ``team_to`` was given for an item with no team
                assignment, or an ``EntityState`` target carries another
                workflow (before any write).
            TypeError: A target is not a state Id, a name or an
                ``EntityState`` (before any write).
            NotFoundError: A target is not a state of its level's workflow,
                or the item was not found.
            AmbiguousMatchError: A target name matched several states, or the
                item carries more than one team assignment.
            VerificationError: ``verify`` is True and a level did not show its
                target after its write; for the item, before the team level is
                written.
            ReadOnlyViolation: Client is in readonly mode (after the reads,
                before any write).
            ParseError: A record came back without its ``EntityState`` or
                ``Workflow``, or failed model validation.
            RequestValidationError: TP refused a state write
            AuthenticationError: Invalid credentials
            ForbiddenError: Insufficient permissions
            NetworkError: Transport-level failure
            APIError: Other API errors
        """
        levels = await self.entity_state_levels(id)
        self._check_team_to(id, levels, team_to)
        target = await self._resolve_level(to, levels.project.workflow_id, level="project")
        team_target = await self._team_target(id, levels, team_to, target)
        item = await self.update(id, EntityState={"Id": target.id}, verify=verify)
        assignment = await self._move_team_level(levels, team_target, verify=verify)
        if not verify:
            return await self.entity_state_levels(id)
        project = _observed(
            item.entity_state,
            owner=f"{self.entity_type} {id}",
            workflow_id=levels.project.workflow_id,
        )
        team = None
        if assignment is not None and levels.team is not None:
            team = _observed(
                assignment.entity_state,
                owner=f"TeamAssignment {assignment.id}",
                workflow_id=levels.team.workflow_id,
            )
        return StateLevels(
            project=project,
            team=team,
            team_assignment_id=levels.team_assignment_id,
            collapsed=levels.collapsed,
        )

    def _check_team_to(self, id: int, levels: StateLevels, team_to: StateTarget | None) -> None:
        """Refuse a ``team_to`` the item has no level for, or its absence where it is needed.

        Raises:
            ValueError: ``team_to`` was given and the item has no team level.
            SplitTransitionError: The team level is distinct and ``team_to``
                is absent.
        """
        if levels.team is None:
            if team_to is not None:
                raise ValueError(
                    f"{self.entity_type} {id} has no team assignment, so there is no team "
                    "level for team_to=; pass to= alone"
                )
            return
        if team_to is None and not levels.collapsed:
            raise SplitTransitionError(
                f"{self.entity_type} {id} has a team level in workflow "
                f"{levels.team.workflow_id}, distinct from its project workflow "
                f"{levels.project.workflow_id}; moving the project level alone would split "
                "them - pass team_to= to move both",
                entity_id=id,
                project_workflow_id=levels.project.workflow_id,
                team_workflow_id=levels.team.workflow_id,
            )

    async def _team_target(
        self, id: int, levels: StateLevels, team_to: StateTarget | None, target: EntityState
    ) -> EntityState | None:
        """Resolve the team level's target: ``None`` with no team level, ``target`` when shared.

        Raises:
            SplitTransitionError: The levels are collapsed and ``team_to``
                resolves to another state than ``target``.
        """
        if levels.team is None:
            return None
        if team_to is None:
            return target
        team_target = await self._resolve_level(team_to, levels.team.workflow_id, level="team")
        if levels.collapsed and team_target.id != target.id:
            raise SplitTransitionError(
                f"{self.entity_type} {id} has both levels in workflow "
                f"{levels.team.workflow_id}, which cannot hold two targets: to= is state "
                f"{target.id} and team_to= is state {team_target.id}",
                entity_id=id,
                project_workflow_id=levels.project.workflow_id,
                team_workflow_id=levels.team.workflow_id,
            )
        return team_target

    async def _resolve_level(
        self, target: StateTarget, workflow_id: int, *, level: str
    ) -> EntityState:
        """Resolve one level's target to a state of that level's workflow.

        Raises:
            ValueError: An ``EntityState`` target carries another workflow, or
                none.
            TypeError: The target is not a state Id, a name or an
                ``EntityState``.
            NotFoundError: No state of that Id or name is in the workflow.
            AmbiguousMatchError: A name matched several states.
        """
        states = self._client.entity_states
        if isinstance(target, EntityState):
            carried = target.workflow.id if target.workflow is not None else None
            if carried != workflow_id:
                raise ValueError(
                    f"the {level} target, EntityState {target.id}, carries workflow {carried}, "
                    f"not the {level} workflow {workflow_id}"
                )
            return target
        if isinstance(target, str):
            return await states.resolve(target, workflow_id=workflow_id)
        if isinstance(target, bool) or not isinstance(target, int):
            raise TypeError(
                f"the {level} target must be a state Id, a state name or an EntityState, "
                f"not {target!r}"
            )
        for state in await states.for_workflow(workflow_id):
            if state.id == target:
                return state
        raise NotFoundError(f"no state with Id {target} in the {level} workflow {workflow_id}")

    async def _move_team_level(
        self, levels: StateLevels, team_target: EntityState | None, *, verify: bool
    ) -> TeamAssignment | None:
        """Move the team level after the item's, returning the team assignment's re-read.

        A distinct team level is written. A collapsed one moved with the
        item's write, so nothing is sent: with ``verify`` the team assignment
        is re-read as the evidence that it followed.

        Returns:
            The team assignment as re-read or echoed; ``None`` when there is no
            team level, or a collapsed one was not verified.

        Raises:
            VerificationError: ``verify`` is True and the team assignment does
                not show ``team_target``.
        """
        assignment_id = levels.team_assignment_id
        if team_target is None or assignment_id is None:
            return None
        assignments = self._client.team_assignments
        if not levels.collapsed:
            return await assignments.update(
                assignment_id, EntityState={"Id": team_target.id}, verify=verify
            )
        if not verify:
            return None
        # Deliberately the shared verifying re-read of ``BaseResource.update``,
        # called with no write before it: the item's write is the one that
        # moved this level.
        return await assignments._verify_update(
            assignment_id, {"EntityState": {"Id": team_target.id}}
        )
