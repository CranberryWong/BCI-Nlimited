#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR="${ROOT_DIR}/docker-bundle"
PLATFORM="${1:-linux/amd64}"
TAG="${BCI_IMAGE_TAG:-latest}"

mkdir -p "${OUTPUT_DIR}"

docker buildx build \
  --platform "${PLATFORM}" \
  --load \
  -t "bci-music-dashboard-backend:${TAG}" \
  "${ROOT_DIR}/backend"

docker buildx build \
  --platform "${PLATFORM}" \
  --load \
  -t "bci-music-dashboard-frontend:${TAG}" \
  "${ROOT_DIR}/frontend"

docker save \
  "bci-music-dashboard-backend:${TAG}" \
  "bci-music-dashboard-frontend:${TAG}" \
  | gzip > "${OUTPUT_DIR}/bci-music-dashboard-images-${TAG}.tar.gz"

cp "${ROOT_DIR}/docker-compose.yml" "${OUTPUT_DIR}/docker-compose.yml"
cp "${ROOT_DIR}/.env.example" "${OUTPUT_DIR}/.env.example"
cp "${ROOT_DIR}/scripts/import-docker-bundle.ps1" "${OUTPUT_DIR}/start-windows.ps1"

mkdir -p \
  "${OUTPUT_DIR}/models" \
  "${OUTPUT_DIR}/backend/data/presets" \
  "${OUTPUT_DIR}/backend/data/sessions" \
  "${OUTPUT_DIR}/xdf-records"

if [ -f "${ROOT_DIR}/models/mlp_valence_model.pkl" ]; then
  cp "${ROOT_DIR}/models/mlp_valence_model.pkl" "${OUTPUT_DIR}/models/"
fi

cp -R "${ROOT_DIR}/backend/data/presets/." "${OUTPUT_DIR}/backend/data/presets/"
cp -R "${ROOT_DIR}/backend/data/sessions/." "${OUTPUT_DIR}/backend/data/sessions/"
find "${OUTPUT_DIR}" -name ".DS_Store" -delete

echo "Docker bundle created at: ${OUTPUT_DIR}"
echo "Target platform: ${PLATFORM}"
