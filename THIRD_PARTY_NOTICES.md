# Third-party notices

## OmaSonos

The persistent event backend, its QML process-management pattern, and related
tests are derived from **OmaSonos 0.2.1** by **ctl0v0**, source revision
`fa098ac4c24b1732fd120a93c83491cd4b73f0ab`.

Source: <https://github.com/ctl0v0/omasonos>

OmaSonos is licensed under the MIT License. The original notice is preserved
at [LICENSES/OMASONOS-MIT.txt](LICENSES/OMASONOS-MIT.txt). Local changes include
plugin identity and paths, exact-room selection, LAN/IP and artwork hardening,
TuneIn fetch restrictions, bonded-component filtering, and integration with
the existing controller's queue, search, rename, and sound features.

## Runtime Python dependencies

The plugin installs its runtime dependencies from the hash-locked
`requirements.lock`. They are not copied into this repository. Their own
licenses remain in force; the principal project is
[SoCo](https://github.com/SoCo/SoCo), the Python Sonos controller library.

The complete direct and transitive runtime set for version 4.1.0 is:

| Package | Version | License |
|---|---:|---|
| appdirs | 1.4.4 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| charset-normalizer | 3.5.1 | MIT |
| defusedxml | 0.7.1 | PSFL |
| idna | 3.19 | BSD-3-Clause |
| ifaddr | 0.2.0 | MIT |
| lxml | 6.1.2 | BSD-3-Clause |
| requests | 2.34.2 | Apache-2.0 |
| SoCo | 0.31.2 | MIT |
| urllib3 | 2.7.0 | MIT |
| xmltodict | 1.0.4 | MIT |

Package metadata and source/license links are available from the corresponding
PyPI project pages and installed distribution metadata.
