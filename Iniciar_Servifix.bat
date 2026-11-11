@echo off
REM Inicia ServiFix en el computador: backend (FastAPI) + interfaz (Streamlit)
cd /d "%~dp0"
if exist venv311\Scripts\activate.bat (call venv311\Scripts\activate.bat) else if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat)
start "ServiFix API" cmd /k uvicorn main:app --reload --port 8000
timeout /t 4 >nul
start "ServiFix Web" cmd /k streamlit run app.py
