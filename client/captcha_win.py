#!/usr/bin/env python3
"""Windows: 独立子进程 — 本地 HTTP 服务 + pywebview(Edge WebView2) → 写 %TEMP%/lol_captcha_result.txt 后退出"""
import sys, json, socket, threading, os, time, tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler

aid = "197104175"
RESULT_FILE = os.path.join(tempfile.gettempdir(), "lol_captcha_result.txt")

HTML_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://t.captcha.qq.com/TCaptcha.js"></script>
</head>
<body style="margin:0;padding:0;height:100vh;display:flex;
justify-content:center;align-items:center;flex-direction:column;
background:#f5f7fa;font-family:Microsoft YaHei,sans-serif">
<div id="msg" style="color:#2d3748;font-size:15px;margin-bottom:16px">请完成安全验证</div>
<div id="cap"></div>
<script>
try{new TencentCaptcha(%s,function(r){
if(r.ret===0){window.location.href="/done?ticket="+encodeURIComponent(r.ticket)+
"&randstr="+encodeURIComponent(r.randstr)}else{document.getElementById("cap").innerHTML=
"<p style='color:#e53e3e;font-size:16px;margin-top:40px'>验证未通过 (code:"+r.ret+")</p>"+
"<p style='color:#718096;font-size:12px'>请关闭窗口重试</p>"}
}).show()}catch(e){document.getElementById("msg").textContent="加载失败: "+e.message}
</script></body></html>""" % json.dumps(aid)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/done?"):
            qs = self.path[6:]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
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
httpd.timeout = 1
thr = threading.Thread(target=httpd.serve_forever, daemon=True)
thr.start()

url = f"http://127.0.0.1:{port}/"

# Verify server up
import urllib.request
for _ in range(30):
    try:
        urllib.request.urlopen(url, timeout=0.1)
        break
    except:
        time.sleep(0.1)

import webview
done = [False]

def on_closed():
    done[0] = True

w = webview.create_window("安全验证 (腾讯云)", url,
                          width=440, height=420, resizable=False, on_top=True)
w.events.closed += on_closed

# Tick until done or timeout
def tick():
    tick.c += 1
    if done[0] or tick.c > 480:  # 120s
        w.destroy()
tick.c = 0

webview.start(func=tick)
httpd.shutdown()
