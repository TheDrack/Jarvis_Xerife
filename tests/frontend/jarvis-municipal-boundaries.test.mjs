import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';

const encoded = (await readFile(new URL('../../app/static/world-municipal-boundaries.json.gz.b64', import.meta.url), 'utf8')).replace(/\s+/g, '');
const dataset = JSON.parse(gunzipSync(Buffer.from(encoded, 'base64')).toString('utf8'));

test('IBGE 2025 municipal boundary asset has complete Santa Catarina coverage and valid geometry', () => {
  assert.equal(dataset.edition, 2025);
  assert.deepEqual(dataset.stateCoverage, ['SC']);
  assert.equal(dataset.featureCount, 295);
  assert.equal(dataset.municipalityLabels.length, 295);
  assert.ok(dataset.municipalities.length >= dataset.featureCount);
  assert.ok(dataset.municipalities.every((ring) => ring.length >= 4 && ring[0][0] === ring.at(-1)[0] && ring[0][1] === ring.at(-1)[1]));
  assert.ok(dataset.municipalityLabels.every((label) => label.name && Number.isFinite(label.latitude) && Number.isFinite(label.longitude)));
  assert.match(dataset.sourceUrl, /ibge\.gov\.br/);
});
