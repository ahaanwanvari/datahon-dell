# Flood Watch / Texas Flood Atlas — work completed

Date: November 13, 2026.

## Current status

**Automatic photo review:** Generate flooded view now also runs Qwen analysis,
displays its explanation below the viewer, and adds hover/focus/tap info markers
for grounded visual features. These are unverified photo observations, not
certified safe spots or image-only evacuation directions. See
`training/AUTOMATIC_PHOTO_REVIEW.md` for model provenance and live checks.


**Photo location update:** Added an index of 1,200 georeferenced UTSA images,
exact and conservative resized-copy matching, source-reference thumbnails,
footprint display, and explicit map-pin confirmation before destination lookup.
Unknown images still require GPS or user-supplied location; this is not global
image geolocation. See `training/PHOTO_LOCATION.md` for checks and limitations.


**Photo-to-flood workflow:** The app now supports local reference-photo editing
with FLUX.2 Klein 4B, a before/generated slider, and source-backed preparedness
site lookup with model assessment. This replaces image description as the main
upload flow. See `training/FLOOD_SCENARIOS.md` for model provenance, live checks,
and geographic/data limits. Generated flood imagery is not a flood forecast or
road-passability input.


**Integration update (November 13):** The local review checkout now includes a
resident Atlas v2 inference API, a file-path client, an image-question upload
panel, and paired timeline integration. The running app is on port 8766 and the
API on port 8001, managed by separate per-user services. Training and validation
are not launched by inference. See `training/INTEGRATION.md` for current
verification evidence. Earlier sections below describe the state before this
integration; the statement that the adapter is not deployed to the app is now
historical. Source changes remain local and unpushed.


Repository review, two local model-adaptation runs, evaluation, and file-path image testing are complete. The preferred checkpoint for the local `ask_image()` helper is **Atlas v2**.

The web application still uses its configured model API. The trained adapter has **not** been deployed to that API. The newer review/training source files described below are local changes and have **not** been committed or pushed to GitHub.

## 1. Identified and explained the application

Located the original Flood Change Explorer in `/home/dell/jupyterlab/GB10competition/flood_explorer` and inspected its code and documentation.

Explained its workflow:

1. Import dated images and location metadata.
2. Compare consecutive observations of the same location with Qwen.
3. Save descriptions, change types, apparent magnitude, uncertainty, and source evidence.
4. Build dated timelines in the application.
5. Browse image pairs, search descriptions, optionally review observations, and export evidence.

The model interprets images. The application handles pairing, persistence, search, and timeline generation. Observation windows do not establish exact flood onset dates.

## 2. Published the initial application repository

- Confirmed GitHub CLI was already installed; installation was unnecessary.
- Started device authentication, which you completed with your GitHub account.
- Prepared a standalone application checkout at `/home/dell/datahon-dell`.
- Excluded runtime state, virtual environments, caches, environment files, and logs.
- Retained the original GNU GPL v3 license and source/dataset attribution.
- Updated the README with the new clone URL.
- Ran the initial eight application tests successfully.
- Created and pushed the public repository: <https://github.com/ahaanwanvari/datahon-dell>.
- Initial application commit: `d1a5c9b`.

Authentication codes and credentials are intentionally omitted from this handoff.

## 3. Inspected JupyterLab, the model, and the machine

Identified the model used by `Untitled1.ipynb` and the Docker inference server:

| Item | Value |
|---|---|
| Base model | `Qwen/Qwen3-VL-8B-Instruct` |
| Pinned model revision | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |
| GPU | NVIDIA GB10 |
| Existing server container | `qwen-vl-server` |
| Existing model API | `http://127.0.0.1:8000/v1` |
| Jupyter workspace | `/home/dell/jupyterlab` |

The existing vLLM server reserved most of the unified memory. Training and checkpoint tests therefore temporarily paused that server while holding an exclusive GPU lock and restored it afterward. The image helper can also keep a model resident between prompts; `predict.close_model()` releases that worker.

## 4. Prepared the training environment

Created `/home/dell/jupyterlab/.flood-training-venv` without replacing the existing Jupyter environment.

- Reused installed Jupyter/PyTorch packages through a `.pth` entry.
- Installed a compatible Hugging Face Hub version locally to resolve the existing Transformers/Hub dependency conflict.
- Used the installed PyTorch, Transformers, and PEFT stack for LoRA adaptation.
- Diagnosed the first training attempt's Triton compiler failure: Python 3.12 development headers were missing.
- Downloaded and extracted the headers locally, without requiring a system-wide installation.
- Configured the compiler include path and confirmed that the Triton CUDA extension compiled.

Tested package versions included PyTorch `2.13.0+cu130`, Transformers `5.16.1`, and PEFT `0.20.0`.

## 5. First adaptation: UTSA image-pair descriptions

### Data inspection and label decision

Used the installed UTSA dataset at `/home/dell/jupyterlab/Texas_Flood_Student_Data`:

- Dataset: `jennifer-fowler/UTSA-flood-images`.
- Revision: `ad98e681e7cf6af9ced145833b522c4f6c0acad1`.
- 1,204 aerial images, including 575 documented Harvey before/after pairs and 54 standalone images.

The supplied flood annotation fields were blank. Saved Flood Watch reviews also contained no human-confirmed examples. Initially prepared a human-review interface, including optional Qwen suggestions. You subsequently requested fully autonomous labeling and training, so the first run used **AI-generated, unverified targets**, with that origin recorded explicitly.

Reused existing Qwen observations only where both source image hashes matched. Excluded synthetic demo fixtures and generated missing targets with the existing local model. Did not fabricate comparisons for standalone images.

### Split and training

| Split | Pairs |
|---|---:|
| Training | 457 |
| Validation | 85 |
| Held-out testing | 25 |
| Excluded near held-out footprints | 8 |

Reserved whole localities for validation/testing and removed nearby training footprints using a bounding-box buffer. Verified source image SHA-256 values.

Training configuration:

- One epoch; 115 optimizer steps.
- Rank-8 LoRA on language-model attention `q_proj` and `v_proj` projections.
- Approximately 3.83 million trainable parameters; base weights frozen.
- Learning rate `5e-5`; accumulation of four examples.
- Bfloat16, gradient checkpointing, assistant-only token loss, seed `3407`.

### Result

Validation token loss decreased from **0.7941 to 0.3038**. This measures agreement with AI-generated targets, not independently verified flood accuracy.

Saved and reloaded the first adapter, checked that its weights had received nonzero updates, and completed a held-out base-versus-adapter comparison. Verified 457 training records, 115 optimizer steps, and finite losses.

First adapter: `/home/dell/jupyterlab/flood_training/adapter`.

First training report: `/home/dell/jupyterlab/flood_training/training_report.json`.

## 6. Built notebook and image-file testing support

Created `/home/dell/jupyterlab/Flood_Watch_Train_and_Test.ipynb` and supporting modules under `/home/dell/jupyterlab/flood_training`.

Work included:

- Dataset review and optional labeling controls.
- Automatic training status and comparison controls.
- Before/after previews and held-out pair selection.
- A file-path API accepting a new image and a natural-language question.
- Optional second-image input for comparison.
- Upload/prompt interface support.
- Model-worker reuse between prompts and a clean shutdown function.
- GPU serialization and inference-server lifecycle handling.
- Active-checkpoint selection and checkpoint-aware comparison-cache checks.

Fixed issues encountered during use:

- Replaced invisible background-thread output handling with explicit widget output messages.
- Added visible loading progress and busy-button behavior.
- Diagnosed Jupyter processes lacking supplementary Docker group membership; added a Docker-group execution fallback and explicit inspection errors.
- Used GPU locking to prevent overlapping model loads.
- Preserved the existing persistent-worker helper behavior while adding checkpoint selection.
- Explained that loading the notebook's newer disk version does not interrupt separately running training.

### Test a new image

Run this in a JupyterLab cell, replacing the file path and question:

```python
import sys
sys.path.insert(0, "/home/dell/jupyterlab/flood_training")

from predict import ask_image, close_model

answer = ask_image(
    "/home/dell/jupyterlab/my_new_image.jpg",
    "Is flooding visible? Describe the evidence and any uncertainty."
)
print(answer)

# Run when finished asking questions to release the resident model:
# close_model()
```

For two images:

```python
answer = ask_image(
    "/path/to/before.jpg",
    "Compare the two images and describe visible changes and uncertainty.",
    second_image="/path/to/after.jpg",
)
print(answer)
```

Initial model loading takes roughly two minutes on this setup. Later prompts can reuse the resident worker. Uploaded/copied test images are stored locally under `custom_tests`; the helper does not add them to training.

## 7. Cloned and analyzed the newer GitHub application

Created a fresh clone at `/home/dell/datahon-dell-review`, preserving the earlier checkout.

Reviewed commit: `d6724a272778631c2b114badbd2b83f0ee854e46` — “Add Texas flood planning and route risk screening.”

The application is now called **Texas Flood Atlas**. Inspected its README, backend, frontend, model prompt, APIs, route-screening logic, and tests.

Found that:

- Qwen is still called only for historical image-pair descriptions.
- OSRM generates route alternatives.
- FEMA/TxDOT matching and fixed arithmetic perform route screening.
- Alerts, gauges, roads, and mapped hazards come from public feeds.
- The recovery scenario calculator multiplies user-entered assumptions.
- The repo did not contain an adapter-training loop or trained-adapter serving configuration.

All **nine** existing application tests passed during this review.

Wrote the assessment in `training/ANALYSIS.md` and added training instructions and scripts. Updated the clone's README to link to that material.

## 8. Identified the next training needs

Inspected the first run's 542 targets:

| Target type | Count |
|---|---:|
| Water increase | 480 |
| Water decrease | 49 |
| Stable | 9 |
| Uncertain | 4 |

This exposed a strong water-increase imbalance and a lack of supervised single-image questions, despite the new-image prompting use case.

Selected three complementary tasks:

1. Published-label single-image flood/road-condition VQA.
2. UTSA paired-description replay to retain the existing timeline task.
3. Identical-image controls whose no-change target follows from exact input equality.

Excluded fine-grained building-count questions because the model input previews reduce the original high-resolution imagery to at most 448 pixels on a side.

Did not train the VLM to forecast floods, certify road passability, issue evacuation instructions, infer flood depth, or estimate monetary losses. The repository does not provide training targets or model-based implementations for those functions.

## 9. Second adaptation: Atlas v2

### Published-label dataset

Used the FloodNet VQA mirror:

- Dataset: `takara-ai/FloodNet_2021-Track_2_Dataset_HF`.
- Revision: `9a2135a8d25b2cc471c9694b79107d1af4a64d8a`.
- Metadata checkout: `/home/dell/jupyterlab/FloodNet_VQA_source`.
- Selected original images: `/home/dell/jupyterlab/FloodNet_VQA_images`.

Inspected the original project documentation and the actual question annotations. The labeled source pool contained 4,511 questions associated with 1,448 image annotation files. The mirror's official validation/test annotations omitted answers.

After Hugging Face per-file requests were rate-limited, obtained metadata through a Git checkout and downloaded selected LFS image objects in batches. Downloaded **566 source images**, approximately **2.82 GB**, and verified their SHA-256 values. Generated reusable RGB previews.

Kept source questions, answers, annotation references, revision identifiers, and image hashes. VQA targets came from the published annotations; no AI model generated these new VQA labels.

### Splits and mixture

Regrouped the labeled source training pool by numeric filename hundred-blocks, with five-image boundary buffers. Split groups before selecting or balancing questions. Checked that exact images did not cross splits. Capped repeated questions per image.

| Task | Train | Validation | Test |
|---|---:|---:|---:|
| Published-label single-image VQA | 517 | 96 | 96 |
| AI-generated UTSA paired-description replay | 147 | 27 | 0 |
| Deterministic identical-image controls | 64 | 16 | 0 |
| **Total** | **728** | **139** | **96** |

The VQA training subset contained 128 flooded, 128 non-flooded, 128 yes, 128 no, and five mixed answers. Each VQA evaluation subset contained 24 answers in each of the four main categories. The 96 test questions used 80 images.

These are filename-group holdouts from the labeled training pool, **not** the official hidden test benchmark. They are from the same Harvey event. Filename grouping and buffers reduce trivial adjacent-view leakage but do not establish geographic or event independence. The balanced evaluation also does not represent natural deployment prevalence.

### Training configuration

- Initialized from the first UTSA adapter.
- Preserved a frozen copy of that adapter for comparison.
- Froze base model weights; trained only the active LoRA parameters.
- One epoch; **182 optimizer steps**.
- Learning rate **2e-5**, weight decay `0.01`, accumulation of four examples.
- Bfloat16, gradient checkpointing, assistant-only token loss, seed `3407`.
- Verified token-prefix masking for single-image, paired-change, and identical-image tasks.
- Recorded per-example metrics and separate validation losses by task.

### Results

| Metric | First UTSA adapter | Atlas v2 |
|---|---:|---:|
| Held-out VQA exact-answer accuracy | 53.125% — 51/96 | **90.625% — 87/96** |
| Held-out VQA macro-F1 | 0.463 | **0.906** |
| Single-image VQA validation loss | 1.027 | **0.048** |
| Identical-image control validation loss | 2.342 | **0.628** |
| Paired-change validation loss | **0.288** | 0.338 |
| Overall mixed validation loss | 1.035 | **0.171** |

Lower loss is better. Paired-description loss **regressed about 17%**. The acceptance rule required lower overall validation loss and permitted at most a 50% paired-loss regression; Atlas v2 passed that rule. This is a tradeoff favoring the new single-image use case, not evidence that every task improved. The first adapter is retained.

The held-out test was run after the training configuration was fixed. Saved actual predictions and per-answer precision, recall, F1, and support. Neither adapter produced an invalid short-answer category in that evaluation.

### Checkpoint and helper verification

- Saved the new checkpoint separately from the first adapter.
- Reloaded it into a fresh model instance and generated an answer.
- Confirmed that the first adapter's file hash was unchanged.
- Selected Atlas v2 through `active_adapter.json`.
- Tested the actual `predict.ask_image()` file-path helper on a held-out single image: expected `flooded`, received `flooded`.
- Used the same helper on an unseen UTSA image pair with the application's prompt; its response passed the application's JSON schema.
- Closed the verification worker cleanly, allowing inference-server restoration.

The schema check verifies interface compatibility, not independent accuracy of the paired flood description.

## 10. Important file locations

| File or directory | Purpose |
|---|---|
| `/home/dell/datahon-dell` | Earlier standalone app checkout published to GitHub |
| `/home/dell/datahon-dell-review` | Fresh clone of the newer Texas Flood Atlas commit |
| `/home/dell/datahon-dell-review/WORK_COMPLETED.md` | This handoff |
| `/home/dell/datahon-dell-review/training/ANALYSIS.md` | Repository and training-needs assessment |
| `/home/dell/datahon-dell-review/training/README.md` | Training prerequisites and reproduction instructions |
| `/home/dell/datahon-dell-review/training/RESULTS.md` | Atlas v2 results and limitations |
| `/home/dell/datahon-dell-review/training/prepare_data.py` | Dataset selection, downloads, checks, and preparation |
| `/home/dell/datahon-dell-review/training/train_atlas.py` | Continuation training and evaluation |
| `/home/dell/datahon-dell-review/training/atlas_runtime.py` | Pinned model loading and exclusive GPU access |
| `/home/dell/datahon-dell-review/training/check_inference.py` | Actual helper and app-schema verification |
| `/home/dell/jupyterlab/Flood_Watch_Train_and_Test.ipynb` | Notebook for model work and comparison |
| `/home/dell/jupyterlab/flood_training/predict.py` | File-path `ask_image()` and worker shutdown API |
| `/home/dell/jupyterlab/flood_training/prompt_test.py` | Adapter-backed image inference worker |
| `/home/dell/jupyterlab/flood_training/active_adapter.json` | Preferred image-helper checkpoint and fingerprint |
| `/home/dell/jupyterlab/flood_training/adapter` | Preserved first-stage adapter |
| `/home/dell/jupyterlab/flood_training/runs/atlas-v2/adapter` | New Atlas v2 adapter |
| `/home/dell/jupyterlab/flood_training/runs/atlas-v2/data_report.json` | Actual data mix and split limitations |
| `/home/dell/jupyterlab/flood_training/runs/atlas-v2/training_report.json` | Full configuration, losses, and evaluation metrics |
| `/home/dell/jupyterlab/flood_training/runs/atlas-v2/reload_check.json` | Saved-checkpoint reload evidence |
| `/home/dell/jupyterlab/flood_training/runs/atlas-v2/inference_check.json` | Actual single-image/helper and paired-schema results |
| `/home/dell/jupyterlab/flood_training/runs/atlas-v2/*_predictions.json` | Expected and generated held-out VQA answers |
| `/home/dell/jupyterlab/flood_training/runs/atlas-v2/metrics.jsonl` | Per-example training losses and optimizer steps |

## 11. Remaining work and limitations

1. **Web application integration:** configure a model-serving endpoint that loads the trained adapter, then point `FLOOD_VLM_URL` and `FLOOD_MODEL` to it. Current `ask_image()` use of Atlas v2 does not change the web app's API model.
2. **Publishing newer source:** the review checkout's training additions, README update, and this handoff remain local. The later training code and model weights were not pushed to GitHub.
3. **Broader evaluation:** test additional events, locations, sensors, ordinary unchanged scenes, recovery sequences, and uncertain cases using independently verified labels.
4. **Paired-task improvement:** obtain verified temporal-change labels and address the paired-description loss regression before claiming that Atlas v2 improves timeline interpretation.
5. **Operational scope:** the reported scores do not establish flood forecasting, live travel safety, segmentation accuracy, calibrated probabilities, building-count accuracy, or loss estimation. None of those capabilities was validated by this work.

## Sources and attribution

- Application repository: <https://github.com/ahaanwanvari/datahon-dell>
- Original workspace: <https://github.com/jennifer-fowler/GB10competition>
- UTSA imagery: <https://huggingface.co/datasets/jennifer-fowler/UTSA-flood-images>
- FloodNet challenge: <https://github.com/BinaLab/FloodNet-Challenge-EARTHVISION2021>
- FloodNet supervised project: <https://github.com/BinaLab/FloodNet-Supervised_v1.0>
- FloodNet VQA mirror: <https://huggingface.co/datasets/takara-ai/FloodNet_2021-Track_2_Dataset_HF>
- FloodNet paper: Rahnemoonfar et al., *FloodNet: A High Resolution Aerial Imagery Dataset for Post Flood Scene Understanding*, IEEE Access, 2021, DOI `10.1109/ACCESS.2021.3090981`.

The application retains its original license and attribution. Dataset sources have their own terms: the FloodNet mirror declares CC-BY-SA 4.0, while the originating supervised project lists CDLA Permissive 1.0. Downloaded data and model artifacts were kept local; no new blanket dataset license was applied.
