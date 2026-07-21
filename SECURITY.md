# Security Policy

## Supported Versions

Only the latest tagged release receives security patches. Pre-release and development builds are not supported.

## Reporting a Vulnerability

Open a GitHub Security Advisory at **[github.com/edgardo1997/AIVO/security/advisories/new](https://github.com/edgardo1997/AIVO/security/advisories/new)**.

Reports should include:
- Affected version and component
- Steps to reproduce (proof of concept preferred)
- Impact assessment
- Suggested remediation (optional)

You will receive an acknowledgment within 72 hours and a status update at least every 30 days.

## Disclosure

We follow **Coordinated Disclosure**: a fix will be released before the vulnerability is publicly
announced. The default embargo period is 90 days from the initial report.

## Scope

This policy covers the Sentinel application and its published release artifacts (installer, sidecar
binary, updater). It does **not** cover dependencies (report those to their respective maintainers)
or the Tauri framework itself.

## Plugin Publisher Trust

Plugins downloaded from a remote URL must include a SHA-256 content checksum and an Ed25519
publisher signature. Sentinel accepts the plugin only when `publisher_key_id` exists in the JSON
object stored at `SENTINEL_PLUGIN_TRUSTED_KEYS_FILE`. Each value is a base64-encoded raw Ed25519
public key. If the variable is unset, Sentinel reads
`%LOCALAPPDATA%\Sentinel\trusted-plugin-publishers.json`.

Local ZIP installation remains available for development, but an unsigned plugin is reported as
untrusted and runs in the isolated plugin process. A plugin that declares a signature but fails
verification is never loaded.

## Safe Harbor

Research conducted under this policy is authorized and we will not pursue legal action. You must:
- Make a good-faith effort to avoid privacy violations and service disruption
- Not access or modify data beyond what is necessary to demonstrate the vulnerability
- Delete any data collected during research after reporting
- Not conduct denial-of-service, social engineering, or physical attacks

## Recognition

We maintain a public acknowledgments list for verified reporters who request it.
