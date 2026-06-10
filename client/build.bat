@echo off
chcp 65001 >nul
echo.
echo ============================================
echo   🎮 LOL 上传器 - 打包工具
echo ============================================
echo.
echo   [1] 用 Nuitka 编译（推荐，不容易报毒）
echo   [2] 用 PyInstaller 打包（快速但可能报毒）
echo   [0] 退出
echo.
echo ============================================
echo.
set /p choice="请选择 [0/1/2]: "

if "%choice%"=="1" goto nuitka
if "%choice%"=="2" goto pyinstaller
if "%choice%"=="0" goto end
echo 输入无效，请重新运行
pause
goto end

:nuitka
echo.
echo 📦 正在用 Nuitka 编译...
echo.
echo 第一步：安装 Nuitka
pip install nuitka
echo.
echo 第二步：编译...
python -m nuitka --standalone --windows-disable-console --onefile --output-dir=dist client.py
echo.
if exist dist\client.exe (
    echo ✅ 编译成功！文件在 dist\client.exe
    echo 📁 大小：
    dir dist\client.exe
) else (
    echo ❌ 编译失败，看看上面的错误信息
)
echo.
echo 💡 提示：如果报毒，请申请数字签名证书后签名：
echo    signtool sign /fd SHA256 /a /f 你的证书.pfx /p 密码 dist\client.exe
pause
goto end

:pyinstaller
echo.
echo 📦 正在用 PyInstaller 打包...
echo.
echo 第一步：安装 PyInstaller
pip install pyinstaller
echo.
echo 第二步：打包...
pyinstaller --onefile --windowed --name "LOL上传器" client.py
echo.
if exist dist\LOL上传器.exe (
    echo ✅ 打包成功！文件在 dist\LOL上传器.exe
    echo 📁 大小：
    dir dist\LOL上传器.exe
) else (
    echo ❌ 打包失败，看看上面的错误信息
)
pause
goto end

:end
