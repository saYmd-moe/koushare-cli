#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$repo_root/skills/koushare-cli"
target_dir="${1:-$HOME/.agents/skills/koushare-cli}"

if [[ -e "$target_dir" || -L "$target_dir" ]]; then
  printf 'Refusing to replace existing skill: %s\n' "$target_dir" >&2
  printf 'Remove it yourself or pass another destination.\n' >&2
  exit 2
fi

mkdir -p "$(dirname "$target_dir")"
ln -s "$source_dir" "$target_dir"
printf 'Installed koushare-cli skill -> %s\n' "$target_dir"
