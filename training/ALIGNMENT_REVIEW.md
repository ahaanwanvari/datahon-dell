# Application and model alignment review

Reviewed November 13, 2026 against WORK_COMPLETED.md and local source.
Local commit and GitHub origin HEAD both resolve to
`d6724a272778631c2b114badbd2b83f0ee854e46`.

## Follow-up integration

The serving gap identified below has now been implemented locally. The app and
notebook share the Atlas v2 API. See `INTEGRATION.md` for deployment and live
verification results. The original findings below remain the pre-change audit.

## Finding

Texas Flood Atlas and the notebook adapter share a historical visual-evidence
use case, but they are not yet integrated into one serving path.

| Aspect | Web application | Notebook model | Alignment |
|---|---|---|---|
| Checkpoint | Defaults to Qwen/Qwen3-VL-8B-Instruct through FLOOD_VLM_URL | active_adapter.json selects Atlas v2 | Deployment gap: app source does not select the adapter |
| Input | Before/after images plus dates, sensors and declared alignment | One or two images and a free-form question | Paired inputs supported; single-image use is additional functionality |
| Output | Validated JSON: summary, kind, strength, uncertainty, evidence | Free-form answer; saved app-prompt check produced valid JSON | Interface check passed; keep app validation when integrating |
| Image preparation | JPEG preview up to 768 px | RGB preview up to 448 px | Different preprocessing; app integration needs validation at its actual settings |
| Task evidence | Historical visual change descriptions | VQA plus paired-description replay and identical-image controls | Relevant training mix; paired validation loss regressed about 17% |
| Routes and planning | OSRM, public feeds, deterministic screening and arithmetic | No validated forecasting or route-safety model | Do not attribute those app functions to adapter training |

## Evidence and limits

- `app.py` defines the API endpoint/model defaults and the paired JSON request.
- `active_adapter.json` selects `runs/atlas-v2/adapter` for notebook inference.
- `runs/atlas-v2/inference_check.json` records a correct single-image answer and
  an app-schema-compatible paired answer. This is saved verification evidence,
  not a new inference run or independent paired-accuracy evaluation.
- WORK_COMPLETED.md reports held-out VQA accuracy of 87/96 and explicitly
  documents same-event, filename-group split limitations.
- All nine application unit tests passed again during this review. These tests
  do not verify live model serving or checkpoint identity.

## Work needed for full integration

Serve the existing Atlas v2 adapter through an API compatible with the app,
configure FLOOD_VLM_URL and FLOOD_MODEL for that endpoint, verify the served
checkpoint identity, and exercise the actual app request and JSON validation.
Evaluate paired descriptions independently before claiming improved timeline
accuracy. Keep inference separate from training: an image question should never
launch training or validation.

No training, validation, GPU-worker lifecycle, API deployment, GitHub publishing,
or checkpoint selection was changed by this review. Training additions and this
review remain local and uncommitted.
