@echo off
echo Starting Gmail Chatbot...

cd /d %~dp0

REM Activate virtual environment if it exists
if exist "..\..\venv\Scripts\activate.bat" (
  call "..\..\venv\Scripts\activate.bat"
) else if exist "..\..\.venv\Scripts\activate.bat" (
  call "..\..\.venv\Scripts\activate.bat"
)

REM Run Streamlit app
python -u -m streamlit run chat_app_st.py --logger.level debug

pause
