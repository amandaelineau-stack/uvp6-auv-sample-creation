@echo off
rem Starts the ALR-UVP6 app in the web browser (double-click this file).
rem Uses the Python of the active environment, e.g. after: conda activate alr_uvp
cd /d "%~dp0"
python -c "import streamlit" 2>nul || python -m pip install -r requirements.txt
python -m streamlit run app.py
pause
