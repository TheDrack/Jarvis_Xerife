import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');

test('reverse geocoding is requested for the selected point, not every observation', () => {
  assert.doesNotMatch(html, /enrichPlaces\(\);/);
  assert.match(html, /function enrichPlace\(mark\)/);
  assert.match(html, /enrichPlace\(mark\)/);
});

test('reverse-geocode cache precision is sufficient to distinguish nearby street addresses', () => {
  assert.match(html, /function placeKey\(latitude,longitude\)[\s\S]{0,180}toFixed\(4\)/);
});

test('transient geocoding failures are not stored as permanent missing-place results', () => {
  assert.match(html, /retry_after_seconds/);
  assert.match(html, /PLACE_RETRY_AFTER/);
  assert.match(html, /isTransientPlaceFailure/);
});
