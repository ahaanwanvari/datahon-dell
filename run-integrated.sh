#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
training_home="${FLOOD_TRAINING_HOME:-/home/dell/jupyterlab/flood_training}"
model_python="${FLOOD_MODEL_PYTHON:-$(dirname "$training_home")/.flood-training-venv/bin/python}"
export FLOOD_TRAINING_HOME="$training_home"
export FLOOD_INFERENCE_PORT="${FLOOD_INFERENCE_PORT:-8001}"
export FLOOD_VLM_URL="http://127.0.0.1:${FLOOD_INFERENCE_PORT}/v1"
export FLOOD_LOCAL_ATLAS=1
inference_pid=""
if "$model_python" -c 'import os,requests; r=requests.get(os.environ["FLOOD_VLM_URL"].removesuffix("/v1")+"/health",timeout=2); r.raise_for_status(); assert r.json()["model"].startswith("atlas-v2-")' 2>/dev/null; then
  echo "Reusing running Atlas inference service."
else
  "$model_python" -u inference/server.py &
  inference_pid=$!
fi
cleanup() {
  if [[ -n "${app_pid:-}" ]]; then kill "$app_pid" 2>/dev/null || true; fi
  if [[ -n "$inference_pid" ]]; then
    kill "$inference_pid" 2>/dev/null || true
    wait "$inference_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 0' INT TERM
"$model_python" - <<'PY'
import os, time, requests, json
from pathlib import Path
url = os.environ['FLOOD_VLM_URL'].removesuffix('/v1') + '/health'
for _ in range(100):
    try:
        requests.get(url, timeout=1).raise_for_status()
        break
    except requests.RequestException:time.sleep(.1)
else:raise SystemExit('Atlas API did not start; see server output.')
config = Path(os.environ['FLOOD_TRAINING_HOME'])/'inference_service.json'
config.write_text(json.dumps({'url':os.environ['FLOOD_VLM_URL']},indent=2))
PY
./run.sh &
app_pid=$!
if [[ -n "$inference_pid" ]]; then
  wait -n "$inference_pid" "$app_pid"
else
  wait "$app_pid"
fi
