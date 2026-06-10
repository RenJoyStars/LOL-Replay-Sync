# 英雄联盟对局文件助手 (LOL Replay Sync)

🎮 一个基于 PySide6 的桌面客户端，自动监控并上传英雄联盟对局回放文件（.rofl）到自建服务器，方便与多台电脑同步。

---

## 📥 下载最新版本

从 [Releases 页面](https://github.com/RenJoyStars/lol-uploader/releases) 下载：

| 平台 | 下载 | 说明 |
|------|------|------|
| 🍎 macOS | `LOLReplaySync-v0.1-mac.dmg` | 双击 → 拖入 Applications |
| 🪟 Windows | `LOLReplaySync-v0.1-win.exe` | 双击运行（Nuitka 编译，不报毒） |

> **首次打开 Mac 版**如果提示"来自身份不明的开发者"：
> 右键 App → 选择「打开」→ 点「打开」，之后不会再弹

---

## ✨ 功能特点

- **自动监控** — 监听指定文件夹，新 .rofl 文件自动上传到云端
- **多用户支持** — 注册/登录，每个用户文件独立管理
- **云端管理** — 在线查看、下载、删除、重命名已上传的文件
- **元数据解析** — 自动解析 .rofl 文件，显示对局模式、英雄阵容、时长
- **跨平台** — 支持 macOS 和 Windows
- **系统托盘** — 最小化到托盘，后台静默运行
- **自动登录** — 支持记住密码和自动登录
- **中文界面** — 国服英雄名完整中文映射

## 🖥️ 技术栈

| 组件 | 技术 |
|------|------|
| 客户端 | Python + PySide6 |
| 服务端 | Python + Flask + SQLite |
| 部署 | 腾讯云 Ubuntu + Supervisor |
| 打包 | Nuitka（编译为原生可执行文件，不报毒） |
| CI | GitHub Actions 自动编译 Windows 版 |

## 🏗️ 项目结构

```
lol-uploader/
├── client/
│   ├── client.py          # 桌面客户端主程序
│   ├── build.bat          # Windows 本地打包脚本
│   └── requirements.txt   # Python 依赖
├── server/
│   └── app.py             # Flask 后端服务器
├── .github/workflows/     # CI 自动编译配置
├── 教程.md                # 使用教程
└── README.md              # 本文件
```

## 🔧 自行编译

### macOS

```bash
pip install nuitka
python -m nuitka --standalone --macos-create-app-bundle \
    --enable-plugin=pyside6 --output-dir=dist \
    client/client.py
```

### Windows

```bash
pip install nuitka
python -m nuitka --standalone --onefile --windows-console-mode=disable \
    --enable-plugin=pyside6 --output-dir=dist \
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
