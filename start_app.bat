@echo off
rem Starts the ALR-UVP6 app in the web browser (double-click this file).
rem Uses the conda environment alr_uvp when Miniconda or Anaconda is installed
rem in the user folder, otherwise the Python found on the PATH.
cd /d "%~dp0"
for %%C in ("%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%LOCALAPPDATA%\miniconda3") do (
    if exist "%%~C\condabin\conda.bat" (
        call "%%~C\condabin\conda.bat" activate alr_uvp
        goto run
    )
)
:run
python -c "import streamlit" 2>nul || python -m pip install -r requirements.txt
python -m streamlit run app.py
pause
