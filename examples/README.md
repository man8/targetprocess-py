# Examples

Runnable scripts demonstrating `targetprocess-py`. See the
[usage guide](../docs/USAGE.md) for the concepts behind them.

## Configuration

All scripts read credentials from the environment:

| Variable | Meaning |
| --- | --- |
| `TP_DOMAIN` | Instance domain, e.g. `example.tpondemand.com` |
| `TP_TOKEN` | API token (sent as the `access_token` query parameter) |

```bash
export TP_DOMAIN=example.tpondemand.com
export TP_TOKEN=your-api-token
```

Run a script either directly or via `uv`:

```bash
python examples/list_user_stories.py --limit 10
# or
uv run python examples/list_user_stories.py --limit 10
```

## Read examples (safe on any instance)

These build a `READONLY` client — writes are impossible by construction.

| Script | What it shows |
| --- | --- |
| `list_user_stories.py` | `where=` filtering, `include=` field selection, iterating `list()` |
| `readonly_reporting.py` | Pagination across many pages + client-side aggregation, zero writes |

```bash
python examples/list_user_stories.py --where "(EntityState.Name eq 'Open')" --limit 10
python examples/readonly_reporting.py --limit 500
```

## Write examples (allow-listed project only)

These build a `READWRITE` client and **create/update** data, so each guards the
destination two independent ways: the target project must be named on the
command line (`--project-id`, required, no default) **and** allow-listed in the
`TP_WRITE_ALLOWED_PROJECT_IDS` environment variable (comma-separated), and the
write must be confirmed with `--yes`. The double entry defends the realistic
accident — copy the documented command, edit the id. Point it at a
throwaway/sandbox project, **never production**; for man8's TargetProcess, the
API-testing sandbox project id is **`49938`**.

| Script | What it shows |
| --- | --- |
| `create_bug.py` | `create()` on a READWRITE client |
| `bulk_updates.py` | The list-then-`update()` pattern (idempotent) with automatic rate limiting |

```bash
export TP_WRITE_ALLOWED_PROJECT_IDS=49938
python examples/create_bug.py  --project-id 49938 --name "Example bug" --yes
python examples/bulk_updates.py --project-id 49938 --limit 10 --yes
```
