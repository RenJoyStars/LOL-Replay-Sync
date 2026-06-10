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
echo === 安装 Python 依赖 ===
pip install PySide6 requests watchdog nuitka -q
echo ✅ 依赖安装完成
goto compile

:compile
echo.
echo === 编译中（约5-10分钟）===
cd /d %~dp0
python -m nuitka --standalone --onefile --windows-console-mode=disable ^
    --enable-plugin=pyside6 --output-dir=dist ^
    --product-name="英雄联盟对局文件助手" ^
    --file-version="1.0.0" ^
    --assume-yes-for-downloads ^
    client.py
echo.
if exist dist\client.exe (
    echo ✅ 编译成功！dist\client.exe
    dir /-C dist\client.exe | find "client.exe"
) else (
    echo ❌ 编译失败，需安装 Visual C++ 生成工具：
    echo https://visualstudio.microsoft.com/visual-cpp-build-tools/
)
pause
goto end

:end
