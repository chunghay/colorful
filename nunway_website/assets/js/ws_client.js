// Websocket endpoint for hub server.
var wsuri = "ws://ec2-54-200-22-181.us-west-2.compute.amazonaws.com:9000";

var sock = null;

window.onload = function() {
  console.log("loaded");
  sock = new WebSocket(wsuri);

  sock.onopen = function() {
    console.log("connected to " + wsuri);
  };

  sock.onclose = function(e) {
    console.log("connection closed (" + e.code + ")");
  };

  sock.onerror = function(e) {
    console.log("connection error (" + e.code + ")");
  };

  sock.onmessage = function(e) {
    console.log("message received: " + e.data);
    //$("#colorTxt").text(e.data);

    var obj = JSON.parse(e.data);
    $("body").css('background-color', "rgb(" + obj.red + ", " + obj.green + ", " + obj.blue + ")");
  };
};
