import os
import logging
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
from bs4 import BeautifulSoup
import requests
import asyncio
import datetime
import hashlib

# Setup logging pertama
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Konfigurasi dari Environment Variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))

# Validasi environment variables
if not BOT_TOKEN:
    logger.error("❌ ERROR: BOT_TOKEN environment variable is not set!")
    logger.error("💡 Please set BOT_TOKEN in Railway Dashboard → Variables")
    exit(1)

if not CHANNEL_ID:
    logger.error("❌ ERROR: CHANNEL_ID environment variable is not set!")
    logger.error("💡 Please set CHANNEL_ID in Railway Dashboard → Variables")
    exit(1)

logger.info("✅ Environment Variables loaded successfully!")
logger.info(f"   BOT_TOKEN: {BOT_TOKEN[:10]}...")
logger.info(f"   CHANNEL_ID: {CHANNEL_ID}")

# Penyimpanan dalam memory
sent_news_titles = set()

def get_news_from_multiple_sources():
    """Ambil berita dari berbagai sumber yang lebih friendly"""
    all_news = []
    
    # Daftar sumber berita saham
    sources = [
        {
            "name": "Kontan",
            "url": "https://www.kontan.co.id/search/saham",
            "selector": "a[class*='title']",
            "base_url": "https://www.kontan.co.id"
        },
        {
            "name": "CNBC Indonesia", 
            "url": "https://www.cnbcindonesia.com/market",
            "selector": "a[class*='title']",
            "base_url": "https://www.cnbcindonesia.com"
        },
        {
            "name": "Investasi Kontan",
            "url": "https://investasi.kontan.co.id/news",
            "selector": "a",
            "base_url": "https://investasi.kontan.co.id"
        }
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    }
    
    for source in sources:
        try:
            logger.info(f"🔍 Mencari berita dari {source['name']}...")
            response = requests.get(source["url"], headers=headers, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"⚠️ Gagal akses {source['name']}: Status {response.status_code}")
                continue
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Cari elemen berita
            news_elements = []
            
            # Coba berbagai selector
            selectors_to_try = [
                source["selector"],
                "a[href*='/news/']",
                "a[href*='/read/']", 
                "h2 a",
                "h3 a",
                ".title a",
                ".news-title a"
            ]
            
            for selector in selectors_to_try:
                elements = soup.select(selector)
                if elements:
                    news_elements.extend(elements)
                    break
            
            for element in news_elements[:15]:  # Batasi 15 elemen per sumber
                try:
                    title = element.get_text(strip=True)
                    if not title or len(title) < 20:
                        continue
                    
                    # Dapatkan link
                    href = element.get('href', '')
                    if not href:
                        continue
                        
                    # Format URL lengkap
                    if href.startswith('/'):
                        full_url = f"{source['base_url']}{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"{source['base_url']}/{href}"
                    
                    # Skip link tidak valid
                    if any(invalid in full_url.lower() for invalid in ['javascript:', 'mailto:', '#']):
                        continue
                    
                    # Filter berita relevan
                    if is_relevant_news(title):
                        news_item = {
                            'title': title,
                            'link': full_url,
                            'date': datetime.datetime.now().strftime("%Y-%m-%d"),
                            'source': source['name']
                        }
                        all_news.append(news_item)
                        logger.info(f"📰 {source['name']}: {title[:50]}...")
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            logger.warning(f"⚠️ Error akses {source['name']}: {str(e)}")
            continue
    
    # Hapus duplikat berdasarkan judul
    unique_news = []
    seen_titles = set()
    
    for item in all_news:
        title_hash = hashlib.md5(item['title'].lower().strip().encode()).hexdigest()
        if title_hash not in seen_titles:
            seen_titles.add(title_hash)
            unique_news.append(item)
    
    logger.info(f"✅ Total {len(unique_news)} berita unik ditemukan")
    return unique_news

def is_relevant_news(title):
    """Filter berita yang relevan dengan saham dan investasi"""
    if not title or len(title) < 15:
        return False
        
    title_lower = title.lower()
    
    keywords = [
        'saham', 'bursa', 'idx', 'emiten', 'dividen', 'laba', 'rugi',
        'right issue', 'ipo', 'obligasi', 'reksadana', 'investasi',
        'sekuritas', 'trading', 'portofolio', 'korporasi', 'financial',
        'keuangan', 'profit', 'ekspansi', 'rupiah', 'dolar', 'ekonomi'
    ]
    
    return any(keyword in title_lower for keyword in keywords)

async def send_news(context: ContextTypes.DEFAULT_TYPE):
    """Kirim berita baru ke Telegram"""
    try:
        logger.info("🔍 Mencari berita terbaru...")
        
        news_items = get_news_from_multiple_sources()
        
        if not news_items:
            logger.info("📭 Tidak ada berita ditemukan")
            return
            
        sent_count = 0
        for item in news_items:
            title_hash = hashlib.md5(item['title'].strip().lower().encode()).hexdigest()
            
            if title_hash not in sent_news_titles:
                try:
                    message = (
                        f"📢 **{item['title']}**\n\n"
                        f"📅 {item['date']}\n"
                        f"🌐 Sumber: {item['source']}\n\n"
                        f"🔗 {item['link']}\n\n"
                        f"#BeritaSaham #Investasi"
                    )
                    
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=message,
                        parse_mode='Markdown',
                        disable_web_page_preview=False
                    )
                    
                    sent_news_titles.add(title_hash)
                    sent_count += 1
                    
                    logger.info(f"✅ Terkirim: {item['title'][:50]}...")
                    await asyncio.sleep(1)  # Delay antar pesan
                    
                except Exception as e:
                    logger.error(f"❌ Gagal kirim: {e}")
        
        logger.info(f"📨 {sent_count} berita terkirim")
        
        # Cleanup memory
        if len(sent_news_titles) > 200:
            sent_news_titles.clear()
            logger.info("🧹 Memory cache dibersihkan")
            
    except Exception as e:
        logger.error(f"❌ Error di send_news: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start"""
    await update.message.reply_text(
        "🤖 **IDX Stock News Bot**\n\n"
        "Saya mengirimkan berita saham terbaru dari:\n"
        "• 📊 Kontan\n• 📈 CNBC Indonesia\n"
        "• 💰 Investasi Kontan\n\n"
        "📋 Perintah tersedia:\n"
        "• /start - Info bot\n"
        "• /status - Status\n" 
        "• /test - Test berita\n"
        "• /clear - Reset cache\n\n"
        "🔧 Deployed di Railway"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /status"""
    await update.message.reply_text(
        f"📊 **Status Bot**\n\n"
        f"• Berita dikirim: {len(sent_news_titles)}\n"
        f"• Interval: {CHECK_INTERVAL} detik\n"
        f"• Sumber: Multiple websites\n"
        f"• Terakhir dicek: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"• Status: ✅ AKTIF"
    )

async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /clear"""
    sent_news_titles.clear()
    await update.message.reply_text("✅ Cache berhasil dibersihkan!")

async def test_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /test"""
    await update.message.reply_text("🔍 Testing pencarian berita...")
    
    news_items = get_news_from_multiple_sources()
    
    if news_items:
        message = f"✅ Ditemukan {len(news_items)} berita:\n\n"
        for i, item in enumerate(news_items[:3]):
            message += f"{i+1}. {item['title']}\n"
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("❌ Tidak ada berita ditemukan")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Main function"""
    try:
        logger.info("🚀 Starting News Bot (Multiple Sources)...")
        
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CommandHandler("test", test_news))
        application.add_handler(CommandHandler("clear", clear_cache))
        
        # Schedule job
        if application.job_queue:
            application.job_queue.run_repeating(
                send_news, 
                interval=CHECK_INTERVAL, 
                first=10
            )
            logger.info(f"✅ Scheduled job dengan interval {CHECK_INTERVAL}s")
        
        logger.info("🤖 Bot started! Press Ctrl+C to stop.")
        
        # Start polling
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        exit(1)

if __name__ == '__main__':
    main()