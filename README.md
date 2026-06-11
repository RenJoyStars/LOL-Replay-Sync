# 英雄联盟对局文件同步助手 (LOL Replay Sync)

🎮 自动监控并上传英雄联盟对局回放文件（.rofl）到云端服务器，支持多设备同步、回放、云端管理。

---

## 📥 下载

从 [Releases 页面](https://github.com/RenJoyStars/LOL-Replay-Sync/releases) 下载最新版本：

| 平台 | 文件 | 说明 |
|------|------|------|
| 🍎 **Mac (Apple Silicon)** | `LOLReplaySync-v0.4-mac-arm64.dmg` | M 系列芯片 |
| 🪟 **Windows** | `LOLReplaySync-v0.4-win.exe` | 所有 Windows |

> **Mac 首次打开提示"来自身份不明的开发者"**：右键 App →「打开」→ 点「打开」即可。

---

## ✨ 功能

### 核心同步
- **自动同步** — 监听对局文件夹，新 .rofl 文件自动上传到云端
- **一键下载** — 勾选云端文件，一键下载所有缺失的对局到本地
- **多设备共享** — 换台电脑登录即拉取，朋友共享对局录像

### 对局回放
- **云端回放** — 点击「▶ 回放」直接调用 LOL 客户端播放云端录像
- **版本智能匹配** — 自动检测客户端精确版本号（通过 LCU API 获取 `16.12.785.1316`），版本不匹配时提示
- **自动下载到回放目录** — 回放文件自动放入正确的 Replays 目录

### 数据解析
- **ROFL 元数据解析** — 自动解析 RIOT 二进制格式，显示：对局模式、地图、时长、版本号、红蓝双方英雄阵容
- **国服英雄中文名** — 完整中文英雄名映射，红蓝方分两行清晰展示
- **批量解析** — 勾选多个文件一键解析所有对局信息
- **版本联动** — 解析 ROFL 文件后自动更新主页面游戏版本号

### 云端管理
- **文件列表** — 查看所有云端文件，显示文件名、大小、对局信息、英雄阵容
- **日期筛选** — 按日期范围筛选对局
- **模式/版本筛选** — 按游戏模式或版本号过滤
- **勾选批量操作** — 支持批量下载、批量解析、批量删除
- **下载/删除/重命名** — 单个文件操作

### 安全
- **腾讯云验证码** — 登录/注册需完成人机验证，防止暴力破解
- **IP 限流** — 服务端每分钟最多 8 次请求，超限自动封禁
- **自动登录** — 记住密码 + 自动登录，已登录用户跳过验证码

### 界面
- **同步进度** — 同步按钮变黄色 + 实时进度计数
- **悬浮提示** — 按钮悬停显示详细说明
- **系统托盘** — 最小化到托盘后台运行，自定义图标
- **游戏版本状态** — 绿色（精确）/ 黄色（模糊）/ 红色（无法识别）
- **全中文界面**

---

## 🌐 服务器

**地址：** `175.178.183.14:5050`

腾讯云 Ubuntu + Supervisor 部署，开箱即用。注册后立即可用，用户数据独立存储。

---

## 🏗️ 技术栈

| 组件 | 技术 |
|------|------|
| 客户端 | Python + PySide6 |
| 服务端 | Python + Flask + SQLite |
| 打包 | Nuitka 编译为原生可执行文件 |
| 验证码 | 腾讯云 CAPTCHA（pywebview 跨平台方案） |
| 部署 | 腾讯云 Ubuntu + Supervisor |
| CI/CD | GitHub Actions 自动编译 |

---

## 🔧 自行编译

### macOS (Apple Silicon)

```bash
pip install PySide6 requests watchdog nuitka pillow pywebview
python -m nuitka --standalone --macos-create-app-bundle \
    --enable-plugin=pyside6 --output-dir=dist \
    --macos-app-name="英雄联盟对局文件助手" \
    --macos-app-version="0.4" \
    --macos-app-icon=client/icon.icns \
    --assume-yes-for-downloads \
    client/client.py
```

### Windows

```bash
pip install PySide6 requests watchdog nuitka pywebview
# 先编译验证码助手
python -m nuitka --standalone --onefile --windows-console-mode=disable \
    --output-dir=dist --output-filename=captcha_helper.exe \
    --assume-yes-for-downloads client/captcha_win.py
# 再编译主程序
python -m nuitka --standalone --onefile --windows-console-mode=disable \
    --enable-plugin=pyside6 --output-dir=dist \
    --windows-icon-from-ico=client/icon.ico \
    --include-data-files=dist/captcha_helper.exe=./captcha_helper.exe \
    --assume-yes-for-downloads client/client.py
```

### 从源码运行

```bash
pip install PySide6 requests watchdog pywebview
cd client && python client.py
```

---

## 📂 项目结构

```
lol-uploader/
├── client/
│   ├── client.py             # 桌面客户端主程序
│   ├── captcha_webkit.py     # macOS 验证码子进程
│   ├── captcha_win.py        # Windows 验证码子进程
│   ├── icon.icns / icon.ico  # 应用图标
│   ├── build.bat             # Windows 打包脚本
│   └── requirements.txt      # Python 依赖
├── server/
│   └── app.py                # Flask 后端
├── .github/workflows/        # CI 自动编译
│   ├── build-macos.yml
│   └── build-windows.yml
└── README.md
```

## 📝 License

MIT
