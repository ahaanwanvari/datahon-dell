# Automatic photo review and image annotations

Generate flooded view now runs a persisted Qwen review and the flood image edit
in one job. The edit finishes first; both Qwen review and fallback grounding receive
the saved generated.png, with basis generated_flood_image and its image URL recorded. The full structured review appears directly below the comparison,
followed by optional questions and confirmed-location destination lookup.

Atlas v2 produces the scene summary, flood implications and limitations.
When the adapter cannot provide supported annotation positions, a separate
object-localization request uses the original Qwen3-VL-8B weights with the LoRA
adapter temporarily disabled. This reuses resident base weights; it does not
load another Qwen model or run training. The GPU request lock covers the adapter
context, whose exit restores the adapter before another request can run.
Responses and saved analysis distinguish adapter review from base-model grounding.

Annotations refer only to the generated flood image and are clipped with its half of
the slider. Their positions are model estimates. Hover, keyboard focus or tap
opens details; Escape or the close control dismisses them. Details include
visible evidence, relevance, and access checks. A button leads to the existing
confirmed-location and mapped-access workflow. Touch and keyboard operation are
supported alongside hover, and explanatory text remains readable below the image.

A marked roof or building is not a verified shelter or high ground. The app does
not label a spot safe or produce turn-by-turn evacuation instructions from a
photo or generated floodwater. Model-estimated positions, missing information,
unsafe/unknown access and the difference between visual evidence and real-world
navigation remain explicit. If no feature can be grounded, no marker is invented.

Coordinates must be finite and in range. Grounding boxes must have positive area
within the generated image; placeholders and invalid categories are dropped.
Image-only output cannot set `verified_safe` true. Analysis failures remain
visible and do not silently turn generated pixels into safety evidence.

The optional follow-up question form is now adjacent to the automatic review,
rather than requiring a separate action to obtain the first explanation.
Existing previews without review data say so and require a new generation to
include this feature. Model weights and training/validation runs are unchanged.

Safety reference: https://www.weather.gov/safety/flood-during

## Verification — November 13, 2026

- 31 application/API/scenario/location/analysis unit tests passed.
- Validation checks include finite normalized points, invalid categories,
  zero-area grounding boxes, explicit non-certification, and base-response
  provenance when the adapter is disabled.
- A real unflooded UTSA photo produced a persisted explanation and two grounded
  building markers with model estimates near visible structures. Marker placement
  was visually inspected. These checks do not validate refuge suitability.
- Real browser checks passed for automatic explanation placement, hover details,
  keyboard focus/Escape, mobile click access, and another Generate click running
  both tasks without a separate question submission.
- The warmed combined browser run took 38.73 seconds. Both resident models
  retained a model-load count of one. The first run after the inference-service
  update included initial weight loading; timing is not a general guarantee.
- The original photo is the only annotation basis; markers do not certify the
  generated illustration, select a safe roof, or invent a passable route.

Machine-local evidence is saved under
`/home/dell/jupyterlab/flood_training/runs/atlas-v2/automatic_analysis_check.json`
and `automatic_analysis_browser_check.json`. Scenario
`152ce7afd542413f937166477b3531f6` contains the inspected original/preview and full
analysis record. No training or validation loop was restarted.
