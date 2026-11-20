'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  buildCompanyMarkers,
  calculateBounds,
  clusterCompanyMarkers,
  projectPoint,
} = require('../../app/static/jarvis-prospecting-map.js');

const company = (name, latitude, longitude, status = 'success', precision = 'premise') => ({
  company_name: name,
  city: 'São José',
  state: 'SC',
  cnpj: '12345678000190',
  geocoding: {
    status,
    precision,
    provider: 'geocodebr:cnefe',
    coordinate: {
      latitude,
      longitude,
      accuracy_m: 20,
      crs: 'EPSG:4674',
    },
  },
});

test('company markers accept valid cached coordinates and preserve CRS and precision', () => {
  const markers = buildCompanyMarkers([
    company('Alfa', -27.6136, -48.6366),
    company('Beta', -27.61, -48.63, 'partial', 'street'),
    company('Failed', null, null, 'failed', 'unknown'),
    { company_name: 'No cache', geocoding: null },
  ]);

  assert.equal(markers.length, 2);
  assert.equal(markers[0].kind, 'company');
  assert.equal(markers[0].coordinate.crs, 'EPSG:4674');
  assert.equal(markers[0].approximate, false);
  assert.equal(markers[1].approximate, true);
});

test('company marker builder rejects out-of-range and incomplete coordinates', () => {
  const markers = buildCompanyMarkers([
    company('Bad latitude', 91, -48),
    company('Bad longitude', -27, -181),
    company('Missing longitude', -27, null),
  ]);
  assert.deepEqual(markers, []);
});

test('map bounds include every marker and expand a single point to a useful viewport', () => {
  const one = buildCompanyMarkers([company('Alfa', -27.6, -48.6)]);
  const bounds = calculateBounds(one);
  assert.ok(bounds.maxLatitude > -27.6);
  assert.ok(bounds.minLatitude < -27.6);
  assert.ok(bounds.maxLongitude > -48.6);
  assert.ok(bounds.minLongitude < -48.6);
});

test('projectPoint maps geographic extrema to the expected viewport corners', () => {
  const bounds = {
    minLatitude: -30,
    maxLatitude: -20,
    minLongitude: -55,
    maxLongitude: -45,
  };
  assert.deepEqual(projectPoint(-55, -20, bounds, 1000, 500), { x: 0, y: 0 });
  assert.deepEqual(projectPoint(-45, -30, bounds, 1000, 500), { x: 1000, y: 500 });
});

test('company markers cluster spatially while retaining their members', () => {
  const markers = buildCompanyMarkers([
    company('Alfa', -27.6000, -48.6000),
    company('Beta', -27.6001, -48.6001),
    company('Gamma', -27.7000, -48.7000),
  ]);
  const projected = markers.map((marker, index) => ({
    ...marker,
    x: index < 2 ? 100 + index : 700,
    y: index < 2 ? 100 + index : 400,
  }));
  const clusters = clusterCompanyMarkers(projected, 24);
  assert.equal(clusters.length, 2);
  assert.deepEqual(clusters.map(item => item.count).sort(), [1, 2]);
  assert.equal(clusters.find(item => item.count === 2).members.length, 2);
});


test('map rejects projected or unknown CRS instead of treating meters as degrees', () => {
  const projected = company('Projected', -27.6, -48.6);
  projected.geocoding.coordinate.crs = 'EPSG:31982';
  const unknown = company('Unknown', -27.6, -48.6);
  unknown.geocoding.coordinate.crs = 'LOCAL:GRID';
  assert.deepEqual(buildCompanyMarkers([projected, unknown]), []);
});
