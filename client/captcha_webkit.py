#!/opt/homebrew/bin/python3.13
"""验证码：本地 HTTP 服务 + 打开默认浏览器 → 回调捕获 → 写结果文件"""
import json, os, socket, webbrowser, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

AID = "197104175"
RESULT_FILE = "/tmp/captcha_result.txt"

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
<style>*{{margin:0;padding:0;box-sizing:border-box}}
body{{height:100vh;display:flex;justify-content:center;align-items:center;
flex-direction:column;background:#f5f7fa;font-family:-apple-system,sans-serif}}
#msg{{color:#2d3748;font-size:15px;margin-bottom:16px}}
</style></head><body>
<div id="msg">加载中...</div><div id="cap"></div>
<script>{tcaptcha_js}</script>
<script>
try{{
    var c=new TencentCaptcha({json.dumps(AID)},function(r){{
        if(r.ret===0){{
            window.location.href=
                "/done?ticket="+encodeURIComponent(r.ticket)+
                "&randstr="+encodeURIComponent(r.randstr)
        }}else{{
            document.getElementById("cap").innerHTML=
                "<p style='color:#e53e3e;margin-top:40px'>验证未通过</p>"
            document.getElementById("msg").textContent=""
        }}
    }})
    document.getElementById("msg").textContent="请完成安全验证"
    c.show()
}}catch(e){{document.getElementById("msg").textContent="错误: "+e.message}}
</script></body></html>"""


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
        elif p.path == "/done":
            qs = parse_qs(p.query)
            ticket = qs.get("ticket", [""])[0]
            randstr = qs.get("randstr", [""])[0]
            with open(RESULT_FILE, "w") as f:
                f.write(f"ticket={ticket}&randstr={randstr}")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body style='font-family:sans-serif;text-align:center;padding-top:100px'>"
                             b"<h2 style='color:#48bb78'>验证完成</h2><p>请关闭此页面</p>"
                             b"<script>window.close()</script></body></html>")
            # 延迟退出避免浏览器连接断开
            threading.Thread(target=self._delayed_exit, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def _delayed_exit(self):
        import time
        time.sleep(0.5)
        os._exit(0)

    def log_message(self, fmt, *args):
        pass


def main():
    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"
    
    server = HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    
    # 打开默认浏览器
    webbrowser.open(url)
    
    # 阻塞直到服务器退出（由 /done 回调触发）
    try:
        while server:
            import time
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
