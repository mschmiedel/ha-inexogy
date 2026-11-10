#!/usr/bin/env bash
# Build the release asset named in hacs.json (zip_release): the tracked files of
# custom_components/inexogy at the archive root, as HACS and the Marketplace
# extract it into the integration folder.
# Usage: scripts/build_zip.sh [git ref, default HEAD] [output, default inexogy.zip]
set -euo pipefail

ref="${1:-HEAD}"
out="${2:-inexogy.zip}"

git archive --format=zip -o "$out" "${ref}:custom_components/inexogy"
files="$(unzip -Z1 "$out")"
if ! grep -qx 'manifest.json' <<<"$files"; then
  echo "manifest.json is not at the root of $out" >&2
  exit 1
fi
echo "Built $out from ${ref}: $(grep -cv '/$' <<<"$files") files"
