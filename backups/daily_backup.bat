@echo off
set PGPASSWORD=PkkigWydhjteUnJMayxTUTaYXawupuSG
set BACKUP_DIR=C:\Users\lalal\trust\backups
set DATE=%date:~0,4%%date:~5,2%%date:~8,2%

pg_dump -h maglev.proxy.rlwy.net -p 52152 -U postgres -d railway -F c -f "%BACKUP_DIR%\railway_backup_%DATE%.dump"

if %ERRORLEVEL% EQU 0 (
    echo [%DATE%] Backup OK >> "%BACKUP_DIR%\backup_log.txt"
) else (
    echo [%DATE%] Backup FAILED >> "%BACKUP_DIR%\backup_log.txt"
)

:: 30 days old backup delete
forfiles /p "%BACKUP_DIR%" /m "railway_backup_*.dump" /d -30 /c "cmd /c del @file" 2>nul
