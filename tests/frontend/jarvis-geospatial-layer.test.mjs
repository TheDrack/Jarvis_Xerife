import test from 'node:test';
import assert from 'node:assert/strict';
import '../../app/static/jarvis-geospatial-layer.js';

const { buildDeviceMarkers } = globalThis.JarvisGeospatialLayer;

const asset = (id, latitude, longitude, status = 'online') => ({
  id, name: `Device ${id}`, latitude, longitude, located: true, status,
});

test('global zoom aggregates nearby assets into a bounded cluster', () => {
  const nearby = Array.from({ length: 10 }, (_, index) =>
    asset(index + 1, 10 + index * 0.02, 10 + index * 0.02, index === 1 ? 'offline' : 'online')
  );
  const markers = buildDeviceMarkers([
    ...nearby,
    asset(99, -55, -100),
  ], 1);

  assert.equal(markers.length, 2);
  const cluster = markers.find((item) => item.kind === 'device_cluster');
  assert.ok(cluster);
  assert.equal(cluster.count, 10);
  assert.equal(cluster.assets_total, 10);
  assert.equal(cluster.assets.length, 8);
  assert.deepEqual(cluster.assets.map((item) => item.id), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.equal(cluster.online_count, 9);
  assert.equal(cluster.offline_count, 1);
});

test('regional zoom reduces cluster size while retaining individual asset identity', () => {
  const markers = buildDeviceMarkers([
    asset(1, 10, 10),
    asset(2, 10.2, 10.1),
    asset(3, 10.4, 10.3),
    asset(4, 30, 30),
  ], 1.45);

  assert.equal(markers.length, 2);
  assert.equal(markers.find((item) => item.kind === 'device_cluster').count, 3);
});

test('local zoom returns individual devices without cluster wrappers', () => {
  const markers = buildDeviceMarkers([
    asset(9, -23.5, -46.6),
    asset(10, -23.6, -46.7),
  ], 2.05);

  assert.deepEqual(markers.map((item) => item.id), [9, 10]);
  assert.ok(markers.every((item) => item.kind === 'device'));
});

test('invalid and unlocated assets are ignored without mutating the inventory', () => {
  const valid = asset(1, 0, 0);
  const source = [valid, asset(-1, 91, 0), { id: 2, located: false }];
  const before = JSON.stringify(source);

  const markers = buildDeviceMarkers(source, 2.4);

  assert.deepEqual(markers.map((item) => item.id), [1]);
  assert.equal(JSON.stringify(source), before);
});

test('dense inventories never exceed the marker budget at local zoom', () => {
  const source = Array.from({ length: 1200 }, (_, index) => ({
    id: index + 1,
    name: `Device ${index + 1}`,
    latitude: -70 + (index % 100) * 1.4,
    longitude: -170 + Math.floor(index / 100) * 2.8,
    located: true,
    status: index % 2 ? 'online' : 'offline',
  }));

  const markers = buildDeviceMarkers(source, 2.4);

  assert.ok(markers.length <= 300);
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
  assert.match(html, /kind==='device_cluster'/);
});
