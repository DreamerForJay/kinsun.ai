#!/usr/bin/env bash
# Bash port of build_staging_images.ps1 — same four images, same build args, and
# the same post-build assertions (linux/amd64, artifact label, non-root user,
# frontend consent-policy provenance label). Exists only because the repository
# ships a PowerShell script and pwsh is unavailable on this machine.
#
# Builds locally. Nothing is pushed to AWS.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <release-id> <consent-policy-version>" >&2
  exit 2
fi

release_id="$1"
consent_policy_version="$2"

[[ "$release_id" =~ ^[a-f0-9]{7,40}$ ]] || {
  echo "release-id must be 7-40 lowercase hex chars (a git sha)" >&2; exit 2; }
[[ "$consent_policy_version" =~ ^[a-z0-9][a-z0-9._-]{0,127}$ ]] || {
  echo "consent-policy-version has an unsupported format" >&2; exit 2; }

command -v docker >/dev/null || { echo "Docker was not found on PATH." >&2; exit 1; }

cd "$(dirname "$0")/.."

build_one() {
  local artifact="$1" dockerfile="$2" context="$3" tag="$4"; shift 4
  # ${extra[@]} on an empty array trips `set -u` on bash 3.2 (macOS default),
  # so the expansion is guarded rather than referenced directly.
  local extra=()
  if [[ $# -gt 0 ]]; then extra=("$@"); fi

  docker build \
    --platform linux/amd64 \
    --file "$dockerfile" \
    --tag "$tag" \
    --label "io.kinsun.artifact=${artifact}" \
    ${extra[@]+"${extra[@]}"} \
    "$context"

  local os arch label user
  os=$(docker image inspect "$tag" --format '{{.Os}}')
  arch=$(docker image inspect "$tag" --format '{{.Architecture}}')
  label=$(docker image inspect "$tag" --format '{{index .Config.Labels "io.kinsun.artifact"}}')
  user=$(docker image inspect "$tag" --format '{{.Config.User}}')

  [[ "$os" == "linux" && "$arch" == "amd64" ]] || {
    echo "Image platform mismatch for ${artifact}; linux/amd64 is required." >&2; exit 1; }
  [[ "$label" == "$artifact" ]] || {
    echo "Artifact label mismatch for ${artifact}." >&2; exit 1; }
  [[ -n "$user" && "$user" != "0" && "$user" != "0:0" && "$user" != "root" ]] || {
    echo "Image ${artifact} does not declare a non-root runtime user." >&2; exit 1; }

  if [[ "$artifact" == "frontend" ]]; then
    local consent
    consent=$(docker image inspect "$tag" \
      --format '{{index .Config.Labels "io.kinsun.consent-policy-version"}}')
    [[ "$consent" == "$consent_policy_version" ]] || {
      echo "Frontend consent policy provenance label mismatch." >&2; exit 1; }
  fi

  echo "ok    built ${artifact} as linux/amd64, non-root (user=${user})"
}

build_one frontend packages/frontend/Dockerfile . \
  "kinsun-staging-frontend:${release_id}" \
  --label "io.kinsun.consent-policy-version=${consent_policy_version}" \
  --build-arg "NEXT_PUBLIC_CONSENT_POLICY_VERSION=${consent_policy_version}" \
  --build-arg "NEXT_PUBLIC_WS_URL="

build_one core-api services/core-api/Dockerfile.api services/core-api \
  "kinsun-staging-core-api:${release_id}"

build_one core-migration services/core-api/Dockerfile services/core-api \
  "kinsun-staging-core-migration:${release_id}"

build_one agent-runtime services/agent-runtime/Dockerfile . \
  "kinsun-staging-agent-runtime:${release_id}"

echo
echo "Local staging image build passed. No image was pushed to AWS."
echo "Frontend consent policy compiled into the bundle: ${consent_policy_version}"
