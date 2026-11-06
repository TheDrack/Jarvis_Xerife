import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');

test('orbital zoom supports close inspection beyond the former 2.4x ceiling', () => {
  assert.match(html, /Math\.min\(3\.6,/);
  assert.match(html, /zoomBy\(1\.2\)/);
  assert.match(html, /zoomBy\(1\/1\.2\)/);
});

test('HUD typography and globe controls are more legible', () => {
  assert.match(html, /--fs-2xs:9px;--fs-xs:10px;--fs-sm:11px/);
  assert.match(html, /globe-tools button\{width:30px;height:30px/);
});

test('orbital observation list uses reverse-geocoded labels when cached', () => {
  assert.match(html, /Globe\.placeFor\(o\.position\.latitude,o\.position\.longitude\)/);
  assert.match(html, /cachedPlace&&cachedPlace\.label/);
  assert.match(html, /toFixed\(3\)/);
});

test('aircraft route is conditional on valid endpoints and uses dashed great-circle geometry', () => {
  assert.match(html, /origin_latitude/);
  assert.match(html, /destination_latitude/);
  assert.match(html, /setLineDash\(\[3,5\]\)/);
  assert.match(html, /drawAircraftRoutes/);
  assert.match(html, /ROTA/);
});

test('selection exposes origin, destination and reverse-geocode precision', () => {
  assert.match(html, /addFact\('DESTINO',attributes\.destination\)/);
  assert.match(html, /addFact\('ORIGEM',attributes\.origin\)/);
  assert.match(html, /PRECIS/);
});
