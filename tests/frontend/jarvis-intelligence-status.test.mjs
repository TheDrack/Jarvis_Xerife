import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import '../../app/static/jarvis-intelligence-status.js';
const { describeSourceFailures } = globalThis.JarvisIntelligenceStatus;
test('grouped source diagnostics name each failing public provider', () => {
  const result = describeSourceFailures(['gdelt','nasa_eonet','usgs_earthquakes'], {
    gdelt: { available: false, error_code: 'TIMEOUT' },
    nasa_eonet: { available: true },
    usgs_earthquakes: { available: false, error_code: 'HTTP_429' },
  });
  assert.equal(result, 'GDELT: TIMEOUT · USGS: HTTP_429');
});
test('source diagnostics ignore healthy and missing providers and supply a fallback error', () => {
  const result = describeSourceFailures(['gdelt','nasa_eonet','usgs_earthquakes'], {
    gdelt: { available: true },
    usgs_earthquakes: { available: false },
  });
  assert.equal(result, 'USGS: UNAVAILABLE');
});
test('source diagnostics provide readable OSIRIS and unknown-provider labels', () => {
  const result = describeSourceFailures(['osiris_cctv','custom_feed'], {
    osiris_cctv: { available: false, error_code: 'NETWORK_ERROR' },
    custom_feed: { available: false, error_code: 'HTTP_503' },
  });
  assert.equal(result, 'OSIRIS / CCTV: NETWORK_ERROR · CUSTOM FEED: HTTP_503');
});
test('desktop source panel renders provider-level failure diagnostics', async () => {
  const html = await readFile(new URL('../../app/static/jarvis-desktop.html', import.meta.url), 'utf8');
  assert.ok(html.includes('jarvis-intelligence-status.js'));
  assert.ok(html.includes('JarvisIntelligenceStatus.describeSourceFailures(spec.ids,health)'));
});
