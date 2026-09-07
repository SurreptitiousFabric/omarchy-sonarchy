### Repository URL

https://github.com/SurreptitiousFabric/omarchy-sonarchy

### Category

Hardware

### Tags

media, bar, ai

### Suggest a missing tag

_No response_

### Maintainer notes

OWNER-REVIEW DRAFT ONLY — release remains on HOLD. Do not submit this draft
until the exact release candidate passes all applicable gates and the owner
explicitly confirms every checklist statement and approves the final title,
body, preview, permanent ID and commit.

Sonarchy is an independent, MIT-licensed, keyboard-first Quickshell controller
for local Sonos systems. Plugin ID: `io.github.surreptitiousfabric.sonarchy`.
It is not made, sponsored or endorsed by Sonos. `preview.png` is an isolated
Queue/navigation demonstration with invented data and test theme/control
visuals, not a screenshot of an installed household or release acceptance.
See `docs/marketplace-preparation.md` for asset provenance and the dated registry
check; repeat the ID check immediately before submission.

Dependencies: Omarchy/Quickshell/Qt, stable CPython 3.14.x (floor 3.14.0), and
the exact hash-locked runtime dependencies, including SoCo 0.31.2. First start
creates a private data-directory virtual environment and downloads pinned,
hashed packages from PyPI. There is no plugin-add install hook, sudo or global
Python installation. Environment health checks and safe promotion are described
in README; installed upgrade/lifecycle acceptance remains a separate gate.
Removal leaves the private environment and small state/cache directories for
explicit owner cleanup. MIT and third-party notices are in the repository.

Network: local Sonos discovery/control, a bounded LAN event-notification
listener, public Apple/Global Player catalog requests and permitted artwork
retrieval. No HTTP control API. Optional radio artwork enrichment sends the
current title/artist to Apple's public catalog and can be disabled. The backend
owns an owner-only Unix socket; a stdio MCP adapter uses a narrow allowlist.
Read-only is the default. Independently enabled, reviewed/preflighted tools
support exact Apple-song Sonos Playlist creation and bounded native Sonos
Playlist playback. Creation does not start playback. There are no general MCP
transport/volume/grouping or arbitrary URI/command tools. A connected AI client
may process read data remotely; local MCP transport is not a local-AI guarantee.

Apple catalog matches do not prove household playback rights or exact recording
acceptance. There is no private Apple-library access or arbitrary queue
restoration guarantee; nonempty/unverifiable destructive replacements are
refused. Device/source-specific and installed keyboard/lifecycle acceptance
remain incomplete. See ACCEPTANCE_TESTS.md, PRIVACY.md and CAPABILITIES.md.

A fresh exact-commit marketplace baseline and authorized maintainer decision
are required before listing. Hash-locked pip bootstrap is a declared
package-manager capability for review; do not treat a historical scan or this
draft as current verification. Plugins execute unsandboxed upstream code;
listing approval is not certification or a security audit.

### Submission checklist

- [ ] The repository is public and contains installation and removal instructions.
- [ ] I have documented the plugin license and any external dependencies.
- [ ] I confirm that I own or have permission to submit this plugin and its preview assets.
- [ ] The plugin does not overwrite user configuration without explicit consent.
- [ ] I understand that approval is for listing and is not a security review.
