#!/usr/bin/env bash
# Start mock providers (9100) + studio (8010) wired to the mocks. Usage: dev_tools/run_e2e.sh [data_dir]
set -e
cd "$(dirname "$0")/.."
DATA="${1:-/tmp/aas_e2e_data}"
M=http://127.0.0.1:9100
export META_DIALOG_BASE=$M/fb META_GRAPH_BASE=$M/graph IG_AUTH_BASE=$M/igauth IG_API_BASE=$M/igapi \
       IG_GRAPH_BASE=$M/iggraph LINE_API_BASE=$M/line SHOPEE_AFFILIATE_ENDPOINT=$M/shopee/graphql \
       META_APP_ID=111222333 META_APP_SECRET=mocksecret IG_APP_ID=444555666 IG_APP_SECRET=mockigsecret \
       VIDEO_MOCK=1 VIDEO_MOCK_SECONDS=${VIDEO_MOCK_SECONDS:-8} STUDIO_CLIP_CREDITS=10 COMMUNITY_DATA_DIR="$DATA" ENABLED_VIDEO_MODELS=all
python3 -m uvicorn dev_tools.mock_providers:app --host 127.0.0.1 --port 9100 --log-level warning &
python3 -m uvicorn community_app:app --host 127.0.0.1 --port 8010 --log-level warning &
wait
