import os
import time
import feedparser
import urllib.parse
import requests
from groq import Groq 
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import sys

# ==========================================
# 1. KONFIGURASI KREDENSIAL & API
# ==========================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama3-70b-8192" 

BLOG_ID = os.environ.get("BLOG_ID")
SCOPES = ['https://www.googleapis.com/auth/blogger']
TOKEN_FILE = 'token.json'
INDEXING_SCOPES = ['https://www.googleapis.com/auth/indexing']
INDEXING_KEY_FILE = 'service_account.json'

FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")

HISTORY_FILE = 'history.txt' # File penyimpan riwayat

# --- Inisialisasi Blogger API ---
try:
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        blogger_service = build('blogger', 'v3', credentials=creds)
        print("✅ Otentikasi Blogger berhasil.")
    else:
        raise FileNotFoundError(f"File {TOKEN_FILE} tidak ditemukan di sistem!")
except Exception as e:
    print(f"FATAL ERROR: Otentikasi Blogger Gagal: {e}")
    sys.exit(1)

# --- Inisialisasi Indexing API ---
indexing_service = None
try:
    if os.path.exists(INDEXING_KEY_FILE):
        idx_creds = service_account.Credentials.from_service_account_file(INDEXING_KEY_FILE, scopes=INDEXING_SCOPES)
        indexing_service = build('indexing', 'v3', credentials=idx_creds)
        print("✅ Google Indexing API siap digunakan.")
    else:
        print("⚠️ File service_account.json tidak ditemukan.")
except Exception as e:
    print(f"⚠️ Gagal menginisialisasi Indexing API: {e}")

# ==========================================
# 2. SUMBER BERITA (DIBAGI 2 KATEGORI)
# ==========================================
RSS_FEEDS = {
    "Sepakbola Nasional": [
        "https://news.google.com/rss/search?q=Timnas+Indonesia+when:1d&hl=id&gl=ID&ceid=ID:id",
        "https://news.google.com/rss/search?q=Liga+1+Indonesia+when:1d&hl=id&gl=ID&ceid=ID:id",
        "https://www.bing.com/news/search?q=Timnas+Indonesia+OR+Liga+1+Indonesia&format=rss",
        "https://www.antaranews.com/rss/olahraga.xml"
    ],
    "Sepakbola Dunia": [
        "https://news.google.com/rss/search?q=Liga+Inggris+OR+Liga+Champions+when:1d&hl=id&gl=ID&ceid=ID:id",
        "https://news.google.com/rss/search?q=Real+Madrid+OR+Barcelona+when:1d&hl=id&gl=ID&ceid=ID:id",
        "https://feeds.bbci.co.uk/sport/football/rss.xml",
        "https://www.skysports.com/rss/12040"
    ]
}

# ==========================================
# 3. FUNGSI UTAMA
# ==========================================
def muat_riwayat_lokal():
    """Membaca file history.txt jika ada."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def simpan_riwayat_lokal(link):
    """Menyimpan link ke file history.txt."""
    with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{link}\n")

def dapatkan_berita_dari_rss(kategori_rss, limit_per_sumber=2):
    semua_berita = []
    for kategori, daftar_url in kategori_rss.items():
        for url in daftar_url:
            print(f"Membaca RSS [{kategori}] dari: {url}")
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:limit_per_sumber]:
                    gambar_url = ""
                    link_asli = entry.get('link', entry.get('id', ''))
                    
                    try:
                        if 'media_content' in entry and len(entry.media_content) > 0:
                            gambar_url = entry.media_content[0].get('url', '')
                        elif 'links' in entry:
                            for link in entry.links:
                                if link.get('rel') == 'enclosure' and 'image' in link.get('type', ''):
                                    gambar_url = link.get('href', '')
                                    break
                        
                        if not gambar_url:
                            prompt_gambar = f"High quality cinematic sports photography, professional football match action, dramatic lighting, illustration of: {entry.title}"
                            prompt_aman = urllib.parse.quote(prompt_gambar)
                            gambar_url = f"https://image.pollinations.ai/prompt/{prompt_aman}?width=800&height=400&nologo=true"
                    except Exception:
                        pass

                    berita = {
                        'judul': entry.title,
                        'link': link_asli,
                        'deskripsi': entry.get('summary', entry.get('description', '')),
                        'gambar': gambar_url,
                        'kategori': kategori 
                    }
                    semua_berita.append(berita)
            except Exception as e:
                print(f"Gagal membaca RSS {url}: {e}")
    return semua_berita

def tulis_artikel_dengan_groq(berita):
    konteks = "sepakbola Indonesia (seperti Timnas, Liga 1, pemain keturunan, dll)" if berita['kategori'] == 'Sepakbola Nasional' else "sepakbola mancanegara (Liga Top Eropa, Liga Champions, superstar dunia, dll)"
    
    prompt = f"""
    Bertindaklah sebagai jurnalis olahraga profesional dan pandit sepakbola yang bersemangat, tajam, dan informatif. 
    Tulis ulang berita sepakbola berikut ke dalam bahasa Indonesia yang memancing rasa penasaran, mendalam, dan SEO friendly. 
    Fokuskan nuansanya pada kancah {konteks}.
    
    Data Berita Asli:
    Judul: {berita['judul']}
    Deskripsi: {berita['deskripsi']}
    
    Syarat penulisan:
    1. Buat Judul baru yang sangat clickbait, heboh, namun tetap relevan dengan isi berita dan tidak hoaks.
    2. Tulis isi artikel minimal 3 paragraf dengan gaya bahasa asyik ala komentator bola.
    3. Format artikel harus menggunakan tag HTML (seperti <h2>, <p>, <strong>, <em>).
    4. Jangan masukkan tag <html>, <head>, atau <body>, cukup isi artikelnya saja.
    5. Berikan kredit sumber berita di akhir artikel (Sumber: <a href="{berita['link']}">{berita['link']}</a>).
    """
    
    for attempt in range(3):
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=GROQ_MODEL,
                temperature=0.7,
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            wait_time = (attempt + 1) * 30
            print(f"⚠️ Error/Limit API Groq: {e}. Menunggu {wait_time} detik...")
            time.sleep(wait_time)
            
    return None

def posting_ke_blogger(judul, konten_html, label_kategori):
    if not BLOG_ID:
        print("❌ BLOG_ID tidak ditemukan!")
        return None

    post_body = {
        'title': judul,
        'content': konten_html,
        'labels': [label_kategori, 'Berita Bola Terpanas']
    }
    
    try:
        request = blogger_service.posts().insert(blogId=BLOG_ID, body=post_body)
        response = request.execute()
        post_url = response.get('url')
        print(f"✅ Sukses memposting ke Blogger dengan label '{label_kategori}': {post_url}")

        if indexing_service and post_url:
            try:
                notification = {'url': post_url, 'type': 'URL_UPDATED'}
                indexing_service.urlNotifications().publish(body=notification).execute()
                print(f"🚀 [AUTO-INDEX] Ping berhasil!")
            except Exception as idx_err:
                print(f"⚠️ [AUTO-INDEX] Gagal submit ke Google Search: {idx_err}")
                
        return post_url 
    except Exception as e:
        print(f"❌ Gagal memposting ke Blogger: {e}")
        return None

def posting_ke_facebook(judul, url_artikel):
    if not FB_ACCESS_TOKEN or not FB_PAGE_ID:
        print("⚠️ Rahasia Facebook tidak ditemukan. Melewati auto-post FB.")
        return

    pesan_status = f"🔥 Berita Terpanas Baru Saja Rilis!\n\n{judul}\n\n🔗 Sumber Berita: {url_artikel}\n\nBaca selengkapnya di link bawah ini 👇"
    url_api = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed"
    payload = {
        'message': pesan_status,
        'link': url_artikel,
        'access_token': FB_ACCESS_TOKEN
    }

    try:
        response = requests.post(url_api, data=payload)
        if response.status_code == 200:
            print("✅ [AUTO-SOSMED] Sukses membagikan tautan ke Halaman Facebook!")
        else:
            print(f"⚠️ [AUTO-SOSMED] Gagal memposting ke Facebook: {response.text}")
    except Exception as e:
        print(f"❌ [AUTO-SOSMED] Error saat menghubungi Facebook API: {e}")

# ==========================================
# 4. EKSEKUSI PROGRAM
# ==========================================
def main():
    print("=== Memulai Auto-Blogger Sepakbola (Didukung oleh Groq AI) ===")
    
    # KINI HANYA MENGANDALKAN HISTORY LOKAL
    riwayat_lokal = muat_riwayat_lokal()
    print(f"📂 Ditemukan {len(riwayat_lokal)} riwayat di history.txt")
    
    link_sesi_ini = set() 
    
    daftar_berita = dapatkan_berita_dari_rss(RSS_FEEDS, limit_per_sumber=2)
    print(f"Ditemukan total {len(daftar_berita)} berita bola dari RSS.")
    
    for index, berita in enumerate(daftar_berita):
        print(f"\n[{index + 1}/{len(daftar_berita)}] Mengecek berita [{berita['kategori']}]: {berita['judul']}")
        
        if not berita['link'] or len(berita['link']) < 5:
            continue

        # 1. CEK HISTORY LOKAL (Mutlak)
        if (berita['link'] in riwayat_lokal) or (berita['link'] in link_sesi_ini):
            print("⏩ Melewati berita: Sudah diposting sebelumnya (Duplikat).")
            continue
            
        link_sesi_ini.add(berita['link'])
        hasil_ai = tulis_artikel_dengan_groq(berita)
        
        if hasil_ai:
            baris_teks = hasil_ai.split('\n')
            judul_baru = baris_teks[0].replace('<h1>', '').replace('</h1>', '').replace('##', '').replace('**', '').strip()
            konten_artikel = '\n'.join(baris_teks[1:]).replace('```html', '').replace('```', '')
            
            tag_pelacak = f"\n"
            konten_artikel = tag_pelacak + konten_artikel
            
            if berita['gambar']:
                tag_gambar = f'<div style="text-align: center; margin-bottom: 20px;"><img src="{berita["gambar"]}" alt="{judul_baru}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);" /></div>\n'
                konten_artikel = tag_gambar + konten_artikel

            kode_iklan = """
            <div style="margin-top: 30px; margin-bottom: 20px; text-align: center;">
                <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5762789427984759" crossorigin="anonymous"></script>
            </div>
            """
            konten_artikel = konten_artikel + kode_iklan

            post_url = posting_ke_blogger(judul_baru, konten_artikel, berita['kategori'])
            
            # Jika sukses posting ke Blogger, share ke FB lalu simpan ke history.txt
            if post_url:
                posting_ke_facebook(judul_baru, post_url)
                simpan_riwayat_lokal(berita['link'])
                riwayat_lokal.add(berita['link'])
            
            print("⏳ Menunggu 20 detik sebelum memproses berita selanjutnya...")
            time.sleep(20)
        else:
            print(f"Gagal di-generate, melewati artikel: {berita['judul']}")

    print("\n=== Proses Auto-Blogger Selesai ===")

if __name__ == '__main__':
    main()
