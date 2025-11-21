#!/bin/bash

echo "=========================================="
echo "🤖 IDX News Bot - Railway Deployment"
echo "=========================================="

# Check essential environment variables
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ ERROR: BOT_TOKEN environment variable is required!"
    echo "💡 Please set BOT_TOKEN in Railway Dashboard → Variables"
    exit 1
fi

if [ -z "$CHANNEL_ID" ]; then
    echo "❌ ERROR: CHANNEL_ID environment variable is required!"
    echo "💡 Please set CHANNEL_ID in Railway Dashboard → Variables"
    exit 1
fi

echo "✅ Environment variables check passed"
echo "🔧 Installing dependencies..."

# Install Chrome for Railway
apt-get update
apt-get install -y wget curl gnupg

wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

apt-get update
apt-get install -y google-chrome-stable

echo "✅ Dependencies installed"
echo "🚀 Starting bot..."

# Run the bot
python3 bot_simple_selenium.py