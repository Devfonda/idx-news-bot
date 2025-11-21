import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
from bs4 import BeautifulSoup
import requests
import asyncio
import time
import datetime
import hashlib

# Konfigurasi - Gunakan environment variables di Railway
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN not set!")
    exit(1)
    
if not CHANNEL_ID:
    print("❌ ERROR: CHANNEL_ID not set!")
    exit(1)

logging.info(f"✅ Environment Variables loaded:")
logging.info(f"   BOT_TOKEN: {BOT_TOKEN[:10]}...")
logging.info(f"   CHANNEL_ID: {CHANNEL_ID}")
logging.info(f"   CHECK_INTERVAL: {CHECK_INTERVAL}")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Penyimpanan dalam memory (tanpa database)
sent_news_titles = set()
sent_news_links = set()

def setup_driver():
    """Setup Chrome driver untuk Railway"""
    chrome_options = Options()
    
    # Options untuk Railway/Cloud environment
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Untuk Railway, gunakan CHROMIUM
    try:
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("✅ ChromeDriver berhasil diinisialisasi")
        return driver
    except Exception as e:
        logger.error(f"❌ Gagal setup ChromeDriver: {e}")
        raise

def get_news_requests():
    """Mengambil berita menggunakan requests"""
    try:
        logger.info("🔄 Mengakses website IDX dengan Requests...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'id,en-US;q=0.7,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
        }
        
        response = requests.get("https://www.idx.co.id/id/berita/", headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        news_items = []
        
        # Cari berita berdasarkan struktur yang umum di IDX
        # Coba berbagai kemungkinan selector
        selectors_to_try = [
            'a[href*="/berita/"]',
            'div.news-item a',
            'div.berita-item a',
            'article a',
            'div.post-title a',
            'h2 a',
            'h3 a'
        ]
        
        for selector in selectors_to_try:
            elements = soup.select(selector)
            for element in elements:
                try:
                    title = element.get_text(strip=True)
                    href = element.get('href', '')
                    
                    if len(title) < 10:
                        continue
                    
                    # Format URL
                    if href.startswith('/'):
                        full_url = f"https://www.idx.co.id{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"https://www.idx.co.id/{href}"
                    
                    # Skip invalid links
                    if any(invalid in full_url for invalid in ['javascript:', 'mailto:', '#']):
                        continue
                    
                    # Filter berita relevan
                    if is_relevant_news(title):
                        news_item = {
                            'title': title,
                            'link': full_url,
                            'date': datetime.datetime.now().strftime("%Y-%m-%d")
                        }
                        news_items.append(news_item)
                        logger.info(f"📰 Ditemukan: {title[:60]}...")
                        
                except Exception as e:
                    continue
        
        # Remove duplicates
        unique_news = []
        seen = set()
        for item in news_items:
            identifier = item['title'].lower().strip()
            if identifier not in seen:
                seen.add(identifier)
                unique_news.append(item)
        
        logger.info(f"✅ Total {len(unique_news)} berita unik ditemukan")
        return unique_news
        
    except Exception as e:
        logger.error(f"❌ Error Requests: {e}")
        return []

def is_relevant_news(title):
    """Filter berita yang relevan"""
    if not title or len(title) < 10:
        return False
        
    title_lower = title.lower()
    
    keywords = [
        'aksi korporasi', 'right issue', 'ekspansi bisnis', 'backdoor listing', 
        'corporate action', 'rights issue', 'dividen', 'stock split', 'obligasi',
        'emitmen', 'ipo', 'saham', 'bursa efek', 'korporasi', 'ekspansi',
        'rups', 'ratah', 'obligasi', 'sukuk', 'reksadana', 'laporan',
        'financial', 'keuangan', 'laba', 'rugi', 'profit', 'emiten', 'bursa',
        'efek', 'investasi', 'portofolio', 'sekuritas', 'trading'
    ]
    
    return any(keyword in title_lower for keyword in keywords)

def get_news_selenium():
    """Fallback menggunakan Selenium jika requests gagal"""
    driver = None
    try:
        logger.info("🔄 Mencoba dengan Selenium...")
        driver = setup_driver()
        driver.get("https://www.idx.co.id/id/berita/")
        
        # Tunggu lebih lama untuk render JavaScript
        time.sleep(10)
        
        # Dapatkan HTML
        html_content = driver.page_source
        
        # Simpan untuk debugging (opsional)
        if os.getenv('DEBUG_HTML'):
            with open("/tmp/debug_page.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info("💾 HTML disimpan untuk debugging")
        
        # Parse dengan BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Gunakan logic yang sama dengan requests
        news_items = []
        links = soup.find_all('a', href=True)
        
        for link in links:
            try:
                title = link.get_text(strip=True)
                href = link['href']
                
                if len(title) < 10:
                    continue
                
                # Format URL
                if href.startswith('/'):
                    full_url = f"https://www.idx.co.id{href}"
                elif href.startswith('http'):
                    full_url = href
                else:
                    continue  # Skip relative URLs tanpa slash
                
                # Filter
                if ('/berita/' in full_url and 
                    is_relevant_news(title) and
                    not any(invalid in full_url for invalid in ['javascript:', 'mailto:', '#'])):
                    
                    news_items.append({
                        'title': title,
                        'link': full_url,
                        'date': datetime.datetime.now().strftime("%Y-%m-%d")
                    })
                    
            except Exception as e:
                continue
        
        # Remove duplicates
        unique_news = []
        seen = set()
        for item in news_items:
            identifier = item['title'].lower().strip()
            if identifier not in seen:
                seen.add(identifier)
                unique_news.append(item)
        
        logger.info(f"✅ Selenium menemukan {len(unique_news)} berita")
        return unique_news
        
    except Exception as e:
        logger.error(f"❌ Error Selenium: {e}")
        return []
    finally:
        if driver:
            driver.quit()

async def send_news(context: ContextTypes.DEFAULT_TYPE):
    """Kirim berita baru ke channel"""
    try:
        logger.info("🔍 Memulai pencarian berita...")
        
        # Coba requests dulu
        news_items = get_news_requests()
        
        # Fallback ke Selenium
        if not news_items:
            logger.info("🔄 Fallback ke Selenium...")
            news_items = get_news_selenium()
        
        if not news_items:
            logger.info("📭 Tidak ada berita baru ditemukan")
            return
            
        sent_count = 0
        for item in news_items:
            # Generate hash untuk deduplication
            title_hash = hashlib.md5(item['title'].strip().lower().encode()).hexdigest()
            
            if title_hash not in sent_news_titles:
                try:
                    # Format pesan
                    message = (
                        f"📢 **{item['title']}**\n\n"
                        f"📅 {item['date']}\n\n"
                        f"🔗 {item['link']}\n\n"
                        f"#BeritaSaham #IDX #Investasi"
                    )
                    
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=message,
                        parse_mode='Markdown',
                        disable_web_page_preview=False
                    )
                    
                    # Simpan ke memory
                    sent_news_titles.add(title_hash)
                    sent_count += 1
                    
                    logger.info(f"✅ Terkirim: {item['title'][:50]}...")
                    await asyncio.sleep(1)  # Delay antar pesan
                    
                except Exception as e:
                    logger.error(f"❌ Gagal kirim pesan: {e}")
            else:
                logger.debug(f"⏭️ Skip: {item['title'][:50]}...")
        
        logger.info(f"📨 Berhasil mengirim {sent_count} berita baru")
        
        # Cleanup memory
        if len(sent_news_titles) > 500:
            # Keep only last 300 items
            sent_news_titles.clear()
            logger.info("🧹 Memory dibersihkan")
        
    except Exception as e:
        logger.error(f"❌ Error di send_news: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start"""
    await update.message.reply_text(
        "🤖 **IDX Stock News Bot** (Railway Edition)\n\n"
        "Saya memantau berita saham dari IDX secara real-time!\n\n"
        "📋 Perintah tersedia:\n"
        "• /start - Info bot\n"
        "• /status - Status bot\n" 
        "• /test - Test pencarian berita\n"
        "• /clear - Reset cache\n"
        "• /debug - Analisis website\n\n"
        "🔧 Deployed di Railway"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /status"""
    await update.message.reply_text(
        f"📊 **Status Bot**\n\n"
        f"• Berita dikirim: {len(sent_news_titles)}\n"
        f"• Interval: {CHECK_INTERVAL}s\n"
        f"• Environment: Railway\n"
        f"• Terakhir dicek: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"• Status: ✅ AKTIF"
    )

async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /clear"""
    sent_news_titles.clear()
    sent_news_links.clear()
    await update.message.reply_text("✅ Cache berhasil dibersihkan!")

async def test_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /test"""
    await update.message.reply_text("🔍 Testing pencarian berita...")
    
    news_items = get_news_requests()
    if not news_items:
        news_items = get_news_selenium()
        
    if news_items:
        message = f"✅ Ditemukan {len(news_items)} berita:\n\n"
        for i, item in enumerate(news_items[:3]):
            message += f"{i+1}. {item['title']}\n"
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("❌ Tidak ada berita ditemukan")

async def debug_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /debug"""
    await update.message.reply_text("🔧 Analisis struktur website...")
    
    try:
        response = requests.get("https://www.idx.co.id/id/berita/", timeout=30)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        analysis = "📊 **Analisis Website:**\n\n"
        analysis += f"• Title: {soup.title.string if soup.title else 'N/A'}\n"
        analysis += f"• Div elements: {len(soup.find_all('div'))}\n"
        analysis += f"• Links: {len(soup.find_all('a'))}\n"
        
        # Cari link berita
        news_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/berita/' in href:
                title = link.get_text(strip=True)
                if len(title) > 10:
                    news_links.append(title[:40])
        
        analysis += f"• Potential news: {len(news_links)}\n"
        if news_links:
            analysis += "Contoh:\n• " + "\n• ".join(news_links[:3])
        
        await update.message.reply_text(analysis)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Main function"""
    try:
        logger.info("🚀 Starting IDX News Bot (Railway Edition)")
        
        # Test koneksi
        logger.info("🔧 Testing environment...")
        
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CommandHandler("clear", clear_cache))
        application.add_handler(CommandHandler("test", test_news))
        application.add_handler(CommandHandler("debug", debug_site))
        
        application.add_error_handler(error_handler)
        
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
        # Exit dengan code error untuk restart di Railway
        exit(1)

if __name__ == '__main__':
    main()