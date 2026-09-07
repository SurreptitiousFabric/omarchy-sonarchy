# Proposed spacing-role platform contract

This is the device-free proposal for release dependency #119. It is not an
accepted or installed API, and does not complete #88, #89 or the combined #64
release gate. Upstream submission, supported-platform adoption and installed
changes require separately scoped authority under [ADR 0004](adr/0004-qml-platform-type-contract.md).

## Actual declaration and reproducer

The reference host is aarch64, omarchy-dev `4.0.0.r6589.gdec29fa-1`,
quickshell-git `0.3.0.r20.g28771c7-1`, Qt declarative `6.11.2-1`.
Installed `Commons/Style.qml` SHA-256 is
`f5901092617ae62645597199270afd4dfb0644d596bdfff16e1834fca6ad7243`.
It declares `readonly property QtObject spacing: QtObject { ... }`.
Strict lint against the real installed imports cannot see these actual members:

```qml
import QtQuick
import qs.Commons
QtObject {
  property int hairline: Style.spacing.hairline
  property int labelGap: Style.spacing.labelGap
}
```

Both accesses report `missing-property`. The anonymous object's declaration
contains a readonly real `scale` and these readonly integer roles:

| Roles | Defaults at scale 1 |
| --- | --- |
| hairline, xxs, xs, sm, md, lg, xl, xxl, xxxl, huge | 1, 2, 3, 4, 6, 8, 10, 12, 14, 18 |
| controlGap, controlPaddingX, controlPaddingY, inputPaddingY | 8, 10, 6, 7 |
| controlHeight, popupRowHeight, dropdownWidth, searchableDropdownWidth | 28, 28, 240, 260 |
| numberFieldWidth, searchablePopupMinHeight | 120, 220 |
| rowGap, rowPaddingX, labelGap, panelGap, panelPadding, popupPadding | 8, 12, 4, 14, 18, 14 |

The effective scale follows spacing scale and, when enabled, font scale. Valid
nonnegative numeric overrides are rounded and bypass scaling. Negative or
nonnumeric overrides fall back to scaled defaults. Positive fractional pixel
values round to at least one; zero scale produces zero fallback spacing.
`hairline` uses the scaling helper directly and ignores dictionary overrides.

## Minimal platform-owned proposal

Export `SpacingRoles` from the real Commons module and type the actual
`Style.spacing` property and instance with it. Preserve every existing public
role name, type, readonly output and notification. For example:

```qml
// SpacingRoles.qml: illustrative subset, not an installed API.
import QtQuick
QtObject {
  required property real input_scale
  required property int input_labelGap
  readonly property real scale: input_scale
  readonly property int labelGap: input_labelGap
}
// In Style.qml, bind every input to its existing expression:
// readonly property SpacingRoles spacing: SpacingRoles {
//   input_scale: root.effectiveSpacingScale
//   input_labelGap: root.spacingToken("label-gap", 4)
// }
```

Input naming, visibility and ownership need upstream review. The prototype
establishes feasibility, not a compatibility promise for these illustrative
input names. Production consumers retain `Style.spacing.labelGap` and all
other existing paths. Do not duplicate theme calculations in Sonarchy, cast
anonymous instances to a nominal local type, erase static checks or suppress
warnings to make a candidate pass.

## Required proof and adoption boundary

Run the focused probes on the recorded platform:

```bash
SONARCHY_PLATFORM_TESTS=1 mise exec -- python -m pytest -q tests/test_qml_type_contract.py -k spacing
```

The real-import probe performs static analysis without instantiating Style.
The isolated runtime probes extract the actual spacing declaration, effective
scale expression and pure `spaceReal`, `space`, and `spacingToken` helpers.
Only underlying scalar/dictionary inputs are fixtures; the live singleton and
its host-query startup are never run. These probes verify every role's default,
live scale/font changes, per-role rounded overrides, invalid override fallback,
minimum-pixel behavior and readonly assignment rejection.

The full extracted anonymous declaration fails strict consumer lint, while the
named proposal passes it and the same runtime checks. Deliberate removed,
mistyped, writable and frozen roles must fail the contract. A misspelled
consumer property must still fail named-proposal lint. This is declaration and
binding evidence, not full installed theme-reload acceptance.

The required clean-candidate `mise run validate-platform` includes these probes
in its control stage. Their expected reproduction of the current type failure
does not excuse any shipped QML diagnostic: real root-file lint remains strict.
Before adoption, record an accepted build's source, exports, versions and
digests, verify its real declarations and runtime behavior, and prove the
spacing diagnostics disappear. The combined candidate must independently pass
the complete gate. Until then #119 and release acceptance remain open.
