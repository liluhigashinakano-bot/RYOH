@echo off
cd /d C:\Users\lalal\trust\backend
if not exist "venv" (
    py -3.12 -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
if not exist "data" mkdir data
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
