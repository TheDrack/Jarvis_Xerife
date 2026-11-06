import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');

test('orbital zoom supports close inspection up to 64x', () => {
  assert.match(html, /Math\.min\(64,/);
  assert.match(html, /zoomBy\(1\.2\)/);
  assert.match(html, /zoomBy\(1\/1\.2\)/);
  assert.match(html, /mark\.cluster\?Math\.min\(64,Math\.max\(2\.2,/);
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

test('aircraft route geometry distinguishes filed plans from airport-pair estimates', () => {
  assert.match(html, /origin_latitude/);
  assert.match(html, /destination_latitude/);
  assert.match(html, /setLineDash\(route\.kind==='flight_plan'\?\[6,4\]:\[2,6\]\)/);
  assert.match(html, /drawAircraftRoutes/);
  assert.match(html, /airport_pair_estimate/);
  assert.match(html, /PLANO DE VOO · WAYPOINTS/);
  assert.match(html, /ESTIMATIVA · SOMENTE AEROPORTOS/);
});
test('aircraft observations accumulate a continuous, session-scoped track independently from route estimates', () => {
  assert.match(html, /const aircraftTracks=new Map\(\)/);
  assert.match(html, /appendAircraftTrack\(aircraftTracks,o/);
  assert.match(html, /rgba\(126,240,200/);
  assert.match(html, /LINHA CONTÍNUA · POSIÇÕES OBSERVADAS PELO JARVIS NESTA SESSÃO/);
  assert.match(html, /timestamp-segment\[segment\.length-1\]\.timestamp>300000/);
});
test('aircraft route lookups are cached and failed callsigns are retried instead of being permanently suppressed', () => {
  assert.match(html, /const aircraftRouteCache=new Map\(\)/);
  assert.match(html, /10\*60000/);
  assert.match(html, /routeRetryAt/);
  assert.match(html, /missing_ident/);
});
test('aircraft selection links to FlightAware without scraping or requiring its paid API', () => {
  assert.match(html, /https:\/\/pt\.flightaware\.com\/live\/flight\//);
  assert.match(html, /FLIGHTAWARE · ABRIR VOO/);
  assert.doesNotMatch(html, /aeroapi\.flightaware\.com/);
});

test('selection exposes origin, destination and reverse-geocode precision', () => {
  assert.match(html, /addFact\('DESTINO',attributes\.destination\|\|mark\.flightRoute&&mark\.flightRoute\.destination\.ident\)/);
  assert.match(html, /addFact\('ORIGEM',attributes\.origin\|\|mark\.flightRoute&&mark\.flightRoute\.origin\.ident\)/);
  assert.match(html, /PRECIS/);
});
test('aircraft routes render airport endpoints as well as the great-circle line', () => {
  assert.ok(html.includes('for(const endpoint of [route.origin,route.destination])'));
  assert.ok(html.includes('fillText(code.slice(0,18)'));
});
test('orbital inline script remains syntactically valid after aircraft-layer changes', () => {
  const scripts = html.split('<script>').slice(1).map((script) => script.split('</script>')[0]);
  assert.equal(scripts.length, 1);
  assert.doesNotThrow(() => new Function(scripts[0]));
});
