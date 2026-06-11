#!/opt/homebrew/bin/python3.13
"""macOS: 独立子进程 — WKWebView 内嵌 TCaptcha.js → URL Scheme 回调 → 写结果文件"""
import json, os
from Foundation import NSObject, NSURL
from AppKit import NSApplication, NSWindow
import WebKit

AID = "197104175"
RESULT_FILE = "/tmp/captcha_result.txt"

# --- 读取内嵌 TCaptcha.js ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TCAPTCHA_PATH = os.path.join(SCRIPT_DIR, "TCaptcha.js")
if not os.path.exists(TCAPTCHA_PATH):
    TCAPTCHA_PATH = "/tmp/TCaptcha.js"
with open(TCAPTCHA_PATH, "r", encoding="utf-8") as f:
    tcaptcha_js = f.read()

HTML = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{height:100vh;display:flex;justify-content:center;align-items:center;
flex-direction:column;background:#f5f7fa;font-family:-apple-system,sans-serif}}
#msg{{color:#2d3748;font-size:15px;margin-bottom:16px}}
#status{{color:#718096;font-size:12px;margin-top:8px}}
</style>
</head><body>
<div id="msg">加载中...</div>
<div id="cap"></div>
<div id="status"></div>
<script>
// WKWebView loadHTMLString 下 document.domain 为空，TCaptcha 用它构造 sdk url 会失败
Object.defineProperty(document, 'domain', {{
    get: function(){{ return 't.captcha.qq.com'; }},
    configurable: true
}});
</script>
<script>{tcaptcha_js}</script>
<script>
try{{
    document.getElementById('msg').textContent = '请完成安全验证';
    document.getElementById('status').textContent = 'TCaptcha.js ' + (typeof TencentCaptcha === 'function' ? '✓' : '✗');
    var c = new TencentCaptcha({json.dumps(AID)}, function(r){{
        if (r.ret === 0) {{
            window.location.href =
                "captcha_callback://done?ticket=" + encodeURIComponent(r.ticket) +
                "&randstr=" + encodeURIComponent(r.randstr);
        }} else {{
            document.getElementById("cap").innerHTML =
                "<p style='color:#e53e3e;font-size:16px;margin-top:40px'>验证未通过 (code:" + r.ret + ")</p>" +
                "<p style='color:#718096;font-size:12px'>请关闭窗口重试</p>";
        }}
    }});
    c.show();
}} catch(e) {{
    document.getElementById('msg').textContent = '加载失败';
    document.getElementById('status').textContent = e.message;
}}
</script></body></html>"""


class NavDelegate(NSObject):
    def webView_decidePolicyForNavigationAction_decisionHandler_(self, wv, action, handler):
        u = action.request().URL().absoluteString() if action.request().URL() else ""
        if u.startswith("captcha_callback://done?"):
            qs = u.replace("captcha_callback://done?", "")
            with open(RESULT_FILE, "w") as f:
                f.write(qs)
            NSApplication.sharedApplication().terminate_(None)
            return
        handler(1)  # WKNavigationActionPolicyAllow


def main():
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

    base = NSURL.URLWithString_("https://t.captcha.qq.com/")
    wv.loadHTMLString_baseURL_(HTML, base)

    win.setContentView_(wv)
    win.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)

    from PyObjCTools import AppHelper
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
