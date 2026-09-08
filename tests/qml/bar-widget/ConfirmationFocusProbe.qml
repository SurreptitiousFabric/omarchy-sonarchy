import QtQuick
import QtTest
import Quickshell
import qs.Commons
import qs.Ui

FloatingWindow {
  id: window
  implicitWidth: 620
  implicitHeight: 820
  visible: true

  QtObject {
    id: fakeService
    property bool actionBusy: false
    property bool alarmsLoading: false
    property var deviceDetails: ({})
    property var devices: [{uid:"room",name:"Test room",online:true}]
    property var rooms: devices
    property var liveFavorites: ({items:[]})
    property var alarms: [{id:"a",room_uid:"room",room:"Test room",time:"08:00",enabled:false,recurrence:"DAILY",volume:10}]
    property int deletions: 0
    function hasCapability(operation) { return true }
    function refreshDetails() {}
    function loadAlarms() {}
    function ensureFavorites() {}
    function deleteAlarm(id) { if(id!=="a") throw new Error("Wrong alarm"); deletions++ }
  }
  Item {
    id: host
    anchors.fill: parent
    Button { id: header; text:"Fixed header"; focusable:true }
    SonarchySystemPage {
      id: page
      y: 50
      width: 324
      height: 314
      service: fakeService
      device: ({uid:"room",name:"Test room",volume:10})
    }
    TestCase { id: input; when:false }
    property var failures: []
    function check(ok,message) { if(!ok) failures=failures.concat([message]) }
    function find(owner,predicate) {
      if(predicate(owner)) return owner
      var children=owner.children || []
      for(var i=0;i<children.length;i++) { var found=find(children[i],predicate);if(found)return found }
      return null
    }
    function visibleHeight(control) {
      var point=control.mapToItem(page,0,0)
      return Math.max(0,Math.min(page.height,point.y+control.height)-Math.max(0,point.y))
    }
    function run() {
      for(var size of [{width:324,height:314},{width:584,height:614}]) {
        page.width=size.width;page.height=size.height
        page.confirmation="";fakeService.deletions=0
        input.wait(150)
        var button=find(page,function(c){return c.tooltipText==="Delete alarm"})
        if(!button)throw new Error("Missing Delete alarm")
        button.forceActiveFocus();page.ensureVisible(button);input.wait(100)
        check(button.activeFocus && visibleHeight(button)===button.height,"initial focus visibility "+size.width)
        input.keyClick(Qt.Key_Return);input.wait(150)
        check(page.confirmation==="alarm-delete:a","keyboard first press did not arm")
        check(button.activeFocus,"arming changed focus")
        check(visibleHeight(button)===button.height,"confirmation clipped "+size.width+": "+visibleHeight(button)+"/"+button.height)
        check(fakeService.deletions===0,"first press deleted alarm")
        console.log("CONFIRM_FOCUS_CASE",size.width,visibleHeight(button),button.height)
        input.wait(5100)
        check(page.confirmation==="","original confirmation timer did not expire")
        check(button.activeFocus && fakeService.deletions===0,"expiry changed focus or deleted alarm")
        // A deliberate second press still invokes the exact action once.
        input.keyClick(Qt.Key_Return);input.wait(100)
        input.keyClick(Qt.Key_Return);input.wait(100)
        check(page.confirmation==="" && fakeService.deletions===1,"second press dispatch changed")
        // Unrelated fixed-header focus must not be pulled into the page on growth.
        var flick=find(page,function(c){return c.contentY!==undefined && c.contentHeight!==undefined})
        header.forceActiveFocus();var before=flick.contentY
        page.confirmation="alarm-delete:a";input.wait(150)
        check(header.activeFocus && flick.contentY===before,"layout growth moved fixed-header focus/scroll")
      }
      console.log(failures.length===0?"CONFIRM_FOCUS_PASS":"CONFIRM_FOCUS_FAIL",JSON.stringify(failures))
      Qt.quit()
    }
    Timer { interval:300;running:true;onTriggered:{try{host.run()}catch(error){console.log("CONFIRM_FOCUS_FAIL",String(error));Qt.quit()}} }
  }
}
