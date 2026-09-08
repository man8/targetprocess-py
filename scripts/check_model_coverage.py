#!/usr/bin/env python3
"""Report how much of each TP entity type's API field surface the models declare.

A model that declares a fraction of its type's fields still parses a live
payload - the undeclared keys land in ``model_extra`` - but nothing about them
is typed, documented, or discoverable, and a caller has to know the wire name to
reach one. This measures that gap against the authority: TP's own
``/api/v1/{collection}/meta``, which names every value and reference property
the instance exposes for the type.

Dev-time only, and deliberately not wired into CI: it needs a live instance and
a real token, and CI has neither. Run it when the models change, or to
regenerate the coverage table.

Credentials come from ``TP_API_TOKEN``/``TP_BASE_URL`` in the environment, else
from ``~/.config/targetprocess/.env``. Only GET requests are issued.

    scripts/check_model_coverage.py                 # per-model report
    scripts/check_model_coverage.py --markdown      # the coverage table
    scripts/check_model_coverage.py --missing       # name every undeclared field
    scripts/check_model_coverage.py --fail-under 90 # opt-in gate
    scripts/check_model_coverage.py --validate      # parse real records

``--validate`` is the check ``/meta`` alone cannot make. ``/meta`` says which
properties exist, not what TP puts in them, and the two differ: a ``Bug``'s
``EntityType`` arrives without an ``Id`` where a ``UserStory``'s carries one.
Declaring a field can therefore turn a payload the models used to tolerate into
a hard parse failure, which no offline fixture will show. This fetches real
records and parses them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targetprocess import models, resources  # noqa: E402
from targetprocess.resources.base import BaseResource  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from pydantic import BaseModel

ENV_FILE = Path.home() / ".config" / "targetprocess" / ".env"

# Model class -> the collection segment its /meta lives under. Ordered as the
# report reads best: work items first, then the planning and lookup types, then
# the join and supporting types.
COLLECTIONS: dict[str, str] = {
    "UserStory": "UserStories",
    "Bug": "Bugs",
    "Task": "Tasks",
    "Feature": "Features",
    "Epic": "Epics",
    "Request": "Requests",
    "TestCase": "TestCases",
    "Project": "Projects",
    "Team": "Teams",
    "Release": "Releases",
    "Iteration": "Iterations",
    "TeamIteration": "TeamIterations",
    "User": "Users",
    "EntityState": "EntityStates",
    "Priority": "Priorities",
    "Role": "Roles",
    "RelationType": "RelationTypes",
    "Severity": "Severities",
    "Process": "Processes",
    "Workflow": "Workflows",
    "EntityType": "EntityTypes",
    "Term": "Terms",
    "CustomActivity": "CustomActivities",
    "CustomRule": "CustomRules",
    "Relation": "Relations",
    "Assignment": "Assignments",
    "TeamAssignment": "TeamAssignments",
    "RoleEffort": "RoleEfforts",
    "Time": "Times",
    "Comment": "Comments",
    "Attachment": "Attachments",
    "CustomField": "CustomFields",
}

# Fields left undeclared on purpose, with the reason. Counted out of the
# denominator so a deliberate omission does not read as a coverage gap - and
# named here so it stays a decision on the record rather than an oversight.
EXCLUDED: dict[tuple[str, str], str] = {
    (
        "User",
        "Password",
    ): "write-only credential (TP reports CanGet=false); declaring it would put a "
    "password-shaped attribute into model_dump output",
}

# Fields the models declare that this instance's /meta does not list, each kept
# on purpose. Without this map they read as anomalies on every run; with it, a
# genuinely new mismatch is the only thing the report surfaces.
KNOWN_DEVIATIONS: dict[tuple[str, str], str] = {
    ("Task", "Parent"): "undocumented but queryable; returns the owning Assignable",
    ("Feature", "BusinessValue"): "absent on this instance (include= returns 400); "
    "retained because removing a published field would break callers",
    ("Epic", "BusinessValue"): "absent on this instance (include= returns 400); "
    "retained because removing a published field would break callers",
    ("Iteration", "Team"): "absent upstream (include= returns 400); the team-scoped "
    "sprint is TeamIteration",
    ("TestCase", "EntityState"): "absent upstream (include= returns 400); TestCase is a "
    "General, not an Assignable",
    ("TestCase", "AssignedUser"): "absent upstream (include= returns 400); TestCase has "
    "no AssignedUser collection",
}

# Fields declared on the Entity base that, on the named type, /meta lists as a
# collection of a different kind from what the base field holds - so include=
# returns a shape the model cannot parse. Kept out of --validate's hydration
# (the coverage count is unaffected: collections are outside it), with the
# same staleness check as the maps above. Read from the typed resources' own
# ``unhydratable_includes`` declarations, so the library's refusal and this
# script's hydration list cannot drift apart.
UNHYDRATABLE: dict[tuple[str, str], str] = {
    (resource.entity_type, field): reason
    for name in resources.__all__
    if isinstance(resource := getattr(resources, name), type)
    and issubclass(resource, BaseResource)
    and resource is not BaseResource
    for field, reason in resource.unhydratable_includes.items()
}

# Declared on the Entity base and so present on every model, but not part of
# every type's /meta: ResourceType is a wire envelope key TP never lists, and
# the lookup and join types carry no CreateDate, ModifyDate or CustomFields
# collection. Absent from a type's /meta they simply stay None, which is not a
# mismatch worth reporting.
BASE_FIELDS = frozenset({"ResourceType", "CreateDate", "ModifyDate", "CustomFields"})


class Coverage(NamedTuple):
    """One model's measured field coverage against its ``/meta``.

    ``missing`` and ``unexplained`` are the two directions the model can be
    wrong in: a field TP declares that the model does not, and a field the model
    declares that TP does not. ``stale`` names an EXCLUDED, KNOWN_DEVIATIONS or
    UNHYDRATABLE entry that no longer applies. All three should be empty.
    """

    model: str
    collection: str
    declared: int
    total: int
    missing: tuple[str, ...]
    undeclared_excluded: tuple[str, ...]
    deviations: tuple[str, ...]
    unexplained: tuple[str, ...]
    stale: tuple[str, ...]
    hydratable: frozenset[str]

    @property
    def percent(self) -> int:
        """Declared share of the type's countable field surface, as a percentage.

        Raises:
            ValueError: The type reported no countable fields at all, so there
                is nothing to take a share of. A zero denominator means the
                measurement failed - a renamed ``/meta`` group, an unexpected
                200 body - and returning 100 there would report a broken
                instrument as full coverage.
        """
        if not self.total:
            raise ValueError(
                f"{self.model}: /meta reported no value or reference properties. "
                "The measurement failed rather than finding full coverage."
            )
        return round(100 * self.declared / self.total)


def _load_credentials() -> tuple[str, str]:
    """Return ``(base_url, token)`` from the environment or the shared dotenv."""
    token = os.environ.get("TP_API_TOKEN", "")
    base_url = os.environ.get("TP_BASE_URL", "")

    if (not token or not base_url) and ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("\"'")
            if key == "TP_API_TOKEN" and not token:
                token = value
            elif key == "TP_BASE_URL" and not base_url:
                base_url = value

    if not token:
        raise SystemExit(
            f"No TP_API_TOKEN in the environment or {ENV_FILE}. This script reads a live "
            "instance; it cannot run without one."
        )

    if not base_url:
        raise SystemExit(
            f"No TP_BASE_URL in the environment or {ENV_FILE}. Set it to the instance's "
            "https:// URL; this script has no default instance."
        )

    # TP carries the token as a query parameter, so it travels in the URL of
    # every request. Refuse any scheme that would send it in clear (or read a
    # local file), rather than trusting whatever the environment supplied.
    if not base_url.startswith("https://"):
        raise SystemExit(
            f"TP_BASE_URL must be an https:// URL; got {base_url!r}. The access token "
            "travels as a query parameter and must not be sent in clear."
        )
    return base_url, token


def _get(base_url: str, token: str, path: str, **params: str) -> dict[str, Any]:
    """GET a JSON endpoint under ``/api/v1`` and return the decoded body."""
    query = urllib.parse.urlencode({"format": "json", **params, "access_token": token})
    url = f"{base_url.rstrip('/')}/api/v1/{path}?{query}"
    # urlopen with a str and no data is unconditionally a GET; the https scheme
    # is asserted in _load_credentials.
    with urllib.request.urlopen(url, timeout=30) as response:
        payload: dict[str, Any] = json.load(response)
    return payload


def _fetch_meta(base_url: str, token: str, collection: str) -> dict[str, Any]:
    """GET ``/api/v1/{collection}/meta`` and return the decoded body."""
    return _get(base_url, token, f"{collection}/meta")


def _fetch_sample(
    base_url: str, token: str, collection: str, fields: frozenset[str], take: int
) -> list[dict[str, Any]]:
    """GET a page of real records, hydrating every declared field."""
    include = f"[{','.join(sorted(fields))}]"
    body = _get(base_url, token, collection, take=str(take), include=include)
    items: list[dict[str, Any]] = body.get("Items", [])
    return items


def _property_names(meta: dict[str, Any], *groups: str) -> set[str]:
    """Return the property names in the named ``/meta`` groups."""
    properties = meta.get("ResourceMetadataPropertiesDescription", {})
    return {
        name
        for group in groups
        for item in properties.get(group, {}).get("Items", [])
        if (name := item.get("Name"))
    }


def _api_field_names(meta: dict[str, Any]) -> set[str]:
    """Return every value and reference property name the type declares.

    Collection properties (``Comments``, ``Assignments``, ``Times``, ...) are
    excluded from the count: they are hydrated only via ``include=`` and arrive
    as an ``Items`` envelope rather than as a field of the entity. This is the
    denominator the work item's coverage table is measured against.
    """
    return _property_names(
        meta,
        "ResourceMetadataPropertiesResourceValuesDescription",
        "ResourceMetadataPropertiesResourceReferencesDescription",
    )


def _api_collection_names(meta: dict[str, Any]) -> set[str]:
    """Return the type's collection property names."""
    return _property_names(meta, "ResourceMetadataPropertiesResourceCollectionsDescription")


def _declared_aliases(model: type[BaseModel]) -> set[str]:
    """Return the wire names the model declares, inherited fields included."""
    return {field.alias or name for name, field in model.model_fields.items()}


def _measure(model_name: str, collection: str, meta: dict[str, Any]) -> Coverage:
    """Compare one model's declared aliases against its type's ``/meta``."""
    api = _api_field_names(meta)
    collections = _api_collection_names(meta)
    declared = _declared_aliases(getattr(models, model_name))

    excluded = {field for (owner, field) in EXCLUDED if owner == model_name}
    unhydratable = {field for (owner, field) in UNHYDRATABLE if owner == model_name}
    countable = api - excluded

    # Declared aliases the API's value/reference groups never mention. A
    # collection property or an Entity-base field is a legitimate declaration;
    # a documented deviation is a decision already taken; anything left is a
    # rename upstream, a typo, or a field that never existed.
    surplus = declared - api - collections - BASE_FIELDS
    known = {field for (owner, field) in KNOWN_DEVIATIONS if owner == model_name}

    # An entry in either map that no longer applies - the field was declared
    # after all, or TP started reporting it - silently stops doing anything.
    # Both maps exist to keep a decision visible, so a dead entry is reported
    # rather than left to rot.
    stale = tuple(
        sorted(
            [f"EXCLUDED {field} (now declared)" for field in excluded & declared]
            + [f"EXCLUDED {field} (absent from /meta)" for field in excluded - api]
            + [f"KNOWN_DEVIATIONS {field} (now in /meta)" for field in known & api]
            + [f"KNOWN_DEVIATIONS {field} (no longer declared)" for field in known - declared]
            + [
                f"UNHYDRATABLE {field} (absent from /meta)"
                for field in unhydratable - api - collections
            ]
            + [f"UNHYDRATABLE {field} (not declared)" for field in unhydratable - declared]
        )
    )

    return Coverage(
        model=model_name,
        collection=collection,
        declared=len(countable & declared),
        total=len(countable),
        missing=tuple(sorted(countable - declared)),
        undeclared_excluded=tuple(sorted((excluded & api) - declared)),
        deviations=tuple(sorted(surplus & known)),
        unexplained=tuple(sorted(surplus - known)),
        stale=stale,
        # What include= will accept and the model will parse: a declared
        # alias TP actually has, less any whose hydrated shape the model
        # cannot hold. Asking for one TP lacks fails the request with 400.
        hydratable=frozenset((declared & (api | collections)) - unhydratable),
    )


def _print_decisions(row: Coverage, pad: str) -> None:
    """Print the documented deviations, exclusions and unhydratable fields for one model."""
    for field in row.deviations:
        print(f"{pad}    deviation: {field} - {KNOWN_DEVIATIONS[(row.model, field)]}")
    for field in row.undeclared_excluded:
        print(f"{pad}    excluded: {field} - {EXCLUDED[(row.model, field)]}")
    for (owner, field), reason in UNHYDRATABLE.items():
        if owner == row.model:
            print(f"{pad}    unhydratable: {field} - {reason}")


def _print_report(rows: list[Coverage], *, show_missing: bool, verbose: bool) -> None:
    """Print the per-model coverage report to stdout."""
    width = max(len(row.model) for row in rows)
    pad = " " * width
    for row in sorted(rows, key=lambda r: (r.percent, r.model)):
        print(f"{row.model:<{width}}  {row.declared:>3}/{row.total:<3}  {row.percent:>3}%")
        if show_missing and row.missing:
            print(f"{pad}    missing: {', '.join(row.missing)}")
        for field in row.unexplained:
            print(f"{pad}    UNEXPLAINED: {field} is declared but absent from /meta")
        for entry in row.stale:
            print(f"{pad}    STALE: {entry}")
        if verbose:
            _print_decisions(row, pad)

    declared = sum(row.declared for row in rows)
    total = sum(row.total for row in rows)
    unexplained = sum(len(row.unexplained) for row in rows)
    print(
        f"\n{len(rows)} models: {declared}/{total} fields declared "
        f"({round(100 * declared / total)}%)"
    )
    if unexplained:
        print(f"{unexplained} declared field(s) absent from /meta and undocumented")


def _print_markdown(rows: list[Coverage]) -> None:
    """Print the coverage table in the form the work item carries it."""
    print("| Model | Declared | API fields | Coverage |")
    print("| -- | -- | -- | -- |")
    for row in sorted(rows, key=lambda r: (r.percent, r.model)):
        print(f"| {row.model} | {row.declared} | {row.total} | {row.percent}% |")


def _validate_live(
    base_url: str, token: str, rows: list[Coverage], take: int
) -> tuple[int, int, set[str], list[str]]:
    """Parse real records through each model.

    Returns ``(parsed, attempted, extras seen, models not checked)``.

    Failures are printed as they are found. A field that never appears in the
    sample proves nothing, so this complements the coverage count rather than
    replacing it.
    """
    ok = total = 0
    extras: set[str] = set()
    unchecked: list[str] = []
    for row in rows:
        model = getattr(models, row.model)
        # Ask for every alias the model declares, minus the ones this instance
        # rejects, so the sample exercises the real hydrated shape.
        try:
            items = _fetch_sample(base_url, token, row.collection, row.hydratable, take)
        except urllib.error.HTTPError as exc:  # pragma: no cover - instance-dependent
            # Not a skip: a collection whose sample cannot be fetched is a
            # model this run did not check, and saying so is the point.
            print(f"{row.model:<16} {'FETCH ' + str(exc.code):>7} - NOT CHECKED")
            unchecked.append(row.model)
            continue

        failures = 0
        for item in items:
            total += 1
            try:
                parsed = model.model_validate(item)
            except Exception as exc:  # noqa: BLE001 - report whatever validation raised
                failures += 1
                detail = " ".join(str(exc).split())[:160]
                print(f"  PARSE FAILURE {row.model} Id={item.get('Id')}: {detail}")
                continue
            ok += 1
            if parsed.model_extra:
                extras.update(f"{row.model}.{key}" for key in parsed.model_extra)
        verdict = f"{len(items) - failures}/{len(items)}"
        print(f"{row.model:<16} {verdict:>7} parsed" + (" - FAILURES" if failures else ""))
        if not items:
            print(f"{row.model:<16} {'EMPTY':>7} - NOT CHECKED (no records)")
            unchecked.append(row.model)
    return ok, total, extras, unchecked


def main(argv: list[str] | None = None) -> int:
    """Measure every model's coverage and report it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown", action="store_true", help="print the coverage table")
    parser.add_argument("--missing", action="store_true", help="name every undeclared field")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="also print the documented deviations and exclusions",
    )
    parser.add_argument(
        "--fail-under",
        type=int,
        default=None,
        metavar="PCT",
        help="exit non-zero if any model falls below this coverage",
    )
    parser.add_argument("--model", action="append", help="measure only this model (repeatable)")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="also parse a sample of real records through each model",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=50,
        metavar="N",
        help="records per collection for --validate (default 50)",
    )
    args = parser.parse_args(argv)

    base_url, token = _load_credentials()
    wanted = set(args.model) if args.model else set(COLLECTIONS)
    unknown_models = wanted - set(COLLECTIONS)
    if unknown_models:
        raise SystemExit(f"Not a measured model: {', '.join(sorted(unknown_models))}")

    rows = [
        _measure(model, collection, _fetch_meta(base_url, token, collection))
        for model, collection in COLLECTIONS.items()
        if model in wanted
    ]

    if args.markdown:
        _print_markdown(rows)
    else:
        _print_report(rows, show_missing=args.missing, verbose=args.verbose)

    if args.validate:
        print("\nParsing real records:")
        ok, total, extras, unchecked = _validate_live(base_url, token, rows, args.sample)
        print(f"\n{ok}/{total} live records parsed across {len(rows) - len(unchecked)} models")
        if args.verbose and extras:
            print("undeclared keys encountered:", ", ".join(sorted(extras)))
        if unchecked:
            # Silence from a model that was never exercised is not evidence
            # it parses, so it fails the run rather than passing quietly.
            print(
                f"\n{len(unchecked)} model(s) not checked: {', '.join(unchecked)}",
                file=sys.stderr,
            )
            return 1
        if ok != total:
            print(f"\n{total - ok} live record(s) failed to parse", file=sys.stderr)
            return 1

    return _gate(rows, args.fail_under)


def _gate(rows: list[Coverage], fail_under: int | None) -> int:
    """Return the exit code: 0 only when every check the run can make passed.

    Three ways to fail, not one. A coverage shortfall is the obvious one; a
    declared field absent from ``/meta`` and a dead EXCLUDED /
    KNOWN_DEVIATIONS entry are the two that would otherwise pass quietly.
    """
    # A field declared but absent from /meta is a mismatch in the other
    # direction, and the Coverage docstring says both should be empty - so it
    # fails the run too, not only the coverage shortfall.
    stale = [row for row in rows if row.stale]
    if stale:
        print(
            "\n" + "\n".join(f"stale entry - {row.model}: {e}" for row in stale for e in row.stale),
            file=sys.stderr,
        )
        return 1

    unexplained = [row for row in rows if row.unexplained]
    if unexplained:
        print(
            f"\n{sum(len(row.unexplained) for row in unexplained)} declared field(s) absent "
            f"from /meta and undocumented: "
            + ", ".join(f"{row.model}.{f}" for row in unexplained for f in row.unexplained),
            file=sys.stderr,
        )
        return 1

    if fail_under is not None:
        below = [row for row in rows if row.percent < fail_under]
        if below:
            print(
                f"\n{len(below)} model(s) below {fail_under}%: "
                f"{', '.join(row.model for row in below)}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
