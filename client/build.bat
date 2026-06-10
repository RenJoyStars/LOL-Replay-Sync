@echo off
chcp 65001 >nul
title LOL 上传器 - 打包工具
echo.
echo ============================================
echo   🎮 LOL 上传器 - Windows 打包工具
echo ============================================
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
echo === 第二步：用 Nuitka 编译 ===
echo.
cd /d %~dp0
python -m nuitka --standalone --onefile --windows-disable-console ^
    --enable-plugin=pyside6 --output-dir=dist ^
    --product-name="英雄联盟对局文件助手" ^
    --file-version="1.0.0" ^
    client.py
echo.
if exist dist\client.exe (
    echo ✅ 编译成功！
    echo 📁 dist\client.exe
    dir /-C dist\client.exe | find "client.exe"
) else (
    echo ❌ 编译失败，需安装 Visual C++ 生成工具：
    echo https://visualstudio.microsoft.com/visual-cpp-build-tools/
)
echo.
pause
goto end

:end
