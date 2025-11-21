#!/bin/bash

echo "🚀 Starting IDX News Bot on Railway..."

# Install Chrome and dependencies
apt-get update
apt-get install -y wget curl

# Download and install Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
apt-get update
apt-get install -y google-chrome-stable

echo "✅ Chrome installed successfully"

# Run the bot
python3 bot_simple_selenium.py