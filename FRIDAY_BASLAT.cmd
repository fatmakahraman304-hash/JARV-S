@echo off
setlocal
pushd "%~dp0" || exit /b 1
if /i "%~1"=="--install-only" goto install
if exist ".venv\Scripts\pythonw.exe" if exist ".venv\friday-setup.ok" goto launch

:install
if exist ".venv\Scripts\python.exe" goto dependencies
where py.exe >nul 2>&1
if errorlevel 1 goto pathpython
py -3.13 -m venv .venv
if not errorlevel 1 goto dependencies

:pathpython
python -c "import sys; sys.exit(sys.version_info[:2] != (3, 13))"
if errorlevel 1 goto missing
python -m venv .venv
if errorlevel 1 goto failed

:dependencies
if exist ".venv\friday-setup.ok" del ".venv\friday-setup.ok"
".venv\Scripts\python.exe" setup.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
>".venv\friday-setup.ok" echo OK
if errorlevel 1 goto failed
if /i "%~1"=="--install-only" goto done

:launch
start "" ".venv\Scripts\pythonw.exe" "main.py"
if errorlevel 1 goto failed
:done
popd
exit /b 0

:missing
echo Python 3.13 kurulmali. Kurulumdan sonra tekrar deneyin.
:failed
echo FRIDAY baslatilamadi. Yukaridaki hata iletisini kontrol edin.
if /i not "%~1"=="--install-only" pause
popd
exit /b 1
