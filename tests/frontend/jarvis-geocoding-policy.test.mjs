import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');

test('reverse geocoding prioritizes visible points and selected cluster centers', () => {
  assert.doesNotMatch(html, /enrichPlaces\(\);/);
  assert.match(html, /function enrichPlace\(mark\)/);
  assert.match(html, /enrichPlace\(mark\)/);
  assert.match(html, /regionZoom:isCluster\?Number\(mark\.zoomLevel\)\|\|1:null/);
});

test('cluster reverse geocoding uses a generalized administrative label, not a member address', () => {
  assert.match(html, /regional_reverse_geocode/);
  assert.match(html, /generalizeRegion\(\[data\],group\.regionZoom\)/);
  assert.match(html, /address:group\.regionZoom!==null\?label/);
  assert.match(html, /rawAddress:data\.address/);
  assert.match(html, /generalizeRegion\(\[\{address:entry\.rawAddress\}\],Number\(mark\.zoomLevel\)\|\|1\)/);
  assert.match(html, /const cachedPlace=Globe\.placeFor\?Globe\.placeFor\(latitude,longitude\):null/);
});

test('reverse-geocode cache precision is sufficient to distinguish nearby street addresses', () => {
  assert.match(html, /function placeKey\(latitude,longitude\)[\s\S]{0,180}toFixed\(4\)/);
});

test('transient geocoding failures are not stored as permanent missing-place results', () => {
  assert.match(html, /retry_after_seconds/);
  assert.match(html, /PLACE_RETRY_AFTER/);
  assert.match(html, /isTransientPlaceFailure/);
});
test('visible point geocoding remains bounded and reuses cached coordinates', () => {
  assert.ok(html.includes("const PLACE_CACHE_KEY='jarvis_globe_places_v3';"));
  assert.ok(html.includes('const PLACE_VISIBLE_QUEUE_LIMIT=48;'));
  assert.ok(html.includes('enrichVisiblePlaces(visible.map(item=>item.m))'));
  assert.ok(html.includes('const PLACE_VISIBLE_SCAN_INTERVAL_MS=750;'));
  assert.ok(html.includes('const cached=placeCache.get(key);'));
  assert.match(html, /PLACE_RETRY_AFTER/);
});

test('deduplicated reverse-geocode requests fan results out to all marker instances sharing coordinates', () => {
  assert.match(html, /placeQueueByKey=new Map\(\)/);
  assert.match(html, /const pending=placeQueueByKey\.get\(key\)/);
  assert.match(html, /pending\.marks\.push\(mark\)/);
  assert.match(html, /group\.marks\.forEach\(mark=>applyPlace\(mark,entry\)\)/);
  assert.match(html, /placeQueueByKey\.delete\(group\.key\)/);
});

test('cluster labels are derived from cached reverse-geocoded member coordinates', () => {
  assert.match(html, /generalizeRegionFromMembers\(members,zoom,placeFor\)/);
});
