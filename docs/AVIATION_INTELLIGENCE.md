# Jarvis Aviation Intelligence

## Geometry contract

The orbital layer keeps three geometries separate:

- `observed_track`: ordered aircraft positions received by Jarvis during the current browser session. Rendered as a continuous line. It is not a complete provider history and is not persisted across reloads.
- `flight_plan`: provider-supplied filed route with at least two validated waypoints. Rendered as a blue dashed line. Only this geometry may be described as a filed route.
- `airport_pair_estimate`: origin/destination airport coordinates associated with a callsign, without waypoints. Rendered as an amber dotted great-circle arc. It is an estimate, not an ATC route or observed trajectory.

Missing route data never creates synthetic geometry.

## Identity and collection

Aircraft identity resolution prefers ICAO24, then registration, then normalized callsign. Callsign is used for the current GEV/ADS-BDB route lookup. Route results are cached per aircraft identity and UTC observation day; negative lookups expire and can be retried. Requests are bounded and queued.

Observed positions are deduplicated, timestamp-sorted, limited to 240 points per aircraft and two hours in the browser session. A gap over five minutes breaks the rendered line to avoid implying continuous surveillance.

## Sources and licensing

- Current route enrichment uses the local God's Eye View REST endpoint `/api/adsbdb/route/{callsign}`. Its current response supplies origin and destination airports only; therefore it is always classified as `airport_pair_estimate`.
- Live positions and aircraft metadata remain sourced from the configured GEV/OSIRIS observation providers. Their fields are shown only when present and their source provenance is retained.
- Selecting an aircraft exposes its FlightAware flight page as an external reference. Jarvis does not scrape FlightAware pages.
- FlightAware AeroAPI exposes richer flight, track and filed-route endpoints, but it is usage-priced. No AeroAPI calls or credential requirements are enabled by this change. A future integration must be explicitly enabled, queried only on user selection, rate-limited, cached, and show its estimated cost/provenance.

## UI semantics

- Continuous mint line: positions observed by Jarvis in this session.
- Blue dashed line: provider-supplied filed route/waypoints.
- Amber dotted line: estimated great-circle connection between airports.
- The aircraft inspector separates callsign, ICAO24, registration, aircraft type, altitude, speed, heading, squawk, route status, route provider, and session-track coverage when available.

## Verification limits

The local GEV route endpoint was probed with callsign `GLO1235` and returned Recife (REC) to São Paulo (CGH). This verifies the airport-pair lookup only; it does not verify the actual flight plan, current aircraft position, or historical track for that flight.
