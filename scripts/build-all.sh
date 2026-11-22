#!/usr/bin/env bash
# Builds every package environment end to end: assemble -> neoradar-cli convert -> finalize.
#
#   scripts/build-all.sh <source tree> [package ids, comma-separated]
#
# NEORADAR_CLI overrides the CLI command (default: neoradar-cli), e.g.
#   NEORADAR_CLI="node ../neoradar-cli/dist/index.js" scripts/build-all.sh ~/Documents/FrenchVACC
set -euo pipefail

source_tree="${1:?usage: build-all.sh <source tree> [ids]}"
only="${2:-}"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cli="${NEORADAR_CLI:-neoradar-cli}"
python="${PYTHON:-python3}"
"$python" -c "" >/dev/null 2>&1 || python=python

only_args=()
[ -n "$only" ] && only_args=(--only "$only")

"$python" "$repo/scripts/build.py" assemble --source "$source_tree" ${only_args[@]+"${only_args[@]}"}

if [ -n "$only" ]; then
  IFS=',' read -r -a ids <<< "$only"
else
  ids=()
  while IFS= read -r id; do [ -n "$id" ] && ids+=("$id"); done < <("$python" "$repo/scripts/build.py" ids | tr -d '[]" \r' | tr ',' '\n')
fi

for id in "${ids[@]}"; do
  env_dir="$repo/build/$id"
  echo "== convert $id"
  # convert asks for one confirmation; it reports failures through its exit code and the log.
  ( cd "$repo/build" && echo y | $cli convert "$id" )
  [ -f "$env_dir/server-dataset.json" ] || { echo "convert did not write $env_dir/server-dataset.json" >&2; exit 1; }
  if [ -f "neoradar-cli.log" ]; then mv neoradar-cli.log "$env_dir/neoradar-cli.log"; fi
  if [ -f "$repo/build/neoradar-cli.log" ]; then mv "$repo/build/neoradar-cli.log" "$env_dir/neoradar-cli.log"; fi
done

"$python" "$repo/scripts/build.py" finalize ${only_args[@]+"${only_args[@]}"}
