@echo off
REM ======================================================================
REM run_tests.bat - Runs the router's unit tests with Python's unittest.
REM It looks for test_router.py inside a "tests" folder next to this file.
REM NOTE: that tests folder is not included in this repo, so no tests are found.
REM ======================================================================
title AQUA SHIELD AI - Unit Tests
echo =================================================================
echo   Running AQUA SHIELD AI Router Unit Tests (Offline / Mocked)
echo =================================================================
REM discover -s <folder> -p <file pattern> -v (verbose: print each test name)
python -m unittest discover -s "%~dp0tests" -p "test_router.py" -v
pause

