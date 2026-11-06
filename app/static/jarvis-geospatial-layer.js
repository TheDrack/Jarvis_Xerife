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

  function clusterThresholdForZoom(zoom) {
    const level = Number.isFinite(Number(zoom)) ? Math.max(0.75, Math.min(64, Number(zoom))) : 1;
    return Math.max(8, 26 / Math.sqrt(level));
  }

  function clusterScreenPoints(points, threshold) {
    const source = Array.isArray(points) ? points : [];
    const radius = Number.isFinite(Number(threshold)) ? Math.max(1, Number(threshold)) : 26;
    const clusters = [];
    const cells = new Map();

    for (const item of source) {
      if (!item || !item.m || !Number.isFinite(Number(item.sx)) || !Number.isFinite(Number(item.sy))) continue;
      const kind = String(item.m.kind || 'unknown');
      const gx = Math.floor(Number(item.sx) / radius);
      const gy = Math.floor(Number(item.sy) / radius);
      let target = null;
      let bestDistance = radius;

      for (let dx = -1; dx <= 1; dx += 1) {
        for (let dy = -1; dy <= 1; dy += 1) {
          const bucket = cells.get(kind + ':' + (gx + dx) + ',' + (gy + dy));
          if (!bucket) continue;
          for (const candidate of bucket) {
            const distance = Math.hypot(candidate.x - Number(item.sx), candidate.y - Number(item.sy));
            if (distance <= bestDistance) {
              bestDistance = distance;
              target = candidate;
            }
          }
        }
      }

      if (!target) {
        target = {
          kind,
          x: Number(item.sx),
          y: Number(item.sy),
          sumX: Number(item.sx),
          sumY: Number(item.sy),
          items: [item],
          color: item.color,
          bucketX: gx,
          bucketY: gy,
        };
        clusters.push(target);
        const key = kind + ':' + gx + ',' + gy;
        if (!cells.has(key)) cells.set(key, []);
        cells.get(key).push(target);
        continue;
      }

      target.items.push(item);
      target.sumX += Number(item.sx);
      target.sumY += Number(item.sy);
      target.x = target.sumX / target.items.length;
      target.y = target.sumY / target.items.length;

      const nextX = Math.floor(target.x / radius);
      const nextY = Math.floor(target.y / radius);
      if (nextX !== target.bucketX || nextY !== target.bucketY) {
        const previousKey = kind + ':' + target.bucketX + ',' + target.bucketY;
        const previousBucket = cells.get(previousKey);
        if (previousBucket) {
          const index = previousBucket.indexOf(target);
          if (index >= 0) previousBucket.splice(index, 1);
          if (!previousBucket.length) cells.delete(previousKey);
        }
        target.bucketX = nextX;
        target.bucketY = nextY;
        const nextKey = kind + ':' + nextX + ',' + nextY;
        if (!cells.has(nextKey)) cells.set(nextKey, []);
        cells.get(nextKey).push(target);
      }
    }
    return clusters;
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

  function buildDeviceMarkers(assets) {
    const inventory = Array.isArray(assets) ? assets : [];
    return inventory
      .filter((asset) =>
        asset && asset.located === true &&
        validCoordinate(asset.latitude, -90, 90) &&
        validCoordinate(asset.longitude, -180, 180) &&
        asset.id !== undefined && asset.id !== null
      )
      .map((asset) => Object.assign({}, asset, {
        kind: 'device',
        count: 1,
        assets: [asset],
      }));
  }

  function normalizeAircraftIdentity(observation) {
    const source = observation && typeof observation === 'object' ? observation : {};
    const attributes = source.attributes && typeof source.attributes === 'object' ? source.attributes : {};
    const entityId = String(source.entity_id || '').trim();
    const rawIcao = String(attributes.icao24 || attributes.icao || (/^[0-9a-f]{6}$/i.test(entityId) ? entityId : '')).trim();
    const icao24 = /^[0-9a-f]{6}$/i.test(rawIcao) ? rawIcao.toLowerCase() : '';
    const registration = String(attributes.registration || attributes.reg || '').trim().toUpperCase();
    const callsign = String(attributes.callsign || attributes.flight || '').trim().toUpperCase();
    const key = icao24 ? 'icao24:' + icao24 :
      registration ? 'registration:' + registration :
      callsign ? 'callsign:' + callsign :
      entityId ? 'entity:' + String(source.source_id || 'unknown') + ':' + entityId : '';
    return { key, icao24, registration, callsign };
  }

  function normalizeAircraftPosition(observation) {
    const source = observation && typeof observation === 'object' ? observation : {};
    const position = source.position && typeof source.position === 'object' ? source.position : {};
    if (!validCoordinate(position.latitude, -90, 90) || !validCoordinate(position.longitude, -180, 180)) return null;
    const timestamp = typeof source.observed_at === 'number'
      ? source.observed_at < 100000000000 ? source.observed_at * 1000 : source.observed_at
      : Date.parse(source.observed_at || '');
    if (!Number.isFinite(timestamp) || timestamp <= 0) return null;
    const attributes = source.attributes && typeof source.attributes === 'object' ? source.attributes : {};
    return {
      timestamp,
      latitude: Number(position.latitude),
      longitude: Number(position.longitude),
      altitudeFt: attributes.altitude_ft != null && Number.isFinite(Number(attributes.altitude_ft)) ? Number(attributes.altitude_ft) : null,
      groundSpeedKnots: attributes.speed_knots != null && Number.isFinite(Number(attributes.speed_knots)) ? Number(attributes.speed_knots) : null,
      headingDeg: attributes.heading_deg != null && Number.isFinite(Number(attributes.heading_deg)) ? Number(attributes.heading_deg) : null,
      sourceId: String(source.source_id || ''),
    };
  }

  function appendAircraftTrack(tracks, observation, options = {}) {
    if (!(tracks instanceof Map)) return null;
    const identity = normalizeAircraftIdentity(observation);
    const position = normalizeAircraftPosition(observation);
    if (!identity.key || !position) return null;
    const now = Number.isFinite(Number(options.now)) ? Number(options.now) : Date.now();
    const maxPoints = Math.max(2, Math.min(2000, Number(options.maxPoints) || 240));
    const maxAgeMs = Math.max(60000, Number(options.maxAgeMs) || 2 * 60 * 60 * 1000);
    let track = tracks.get(identity.key);
    if (!track) {
      track = { key: identity.key, ...identity, points: [] };
      tracks.set(identity.key, track);
    }
    Object.assign(track, identity);
    const duplicate = track.points.findIndex((point) =>
      point.timestamp === position.timestamp ||
      (Math.abs(point.timestamp - position.timestamp) <= 60000 &&
        Math.abs(point.latitude - position.latitude) < 0.00001 &&
        Math.abs(point.longitude - position.longitude) < 0.00001)
    );
    if (duplicate >= 0) {
      track.points[duplicate] = position;
    } else {
      track.points.push(position);
    }
    track.points.sort((a, b) => a.timestamp - b.timestamp);
    track.points = track.points
      .filter((point) => point.timestamp >= now - maxAgeMs)
      .slice(-maxPoints);
    if (!track.points.length) {
      tracks.delete(identity.key);
      return null;
    }
    return track;
  }

  function normalizeAircraftRoute(route) {
    const source = route && typeof route === 'object' ? route : {};
    const validPoint = (point) => point && validCoordinate(
      point.latitude !== undefined ? point.latitude : point.lat, -90, 90
    ) && validCoordinate(
      point.longitude !== undefined ? point.longitude : point.lon, -180, 180
    );
    const normalizePoint = (point) => ({
      ident: String(point.ident || point.code || point.name || '').trim(),
      name: String(point.name || '').trim(),
      latitude: Number(point.latitude !== undefined ? point.latitude : point.lat),
      longitude: Number(point.longitude !== undefined ? point.longitude : point.lon),
    });
    const waypoints = (Array.isArray(source.waypoints) ? source.waypoints : [])
      .filter(validPoint).map(normalizePoint);
    const hasFlightPlan = source.kind === 'flight_plan' && waypoints.length >= 2;
    const origin = validPoint(source.origin) ? normalizePoint(source.origin) : waypoints[0] || null;
    const destination = validPoint(source.destination) ? normalizePoint(source.destination) : waypoints[waypoints.length - 1] || null;
    if (!origin || !destination) return null;
    return {
      kind: hasFlightPlan ? 'flight_plan' : 'airport_pair_estimate',
      confirmed: hasFlightPlan,
      origin,
      destination,
      waypoints: hasFlightPlan ? waypoints : [],
      provider: String(source.provider || 'unknown'),
      sourceQuality: hasFlightPlan ? 'filed_route' : 'airport_pair_only',
    };
  }

  return {
    buildDeviceMarkers, clusterScreenPoints, clusterThresholdForZoom,
    generalizeRegion, generalizeRegionFromMembers, chooseBoundaryLayer,
    normalizeAircraftIdentity, normalizeAircraftPosition, appendAircraftTrack, normalizeAircraftRoute,
  };
});