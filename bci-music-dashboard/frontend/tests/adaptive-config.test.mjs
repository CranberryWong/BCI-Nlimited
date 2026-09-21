import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const base = new URL('../src/views/Dashboard/', import.meta.url);
const source = await readFile(new URL('config/catalog.ts', base), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { defaults, tabs, choices, bounds, info } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
function leaves(value, path, visit) {
  if (value !== null && typeof value === 'object') Object.entries(value).forEach(([key, child]) => leaves(child, `${path}.${key}`, visit));
  else visit(value, path);
}
test('all nine configuration modules have defaults', () => {
  assert.equal(tabs.length, 9);
  assert.deepEqual(tabs.map(t => t.id), Object.keys(defaults));
});
test('every preset value has help and matches its selector / numeric bounds', () => {
  for (const [module, config] of Object.entries(defaults)) leaves(config, module, (value, path) => {
    assert.ok(info(path).label && info(path).help.trim().length > 0, path);
    const options = choices(path);
    if (options) assert.ok(options.includes(value), `${path}: ${value}`);
    if (typeof value === 'number') { const limits = bounds(path); assert.ok(value >= limits.min && value <= limits.max, path); }
  });
});
test('ordered repeated harmony and empty terminal transitions are retained', () => {
  assert.deepEqual(defaults.harmony.progressions.climax, ['IV', 'V', 'V', 'I']);
  assert.equal(defaults.form.minimum_phrases_per_section, 2);
  assert.equal(defaults.form.maximum_phrases_per_section, 4);
  assert.deepEqual(defaults.form.transitions.coda, []);
  for (const [from, destinations] of Object.entries(defaults.form.transitions)) {
    const ids = defaults.form.sections.map(s => s.id);
    assert.ok(ids.includes(from));
    destinations.forEach(to => assert.ok(ids.includes(to)));
  }
});
test('nullable device and location values remain unset', () => {
  assert.equal(defaults.inputs.weather.latitude, null);
  assert.equal(defaults.inputs.weather.longitude, null);
  assert.equal(defaults.outputs.audio.output_device, null);
});
test('model constraints and MIDI channel bounds are explicit', () => {
  assert.deepEqual(bounds('melody.frame_hz'), { min: 25, max: 25, step: 1 });
  assert.deepEqual(bounds('harmony.counterpoint.maximum_voices'), { min: 1, max: 2, step: 1 });
  assert.equal(bounds('outputs.midi.channels.marimba').max, 16);
});
test('tonal prototype uses one tonic and one base scale while preserving scale pitch sets', async () => {
  assert.equal(defaults.tonal.default_root, 'C');
  assert.equal(defaults.tonal.base_scale, 'gong');
  assert.equal(defaults.tonal.scale_constraint, 'strict');
  assert.equal('positive_scale' in defaults.tonal, false);
  assert.equal('negative_scale' in defaults.tonal, false);
  assert.equal('neutral_scale' in defaults.tonal, false);
  assert.equal('allowed_roots' in defaults.tonal, false);
  assert.equal('melody_range' in defaults.tonal, false);
  assert.equal('strong_beat_degrees' in defaults.tonal, false);
  assert.deepEqual(defaults.tonal.scales.major, [0,2,4,5,7,9,11]);
  assert.deepEqual(defaults.tonal.scales.gong, [0,2,4,7,9]);
  const selector = await readFile(new URL('config/TonalPitchSelector.vue', base), 'utf8');
  assert.match(selector, /未高亮仍可选择/);
  assert.match(selector, /恢复标准定义/);
  assert.match(selector, /音阶至少包含三个音级/);
  const node = await readFile(new URL('config/ConfigNode.vue', base), 'utf8');
  assert.match(node, /展开并编辑音阶定义（高级）/);
});
test('configuration drawer reads and writes the adaptive API store', async () => {
  const drawer = await readFile(new URL('AdaptiveConfigDrawer.vue', base), 'utf8');
  assert.match(drawer, /adaptive\.loadConfig\(\)/);
  assert.match(drawer, /adaptive\.saveModule\(active\.value/);
  assert.match(drawer, /adaptive\.resetModule\(active\.value\)/);
  assert.doesNotMatch(drawer, /localStorage/);
});
