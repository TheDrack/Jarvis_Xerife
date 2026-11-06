import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
import '../../app/static/jarvis-geospatial-layer.js';

const { buildDeviceMarkers, cellSizeForZoom, generalizeRegion } = globalThis.JarvisGeospatialLayer;

const asset = (id, latitude, longitude, status = 'online', place = {}) => ({
  id, name: `Device ${id}`, latitude, longitude, located: true, status, place,
});

test('geographic cells contract progressively as orbital zoom increases', () => {
  const sizes = [1, 1.45, 2.05, 3.2, 4.5, 6.2, 7.2].map(cellSizeForZoom);
  assert.deepEqual(sizes, [20, 8, 1, 0.25, 0.05, 0.01, 0]);
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

test('global zoom aggregates nearby assets into a bounded cluster', () => {
  const nearby = Array.from({ length: 10 }, (_, index) =>
    asset(index + 1, 10 + index * 0.02, 10 + index * 0.02, index === 1 ? 'offline' : 'online')
  );
  const markers = buildDeviceMarkers([...nearby, asset(99, -55, -100)], 1);
  assert.equal(markers.length, 2);
  const cluster = markers.find((item) => item.kind === 'device_cluster');
  assert.ok(cluster);
  assert.equal(cluster.count, 10);
  assert.equal(cluster.assets_total, 10);
  assert.equal(cluster.assets.length, 8);
  assert.deepEqual(cluster.assets.map((item) => item.id), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.equal(cluster.online_count, 9);
  assert.equal(cluster.offline_count, 1);
  assert.equal(cluster.region, 'Região geográfica');
});

test('regional zoom reduces cluster size while retaining individual asset identity', () => {
  const markers = buildDeviceMarkers([
    asset(1, 10, 10), asset(2, 10.2, 10.1), asset(3, 10.4, 10.3), asset(4, 30, 30),
  ], 1.45);
  assert.equal(markers.length, 2);
  assert.equal(markers.find((item) => item.kind === 'device_cluster').count, 3);
});

test('city zoom separates nearby city cells instead of preserving state-scale clusters', () => {
  const markers = buildDeviceMarkers([
    asset(1, -23.55, -46.63), asset(2, -23.56, -46.64), asset(3, -23.8, -46.9),
  ], 3.2);
  assert.equal(markers.length, 2);
  assert.equal(markers.find((item) => item.kind === 'device_cluster').count, 2);
});

test('street zoom can resolve a dense city cluster into individual assets', () => {
  const markers = buildDeviceMarkers([
    asset(1, -23.5500, -46.6300), asset(2, -23.5501, -46.6301),
  ], 7.2);
  assert.deepEqual(markers.map((item) => item.id), [1, 2]);
});

test('invalid and unlocated assets are ignored without mutating the inventory', () => {
  const valid = asset(1, 0, 0);
  const source = [valid, asset(-1, 91, 0), { id: 2, located: false }];
  const before = JSON.stringify(source);
  const markers = buildDeviceMarkers(source, 7.2);
  assert.deepEqual(markers.map((item) => item.id), [1]);
  assert.equal(JSON.stringify(source), before);
});

test('dense inventories stay bounded while zoom expands the marker budget', () => {
  const source = Array.from({ length: 1200 }, (_, index) => ({
    id: index + 1, name: `Device ${index + 1}`,
    latitude: -70 + (index % 100) * 1.4,
    longitude: -170 + Math.floor(index / 100) * 2.8,
    located: true, status: index % 2 ? 'online' : 'offline',
  }));
  const globalMarkers = buildDeviceMarkers(source, 1);
  const localMarkers = buildDeviceMarkers(source, 4.5);
  assert.ok(globalMarkers.length <= 300);
  assert.ok(localMarkers.length <= 1800);
  assert.ok(localMarkers.length > globalMarkers.length);
  assert.equal(localMarkers.reduce((total, marker) => total + marker.count, 0), source.length);
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
  assert.match(html, /kind==='device_cluster'/);
  assert.match(html, /item\.m\.kind==='device'\|\|item\.m\.kind==='device_cluster'/);
  assert.match(html, /Math\.min\(8,/);
  assert.match(html, /generalizeRegion/);
  assert.match(html, /const size=Math\.max\(2,Math\.min\(4\.5,/);
  assert.match(html, /labelBoxes\.length>=Math\.min\(120,Math\.round\(45\+zoom\*12\)\)/);
  assert.match(html, /if\(!chosen\)\{ctx\.restore\(\);return;\}/);
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