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

test('only features, fixes, and breaking changes request a release', () => {
  for (const message of ['feat: add selection', 'fix(gpu): load CUDA', 'refactor!: change schema',
    'docs!: change support policy', 'refactor: change schema\n\nBREAKING CHANGE: old files need conversion',
    'refactor: change schema\n\nBREAKING-CHANGE: old files need conversion']) {
    assert.equal(isReleaseCommit(message), true, message);
  }
  for (const message of ['chore: ship', 'docs: explain selection', 'refactor: simplify code',
    'docs: help\n\nfeat: old text', 'Merge pull request #1\n\nfix: repair', 'fix:',
    'feature: add selection', 'docs(release): 1.2.3 [skip ci]', 'fix: repair [skip release]']) {
    assert.equal(isReleaseCommit(message), false, message);
  }
});

test('PRs, manual runs, tags, and other branches cannot publish', () => {
  assert.equal(shouldRelease('push', 'refs/heads/main', 'fix: repair export'), true);
  for (const [event, ref] of [
    ['pull_request', 'refs/heads/main'], ['workflow_dispatch', 'refs/heads/main'],
    ['push', 'refs/heads/feature'], ['push', 'refs/tags/v1.0.0'],
  ]) {
    assert.equal(shouldRelease(event, ref, 'fix: repair export'), false);
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

test('ordinary docs and refactors at HEAD do not request a release', async () => {
  assert.equal(await analyze(['feat: earlier feature', 'docs: update the guide']), null);
  assert.equal(await analyze(['fix: earlier fix', 'refactor: simplify code']), null);
});

test('fix requests a patch', async () => {
  assert.equal(await analyze(['docs: write a guide', 'fix: repair export']), 'patch');
});

test('features accumulated before a fix produce a minor release', async () => {
  assert.equal(await analyze(['feat: new export', 'fix: repair export']), 'minor');
});

test('breaking changes of any allowed type produce a major release', async () => {
  for (const type of ['feat', 'fix', 'docs', 'refactor']) {
    assert.equal(await analyze([`${type}!: change behavior`]), 'major');
    assert.equal(await analyze([`${type}: change behavior\n\nBREAKING CHANGE: old files need conversion`]), 'major');
  }
});

test('the generated release commit does not request another release', async () => {
  assert.equal(await analyze(['feat: export', 'docs(release): 1.0.0 [skip ci]']), null);
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
    git(cwd, 'commit', '--allow-empty', '-m', 'feat: initial release');
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
    git(cwd, 'commit', '--allow-empty', '-m', 'docs: explain export');
    git(cwd, 'push', 'origin', 'main', '--tags');
    assert.equal(await run(), false);
    git(cwd, 'commit', '--allow-empty', '-m', 'feat: new export');
    git(cwd, 'push', 'origin', 'main');
    const next = await run();
    assert.equal(next.nextRelease.version, '1.1.0');
    assert.match(next.nextRelease.notes, /new export/);
    assert.match(next.nextRelease.notes, /explain export/);
    assert.equal(git(cwd, 'tag', '--list').trim(), 'v1.0.0');
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
