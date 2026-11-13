# Local flood illustrations and location planning

This feature changes the app from image description alone to a reference-photo
editing workflow. It does not train an image generator or a flood simulator.

## Models

- Atlas v2: existing Qwen3-VL-8B adapter, describes the scene and assesses supplied
  planning-site facts. Its prior flood classification metrics do not validate
  generative flood realism, geography or evacuation decisions.
- Editor: `black-forest-labs/FLUX.2-klein-4B`, revision
  `e7b7dc27f91deacad38e78976d1f2b499d76a294`, Apache 2.0. Uses reference-image
  editing with four distilled inference steps, guidance 1.0, bfloat16 and a
  maximum output side of 768 px. The prompt preserves perspective and landmarks
  while depicting a selected qualitative flood scenario. No measured water
  level or physical flood extent is inferred.

Both share one GPU owner and serialized inference inside the resident API.
There is no call to a training or validation entry point. Model downloads are
separate from request handling and never silently retrigger on a user question.

## Location planning

Image EXIF GPS or an explicitly supplied address/coordinate locates the photo.
Model-recognized landmarks do not establish an address. Current device location
is optional and must be confirmed as the photo location.

FEMA provides shelter inventory/listing records. Inventory membership does not
establish that a site is open, accessible or suitable for a particular flood.
Open-Meteo/Copernicus terrain elevations use approximately 90 m cells, not
building heights. A three-metre positive elevation difference is a planning
filter, not an inundation boundary or safety threshold. Known floodplain/surge
flags exclude sites from model selection; unknown flags remain explicit.
The model can choose only IDs from the server-provided planning shortlist.
Its reasons are displayed as a planning assessment, not an evacuation order.

The existing Texas route service samples FEMA polygons and TxDOT reports.
Unknown coverage and reported hazards do not become a positive route result.
The generated water image is never used to infer flooded roads, real-world
coordinates or route clearance. Absence of a matched hazard does not establish
passability. Supported public-data coverage is explicit in each result.

## Persistence and failure behavior

Local `.state/scenarios/<id>/` folders hold original/generated images and atomic
JSON job records, including model provenance and prompt. IDs are validated before
filesystem access. Generation failures produce a failed job, not a fabricated
image. In-progress jobs are marked interrupted after an app restart. Uploads are
not used for training. External data services receive coordinates; photos stay
on this machine.

## Sources

- Editor: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
- FEMA shelter services: https://gis.fema.gov/arcgis/rest/services/NSS/FEMA_NSS/MapServer
- Terrain/API attribution: https://open-meteo.com/en/docs/elevation-api
- Geocoding: https://nominatim.org/release-docs/latest/api/Search/
- Flood guidance: https://www.weather.gov/safety/flood-during

Verification results are recorded after the live image-edit smoke test. The unit
suite checks unsupported model-selected destinations, missing terrain data,
interrupted jobs, path traversal and generation failure without fake output.

## Live verification — November 13, 2026

- Downloaded all required editor components at the pinned revision using `hf`.
- Passed 19 application/API/scenario unit tests and syntax/whitespace checks.
- Submitted a real unflooded UTSA aerial photo through `/api/scenarios` and
  inspected the generated PNG. Major roads, houses and tree positions remained
  recognizable, with model-generated floodwater added. This is qualitative
  inspection, not validation of a physical flood scenario.
- First editor request: 123.47 s, including initial editor loading. Second
  request through the real browser file picker: 16.03 s. Both models reported
  one model load each after two generated outputs. Timings depend on the photo
  and machine state.
- Browser checks covered upload validation, slider clipping, persisted-job
  restoration, destination form submission, and clearing the previous photo's
  location on a new upload. Mobile-width layout checks passed.
- The destination check exercised public-data failures: unavailable FEMA and
  terrain responses remained explicit, and the app did not invent a destination.
  A separate live source query returned actual FEMA shelter inventory records.
- Source caching uses ten minutes for shelter responses and one day for terrain
  responses; cached retrieval timestamps remain available. Failed shelter
  requests are retried against the corresponding official FeatureServer URL.
  Expired cache records do not become fabricated fresh observations.

Sample generated output and its exact saved prompt/provenance:

- `/home/dell/datahon-dell-review/.state/scenarios/ded3f7dc37814528895ad5e7c08d6077/generated.png`
- `/home/dell/datahon-dell-review/.state/scenarios/ded3f7dc37814528895ad5e7c08d6077/job.json`

Detailed machine-local smoke-test evidence is in
`/home/dell/jupyterlab/flood_training/runs/atlas-v2/flood_scenario_check.json`,
`flood_scenario_browser_check.json`, and `flood_destination_check.json`.
The implementation uses local Diffusers/FLUX inference, selected explicitly by
the user, rather than a hosted image-generation API. Adapter weights and
training/validation processes were not modified or restarted.

The final retry with caching enabled returned five real shelter-inventory sites
and complete terrain elevations without source errors. For the test origin
(15 m terrain elevation), shortlisted sites were between 9 and 15 m: none met
the higher-terrain planning filter. The model correctly returned a null choice.
This verifies source handling and abstention, not successful evacuation routing.

## Coordinate lookup performance update

Shelter feeds run concurrently with bounded source timeouts. Nearby pins share
a rounded query-area cache while distances retain the exact confirmed origin.
Open-listing responses cache for ten minutes; static inventory and terrain cache
for one day, with source retrieval timestamps retained. Duplicate retries to the
same elevation endpoint are removed. Candidate records are published before
terrain/access/model work, with progress visible on the page. Route screening
has a four-second completion budget and timed-out routes remain unverified.
Qwen ranking is skipped when there are no eligible destinations and has a six-
second HTTP read timeout otherwise. These changes do not promote unknown safety
evidence.

An interrupted destination lookup preserves the generated preview and permits
retry. Repeated lookup clears previous results before publishing new ones.

Live manually entered coordinate flow (`29.84302629, -95.63873291`) resolved
and confirmed the map pin immediately, then returned five source-backed records
in 8.07 seconds. The same flow took 15.98 seconds before shortening route and
model waits. A separate cached confirmed-coordinate check took 4.12 seconds,
then 0.16 seconds from cache. These are measured examples, not latency
guarantees.
Evidence: `destination_speed_check.json` and `destination_api_speed_check.json`
under `/home/dell/jupyterlab/flood_training/runs/atlas-v2/`. All 35 current tests
passed, including concurrent feeds, early partial results, skipping empty model
ranking and interrupted-lookup recovery. Only the website process was restarted;
the model service and training/validation processes were left running.
