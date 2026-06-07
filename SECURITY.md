# Security Policy

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**
A public report discloses the problem before a fix is available.

Instead, report privately through GitHub's built-in private vulnerability
reporting:

1. Go to the [Security tab](https://github.com/dandriscoll/devlogs/security) of
   this repository.
2. Click **Report a vulnerability** and fill in the advisory form.

This opens a private channel with the maintainer. Please include:

- a description of the issue and its impact,
- steps to reproduce (or a proof of concept),
- affected version(s),
- any suggested remediation.

You can expect an initial acknowledgement, and we'll keep you updated as the fix
progresses. Once a fix ships, we're happy to credit you in the release notes if
you'd like.

## Supported versions

devlogs is an actively developed development tool; fixes land on the latest
`2.4.x` release line. Please upgrade to the latest version before reporting, in
case the issue is already resolved.

## Scope notes

devlogs is intended for **development** environments and is typically guarded so
it only runs outside production. Connection strings can contain OpenSearch
credentials — keep `.env`/`.env.devlogs` files out of version control (the
provided `.gitignore` already excludes them) and prefer `devlogs mkurl` to build
properly encoded URLs without pasting secrets into shell history.
