# Security Policy

NATURE Agent Validator is at an early **Alpha** stage (`0.1.0a1`). Interfaces,
the scenario format, and behaviour may still change. We take security issues
seriously.

## Supported versions

| Version | Supported |
| ------- | --------- |
| `0.1.0a1` (current Alpha) | Yes — fixes land on the latest Alpha/pre-release only |
| Any earlier / unreleased state | No |

During Alpha there are no long-term support branches. Security fixes are made
against the current development line and included in the next pre-release.

## Reporting a vulnerability

Report suspected vulnerabilities **privately**. Do not open a public issue,
pull request, or discussion for an unfixed vulnerability, and do not publish,
share, or demonstrate the details.

Where to report:

- If this repository has **GitHub Private Vulnerability Reporting** enabled,
  use it: the **Security** tab -> *"Report a vulnerability"* (Security
  Advisories). That is the authorized private channel; reports stay
  confidential to the maintainers until a coordinated fix is available.
- If private reporting is not available to you -- for example the repository is
  not yet public, or the feature is not enabled -- do **not** disclose the
  issue publicly. Hold the details privately until the channel above is
  available, then submit them there.

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
