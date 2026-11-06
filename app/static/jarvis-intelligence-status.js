(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.JarvisIntelligenceStatus = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  const SOURCE_LABELS = Object.freeze({
    gdelt: 'GDELT',
    nasa_eonet: 'NASA EONET',
    usgs_earthquakes: 'USGS',
    gods_eye_view: "GOD'S EYE VIEW",
    osiris_earthquakes: 'OSIRIS / EARTHQUAKES',
    osiris_fires: 'OSIRIS / FIRES',
    osiris_news: 'OSIRIS / NEWS',
    osiris_weather: 'OSIRIS / WEATHER',
    osiris_gdelt: 'OSIRIS / GDELT',
    osiris_flights: 'OSIRIS / FLIGHTS',
    osiris_maritime: 'OSIRIS / MARITIME',
    osiris_satellites: 'OSIRIS / SATELLITES',
    osiris_cctv: 'OSIRIS / CCTV',
  });
  function describeSourceFailures(ids, health) {
    const sourceIds = Array.isArray(ids) ? ids : [];
    const sourceHealth = health && typeof health === 'object' ? health : {};
    const seen = new Set();
    const failures = [];
    for (const value of sourceIds) {
      const id = String(value || '').trim();
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const item = sourceHealth[id];
      if (!item || item.available) continue;
      const code = String(item.error_code || 'UNAVAILABLE').trim();
      const label = SOURCE_LABELS[id] || id.replace(/_/g, ' ').toUpperCase();
      failures.push(label + ': ' + code);
    }
    return failures.join(' · ');
  }
  return Object.freeze({ describeSourceFailures });
});
