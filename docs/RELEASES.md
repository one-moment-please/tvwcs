# Releases

Releases are built by `.github/workflows/release.yml`. You can also build a zip locally without GitHub.

## Usual flow

1. **Bump the version.** Change `VERSION` and add a dated section at the top of `CHANGELOG.md`.
2. **Merge to `main`.** If no release exists yet for that version, the Release workflow runs the tests, builds `TVWCS-<version>.zip` and `tvwcs.tar.gz` and publishes them as the **prerelease** `v<version>`. TVWCS offers it only to people who turned on **Include prereleases**.
3. **Test it on a TV computer.**
4. **Promote it.** Run the **Promote** workflow (Actions tab) with the tag, such as `v3.0.0`. It marks that release as **latest**, which **Check for TVWCS updates** installs by default and **Roll back to the latest release** goes back to. The README's install command downloads `tvwcs.tar.gz` from the latest release, so promoting also changes what new installs get.

## Other ways

- **Beta build:** push to the `beta` branch. The workflow builds a prerelease tagged `beta-<run number>`.
- **Publish at once:** push a tag such as `v3.0.0` by hand. That release is marked latest straight away.
- **Local build:**
  ```sh
  ./scripts/make-release.sh          # resources/TVWCS-<version>.zip and resources/tvwcs.tar.gz
  ./scripts/make-release.sh --beta   # resources/TVWCS-<version>-beta.<n>.zip
  ```

## Version numbers

`MAJOR.MINOR.PATCH`. Bump MAJOR for big or breaking changes, MINOR for new features, PATCH for fixes.
