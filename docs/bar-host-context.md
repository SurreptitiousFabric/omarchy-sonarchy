# Bar-host context proposal

Status: device-free prototype for #96, following [ADR 0004](adr/0004-qml-platform-type-contract.md).
This is not an installed Omarchy API or a production Sonarchy migration.

## Observed reads

Sonarchy's root `BarWidget.qml` reads the following host surface. The installed
`Ui.BarWidget` declares `bar` as nullable `QtObject`; its concrete built-in host
is `plugins/bar/Bar.qml`. A compatible custom host need not inherit that type.

| Read | Current declaration / use | Current unavailable behavior |
| --- | --- | --- |
| `bar.shell.serviceFor(pluginId)` | Built-in `shell` is `var`; Sonarchy requests its own service ID | Null host/shell returns null; callability is not checked |
| `bar.fontFamily` | Built-in writable `string`; panel and glyph fonts | Some reads use `Style.font.family`; several panel reads are unguarded |
| `bar.foreground` | Built-in writable bound `color`; panel foreground | Null host falls back to `Color.popups.text` |
| `bar.barForeground` | Built-in writable bound `color`; bar glyph foreground | Null host falls back to `Color.foreground` |
| inherited `vertical` | Base forwards host `bool` | Null host becomes false |
| inherited `barSize` | Base forwards host `int` | Null host uses `Style.bar.sizeHorizontal` |

These existing guards do not validate missing members on a non-null custom
host. The generic base also provides `broadcast` and `setting`; those methods,
arbitrary host operations and settings are outside this context's scope.
The inventory test checks the actual Sonarchy reads and installed declarations;
it does not instantiate the built-in host or claim its full compatibility.

## Additive API and ownership

The real named [BarHostContext.qml](../tests/qml/host-context/BarHostContext.qml)
prototype exposes this read view:

| Member | Type | Ownership / behavior |
| --- | --- | --- |
| `host` | readonly `QtObject`, nullable | Identity of the generic host this context belongs to |
| `fontFamily` | readonly `string` | Live view of the owner's font family |
| `foreground`, `barForeground` | readonly `color` | Live views of their distinct host colors |
| `vertical` | readonly `bool` | Live host orientation |
| `barSize` | readonly `int` | Live host bar thickness |
| `serviceFor(pluginId)` | `string` → `QtObject` or null | Validated lookup only; never creates a service |

The owner supplies required typed `inputHost`, `inputFontFamily`,
`inputForeground`, `inputBarForeground`, `inputVertical` and `inputBarSize`
bindings. Keep those bindings live: copying values at startup or assigning over
them disconnects later host changes. Qt documents this distinction in
[property bindings](https://doc.qt.io/qt-6/qtqml-syntax-propertybinding.html).
The readonly view does not change the existing host's writable font/color
properties. Input properties remain writable QML properties: owner-only use is
a design convention, not access control. Their final visibility/names require
platform review.

Only the `serviceLookup` capability is deliberately `var`. The owner supplies a
pure function that reads a registry; absent, non-callable or throwing lookup
returns null. A non-QObject result is rejected using `instanceof QtObject`.
A null owner suppresses lookup entirely. This validates object identity/type,
not the returned service's application methods or authorization; a future
Sonarchy-service contract remains a separate boundary. The context is for
trusted in-process QML, not a security sandbox.

Bindings also depend on properties read inside the lookup function. The runtime
probe reuses the exact installed shell `serviceFor` declaration against a
test-owned `_services` dictionary and checks registry replacement/removal.
The owner must emit changes: replacing the dictionary is observable; silently
mutating a JavaScript dictionary in place is not the supported notification
contract. No `ensureService`, shell startup, network or installed registry is run.

## Compatibility and replacement

A platform could add nullable `property BarHostContext hostContext: null` beside
the existing `property QtObject bar: null`, without narrowing or replacing
`bar`. Existing widgets could continue using `bar`; custom hosts could supply
the named context through typed live bindings without inheriting the built-in
Bar. The host/platform owns each context's lifetime and its registry binding.

[HostConsumer.qml](../tests/qml/host-context/HostConsumer.qml) demonstrates a
consumer that accepts both properties and uses the context only when
`hostContext.host === bar` and both exist. Replacing either one first produces
fallback values and no service until the new pair agrees. Null host/context
behaves the same way. It never dispatches through the previous host's registry
during a mismatch. Fallback font/colors/size are typed, owner-supplied live
inputs; fallback orientation is false.

This prototype consumer deliberately does not dynamically inspect legacy host
fields when the context is unavailable. Adopting it unchanged on an old host
would lose service access. Therefore production migration must either require
an accepted platform context contract or separately design and verify a legacy
adapter. Merely adding the optional property would not migrate Sonarchy.
The two unrelated test host shapes establish the proposal's binding behavior,
not compatibility with every installed/custom host. Host destruction and full
shell reload acceptance belong to that separately authorized adoption work.

## Device-free verification and limits

Run on the recorded development host:

```bash
SONARCHY_PLATFORM_TESTS=1 mise exec -- python -m pytest -q tests/test_qml_type_contract.py
```

The existing required platform-control module runs scoped strict lint on the
actual proposed type and consumer, with no qmltypes fiction, casts or warning
suppression. A misspelled typed property must fail. Offscreen Qt tests cover
live font/colors/geometry, both replacement orders, nulls, readonly output,
writable legacy fields, missing/invalid lookup and service replacement/removal.
Frozen font/color outputs and a removed identity guard must fail the runtime
checks. Test fixtures use deterministic objects; the installed pure lookup is
extracted only after its body passes a purity-shape assertion.

Generic Python CI skips this host-gated module honestly. The fixture subdirectory
is not part of the standalone component runner. Run the explicit command above
or the full platform gate to exercise it. No live Style/Color singleton, built-in
bar, desktop restart, speaker discovery or speaker mutation is involved.

Reference evidence: aarch64, omarchy-dev `4.0.0.r6589.gdec29fa-1`,
quickshell-git `0.3.0.r20.g28771c7-1`, Qt declarative `6.11.2-1`.
Observed installed source SHA-256 values:

```text
Ui/BarWidget.qml     8be00e2553a486b3dbfcb4f99de976035f323c4061b993dbc1842c75ff8b9022
plugins/bar/Bar.qml  8bbe27ad7c617da1a3770fd5731b8cc79935ac34f04873c3933f7ff581a7cb15
shell.qml           9f1db77dcc3c111ceccc860ac472d19b35d385958a63d270ea51e413ab86f1f0
```

Omarchy owns any exported platform contract and compatibility promise. Upstream
submission, installed-system changes and production adoption require separate
scope and authority. #95 owns theme-role adoption; #87–#89 retain their complete
zero-warning criteria, and #64/#48 remain incomplete/HOLD until the exact real
release candidate passes the combined platform gate. This prototype does not
turn that gate green or waive its existing diagnostics.
