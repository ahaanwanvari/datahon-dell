# Texas Flood Atlas

Local Texas-focused flood decision-support prototype. It combines dated satellite-image change discovery with nearby public gauge, road-condition, and mapped flood-hazard context. Qwen runs on your existing GB10 model server. Human review is optional.

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
python -m unittest -v test_app
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
