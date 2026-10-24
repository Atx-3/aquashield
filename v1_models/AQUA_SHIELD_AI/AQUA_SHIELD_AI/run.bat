@echo off
REM ======================================================================
REM run.bat - Double-click to start the AQUA SHIELD AI router in a terminal.
REM It runs main.py, which lets you type commands (e.g. "forecast the spill")
REM and shows which investigation tool the local Qwen3 LLM picked.
REM Requires Ollama running locally with the qwen3:1.7b model pulled.
REM ======================================================================
REM "@echo off" above hides the commands themselves, so only their output is shown.
REM "title" sets the text in the terminal window's title bar.
title AQUA SHIELD AI - Intent & Tool Router
echo =================================================================
echo   Starting AQUA SHIELD AI Intent & Tool Router (Qwen3 1.7B)
echo =================================================================
REM %~dp0 = the folder this .bat file is in, so main.py is found from anywhere
python "%~dp0main.py"
REM Keep the window open after the program ends so you can read the output
pause

