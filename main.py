import os
import re
import feedparser
from bs4 import BeautifulSoup
from gtts import gTTS
from moviepy.editor import TextClip, ColorClip, CompositeVideoClip, AudioFileClip

def clean_news_text(raw_text):
    """
    यह फ़ंक्शन न्यूज़ डेटा से HTML टैग्स, URLs, और फालतू कोड/अक्षरों को पूरी तरह साफ़ करता है।
    """
    if not raw_text:
        return ""
    
    # 1. HTML टैग्स हटाएँ
    soup = BeautifulSoup(raw_text, "html.parser")
    text = soup.get_text()
    
    # 2. URLs और वेब एड्रेस हटाएँ
    text = re.sub(r'http[s]?://\S+|www\.\S+', '', text)
    
    # 3. HTML entities जैसे &nbsp; हटाएँ
    text = re.sub(r'&[a-zA-Z0-9#]+;', ' ', text)
    
    # 4. 4 या उससे लंबे अंग्रेज़ी/अंकों के कोड हटाएँ (जो RSS फालतू भेजता है)
    text = re.sub(r'\b[a-zA-Z0-9_\-=]{4,}\b', '', text)
    
    # 5. फालतू स्पेस और न्यू-लाइन्स साफ़ करें
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def generate_video():
    # 1. RSS Feed से ताज़ा खबर उठाना
    rss_url = "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi" # आपकी हिंदी न्यूज़ RSS URL
    feed = feedparser.parse(rss_url)
    
    if not feed.entries:
        print("कोई न्यूज़ नहीं मिली!")
        return

    first_entry = feed.entries[0]
    raw_title = first_entry.get('title', '')
    raw_desc = first_entry.get('summary', '')

    # 2. न्यूज़ टेक्स्ट की गहरी सफाई (Clean Up)
    clean_title = clean_news_text(raw_title)
    clean_desc = clean_news_text(raw_desc)

    # वॉइस के लिए केवल साफ हिंदी टेक्स्ट ही इस्तेमाल होगा
    script_text = f"{clean_title}। {clean_desc}"
    print(f"साफ किया गया वॉइस टेक्स्ट: {script_text}")

    # 3. TTS (Text-to-Speech) - वॉइस जनरेट करना
    tts = gTTS(text=script_text, lang='hi', slow=False)
    audio_path = "news_audio.mp3"
    tts.save(audio_path)

    # 4. ऑडियो क्लिप की लंबाई निकालना
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    # 5. वीडियो क्लिप बनाना (15 FPS ऑप्टिमाइज्ड)
    bg_clip = ColorClip(size=(1080, 1920), color=(15, 15, 25), duration=duration)

    # ऑन-स्क्रीन टेक्स्ट क्लिप
    display_text = f"{clean_title}\n\n{clean_desc}"
    txt_clip = TextClip(
        display_text, 
        fontsize=45, 
        color='white', 
        size=(950, 1600), 
        method='caption', 
        font='DejaVu-Sans-Bold'
    ).set_position('center').set_duration(duration)

    # ऑडियो और टेक्स्ट को मिलाना
    video = CompositeVideoClip([bg_clip, txt_clip]).set_audio(audio_clip)

    # 6. वीडियो रेंडर करना (15 FPS)
    output_video = "final_news.mp4"
    video.write_videofile(
        output_video, 
        fps=15, 
        codec='libx264', 
        audio_codec='aac',
        preset='ultrafast'
    )
    print("वीडियो सफलतापूर्वक तैयार हो गया!")

if __name__ == "__main__":
    generate_video()
    
