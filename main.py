import os
import re
import asyncio
import feedparser
from bs4 import BeautifulSoup
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import TextClip, AudioFileClip, CompositeVideoClip, ColorClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# 1. CLEAN TEXT (RSS FILTER)
def clean_news_text(raw_text):
    if not raw_text:
        return ""
    soup = BeautifulSoup(raw_text, "html.parser")
    text = soup.get_text()
    text = re.sub(r'http[s]?://\S+', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    return text.strip()

# 2. FAST NEWS ANCHOR VOICE (EDGE-TTS)
async def generate_fast_voice(text, output_audio):
    # +25% rate makes it sound like a fast-paced news anchor
    voice = "hi-IN-MadhurNeural"
    communicate = edge_tts.Communicate(text, voice, rate="+25%")
    await communicate.save(output_audio)

# 3. AUTO THUMBNAIL GENERATOR
def create_thumbnail(title_text, output_img, size=(1280, 720)):
    w, h = size
    img = Image.new('RGB', (w, h), color=(18, 18, 18))
    draw = ImageDraw.Draw(img)
    
    # Border & Banner Format
    draw.rectangle([20, 20, w - 20, h - 20], outline=(255, 255, 255), width=8)
    draw.rectangle([40, 40, w - 40, 160], fill=(220, 20, 60))
    
    # Header text
    draw.text((60, 60), "BREAKING NEWS", fill=(255, 255, 255))
    img.save(output_img)

# 4. VIDEO MAKER (FOR SHORTS & LONG)
def build_video(title, desc, audio_path, output_video, aspect_ratio="9:16"):
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    if aspect_ratio == "9:16":
        size = (1080, 1920)
        font_size = 50
        text_box_size = (900, 1200)
    else: # 16:9 Long Video
        size = (1920, 1080)
        font_size = 60
        text_box_size = (1700, 800)

    bg = ColorClip(size=size, color=(15, 15, 30)).set_duration(duration)

    display_text = f"🔴 {title}\n\n{desc}"
    txt_clip = TextClip(
        display_text,
        fontsize=font_size,
        color='white',
        size=text_box_size,
        method='caption',
        font="DejaVu-Sans-Bold"
    ).set_position('center').set_duration(duration)

    video = CompositeVideoClip([bg, txt_clip]).set_audio(audio)
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

# 5. UPLOAD TO YOUTUBE WITH THUMBNAIL
def upload_to_youtube(video_path, thumbnail_path, title, description, tags):
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

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

    video_id = response.get("id")
    print(f"Uploaded Successfully! Video ID: {video_id}")

    # Set Thumbnail
    if os.path.exists(thumbnail_path):
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path)
        ).execute()
        print("Thumbnail set successfully!")

# MAIN EXECUTION
def main():
    rss_url = "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        print("No news found.")
        return

    entry = feed.entries[0]
    title = clean_news_text(entry.get("title", ""))
    desc = clean_news_text(entry.get("summary", ""))

    full_anchor_text = f"{title}। {desc}"

    # 1. Fast Audio Generation
    audio_file = "news_fast.mp3"
    asyncio.run(generate_fast_voice(full_anchor_text, audio_file))

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
        title=f"[Shorts] {title}",
        description=f"{desc}\n\n#news #breakingnews #shorts",
        tags=["shorts", "news", "hindi news"]
    )

    # 6. Upload Long Video
    print("Uploading Long Video to YouTube...")
    upload_to_youtube(
        long_video, thumb_long,
        title=f"ताज़ा खबर: {title}",
        description=f"{desc}\n\nताज़ा ख़बरों और अपडेट के लिए सब्सक्राइब करें।",
        tags=["news", "hindi news", "breaking news"]
    )

if __name__ == "__main__":
    main()
    
