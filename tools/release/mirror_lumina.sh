#!/usr/bin/env bash
set -euo pipefail

tag=${1:-}
if [[ ! $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Expected a release tag such as v0.5.3." >&2
  exit 2
fi

: "${LUMINA_URL:?Missing LUMINA_URL}"
: "${LUMINA_USER:?Missing LUMINA_USER}"
: "${LUMINA_PASSWORD:?Missing LUMINA_PASSWORD}"

upload_root=${LUMINA_URL%/}
download_origin=https://registry.amaicat.work
download_root=$download_origin/repository/github-krose
if [[ $upload_root == https://registry.amaicat.work ]]; then
  echo "Upload endpoint is the public mirror domain."
else
  echo "Upload endpoint differs from the public mirror domain."
fi
version=${tag#v}
assets=(
  "Krose-$version-windows-x64-setup.exe"
  "Krose-$version-macos-universal.pkg"
  "Krose-$version-windows-x64-portable.zip"
  "Krose-$version-macos-universal-app.zip"
)
aliases=(windows-setup.exe macos-universal.pkg windows-portable.zip macos-universal-app.zip)

release_files=$(mktemp -d)
trap 'rm -rf -- "$release_files"' EXIT
cd "$release_files"
patterns=(--pattern SHA256SUMS.txt)
for name in "${assets[@]}"; do
  patterns+=(--pattern "$name")
done
gh release download "$tag" --repo "$GITHUB_REPOSITORY" "${patterns[@]}"
sha256sum "${assets[@]}" | cmp - SHA256SUMS.txt

public_matches() {
  local target=$1 expected=$2 sha1 etag
  local options=(--proto '=https' -H 'Cache-Control: no-cache' --connect-timeout 15 --max-time 30)
  sha1=$(curl -qfsS "${options[@]}" --get --data-urlencode 'repository=github-krose' \
    --data-urlencode "name=$target" "$download_origin/service/rest/v1/search/assets" 2>/dev/null |
    jq -er --arg target "$target" --arg expected "$expected" \
      '.items[] | select(.path == $target and .checksum.sha256 == $expected) | .checksum.sha1') ||
    return 1
  [[ $sha1 =~ ^[0-9a-f]{40}$ ]] || return 1
  etag=$(curl -qfsSLI "${options[@]}" --proto-redir '=https' "$download_root/$target" 2>/dev/null |
    awk 'tolower($1) == "etag:" { gsub(/["\r]/, "", $2); etag=$2 } END {print etag}') ||
    return 1
  [[ $etag == "$sha1" ]]
}

upload() {
  local source=$1 dir=$2 name=$3 method response code bytes
  bytes=$(wc -c < "$source")
  local options=(--silent --show-error --proto '=https' --retry 0
    --connect-timeout 30 --max-time 180 --user "$LUMINA_USER:$LUMINA_PASSWORD"
    --output /dev/null --write-out '%{http_code} (%{size_upload} bytes, %{time_total}s, %{speed_upload} B/s, HTTP/%{http_version})')
  local put_url="$upload_root/repository/github-krose/$dir/$name"
  for method in PUT POST PUT-HTTP1; do
    if [[ $method == PUT ]]; then
      response=$(curl -q "${options[@]}" --upload-file "$source" "$put_url") || true
    elif [[ $method == POST ]]; then
      response=$(curl -q "${options[@]}" --form-string "raw.directory=/$dir" \
        --form "raw.asset1=@$source" --form-string "raw.asset1.filename=$name" \
        "$upload_root/service/rest/v1/components?repository=github-krose") || true
    else
      response=$(curl -q "${options[@]}" --http1.1 -H 'Expect:' \
        --upload-file "$source" "$put_url") || true
    fi
    code=${response%% *}
    echo "$method $dir/$name: ${response:-network error} (file: $((bytes)) bytes)"
    case $code in
      2??) return 0 ;;
      401|403|413) return 1 ;;
      *) sleep 5 ;;
    esac
  done
  return 1
}

sync_file() {
  local source=$1 dir=$2 name=$3 expected
  expected=$(sha256sum "$source")
  expected=${expected%% *}
  if public_matches "$dir/$name" "$expected"; then
    echo "Verified existing $dir/$name"
    return
  fi

  # A gateway timeout can occur after the origin stored the file.
  upload "$source" "$dir" "$name" || true
  for delay in 0 5 15; do
    sleep "$delay"
    if public_matches "$dir/$name" "$expected"; then
      echo "Verified $dir/$name"
      return
    fi
  done
  echo "Public download missing or SHA-256 mismatch: $dir/$name" >&2
  return 1
}

for name in "${assets[@]}" SHA256SUMS.txt; do
  sync_file "$name" "$tag" "$name"
done

latest=$(gh api "repos/$GITHUB_REPOSITORY/releases/latest" --jq '.tag_name')
if [[ $tag == "$latest" ]]; then
  for index in "${!assets[@]}"; do
    sync_file "${assets[index]}" latest "${aliases[index]}"
  done
fi
