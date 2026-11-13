# Atlas v2 integration — November 13, 2026

The local application and notebook now use one resident Atlas v2 model.

- Application: http://127.0.0.1:8766
- Vision API: http://127.0.0.1:8001/v1
- Readiness and model identity: http://127.0.0.1:8001/health
- Model: `atlas-v2-d41f87b26973ae3f`
- Adapter SHA-256: `d41f87b26973ae3f8dd0148f38f0740bc3d3cfc7e0a61cef74c3657d0f6068d1`

The separate older application on port 8765 has not been replaced. Use port 8766
for this integration. Source changes are local and have not been pushed.

## Inference path

The browser upload panel, app timeline indexing, `inference.client.ask_image`,
and the installed notebook `predict.ask_image` send requests to the same API.
The API serializes generation and loads the selected adapter once, holding GPU
ownership until shutdown. App-only restarts and notebook kernel restarts do not
unload that service. API shutdown/restart, machine reboot or a process failure
requires loading the model again. None of these request paths starts training
or model validation.

The model identifier includes its adapter fingerprint, so the app's existing
observation cache distinguishes this checkpoint from the base model. Responses
with a mismatched model identity are rejected. Paired output is validated by the
app; the service does not claim grammar-constrained JSON generation.

Previews are capped at 448 px for the trained model. Original image paths,
metadata, hashes and observation provenance remain available through the app.
Questions and uploaded images are not added to training.

## Verification performed

- All 13 application/API tests passed.
- Python syntax, shell syntax, JavaScript syntax and diff whitespace checks passed.
- Desktop and mobile screenshots were visually inspected.
- Two real single-image file-path queries used one model load. First request:
  173.04 s, including GPU handoff and loading. Second brief question: 0.35 s.
  These are observed timings, not general latency guarantees; longer answers
  require more generation time.
- Actual `/api/ask` upload route returned an Atlas v2 answer.
- Browser file selection, preview generation, submission, answer rendering and
  button re-enabling were exercised through Chrome's DevTools interface.
- One real held-out UTSA pair was imported into the new review app, indexed,
  validated and persisted as a timeline observation. This is a smoke test,
  not an independent accuracy evaluation. Demo records remain separate.
- Repeating discovery reused the persisted observation with no additional
  inference request.
- Restarting only `flood-atlas-app` preserved the API and model load count.
- The user's open notebook made a real query through the shared service with
  no private model worker.
- Final verification snapshot: model ready, six successful requests, one model
  load. Later user requests naturally increase the request count.

Detailed machine-local evidence:
`/home/dell/jupyterlab/flood_training/runs/atlas-v2/integration_check.json`
and `browser_check.json` in the same directory.

## Operation

The running services are `flood-atlas-app` and `flood-atlas-inference` under
`systemctl --user`. They are installed but not enabled for automatic login
startup. `deployment/install-local-services.py` reproduces their definitions.
See the repository README for start, stop, logs and notebook examples.

The shared service pauses the existing base-model Docker server while using the
GPU; graceful shutdown restores it. Stop both Atlas services before separately
running training. No training or model-validation process was restarted during
this integration, and existing adapter weights were not changed.

Public feeds, routing and recovery arithmetic retain their original behavior.
The model quality and held-out evaluation limitations in RESULTS.md still apply.
