import { execFileSync } from 'node:child_process';
import { appendFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { analyzeCommits as analyzeConventionalCommits } from '@semantic-release/commit-analyzer';
import { headMessage, isReleaseCommit } from './release-trigger.mjs';

export async function analyzeCommits(_config, context) {
  // A qualifying HEAD requests publishing; analyze all unreleased commits for the version.
  if (!isReleaseCommit(headMessage(context.cwd))) {
    context.logger.log('Only a feature, fix, or breaking change at HEAD requests a release.');
    return null;
  }
  return analyzeConventionalCommits({
    preset: 'conventionalcommits',
    releaseRules: [{ breaking: true, release: 'major' }],
  }, context);
}

export function prepare(_config, { cwd, nextRelease }) {
  if (process.platform !== 'win32') {
    throw new Error('Publish Windows installers from the Windows release workflow.');
  }
  execFileSync(join(cwd, '.venv', 'Scripts', 'python.exe'), [
    'scripts/prepare-release.py', nextRelease.version,
  ], { cwd, stdio: 'inherit' });
  const changelog = join(cwd, 'CHANGELOG.md');
  const previous = existsSync(changelog) ? readFileSync(changelog, 'utf8').replace(/^# Changelog\s*/, '') : '';
  writeFileSync(changelog, `# Changelog\n\n${nextRelease.notes.trim()}\n\n${previous}`);
}

export function success(_config, { nextRelease, env }) {
  // Expose only the version that was successfully published.
  if (env.GITHUB_OUTPUT) appendFileSync(env.GITHUB_OUTPUT, `version=${nextRelease.version}\n`);
}
