(function attachJarvisProspectingMap(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.JarvisProspectingMap = api;
})(typeof globalThis === 'object' ? globalThis : this, function createProspectingMap() {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const GEOGRAPHIC_CRS = new Set(['EPSG:4326', 'EPSG:4674']);
  const validCoordinate = (value, min, max) => {
    if (value === null || value === undefined || typeof value === 'boolean') return false;
    if (typeof value === 'string' && value.trim() === '') return false;
    const number = Number(value);
    return Number.isFinite(number) && number >= min && number <= max;
  };

  function buildCompanyMarkers(companies) {
    return (Array.isArray(companies) ? companies : [])
      .filter((company) => {
        const geocoding = company && company.geocoding;
        const coordinate = geocoding && geocoding.coordinate;
        const crs = String(coordinate && coordinate.crs || 'EPSG:4326').toUpperCase();
        return geocoding &&
          (geocoding.status === 'success' || geocoding.status === 'partial') &&
          coordinate &&
          GEOGRAPHIC_CRS.has(crs) &&
          validCoordinate(coordinate.latitude, -90, 90) &&
          validCoordinate(coordinate.longitude, -180, 180);
      })
      .map((company) => {
        const geocoding = company.geocoding;
        const coordinate = geocoding.coordinate;
        const precision = String(geocoding.precision || 'unknown');
        return {
          kind: 'company',
          name: String(company.company_name || company.legal_name || 'Empresa sem nome'),
          cnpj: String(company.cnpj || ''),
          city: String(company.city || ''),
          state: String(company.state || ''),
          status: geocoding.status,
          precision,
          provider: String(geocoding.provider || 'unknown'),
          formattedAddress: String(geocoding.formatted_address || ''),
          approximate: geocoding.status === 'partial' ||
            ['interpolated', 'postal_code', 'locality', 'region', 'unknown'].includes(precision),
          coordinate: {
            latitude: Number(coordinate.latitude),
            longitude: Number(coordinate.longitude),
            accuracy_m: coordinate.accuracy_m == null ? null : Number(coordinate.accuracy_m),
            crs: String(coordinate.crs || 'EPSG:4326'),
          },
          company,
        };
      });
  }

  function calculateBounds(markers) {
    const points = Array.isArray(markers) ? markers : [];
    if (!points.length) {
      return { minLatitude: -60, maxLatitude: 15, minLongitude: -85, maxLongitude: -30 };
    }

    let minLatitude = 90, maxLatitude = -90, minLongitude = 180, maxLongitude = -180;
    for (const marker of points) {
      const coordinate = marker.coordinate || marker;
      const latitude = Number(coordinate.latitude);
      const longitude = Number(coordinate.longitude);
      minLatitude = Math.min(minLatitude, latitude);
      maxLatitude = Math.max(maxLatitude, latitude);
      minLongitude = Math.min(minLongitude, longitude);
      maxLongitude = Math.max(maxLongitude, longitude);
    }

    const latitudeSpan = Math.max(0.15, maxLatitude - minLatitude);
    const longitudeSpan = Math.max(0.15, maxLongitude - minLongitude);
    const latitudePadding = Math.max(0.03, latitudeSpan * 0.18);
    const longitudePadding = Math.max(0.03, longitudeSpan * 0.18);
    return {
      minLatitude: Math.max(-85, minLatitude - latitudePadding),
      maxLatitude: Math.min(85, maxLatitude + latitudePadding),
      minLongitude: Math.max(-180, minLongitude - longitudePadding),
      maxLongitude: Math.min(180, maxLongitude + longitudePadding),
    };
  }

  function projectPoint(longitude, latitude, bounds, width, height) {
    const longitudeSpan = Math.max(1e-9, bounds.maxLongitude - bounds.minLongitude);
    const latitudeSpan = Math.max(1e-9, bounds.maxLatitude - bounds.minLatitude);
    return {
      x: ((Number(longitude) - bounds.minLongitude) / longitudeSpan) * width,
      y: ((bounds.maxLatitude - Number(latitude)) / latitudeSpan) * height,
    };
  }

  function clusterCompanyMarkers(markers, threshold = 26) {
    const source = Array.isArray(markers) ? markers : [];
    const radius = Number.isFinite(Number(threshold)) ? Math.max(4, Number(threshold)) : 26;
    const buckets = new Map();
    for (const marker of source) {
      if (!marker || !Number.isFinite(Number(marker.x)) || !Number.isFinite(Number(marker.y))) continue;
      const key = Math.floor(Number(marker.x) / radius) + ':' + Math.floor(Number(marker.y) / radius);
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(marker);
    }
    return Array.from(buckets.values()).map((members) => ({
      kind: 'company_cluster',
      count: members.length,
      members,
      x: members.reduce((sum, item) => sum + Number(item.x), 0) / members.length,
      y: members.reduce((sum, item) => sum + Number(item.y), 0) / members.length,
      approximate: members.some((item) => item.approximate),
    }));
  }

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
    return element;
  }

  let landPromise = null;
  async function loadLand() {
    if (!landPromise) {
      landPromise = fetch('/static/world-land.json', { cache: 'force-cache' })
        .then((response) => {
          if (!response.ok) throw new Error('Camada cartográfica local indisponível.');
          return response.json();
        })
        .catch((error) => {
          landPromise = null;
          throw error;
        });
    }
    return landPromise;
  }

  function appendLand(svg, land, bounds, width, height) {
    const rings = land && Array.isArray(land.rings) ? land.rings : [];
    const group = svgElement('g', { class: 'prospecting-map-land', 'aria-hidden': 'true' });
    for (const ring of rings) {
      if (!Array.isArray(ring) || ring.length < 6 || ring.length % 2 !== 0) continue;
      let previousLongitude = null;
      let crossesDateline = false;
      const commands = [];
      for (let index = 0; index < ring.length; index += 2) {
        const longitude = Number(ring[index]);
        const latitude = Number(ring[index + 1]);
        if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) continue;
        if (previousLongitude !== null && Math.abs(longitude - previousLongitude) > 180) {
          crossesDateline = true;
          break;
        }
        previousLongitude = longitude;
        const point = projectPoint(longitude, latitude, bounds, width, height);
        commands.push((commands.length ? 'L' : 'M') + point.x.toFixed(1) + ' ' + point.y.toFixed(1));
      }
      if (crossesDateline || commands.length < 3) continue;
      commands.push('Z');
      group.appendChild(svgElement('path', { d: commands.join(' ') }));
    }
    svg.appendChild(group);
  }

  function renderGrid(svg, bounds, width, height) {
    const group = svgElement('g', { class: 'prospecting-map-grid', 'aria-hidden': 'true' });
    for (let index = 1; index < 6; index += 1) {
      const x = (width / 6) * index;
      group.appendChild(svgElement('line', { x1: x, y1: 0, x2: x, y2: height }));
    }
    for (let index = 1; index < 5; index += 1) {
      const y = (height / 5) * index;
      group.appendChild(svgElement('line', { x1: 0, y1: y, x2: width, y2: y }));
    }
    svg.appendChild(group);
  }

  async function render(container, companies, onSelect) {
    if (!container) return { markers: 0, clusters: 0 };
    const markers = buildCompanyMarkers(companies);
    container.replaceChildren();

    if (!markers.length) {
      const empty = document.createElement('div');
      empty.className = 'prospecting-map-empty';
      empty.textContent = 'Nenhuma coordenada disponível no cache para este recorte. Execute uma campanha com --geocode para gerar os pontos.';
      container.appendChild(empty);
      return { markers: 0, clusters: 0 };
    }

    const width = 1000;
    const height = 560;
    const bounds = calculateBounds(markers);
    const land = await loadLand();
    const svg = svgElement('svg', {
      class: 'prospecting-map-svg',
      viewBox: '0 0 ' + width + ' ' + height,
      role: 'img',
      'aria-label': 'Mapa de empresas geocodificadas',
      preserveAspectRatio: 'xMidYMid meet',
    });
    svg.appendChild(svgElement('rect', { x: 0, y: 0, width, height, class: 'prospecting-map-ocean' }));
    renderGrid(svg, bounds, width, height);
    appendLand(svg, land, bounds, width, height);

    const projected = markers.map((marker) => Object.assign({}, marker,
      projectPoint(marker.coordinate.longitude, marker.coordinate.latitude, bounds, width, height)));
    const clusters = clusterCompanyMarkers(projected, 28);
    const markerGroup = svgElement('g', { class: 'prospecting-map-markers' });

    clusters.forEach((cluster) => {
      const group = svgElement('g', {
        class: 'prospecting-map-marker' + (cluster.approximate ? ' is-approximate' : ''),
        role: 'button',
        tabindex: 0,
        'aria-label': cluster.count + ' empresa(s) nesta localização',
        transform: 'translate(' + cluster.x.toFixed(1) + ' ' + cluster.y.toFixed(1) + ')',
      });
      group.appendChild(svgElement('circle', {
        r: cluster.count > 1 ? Math.min(17, 7 + Math.log2(cluster.count) * 3) : 6,
      }));
      if (cluster.count > 1) {
        const label = svgElement('text', { x: 0, y: 3.5, 'text-anchor': 'middle' });
        label.textContent = String(cluster.count);
        group.appendChild(label);
      }
      const title = svgElement('title');
      title.textContent = cluster.count === 1
        ? cluster.members[0].name + ' · ' + cluster.members[0].precision
        : cluster.count + ' empresas agrupadas';
      group.appendChild(title);

      const select = () => {
        if (typeof onSelect === 'function') onSelect(cluster);
      };
      group.addEventListener('click', select);
      group.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          select();
        }
      });
      markerGroup.appendChild(group);
    });

    svg.appendChild(markerGroup);
    container.appendChild(svg);
    return {
      markers: markers.length,
      clusters: clusters.length,
      success: markers.filter((marker) => !marker.approximate).length,
      partial: markers.filter((marker) => marker.approximate).length,
      bounds,
    };
  }

  return {
    buildCompanyMarkers,
    calculateBounds,
    clusterCompanyMarkers,
    projectPoint,
    render,
  };
});
