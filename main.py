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
import edge_tts
import google.generativeai as genai

# --- CONFIGURATION ---
# फॉन्ट का पाथ (GitHub Actions में ऑटोमैटिक इंस्टॉल हो जाएगा)
FONT_PATH = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"

# Gemini Setup
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 1. CLEAN HTML ---
def clean_html(text):
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'http[s]?://\S+', '', clean)
    clean = re.sub(r'&[a-zA-Z0-9#]+;', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

# --- 2. FETCH NEWS ---
def get_latest_news():
    rss_url = "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"
    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        xml_data = response.read()
    root = ET.fromstring(xml_data)
    item = root.find('./channel/item')
    if item is None:
        return None, None
    title = clean_html(item.find('title').text if item.find('title') is not None else "")
    description = clean_html(item.find('description').text if item.find('description') is not None else "")
    return title, description

# --- 3. GEMINI SCRIPT GENERATION ---
def generate_script_with_gemini(news_title, news_desc):
    prompt = f"""
    आप एक YouTube न्यूज़ एंकर हैं। इस न्यूज़ के आधार पर हिंदी में एक शॉर्ट स्क्रिप्ट (50 शब्द) और एक लॉन्ग स्क्रिप्ट (150 शब्द) लिखें।
    न्यूज़ टाइटल: {news_title}
    न्यूज़ डिस्क्रिप्शन: {news_desc}
    
    आउटपुट फॉर्मेट बिल्कुल ऐसा होना चाहिए:
    TITLE: [यहाँ एक आकर्षक हिंदी टाइटल लिखें]
    SHORT_SCRIPT: [यहाँ शॉर्ट स्क्रिप्ट लिखें]
    LONG_SCRIPT: [यहाँ लॉन्ग स्क्रिप्ट लिखें]
    """
    response = model.generate_content(prompt)
    text = response.text
    
    title_match = re.search(r'TITLE:\s*(.*)', text)
    short_match = re.search(r'SHORT_SCRIPT:\s*(.*?)(?=LONG_SCRIPT:|$)', text, re.DOTALL)
    long_match = re.search(r'LONG_SCRIPT:\s*(.*)', text, re.DOTALL)
    
    title = title_match.group(1).strip() if title_match else news_title
    short_script = short_match.group(1).strip() if short_match else news_desc
    long_script = long_match.group(1).strip() if long_match else news_desc
    
    return title, short_script, long_script

# --- 4. TTS AUDIO GENERATION ---
async def make_audio(text, output_file):
    communicate = edge_tts.Communicate(text, "hi-IN-MadhurNeural")
    await communicate.save(output_file)

def generate_audio(text, output_file):
    try:
        asyncio.run(make_audio(text, output_file))
        print("Audio generated successfully!")
    except Exception as e:
        print(f"Audio generation error: {e}")
        raise e

# --- 5. IMAGE & THUMBNAIL GENERATION ---
def create_overlay(title, desc, size=(1080, 1920)):
    w, h = size
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, 45)
        header_font = ImageFont.truetype(FONT_PATH, 60)
    except Exception as e:
        print(f"Font error: {e}. Using default.")
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

def create_thumbnail(title, output_path="thumbnail.jpg"):
    w, h = 1280, 720
    img = Image.new('RGB', (w, h), color=(20, 30, 48))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, 60)
        header_font = ImageFont.truetype(FONT_PATH, 80)
    except:
        font = ImageFont.load_default()
        header_font = font

    # Background design
    draw.rectangle([0, h-200, w, h], fill=(220, 38, 38))
    draw.text((50, 50), "BREAKING NEWS", font=header_font, fill=(255, 255, 255))
    
    wrapped_title = "\n".join(textwrap.wrap(title, width=40))
    draw.text((50, 200), wrapped_title, font=font, fill=(255, 255, 255))
    
    img.save(output_path)
    return output_path

# --- 6. VIDEO BUILDER ---
def build_video(title, desc, audio_path, output_video, aspect_ratio="9:16"):
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    size = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)

    bg_img = Image.new('RGB', size, color=(15, 23, 42))
    bg_path = f"bg_{size[0]}x{size[1]}.png"
    bg_img.save(bg_path)

    overlay_path = create_overlay(title, desc, size=size)

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

# --- 7. YOUTUBE UPLOADER ---
def upload_to_youtube(video_path, thumbnail_path, title, description, tags):
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

    video_id = response.get('id')
    print(f"Video Uploaded Successfully! ID: {video_id}")

    # Thumbnail Upload
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path)
        ).execute()
        print("Thumbnail Uploaded Successfully!")
    except Exception as e:
        print(f"Thumbnail upload failed: {e}")

# --- MAIN EXECUTION ---
def main():
    print("Fetching news...")
    news_title, news_desc = get_latest_news()
    if not news_title:
        print("No news found to process.")
        return

    print(f"News Title: {news_title}")
    print("Generating Script with Gemini...")
    title, short_script, long_script = generate_script_with_gemini(news_title, news_desc)
    print(f"Generated Title: {title}")

    # Thumbnail Generate
    print("Generating Thumbnail...")
    thumbnail_path = create_thumbnail(title)

    # --- SHORTS VIDEO ---
    print("Building Shorts Video...")
    short_audio = "short_audio.mp3"
    generate_audio(short_script, short_audio)
    short_video = "shorts_video.mp4"
    build_video(title, short_script, short_audio, short_video, aspect_ratio="9:16")
    
    print("Uploading Shorts to YouTube...")
    upload_to_youtube(
        short_video,
        thumbnail_path,
        title=f"[Shorts] {title}",
        description=f"{short_script}\n\n#shorts #news #hindinews #breakingnews",
        tags=["shorts", "news", "hindinews", "breakingnews"]
    )

    # --- LONG VIDEO ---
    print("Building Long Video...")
    long_audio = "long_audio.mp3"
    generate_audio(long_script, long_audio)
    long_video = "long_video.mp4"
    build_video(title, long_script, long_audio, long_video, aspect_ratio="16:9")
    
    print("Uploading Long Video to YouTube...")
    upload_to_youtube(
        long_video,
        thumbnail_path,
        title=title,
        description=f"{long_script}\n\n#news #hindinews #breakingnews",
        tags=["news", "hindinews", "breakingnews", "india"]
    )

if __name__ == "__main__":
    main()
