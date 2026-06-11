# 验证码优化：WKWebView 直注 HTML + URL Scheme 拦截

**时间**: 2026-06-11 13:11 CST

## 目标
优化 `captcha_webkit.py`，去掉 HTTP 服务器中间层，减少验证码弹窗的冷启动延迟。

## 方案
- **之前**: Python 启动一个本地 HTTP 服务器 → WKWebView 加载 `http://localhost:...` → JS 写 page title → Python 轮询 title
- **现在**: WKWebView 直注 HTML（`loadHTMLString_baseURL_`）→ 拦截 `captcha_callback://done?ticket=...&randstr=...` URL Scheme → 直接写 `/tmp/captcha_result.txt` → `NSApp.terminate` 退出

## 关键修复

### 1. pyobjc 安装问题
- 系统 Python (`/usr/bin/python3`) 无法编译 pyobjc-core，之前安装的 pyobjc 实际在 Homebrew Python 3.13 (`/opt/homebrew/bin/python3.13`)
- 用 `--break-system-packages` 重新安装 pyobjc-framework-WebKit 到 Homebrew Python

### 2. launch_captcha_webkit Python 路径
- `client.py` 中更新 `launch_captcha_webkit`：Mac 优先搜索 `/opt/homebrew/bin/python3.13`，回退 `sys.executable`

### 3. WKNavigationDelegate 协议
- PyObjC 中不能直接 `class NavDelegate(WebKit.WKNavigationDelegate)`，需继承 `NSObject` 并实现 `webView_decidePolicyForNavigationAction_decisionHandler_` 方法
- `setNavigationDelegate_` 接受任何响应对应 selector 的 NSObject

## 文件变更
- `client/captcha_webkit.py` — 完全重写（直注 HTML + URL Scheme 拦截）
- `client/client.py` — `launch_captcha_webkit` 子进程 Python 路径选择
- 已提交 `d8036de` 并推送到 `RenJoyStars/LOL-Replay-Sync`

## 验证
- WKWebView 窗口正常启动（4秒未退出 ✅）
- 验证码完成后的 ticket 传递路径：URL Scheme → 文件写入 → QTimer 轮询 → 客户端解析 — 逻辑链完整
