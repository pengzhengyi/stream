# Security policy

## Supported versions

medleyplay is in early development and hasn't published a release yet. Security
fixes apply to the latest commit on the default branch.

## Reporting a vulnerability

Please don't report security vulnerabilities in public issues. Use GitHub's
private vulnerability reporting instead: open the repository's **Security** tab,
choose **Report a vulnerability**, and submit the report. GitHub notifies the
maintainer without making the details public.

Include:

- The affected version or commit.
- Reproduction steps.
- Expected and actual behavior.
- The potential impact.
- Any suggested fix or mitigation.

To report a conduct problem rather than a vulnerability, see the
[Code of Conduct](CODE_OF_CONDUCT.md#enforcement).

## What medleyplay treats as sensitive

- **Site logins.** medleyplay can use your own Bilibili login cookies to reach
  higher-quality audio. They stay on the machine that runs the server, are never
  sent anywhere but the site they belong to, and are never served to other
  devices. Never paste cookies into an issue or a log excerpt.
- **The local network.** The server is meant for a trusted home network. A way
  for another device to read files outside the music library, or to make the
  server fetch an address that isn't a supported music site, is a vulnerability.
