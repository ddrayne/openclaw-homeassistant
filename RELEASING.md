# Releasing for HACS

HACS uses the newest published GitHub Release as this integration's remote
version. A Git tag by itself is not enough. Stable releases must not be marked as
pre-releases; beta releases should use a prerelease tag such as
`v1.9.0-beta.1` and be marked as a GitHub pre-release.

## Release checklist

1. Choose the next semantic version and update `version` in
   `custom_components/openclaw/manifest.json`.
2. Run the complete local test suite:

   ```bash
   python -m pip install -e '.[test]'
   pytest
   ```

3. Write the release notes in `release-notes/v<version>.md`. The first line is
   the release title, e.g. `# v1.9.0 — Short description`; the rest is the body.
4. Commit and push the version bump and notes to `main`, then wait for the
   GitHub Actions test workflow to pass.
5. Publish a full GitHub Release whose tag is `v` followed by the manifest
   version. Either:

   - **Actions → Release → Run workflow** on `main` with the version (e.g.
     `1.9.0`). The workflow checks that `manifest.json` matches, that the tag
     does not exist yet and that the notes file is there, runs the tests, and
     publishes the release. A version with a suffix (`1.10.0-beta.1`) is
     marked as a pre-release automatically.
   - Or from a checkout with the GitHub CLI:

     ```bash
     gh release create v1.9.0 \
       --target main \
       --title "v1.9.0 — Short description" \
       --notes-file release-notes/v1.9.0.md
     ```

     (Remove the title line from the notes first, or it appears twice.)

6. Verify the release and its manifest:

   ```bash
   gh release view v1.9.0
   git show v1.9.0:custom_components/openclaw/manifest.json
   ```

HACS may cache repository metadata briefly. If an upgrade does not appear,
refresh the repository information from the integration's HACS page.

For the current HACS repository requirements, see
<https://hacs.xyz/docs/publish/integration/>.
