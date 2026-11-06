import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
import '../../app/static/jarvis-geospatial-layer.js';

const { buildDeviceMarkers, clusterScreenPoints, clusterThresholdForZoom, generalizeRegion, generalizeRegionFromMembers } = globalThis.JarvisGeospatialLayer;

const asset = (id, latitude, longitude, status = 'online', place = {}) => ({
  id, name: `Device ${id}`, latitude, longitude, located: true, status, place,
});

test('screen-space cluster radius contracts with orbital zoom', () => {
  const thresholds = [0.75, 1, 2, 4, 16, 64].map(clusterThresholdForZoom);
  assert.deepEqual(thresholds, [26 / Math.sqrt(0.75), 26, 26 / Math.sqrt(2), 13, 8, 8]);
});

test('screen-space clustering merges nearby points and separates them as zoom increases', () => {
  const points = [
    { sx: 100, sy: 100, m: { kind: 'device', id: 'a' }, color: '#fff' },
    { sx: 118, sy: 104, m: { kind: 'device', id: 'b' }, color: '#fff' },
  ];
  const globalClusters = clusterScreenPoints(points, clusterThresholdForZoom(1));
  const streetClusters = clusterScreenPoints(points, clusterThresholdForZoom(64));
  assert.equal(globalClusters.length, 1);
  assert.equal(globalClusters[0].items.length, 2);
  assert.equal(streetClusters.length, 2);
});

test('screen-space clusters preserve category boundaries and every member identity', () => {
  const points = [
    { sx: 100, sy: 100, m: { kind: 'device', id: 'device-1' } },
    { sx: 101, sy: 101, m: { kind: 'device', id: 'device-2' } },
    { sx: 100, sy: 100, m: { kind: 'camera', id: 'camera-1' } },
    { sx: 101, sy: 101, m: { kind: 'camera', id: 'camera-2' } },
  ];
  const clusters = clusterScreenPoints(points, 26);
  assert.equal(clusters.length, 2);
  assert.deepEqual(clusters.map((cluster) => cluster.items.map((item) => item.m.id)), [
    ['device-1', 'device-2'],
    ['camera-1', 'camera-2'],
  ]);
});

test('screen-space clustering reindexes moving centroids across neighboring cells', () => {
  const points = [
    { sx: 24, sy: 20, m: { kind: 'aircraft', id: 'a' } },
    { sx: 44, sy: 20, m: { kind: 'aircraft', id: 'b' } },
    { sx: 54, sy: 20, m: { kind: 'aircraft', id: 'c' } },
  ];
  const clusters = clusterScreenPoints(points, 26);
  assert.equal(clusters.length, 1);
  assert.deepEqual(clusters[0].items.map((item) => item.m.id), ['a', 'b', 'c']);
});

test('regional clusters generalize their place label to one administrative level', () => {
  const members = [
    asset(1, -23.55, -46.63, 'online', { city: 'São Paulo', state: 'São Paulo', country: 'Brasil', neighbourhood: 'Sé' }),
    asset(2, -23.56, -46.64, 'online', { city: 'São Paulo', state: 'São Paulo', country: 'Brasil', neighbourhood: 'República' }),
  ];
  assert.equal(generalizeRegion(members, 1), 'Brasil');
  assert.equal(generalizeRegion(members, 1.45), 'São Paulo · Brasil');
  assert.equal(generalizeRegion(members, 2.05), 'São Paulo · São Paulo · Brasil');
  assert.equal(generalizeRegion(members, 4.5), 'São Paulo · São Paulo · Brasil');
});

test('regional reverse-geocode address data is generalized at the cluster zoom level', () => {
  const reverseGeocode = { address: { country: 'Brasil', state: 'São Paulo', city: 'São Paulo', suburb: 'Sé', road: 'Praça da Sé', house_number: '1' } };
  assert.equal(generalizeRegion([reverseGeocode], 1), 'Brasil');
  assert.equal(generalizeRegion([reverseGeocode], 1.45), 'São Paulo · Brasil');
  assert.equal(generalizeRegion([reverseGeocode], 2.05), 'São Paulo · São Paulo · Brasil');
  assert.equal(generalizeRegion([reverseGeocode], 4.5), 'Sé · São Paulo · São Paulo · Brasil');
});

test('cluster generalization resolves the common ancestor from each member cache entry', () => {
  const members = [
    { latitude: -23.55, longitude: -46.63, record: { id: 'a' } },
    { latitude: -23.56, longitude: -46.64, record: { id: 'b' } },
  ];
  const lookupPlace = (latitude, longitude) => ({
    rawAddress: {
      country: 'Brasil',
      state: 'São Paulo',
      city: latitude < -23.555 ? 'Santos' : 'São Paulo',
      suburb: latitude < -23.555 ? 'Gonzaga' : 'Sé',
      road: 'Rua específica',
    },
  });
  assert.equal(generalizeRegionFromMembers(members, 64, lookupPlace), 'São Paulo · Brasil');
});

test('screen-space clustering preserves all members in a dense viewport-sized inventory', () => {
  const points = Array.from({ length: 5000 }, (_, index) => ({
    sx: (index % 100) * 5,
    sy: Math.floor(index / 100) * 5,
    m: { kind: index % 2 ? 'device' : 'camera', id: index },
  }));
  const clusters = clusterScreenPoints(points, 26);
  assert.ok(clusters.length < points.length);
  assert.equal(clusters.reduce((total, cluster) => total + cluster.items.length, 0), points.length);
});

test('device markers remain individual until the shared screen-space renderer clusters them', () => {
  const nearby = Array.from({ length: 10 }, (_, index) =>
    asset(index + 1, 10 + index * 0.02, 10 + index * 0.02, index === 1 ? 'offline' : 'online')
  );
  const source = [...nearby, asset(99, -55, -100)];
  const globalMarkers = buildDeviceMarkers(source, 1);
  const streetMarkers = buildDeviceMarkers(source, 64);
  assert.equal(globalMarkers.length, source.length);
  assert.equal(streetMarkers.length, source.length);
  assert.ok(globalMarkers.every((marker) => marker.kind === 'device' && marker.count === 1));
  assert.deepEqual(globalMarkers.map((marker) => marker.id), source.map((item) => item.id));
  assert.deepEqual(streetMarkers.map((marker) => marker.id), source.map((item) => item.id));
});

test('device marker generation does not depend on geographic degree cells or zoom', () => {
  const source = [
    asset(1, 10, 10), asset(2, 10.2, 10.1), asset(3, 10.4, 10.3), asset(4, 30, 30),
  ];
  for (const zoom of [1, 1.45, 4, 16, 64]) {
    const markers = buildDeviceMarkers(source, zoom);
    assert.deepEqual(markers.map((item) => item.id), [1, 2, 3, 4]);
  }
});

test('device marker generation retains dense city assets for projection-aware clustering', () => {
  const markers = buildDeviceMarkers([
    asset(1, -23.55, -46.63), asset(2, -23.56, -46.64), asset(3, -23.8, -46.9),
  ], 3.2);
  assert.deepEqual(markers.map((item) => item.id), [1, 2, 3]);
});

test('invalid and unlocated assets are ignored without mutating the inventory', () => {
  const valid = asset(1, 0, 0);
  const source = [valid, asset(-1, 91, 0), { id: 2, located: false }];
  const before = JSON.stringify(source);
  const markers = buildDeviceMarkers(source, 7.2);
  assert.deepEqual(markers.map((item) => item.id), [1]);
  assert.equal(JSON.stringify(source), before);
});

test('dense device inventories preserve all located assets for the shared renderer', () => {
  const source = Array.from({ length: 1200 }, (_, index) => ({
    id: index + 1, name: `Device ${index + 1}`,
    latitude: -70 + (index % 100) * 1.4,
    longitude: -170 + Math.floor(index / 100) * 2.8,
    located: true, status: index % 2 ? 'online' : 'offline',
  }));
  const markers = buildDeviceMarkers(source, 1);
  assert.equal(markers.length, source.length);
  assert.equal(markers.reduce((total, marker) => total + marker.count, 0), source.length);
});

test('desktop HUD loads the geospatial layer and debounces zoom-only rebuilds', async () => {
  const { readFile } = await import('node:fs/promises');
  const { fileURLToPath } = await import('node:url');
  const htmlPath = fileURLToPath(new URL('../../app/static/jarvis-desktop.html', import.meta.url));
  const html = await readFile(htmlPath, 'utf8');
  const moduleTag = html.indexOf('<script src="/static/jarvis-geospatial-layer.js"></script>');
  const mainScript = html.indexOf('<script>', moduleTag);
  assert.ok(moduleTag >= 0 && mainScript > moduleTag);
  assert.match(html, /deviceLayerTimer=setTimeout\(\(\)=>\{/);
  assert.match(html, /Globe\.setDeviceData\(locatedDevices\(\)\)/);
  assert.match(html, /\},450\);/);
  assert.match(html, /const clusters=layer\.clusterScreenPoints\(visible,threshold\)/);
  assert.doesNotMatch(html, /if\(item\.m\.kind==='device'\|\|item\.m\.kind==='device_cluster'\)/);
  assert.match(html, /Math\.min\(64,/);
  assert.match(html, /generalizeRegion/);
  assert.match(html, /const size=Math\.max\(2,Math\.min\(4\.5,/);
  assert.match(html, /labelBoxes\.length>=Math\.min\(120,Math\.round\(45\+zoom\*12\)\)/);
  assert.match(html, /if\(!chosen\)\{ctx\.restore\(\);return;\}/);
});
test('mixed-city clusters resolve to the deepest common administrative ancestor', () => {
  const members = [
    asset(1, -23.55, -46.63, 'online', { city: 'São Paulo', state: 'São Paulo', country: 'Brasil', neighbourhood: 'Sé' }),
    asset(2, -23.56, -46.64, 'online', { city: 'Santos', state: 'São Paulo', country: 'Brasil', neighbourhood: 'Gonzaga' }),
  ];
  assert.equal(generalizeRegion(members, 64), 'São Paulo · Brasil');
  const crossState = [
    members[0],
    asset(3, -25.43, -49.27, 'online', { city: 'Curitiba', state: 'Paraná', country: 'Brasil', neighbourhood: 'Centro' }),
  ];
  assert.equal(generalizeRegion(crossState, 64), 'Brasil');
});

test('administrative boundary selection follows viewport area, not administrative names', () => {
  const { chooseBoundaryLayer } = globalThis.JarvisGeospatialLayer;
  const layers = [
    { id: 'countries', meanAreaKm2: 2500000 },
    { id: 'states', meanAreaKm2: 85000 },
    { id: 'municipalities', meanAreaKm2: 1200 },
    { id: 'neighbourhoods', meanAreaKm2: 18 },
  ];
  assert.equal(chooseBoundaryLayer(1, 510000000, layers).id, 'countries');
  assert.equal(chooseBoundaryLayer(5, 90000, layers).id, 'states');
  assert.equal(chooseBoundaryLayer(10, 1400, layers).id, 'municipalities');
  assert.equal(chooseBoundaryLayer(18, 20, layers).id, 'neighbourhoods');
});

test('administrative boundary dataset includes attributed country and state linework', async () => {
  const path = new URL('../../app/static/world-admin-boundaries.json.gz.b64', import.meta.url);
  const encoded = (await readFile(path, 'utf8')).replace(/\\s+/g, '');
  const data = JSON.parse(gunzipSync(Buffer.from(encoded, 'base64')).toString('utf8'));
  assert.ok(data.countries.length > 100);
  assert.ok(data.states.length > 1000);
  assert.match(data.stateCoverage, /Selected countries/);
  assert.match(data.attribution, /Natural Earth/);
  assert.equal(data.license, 'Public domain');
});

test('HUD loads and renders administrative contours using the scale selector', async () => {
  const { readFile } = await import('node:fs/promises');
  const { fileURLToPath } = await import('node:url');
  const html = await readFile(fileURLToPath(new URL('../../app/static/jarvis-desktop.html', import.meta.url)), 'utf8');
  assert.match(html, /world-admin-boundaries\.json/);
  assert.match(html, /function drawAdminBoundaries\(/);
  assert.match(html, /chooseBoundaryLayer\(zoom,viewportAreaKm2,adminBoundaries\.layers\)/);
  assert.match(html, /drawAdminBoundaryLines\(adminBoundaries\.countries/);
  assert.match(html, /drawAdminBoundaryLines\(adminBoundaries\.states/);
});
test('desktop renderer sends every visible category through the shared screen-space clusterer', async () => {
  const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');
  assert.match(html, /const threshold=layer\.clusterThresholdForZoom\(zoom\)/);
  assert.match(html, /const clusters=layer\.clusterScreenPoints\(visible,threshold\)/);
  assert.doesNotMatch(html, /if\(item\.m\.kind==='device'\|\|item\.m\.kind==='device_cluster'\)/);
  assert.match(html, /kind:'cluster',label:count\+' '\+String\(first\.m\.kind/);
});

test('orbital zoom supports street-level inspection and cluster members are individually selectable', async () => {
  const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');
  assert.match(html, /Math\.min\(64,Number\.isFinite\(value\)\?value:1\)/);
  assert.match(html, /data-cluster-member/);
  assert.match(html, /cluster-member-list/);
  assert.match(html, /renderSelection\(member\)/);
  assert.match(html, /Math\.min\(64,Math\.max\(4,/);
});

test('orbital HUD exposes filters for all principal observation layers', async () => {
  const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');
  for (const layer of ['satellite', 'aircraft', 'vessel', 'fire', 'quake', 'camera', 'device', 'installation', 'radio_station']) {
    assert.match(html, new RegExp('data-layer="' + layer + '"'));
  }
  assert.match(html, /state\.layers\.device\?locatedDevices\(\):\[\]/);
  assert.match(html, /return state\.layers\[layer\]!==false/);
});

test('cluster clicks open a member inspector instead of forcing an automatic zoom', async () => {
  const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');
  assert.match(html, /AGRUPAMENTO ABERTO · SELECIONE UM MEMBRO OU USE APROXIMAR/);
  assert.match(html, /if\(mark\.cluster\|\|mark\.kind==='device_cluster'\)/);
  assert.doesNotMatch(html, /const next=current<1\.2\?1\.8:current<2\.2\?3\.2:Math\.min\(8/);
});

test('unchanged intelligence snapshots do not redraw the globe', async () => {
  const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');
  assert.match(html, /if\(!uiChanged&&!globeChanged\)return/);
  assert.match(html, /renderAll\(\{globe:globeChanged\}\)/);
  assert.match(html, /if\(changed\)\{buildAreas\(\);if\(state\.layers\.device\)refreshGlobe\(\);\}/);
  assert.match(html, /if\(state\.token&&!document\.hidden\)refreshLatest/);
});

test('installation markers retain high-priority reverse geocoding', async () => {
  const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');
  assert.match(html, /PLACE_PRIORITY=\{device:0,camera:1,installation:2/);
  assert.match(html, /LABEL_KINDS=new Set\(\[[^\]]*installation/);
});

test('aircraft observations resolve a stable identity across provider-specific identifiers', () => {
  const { normalizeAircraftIdentity } = globalThis.JarvisGeospatialLayer;
  assert.deepEqual(normalizeAircraftIdentity({
    entity_id: 'a1b2c3',
    attributes: { icao24: 'A1B2C3', callsign: ' GLO1235 ', registration: 'PR-GXQ' },
  }), {
    key: 'icao24:a1b2c3',
    icao24: 'a1b2c3',
    registration: 'PR-GXQ',
    callsign: 'GLO1235',
  });
  assert.equal(normalizeAircraftIdentity({
    entity_id: 'GLO1235',
    attributes: { callsign: 'GLO1235' },
  }).key, 'callsign:GLO1235');
});

test('aircraft track history deduplicates positions and enforces age and point limits', () => {
  const { appendAircraftTrack } = globalThis.JarvisGeospatialLayer;
  const tracks = new Map();
  const observation = (timestamp, latitude, longitude) => ({
    entity_id: 'a1b2c3',
    source_id: 'adsb',
    observed_at: new Date(timestamp).toISOString(),
    position: { latitude, longitude },
    attributes: { icao24: 'a1b2c3', callsign: 'GLO1235', altitude_ft: 35000 },
  });
  appendAircraftTrack(tracks, observation(1000, -23, -46), { now: 100000, maxPoints: 2, maxAgeMs: 500000 });
  appendAircraftTrack(tracks, observation(2000, -22.9, -45.9), { now: 100000, maxPoints: 2, maxAgeMs: 500000 });
  appendAircraftTrack(tracks, observation(2000, -22.9, -45.9), { now: 100000, maxPoints: 2, maxAgeMs: 500000 });
  appendAircraftTrack(tracks, observation(3000, -22.8, -45.8), { now: 100000, maxPoints: 2, maxAgeMs: 500000 });
  const track = tracks.get('icao24:a1b2c3');
  assert.equal(track.points.length, 2);
  assert.equal(track.points[0].latitude, -22.9);
  assert.equal(track.points[1].latitude, -22.8);
  assert.equal(track.callsign, 'GLO1235');
});

test('aircraft routes distinguish confirmed flight plans from airport-pair estimates', () => {
  const { normalizeAircraftRoute } = globalThis.JarvisGeospatialLayer;
  const estimated = normalizeAircraftRoute({
    origin: { code: 'REC', latitude: -8.12649, longitude: -34.9236 },
    destination: { code: 'CGH', latitude: -23.62611, longitude: -46.65639 },
    provider: 'adsbdb_via_gods_eye_view',
  });
  assert.equal(estimated.kind, 'airport_pair_estimate');
  assert.equal(estimated.confirmed, false);
  assert.equal(estimated.waypoints.length, 0);
  const planned = normalizeAircraftRoute({
    kind: 'flight_plan',
    waypoints: [{ ident: 'REC', latitude: -8.12649, longitude: -34.9236 }, { ident: 'CGH', latitude: -23.62611, longitude: -46.65639 }],
    provider: 'flightaware_aeroapi',
  });
  assert.equal(planned.kind, 'flight_plan');
  assert.equal(planned.confirmed, true);
  assert.equal(planned.waypoints.length, 2);
});
