import QtQuick
import QtTest
import "."

Item {
  Consumer { id: consumer }
  TestCase {
    name: "SpacingContract"
    function verifyDefaults(scale) {
      compare(consumer.scale, scale)
      for (var role in consumer.defaults)
        compare(consumer[role], consumer.defaults[role] * scale, role)
    }
    function test_live_scaling_overrides_rounding_and_readonly_roles() {
      verifyDefaults(1)
      consumer.provider.spacingScale = 2
      verifyDefaults(2)
      consumer.provider.fontScale = 1.5
      verifyDefaults(3)
      consumer.provider.spacingOverrides = ({
        "label-gap": 3.6, "control-height": 27.2, "row-gap": -1,
        "xs": "invalid", "hairline": 99
      })
      compare(consumer.labelGap, 4)
      compare(consumer.controlHeight, 27)
      compare(consumer.rowGap, 24)
      compare(consumer.xs, 9)
      compare(consumer.hairline, 3)
      consumer.provider.spacingScaleWithFont = false
      compare(consumer.scale, 2)
      compare(consumer.rowGap, 16)
      compare(consumer.labelGap, 4)
      compare(consumer.controlHeight, 27)
      consumer.provider.spacingOverrides = ({})
      verifyDefaults(2)
      var overrides = ({})
      var expected = ({hairline: 2})
      var sentinel = 100
      for (var role in consumer.defaults) {
        if (role !== "hairline") {
          var key = role.replace(/[A-Z]/g, function(letter) { return "-" + letter.toLowerCase() })
          overrides[key] = sentinel + 0.6
          expected[role] = sentinel + 1
          sentinel += 7
        }
      }
      consumer.provider.spacingOverrides = overrides
      for (var role in consumer.defaults)
        compare(consumer[role], expected[role], role)
      consumer.provider.spacingOverrides = ({})
      consumer.provider.spacingScale = 0
      verifyDefaults(0)
      consumer.provider.spacingScale = 0.1
      compare(consumer.hairline, 1)
      compare(consumer.labelGap, 1)
      compare(consumer.huge, 2)
      consumer.provider.spacingScale = 1
      verifyDefaults(1)

      var roles = Object.keys(consumer.defaults).concat(["scale"])
      for (var role of roles) {
        var rejected = false
        try { consumer.provider.spacing[role] = 123 }
        catch (error) { rejected = true }
        verify(rejected, "Role must remain readonly: " + role)
      }
      verify(consumer.provider.spacing.genuinelyMissing === undefined)
    }
  }
}
