export default {
  branches: ['main'],
  repositoryUrl: 'https://github.com/AmreetKumarkhuntia/earse-it.git',
  tagFormat: 'v${version}',
  plugins: [
    './scripts/semantic-release.mjs',
    ['@semantic-release/release-notes-generator', {
      preset: 'conventionalcommits',
      presetConfig: {
        types: [
          { type: 'feat', section: 'Features' },
          { type: 'fix', section: 'Fixes' },
          { type: 'docs', section: 'Documentation' },
          { type: 'refactor', section: 'Refactoring' },
        ],
      },
    }],
    ['@semantic-release/git', {
      assets: [
        'CHANGELOG.md', 'package.json', 'package-lock.json',
        'src-tauri/tauri.conf.json', 'src-tauri/Cargo.toml', 'src-tauri/Cargo.lock',
        'worker/pyproject.toml', 'worker/erase_it/__init__.py', 'scripts/install-nvidia.ps1',
      ],
      message: 'docs(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}',
    }],
    ['@semantic-release/github', {
      assets: [
        { path: 'artifacts/release/*.exe', label: 'Windows setup — app and optional NVIDIA support' },
        { path: 'artifacts/release/third-party-sources-and-notices-*.zip', label: 'Third-party sources and notices' },
        { path: 'artifacts/release/erase-it-nvidia-*', label: 'NVIDIA runtime data — setup downloads this automatically' },
        { path: 'artifacts/release/SHA256SUMS', label: 'SHA-256 checksums' },
      ],
      successComment: false,
      failComment: false,
      failTitle: false,
      releasedLabels: false,
    }],
  ],
};
