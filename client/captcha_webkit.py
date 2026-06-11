#!/usr/bin/env python3
"""macOS: 独立子进程 — 本地 HTTP 服务 + WKWebView 弹窗 → 写 /tmp/captcha_result.txt 后退出"""
import sys, json, socket, threading, os, time
import objc, WebKit, AppKit
from PyObjCTools import AppHelper
from http.server import HTTPServer, BaseHTTPRequestHandler

aid = "197104175"
RESULT_FILE = "/tmp/captcha_result.txt"

HTML_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://t.captcha.qq.com/TCaptcha.js"></script>
</head>
<body style="margin:0;padding:0;height:100vh;display:flex;
justify-content:center;align-items:center;flex-direction:column;
background:#f5f7fa;font-family:-apple-system,sans-serif">
<div id="msg" style="color:#2d3748;font-size:15px;margin-bottom:16px">请完成安全验证</div>
<div id="cap"></div>
<script>
try {
  new TencentCaptcha(%s, function(r){
    if(r.ret===0){
      window.location.href="/done?ticket="+encodeURIComponent(r.ticket)+
        "&randstr="+encodeURIComponent(r.randstr);
    }else{
      document.getElementById("cap").innerHTML=
        "<p style='color:#e53e3e;font-size:16px;margin-top:40px'>验证未通过 (code:"+r.ret+")</p>"+
        "<p style='color:#718096;font-size:12px'>请关闭窗口，稍后重试</p>";
    }
  }).show();
} catch(e) {
  document.getElementById("msg").textContent="加载失败: "+e.message;
}
</script></body></html>""" % json.dumps(aid)

# Start local HTTP server
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/done?"):
            qs = self.path[6:]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK - you may close this window")
            with open(RESULT_FILE, "w") as f:
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

# Wait for server to be ready
import urllib.request
url = f"http://127.0.0.1:{port}/"
for _ in range(30):
    try:
        urllib.request.urlopen(url, timeout=0.1)
        break
    except:
        time.sleep(0.1)

# Create WKWebView window
app = AppKit.NSApplication.sharedApplication()
win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    ((400, 300), (440, 400)),
    AppKit.NSTitledWindowMask | AppKit.NSClosableWindowMask | AppKit.NSMiniaturizableWindowMask,
    AppKit.NSBackingStoreBuffered, False
)
win.setTitle_("安全验证 (腾讯云)")
win.center()

wv = WebKit.WKWebView.alloc().initWithFrame_configuration_(
    ((0, 0), (440, 370)),
    WebKit.WKWebViewConfiguration.alloc().init()
)
win.setContentView_(wv)

from Foundation import NSURL, NSURLRequest
wv.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))

# Poll for done
def check():
    if os.path.exists(RESULT_FILE):
        httpd.shutdown()
        AppKit.NSApplication.sharedApplication().terminate_(None)
    else:
        AppHelper.callAfter(0.3, check)

AppHelper.callAfter(0.5, check)
win.makeKeyAndOrderFront_(None)
app.activateIgnoringOtherApps_(True)
AppHelper.runEventLoop()
