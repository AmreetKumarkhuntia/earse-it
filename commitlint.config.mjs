export default {
  extends: ['@commitlint/config-conventional'],
  // Merge, revert, and version-only messages must follow the same format.
  defaultIgnores: false,
  rules: {
    'type-enum': [2, 'always', ['feat', 'fix', 'docs', 'refactor']],
    'scope-case': [2, 'always', 'kebab-case'],
    'header-max-length': [2, 'always', 100],
    'breaking-change-exclamation-mark': [0],
  },
  helpUrl: 'https://github.com/AmreetKumarkhuntia/earse-it/blob/main/CONTRIBUTING.md',
};
