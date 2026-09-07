# ADR 0004: preserve real QML platform types

Status: proposed for acceptance with #91. No production API change in this ADR.

## Decision

Prefer platform-owned named theme-role types at the actual Omarchy property
declarations. Preserve existing `Style.font.family/body/...` and
`Color.popups.text/...` access paths, notifications and readonly semantics.
Do not pretend the currently installed anonymous objects are instances of a
locally declared nominal type. Until an accepted platform build provides the
contract, keep the strict release gate failed for these diagnostics.

For host access, prepare an additive typed host context rather than narrowing
legacy `Ui.BarWidget.bar` to the built-in bar implementation. This requires a
separate bounded prototype because custom bar hosts and dynamic service lookup
must remain supported. No host API is changed by this decision.

## Evidence and reproducer

Reference platform: aarch64, omarchy-dev `4.0.0.r6589.gdec29fa-1`,
quickshell-git `0.3.0.r20.g28771c7-1`, Qt declarative `6.11.2-1`.

Installed `Commons/qmldir` exports Style, Color, Border and Util singletons,
but no public named font/popup-role types. `Style.qml` declares `font` and
`Color.qml` declares `popups` as `QtObject`. `Ui/BarWidget.qml` similarly
declares `bar` as `QtObject`; the concrete built-in bar lives under
`plugins/bar/Bar.qml`, not a general public host interface.

This minimal consumer, linted with real installed qs modules, reports two
missing-property warnings even though the concrete declarations contain those
members:

```qml
import QtQuick
import qs.Commons
QtObject {
  property string family: Style.font.family
  property color text: Color.popups.text
}
```

Run the device-free probes with:

```bash
SONARCHY_PLATFORM_TESTS=1 mise exec -- python -m pytest -q tests/test_qml_type_contract.py
```

The required `mise run validate-platform` job includes this module alongside
`tests/test_platform_host.py`; a probe failure fails its required control stage.
The targeted command above is for development, not a substitute for the full
clean-candidate platform gate.

The first probe lints real installed modules without instantiating them, then
checks popup text at runtime using the actual `Color.qml` popup declaration and
pure `pick` lookup helper. Deterministic palette/dictionary inputs verify that
text exists, follows fallback and theme-value changes, and remains writable.
The unrelated composed background/border colors use fixture inputs; this does
not test their composition algorithms. Removed/renamed text, readonly text and
a frozen text value must fail the same probe, even when the static diagnostic
categories are unchanged. The live Color singleton is never instantiated.

The font runtime probe extracts the actual font-role declaration expressions from
installed Style.qml and supplies only deterministic underlying theme inputs.
It verifies existing roles, a genuinely absent property, live family/size
updates and readonly assignment rejection. It deliberately does not instantiate
the full Style singleton, whose startup invokes host-query helpers. This is
evidence for declaration/binding semantics, not a full theme reload acceptance
test. The named-role prototype passes strict lint and the same runtime checks.

## Minimal upstream proposal

Introduce an exported `FontRoles` type with explicit property types. Preserve
public readonly role names, with bound inputs initialized by Style rather than
copying values at startup. The following is illustrative, not a shipped API:

```qml
// FontRoles.qml
import QtQuick
QtObject {
  required property string input_family
  required property int input_body
  readonly property string family: input_family
  readonly property int body: input_body
}
```

Style's declaration becomes `readonly property FontRoles font: FontRoles { ... }`,
with `input_family: root.fontFamily` and the existing body expression bound to
`input_body`. Apply the same principle to every existing role, retaining types
and notifications. Input names/visibility need upstream review; the prototype
only establishes feasibility and readonly output behavior. For `PopupRoles`,
preserve the current writable color-role semantics rather than assuming they
are readonly because the containing object property is readonly.

The [named host-context prototype](../bar-host-context.md) for #96 specifies
typed live font/color/geometry views, a generic owner identity and a validated
dynamic service lookup. It preserves legacy `bar` rather than casting it,
tests nulls and both replacement orders, and keeps missing-property lint useful.
It is not a shipped API: platform export, legacy-host migration and production
adoption need separately authorized scope and an accepted platform contract.

## Rejected alternatives and ownership

- Broad `var` aliases, bracket access, category suppression or warning baselines
  merely hide misspellings as well as current type limitations.
- Fake qmltypes lie about the installed API. Nominal casts to a newly invented
  local role type do not make anonymous upstream objects instances of it.
- Frozen local role copies lose theme-change notifications. A dynamic projection
  could retain bindings but would still require a reviewed dynamic boundary;
  it is not selected here simply to produce a green gate.
- Importing/casting the built-in Bar directly couples the plugin to one bar
  implementation and does not preserve arbitrary compatible custom hosts.

Omarchy owns the named platform API and its compatibility guarantees. Sonarchy
owns its minimum supported platform declaration and reruns real-import/runtime
contract checks on every proposed platform update. Upstream submission or
installed-system changes require separately scoped authority; this ADR is only
a local proposal. No platform upgrade is performed automatically.

## Follow-up boundaries

#95 owns accepted theme-role platform adoption and real-build verification.
#119 separately scopes the [spacing-role contract](../spacing-role-contract.md),
including its actual-declaration proof and named-type proposal.
#96 owns only the typed host-context prototype/decision. #87–#89 retain all
zero-warning acceptance criteria; delegate context, page `ensureVisible`
dispatch and window-focus typing are distinct from theme/host role types.
#64 remains incomplete until the combined real candidate passes its full gate.

The distinction between declared object types, custom property types and live
bindings follows [Qt's property documentation](https://doc.qt.io/qt-6/qtqml-syntax-objectattributes.html).
The probes, not documentation alone, establish behavior on this recorded host.
