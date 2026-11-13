# Texas Flood Atlas model adaptation

Read [ANALYSIS.md](ANALYSIS.md) for the task and data assessment.

This continues the local Qwen3-VL-8B-Instruct LoRA using published FloodNet VQA answers, UTSA change-description replay, and exact identical-image controls. It does not train flood forecasting, routing, road passability or damage valuation.

## Local prerequisites

- Existing pinned Qwen base weights in the Hugging Face cache.
- Existing first-stage adapter, `pairs.json`, `labels.jsonl` and `workflow.py` under `~/jupyterlab/flood_training`.
- UTSA images under `~/jupyterlab/Texas_Flood_Student_Data`.
- FloodNet VQA metadata checkout under `~/jupyterlab/FloodNet_VQA_source`, pinned to `9a2135a8d25b2cc471c9694b79107d1af4a64d8a`. Clone with `GIT_LFS_SKIP_SMUDGE=1` so metadata is available without downloading all source images. The preparation script fetches selected LFS image objects and verifies SHA-256 values.
- The tested isolated interpreter is `~/jupyterlab/.flood-training-venv/bin/python` (PyTorch 2.13.0+cu130, Transformers 5.16.1, PEFT 0.20.0). CUDA extension compilation needs Python 3.12 headers; on this machine they are extracted locally into the environment's `headers/` directory.

## Prepare and train

From the repository root:

```bash
~/jupyterlab/.flood-training-venv/bin/python -u training/prepare_data.py
~/jupyterlab/.flood-training-venv/bin/python -u training/train_atlas.py
```

Preparation preserves dataset answers and provenance, groups images before splitting, balances answer categories, checks exact-image separation and writes a manifest. It never generates new VQA labels with an AI model. Official validation/test annotations have no public answers, so evaluation uses explicitly regrouped labeled training images, not the official hidden benchmark.

Results are stored separately under `~/jupyterlab/flood_training/runs/atlas-v2/`:

- `data_report.json`: data mix, labels, source revision and split limitations.
- `dataset.json`: exact inputs, prompts, targets and their origin.
- `metrics.jsonl`: training progress and losses.
- `adapter/`: the new LoRA checkpoint; the previous adapter is preserved.
- `training_report.json`: prior-versus-new validation losses and published-label held-out VQA metrics.
- `*_predictions.json`: actual questions, expected labels and generated predictions.

Only default LoRA weights train; the base weights and the second frozen copy of the prior adapter are preserved. Learning rate: 2e-5; one epoch; accumulation: 4; seed: 3407. Only assistant tokens contribute to loss. The new candidate must improve validation loss without a large paired-description regression before becoming the preferred image-testing adapter. Held-out test results are reported after training and are not used to choose hyperparameters.

The training runtime serializes GPU access with the existing image-test helper and temporarily pauses `qwen-vl-server`. It restores that server when training exits. If a notebook is keeping the earlier model worker loaded, finish its current prompt and call `predict.close_model()` to release that worker before training.

This training script writes a candidate, not a production deployment. The application reads `FLOOD_VLM_URL` and `FLOOD_MODEL`; its existing Docker server still serves the base model unless configured separately. Local `predict.ask_image` can select an accepted adapter through `active_adapter.json` after checkpoint reload validation.

## Dataset attribution

FloodNet: Rahnemoonfar et al., *FloodNet: A High Resolution Aerial Imagery Dataset for Post Flood Scene Understanding*, IEEE Access, 2021, DOI 10.1109/ACCESS.2021.3090981.

- https://github.com/BinaLab/FloodNet-Challenge-EARTHVISION2021
- https://huggingface.co/datasets/takara-ai/FloodNet_2021-Track_2_Dataset_HF

Downloaded data, image bytes, manifests containing local paths and trained weights are kept outside the source checkout.
