@echo off
echo.
echo =========================================
echo       MVlab - 一鍵自動發布至 GitHub
echo =========================================
echo.
echo 正在儲存您所有的變更...
git add .
set datetime=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set datetime=%datetime: =0%
git commit -m "Auto Update %datetime%"
echo.
echo 正在上傳至 GitHub...
git push origin main
echo.
echo =========================================
echo 發布完成！您在網頁上大約 1 分鐘後就能看見更新！
echo =========================================
echo.
pause
