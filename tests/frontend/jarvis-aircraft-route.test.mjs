import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');

test('visible aircraft routes are prefetched with a bounded queue and selection priority', () => {
  assert.match(html, /function enrichVisibleAircraftRoutes\(visibleMarks\)/);
  assert.match(html, /AIRCRAFT_ROUTE_QUEUE_LIMIT=18/);
  assert.match(html, /AIRCRAFT_ROUTE_BATCH_LIMIT=6/);
  assert.match(html, /enrichVisibleAircraftRoutes\(visible\.map\(item=>item\.m\)\)/);
  assert.match(html, /routeBudget=Math\.min\(36/);
});

test('selected aircraft can still request its route on demand', () => {
  assert.match(html, /function enrichAircraftRoute\(mark\)/);
  assert.match(html, /api\('\/api\/intelligence\/aircraft-route\?callsign=/);
  assert.match(html, /mark\.flightRoute=/);
});

test('selected aircraft exposes route status and airport labels', () => {
  assert.match(html, /ORIGEM/);
  assert.match(html, /DESTINO/);
  assert.match(html, /ROTA/);
  assert.match(html, /origin\.latitude/);
  assert.match(html, /destination\.latitude/);
  assert.match(html, /ARCO GEODÉSICO/);
  assert.match(html, /ASSOCIAÇÃO POR CALLSIGN/);
  assert.match(html, /selection-facts-section/);
  assert.match(html, /PROVENIÊNCIA/);
  assert.match(html, /LOCALIZAÇÃO/);
});
