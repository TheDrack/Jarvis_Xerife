(function attachJarvisGeospatialLayer(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.JarvisGeospatialLayer = api;
})(typeof globalThis === 'object' ? globalThis : this, function createGeospatialLayer() {
  'use strict';

  const validCoordinate = (value, min, max) => {
    if (value === null || value === undefined || typeof value === 'boolean') return false;
    if (typeof value === 'string' && value.trim() === '') return false;
    const number = Number(value);
    return Number.isFinite(number) && number >= min && number <= max;
  };

  function clusterCenter(assets) {
    let x = 0;
    let y = 0;
    let z = 0;
    for (const asset of assets) {
      const latitude = asset.latitude * Math.PI / 180;
      const longitude = asset.longitude * Math.PI / 180;
      const cosLatitude = Math.cos(latitude);
      x += cosLatitude * Math.sin(longitude);
      y += Math.sin(latitude);
      z += cosLatitude * Math.cos(longitude);
    }
    return {
      latitude: Math.atan2(y, Math.hypot(x, z)) * 180 / Math.PI,
      longitude: Math.atan2(x, z) * 180 / Math.PI,
    };
  }

  function cellSizeForZoom(zoom) {
    const level = Number.isFinite(Number(zoom)) ? Number(zoom) : 1;
    if (level < 1.15) return 20;
    if (level < 1.55) return 8;
    if (level < 2.8) return 1;
    if (level < 4) return 0.25;
    if (level < 5.5) return 0.05;
    if (level < 7) return 0.01;
    return 0;
  }

  function chooseBoundaryLayer(zoom, viewportAreaKm2, layers) {
    const candidates = Array.isArray(layers)
      ? layers.filter((layer) => layer && Number.isFinite(Number(layer.meanAreaKm2)) && Number(layer.meanAreaKm2) > 0)
      : [];
    if (!candidates.length || !Number.isFinite(Number(viewportAreaKm2)) || Number(viewportAreaKm2) <= 0) return null;
    const level = Math.max(1, Number(zoom) || 1);
    const visibleRegions = Math.min(3.5, 2.5 + level * 0.05);
    const targetArea = Number(viewportAreaKm2) / visibleRegions;
    return candidates.reduce((best, layer) => {
      const score = Math.abs(Math.log(Number(layer.meanAreaKm2) / targetArea));
      return !best || score < best.score ? { layer, score } : best;
    }, null).layer;
  }

  function placeOf(asset) {
    const source = asset && asset.record && typeof asset.record === 'object' ? asset.record : asset || {};
    const attributes = source.attributes && typeof source.attributes === 'object' ? source.attributes : {};
    const place = source.place && typeof source.place === 'object' ? source.place :
      asset && asset.place && typeof asset.place === 'object' ? asset.place : {};
    const address = source.address && typeof source.address === 'object' ? source.address : {};
    const read = (...values) => {
      const value = values.find((item) => typeof item === 'string' && item.trim());
      return value ? value.trim() : '';
    };
    return {
      country: read(place.country, address.country, source.country, attributes.country),
      state: read(place.state, place.region, address.state, address.region, source.state, attributes.state, attributes.region),
      city: read(place.city, place.town, place.municipality, address.city, address.town, address.municipality, source.city, attributes.city, attributes.town),
      neighbourhood: read(place.neighbourhood, place.neighborhood, place.suburb, place.district,
        address.neighbourhood, address.neighborhood, address.suburb, address.district,
        source.neighbourhood, source.neighborhood, attributes.neighbourhood, attributes.neighborhood,
        attributes.suburb, attributes.district),
    };
  }

  function generalizeRegion(assets, zoom) {
    const members = Array.isArray(assets) ? assets : [];
    if (!members.length) return 'Região geográfica';
    const level = Number.isFinite(Number(zoom)) ? Number(zoom) : 1;
    const places = members.map(placeOf);
    const common = (field) => {
      const values = places.map((place) => place[field]);
      if (!values[0] || values.some((value) => value.toLocaleLowerCase() !== values[0].toLocaleLowerCase())) return '';
      return values[0];
    };
    const country = common('country');
    const state = common('state');
    const city = common('city');
    const neighbourhood = common('neighbourhood');
    let fields;
    if (level < 1.15) fields = [country];
    else if (level < 1.55) fields = [state, country];
    else if (level < 3.5) fields = [city, state, country];
    else fields = [neighbourhood, city, state, country];
    const label = fields.filter(Boolean).join(' · ');
    return label || 'Região geográfica';
  }

  function generalizeRegionFromMembers(members, zoom, lookupPlace) {
    const records = (Array.isArray(members) ? members : []).map((member) => {
      const source = member && member.record && typeof member.record === 'object'
        ? member.record
        : member || {};
      const cached = typeof lookupPlace === 'function'
        ? lookupPlace(member && member.latitude, member && member.longitude)
        : null;
      if (cached && cached.rawAddress && typeof cached.rawAddress === 'object') {
        return Object.assign({}, source, { address: cached.rawAddress });
      }
      return source;
    });
    return generalizeRegion(records, zoom);
  }

  function buildDeviceMarkers(assets, zoom) {
    const inventory = Array.isArray(assets) ? assets : [];
    const level = Number.isFinite(Number(zoom)) ? Number(zoom) : 1;
    const valid = inventory.filter((asset) =>
      asset && asset.located === true &&
      validCoordinate(asset.latitude, -90, 90) &&
      validCoordinate(asset.longitude, -180, 180) &&
      asset.id !== undefined && asset.id !== null
    );
    const maxMarkers = Math.min(6000, Math.round(300 * Math.pow(Math.max(1, level), 1.25)));
    let cellSize = cellSizeForZoom(level);

    if (cellSize === 0 && valid.length <= maxMarkers) {
      return valid.map((asset) => Object.assign({}, asset, {
        kind: 'device', count: 1, assets: [asset],
      }));
    }
    if (cellSize === 0) cellSize = 0.01;

    let cells = new Map();
    do {
      cells = new Map();
      for (const asset of valid) {
        const latitude = Number(asset.latitude);
        const longitude = Number(asset.longitude);
        const row = Math.floor((latitude + 90) / cellSize);
        const column = Math.floor((longitude + 180) / cellSize);
        const key = row + ':' + column;
        if (!cells.has(key)) cells.set(key, []);
        cells.get(key).push(asset);
      }
      if (cells.size <= maxMarkers || cellSize >= 180) break;
      cellSize *= 2;
    } while (true);

    const markers = [];
    for (const [key, members] of cells) {
      if (members.length === 1) {
        markers.push(Object.assign({}, members[0], {
          kind: 'device', count: 1, assets: members,
        }));
        continue;
      }
      const center = clusterCenter(members);
      const onlineCount = members.filter((item) => item.status === 'online').length;
      markers.push({
        id: 'cluster:' + key,
        kind: 'device_cluster',
        latitude: center.latitude,
        longitude: center.longitude,
        name: members.length + ' dispositivos',
        label: members.length + ' dispositivos',
        count: members.length,
        online_count: onlineCount,
        offline_count: members.length - onlineCount,
        assets_total: members.length,
        region: generalizeRegion(members, level),
        assets: members.slice().sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true })),
      });
    }
    return markers;
  }

  return { buildDeviceMarkers, cellSizeForZoom, generalizeRegion, generalizeRegionFromMembers, chooseBoundaryLayer };
});