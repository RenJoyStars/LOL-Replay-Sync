# 英雄联盟对局文件同步助手 (LOL Replay Sync)

🎮 一个基于 PySide6 的桌面客户端，自动监控并上传英雄联盟对局回放文件（.rofl）到自建服务器，方便与多台电脑同步。

---

## 📥 下载最新版本

从 [Releases 页面](https://github.com/RenJoyStars/lol-uploader/releases) 下载最新版本：

| 平台 | 下载 | 说明 |
|------|------|------|
| 🍎 **Mac (Apple Silicon)** | `LOLReplaySync-v0.3-mac-arm64.dmg` | M系列 芯片 |
| 🍎 **Mac (Intel)** | `LOLReplaySync-v0.3-mac-x86.dmg` | Intel 芯片 Mac（CI 自动编译） |
| 🪟 **Windows** | `LOLReplaySync-v0.3-win.exe` | 所有 Windows |

> **首次打开 Mac 版**如果提示"来自身份不明的开发者"：
> 右键 App → 选择「打开」→ 点「打开」，之后不会再弹

---

## ✨ 功能特点

### 🎮 核心功能
- **自动同步** — 监听指定文件夹，新 .rofl 文件自动上传到云端，换台电脑登录即可拉取
- **云端管理** — 在线查看、下载、删除、重命名，一键下载所有未同步文件
- **录像回看** — 云端文件可调用本地 LOL 客户端直接播放回放（版本匹配自动识别）
- **元数据解析** — 自动解析 .rofl 文件，显示对局模式、英雄阵容、时长、版本号

### 🛡️ 安全防护
- **验证码验证** — 登录/注册需完成算式验证或腾讯云验证码，防止暴力破解
- **IP 限流** — 每分钟最多 8 次尝试，超限自动封禁 60 秒
- **记住密码 / 自动登录** — 本地安全保存，自动登录跳过验证码

### 🎨 界面优化
- **云端筛选** — 按模式、版本号、日期范围筛选对局文件
- **跨平台** — 支持 macOS（arm64 + Intel）和 Windows
- **系统托盘** — 最小化到托盘，后台静默运行
- **中文界面** — 国服英雄名完整中文映射

## 🌐 服务器信息

**当前服务器地址：** `175.178.183.14:5050`

服务器为个人维护的腾讯云 Ubuntu 实例，开箱即用。注册账号后即可使用，每个用户数据独立存储。

## 🖥️ 技术栈

| 组件 | 技术 |
|------|------|
| 客户端 | Python + PySide6 |
| 服务端 | Python + Flask + SQLite |
| 部署 | 腾讯云 Ubuntu + Supervisor |
| 验证码 | 腾讯云 CAPTCHA + 本地算式验证 |
| 打包 | Nuitka（编译为原生可执行文件，不报毒） |
| CI | GitHub Actions 自动编译 Windows + Mac Intel 版 |

## 🏗️ 项目结构

```
lol-uploader/
├── client/
│   ├── client.py          # 桌面客户端主程序
│   ├── build.bat          # Windows 本地打包脚本
│   ├── icon.ico           # Windows 应用图标
│   ├── icon.icns          # macOS 应用图标
│   └── requirements.txt   # Python 依赖
├── server/
│   └── app.py             # Flask 后端服务器
├── .github/workflows/     # CI 自动编译配置
│   ├── build-windows.yml  # Windows 版 CI
│   └── build-macos.yml    # Mac Intel 版 CI
├── 教程.md                # 使用教程
└── README.md              # 本文件
```

## 🔧 自行编译

### macOS

```bash
pip install nuitka pillow
python -m nuitka --standalone --macos-create-app-bundle \
    --enable-plugin=pyside6 --output-dir=dist \
    --macos-app-icon=client/icon.icns \
    client/client.py
```

### Windows

```bash
pip install nuitka
python -m nuitka --standalone --onefile --windows-console-mode=disable \
    --enable-plugin=pyside6 --output-dir=dist \
    --windows-icon-from-ico=client\icon.ico \
    --assume-yes-for-downloads \
    client\client.py
```

### 从源码运行

```bash
pip install PySide6 requests watchdog
cd client && python client.py
```

## 📝 License

MIT
