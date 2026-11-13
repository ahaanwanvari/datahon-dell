# Atlas v2 training results

The local Qwen3-VL-8B-Instruct adapter was continued for one epoch on 728 examples: 517 published-label FloodNet VQA questions, 147 earlier UTSA image-pair descriptions, and 64 exact identical-image controls. The base model and previous adapter remain intact.

Evaluation used 139 validation examples and 96 VQA questions from held-out filename groups. Those 96 questions use 80 images, with 24 answers in each of four categories: flooded, non flooded, yes, and no. These are regrouped labeled training-pool images because official validation/test answers are withheld. This is a balanced local pilot on the same Harvey event, not official benchmark or event-independent accuracy.

| Metric | Previous UTSA adapter | Atlas v2 |
|---|---:|---:|
| Held-out VQA exact-answer accuracy | 53.125% (51/96) | 90.625% (87/96) |
| Held-out VQA macro-F1 | 0.463 | 0.906 |
| Single-image VQA validation loss | 1.027 | 0.048 |
| Identical-image control validation loss | 2.342 | 0.628 |
| Paired-change validation loss | 0.288 | 0.338 |
| Overall mixed validation loss | 1.035 | 0.171 |

Lower loss is better. Paired-description loss regressed about 17%; retain the first adapter when that task is the priority. The validation acceptance rule allowed at most a 50% paired-loss regression while requiring improved overall loss; this checkpoint passed that rule. VQA exact match and token loss are different measures. Improved loss on identical-image controls does not establish that ordinary unchanged scenes are reliably detected.

The main improvement is supervised single-image flood/road-condition question answering. Training does not establish live road safety, flood forecasts, water depth, building counts or monetary damage estimates. UTSA paired replay remains AI-generated; it is not independently verified flood-change ground truth.

Artifacts: `~/jupyterlab/flood_training/runs/atlas-v2/`. Full per-answer metrics and actual predictions are in `training_report.json`, `previous_utsa_adapter_predictions.json` and `atlas_v2_predictions.json`. The saved checkpoint is reloaded before activation; file-path and app-schema checks are recorded separately in `reload_check.json` and `inference_check.json`.
