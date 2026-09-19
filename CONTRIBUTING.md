# Commit messages

Run `npm ci` after cloning. It installs the Git commit-message hook automatically.
Every new commit must use this format:

```text
type(optional-scope): short description
```

Only these four types are allowed:

| Type | Use it for | Example |
| --- | --- | --- |
| `feat` | A new user-facing capability | `feat(gpu): add NVIDIA processing` |
| `fix` | Correcting a bug | `fix(installer): handle Windows paths` |
| `docs` | Documentation | `docs: explain subject selection` |
| `refactor` | Restructuring without changing behavior | `refactor(worker): simplify device detection` |

Use lowercase types and kebab-case scopes, a short imperative description,
no trailing period, and a header of at most 100 characters. Keep proper names
such as Windows and NVIDIA capitalized within descriptions. Types such as
`chore`, `ci`, `build`, `test`, `style`, and `revert`, and unformatted messages
are rejected. Describe a reversal as a `fix` or `refactor` as appropriate.

For a breaking change, append `!` before the colon or add a `BREAKING CHANGE:`
footer explaining what users need to change. Separate the body/footer from the
header with a blank line.

```text
feat(projects)!: change the project file format

BREAKING CHANGE: export existing projects before upgrading.
```

The hook rejects an invalid message before Git creates the commit. GitHub CI
also checks every new commit in a push or pull request, plus the PR title used
for squash merging. Existing history is left intact. Use squash or rebase merges;
a plain `Merge ...` message does not follow this policy.

To check your latest commit manually:

```sh
npm run commitlint -- --last --verbose
```

Local hooks can be bypassed by Git. To require this policy before merging, make
the `frontend` GitHub Actions check a required check in the `main` branch rules.

## Releases

On `main`, a `feat` or `fix` commit at HEAD automatically requests a release after
validation. A breaking change of any allowed type also requests a release.
Semantic-release considers all unreleased commits: features produce a minor,
fixes a patch, and breaking changes a major. Ordinary `docs` and `refactor`
commits run build/test CI without publishing. Add `[skip release]` to defer
publishing for a particular push.

Generated release commits use `docs(release): VERSION [skip ci]`, which follows
the same message rules and prevents a release loop. The optional NVIDIA pack is
attached after the app installer is published. Pull the generated release commit
before your next push.
