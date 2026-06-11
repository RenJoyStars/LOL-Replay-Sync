#!/opt/homebrew/bin/python3.13
"""macOS: 独立子进程 — WKWebView 直注 HTML → 拦截 URL Scheme → 写结果文件"""
import json, os
from Foundation import NSObject, NSURL
from AppKit import NSApplication, NSWindow
import WebKit

AID = "197104175"
RESULT_FILE = "/tmp/captcha_result.txt"

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://t.captcha.qq.com/TCaptcha.js"></script>
</head>
<body style="margin:0;padding:0;height:100vh;display:flex;
justify-content:center;align-items:center;flex-direction:column;
background:#f5f7fa;font-family:-apple-system,sans-serif">
<div id="msg" style="color:#2d3748;font-size:15px;margin-bottom:16px">请完成安全验证</div>
<div id="cap"></div>
<script>
try{var c=new TencentCaptcha(%s,function(r){
if(r.ret===0){window.location.href=
"captcha_callback://done?ticket="+encodeURIComponent(r.ticket)+
"&randstr="+encodeURIComponent(r.randstr)}else{
document.getElementById("cap").innerHTML=
"<p style='color:#e53e3e;font-size:16px;margin-top:40px'>验证未通过 (code:"+r.ret+")</p>"+
"<p style='color:#718096;font-size:12px'>请关闭窗口重试</p>"}
});c.show()}catch(e){document.getElementById("msg").textContent="加载失败: "+e.message}
</script></body></html>""" % json.dumps(AID)


class NavDelegate(NSObject):
    """拦截 captcha_callback://done?... 写入结果文件并退出"""
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
    app.setActivationPolicy_(0)  # NSApplicationActivationPolicyRegular

    rect = ((300, 300), (460, 460))
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, 15, 2, False
    )
    win.setTitle_("安全验证 (腾讯云)")
    win.center()

    config = WebKit.WKWebViewConfiguration.alloc().init()
    wv = WebKit.WKWebView.alloc().initWithFrame_configuration_(
        ((0, 0), (460, 430)), config
    )
    wv.setNavigationDelegate_(NavDelegate.alloc().init())

    # 直注 HTML，baseURL 用腾讯域名让 TCaptcha.js 同域加载
    base = NSURL.URLWithString_("https://t.captcha.qq.com/")
    wv.loadHTMLString_baseURL_(HTML, base)

    win.setContentView_(wv)
    win.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)

    from PyObjCTools import AppHelper
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
