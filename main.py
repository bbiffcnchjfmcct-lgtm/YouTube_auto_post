import os
import re
import asyncio
import feedparser
from bs4 import BeautifulSoup
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import TextClip, ColorClip, CompositeVideoClip, AudioFileClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# ==========================================
# 1. CLEAN TEXT (RSS FILTER)
# ==========================================
def clean_news_text(raw_text):
    if not raw_text:
        return ""
    soup = BeautifulSoup(raw_text, "html.parser")
    text = soup.get_text()
    text = re.sub(r'http[s]?://\S+|www\.\S+', '', text)
    text = re.sub(r'&[a-zA-Z0-9#]+;', ' ', text)
    text = re.sub(r'\b[a-zA-Z0-9_\-=]{4,}\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ==========================================
# 2. FAST NEWS ANCHOR VOICE (EDGE-TTS)
# ==========================================
async def generate_fast_voice(text, output_audio):
    # +25% Rate makes it sound like a fast-paced news reader
    voice = "hi-IN-SwaraNeural" # News anchor style voice
    communicate = edge_tts.Communicate(text, voice, rate="+25%")
    await communicate.save(output_audio)

# ==========================================
# 3. AUTO THUMBNAIL GENERATOR
# ==========================================
def create_thumbnail(title_text, output_img, size=(1280, 720)):
    w, h = size
    img = Image.new("RGB", (w, h), color=(180, 0, 0)) # Red News Theme
    draw = ImageDraw.Draw(img)
    
    # Border & Inner Banner
    draw.rectangle([20, 20, w - 20, h - 20], outline=(255, 255, 255), width=8)
    draw.rectangle([40, h // 2 - 100, w - 40, h // 2 + 100], fill=(0, 0, 0))
    
    # Banner Text
    draw.text((60, h // 2 - 40), f"BREAKING NEWS:\n{title_text[:40]}...", fill=(255, 255, 0))
    img.save(output_img)

# ==========================================
# 4. VIDEO MAKER (9:16 SHORTS & 16:9 LONG)
# ==========================================
def build_video(title, desc, audio_path, output_video, aspect_ratio="9:16"):
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    
    if aspect_ratio == "9:16":
        size = (1080, 1920)
        font_size = 50
        text_box_size = (950, 1500)
    else: # 16:9 Long Video
        size = (1920, 1080)
        font_size = 55
        text_box_size = (1700, 800)

    bg = ColorClip(size=size, color=(15, 15, 30), duration=duration)
    
    display_text = f"🚨 बड़ी खबर 🚨\n\n{title}\n\n{desc}"
    txt_clip = TextClip(
        display_text, 
        fontsize=font_size, 
        color='white', 
        size=text_box_size, 
        method='caption', 
        font='DejaVu-Sans-Bold'
    ).set_position('center').set_duration(duration)

    video = CompositeVideoClip([bg, txt_clip]).set_audio(audio)
    video.write_videofile(output_video, fps=15, codec='libx264', audio_codec='aac', preset='ultrafast')

# ==========================================
# 5. YOUTUBE UPLOADER WITH THUMBNAIL
# ==========================================
def upload_to_youtube(video_path, thumbnail_path, title, description, tags):
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

    if not (client_id and client_secret and refresh_token):
        print("Secrets missing, skipping upload.")
        return

    creds = Credentials(
        None,
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
            "categoryId": "25" # News & Politics
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

    video_id = response.get("id")
    print(f"Uploaded Successfully! Video ID: {video_id}")

    # Set Thumbnail
    if os.path.exists(thumbnail_path):
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path)
        ).execute()
        print("Thumbnail set successfully!")

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    rss_url = "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        print("No news found.")
        return

    entry = feed.entries[0]
    title = clean_news_text(entry.get('title', ''))
    desc = clean_news_text(entry.get('summary', ''))

    full_voice_text = f"ताज़ा खबर! {title}। {desc}"
    
    # 1. Fast Audio Generate
    audio_file = "news_fast.mp3"
    asyncio.run(generate_fast_voice(full_voice_text, audio_file))

    # 2. Generate Thumbnails
    thumb_shorts = "thumb_shorts.jpg"
    thumb_long = "thumb_long.jpg"
    create_thumbnail(title, thumb_shorts, size=(1080, 1920))
    create_thumbnail(title, thumb_long, size=(1280, 720))

    # 3. Create Shorts Video (9:16)
    shorts_video = "shorts_news.mp4"
    print("Generating Shorts Video (9:16)...")
    build_video(title, desc, audio_file, shorts_video, aspect_ratio="9:16")

    # 4. Create Long Video (16:9)
    long_video = "long_news.mp4"
    print("Generating Long Video (16:9)...")
    build_video(title, desc, audio_file, long_video, aspect_ratio="16:9")

    # 5. Upload Shorts
    print("Uploading Shorts to YouTube...")
    upload_to_youtube(
        shorts_video, thumb_shorts, 
        title=f"{title[:80]} #Shorts #News", 
        description=f"{desc}\n\n#news #breakingnews #shorts", 
        tags=["shorts", "news", "hindi news"]
    )

    # 6. Upload Long Video
    print("Uploading Long Video to YouTube...")
    upload_to_youtube(
        long_video, thumb_long, 
        title=f"[ताजा समाचार] {title[:80]}", 
        description=f"{desc}\n\nताज़ा तरीन ख़बरों के लिए सब्सक्राइब करें।", 
        tags=["news", "hindi news", "breaking news"]
    )

if __name__ == "__main__":
    main()
