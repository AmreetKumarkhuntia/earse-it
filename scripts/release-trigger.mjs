import { execFileSync } from 'node:child_process';
import { appendFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

export function isReleaseCommit(message) {
  const subject = message.split(/\r?\n/, 1)[0];
  return /^chore(?:\([^()\r\n]+\))?!?:\s+\S/.test(subject)
    && !/\[(?:skip ci|ci skip|skip release|release skip)\]/i.test(message);
}

export function headMessage(cwd = process.cwd()) {
  return execFileSync('git', ['log', '-1', '--format=%B'], {
    cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
  });
}

export function shouldRelease(event, ref, message) {
  return event === 'push' && ref === 'refs/heads/main' && isReleaseCommit(message);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const release = shouldRelease(process.env.GITHUB_EVENT_NAME, process.env.GITHUB_REF, headMessage());
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(process.env.GITHUB_OUTPUT, `release=${release}\n`);
  }
  console.log(release ? 'Chore commit: release after validation.' : 'Build and test without publishing.');
}
