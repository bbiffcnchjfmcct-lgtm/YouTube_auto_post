import os
import re
import asyncio
import textwrap
import urllib.request
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# 1. DOWNLOAD HINDI FONT AUTOMATICALLY (WORKING LINK)
FONT_PATH = "NotoSansDevanagari-Bold.ttf"

def ensure_hindi_font():
    if not os.path.exists(FONT_PATH):
        print("Downloading Devanagari Font...")
        url = "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansdevanagari/NotoSansDevanagari-Bold.ttf"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response, open(FONT_PATH, 'wb') as out_file:
                out_file.write(response.read())
            print("Font downloaded successfully!")
        except Exception as e:
            print(f"Font download failed: {e}")

ensure_hindi_font()

# 2. CLEAN HTML & GARBAGE TEXT FROM RSS FEED
def clean_html(text):
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = re.sub(r'http[s]?://\S+', '', clean)
    clean = re.sub(r'&[a-zA-Z0-9#]+;', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def get_latest_news():
    rss_url = "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"
    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    item = root.find('.//channel/item')

    if item is None:
        return None, None

    title = clean_html(item.find('title').text if item.find('title') is not None else "")
    description = clean_html(item.find('description').text if item.find('description') is not None else "")

    return title, description

# 3. TEXT-TO-SPEECH (EDGE-TTS AUTOMATIC INSTALL & RUN)
def generate_audio(text, output_file="news.mp3"):
    try:
        os.system(f'python -m pip install edge-tts')
        import edge_tts
        async def main_tts():
            communicate = edge_tts.Communicate(text, "hi-IN-MadhurNeural", rate="+20%")
            await communicate.save(output_file)
        asyncio.run(main_tts())
        print("Audio generated successfully!")
    except Exception as e:
        print(f"Audio generation error: {e}")
        raise e

# 4. CREATE OVERLAY TEXT IMAGE WITH HINDI FONT
def create_text_overlay(title, desc, size=(1080, 1920)):
    w, h = size
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_PATH, 42)
        header_font = ImageFont.truetype(FONT_PATH, 50)
    except Exception:
        font = ImageFont.load_default()
        header_font = font

    wrap_w = 24 if w == 1080 else 45
    wrapped_title = "\n".join(textwrap.wrap(title, width=wrap_w))
    wrapped_desc = "\n".join(textwrap.wrap(desc, width=wrap_w + 5))

    box_h = int(h * 0.40)
    box_top = h - box_h - 100

    draw.rectangle([60, box_top - 50, 450, box_top + 15], fill=(220, 38, 38))
    draw.text((80, box_top - 40), "BREAKING NEWS", font=header_font, fill=(255, 255, 255))

    draw.rectangle([40, box_top, w - 40, h - 80], fill=(0, 0, 0, 220), outline=(220, 38, 38), width=5)

    full_text = f"{wrapped_title}\n\n{wrapped_desc}"
    draw.text((70, box_top + 40), full_text, font=font, fill=(255, 255, 255))

    overlay_path = f"overlay_{w}x{h}.png"
    img.save(overlay_path)
    return overlay_path

# 5. CREATE VIDEO WITH BACKGROUND & OVERLAY
def build_video(title, desc, audio_path, output_video, aspect_ratio="9:16"):
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    size = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)

    bg_img = Image.new('RGB', size, color=(15, 23, 42))
    bg_path = f"bg_{size[0]}x{size[1]}.png"
    bg_img.save(bg_path)

    overlay_path = create_text_overlay(title, desc, size=size)

    bg_clip = ImageClip(bg_path).set_duration(duration)
    txt_clip = ImageClip(overlay_path).set_duration(duration)

    video = CompositeVideoClip([bg_clip, txt_clip]).set_audio(audio)
    video.write_videofile(
        output_video,
        fps=24,
        codec='libx264',
        audio_codec='aac',
        temp_audiofile='temp-audio.m4a',
        remove_temp=True
    )

    audio.close()
    video.close()

    for p in [bg_path, overlay_path]:
        if os.path.exists(p):
            os.remove(p)

# 6. YOUTUBE UPLOADER
def upload_to_youtube(video_path, title, description, tags):
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("YouTube API Credentials missing in Secrets!")
        return

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "25"
        },
        "status": {
            "privacyStatus": "public"
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploading... {int(status.progress() * 100)}%")

    print(f"Video Uploaded Successfully! ID: {response.get('id')}")

# MAIN EXECUTION
def main():
    print("Fetching news...")
    title, desc = get_latest_news()

    if not title:
        print("No news found to process.")
        return

    print(f"News Title: {title}")

    full_text = f"{title}। {desc}"
    audio_file = "news_audio.mp3"
    generate_audio(full_text, audio_file)

    shorts_video = "shorts_news.mp4"
    print("Building Shorts Video...")
    build_video(title, desc, audio_file, shorts_video, aspect_ratio="9:16")

    print("Uploading to YouTube...")
    upload_to_youtube(
        shorts_video,
        title=f"[Shorts] {title}",
        description=f"{desc}\n\n#news #breakingnews #shorts #hindi",
        tags=["shorts", "news", "hindinews"]
    )

if __name__ == "__main__":
    main()
    
