@echo off
setlocal

if not defined EVEN_HOME set "EVEN_HOME=%~dp0.."

"%EVEN_HOME%\.venv\Scripts\even.exe" %*
exit /b %ERRORLEVEL%
