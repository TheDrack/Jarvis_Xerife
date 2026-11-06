# Geospatial scale model

## Objective

The orbital globe uses the visible geographic scale to choose which administrative boundaries are useful. The selected layer is based on spatial area, not on the administrative label alone. A large metropolitan area can therefore occupy the same visual tier as a small province or state.

## Current implementation

- Orbital zoom maximum: 24x.
- Device marker budget grows with zoom and is capped at 6,000 markers.
- Country boundaries: Natural Earth admin-0 land boundary lines, 1:50m.
- State/province boundaries: Natural Earth admin-1 boundary lines, 1:10m, for a broad set of large countries including Brazil. Other countries currently fall back to country borders.
- The compact runtime dataset is `app/static/world-admin-boundaries.json.gz.b64`.
- The globe keeps the current continental appearance below the country-boundary threshold; country lines appear after zooming in, and state/province lines are selected at a finer spatial scale.
- Boundary-layer selection compares the estimated visible area with each layer's mean feature area. It does not hard-code "city" as always smaller than "state".

## Point enrichment and aircraft routes

- Visible globe points are reverse-geocoded in a bounded queue.
- The queue is rate-limited by the existing local geocoding endpoint, reuses the browser cache, and prioritizes higher-value visible markers.
- Pending lookups are deduplicated by coordinate and fan the resolved result out to every marker instance sharing that coordinate. Cluster labels are generalized from the cached raw administrative fields of their member coordinates; they no longer discard the enrichment and fall back to a generic region label.
- The cache key was versioned so entries created before raw administrative fields were retained do not mask the new zoom-aware labels.
- Aircraft route lookups are queued for visible aircraft, bounded, and rate-spaced. The renderer draws the great-circle arc and the origin/destination airport markers, with selected aircraft prioritized.
- Route lookup uses the local loopback GEV REST endpoint independently of the optional GEV MCP observation connector. The observation feed still requires its configured MCP entrypoint and bounded area; a missing MCP connector must not disable route lookup when the local REST service is running.
- A missing route is reported as unavailable/not found; it is never inferred from the aircraft's current position.

## Data provenance

The static country/state boundary bundle is derived from Natural Earth Vector:
- Admin-0 land boundaries (1:50m)
- Admin-1 state/province boundaries (1:10m) for selected countries; it is not a complete global ADM1 coverage

Natural Earth data is public domain. The bundle retains the attribution string: "Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com".

## Next administrative tiers

Natural Earth is not a global municipal/neighbourhood boundary source. City, district, municipality and neighbourhood contours require a separate regional data path:

1. Resolve the country and administrative context for the current viewport.
2. Request only the relevant local ADM2+ boundaries from geoBoundaries (gbOpen) or an OSM administrative-boundary relation source.
3. Validate geometry, source year, license and attribution before caching.
4. Simplify geometry to the current display scale and load only the viewport's region.
5. Select the layer by feature area and visible area, so a large city and a small state can occupy comparable visual scales.

The current static ADM1 bundle covers selected countries, not every country. geoBoundaries coverage and ADM levels vary by country; neighbourhood boundaries are not globally standardized. Missing local boundary data must fall back to the next available administrative layer, never to a fabricated outline.