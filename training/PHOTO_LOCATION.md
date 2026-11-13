# Photo matching and confirmed map origin

## Scope

This implementation identifies registered UTSA images, not arbitrary places in
worldwide photographs. Original file hashes and canonical RGB pixel hashes can
establish exact dataset matches. A perceptual-hash/color descriptor comparison
can suggest resized or recompressed copies. It is not a trained geographic
recognition model, and its scores are not calibrated probabilities. Different
viewpoints, substantial crops, changed seasons and generic lookalike scenes may
remain unmatched. Unknown photos require GPS or an explicit location input.

The machine index contains 1,200 photos with usable coordinates from the dataset
metadata CSV. Source bytes are verified against supplied hashes when building
the index. The index is derived data in `.state/photo-locations.npz`; images and
index weights are not added to Git. `FLOOD_IMAGE_DATA` selects another installed
copy of the dataset. A changed metadata file invalidates the cached index.

## Location semantics

Aerial-image coordinates are usually the ground-footprint center, not the exact
camera position or a particular building. The suggested center, metadata source,
reference thumbnail and footprint are shown for confirmation. The original
uploaded photo is matched; generated flood imagery is never used to locate it.

Duplicate image content registered at different coordinates is ambiguous and
cannot silently choose one. Visual candidates are labeled suggestions. The
user can move the map pin or resolve an address, then must explicitly confirm it.
GPS and current-device locations also require map confirmation.

The API saves confirmed coordinates and timestamps. Destination lookup rejects
unconfirmed scenarios, and its origin comes exclusively from the saved pin,
rather than an arbitrary location in the request body. Changing or re-resolving
a location invalidates prior confirmation and destination results.

Map tiles are displayed directly from OpenStreetMap with visible attribution;
only displayed tiles are requested, without prefetching or offline bulk caching.
Photo bytes remain local. Map/tile and geocoding services receive location data.

## Checks

- 25 application/API/scenario/location unit tests passed.
- Unit cases cover exact files, unchanged pixels in a different encoding,
  resized JPEG copies, unrelated photos, ambiguous duplicate registrations,
  reference-path validation, invalid coordinates, required confirmation and
  clearing results after a changed pin.
- Twenty sampled real dataset images, resized to a maximum of 384 px and saved
  as quality-45 JPEGs, all matched their expected registered image. This small
  copy-transformation smoke test is not a benchmark for arbitrary geolocation
  or a false-positive-rate estimate.
- Matching uses CPU descriptors. The inference API and model weights are not
  modified, restarted or trained for this feature.

Machine-local evidence:
`/home/dell/jupyterlab/flood_training/runs/atlas-v2/photo_location_check.json`
and `photo_location_browser_check.json`.

Live browser verification also passed for an existing photo's content match,
reference thumbnail, map-pin movement, explicit confirmation, invalidation after
address edits, and destination lookup using the persisted pin. A new original
UTSA upload automatically matched `TX001_2016_NAIP`, displayed its footprint and
confirmation map, and kept destination lookup disabled pending confirmation.
Desktop map rendering and mobile-width layout were checked. Both resident
models retained a load count of one throughout deployment and these checks.
