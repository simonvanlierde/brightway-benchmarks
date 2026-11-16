# First release

One-time steps around the first `just release`, in order. Open this file as an issue,
then delete it:

```sh
gh issue create --title "First release" --body-file .github/first-release.md
```

- [ ] **Signing key**, before the first tag: add your SSH signing key to
  `.github/allowed_signers` and commit it to `main`. The comment in that file has the
  command. The release workflow publishes nothing for a tag signed with another key.
- [ ] **Zenodo**, before the first release: turn this repo on at the Zenodo link that
  `just repo-settings` prints. Zenodo then archives each GitHub release and mints a DOI.
  Put the concept DOI (the one for all versions) in `CITATION.cff` as `doi:` and run
  `just citation`.
- [ ] **Software Heritage**, after the release: ask it to archive the repo at
  <https://archive.softwareheritage.org/save/>, with origin type `git` and
  `https://github.com/simonvanlierde/brightway-benchmarks`. When the visit is done, the archive badge in the README
  turns from "not found" to "archived". Open it and copy the release's SWHID into
  `CITATION.cff` under `identifiers` (`type: swh`).
- [ ] **Research Software Directory**: add the project at
  <https://research-software-directory.org> ("+", then "New Software"). Give it the
  concept DOI, so it lists each new release and imports the contributors.
- [ ] **OpenSSF Best Practices badge**: fill in the questionnaire at
  <https://www.bestpractices.dev/en/projects/new>
  and add the badge it gives you to the README.
