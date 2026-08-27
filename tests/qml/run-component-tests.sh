#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
QML_TEST_RUNNER="/usr/lib/qt6/bin/qmltestrunner"
OMARCHY_SLIDER="/usr/share/omarchy/shell/Ui/PanelSlider.qml"

[[ -x "$QML_TEST_RUNNER" ]] || {
  echo "qmltestrunner is unavailable: $QML_TEST_RUNNER" >&2
  exit 1
}
[[ -f "$OMARCHY_SLIDER" ]] || {
  echo "Omarchy PanelSlider is unavailable: $OMARCHY_SLIDER" >&2
  exit 1
}

TEST_ROOT="$(mktemp -d /tmp/sonarchy-component-test.XXXXXX)"
cleanup() {
  rm -rf -- "$TEST_ROOT"
}
trap cleanup EXIT

mkdir -p "$TEST_ROOT/imports" "$TEST_ROOT/tests"
cp -R "$PROJECT_ROOT/tests/qml/imports/." "$TEST_ROOT/imports/"
ln -s "$OMARCHY_SLIDER" "$TEST_ROOT/imports/qs/Ui/PanelSlider.qml"
for component in SonarchyAlarmDraft.qml SonarchyContentState.qml SonarchyErrorState.qml SonarchySlider.qml; do
  ln -s "$PROJECT_ROOT/$component" "$TEST_ROOT/tests/$component"
done
for test_file in "$PROJECT_ROOT"/tests/qml/tst_*.qml; do
  ln -s "$test_file" "$TEST_ROOT/tests/$(basename -- "$test_file")"
done

env -u QT_QPA_PLATFORMTHEME \
  QT_QPA_PLATFORM=offscreen \
  QT_STYLE_OVERRIDE=Fusion \
  QT_QUICK_CONTROLS_STYLE=Basic \
  "$QML_TEST_RUNNER" \
  -input "$TEST_ROOT/tests" \
  -import "$TEST_ROOT/imports"
