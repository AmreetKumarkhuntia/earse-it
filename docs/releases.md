# Automated releases

Commit messages are enforced by a Git hook and CI. Only `feat`, `fix`, `docs`, and
`refactor` are allowed: `type(optional-scope): short description`. Run `npm ci` to
install the hook. See [CONTRIBUTING.md](../CONTRIBUTING.md) for examples and rules.

Push a `feat` or `fix` commit to `main` to request an automatic release. Breaking
changes of any allowed type also request one. Ordinary `docs` and `refactor`
commits, pull requests, and manual runs build and test without publishing. Add
`[skip release]` to defer publishing for a particular push. Only HEAD decides
whether the push requests a release; use a matching PR title when squash merging.

After frontend tests, worker tests, real CPU inference, and Rust formatting pass,
semantic-release calculates the version from all commits since the last release:
`fix` gives a patch, `feat` a minor, and `!` or a `BREAKING CHANGE:` footer a major.
With no existing version tag, semantic-release starts at **1.0.0**.

The workflow updates the npm, Tauri, Rust, and Python versions and the optional
NVIDIA installer version, then packages and checks both frozen workers. It builds
the Windows installer with pinned download hashes and tests an actual silent
installation with NVIDIA support before publishing. It commits these versions and `CHANGELOG.md` as
`docs(release): VERSION [skip ci]`, pushes that commit and `vVERSION`, and publishes
the installer, NVIDIA data files, sources/notices ZIP, and checksums to GitHub Releases. Pull the
generated commit before your next push. Release builds run serially; if `main`
has advanced before semantic-release starts, it skips the stale run. Use another
`feat` or `fix` commit to request a release of the latest changes in that case.

Publishing uses the workflow's built-in `GITHUB_TOKEN` with `contents: write` only
for the release job. No npm publishing token or personal access token is needed.
Repository branch/tag rules must allow that job to push the release commit and
version tag. The generated commit skips CI; installer publishing happens in the
same workflow and does not depend on a second workflow triggered by the bot's tag.
Both workers and the setup EXE are built in the same release job. GitHub keeps the
release as a draft until all assets have uploaded, so setup's NVIDIA downloads
are available when the release becomes public. Hosted Windows runners verify
installation and CUDA runtime loading; they cannot test inference on physical
NVIDIA hardware. The NVIDIA files stay below GitHub's per-asset size limit and
setup joins them automatically. Development installers include CPU support only.

For unattended release installation, use `setup.exe /S /NVIDIA`; omit `/NVIDIA`
for CPU only. An unsuccessful requested NVIDIA installation exits with code 30.
The app remains installed and can use CPU processing. The setup log is at
`%APPDATA%\io.github.amreetkumarkhuntia.eraseit\nvidia-setup.log`.

If building fails, no release commit or tag is pushed. If GitHub uploading fails
after tagging, the workflow retains `erase-it-release-files` as an Actions
artifact. Create or recover a draft release for the existing tag, upload the files
from that run, and publish the draft; rerunning semantic-release will not rebuild
an already tagged version. Published versions are not overwritten.

Release logic checks (no publishing):

```sh
npm run test:release
python -m unittest discover -s scripts -p 'test_release.py' -v
```
