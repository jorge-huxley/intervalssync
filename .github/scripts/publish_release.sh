#!/usr/bin/env bash

set -euo pipefail

tag=${1:?usage: publish_release.sh TAG ASSET_DIRECTORY}
asset_directory=${2:?usage: publish_release.sh TAG ASSET_DIRECTORY}

if [[ ! -d "$asset_directory" ]]; then
  echo "Asset directory does not exist: $asset_directory" >&2
  exit 1
fi

mapfile -d '' assets < <(find "$asset_directory" -type f -print0 | sort -z)
if (( ${#assets[@]} == 0 )); then
  echo "No release assets found under $asset_directory" >&2
  exit 1
fi

# Creating a draft first prevents users from seeing a release with missing
# downloads. On a retry, reuse the existing draft and its completed assets.
if ! gh release view "$tag" >/dev/null 2>&1; then
  gh release create "$tag" --draft --generate-notes --verify-tag
fi

for asset in "${assets[@]}"; do
  name=$(basename "$asset")

  if gh release view "$tag" --json assets \
    --jq '.assets[] | select(.state == "uploaded") | .name' | grep -Fxq "$name"; then
    echo "Already uploaded: $name"
    continue
  fi

  uploaded=false
  for attempt in 1 2 3; do
    echo "Uploading $name (attempt $attempt of 3)..."
    if gh release upload "$tag" "$asset" --clobber; then
      uploaded=true
      break
    fi

    if (( attempt < 3 )); then
      delay=$((attempt * 15))
      echo "Upload failed; retrying $name in ${delay}s..." >&2
      sleep "$delay"
    fi
  done

  if [[ "$uploaded" != true ]]; then
    echo "Failed to upload $name after 3 attempts." >&2
    exit 1
  fi
done

# Tags with a hyphen are prereleases. Publish only after every asset succeeds,
# so a failed job remains a recoverable draft rather than a partial release.
if [[ "$tag" == *-* ]]; then
  gh release edit "$tag" --draft=false --prerelease --latest=false
else
  gh release edit "$tag" --draft=false --prerelease=false --latest
fi
