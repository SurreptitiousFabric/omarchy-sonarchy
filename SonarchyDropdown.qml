import qs.Ui

Dropdown {
  id: root

  property bool focusable: true
  property bool keyboardOwnsFocus: true

  signal clicked()

  activeFocusOnTab: focusable
  hasCursor: activeFocus
  onClicked: toggle()
}
