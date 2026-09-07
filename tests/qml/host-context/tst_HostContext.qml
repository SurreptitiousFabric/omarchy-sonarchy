import QtQuick
import QtTest

Item {
  id: root

  Component {
    id: fixture

    Item {
      id: sample
      // Unrelated legacy host shapes; neither inherits the built-in Bar.
      property QtObject hostA: QtObject {
        property string fontFamily: "host-a"
        property color foreground: "#123456"
        property color barForeground: "#234567"
        property bool vertical: false
        property int barSize: 30
      }
      property Item hostB: Item {
        property string fontFamily: "host-b"
        property color foreground: "#345678"
        property color barForeground: "#456789"
        property bool vertical: true
        property int barSize: 50
      }
      property QtObject serviceA: QtObject {}
      property QtObject serviceB: QtObject {}
      // Registry.qml contains the installed shell's pure serviceFor function.
      property Registry registryA: Registry {
        _services: ({"io.github.surreptitiousfabric.sonarchy": sample.serviceA})
      }
      property Registry registryB: Registry {
        _services: ({"io.github.surreptitiousfabric.sonarchy": sample.serviceB})
      }
      property BarHostContext contextA: BarHostContext {
        inputHost: sample.hostA
        inputFontFamily: sample.hostA.fontFamily
        inputForeground: sample.hostA.foreground
        inputBarForeground: sample.hostA.barForeground
        inputVertical: sample.hostA.vertical
        inputBarSize: sample.hostA.barSize
        serviceLookup: function(pluginId) { return sample.registryA.serviceFor(pluginId) }
      }
      property BarHostContext contextB: BarHostContext {
        inputHost: sample.hostB
        inputFontFamily: sample.hostB.fontFamily
        inputForeground: sample.hostB.foreground
        inputBarForeground: sample.hostB.barForeground
        inputVertical: sample.hostB.vertical
        inputBarSize: sample.hostB.barSize
        serviceLookup: function(pluginId) { return sample.registryB.serviceFor(pluginId) }
      }
      property HostConsumer consumer: HostConsumer {
        bar: sample.hostA
        hostContext: sample.contextA
        fallbackFontFamily: "fallback"
        fallbackForeground: "#abcdef"
        fallbackBarForeground: "#fedcba"
        fallbackBarSize: 20
      }
    }
  }

  TestCase {
    name: "HostContext"
    property var sample

    function init() {
      sample = createTemporaryObject(fixture, root)
      verify(sample !== null)
    }

    function verifyFallback() {
      compare(sample.consumer.activeContext, null)
      compare(sample.consumer.service, null)
      compare(sample.consumer.fontFamily, sample.consumer.fallbackFontFamily)
      compare(sample.consumer.foreground, sample.consumer.fallbackForeground)
      compare(sample.consumer.barForeground, sample.consumer.fallbackBarForeground)
      compare(sample.consumer.barSize, sample.consumer.fallbackBarSize)
      compare(sample.consumer.vertical, false)
    }

    function verifyHostB() {
      compare(sample.consumer.bar, sample.hostB)
      compare(sample.consumer.activeContext, sample.contextB)
      compare(sample.consumer.service, sample.serviceB)
      compare(sample.consumer.fontFamily, "host-b")
      verify(Qt.colorEqual(sample.consumer.foreground, "#345678"))
      verify(Qt.colorEqual(sample.consumer.barForeground, "#456789"))
      compare(sample.consumer.barSize, 50)
      compare(sample.consumer.vertical, true)
    }

    function test_live_bindings() {
      compare(sample.consumer.bar, sample.hostA)
      compare(sample.consumer.fontFamily, "host-a")
      compare(sample.consumer.service, sample.serviceA)
      sample.hostA.fontFamily = "updated-a"
      sample.hostA.foreground = "#56789a"
      sample.hostA.barForeground = "#6789ab"
      sample.hostA.barSize = 42
      sample.hostA.vertical = true
      compare(sample.consumer.fontFamily, "updated-a")
      verify(Qt.colorEqual(sample.consumer.foreground, "#56789a"))
      verify(Qt.colorEqual(sample.consumer.barForeground, "#6789ab"))
      compare(sample.consumer.barSize, 42)
      compare(sample.consumer.vertical, true)
    }

    function test_bar_replaced_first() {
      sample.consumer.bar = sample.hostB
      verifyFallback()
      sample.consumer.hostContext = sample.contextB
      verifyHostB()
      sample.hostA.fontFamily = "old-host-change"
      sample.registryA._services = ({})
      compare(sample.consumer.fontFamily, "host-b")
      compare(sample.consumer.service, sample.serviceB)
      sample.hostB.fontFamily = "new-host-change"
      compare(sample.consumer.fontFamily, "new-host-change")
    }

    function test_context_replaced_first() {
      sample.consumer.hostContext = sample.contextB
      verifyFallback()
      sample.consumer.bar = sample.hostB
      verifyHostB()
    }

    function test_null_host_and_context() {
      sample.consumer.bar = null
      verifyFallback()
      sample.consumer.fallbackFontFamily = "live-fallback"
      sample.consumer.fallbackForeground = "#112233"
      sample.consumer.fallbackBarForeground = "#334455"
      sample.consumer.fallbackBarSize = 24
      verifyFallback()
      sample.consumer.bar = sample.hostA
      compare(sample.consumer.service, sample.serviceA)
      sample.consumer.hostContext = null
      verifyFallback()
    }

    function test_null_context_owner_does_not_call_lookup() {
      sample.contextA.inputHost = null
      const calls = []
      sample.contextA.serviceLookup = function(_pluginId) {
        calls.push(true)
        return sample.serviceA
      }
      verifyFallback()
      compare(sample.contextA.serviceFor("anything"), null)
      compare(calls.length, 0)
    }

    function test_registry_updates_and_unknown_service() {
      sample.registryA._services = ({"io.github.surreptitiousfabric.sonarchy": sample.serviceB})
      compare(sample.consumer.service, sample.serviceB)
      sample.consumer.moduleName = "unknown.plugin"
      compare(sample.consumer.service, null)
      sample.consumer.moduleName = "io.github.surreptitiousfabric.sonarchy"
      compare(sample.consumer.service, sample.serviceB)
      sample.registryA._services = ({})
      compare(sample.consumer.service, null)
    }

    function test_unavailable_lookup() {
      for (const value of [null, undefined, false, 1, "not-callable", ({}), []]) {
        sample.contextA.serviceLookup = value
        compare(sample.consumer.service, null)
      }
      sample.contextA.serviceLookup = function(_pluginId) { throw new Error("fixture") }
      compare(sample.consumer.service, null)
    }

    function test_invalid_service_value() {
      for (const value of [null, undefined, false, 1, "not-a-service", ({}), []]) {
        sample.registryA._services = ({"io.github.surreptitiousfabric.sonarchy": value})
        compare(sample.consumer.service, null)
      }
      sample.registryA._services = ({"io.github.surreptitiousfabric.sonarchy": sample.serviceA})
      compare(sample.consumer.service, sample.serviceA)
    }

    function test_readonly_view_preserves_writable_legacy_host() {
      const changes = [
        ["host", null], ["fontFamily", "override"], ["foreground", "#abcdef"],
        ["barForeground", "#abcdef"], ["vertical", true], ["barSize", 99]
      ]
      for (const change of changes) {
        let rejected = false
        try { sample.contextA[change[0]] = change[1] } catch (error) { rejected = true }
        verify(rejected, change[0] + " must be readonly")
      }
      sample.hostA.fontFamily = "legacy-write"
      compare(sample.consumer.fontFamily, "legacy-write")
    }
  }
}
