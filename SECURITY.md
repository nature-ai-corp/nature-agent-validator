# Security Policy

NATURE Agent Validator is in **Alpha preparation** ahead of its first public
open-source release. Interfaces, the scenario format, and behaviour may still
change. We take security issues seriously.

## Supported versions

| Version | Supported |
| ------- | --------- |
| `0.1.0a1` (current Alpha) | Yes — fixes land on the latest Alpha/pre-release only |
| Any earlier / unreleased state | No |

During Alpha there are no long-term support branches. Security fixes are made
against the current development line and included in the next pre-release.

## Reporting a vulnerability

**Do not disclose suspected vulnerabilities publicly.** Do not open a public
issue, pull request, or discussion describing an unfixed vulnerability.

At this stage the project repository is not yet public and no private
vulnerability reporting channel is available yet:

- **Now (pre-release):** there is no reporting mechanism you can use yet. If
  you have discovered a potential issue, please hold the details privately and
  do not publish, share, or demonstrate them. Once the reporting channel below
  is enabled you can submit your findings through it.
- **After the public OSS release:** the released public repository will enable
  **GitHub Private Vulnerability Reporting** (the "Report a vulnerability"
  button under the repository's **Security** tab / Security Advisories). That
  will be the authorized channel for private reports, keeping them confidential
  to the maintainers until a coordinated fix is available.

This project does not publish a dedicated security contact email address.

### Please also

- Do not publicly disclose an issue before a fix is released and you have
  coordinated a disclosure timeline with the maintainers.
- Do not test against systems or data you do not own or are not authorized to
  test.

## What to include

When a reporting channel is available, a useful report generally contains:

- affected version / commit (`nav --version`, or the Git SHA)
- component (adapter, assertions, evidence, suite, reporting, configuration,
  authoring, CLI)
- a clear description of the issue and its security impact
- minimal reproduction steps, a scenario/environment file, or a short script
- expected vs. actual behaviour
- any relevant environment details (Python version, OS)

Please redact real secrets and any confidential data from your report.

## Response expectations

As an Alpha project maintained on a best-effort basis, we do **not** commit to
a specific acknowledgement, response, or remediation timeline. We will credit
reporters who wish to be acknowledged once a fix is public.
