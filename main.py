import os
import urllib.request
import feedparser
from gtts import gTTS
from moviepy import TextClip, CompositeVideoClip, AudioFileClip, ColorClip
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. Google News RSS Feed से खबर पाना
def fetch_top_news():
    rss_url = "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"
    feed = feedparser.parse(rss_url)
    if feed.entries:
        entry = feed.entries[0]
        title = entry.title
        summary = getattr(entry, 'summary', title)
        return title, summary
    return "आज की मुख्य खबर", "खबर उपलब्ध नहीं है"

# 2. Text-to-Speech (आवाज बनाना)
def generate_audio(text, filename="news_audio.mp3"):
    tts = gTTS(text=text, lang='hi')
    tts.save(filename)
    return filename

# 3. वीडियो बनाना
def create_video(news_text, audio_file, output_file="final_news.mp4"):
    audio = AudioFileClip(audio_file)
    duration = audio.duration

    # बैकग्राउंड (ब्लैक स्क्रीन)
    bg_clip = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=duration)

    # न्यूज़ टेक्स्ट
    txt_clip = TextClip(text=news_text, font_size=50, color='white', size=(900, None), method='caption')
    txt_clip = txt_clip.with_position('center').with_duration(duration)

    # वीडियो और ऑडियो को मिलाना
    video = CompositeVideoClip([bg_clip, txt_clip])
    video = video.with_audio(audio)
    video.write_videofile(output_file, fps=24, codec='libx264', audio_codec='aac')
    return output_file

# 4. YouTube पर अपलोड करना
def upload_to_youtube(video_path, title):
    client_id = os.environ.get('CLIENT_ID')
    client_secret = os.environ.get('CLIENT_SECRET')
    refresh_token = os.environ.get('REFRESH_TOKEN')

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret
    )

    youtube = build('youtube', 'v3', credentials=creds)

    request_body = {
        'snippet': {
            'title': title[:100],
            'description': f"{title}\n\n#news #hindi #news #trending #breakingnews",
            'tags': ['news', 'hindi news', 'breaking news'],
            'categoryId': '25'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part='snippet,status',
        body=request_body,
        media_body=media
    )

    response = request.execute()
    print(f"Video uploaded successfully! Video ID: {response.get('id')}")

if __name__ == '__main__':
    title, summary = fetch_top_news()
    full_text = f"{title}\n\n{summary}"
    print(f"Fetched News: {title}")

    audio_file = generate_audio(full_text)
    video_file = create_video(full_text, audio_file)
    upload_to_youtube(video_file, title)
    
