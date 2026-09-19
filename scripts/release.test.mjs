import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { Writable } from 'node:stream';
import { test } from 'node:test';
import semanticRelease from 'semantic-release';
import releaseConfig from '../release.config.mjs';
import { isReleaseCommit, shouldRelease } from './release-trigger.mjs';
import { analyzeCommits, success } from './semantic-release.mjs';

test('a successful release exposes its exact version to the NVIDIA job', () => {
  const root = mkdtempSync(join(tmpdir(), 'erase-it-release-output-'));
  try {
    const output = join(root, 'output');
    success({}, { nextRelease: { version: '1.2.3' }, env: { GITHUB_OUTPUT: output } });
    assert.equal(readFileSync(output, 'utf8'), 'version=1.2.3\n');
    success({}, { nextRelease: { version: '1.2.3' }, env: {} });
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('only a chore subject can request release', () => {
  for (const message of ['chore: ship', 'chore(deps): update', 'chore(release): publish', 'chore!: break']) {
    assert.equal(isReleaseCommit(message), true, message);
  }
  for (const message of [
    'feat: add export', 'fix: repair export', 'docs: help\n\nchore: ship',
    'Merge pull request #1\n\nchore: ship', 'chore:', 'choreography: change',
    'chore(release): 1.2.3 [skip ci]', 'chore: update [skip release]',
  ]) {
    assert.equal(isReleaseCommit(message), false, message);
  }
});

test('PRs, manual runs, tags, and other branches cannot publish', () => {
  assert.equal(shouldRelease('push', 'refs/heads/main', 'chore: ship'), true);
  for (const [event, ref] of [
    ['pull_request', 'refs/heads/main'], ['workflow_dispatch', 'refs/heads/main'],
    ['push', 'refs/heads/feature'], ['push', 'refs/tags/v1.0.0'],
  ]) {
    assert.equal(shouldRelease(event, ref, 'chore: ship'), false);
  }
});

async function analyze(messages) {
  const cwd = mkdtempSync(join(tmpdir(), 'erase-it-release-'));
  const git = (...args) => execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  try {
    git('init', '-b', 'main');
    git('config', 'user.email', 'release-test@example.com');
    git('config', 'user.name', 'Release Test');
    git('config', 'commit.gpgsign', 'false');
    const commits = messages.map(message => {
      git('commit', '--allow-empty', '-m', message);
      return { message, hash: git('rev-parse', 'HEAD').trim() };
    });
    return await analyzeCommits({}, { cwd, commits, logger: { log() {} } });
  } finally {
    rmSync(cwd, { recursive: true, force: true });
  }
}

test('analyzer also rejects older chores when HEAD is a feature', async () => {
  assert.equal(await analyze(['chore: earlier maintenance', 'feat: new export']), null);
});

test('chore requests at least a patch, including non-conventional earlier commits', async () => {
  assert.equal(await analyze(['Fix the old export path', 'chore: ship']), 'patch');
});

test('features accumulated before a chore request produce a minor release', async () => {
  assert.equal(await analyze(['feat: new export', 'chore(release): ship']), 'minor');
});

test('breaking features and breaking chores produce major releases', async () => {
  assert.equal(await analyze(['feat!: new format', 'chore: ship']), 'major');
  assert.equal(await analyze(['chore!: change runtime']), 'major');
  assert.equal(await analyze(['chore: change runtime\n\nBREAKING CHANGE: old projects need conversion']), 'major');
});

test('the generated release commit does not request another release', async () => {
  assert.equal(await analyze(['feat: export', 'chore(release): 1.0.0 [skip ci]']), null);
});

test('semantic-release dry run resolves the configured plugins and versions without publishing', async () => {
  const root = mkdtempSync(join(tmpdir(), 'erase-it-semantic-'));
  const cwd = join(root, 'checkout');
  const remote = join(root, 'origin.git');
  const git = (directory, ...args) => execFileSync('git', args, {
    cwd: directory, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
  });
  let logs = '';
  const output = new Writable({ write(chunk, _encoding, callback) { logs += chunk.toString(); callback(); } });
  try {
    git(root, 'init', '--bare', '--initial-branch=main', remote);
    git(root, 'clone', remote, cwd);
    git(cwd, 'config', 'user.email', 'release-test@example.com');
    git(cwd, 'config', 'user.name', 'Release Test');
    git(cwd, 'config', 'commit.gpgsign', 'false');
    git(cwd, 'commit', '--allow-empty', '-m', 'chore: first release');
    git(cwd, 'push', 'origin', 'main');
    // Keep all local lifecycle hooks. Only omit GitHub authentication/publishing.
    const plugins = releaseConfig.plugins.filter(entry => entry[0] !== '@semantic-release/github').map(entry => {
      const [name, options] = Array.isArray(entry) ? entry : [entry, {}];
      const path = name.startsWith('./')
        ? fileURLToPath(new URL(`../${name}`, import.meta.url))
        : fileURLToPath(import.meta.resolve(name));
      return [path, options];
    });
    const run = () => semanticRelease({
      ...releaseConfig, repositoryUrl: pathToFileURL(remote).href, plugins, dryRun: true, ci: false,
    }, {
      cwd, stdout: output, stderr: output,
      // Analyze the fixture's main branch even when this test runs in a GitHub PR.
      env: { ...process.env, GITHUB_ACTIONS: '', CI: '' },
    });
    const first = await run();
    assert.ok(first, logs);
    assert.equal(first.nextRelease.version, '1.0.0');
    assert.equal(git(cwd, 'tag', '--list').trim(), '');
    git(cwd, 'tag', 'v1.0.0');
    git(cwd, 'commit', '--allow-empty', '-m', 'feat: new export');
    git(cwd, 'push', 'origin', 'main', '--tags');
    assert.equal(await run(), false);
    git(cwd, 'commit', '--allow-empty', '-m', 'chore: publish export');
    git(cwd, 'push', 'origin', 'main');
    const next = await run();
    assert.equal(next.nextRelease.version, '1.1.0');
    assert.match(next.nextRelease.notes, /new export/);
    assert.match(next.nextRelease.notes, /publish export/);
    assert.equal(git(cwd, 'tag', '--list').trim(), 'v1.0.0');
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
