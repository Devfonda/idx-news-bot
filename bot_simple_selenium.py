import os
import logging
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
from bs4 import BeautifulSoup
import requests
import asyncio
import datetime
import hashlib
import time
import traceback
from urllib.parse import urljoin, urlparse
import json

# Setup logging yang lebih detail
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Konfigurasi dari Environment Variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'

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
logger.info(f"   CHECK_INTERVAL: {CHECK_INTERVAL}")
logger.info(f"   DEBUG_MODE: {DEBUG_MODE}")

# Penyimpanan dalam memory dengan backup file
SENT_NEWS_FILE = "sent_news.txt"
SAMPLE_NEWS_FILE = "sample_news.json"
sent_news_titles = set()
sample_news_items = []  # Untuk menyimpan sample berita

def load_sent_news():
    """Load sent news from file"""
    global sent_news_titles
    try:
        if os.path.exists(SENT_NEWS_FILE):
            with open(SENT_NEWS_FILE, 'r', encoding='utf-8') as f:
                sent_news_titles = set(line.strip() for line in f if line.strip())
            logger.info(f"📁 Loaded {len(sent_news_titles)} sent news from file")
        else:
            logger.info("📁 No sent news file found, starting fresh")
    except Exception as e:
        logger.error(f"❌ Failed to load sent news: {e}")

def save_sent_news():
    """Save sent news to file"""
    try:
        with open(SENT_NEWS_FILE, 'w', encoding='utf-8') as f:
            for title_hash in sent_news_titles:
                f.write(title_hash + '\n')
        logger.info(f"💾 Saved {len(sent_news_titles)} news to file")
    except Exception as e:
        logger.error(f"❌ Failed to save sent news: {e}")

def load_sample_news():
    """Load sample news from file"""
    global sample_news_items
    try:
        if os.path.exists(SAMPLE_NEWS_FILE):
            with open(SAMPLE_NEWS_FILE, 'r', encoding='utf-8') as f:
                sample_news_items = json.load(f)
            logger.info(f"📁 Loaded {len(sample_news_items)} sample news from file")
        else:
            logger.info("📁 No sample news file found, starting fresh")
            sample_news_items = []
    except Exception as e:
        logger.error(f"❌ Failed to load sample news: {e}")
        sample_news_items = []

def save_sample_news():
    """Save sample news to file"""
    try:
        with open(SAMPLE_NEWS_FILE, 'w', encoding='utf-8') as f:
            json.dump(sample_news_items[-50:], f, indent=2, ensure_ascii=False)  # Simpan 50 terakhir
        logger.info(f"💾 Saved {len(sample_news_items)} sample news to file")
    except Exception as e:
        logger.error(f"❌ Failed to save sample news: {e}")

def add_sample_news(news_items):
    """Add new sample news items"""
    global sample_news_items
    
    for item in news_items:
        # Buat item sample dengan timestamp
        sample_item = item.copy()
        sample_item['sample_timestamp'] = datetime.datetime.now().isoformat()
        sample_item['sample_id'] = hashlib.md5(
            f"{item['title']}{item['link']}{datetime.datetime.now().timestamp()}".encode()
        ).hexdigest()[:8]
        
        sample_news_items.append(sample_item)
    
    # Batasi hanya 100 sample terakhir
    if len(sample_news_items) > 100:
        sample_news_items = sample_news_items[-100:]
    
    save_sample_news()

def validate_url(url):
    """Validate URL format"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def get_news_from_multiple_sources():
    """Ambil berita dari berbagai sumber dengan debugging detail"""
    all_news = []
    
    # Daftar sumber berita saham yang diperbarui
    sources = [
        {
            "name": "Kontan",
            "url": "https://www.kontan.co.id/search/saham",
            "selectors": [
                "a[class*='title']",
                "h3 a",
                "h2 a",
                ".title a",
                "a[href*='/news/']"
            ],
            "base_url": "https://www.kontan.co.id",
            "timeout": 20
        },
        {
            "name": "CNBC Indonesia", 
            "url": "https://www.cnbcindonesia.com/market",
            "selectors": [
                "a.title",
                "h2 a", 
                "h3 a",
                "a[href*='/news/']",
                ".list li a"
            ],
            "base_url": "https://www.cnbcindonesia.com",
            "timeout": 20
        },
        {
            "name": "Investasi Kontan",
            "url": "https://investasi.kontan.co.id/news",
            "selectors": [
                "a.title",
                "h2 a",
                "h3 a", 
                "a[href*='/news/']",
                ".article-title a"
            ],
            "base_url": "https://investasi.kontan.co.id",
            "timeout": 20
        }
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'id,en;q=0.9,en-US;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    for source_idx, source in enumerate(sources):
        source_name = source["name"]
        logger.info(f"🔍 [{source_idx+1}/{len(sources)}] Scraping from {source_name}: {source['url']}")
        
        try:
            start_time = time.time()
            response = requests.get(
                source["url"], 
                headers=headers, 
                timeout=source["timeout"],
                allow_redirects=True
            )
            response_time = time.time() - start_time
            
            logger.info(f"   ⏱️ Response time: {response_time:.2f}s, Status: {response.status_code}")
            
            if response.status_code != 200:
                logger.warning(f"   ⚠️ Failed to access {source_name}: HTTP {response.status_code}")
                if DEBUG_MODE and response.status_code == 403:
                    logger.warning(f"   🔍 Debug: Headers used - {headers}")
                continue
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'html' not in content_type:
                logger.warning(f"   ⚠️ Non-HTML content from {source_name}: {content_type}")
                continue
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Debug: log page title and meta
            if DEBUG_MODE:
                page_title = soup.find('title')
                if page_title:
                    logger.info(f"   🔍 Debug - Page title: {page_title.get_text(strip=True)[:100]}...")
                
                meta_description = soup.find('meta', attrs={'name': 'description'})
                if meta_description:
                    desc = meta_description.get('content', '')[:100]
                    logger.info(f"   🔍 Debug - Meta description: {desc}...")
            
            news_elements = []
            found_with_selector = None
            
            # Coba semua selector
            for selector in source["selectors"]:
                elements = soup.select(selector)
                logger.info(f"   🔍 Selector '{selector}': found {len(elements)} elements")
                
                if elements:
                    news_elements = elements
                    found_with_selector = selector
                    logger.info(f"   ✅ Using selector: {selector}")
                    break
            
            if not news_elements:
                logger.warning(f"   ⚠️ No news elements found in {source_name} with any selector")
                # Debug: log some sample HTML
                if DEBUG_MODE:
                    sample_html = str(soup)[:500]
                    logger.info(f"   🔍 Debug - Sample HTML: {sample_html}...")
                continue
            
            logger.info(f"   📰 Processing {len(news_elements)} elements from {source_name}")
            
            processed_count = 0
            for element_idx, element in enumerate(news_elements[:20]):  # Batasi 20 elemen
                try:
                    title = element.get_text(strip=True)
                    if not title:
                        if DEBUG_MODE:
                            logger.debug(f"   [{element_idx}] Empty title, skipping")
                        continue
                    
                    if len(title) < 15:
                        if DEBUG_MODE:
                            logger.debug(f"   [{element_idx}] Title too short: '{title}'")
                        continue
                    
                    # Dapatkan link
                    href = element.get('href', '')
                    if not href:
                        if DEBUG_MODE:
                            logger.debug(f"   [{element_idx}] No href found")
                        continue
                    
                    # Format URL lengkap
                    if href.startswith('/'):
                        full_url = urljoin(source["base_url"], href)
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = urljoin(source["base_url"] + '/', href)
                    
                    # Validasi URL
                    if not validate_url(full_url):
                        if DEBUG_MODE:
                            logger.debug(f"   [{element_idx}] Invalid URL: {full_url}")
                        continue
                    
                    # Skip link tidak valid
                    if any(invalid in full_url.lower() for invalid in ['javascript:', 'mailto:', '#', 'void(0)']):
                        if DEBUG_MODE:
                            logger.debug(f"   [{element_idx}] Invalid URL scheme: {full_url}")
                        continue
                    
                    # Filter berita relevan
                    if not is_relevant_news(title):
                        if DEBUG_MODE:
                            logger.debug(f"   [{element_idx}] Not relevant: '{title}'")
                        continue
                    
                    news_item = {
                        'title': title,
                        'link': full_url,
                        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'source': source_name,
                        'selector_used': found_with_selector,
                        'scrape_timestamp': datetime.datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    processed_count += 1
                    logger.info(f"   ✅ [{element_idx}] Added: {title[:60]}...")
                    
                except Exception as e:
                    logger.error(f"   ❌ Error processing element {element_idx} in {source_name}: {str(e)}")
                    if DEBUG_MODE:
                        logger.debug(f"   🔍 Element HTML: {str(element)[:200]}...")
                    continue
            
            logger.info(f"   📊 {source_name}: {processed_count} valid news processed")
                    
        except requests.exceptions.Timeout:
            logger.error(f"   ❌ Timeout accessing {source_name} after {source['timeout']}s")
        except requests.exceptions.ConnectionError:
            logger.error(f"   ❌ Connection error accessing {source_name}")
        except requests.exceptions.RequestException as e:
            logger.error(f"   ❌ Request exception accessing {source_name}: {e}")
        except Exception as e:
            logger.error(f"   ❌ Unexpected error accessing {source_name}: {e}")
            if DEBUG_MODE:
                logger.error(f"   🔍 Traceback: {traceback.format_exc()}")
        
        # Delay antara sumber berbeda
        if source_idx < len(sources) - 1:
            delay = 2
            logger.info(f"   ⏳ Waiting {delay}s before next source...")
            time.sleep(delay)
    
    # Hapus duplikat berdasarkan judul
    unique_news = []
    seen_titles = set()
    
    for item in all_news:
        title_hash = hashlib.md5(item['title'].lower().strip().encode()).hexdigest()
        if title_hash not in seen_titles:
            seen_titles.add(title_hash)
            unique_news.append(item)
    
    logger.info(f"📊 FINAL: {len(all_news)} raw → {len(unique_news)} unique news")
    
    # Simpan sebagai sample berita
    if unique_news:
        add_sample_news(unique_news)
        logger.info(f"💾 Saved {len(unique_news)} news as samples")
    
    # Log sample news for debugging
    if DEBUG_MODE and unique_news:
        logger.info("🔍 Sample unique news:")
        for i, item in enumerate(unique_news[:3]):
            logger.info(f"   {i+1}. {item['source']}: {item['title'][:80]}...")
    
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
        'keuangan', 'profit', 'ekspansi', 'rupiah', 'dolar', 'ekonomi',
        'bni', 'bca', 'bbri', 'bbca', 'bmri', 'tlkm', 'asii', 'antm',
        'bbni', 'itmg', 'adro', 'mdka', 'inkp', 'jsmr', 'tpia', 'wika',
        'smgr', 'insi', 'icbp', 'unvr', 'myor', 'ultj'
    ]
    
    # Tambahkan kata kunci sektor tertentu
    sector_keywords = [
        'bank', 'tambang', 'minyak', 'gas', 'property', 'real estate',
        'konstruksi', 'infrastruktur', 'technology', 'telekomunikasi',
        'konsumsi', 'retail', 'farmasi', 'kesehatan', 'otomotif'
    ]
    
    all_keywords = keywords + sector_keywords
    
    return any(keyword in title_lower for keyword in all_keywords)

async def send_news(context: ContextTypes.DEFAULT_TYPE):
    """Kirim berita baru ke Telegram dengan error handling yang lebih baik"""
    job_name = context.job.name if context.job else "manual"
    logger.info(f"🔄 [{job_name}] Starting news check...")
    
    try:
        news_items = get_news_from_multiple_sources()
        
        if not news_items:
            logger.info(f"📭 [{job_name}] No news items found")
            return
            
        sent_count = 0
        error_count = 0
        
        for item_idx, item in enumerate(news_items):
            try:
                title_hash = hashlib.md5(item['title'].strip().lower().encode()).hexdigest()
                
                if title_hash in sent_news_titles:
                    if DEBUG_MODE:
                        logger.debug(f"   [{item_idx}] Already sent: {item['title'][:50]}...")
                    continue
                
                # Format pesan
                message = (
                    f"📢 **{item['title']}**\n\n"
                    f"📅 {item['date']}\n"
                    f"🌐 Sumber: {item['source']}\n\n"
                    f"🔗 {item['link']}\n\n"
                    f"#{item['source'].replace(' ', '')} #BeritaSaham #Investasi"
                )
                
                # Kirim pesan
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=message,
                    parse_mode='Markdown',
                    disable_web_page_preview=False
                )
                
                sent_news_titles.add(title_hash)
                sent_count += 1
                
                logger.info(f"   ✅ [{item_idx}] Sent: {item['title'][:60]}...")
                
                # Delay antar pesan untuk menghindari rate limit
                if item_idx < len(news_items) - 1:
                    delay = 1.5
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                error_count += 1
                logger.error(f"   ❌ [{item_idx}] Failed to send news: {str(e)}")
                if "Message is too long" in str(e):
                    logger.error(f"   📝 Message too long, trimming...")
                    # Coba kirim versi yang lebih pendek
                    try:
                        short_message = (
                            f"📢 **{item['title'][:100]}...**\n\n"
                            f"🔗 {item['link']}\n\n"
                            f"#{item['source'].replace(' ', '')} #BeritaSaham"
                        )
                        await context.bot.send_message(
                            chat_id=CHANNEL_ID,
                            text=short_message,
                            parse_mode='Markdown'
                        )
                        sent_news_titles.add(title_hash)
                        sent_count += 1
                        logger.info(f"   ✅ [{item_idx}] Sent trimmed version")
                    except Exception as e2:
                        logger.error(f"   ❌ [{item_idx}] Also failed to send trimmed version: {e2}")
        
        logger.info(f"📨 [{job_name}] Completed: {sent_count} sent, {error_count} errors")
        
        # Simpan ke file
        if sent_count > 0:
            save_sent_news()
        
        # Cleanup memory
        if len(sent_news_titles) > 500:
            # Simpan hanya 300 terbaru
            temp_list = list(sent_news_titles)[-300:]
            sent_news_titles.clear()
            sent_news_titles.update(temp_list)
            save_sent_news()
            logger.info("🧹 Memory cache cleaned (kept 300 most recent)")
            
    except Exception as e:
        logger.error(f"❌ [{job_name}] Critical error in send_news: {e}")
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start"""
    user = update.effective_user
    logger.info(f"👤 User {user.id} ({user.first_name}) used /start")
    
    await update.message.reply_text(
        "🤖 **IDX Stock News Bot**\n\n"
        "Saya mengirimkan berita saham terbaru dari:\n"
        "• 📊 Kontan\n• 📈 CNBC Indonesia\n"
        "• 💰 Investasi Kontan\n\n"
        "📋 Perintah tersedia:\n"
        "• /start - Info bot\n"
        "• /status - Status\n" 
        "• /test - Test berita\n"
        "• /clear - Reset cache\n"
        "• /debug - Debug info\n"
        "• /sample - Lihat sample berita\n\n"
        "🔧 Deployed di Railway"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /status"""
    user = update.effective_user
    logger.info(f"👤 User {user.id} used /status")
    
    # Info tentang jobs yang aktif
    job_count = len(context.application.job_queue.jobs()) if context.application.job_queue else 0
    
    await update.message.reply_text(
        f"📊 **Status Bot**\n\n"
        f"• Berita dikirim: {len(sent_news_titles)}\n"
        f"• Sample berita: {len(sample_news_items)}\n"
        f"• Jobs aktif: {job_count}\n"
        f"• Interval: {CHECK_INTERVAL} detik\n"
        f"• Debug mode: {'✅ ON' if DEBUG_MODE else '❌ OFF'}\n"
        f"• Terakhir dicek: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"• Status: ✅ AKTIF\n\n"
        f"💾 Cache file: {'✅ Ada' if os.path.exists(SENT_NEWS_FILE) else '❌ Tidak ada'}\n"
        f"💾 Sample file: {'✅ Ada' if os.path.exists(SAMPLE_NEWS_FILE) else '❌ Tidak ada'}"
    )

async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /clear"""
    user = update.effective_user
    logger.info(f"👤 User {user.id} used /clear")
    
    old_count = len(sent_news_titles)
    sent_news_titles.clear()
    
    # Hapus file cache juga
    if os.path.exists(SENT_NEWS_FILE):
        os.remove(SENT_NEWS_FILE)
    
    await update.message.reply_text(f"✅ Cache berhasil dibersihkan! ({old_count} entri dihapus)")

async def test_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /test"""
    user = update.effective_user
    logger.info(f"👤 User {user.id} used /test")
    
    await update.message.reply_text("🔍 Testing pencarian berita...")
    
    try:
        news_items = get_news_from_multiple_sources()
        
        if news_items:
            message = f"✅ Ditemukan {len(news_items)} berita:\n\n"
            for i, item in enumerate(news_items[:5]):  # Tampilkan max 5
                message += f"{i+1}. **{item['source']}**: {item['title']}\n"
                message += f"   🔗 {item['link']}\n\n"
            
            # Jika pesan terlalu panjang, potong
            if len(message) > 4000:
                message = message[:4000] + "\n\n... (truncated)"
                
            await update.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Tidak ada berita ditemukan")
            
    except Exception as e:
        error_msg = f"❌ Error during test: {str(e)}"
        logger.error(error_msg)
        await update.message.reply_text(error_msg)

async def debug_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /debug"""
    user = update.effective_user
    logger.info(f"👤 User {user.id} used /debug")
    
    debug_info = (
        f"🐛 **Debug Information**\n\n"
        f"• Python: {os.sys.version}\n"
        f"• Environment: {os.getenv('RAILWAY_ENVIRONMENT', 'Unknown')}\n"
        f"• Memory usage: {len(sent_news_titles)} cached news\n"
        f"• Sample news: {len(sample_news_items)} items\n"
        f"• Check interval: {CHECK_INTERVAL}s\n"
        f"• Debug mode: {DEBUG_MODE}\n"
        f"• Current time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"• Cache file: {SENT_NEWS_FILE} ({os.path.getsize(SENT_NEWS_FILE) if os.path.exists(SENT_NEWS_FILE) else 0} bytes)\n"
        f"• Sample file: {SAMPLE_NEWS_FILE} ({os.path.getsize(SAMPLE_NEWS_FILE) if os.path.exists(SAMPLE_NEWS_FILE) else 0} bytes)\n"
    )
    
    await update.message.reply_text(debug_info)

async def sample_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /sample - Tampilkan sample berita yang berhasil di-scrape"""
    user = update.effective_user
    logger.info(f"👤 User {user.id} used /sample")
    
    if not sample_news_items:
        await update.message.reply_text(
            "📭 Belum ada sample berita yang tersimpan.\n\n"
            "Tunggu hingga bot melakukan scraping berikutnya atau gunakan /test untuk test scraping sekarang."
        )
        return
    
    # Ambil parameter jumlah sample (default 5)
    try:
        count = int(context.args[0]) if context.args else 5
        count = min(max(1, count), 10)  # Batasi antara 1-10
    except (ValueError, IndexError):
        count = 5
    
    # Ambil sample terbaru
    recent_samples = sample_news_items[-count:]
    
    message = f"📊 **Sample Berita Terbaru** ({len(recent_samples)} dari {len(sample_news_items)} total)\n\n"
    
    for i, item in enumerate(recent_samples, 1):
        timestamp = datetime.datetime.fromisoformat(item['scrape_timestamp']).strftime("%H:%M:%S")
        message += (
            f"**{i}. {item['source']}** ({timestamp})\n"
            f"📰 {item['title']}\n"
            f"🔗 {item['link']}\n\n"
        )
    
    # Tambahkan statistik
    sources_count = {}
    for item in sample_news_items:
        sources_count[item['source']] = sources_count.get(item['source'], 0) + 1
    
    message += "**📈 Statistik Sample:**\n"
    for source, count in sources_count.items():
        message += f"• {source}: {count} berita\n"
    
    # Jika pesan terlalu panjang, kirim multiple messages
    if len(message) > 4000:
        parts = []
        current_part = ""
        lines = message.split('\n')
        
        for line in lines:
            if len(current_part + line + '\n') > 4000:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'
        
        if current_part:
            parts.append(current_part)
        
        for i, part in enumerate(parts):
            if i == 0:
                await update.message.reply_text(part, parse_mode='Markdown', disable_web_page_preview=True)
            else:
                await update.message.reply_text(f"*(lanjutan {i+1}/{len(parts)})*\n\n{part}", 
                                              parse_mode='Markdown', disable_web_page_preview=True)
            await asyncio.sleep(0.5)
    else:
        await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)

async def clear_samples(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /clearsamples - Hapus semua sample berita"""
    user = update.effective_user
    logger.info(f"👤 User {user.id} used /clearsamples")
    
    old_count = len(sample_news_items)
    sample_news_items.clear()
    
    # Hapus file sample juga
    if os.path.exists(SAMPLE_NEWS_FILE):
        os.remove(SAMPLE_NEWS_FILE)
    
    await update.message.reply_text(f"✅ Sample berita berhasil dibersihkan! ({old_count} sample dihapus)")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler dengan detail lebih"""
    error_msg = f"Update {update} caused error {context.error}"
    logger.error(error_msg)
    
    # Log traceback lengkap
    logger.error(f"🔍 Full traceback: {traceback.format_exc()}")
    
    # Kirim pesan error ke user jika ada update
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Terjadi error saat memproses perintah. Silakan coba lagi."
            )
        except Exception:
            pass

def main():
    """Main function dengan error handling yang lebih baik"""
    try:
        logger.info("🚀 Starting Enhanced News Bot with Sample Feature...")
        logger.info("📦 Loading sent news cache...")
        
        # Load cache yang tersimpan
        load_sent_news()
        load_sample_news()
        
        # Buat application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CommandHandler("test", test_news))
        application.add_handler(CommandHandler("clear", clear_cache))
        application.add_handler(CommandHandler("debug", debug_info))
        application.add_handler(CommandHandler("sample", sample_news))
        application.add_handler(CommandHandler("clearsamples", clear_samples))
        
        # Setup error handler
        application.add_error_handler(error_handler)
        
        # Schedule job dengan nama untuk identifikasi
        if application.job_queue:
            job = application.job_queue.run_repeating(
                send_news, 
                interval=CHECK_INTERVAL, 
                first=10,
                name="news_checker"
            )
            logger.info(f"✅ Scheduled job '{job.name}' dengan interval {CHECK_INTERVAL}s")
        else:
            logger.error("❌ Job queue not available!")
        
        logger.info("🤖 Bot started successfully! Press Ctrl+C to stop.")
        
        # Start polling dengan config yang lebih robust
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )
        
    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user (Ctrl+C)")
        save_sent_news()  # Simpan sebelum exit
        save_sample_news()  # Simpan sample sebelum exit
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        save_sent_news()  # Coba simpan sebelum exit
        save_sample_news()  # Coba simpan sample sebelum exit
        exit(1)

if __name__ == '__main__':
    main()