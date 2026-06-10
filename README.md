# 英雄联盟对局文件助手 (LOL Replay Sync)

🎮 一个基于 PySide6 的桌面客户端，自动监控并上传英雄联盟对局回放文件（.rofl）到自建服务器，方便与多台电脑同步。

---

## ✨ 功能特点

- **自动监控** — 监听指定文件夹，新 .rofl 文件自动上传到云端
- **多用户支持** — 注册/登录，每个用户文件独立管理
- **云端管理** — 在线查看、下载、删除、重命名已上传的文件
- **元数据解析** — 自动解析 .rofl 文件，显示对局模式、英雄阵容、时长
- **跨平台** — 支持 macOS（Nuitka 编译），Windows 同样可用
- **系统托盘** — 最小化到托盘，后台静默运行
- **自动登录** — 支持记住密码和自动登录
- **中文界面** — 国服英雄名完整中文映射

## 🖥️ 技术栈

| 组件 | 技术 |
|------|------|
| 客户端 | Python + PySide6 |
| 服务端 | Python + Flask + SQLite |
| 部署 | 腾讯云 Ubuntu + Supervisor |
| 打包 | Nuitka（编译为本地可执行文件） |

## 📦 快速开始

### 客户端

```bash
# 1. 安装依赖
pip install PySide6 requests watchdog

# 2. 启动
cd client
python client.py
```

### 服务端（自建）

```bash
# 安装
pip install flask flask-cors

# 启动
cd server
python app.py
```

> 默认运行在 5050 端口，可在 `client.py` 中修改 `SERVER_URL` 连接到你的服务器。

### macOS 安装包

下载 `英雄联盟对局文件助手.dmg`，双击打开，将 App 拖入 Applications 文件夹即可。

> Powered by Nuitka — Python 编译为原生可执行文件，杀软不报毒。

## 🏗️ 项目结构

```
lol-uploader/
├── client/
│   ├── client.py          # 桌面客户端主程序
│   ├── build.bat          # Windows 打包脚本
│   └── requirements.txt   # Python 依赖
├── server/
│   └── app.py             # Flask 后端服务器
├── 教程.md                # 使用教程
└── README.md              # 本文件
```

## 🔧 配置

在 `client/client.py` 中找到：

```python
SERVER_URL = "http://127.0.0.1:5050"  # 改为你的服务器地址
```

## 📝 License

MIT
