#!/opt/homebrew/bin/python3.13
"""macOS: WKWebView + 内嵌 HTTP 服务 → URL Scheme 回调"""
import json, os, socket, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from Foundation import NSObject, NSURL
from AppKit import NSApplication, NSWindow
import WebKit

AID = "197104175"
RESULT_FILE = "/tmp/captcha_result.txt"

# --- 读 TCaptcha.js ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
for p in [os.path.join(SCRIPT_DIR, "TCaptcha.js"), "/tmp/TCaptcha.js"]:
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            tcaptcha_js = f.read()
        break
else:
    tcaptcha_js = ""

HTML = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{height:100vh;display:flex;justify-content:center;align-items:center;
flex-direction:column;background:#f5f7fa;font-family:-apple-system,sans-serif}}
#msg{{color:#2d3748;font-size:15px;margin-bottom:16px}}
#status{{color:#718096;font-size:12px;margin-top:8px}}
</style></head><body>
<div id="msg">加载中...</div><div id="cap"></div><div id="status"></div>
<script>{tcaptcha_js}</script>
<script>
try{{
    var c = new TencentCaptcha({json.dumps(AID)}, function(r){{
        if(r.ret===0){{
            window.location.href="captcha_callback://done?ticket="
                +encodeURIComponent(r.ticket)+"&randstr="+encodeURIComponent(r.randstr);
        }}else{{
            document.getElementById("cap").innerHTML=
                "<p style='color:#e53e3e;margin-top:40px'>验证未通过 (code:"+r.ret+")</p>";
            document.getElementById("msg").textContent="";
        }}
    }});
    document.getElementById('msg').textContent='请完成安全验证';
    c.show();
}}catch(e){{
    document.getElementById('msg').textContent='错误';
    document.getElementById('status').textContent=e.message;
}}
</script></body></html>"""


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


class NavDelegate(NSObject):
    def webView_decidePolicyForNavigationAction_decisionHandler_(self, wv, action, handler):
        u = action.request().URL().absoluteString() if action.request().URL() else ""
        if u.startswith("captcha_callback://done?"):
            qs = u.replace("captcha_callback://done?", "")
            with open(RESULT_FILE, "w") as f:
                f.write(qs)
            NSApplication.sharedApplication().terminate_(None)
            return
        handler(1)


def main():
    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"

    server = HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(0)

    rect = ((300, 300), (460, 460))
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, 15, 2, False
    )
    win.setTitle_("安全验证 (腾讯云)")
    win.center()

    prefs = WebKit.WKPreferences.alloc().init()
    prefs.setJavaScriptEnabled_(True)
    config = WebKit.WKWebViewConfiguration.alloc().init()
    config.setPreferences_(prefs)

    wv = WebKit.WKWebView.alloc().initWithFrame_configuration_(
        ((0, 0), (460, 430)), config
    )
    wv.setNavigationDelegate_(NavDelegate.alloc().init())
    wv.loadRequest_(WebKit.NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))

    win.setContentView_(wv)
    win.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)

    from PyObjCTools import AppHelper
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
