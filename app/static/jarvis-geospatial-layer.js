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
    if (zoom < 1.15) return 20;
    if (zoom < 1.55) return 8;
    if (zoom < 1.95) return 3;
    return 0;
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
    const maxMarkers = 300;
    let cellSize = cellSizeForZoom(level);

    if (cellSize === 0 && valid.length <= maxMarkers) {
      return valid.map((asset) => Object.assign({}, asset, {
        kind: 'device',
        count: 1,
        assets: [asset],
      }));
    }
    if (cellSize === 0) cellSize = 0.5;

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
          kind: 'device',
          count: 1,
          assets: members,
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
        assets: members.slice().sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true })).slice(0, 8),
      });
    }
    return markers;
  }

  return { buildDeviceMarkers, cellSizeForZoom };
});
