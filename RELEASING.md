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

3. Commit and push the change to `main`, then wait for the GitHub Actions test
   workflow to pass.
4. Publish a full GitHub Release whose tag is `v` followed by the manifest
   version:

   ```bash
   gh release create v1.8.2 \
     --target main \
     --title "v1.8.2 — Short description" \
     --notes-file release-notes.md
   ```

5. Verify the release and its manifest:

   ```bash
   gh release view v1.8.2
   git show v1.8.2:custom_components/openclaw/manifest.json
   ```

HACS may cache repository metadata briefly. If an upgrade does not appear,
refresh the repository information from the integration's HACS page.

For the current HACS repository requirements, see
<https://hacs.xyz/docs/publish/integration/>.
