# Texas Flood Atlas

Local Texas-focused flood decision-support prototype. It combines dated satellite-image change discovery with nearby public gauge, road-condition, and mapped flood-hazard context. Qwen runs on your existing GB10 model server. Human review is optional.

## Automatic photo location

Uploaded photos are checked against an index of 1,200 georeferenced UTSA images.
Original files and unchanged re-encodings can match exactly; conservative visual
fingerprints also recognize resized/recompressed copies. Ambiguous candidates
remain suggestions with source thumbnails. This is local dataset matching, not
a worldwide photo-location model. Unknown photos use GPS metadata when available,
or an address/coordinates entered by the user.

The confirmation map shows a proposed pin and, for dataset matches, the source
image's ground footprint. Aerial dataset coordinates are footprint centers, not
verified camera positions or street addresses. Click the map to move the pin,
use arrow keys for adjustments, then choose **This is the photo location**.
Destination lookup is disabled until confirmation, and the server independently
enforces that rule. Editing the location requires a new map confirmation. A
confirmed new pin clears destinations calculated for the old pin.

Destination cards include numeric latitude/longitude and map links. They remain
planning references unless current status and route evidence support more.

The index builds from `image_metadata.csv` under
`FLOOD_IMAGE_DATA` (default `/home/dell/jupyterlab/Texas_Flood_Student_Data`) and is
cached in `.state/photo-locations.npz`. Build it explicitly with
`python photo_location.py`. Matching and map confirmation do not load model weights
or start training. See `training/PHOTO_LOCATION.md` for validation and limits.

## Photo-to-flood preview

The **Flood preview** view accepts JPEG, PNG and WebP photos. Select a minor,
moderate or severe visual scenario and choose **Generate flooded view**. Atlas v2
describes the original scene; a separate local FLUX.2 Klein 4B image editor
creates the flooded illustration. A slider compares the source photo with the
generated image. Both models stay resident between requests. No training runs.

The same button automatically runs Qwen's review of the generated flood image after generation finishes. Its explanation appears
below the viewer. Info markers on the original photo can be hovered, focused or
tapped for visible evidence and access checks. Slide toward Original to reveal
all annotations. They mark features to verify, not certified safe refuges.
Grounding may use base Qwen with the resident adapter temporarily disabled;
review and image editing still reuse the persistent inference service.
See `training/AUTOMATIC_PHOTO_REVIEW.md` for provenance and limits.

Generated water is an illustration, not a physical inundation model. It does not
establish flood extent, depth, probability, timing, or road passability.

After generation, enter the photo's address or coordinates and choose **Find
nearby options**. JPEG GPS metadata can prefill coordinates; device location is
used only after choosing that button. Always confirm that the location matches
the photo. Coordinates, not the photo, are sent to public map/data services.

Planning combines FEMA shelter listings, terrain elevations and an Atlas v2
assessment restricted to source-backed candidate IDs. Sites without confirmed
current availability are marked as planning locations to contact, not operating
shelters. Higher terrain is not proof of safety. Unknown or unfavorable route
coverage is shown explicitly and does not become a route recommendation.
Shelter listings are U.S.-focused; the existing FEMA/TxDOT route screening is
Texas-only. Outside supported coverage the app reports missing information and
links to official sources rather than inventing destinations. Tall buildings
are not automatically treated as shelters.

Images and job records are stored locally under `.state/scenarios/`. Jobs can be
reopened after refreshing the page. If the app restarts during an active job,
the job is marked interrupted and can be generated again.

The pinned editor model and download path are recorded in
`inference/flood_model.json`. To install its weights on the prepared machine:

```bash
python deployment/install-image-model.py
```

The prepared model environment includes Diffusers 0.40.0 and the existing
Torch/Transformers stack. The API reports image-model installation and loading
status at `/health`. See `training/FLOOD_SCENARIOS.md` for provenance and checks.

## Integrated Atlas v2 system

On the prepared GB10 machine, use `./run-integrated.sh` to start the local app
and the shared inference API together. The existing checkpoint must already
exist; this command never runs training or validation. If port 8765 is occupied,
use `FLOOD_PORT=8766 ./run-integrated.sh`.

The API listens on `127.0.0.1:8001`; both paired timeline analysis and the
photo upload and question tools use Atlas v2. One resident model serves
all requests sequentially. The first request after service startup loads weights;
subsequent requests reuse them, even when a notebook kernel restarts. A service
restart requires another load. `/health` reports checkpoint hash, load count,
request count and readiness. The app caches observations using a model ID that
includes the adapter fingerprint. Changing the adapter requires a service and
app restart, so requests cannot silently change checkpoints.

The service holds the existing exclusive GPU lock and pauses `qwen-vl-server`
while resident. It restores that container on graceful shutdown. Do not run the
older notebook-only worker alongside it; finish its query and call its original
`predict.close_model()` before starting the shared service. Training, if started
separately, must wait until the shared service is stopped.

For a notebook that never owns model weights:

```python
import sys
sys.path.insert(0, "/home/dell/datahon-dell-review")
from inference.client import ask_image

answer = ask_image("/absolute/path/to/image.png", "Is flooding visible? Explain the evidence.")
print(answer)
```

The existing `flood_training/predict.py` helper on this machine is also connected
through `flood_training/inference_service.json`. Reload that helper once when
switching an already-open notebook. `predict.close_model()` only releases an
older private worker; it does not unload the shared service.

Configuration: `FLOOD_TRAINING_HOME` identifies the checkpoint workspace,
`FLOOD_MODEL_PYTHON` the prepared model interpreter, `FLOOD_INFERENCE_PORT`
the local API port, and `FLOOD_PORT` the app port. Standalone API startup is
`<model-python> inference/server.py`. It requires the prepared Torch,
Transformers and PEFT environment described in `training/README.md`.

Atlas JSON is validated by the application after generation. The local API does
not advertise grammar-constrained decoding. Malformed answers fail visibly
rather than becoming observations. Preview resolution is consistently capped at
448 pixels; model evaluation limitations in `training/RESULTS.md` still apply.
The public feeds, routing and recovery calculator keep their existing functions.

### Services on this machine

The integrated app is running at **http://127.0.0.1:8766**, independently of the
older app on port 8765. Per-user services keep the API outside notebook kernels:

```bash
systemctl --user status flood-atlas-inference flood-atlas-app
journalctl --user -u flood-atlas-inference -f
# Restart just the frontend/backend app without unloading model weights:
systemctl --user restart flood-atlas-app
# Release the GPU when finished (stop the app before its inference service):
systemctl --user stop flood-atlas-app flood-atlas-inference
# Start again; weights load on its first question:
systemctl --user start flood-atlas-app
```

To reproduce these service definitions, run
`python3 deployment/install-local-services.py`, then start the app service. This
installer only writes configuration; it does not start inference or training.
Services are not enabled to start automatically at login. The standalone
launcher remains available when these services are stopped.

## Start

On this computer:

```bash
git clone https://github.com/ahaanwanvari/datahon-dell.git
cd datahon-dell
./run.sh
```

Open **http://127.0.0.1:8765**. The launcher uses the existing Jupyter environment unless `.venv` exists. For a separate installation:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh
```

The initial collection contains 16 **synthetic** RGB images and 12 **prewritten** observations at four fictional Texas locations. It demonstrates imagery review and makes no claim about real flood events. The Texas context panel starts at Houston and queries public NOAA NWPS gauges, TxDOT DriveTexas road conditions, and FEMA NFHL mapped flood hazards. A location search can use a Texas place name or coordinates. No Google Maps key is needed. No models are downloaded and no GPU workloads are stopped.

## Texas decision context prototype

The page organizes the concept into four phases: preparation, active-flood response context, responder prioritization, and recovery assessment. Search a Texas city/address or coordinates to inspect nearby source feeds, or use an imported image location. The context panel displays returned gauge readings/flood categories, road reports and mapped flood-zone records where supplied by the services. Route planning geocodes two Texas locations and returns OSRM alternatives with distance, approximate duration and road names. The app samples each returned route against FEMA flood hazard polygons and TxDOT flood/closure reports, then ranks the candidates by screening score. OSRM still generates the candidates and cannot avoid a reported segment when generating new paths; a matched closure is flagged prominently. Manually added facility/check-location notes are stored only in the local browser. A JSON incident brief can combine these notes with the selected imagery collection's observations. A recovery scenario calculator multiplies a user-supplied affected-building count by user-supplied low/high repair-cost assumptions; it is not an image-derived or FEMA loss estimate.

Treat all output as exploratory context. NOAA gauges cover selected waterways, not every street or flash flood. A missing/zero TxDOT record is not proof that a road is open; the feed covers TxDOT-maintained roads, has terms limiting use, and access for the API may require an approved key. FEMA NFHL zones are mapped hazard designations, not live inundation. Route screening uses mapped background hazard and matching TxDOT reports; it does not predict flood depth or prove that remaining roads are passable. Check all conditions against official TxDOT and local emergency sources before travel. Manually entered facilities are unverified, and the app does not infer shelter safety from building height. The scenario calculator is only arithmetic over user-entered assumptions. It is not a damage estimate. Defensible loss estimation requires event-specific flood depth, building inventory/valuation, and a method such as FEMA Hazus; the app does not compute those inputs. For active emergencies follow local emergency management and NWS alerts; this prototype is not a dispatch or evacuation authority.

Geocoding uses OpenStreetMap Nominatim with a Texas query suffix. Route calculation uses the public OSRM demo service. Entered place names/coordinates are sent to those services to geocode and calculate routes; these public demo endpoints have usage policies and are suitable only for low-volume prototyping. Production deployment should host its own routing service or use an approved service with an appropriate agreement. Map imagery and attribution are provided by OpenStreetMap.

The VLM defaults to `Qwen/Qwen3-VL-8B-Instruct` at `http://127.0.0.1:8000/v1`. When running on the GB10, set `FLOOD_VLM_URL` to the GB10 model server address reachable from the app host. The model is only used for historical image-pair descriptions; it does not issue flood forecasts, route people, or estimate damage.

## Import and discover

Prepare comparable RGB PNG/JPEG previews for repeated observations of the same ground footprint. GeoTIFF reprojection, cloud masking, coregistration, sensor normalization, and multispectral band selection must be done upstream. The app does not perform these steps or measure inundation area.

Create a CSV, with image paths relative to its directory:

```csv
location_id,acquisition_date,image_path,latitude,longitude,locality,sensor,source_url,aligned
river-01,2025-05-01,images/before.jpg,29.76,-95.37,River bend,Sentinel-2,,true
river-01,2025-05-08,images/after.jpg,29.76,-95.37,River bend,Sentinel-2,,true
river-01,2025-05-15,images/later.jpg,29.76,-95.37,River bend,Sentinel-2,,true
```

Required: `location_id`, `acquisition_date`, `image_path`, `latitude`, `longitude`. Optional: `locality`, `sensor`, `source_url`, `aligned`. Dates use YYYY-MM-DD. One image per location per day. A location needs at least two dates for a comparison. `aligned=true` is a declaration by the importer, not alignment performed by this app.

1. Open **Manage imagery**, enter the absolute CSV path, and select **Import collection**.
2. Select **Run automatic discovery**. The background worker compares consecutive dates within each location, creates descriptions and source-linked timelines, and saves results to SQLite.
3. Search descriptions, filter dates/change type/relative rarity, select locations on the geographic overview, and swipe between observations. Source links open original provider URLs when supplied; otherwise they open local previews.
4. Select a timeline entry to inspect the exact image pair, dates, evidence description, source IDs, image SHA-256, model identity and limitations. The full location timeline remains visible when search filters identify a matching event.
5. Optionally annotate, confirm, reject or mark an observation unsure. These actions do not gate timeline generation and do not retrain Qwen. Rejected observations are hidden from discovery by default.
6. **Export evidence** downloads JSON containing metadata, observations, review notes, hashes and provenance. It does not bundle image bytes.

Import replaces the entire imported collection and clears its old observations/annotations. Demo data is separate. Re-running discovery without importing preserves cached results and annotations and retries failed pairs. Cache keys include both image hashes, model name and prompt/schema version. If you change weights behind the same model name, change the model name or reimport to invalidate the cache.

## Model connection

Defaults:

- `FLOOD_VLM_URL=http://127.0.0.1:8000/v1`
- `FLOOD_MODEL=Qwen/Qwen3-VL-8B-Instruct`
- `FLOOD_API_KEY=NONE`
- `FLOOD_PORT=8765`
- `FLOOD_STATE=<app directory>/.state`

Override these environment variables before starting. The endpoint must support vision input and JSON-schema structured output. Requests use RGB previews resized to at most 768×768, deterministic sampling and a 180-second response timeout. Each pair runs sequentially so the app does not load a second model or overwhelm the existing server. Failed responses remain visible in job progress and are never converted to fabricated observations. Successful pairs are persisted as the job progresses.

The server binds to loopback, rejects foreign Host headers and cross-origin writes, and uses no external JavaScript/CDN. The geographic overview is a coordinate plot with clickable locations; **Open map** links to OpenStreetMap. Local image URLs are served by registered ID, not arbitrary filesystem paths. This is a single-user local tool, not an authenticated network service. Keep it on loopback.

## Interpretation and present limits

- This uses the pretrained VLM already installed. It does not train a new detector or establish flood-detection accuracy.
- The initial search is word matching over model descriptions, evidence, place names and notes, with a small synonym list. It does not provide embedding-based semantic image retrieval.
- Rarity is the empirical percentile of the model's apparent change magnitude among pairs in the selected collection. It is **not** a calibrated probability, a seasonal anomaly estimate, or proof of a rare flood. With one pair it is zero.
- Observations are generated for every consecutive pair, including stable/uncertain pairs; use the change filter to focus on water increases. The model considers both images, dates, sensor labels and the alignment declaration.
- The timeline reports observation windows. It does not infer an exact onset date, persistence through missing observations, damage, or causation.
- Evidence is described as a region in text and linked to the exact source pair; bounding-box overlays and water segmentation are future additions.
- Indexing thousands of pairs is supported through persistent results, background processing and caching, but throughput and detection accuracy need measurement on representative real data. Jobs are in-process: after a restart, run discovery again to resume from saved pairs.
- Keep source image files unchanged after import. Reimport if files change. Original paths remain in SQLite; exported metadata omits those local paths. Provider URLs remain in exports.

## Validation

```bash
python -m unittest -v test_app test_inference test_scenarios test_photo_location test_scene_analysis test_flood_lookup
```

Tests cover import atomicity, within-location pairing, cache reuse and annotation preservation, failure continuation/retries, and synthetic provenance. Browser checks were also run against desktop and mobile widths for selection, search, empty results, swipe, timeline navigation, annotations and the importer dialog. A live Qwen check uses synthetic imagery solely to validate the connection and output schema; it cannot establish real flood accuracy.

If you move the repository, stop and restart the server with `./run.sh` from the new folder. Demo image paths are repaired on startup. Reimport your manifest if imported source paths have also moved.

## Installed UTSA real imagery

The Hugging Face dataset `jennifer-fowler/UTSA-flood-images` is installed beside this repository in `/home/dell/jupyterlab/Texas_Flood_Student_Data`. The pinned dataset revision is `ad98e681e7cf6af9ced145833b522c4f6c0acad1`.

It has 1,204 **aerial** images: 575 documented Harvey before/after pairs (1,150 images), 50 standalone NOAA Hill Country aftermath images and four standalone USCG images with caption-level locations. Only the 1,200 precisely georeferenced images appear on the coordinate plot. No location is fabricated for the other four. Original acquisition dates, source IDs, pair IDs, agency, attribution, processing notes, bounds and dataset revision are retained with imported images and included in exports. Images awaiting analysis remain browsable. Standalone images do not receive invented comparisons.

The two-date Harvey pairs compare 2016 baselines with 2017 response imagery. A model description of change across that interval is not proof of an exact flood onset, a damage measurement, or a longer recovery history. The original metadata remains in `image_metadata.csv`; the app does not currently query all 273 context fields to support its conclusions.

To reproduce the download and manifest conversion:

```bash
hf download jennifer-fowler/UTSA-flood-images --repo-type dataset \
  --revision ad98e681e7cf6af9ced145833b522c4f6c0acad1 \
  --local-dir /home/dell/jupyterlab/Texas_Flood_Student_Data
python import_utsa.py /home/dell/jupyterlab/Texas_Flood_Student_Data
```

Import the resulting `explorer_manifest.csv` through **Manage imagery**, then run discovery. Imports replace the current imported collection and its annotations. The importer uses only explicit published pairs and verifies reciprocal companion IDs; all other observations remain separate.

## Attribution

Originally developed in the [GB10competition](https://github.com/jennifer-fowler/GB10competition) workspace. Distributed under the GNU GPL v3; see LICENSE. Source imagery retains its original agency and dataset attribution.

## Local model adaptation

See [the model assessment](training/ANALYSIS.md) and [training instructions](training/README.md) for the local Qwen adapter run using labeled FloodNet VQA, UTSA replay and identical-image controls. Checkpoints and evaluation artifacts stay outside the source checkout. Training creates an adapter; the app continues to use its configured `FLOOD_VLM_URL` and `FLOOD_MODEL` until serving is configured separately.
