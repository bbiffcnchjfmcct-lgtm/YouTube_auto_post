import PIL.Image
# 🛠️ Pillow और MoviePy के बीच के एरर को ठीक करने के लिए यह पैच
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

import os
import re
import asyncio
import textwrap
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import random
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import edge_tts
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
def download_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
    font_path = "NotoSansDevanagari.ttf"
    if not os.path.exists(font_path):
        print("Downloading Hindi Font...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(font_url, headers=headers, timeout=30)
            with open(font_path, 'wb') as f:
                f.write(response.content)
            print("Font downloaded successfully!")
        except Exception as e:
            print(f"Font download failed: {e}")
    return font_path

FONT_PATH = download_font()

# Gemini Setup (अब gemini-1.5-flash इस्तेमाल कर रहे हैं)
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

# --- 2. FETCH TRENDING NEWS (NEWS API YA RSS) ---
def get_latest_news():
    API_KEY = os.environ.get("NEWS_API_KEY")
    
    if API_KEY:
        print("Using News API...")
        try:
            url = f"https://newsapi.org/v2/top-headlines?country=in&language=hi&apiKey={API_KEY}"
            response = requests.get(url, timeout=15)
            data = response.json()
            if data.get('status') == 'ok' and data.get('articles'):
                article = random.choice(data['articles'])
                title = clean_html(article.get('title', ''))
                description = clean_html(article.get('description', ''))
                link = article.get('url', '')
                image_url = article.get('urlToImage', '')
                if title:
                    return title, description, link, image_url
        except Exception as e:
            print(f"News API Error: {e}. Falling back to RSS.")

    # Fallback: Google News RSS (अगर API काम न करे तो)
    print("Using Google News RSS (Fallback)...")
    rss_url = "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"
    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        xml_data = response.read()
    root = ET.fromstring(xml_data)
    
    items = root.findall('./channel/item')
    if not items:
        return None, None, None, None
    
    item = random.choice(items[:5])
    title = clean_html(item.find('title').text if item.find('title') is not None else "")
    description = clean_html(item.find('description').text if item.find('description') is not None else "")
    link = item.find('link').text if item.find('link') is not None else ""
    image_url = ""
    
    return title, description, link, image_url

def fetch_news_image(link, title, size, video_type, provided_image_url=None):
    w, h = size
    
    if provided_image_url:
        try:
            img_data = requests.get(provided_image_url, timeout=10).content
            img_path = f"news_api_image_{w}x{h}.jpg"
            with open(img_path, 'wb') as handler:
                handler.write(img_data)
            print("Image from News API downloaded successfully!")
            return img_path
        except Exception as e:
            print(f"News API image download failed: {e}")

    print(f"Generating AI image for {video_type} video...")
    if video_type == "short":
        prompt = f"Vertical breaking news background about: {title}, highly dramatic, intense lighting, social media viral style, 8k, photorealistic"
    else:
        prompt = f"Widescreen cinematic news studio background about: {title}, professional broadcast, anchor desk, highly detailed, 8k, photorealistic"
        
    encoded_prompt = urllib.parse.quote(prompt)
    random_seed = random.randint(1, 1000000)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={w}&height={h}&seed={random_seed}&nologo=true"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            bg_path = f"bg_ai_{w}x{h}_{random_seed}.jpg"
            with open(bg_path, 'wb') as f:
                f.write(response.content)
            return bg_path
    except Exception as e:
        print(f"AI Image generation failed: {e}")
        
    return None

# --- 3. GEMINI SCRIPT GENERATION ---
def generate_script_with_gemini(news_title, news_desc):
    prompt = f"""
    आप एक वायरल YouTube न्यूज़ एंकर हैं। इस न्यूज़ के आधार पर हिंदी में स्क्रिप्ट लिखें।
    न्यूज़ टाइटल: {news_title}
    न्यूज़ डिस्क्रिप्शन: {news_desc}
    
    आउटपुट फॉर्मेट बिल्कुल ऐसा होना चाहिए:
    TITLE: [यहाँ एक बहुत ही चौंकाने वाला और क्लिक करने लायक हिंदी टाइटल लिखें]
    
    SHORT_SCRIPT: [यहाँ 50-60 शब्दों की शॉर्ट स्क्रिप्ट लिखें। सबसे पहले एक ज़बरदस्त हुक (Hook) लगाएं जिससे लोग रुक जाएं, जैसे 'रुकिए! यह खबर आपको चौंका देगी!', 'क्या आप जानते हैं?'. फिर तेज़ अंदाज़ में न्यूज़ बताएं।]
    
    LONG_SCRIPT: [यहाँ 300-400 शब्दों की एक विस्तृत लॉन्ग स्क्रिप्ट लिखें। इसमें खबर की पूरी डिटेल, बैकग्राउंड, और लोगों की प्रतिक्रियाएं शामिल करें, ताकि वीडियो 3-4 मिनट लंबा बन सके।]
    """
    try:
        response = model.generate_content(prompt)
        text = response.text
        
        title_match = re.search(r'TITLE:\s*(.*)', text)
        short_match = re.search(r'SHORT_SCRIPT:\s*(.*?)(?=LONG_SCRIPT:|$)', text, re.DOTALL)
        long_match = re.search(r'LONG_SCRIPT:\s*(.*)', text, re.DOTALL)
        
        title = title_match.group(1).strip() if title_match else news_title
        short_script = short_match.group(1).strip() if short_match else news_desc
        long_script = long_match.group(1).strip() if long_match else news_desc
        
        return title, short_script, long_script
    except Exception as e:
        print(f"Gemini Error: {e}. Using fallback.")
        return news_title, news_desc, news_desc

# --- 4. TTS AUDIO GENERATION (FEMALE VOICE) ---
async def make_audio(text, output_file):
    communicate = edge_tts.Communicate(text, "hi-IN-SwaraNeural", rate="+20%", volume="+20%")
    await communicate.save(output_file)

def generate_audio(text, output_file):
    try:
        asyncio.run(make_audio(text, output_file))
        print("Audio generated successfully!")
    except Exception as e:
        print(f"Audio generation error: {e}")
        raise e

# --- 5. IMAGE & THUMBNAIL GENERATION ---
def create_overlay(title, desc, size=(1080, 1920), video_type="short"):
    w, h = size
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font_size = 55 if video_type == "short" else 45
        header_size = 70 if video_type == "short" else 60
        font = ImageFont.truetype(FONT_PATH, font_size)
        header_font = ImageFont.truetype(FONT_PATH, header_size)
    except Exception as e:
        print(f"Font error: {e}. Using default.")
        font = ImageFont.load_default()
        header_font = font

    if video_type == "short":
        wrap_w = 22
        wrapped_title = "\n".join(textwrap.wrap(title, width=wrap_w))
        wrapped_desc = "\n".join(textwrap.wrap(desc, width=wrap_w + 5))
        
        box_h = int(h * 0.45)
        box_top = h - box_h - 100
        
        draw.rectangle([60, box_top - 60, 500, box_top + 20], fill=(220, 38, 38))
        draw.text((80, box_top - 50), "BREAKING NEWS", font=header_font, fill=(255, 255, 255))
        draw.rectangle([40, box_top, w - 40, h - 80], fill=(0, 0, 0, 240), outline=(255, 0, 0), width=8)
        
        draw.text((70, box_top + 40), wrapped_title, font=font, fill=(255, 215, 0))
        title_height = len(wrapped_title.split('\n')) * 65
        draw.text((70, box_top + 50 + title_height), wrapped_desc, font=font, fill=(255, 255, 255))
        
    else:
        wrapped_title = "\n".join(textwrap.wrap(title, width=50))
        wrapped_desc = "\n".join(textwrap.wrap(desc, width=60))
        
        box_h = int(h * 0.25)
        box_top = h - box_h - 50
        
        draw.rectangle([0, box_top, w, box_top + 60], fill=(200, 0, 0))
        draw.text((20, box_top + 5), "BREAKING NEWS", font=header_font, fill=(255, 255, 255))
        draw.rectangle([0, box_top + 60, w, h], fill=(0, 0, 0, 230))
        
        draw.text((20, box_top + 70), wrapped_title, font=font, fill=(255, 215, 0))
        title_height = len(wrapped_title.split('\n')) * 50
        draw.text((20, box_top + 80 + title_height), wrapped_desc, font=font, fill=(255, 255, 255))

    overlay_path = f"overlay_{video_type}_{w}x{h}.png"
    img.save(overlay_path)
    return overlay_path

def create_thumbnail(title, output_path="thumbnail.jpg"):
    w, h = 1280, 720
    img = Image.new('RGB', (w, h), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, 70)
        header_font = ImageFont.truetype(FONT_PATH, 90)
        small_font = ImageFont.truetype(FONT_PATH, 40)
    except:
        font = ImageFont.load_default()
        header_font = font
        small_font = font

    draw.rectangle([0, 0, 350, h], fill=(220, 38, 38))
    draw.text((50, 100), "FAST", font=header_font, fill=(255, 255, 255))
    draw.text((50, 200), "NEWS", font=header_font, fill=(255, 215, 0))
    
    wrapped_title = "\n".join(textwrap.wrap(title, width=22))
    draw.text((400, 150), wrapped_title, font=font, fill=(255, 255, 255))
    
    draw.rectangle([350, h-100, w, h], fill=(255, 215, 0))
    draw.text((400, h-80), "SUBSCRIBE FOR MORE NEWS", font=small_font, fill=(0, 0, 0))
    
    img.save(output_path)
    return output_path

# --- 6. VIDEO BUILDER ---
def build_video(title, desc, audio_path, output_video, news_link, provided_image_url, aspect_ratio="9:16", video_type="short"):
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    size = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)

    bg_path = fetch_news_image(news_link, title, size, video_type, provided_image_url)
    
    if not bg_path:
        print("Using fallback solid background.")
        bg_img = Image.new('RGB', size, color=(10, 15, 30))
        bg_path = f"bg_fallback_{size[0]}x{size[1]}.png"
        bg_img.save(bg_path)

    bg_img = Image.open(bg_path).convert('RGBA').resize(size)
    overlay = Image.new('RGBA', size, (0, 0, 0, 160))
    bg_img = Image.alpha_composite(bg_img, overlay).convert('RGB')
    
    bg_path_final = f"bg_final_{size[0]}x{size[1]}.png"
    bg_img.save(bg_path_final)

    overlay_path = create_overlay(title, desc, size=size, video_type=video_type)

    # Ken Burns Effect
    bg_clip = ImageClip(bg_path_final).set_duration(duration)
    bg_clip = bg_clip.resize(lambda t: 1 + 0.04 * t)
    bg_clip = bg_clip.set_position("center")

    txt_clip = ImageClip(overlay_path).set_duration(duration)

    video = CompositeVideoClip([bg_clip, txt_clip]).set_audio(audio)
    video.write_videofile(
        output_video, fps=24, codec='libx264', audio_codec='aac',
        temp_audiofile='temp-audio.m4a', remove_temp=True
    )
    audio.close()
    video.close()

    for p in [bg_path, bg_path_final, overlay_path]:
        if os.path.exists(p):
            os.remove(p)

# --- 7. YOUTUBE UPLOADER ---
def upload_to_youtube(video_path, thumbnail_path, title, description, tags):
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("YouTube API Credentials missing!")
        return

    creds = Credentials(
        token=None, refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id, client_secret=client_secret
    )

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {"title": title[:100], "description": description, "tags": tags, "categoryId": "25"},
        "status": {"privacyStatus": "public"}
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploading... {int(status.progress() * 100)}%")

    video_id = response.get('id')
    print(f"Video Uploaded! ID: {video_id}")

    try:
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_path)).execute()
        print("Thumbnail Uploaded!")
    except Exception as e:
        print(f"Thumbnail failed: {e}")

    try:
        comment_text = f"📢 {title}\n\nइस खबर के बारे में आपका क्या कहना है? कमेंट में बताएं! 👇\n#news #breakingnews"
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": comment_text}}
                }
            }
        ).execute()
        print("Pinned Comment Posted Successfully!")
    except Exception as e:
        print(f"Comment posting failed: {e}")

# --- MAIN EXECUTION ---
def main():
    print("Fetching trending news...")
    news_title, news_desc, news_link, news_image_url = get_latest_news()
    if not news_title:
        print("No news found.")
        return

    print(f"News Title: {news_title}")
    print("Generating Script with Gemini...")
    title, short_script, long_script = generate_script_with_gemini(news_title, news_desc)

    print("Generating Thumbnail...")
    thumbnail_path = create_thumbnail(title)

    # --- SHORTS VIDEO ---
    print("Building Shorts Video...")
    short_audio = "short_audio.mp3"
    generate_audio(short_script, short_audio)
    short_video = "shorts_video.mp4"
    build_video(title, short_script, short_audio, short_video, news_link, news_image_url, aspect_ratio="9:16", video_type="short")
    
    print("Uploading Shorts to YouTube...")
    upload_to_youtube(
        short_video, thumbnail_path,
        title=f"[Shorts] {title}",
        description=f"{short_script}\n\n#shorts #news #hindinews",
        tags=["shorts", "news", "hindinews"]
    )

    # --- LONG VIDEO ---
    print("Building Long Video...")
    long_audio = "long_audio.mp3"
    generate_audio(long_script, long_audio)
    long_video = "long_video.mp4"
    build_video(title, long_script, long_audio, long_video, news_link, news_image_url, aspect_ratio="16:9", video_type="long")
    
    print("Uploading Long Video to YouTube...")
    upload_to_youtube(
        long_video, thumbnail_path,
        title=title,
        description=f"{long_script}\n\n#news #hindinews #breakingnews",
        tags=["news", "hindinews", "breakingnews", "india"]
    )

if __name__ == "__main__":
    main()
