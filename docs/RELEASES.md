# Release process (beta -> publish)

Everything below works with the GitHub Actions in `.github/workflows/release.yml`, but nothing
requires GitHub: you can build a beta zip locally any time.

## 1. Make your list of requests / changes
Commit them on a `beta` branch (or just work on `main` and skip to step 2 if you prefer).

## 2. Get a beta you can download
- **On GitHub:** push to the `beta` branch. The *Release* workflow runs the tests, builds
  `TVWCS-<version>-beta.<n>.zip` and attaches it both as a workflow artifact and as a
  **pre-release** on the Releases page. Download, unzip, run `install.sh`, live with it.
- **Locally (no GitHub needed):**
  ```sh
  ./scripts/make-release.sh --beta     # -> resources/TVWCS-<version>-beta.<n>.zip
  ```

## 3. Iterate
Repeat steps 1-2 as often as you like; each beta is numbered automatically.

## 4. Publish when happy
```sh
# update VERSION and add a dated section to CHANGELOG.md first
git add -A && git commit -m "Release v2.6.0"
git tag v2.6.0 && git push origin v2.6.0
```
Pushing a `v*` tag makes the workflow run the tests again and create the **published**
(non-prerelease) GitHub Release containing `TVWCS-2.6.0.zip`. Locally: `./scripts/make-release.sh`.

## Version numbers (semver)
`MAJOR.MINOR.PATCH` — breaking changes / big features bump MAJOR or MINOR, fixes bump PATCH.
Betas are tied to the version they are about to become (`2.6.0-beta.3` -> `v2.6.0`).
