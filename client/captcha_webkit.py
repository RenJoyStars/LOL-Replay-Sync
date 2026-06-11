#!/usr/bin/env python3
"""macOS WKWebView + local HTTP server -> Tencent CAPTCHA"""
import sys, json, socket, threading
import objc, WebKit, AppKit
from PyObjCTools import AppHelper
from http.server import HTTPServer, BaseHTTPRequestHandler

aid = "197104175"
result_file = "/tmp/captcha_result.txt"

HTML_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://t.captcha.qq.com/TCaptcha.js"></script>
</head>
<body style="display:flex;justify-content:center;align-items:center;
height:100vh;flex-direction:column;background:#f5f7fa;margin:0;
font-family:-apple-system,sans-serif">
<div style="color:#2d3748;font-size:14px;margin-bottom:16px">请完成安全验证</div>
<div id="cap"></div>
<script>
try {
  new TencentCaptcha("%s", function(r){
    if(r.ret===0) {
      window.location.href="/done?ticket="+encodeURIComponent(r.ticket)+
        "&randstr="+encodeURIComponent(r.randstr);
    } else {
      document.getElementById("cap").innerHTML=
        '<p style="color:#e53e3e">验证取消，请关闭窗口重试</p>';
    }
  }).show();
} catch(e) {
  document.getElementById("cap").innerHTML=
    '<p style="color:#e53e3e">验证码加载失败: '+e.message+'</p>';
}
</script>
</body></html>""" % aid

# Start local HTTP server on random port
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/done?"):
            qs = self.path[6:]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK - you may close this window")
            with open(result_file, "w") as f:
                f.write(qs)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))
    def log_message(self, *a): pass

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
httpd = HTTPServer(("127.0.0.1", port), Handler)
thr = threading.Thread(target=httpd.serve_forever, daemon=True)
thr.start()

# Create WKWebView window
app = AppKit.NSApplication.sharedApplication()
win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    ((400, 300), (440, 400)),
    AppKit.NSTitledWindowMask | AppKit.NSClosableWindowMask | AppKit.NSMiniaturizableWindowMask,
    AppKit.NSBackingStoreBuffered, False
)
win.setTitle_("安全验证 (腾讯云)")
win.center()
wv = WebKit.WKWebView.alloc().initWithFrame_configuration_(((0, 0), (440, 370)),
    WebKit.WKWebViewConfiguration.alloc().init())
win.setContentView_(wv)

url = "http://127.0.0.1:%d/" % port
from Foundation import NSURL, NSURLRequest
req = NSURLRequest.requestWithURL_(NSURL.URLWithString_(url))
wv.loadRequest_(req)

# Poll for done signal
def check():
    import os
    if os.path.exists(result_file):
        httpd.shutdown()
        AppKit.NSApplication.sharedApplication().terminate_(None)
    else:
        AppHelper.callAfter(0.3, check)

AppHelper.callAfter(0.5, check)
win.makeKeyAndOrderFront_(None)
app.activateIgnoringOtherApps_(True)
AppHelper.runEventLoop()
