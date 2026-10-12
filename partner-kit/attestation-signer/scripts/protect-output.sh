#!/usr/bin/env bash
# Ignore generated private files, not the operator's whole working directory.
set -euo pipefail
out=$(cd -- "${1:?output directory required}" && pwd -P)
ignore="$out/.gitignore"
[ ! -L "$ignore" ] && { [ ! -e "$ignore" ] || [ -f "$ignore" ]; } \
  || { echo 'Expected a regular .gitignore file.' >&2; exit 1; }
patterns=(attestation-signer.env transport.key .env aws.env operator.env aws/ .kms/ data/ '*.before-rotation-*')
# Existing tracked templates/scripts are fine. Only refuse already tracked
# secret outputs; ignoring them cannot remove their contents from Git history.
if command -v git >/dev/null && git -C "$out" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  for pattern in "${patterns[@]}"; do
    [ -z "$(git -C "$out" ls-files -- "$pattern")" ] \
      || { echo "Private output is already tracked by Git: $pattern. Remove that file from tracking before writing credentials." >&2; exit 1; }
  done
fi
umask 077
for pattern in "${patterns[@]}"; do
  found=false
  if [ -f "$ignore" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      if [ "$line" = "$pattern" ]; then found=true; break; fi
    done < "$ignore"
  fi
  if [ "$found" = false ]; then printf '\n%s\n' "$pattern" >> "$ignore"; fi
done
