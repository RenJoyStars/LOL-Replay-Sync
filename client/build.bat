@echo off
chcp 65001 >nul
title LOL 上传器 - 打包工具
echo.
echo ============================================
echo   🎮 LOL 上传器 - Windows 打包工具
echo ============================================
echo.
echo   ⚠ 推荐用 Nuitka 编译（不报毒）
echo   Windows Defender 不会拦截
echo.
echo   [1] 🚀 一键安装依赖 + 编译
echo   [2] 仅编译（已装过依赖）
echo   [0] 退出
echo.
echo ============================================
echo.
set /p choice="请选择 [0/1/2]: "

if "%choice%"=="1" goto full
if "%choice%"=="2" goto compile
if "%choice%"=="0" goto end
echo 输入无效，请重新运行
pause
goto end

:full
echo.
echo === 第一步：安装 Python 依赖 ===
pip install PySide6 requests watchdog nuitka -q
echo.
echo ✅ 依赖安装完成
echo.
goto compile

:compile
echo.
echo === 第二步：用 Nuitka 编译（不会报毒）===
echo.
python -m nuitka --standalone --onefile --windows-disable-console ^
    --enable-plugin=pyside6 --output-dir=dist ^
    --windows-icon-from-ico=icon.ico ^
    --product-name="英雄联盟对局文件助手" ^
    --file-version="1.0.0" ^
    client.py
echo.
if exist dist\client.exe (
    echo ✅ =========================================
    echo ✅  编译成功！
    echo ✅  文件位置：dist\client.exe
    echo ✅ =========================================
    echo.
    echo 📁 文件大小：
    dir /-C dist\client.exe | find "client.exe"
    echo.
    echo 💡 发送给朋友前建议做数字签名（淘宝 ¥20-50）：
    echo    signtool sign /fd SHA256 /a /f 证书.pfx /p 密码 dist\client.exe
) else (
    echo ❌ 编译失败，查看上面的错误信息
    echo.
    echo 💡 常见问题：
    echo   - 需要安装 Visual C++ 生成工具
    echo   - 下载：https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo   - 安装时勾选「使用 C++ 的桌面开发」
)
echo.
pause
goto end

:end
