import os
import shutil
import random
import json
import google.generativeai as genai
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from yt_dlp import YoutubeDL
from moviepy.editor import VideoFileClip

# --- Konfigurasi AI ---
# Kunci API akan diambil dari "Secrets" di Replit.
try:
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
    if GOOGLE_API_KEY:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
    else:
        model = None
        print("Peringatan: GOOGLE_API_KEY tidak ditemukan di Secrets. AI tidak akan berfungsi.")
except Exception as e:
    print(f"Peringatan: Gagal mengkonfigurasi Google AI. Error: {e}")
    model = None

# Setup Flask App
app = Flask(__name__)
CORS(app)

# Folder untuk menyimpan video sementara
TEMP_DIR = "/tmp/temp_clips"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Rute untuk Menyajikan Halaman Web ---
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# --- Rute untuk API & File Klip ---
@app.route('/process-video', methods=['POST'])
def process_video():
    data = request.get_json()
    yt_url = data.get('url')

    if not yt_url:
        return jsonify({"error": "URL tidak ditemukan"}), 400

    try:
        # --- 1. Mengunduh Video & Transkrip dari YouTube ---
        ydl_opts = {
            'format': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(TEMP_DIR, '%(id)s.%(ext)s'),
            'writesubtitles': True,
            'subtitleslangs': ['id', 'en'],
            'quiet': True,
            'skip_download': False
        }
        
        transcript_text = "Tidak ada transkrip yang ditemukan."
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(yt_url, download=True)
            video_id = info_dict.get("id", "default_id")
            video_title = info_dict.get('title', 'Judul Tidak Ditemukan')
            original_filepath = os.path.join(TEMP_DIR, f"{video_id}.mp4")
            
            subtitle_path_id = os.path.join(TEMP_DIR, f"{video_id}.id.vtt")
            subtitle_path_en = os.path.join(TEMP_DIR, f"{video_id}.en.vtt")
            
            chosen_subtitle_path = None
            if os.path.exists(subtitle_path_id):
                chosen_subtitle_path = subtitle_path_id
            elif os.path.exists(subtitle_path_en):
                chosen_subtitle_path = subtitle_path_en

            if chosen_subtitle_path:
                with open(chosen_subtitle_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                transcript_lines = [line.strip() for line in lines if not '-->' in line and not line.strip().isdigit() and not 'WEBVTT' in line]
                transcript_text = " ".join(filter(None, transcript_lines))

        if not os.path.exists(original_filepath):
             return jsonify({"error": "Gagal mengunduh video dari YouTube."}), 500

        # --- 2. Proses dengan Google AI untuk Mendapatkan Momen ---
        clips_to_make = []
        if model and transcript_text != "Tidak ada transkrip yang ditemukan.":
            prompt = f"""
            Anda adalah seorang editor video viral profesional. Baca transkrip video ini.
            Identifikasi 4 momen paling menarik yang berdurasi antara 15 hingga 45 detik.
            Untuk setiap momen, berikan:
            1. "start_time": Waktu mulai momen dalam detik (integer).
            2. "end_time": Waktu selesai momen dalam detik (integer).
            3. "title": Judul yang sangat menarik untuk klip tersebut (string, maksimal 6 kata).

            Transkrip Video: "{transcript_text[:3000]}"

            Berikan jawaban Anda HANYA dalam format string JSON yang valid berupa daftar objek.
            Contoh:
            [
              {{"start_time": 50, "end_time": 75, "title": "Rahasia Konsistensi Terungkap"}},
              {{"start_time": 180, "end_time": 210, "title": "Kesalahan Fatal Saat Memulai"}}
            ]
            """
            try:
                response = model.generate_content(prompt)
                cleaned_response = response.text.strip().replace('```json', '').replace('```', '')
                clips_to_make = json.loads(cleaned_response)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Gagal mem-parsing respons AI: {e}. Menggunakan metode fallback.")
                clips_to_make = []
        
        if not clips_to_make:
            clips_to_make = [
                {"start_time": 10, "end_time": 30, "title": "Momen Menarik 1 (Otomatis)"},
                {"start_time": 40, "end_time": 60, "title": "Momen Menarik 2 (Otomatis)"},
            ]
        
        # --- 3. Pembuatan Klip Video Secara Nyata ---
        generated_clips = []
        with VideoFileClip(original_filepath) as video:
            for i, clip_data in enumerate(clips_to_make):
                start = clip_data['start_time']
                end = clip_data['end_time']
                title = clip_data['title']

                if start >= video.duration or end > video.duration:
                    continue

                clip_filename = f"{video_id}_clip_{i+1}.mp4"
                clip_path = os.path.join(TEMP_DIR, clip_filename)
                
                new_clip = video.subclip(start, end)
                new_clip.write_videofile(clip_path, codec="libx264", audio_codec="aac", logger=None)
                
                generated_clips.append({
                    "title": title,
                    "filename": clip_filename,
                    "viralScore": random.randint(70, 98)
                })

        return jsonify({
            "original_title": video_title,
            "clips": generated_clips
        })

    except Exception as e:
        return jsonify({"error": f"Terjadi kesalahan: {str(e)}"}), 500

@app.route('/clips/<filename>')
def get_clip(filename):
    return send_from_directory(TEMP_DIR, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
