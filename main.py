import os
import time
import feedparser
import urllib.parse
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.api_core.exceptions import ResourceExhausted
import sys

# ==========================================
# 1. KONFIGURASI KREDENSIAL & API
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel('gemini-3.5-flash')

BLOG_ID = os.environ.get("BLOG_ID")
SCOPES = ['https://www.googleapis.com/auth/blogger']
TOKEN_FILE = 'token.json'

INDEXING_SCOPES = ['https://www.googleapis.com/auth/indexing']
INDEXING_KEY_FILE = 'service_account.json'

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

indexing_service = None
try:
    if os.path.exists(INDEXING_KEY_FILE):
        idx_creds = service_account.Credentials.from_service_account_file(INDEXING_KEY_FILE, scopes=INDEXING_SCOPES)
        indexing_service = build('indexing', 'v3', credentials=idx_creds)
        print("✅ Google Indexing API siap digunakan.")
    else:
        print("⚠️ File service_account.json tidak ditemukan. Melewati fitur Auto-Indexing.")
except Exception as e:
    print(f"⚠️ Gagal menginisialisasi Indexing API: {e}")

# ==========================================
# 2. DAFTAR SUMBER RSS (SEPAKBOLA INDONESIA)
# ==========================================
RSS_FEEDS = [
    "https://www.suara.com/rss/bola",
    "https://sindonews.com/feed/soccer",
    "https://www.cnnindonesia.com/olahraga/rss",
    "https://www.republika.co.id/rss/sepakbola"
]

# ==========================================
# 3. FUNGSI UTAMA
# ==========================================
def ambil_riwayat_postingan():
    riwayat_konten = []
    if not BLOG_ID:
        return riwayat_konten
    try:
        request = blogger_service.posts().list(blogId=BLOG_ID, maxResults=30, status='LIVE')
        response = request.execute()
        posts = response.get('items', [])
        for post in posts:
            riwayat_konten.append(post.get('content', ''))
        print(f"🔍 Sistem Anti-Duplikat aktif: Memeriksa {len(posts)} artikel AKTIF terdahulu.")
    except Exception as e:
        print(f"⚠️ Gagal mengambil riwayat artikel: {e}")
    return riwayat_konten

def dapatkan_berita_dari_rss(rss_urls, limit_per_sumber=3):
    semua_berita = []
    for url in rss_urls:
        print(f"Membaca RSS dari: {url}")
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
                    elif 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
                        gambar_url = entry.media_thumbnail[0].get('url', '')
                        
                    if not gambar_url:
                        # PROMPT GAMBAR KHUSUS SEPAKBOLA
                        prompt_gambar = f"High quality cinematic sports photography, Indonesian football match, dramatic lighting, action shot, illustration of: {entry.title}"
                        prompt_aman = urllib.parse.quote(prompt_gambar)
                        gambar_url = f"https://image.pollinations.ai/prompt/{prompt_aman}?width=800&height=400&nologo=true"
                except Exception:
                    pass

                berita = {
                    'judul': entry.title,
                    'link': link_asli,
                    'deskripsi': entry.get('summary', entry.get('description', '')),
                    'gambar': gambar_url
                }
                semua_berita.append(berita)
        except Exception as e:
            print(f"Gagal membaca RSS {url}: {e}")
    return semua_berita

def tulis_artikel_dengan_gemini(berita):
    # PROMPT GEMINI KHUSUS KOMENTATOR BOLA INDONESIA
    prompt = f"""
    Bertindaklah sebagai jurnalis olahraga profesional dan pandit sepakbola Indonesia yang bersemangat, tajam, dan informatif. 
    Tulis ulang berita sepakbola berikut ke dalam bahasa Indonesia yang memancing rasa penasaran (terpanas), mendalam, dan SEO friendly. Fokuskan nuansanya pada kancah sepakbola Indonesia (Timnas, Liga 1, pemain keturunan, dll).
    
    Data Berita Asli:
    Judul: {berita['judul']}
    Deskripsi: {berita['deskripsi']}
    
    Syarat penulisan:
    1. Buat Judul baru yang sangat clickbait, heboh, namun tetap relevan dengan isi berita dan tidak hoaks.
    2. Tulis isi artikel minimal 3 paragraf dengan gaya bahasa asyik ala komentator bola Indonesia (boleh pakai istilah seperti 'menggetarkan jala', 'taktik jitu', dll).
    3. Format artikel harus menggunakan tag HTML (seperti <h2>, <p>, <strong>, <em>) agar siap diposting di Blogger.
    4. Jangan masukkan tag <html>, <head>, atau <body>, cukup isi artikelnya saja.
    5. Berikan kredit sumber berita di akhir artikel dengan format HTML link (Sumber: <a href="{berita['link']}">{berita['link']}</a>).
    """
    
    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            return response.text
        except ResourceExhausted:
            wait_time = (attempt + 1) * 30
            print(f"⚠️ Limit API Gemini tercapai. Menunggu {wait_time} detik...")
            time.sleep(wait_time)
        except Exception as e:
            print(f"Error saat memanggil Gemini: {e}")
            return None
            
    return None

def posting_ke_blogger(judul, konten_html):
    if not BLOG_ID:
        print("❌ BLOG_ID tidak ditemukan!")
        return

    # LABEL KHUSUS BLOG BOLA
    post_body = {
        'title': judul,
        'content': konten_html,
        'labels': ['Sepakbola Indonesia', 'Berita Bola Terpanas', 'Timnas', 'Liga 1']
    }
    
    try:
        request = blogger_service.posts().insert(blogId=BLOG_ID, body=post_body)
        response = request.execute()
        post_url = response.get('url')
        print(f"✅ Sukses memposting: {post_url}")

        if indexing_service and post_url:
            try:
                notification = {'url': post_url, 'type': 'URL_UPDATED'}
                indexing_service.urlNotifications().publish(body=notification).execute()
                print(f"🚀 [AUTO-INDEX] Ping berhasil! URL telah disubmit ke Google Search.")
            except Exception as idx_err:
                print(f"⚠️ [AUTO-INDEX] Gagal submit ke Google Search: {idx_err}")
                
    except Exception as e:
        print(f"❌ Gagal memposting ke Blogger: {e}")

# ==========================================
# 4. EKSEKUSI PROGRAM
# ==========================================
def main():
    print("=== Memulai Auto-Blogger Sepakbola Indonesia ===")
    
    riwayat_postingan = ambil_riwayat_postingan()
    link_sesi_ini = set() 
    
    daftar_berita = dapatkan_berita_dari_rss(RSS_FEEDS, limit_per_sumber=3)
    print(f"Ditemukan total {len(daftar_berita)} berita bola dari RSS.")
    
    for index, berita in enumerate(daftar_berita):
        print(f"\n[{index + 1}/{len(daftar_berita)}] Mengecek berita: {berita['judul']}")
        
        tag_pelacak = f"<!-- PELACAK_SUMBER: {berita['link']} -->"
        link_pelacak = f'href="{berita["link"]}"'
        
        sudah_diposting = False
        for konten in riwayat_postingan:
            if tag_pelacak in konten or link_pelacak in konten:
                sudah_diposting = True
                break
                
        if sudah_diposting or (berita['link'] in link_sesi_ini):
            print("⏩ Melewati berita: Sudah pernah diposting (Duplikat).")
            continue
            
        link_sesi_ini.add(berita['link'])

        hasil_gemini = tulis_artikel_dengan_gemini(berita)
        
        if hasil_gemini:
            baris_teks = hasil_gemini.split('\n')
            judul_baru = baris_teks[0].replace('<h1>', '').replace('</h1>', '').replace('##', '').replace('**', '').strip()
            konten_artikel = '\n'.join(baris_teks[1:]).replace('```html', '').replace('```', '')
            
            konten_artikel = f"{tag_pelacak}\n" + konten_artikel
            
            if berita['gambar']:
                tag_gambar = f'<div style="text-align: center; margin-bottom: 20px;"><img src="{berita["gambar"]}" alt="{judul_baru}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);" /></div>\n'
                konten_artikel = tag_gambar + konten_artikel

            # KODE IKLAN ADSENSE (Tetap dipertahankan dari versi sebelumnya)
            kode_iklan = """
            <div style="margin-top: 30px; margin-bottom: 20px; text-align: center;">
                <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5762789427984759" crossorigin="anonymous"></script>
            </div>
            """
            konten_artikel = konten_artikel + kode_iklan

            posting_ke_blogger(judul_baru, konten_artikel)
            
            print("⏳ Menunggu 20 detik sebelum memproses berita selanjutnya (Anti-Limit)...")
            time.sleep(20)
        else:
            print(f"Gagal di-generate, melewati artikel: {berita['judul']}")

    print("\n=== Proses Auto-Blogger Selesai ===")

if __name__ == '__main__':
    main()
