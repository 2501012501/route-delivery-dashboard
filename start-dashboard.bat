@echo off
cd /d "%~dp0"
echo Starting Route Delivery Dashboard...
echo.
echo The browser will open automatically once Streamlit is ready.
echo Keep this window open while using the dashboard.
echo To stop, close this window.
echo.
python -m streamlit run Home.py
pause
