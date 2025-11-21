#!/bin/bash
Xvfb :99 -screen 0 1920x1080x16 &
python3 bot_simple_selenium.py
