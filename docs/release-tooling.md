# Release tooling & provenance

This file records the third-party tools used **only** to build, verify, and
prepare NATURE Agent Validator releases in CI (`.github/workflows/ci.yml`).

**None of them is a runtime, optional, or build-backend dependency of the
package.** `pyproject.toml` declares zero `dependencies`, an empty `dev` extra,
and keeps the `setuptools.build_meta` backend. The product `NOTICE` file is
intentionally left NATURE-only: Apache-2.0 §4(d) attribution covers material
distributed *in* the work, and none of this tooling ships with the package.

## GitHub Actions (pinned to a full commit SHA)

| Action | Version | Commit SHA | License |
| --- | --- | --- | --- |
| `actions/checkout` | v7.0.0 | `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0` | MIT |
| `actions/setup-python` | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` | MIT |

## Python CLI tools (exact version pin, `build` job only)

| Tool | Version | License | Purpose |
| --- | --- | --- | --- |
| PyPA `build` | 1.6.0 | MIT | Build the sdist and wheel through the declared PEP 517 backend |
| `sbom4python` | 0.12.6 | Apache-2.0 | Generate an SPDX JSON SBOM for the installed NATURE distribution |

`build` provisions the declared build backend (`setuptools>=77`) in an isolated
environment. `sbom4python` and its dependency closure are installed into a
throwaway virtual environment; that closure is resolved from PyPI at CI time
and printed to the CI log (`pip list` step). Nothing here is vendored into this
repository, and no `sbom4python` source is copied in.

### SPDX License List attribution (CC-BY-3.0)

`sbom4python` (via `lib4sbom`) relies on data derived from the **SPDX License
List** <https://spdx.org/licenses/>. Portions of the SPDX License List are
published by the Linux Foundation under **CC-BY-3.0**. The SPDX license
identifiers that appear in a generated SBOM originate from that list; this
attribution is recorded here.

## Explicitly out of scope

No signing, no build/artifact attestation or provenance statements, no upload
of the SBOM (or any artifact) to an external service, no GitHub Release, no
PyPI publication, no Git tags, no release automation. The workflow only proves
that these release-preparation artifacts can be generated and independently
verified.
