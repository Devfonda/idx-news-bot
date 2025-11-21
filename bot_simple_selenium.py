from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.options import Options
import asyncio
import logging
import time
import datetime

# Konfigurasi - GANTI DENGAN DATA ANDA
BOT_TOKEN = "8249944565:AAH3gLQ9E_UvsJ9rVGmWEC3syNOV9Jmha4U"
CHANNEL_ID = "@TestingBot"
CHECK_INTERVAL = 300  # 5 menit (dalam detik)

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
    """Setup Chrome driver untuk Selenium"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")     # mode headless terbaru
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_news_selenium():
    """Mengambil berita menggunakan Selenium"""
    driver = None
    try:
        logger.info("🔄 Mengakses website IDX dengan Selenium...")
        driver = setup_driver()
        driver.get("https://www.idx.co.id/id/berita/")
        
        # Tunggu page load
        time.sleep(5)
        
        # Dapatkan HTML setelah render JavaScript
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        news_items = []
        
        # Cari semua elemen yang mungkin berisi berita
        # Coba berbagai selector yang umum
        selectors_to_try = [
            'div[class*="news"]',
            'div[class*="berita"]', 
            'article',
            'div.list-berita',
            'div.news-item',
            'div.berita-item',
            'div.post',
            'div.item'
        ]
        
        news_containers = []
        for selector in selectors_to_try:
            elements = soup.select(selector)
            if elements:
                news_containers.extend(elements)
                logger.info(f"✅ Ditemukan {len(elements)} elemen dengan selector: {selector}")
        
        # Jika tidak ditemukan dengan selector spesifik, cari semua div dan article
        if not news_containers:
            news_containers = soup.find_all(['div', 'article'])
            logger.info(f"✅ Menggunakan fallback: ditemukan {len(news_containers)} elemen div/article")
        
        logger.info(f"📊 Total kontainer berita yang akan diproses: {len(news_containers)}")
        
        for container in news_containers[:30]:  # Batasi 30 item untuk performa
            try:
                # Ekstrak judul - coba berbagai elemen
                title_elem = None
                for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    title_elem = container.find(tag)
                    if title_elem:
                        break
                
                if not title_elem:
                    title_elem = container.find('a')
                if not title_elem:
                    title_elem = container.find('span')
                if not title_elem:
                    title_elem = container.find('div', class_=lambda x: x and any(word in str(x).lower() for word in ['title', 'judul', 'head']))
                
                if not title_elem:
                    continue
                    
                title = title_elem.get_text(strip=True)
                if not title or len(title) < 10:
                    continue
                
                # Ekstrak link
                link_elem = container.find('a', href=True)
                if not link_elem:
                    # Jika tidak ada link di container, coba cari di parent
                    link_elem = title_elem.find('a', href=True)
                
                if not link_elem:
                    continue
                    
                link = link_elem['href']
                if link.startswith('/'):
                    link = f"https://www.idx.co.id{link}"
                elif not link.startswith('http'):
                    link = f"https://www.idx.co.id/{link}"
                
                # Skip link yang tidak valid
                if 'javascript:' in link or 'mailto:' in link or '#' in link:
                    continue
                
                # Ekstrak tanggal
                date_elem = (container.find('span', class_='date') or 
                            container.find('time') or
                            container.find('div', class_='date') or
                            container.find('span', class_=lambda x: x and 'date' in str(x).lower()))
                date = date_elem.get_text(strip=True) if date_elem else datetime.datetime.now().strftime("%Y-%m-%d")
                
                # Filter berita berdasarkan kata kunci
                keywords = [
                    'aksi korporasi', 'right issue', 'ekspansi bisnis', 'backdoor listing', 
                    'corporate action', 'rights issue', 'dividen', 'stock split', 'obligasi',
                    'emitmen', 'ipo', 'saham', 'bursa efek', 'korporasi', 'ekspansi',
                    'rups', 'ratah', 'obligasi', 'sukuk', 'reksadana'
                ]
                
                title_lower = title.lower()
                if any(keyword in title_lower for keyword in keywords):
                    news_items.append({
                        'title': title,
                        'link': link,
                        'date': date
                    })
                    logger.info(f"📰 Berita relevan: {title[:50]}...")
                    
            except Exception as e:
                logger.debug(f"Error parsing container: {e}")
                continue
                
        logger.info(f"✅ Total berita relevan ditemukan: {len(news_items)}")
        return news_items
        
    except Exception as e:
        logger.error(f"❌ Error Selenium: {e}")
        return []
    finally:
        if driver:
            driver.quit()

async def send_news(context: ContextTypes.DEFAULT_TYPE):
    """Kirim berita baru ke Telegram"""
    try:
        logger.info("🔍 Mengecek berita baru...")
        news_items = get_news_selenium()
        
        if not news_items:
            logger.info("📭 Tidak ada berita baru yang ditemukan")
            return
            
        sent_count = 0
        for item in news_items:
            # Cek duplikat berdasarkan judul DAN link (lebih akurat)
            title_hash = hash(item['title'].strip().lower())
            link_hash = hash(item['link'].strip().lower())
            
            if title_hash not in sent_news_titles and link_hash not in sent_news_links:
                message = (
                    f"📢 **{item['title']}**\n\n"
                    f"📅 {item['date']}\n\n"
                    f"🔗 {item['link']}\n\n"
                    f"#BeritaSaham #IDX #Investasi"
                )
                try:
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=message,
                        parse_mode='Markdown',
                        disable_web_page_preview=False
                    )
                    
                    # Simpan ke memory
                    sent_news_titles.add(title_hash)
                    sent_news_links.add(link_hash)
                    sent_count += 1
                    
                    logger.info(f"✅ Berita terkirim: {item['title'][:50]}...")
                    await asyncio.sleep(2)  # Delay 2 detik antar pesan
                    
                except Exception as e:
                    logger.error(f"❌ Error mengirim pesan: {e}")
            else:
                logger.debug(f"⏭️ Berita sudah pernah dikirim: {item['title'][:50]}...")
        
        logger.info(f"📨 Berhasil mengirim {sent_count} berita baru")
        
        # Bersihkan memory jika terlalu besar (prevent memory leak)
        if len(sent_news_titles) > 1000:
            sent_news_titles.clear()
            sent_news_links.clear()
            logger.info("🧹 Memory cache dibersihkan")
        
    except Exception as e:
        logger.error(f"❌ Error in send_news: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    await update.message.reply_text(
        "🤖 **IDX Stock News Bot** (Simple Version)\n\n"
        "Saya akan mengirimkan berita terbaru tentang:\n"
        "• 📊 Aksi Korporasi\n• 💰 Right Issue\n"
        "• 🏢 Ekspansi Bisnis\n• 🔄 Backdoor Listing\n"
        "• 💸 Dividen\n• 📈 Stock Split\n\n"
        "✅ **FITUR:**\n"
        "• Menggunakan Selenium\n• Auto-clean memory\n"
        "• Cek setiap 5 menit\n\n"
        "Bot aktif dan sedang memantau berita dari IDX!"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /status"""
    await update.message.reply_text(
        f"📊 **Status Bot**\n\n"
        f"• Berita yang sudah dikirim: {len(sent_news_titles)}\n"
        f"• Interval pengecekan: {CHECK_INTERVAL} detik\n"
        f"• Metode: Selenium WebDriver\n"
        f"• Penyimpanan: Memory (tanpa database)\n"
        f"• Terakhir dicek: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"• Status: ✅ AKTIF"
    )

async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /clear"""
    sent_news_titles.clear()
    sent_news_links.clear()
    await update.message.reply_text("✅ Cache berhasil dibersihkan! Semua berita akan dianggap baru.")

async def test_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /test - manual test"""
    await update.message.reply_text("🔍 Mengecek berita manual...")
    
    news_items = get_news_selenium()
    if news_items:
        message = f"✅ Ditemukan {len(news_items)} berita relevan:\n\n"
        for i, item in enumerate(news_items[:5]):  # Tampilkan 5 pertama
            message += f"{i+1}. {item['title']}\n"
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("❌ Tidak ada berita yang ditemukan.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Error handler"""
    logger.error(f"Exception while handling an update: {context.error}")

def main():
    """Main function"""
    try:
        # Test Selenium pertama kali
        logger.info("🚀 Memulai Bot IDX News (Simple Version)")
        logger.info("🔧 Testing Selenium...")
        
        # Test koneksi Selenium
        driver = setup_driver()
        try:
            driver.get("https://www.idx.co.id")
            logger.info("✅ Selenium berhasil diinisialisasi")
        finally:
            driver.quit()
        
        # Create Telegram application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CommandHandler("clear", clear_cache))
        application.add_handler(CommandHandler("test", test_news))
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Schedule news checking
        if application.job_queue:
            job_queue = application.job_queue
            job_queue.run_repeating(send_news, interval=CHECK_INTERVAL, first=10)
            logger.info(f"✅ JobQueue started dengan interval: {CHECK_INTERVAL} detik")
        else:
            logger.error("❌ JobQueue tidak tersedia!")
            return
        
        logger.info("🤖 Bot berhasil dimulai! Tekan Ctrl+C untuk berhenti.")
        logger.info("📋 Perintah yang tersedia: /start, /status, /clear, /test")
        
        # Start the bot
        application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Gagal memulai bot: {e}")

if __name__ == '__main__':
    main()