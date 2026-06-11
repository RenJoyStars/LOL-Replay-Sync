#!/usr/bin/env python3
"""macOS native WKWebView captcha window - uses system WebKit, zero bundling"""
import sys, json
import objc, WebKit, AppKit
from PyObjCTools import AppHelper

app = AppKit.NSApplication.sharedApplication()
win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    ((400,300),(420,380)),
    AppKit.NSTitledWindowMask | AppKit.NSClosableWindowMask | AppKit.NSMiniaturizableWindowMask,
    AppKit.NSBackingStoreBuffered, False
)
win.setTitle_("安全验证 (腾讯云)")
win.center()
config = WebKit.WKWebViewConfiguration.alloc().init()
wv = WebKit.WKWebView.alloc().initWithFrame_configuration_(((0,0),(420,350)), config)
win.setContentView_(wv)

aid = "197104175"
html = '<!DOCTYPE html><html><head><meta charset="utf-8"><script src="https://ssl.captcha.qq.com/TCaptcha.js"></script></head><body style="display:flex;justify-content:center;align-items:center;height:100vh;flex-direction:column;background:#f5f7fa;margin:0;font-family:-apple-system,sans-serif"><div style="color:#2d3748;font-size:13px;margin-bottom:12px">\u8bf7\u5b8c\u6210\u5b89\u5168\u9a8c\u8bc1</div><div id=c></div><script>new TencentCaptcha('%(aid)s',function(r){if(r.ret===0){document.title="CAPTCHA_DONE:ticket="+encodeURIComponent(r.ticket)+"&randstr="+encodeURIComponent(r.randstr);}}).show()</script></body></html>' % {"aid": aid}

wv.loadHTMLString_baseURL_(html, None)

def check():
    t = wv.title()
    if t and t.startswith("CAPTCHA_DONE:"):
        r = t.replace("CAPTCHA_DONE:", "")
        with open("/tmp/captcha_result.txt","w") as f:
            f.write(r)
        win.close()
        app.terminate_(None)
    else:
        AppHelper.callAfter(0.3, check)

AppHelper.callAfter(0.5, check)
win.makeKeyAndOrderFront_(None)
app.activateIgnoringOtherApps_(True)
AppHelper.runEventLoop()
