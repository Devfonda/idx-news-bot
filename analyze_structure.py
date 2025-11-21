from bs4 import BeautifulSoup
import re

def analyze_html_structure():
    print("🔍 Menganalisis struktur HTML IDX...")
    
    try:
        with open('selenium_page.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        print("📄 Informasi Halaman:")
        print(f"Title: {soup.title.string if soup.title else 'No title'}")
        
        # Cari semua elemen yang mungkin berisi berita
        print("\n🔎 Mencari elemen berita:")
        
        # Cari berdasarkan class yang umum untuk berita
        common_news_classes = [
            'news', 'berita', 'article', 'post', 'item', 'list', 'content'
        ]
        
        for class_name in common_news_classes:
            elements = soup.find_all(class_=re.compile(class_name, re.I))
            if elements:
                print(f"✅ Ditemukan {len(elements)} elemen dengan class mengandung '{class_name}':")
                for i, elem in enumerate(elements[:3]):
                    text = elem.get_text(strip=True)
                    if text and len(text) > 20:
                        print(f"   {i+1}. {text[:100]}...")
        
        # Cari semua article tags
        articles = soup.find_all('article')
        print(f"\n📰 Article tags: {len(articles)}")
        
        # Cari semua div dengan class tertentu
        divs_with_class = soup.find_all('div', class_=True)
        class_counter = {}
        for div in divs_with_class:
            classes = div.get('class', [])
            for cls in classes:
                class_counter[cls] = class_counter.get(cls, 0) + 1
        
        # Tampilkan class yang paling umum
        print(f"\n🏷️ Class yang paling umum:")
        sorted_classes = sorted(class_counter.items(), key=lambda x: x[1], reverse=True)
        for cls, count in sorted_classes[:10]:
            print(f"   {cls}: {count} elemen")
        
        # Cari semua link
        links = soup.find_all('a', href=True)
        print(f"\n🔗 Total link: {len(links)}")
        
        # Filter link yang mungkin berita
        news_links = []
        for link in links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Skip link yang tidak relevan
            if not text or len(text) < 10:
                continue
            if any(skip in href.lower() for skip in ['javascript:', '#', 'mailto:']):
                continue
            
            # Cari link berita
            if any(keyword in text.lower() for keyword in ['berita', 'news', 'update', 'terbaru', 'saham', 'emiten']):
                if href.startswith('/'):
                    href = f"https://www.idx.co.id{href}"
                news_links.append({'text': text, 'href': href})
        
        print(f"📋 Link berita potensial: {len(news_links)}")
        for i, link in enumerate(news_links[:10]):
            print(f"   {i+1}. {link['text'][:80]}...")
            print(f"      → {link['href']}")
        
        # Simpan analisis detail
        with open('structure_analysis.txt', 'w', encoding='utf-8') as f:
            f.write("ANALISIS STRUKTUR WEBSITE IDX\n")
            f.write("="*50 + "\n")
            f.write(f"Title: {soup.title.string if soup.title else 'No title'}\n")
            f.write(f"Total links: {len(links)}\n")
            f.write(f"Total articles: {len(articles)}\n\n")
            
            f.write("CLASS TERPOPULER:\n")
            for cls, count in sorted_classes[:20]:
                f.write(f"{cls}: {count}\n")
            
            f.write("\nLINK BERTITA:\n")
            for link in news_links[:20]:
                f.write(f"{link['text']} → {link['href']}\n")
        
        print(f"\n✅ Analisis lengkap disimpan di: structure_analysis.txt")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    analyze_html_structure()