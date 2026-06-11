# 验证码修复：pywebview 独立子进程方案

**时间**: 2026-06-11 13:18–15:42 CST

## 问题演进

| 阶段 | 方案 | 结果 |
|------|------|------|
| v1 | WKWebView + `loadHTMLString` | origin null，TCaptcha iframe 跨域阻断 → 空白 |
| v2 | WKWebView + 内嵌 TCaptcha.js + patch document.domain | 仍空白，iframe 跨域通信被阻止 |
| v3 | WKWebView + 内嵌 HTTP 服务器 (localhost origin) | TCaptcha 不渲染 |
| v4 | 浏览器方案 (webbrowser.open) | 用户不接受 |
| v5 | **pywebview 独立子进程** ✅ | 一体化原生窗口，正常工作 |

## 最终方案
- `captcha_webkit.py` 使用 pywebview 创建原生 macOS WebView 窗口
- 本地 HTTP 服务器 (127.0.0.1:随机端口) 服务验证码页面
- TCaptcha.js 内嵌在 HTML 中，避免 CDN 加载
- 验证完成后 fetch `/done` 端点 → 服务端写结果文件 → 子进程退出
- 客户端通过 QEventLoop + QTimer 非阻塞轮询结果文件

## 同时修复的 client.py 问题
1. `show_login()` 返回 login_win 引用防止 GC 回收（main() 持有）
2. `main()` 样式表丢失修复（去掉重复的 setStyleSheet/setStyle("Fusion") 冲突）
3. `show_file_manager` 按钮创建合并为统一的一套（修复无英雄时按钮缺失）
4. `do_register` 重复状态行删除
5. `focusInEvent` 死代码修复
6. `import subprocess` 误删修复
7. 子进程 stderr 捕获调试

## 关键文件
- `client/captcha_webkit.py` — pywebview 验证码子进程
- `client/client.py` — 修复后的客户端
- 依赖：pywebview 6.2.1 安装在系统 Python 3.9

## 验证
- 用户确认登录流程正常 ✅
