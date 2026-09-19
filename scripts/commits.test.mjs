import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import releaseConfig from '../release.config.mjs';

const cli = join(process.cwd(), 'node_modules/@commitlint/cli/cli.js');
const lint = message => spawnSync(process.execPath, [cli], { input: message, encoding: 'utf8' });

test('all four allowed types, scopes, and breaking-change syntax pass commitlint', () => {
  for (const type of ['feat', 'fix', 'docs', 'refactor']) {
    for (const message of [`${type}: improve Windows support`, `${type}(gpu-runtime)!: change support`,
      `${type}: change support\n\nBREAKING CHANGE: update your driver`]) {
      const result = lint(message);
      assert.equal(result.status, 0, result.stdout + result.stderr);
    }
  }
});

test('other types, malformed headers, and default merge/revert exceptions are rejected', () => {
  for (const message of ['chore: ship', 'ci: update build', 'test: add checks', 'build: add hooks',
    'perf: speed up export', 'style: change spacing', 'revert: undo change', 'feature: add support',
    'fix:', 'Fix: repair export', 'fix: repair export.', 'fix(Bad Scope): repair export',
    'Merge branch main', 'v1.2.3', 'update everything', `fix: ${'x'.repeat(101)}`]) {
    assert.notEqual(lint(message).status, 0, message);
  }
});

test('the actual semantic-release commit template follows the same rules', () => {
  const template = releaseConfig.plugins.find(entry => entry[0] === '@semantic-release/git')[1].message;
  const message = template.replace('${nextRelease.version}', '1.2.3')
    .replace('${nextRelease.notes}', '## 1.2.3\n\n### Fixes\n\n* repair GPU detection');
  assert.equal(lint(message).status, 0);
});

test('the commit-msg hook reads and rejects the supplied message file', () => {
  const root = mkdtempSync(join(tmpdir(), 'erase-it-commit-'));
  const file = join(root, 'message.txt');
  try {
    writeFileSync(file, 'chore: forbidden type\n');
    const rejected = spawnSync('sh', ['.husky/commit-msg', file], { encoding: 'utf8' });
    assert.equal(rejected.status, 1, rejected.stderr);
    assert.match(rejected.stdout, /type must be one of/);
    writeFileSync(file, 'fix: repair runtime detection\n');
    const accepted = spawnSync('sh', ['.husky/commit-msg', file], { encoding: 'utf8' });
    assert.equal(accepted.status, 0, accepted.stdout + accepted.stderr);
  } finally { rmSync(root, { recursive: true, force: true }); }
});
