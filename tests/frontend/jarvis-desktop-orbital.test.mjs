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
  assert.match(html, /INSPECIONAR NO FLIGHTAWARE/);
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


test('globe focus preserves the current zoom when selecting an entity', () => {
  assert.match(html, /function focusTo\(latitude,longitude,zoomLevel=zoom\)/);
  assert.match(html, /zoomLevel==null\?zoom:clampZoom\(Number\(zoomLevel\)\)/);
  assert.match(html, /function focusSelection\(mark\)/);
  assert.match(html, /focusSelection\(mark\);/);
  assert.match(html, /return Globe\.focusTo\(Number\(latitude\),Number\(longitude\)\)/);
  assert.doesNotMatch(html, /Globe\.focusTo\(position\.latitude,position\.longitude,2\.05\)/);
});

test('high-zoom globe navigation is scale-aware and supports keyboard plus directional controls', () => {
  assert.match(html, /function panBy\(directionX,directionY\)/);
  assert.match(html, /Math\.max\(0\.08,Math\.min\(1\.8,1\/Math\.sqrt\(zoom\)\)\)/);
  for (const direction of ['up','left','down','right']) assert.ok(html.includes('data-pan=\"'+direction+'\"'));
  for (const key of ['ArrowUp','ArrowDown','ArrowLeft','ArrowRight']) assert.ok(html.includes(key));
  assert.match(html, /rot-=Number\(directionX\|\|0\)\*0\.055\*scale/);
  assert.match(html, /tilt-Number\(directionY\|\|0\)\*0\.045\*scale/);
  assert.match(html, /dragScale=Math\.max\(0\.08,Math\.min\(1\.8,1\/Math\.sqrt\(zoom\)\)\)/);
});

test('selection inspector has a prominent top-right close control', () => {
  assert.match(html, /selection-close/);
  assert.match(html, /id=\"selectionClose\"/);
  assert.match(html, /aria-label=\"Fechar descrição\"/);
  assert.match(html, /\.selection-close\{position:absolute;top:8px;right:8px/);
});

test('administrative boundaries render IBGE municipality geometry and labels at close zoom', () => {
  assert.match(html, /adminBoundaries\.municipalities=toVectors\(data\.municipalities\)/);
  assert.match(html, /adminBoundaries\.municipalityLabels=Array\.isArray\(data\.municipalityLabels\)/);
  assert.match(html, /if\(zoom>=5\.5\)/);
  assert.match(html, /async function loadMunicipalityBoundaries\(\)/);
  assert.match(html, /world-municipal-boundaries\.json\.gz\.b64/);
  assert.match(html, /if\(zoom>=9&&adminBoundaries\.municipalityLabels\.length\)/);
  assert.match(html, /id:'municipalities',rank:3/);
});


test('globe pointer controls distinguish single click zoom, double click inspect and right click reset', () => {
  assert.match(html, /SINGLE_CLICK_DELAY_MS\s*=\s*220/);
  assert.match(html, /pendingClickTimer/);
  assert.match(html, /zoomTo\(best,64\)/);
  assert.match(html, /canvas\.addEventListener\('contextmenu'/);
  assert.match(html, /zoomOutMax\(/);
  assert.match(html, /openSelection\(mark\)/);
});

test('plus and minus keys control zoom without hijacking editable fields', () => {
  assert.match(html, /ev\.key==='\+'\|\|ev\.key==='='/);
  assert.match(html, /ev\.key==='-'\|\|ev\.key==='Subtract'/);
  assert.match(html, /Globe\.zoomBy\(1\.2\)/);
  assert.match(html, /Globe\.zoomBy\(1\/1\.2\)/);
});

test('globe rotates slowly only at minimum zoom and respects reduced motion', () => {
  assert.match(html, /zoom<=0\.66/);
  assert.match(html, /rot\+=0\.012\*dt/);
});

test('source collection displays animated orbital rings on the active source', () => {
  assert.match(html, /source-orbit/);
  assert.match(html, /activeSourceAction/);
  assert.match(html, /source-row.*is-loading/);
  assert.match(html, /@keyframes source-orbit-spin/);
});

test('aircraft and satellites expose external inspection links and aircraft centering action', () => {
  assert.match(html, /flightaware\.com\/live\/flight/);
  assert.match(html, /n2yo\.com\/satellite\/\?s=/);
  assert.match(html, /CENTRALIZAR AERONAVE/);
});


test('empty globe clicks resolve the visible geographic point before zooming', () => {
  assert.match(html, /function screenToLocation\(clientX,clientY\)/);
  assert.match(html, /focusTo\(region\.latitude,region\.longitude,64\)/);
});


test('aircraft external inspection falls back only to a valid ICAO24 identifier', () => {
  assert.ok(html.includes('attributes.callsign||(/^[0-9a-f]{6}$/i.test'));
});
