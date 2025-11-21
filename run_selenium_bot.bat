@echo off
title IDX News Bot - Simple Version
echo ===============================
echo    IDX STOCK NEWS BOT
echo    (Simple - No Database)
echo ===============================
echo.
echo Memulai bot berita saham IDX...
echo Tanpa database - menggunakan memory cache
echo Menggunakan Selenium WebDriver...
echo.
echo Pastikan Chrome terinstall di komputer!
echo.
echo Bot akan berjalan di window ini...
echo Untuk menghentikan: Tekan Ctrl+C
echo ===============================
echo.

:: Pindah ke directory script
cd /d "C:\idx-news-bot"

:: Tunggu sebentar
timeout /t 3 /nobreak

:: Jalankan bot simple
py bot_simple_selenium.py

:: Tampilkan pesan jika error
if errorlevel 1 (
    echo.
    echo ===============================
    echo ERROR: Bot berhenti!
    echo Periksa konfigurasi dan coba lagi.
    echo ===============================
)

pause