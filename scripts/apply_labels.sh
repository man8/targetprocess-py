#!/usr/bin/env bash
# Apply the label set defined in .github/labels.yml to the repository.
#
# Requires the GitHub CLI (`gh`), authenticated, and yq. Labels that already
# exist are left untouched unless --force is passed, which updates their colour
# and description in place. Any GitHub API failure aborts loudly rather than
# being reported as "already exists".
#
#   scripts/apply_labels.sh          # create missing labels
#   scripts/apply_labels.sh --force  # also update existing labels in place
set -euo pipefail

usage() {
  echo "usage: ${0##*/} [--force]" >&2
  exit 2
}

force=0
case $# in
  0) ;;
  1) [[ $1 == --force ]] || usage; force=1 ;;
  *) usage ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
labels_file="$repo_root/.github/labels.yml"

for tool in gh yq; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "error: $tool is required" >&2
    exit 1
  fi
done

if [[ ! -f $labels_file ]]; then
  echo "error: $labels_file not found" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh is not authenticated; run 'gh auth login'" >&2
  exit 1
fi

# Resolve the target from this script's own checkout, so running it from inside
# an unrelated clone cannot create these labels on that repository.
repo=$(cd "$repo_root" && gh repo view --json nameWithOwner -q .nameWithOwner)

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# One yq pass for the whole file; a parse failure aborts here under `set -e`
# rather than silently yielding an empty loop.
yq -r '.[] | [.name, .color, (.description // "")] | @tsv' "$labels_file" >"$work/desired"
if [[ ! -s $work/desired ]]; then
  echo "error: no labels defined in $labels_file" >&2
  exit 1
fi

gh label list --repo "$repo" --limit 500 --json name -q '.[].name' >"$work/existing"

created=0
updated=0
unchanged=0

while IFS=$'\t' read -r name color description; do
  if [[ -z $name || -z $color ]]; then
    echo "error: malformed entry in $labels_file: $name" >&2
    exit 1
  fi

  if ! grep -qxF "$name" "$work/existing"; then
    gh label create "$name" --repo "$repo" --color "$color" --description "$description"
    echo "created:   $name"
    created=$((created + 1))
  elif ((force)); then
    gh label edit "$name" --repo "$repo" --color "$color" --description "$description"
    echo "updated:   $name"
    updated=$((updated + 1))
  else
    echo "unchanged: $name (use --force to update)"
    unchanged=$((unchanged + 1))
  fi
done <"$work/desired"

echo "$repo: created $created, updated $updated, unchanged $unchanged."
