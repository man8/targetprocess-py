# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Pre-release commits before 0.1.0 | No |

Security fixes are released as a patch on the latest minor version. Once a new
minor is released the previous minor receives no further fixes; upgrade rather
than wait.

## Reporting a vulnerability

Email louis@man8.com with the subject `targetprocess-py security report`. Do
not open a public GitHub issue for a suspected vulnerability, and do not
disclose it publicly until a fix has been released.

Include a description, the affected version(s), steps to reproduce or a proof
of concept, and the impact you believe it has. A suggested fix is welcome but
not required.

What to expect:

- Acknowledgement within 3 business days.
- An assessment and, where a fix is needed, a target date within 10 business
  days of acknowledgement.
- A fix released as a patch version and a GitHub security advisory, crediting
  the reporter unless anonymity is preferred. The aim is to ship a fix within
  90 days of the report; a simple fix ships much sooner.

## Scope

In scope: anything in this repository that could expose a caller's credentials
or data, or let a third party influence what the client does. Examples: an
`access_token` reaching a log record the library emits, a `Next` URL sending a
request (and the credential it carries) to another host, a sanitisation gap
that lets a real token, host or personal data into a committed cassette, and a
dependency with a known vulnerability.

Out of scope: vulnerabilities in TargetProcess itself (report those to the
vendor), and issues in the application that embeds this library, such as where
it stores its token.

## Operational notes for users

- The token travels as a URL query parameter, which is TargetProcess's only
  token scheme, so it can surface in server, proxy and HTTP-client logs. Do not
  enable httpx request-URL logging in production; the library's own logger
  scrubs the token from the records it emits.
- Prefer a `READONLY` client wherever writes are not needed.
- Keep the library and its dependencies current. Dependabot and `pip-audit`
  run on this repository, and releases note security fixes in
  [CHANGELOG.md](CHANGELOG.md).
