# One-time setup:
# 1. Set GROQ_API_KEY and PEXELS_API_KEY in your environment (or GitHub Actions secrets).
# 2. Use Python 3.11: pip install -r requirements.txt && install ffmpeg (apt/brew).
# 3. Run locally: python main.py  (creates short.mp4 + title.txt).
# 4. Configure YouTube OAuth separately — see uploader.py setup comment.

import asyncio
import os
import random
import re
import sys
from pathlib import Path

import edge_tts
import requests

WORK_DIR = Path(__file__).resolve().parent
SHORT_PATH = WORK_DIR / "short.mp4"
TITLE_PATH = WORK_DIR / "title.txt"
VOICE_PATH = WORK_DIR / "voice.mp3"
CLIPS_DIR = WORK_DIR / "clips"

NICHES = [
    "psychology facts",
    "history facts",
    "money tips",
    "science facts",
    "life hacks",
]

FALLBACK_TOPICS = [
    "Why your brain deletes childhood memories",
    "The Roman emperor who made his horse a senator",
    "Compound interest explained in 60 seconds",
    "Octopuses have three hearts and blue blood",
    "The 2-minute rule that beats procrastination",
    "Cleopatra lived closer to the Moon landing than the pyramids",
    "Hidden fees banks never mention",
    "Bananas are berries but strawberries are not",
    "Why cold showers boost dopamine",
    "The Viking who discovered America before Columbus",
]

MALE_VOICES = [
    "en-US-GuyNeural",
    "en-US-JasonNeural",
    "en-GB-RyanNeural",
]

GROQ_MODELS = [
    "llama3-8b-8192",
    "llama-3.1-8b-instant",
]
PEXELS_CLIP_COUNT = 5
TARGET_W, TARGET_H = 1080, 1920
FPS = 30


def log(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


def pick_trending_topic() -> str:
    log("1", "Picking trending topic via pytrends...")
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360)
        niche = random.choice(NICHES)
        pytrends.build_payload([niche], timeframe="now 7-d", geo="US")
        related = pytrends.related_queries()
        queries = related.get(niche, {}).get("top")
        if queries is not None and not queries.empty:
            topic = str(queries.iloc[0]["query"]).strip()
            if topic:
                log("1", f"Trending topic from pytrends: {topic}")
                return topic
        rising = related.get(niche, {}).get("rising")
        if rising is not None and not rising.empty:
            topic = str(rising.iloc[0]["query"]).strip()
            if topic:
                log("1", f"Rising topic from pytrends: {topic}")
                return topic
        log("1", "pytrends returned no queries; using niche as topic.")
        return niche.title()
    except Exception as exc:
        log("1", f"pytrends failed ({exc}); using fallback topic list.")
        topic = random.choice(FALLBACK_TOPICS)
        log("1", f"Fallback topic: {topic}")
        return topic


def generate_script(topic: str) -> str:
    log("2", "Generating script with Groq API...")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set.")

    prompt = (
        f"Write a YouTube Shorts voiceover script about: {topic}\n\n"
        "Rules:\n"
        "- Exactly 55-65 words\n"
        "- Hook must be in the first 3 words\n"
        "- No 'hey guys' or similar intros\n"
        "- End with a shocking fact or punchline\n"
        "- Output ONLY the script text, no labels or quotes"
    )

    last_error = None
    for model in GROQ_MODELS:
        try:
            log("2", f"Trying Groq model: {model}")
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.9,
                    "max_tokens": 300,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            script = data["choices"][0]["message"]["content"].strip()
            script = re.sub(r'^["\']|["\']$', "", script)
            word_count = len(script.split())
            log("2", f"Script generated with {model} ({word_count} words).")
            if word_count < 40:
                log("2", "Warning: script shorter than expected; continuing anyway.")
            return script
        except Exception as exc:
            last_error = exc
            log("2", f"Groq model {model} failed ({exc}).")

    log("2", f"All Groq models failed ({last_error}); using fallback script.")
    return (
        f"Stop scrolling. {topic} will change how you see the world. "
        "Most people never learn this, but the evidence is everywhere once you notice. "
        "Scientists and historians keep finding new proof every year. "
        "Share this with someone who needs to hear it today. "
        "Here's the part that shocks everyone: the truth was hidden in plain sight all along."
    )


async def _synthesize_voice_async(script: str, output_path: Path, voice: str) -> None:
    communicate = edge_tts.Communicate(script, voice, rate="+15%")
    await communicate.save(str(output_path))


def text_to_speech(script: str) -> Path:
    log("3", "Converting script to speech with edge-tts...")
    voice = random.choice(MALE_VOICES)
    try:
        asyncio.run(_synthesize_voice_async(script, VOICE_PATH, voice))
        log("3", f"Voice saved to {VOICE_PATH} ({voice}, rate +15%).")
        return VOICE_PATH
    except Exception as exc:
        raise RuntimeError(f"edge-tts failed: {exc}") from exc


def topic_keywords(topic: str) -> str:
    words = re.sub(r"[^\w\s]", "", topic).split()
    return " ".join(words[:4]) if words else "facts"


def fetch_pexels_clips(topic: str) -> list[Path]:
    log("4", "Fetching portrait stock clips from Pexels...")
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY environment variable is not set.")

    CLIPS_DIR.mkdir(exist_ok=True)
    query = topic_keywords(topic)
    downloaded: list[Path] = []

    try:
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": api_key},
            params={
                "query": query,
                "orientation": "portrait",
                "per_page": PEXELS_CLIP_COUNT,
                "size": "medium",
            },
            timeout=60,
        )
        response.raise_for_status()
        videos = response.json().get("videos", [])
    except Exception as exc:
        log("4", f"Pexels search failed ({exc}); retrying with generic query 'nature'.")
        try:
            response = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": api_key},
                params={
                    "query": "nature",
                    "orientation": "portrait",
                    "per_page": PEXELS_CLIP_COUNT,
                },
                timeout=60,
            )
            response.raise_for_status()
            videos = response.json().get("videos", [])
        except Exception as retry_exc:
            raise RuntimeError(f"Pexels API failed: {retry_exc}") from retry_exc

    if not videos:
        raise RuntimeError("Pexels returned no portrait videos for this topic.")

    for index, video in enumerate(videos[:PEXELS_CLIP_COUNT]):
        files = video.get("video_files", [])
        portrait_files = [
            f
            for f in files
            if f.get("height", 0) >= f.get("width", 0)
        ]
        candidates = portrait_files or files
        if not candidates:
            continue
        best = max(candidates, key=lambda f: f.get("height", 0))
        url = best.get("link")
        if not url:
            continue
        dest = CLIPS_DIR / f"clip_{index}.mp4"
        try:
            clip_resp = requests.get(url, timeout=120)
            clip_resp.raise_for_status()
            dest.write_bytes(clip_resp.content)
            downloaded.append(dest)
            log("4", f"Downloaded clip {index + 1}/{PEXELS_CLIP_COUNT}: {dest.name}")
        except Exception as exc:
            log("4", f"Failed to download clip {index}: {exc}")

    if not downloaded:
        raise RuntimeError("Could not download any Pexels clips.")
    return downloaded


def _import_moviepy():
    try:
        from moviepy.editor import AudioFileClip, VideoFileClip, concatenate_videoclips

        return AudioFileClip, VideoFileClip, concatenate_videoclips, 1
    except ImportError:
        from moviepy import AudioFileClip, VideoFileClip, concatenate_videoclips

        return AudioFileClip, VideoFileClip, concatenate_videoclips, 2


def _clip_resize(clip, *, height=None, width=None, version: int):
    if version == 2:
        if height is not None:
            return clip.resized(height=height)
        return clip.resized(width=width)
    if height is not None:
        return clip.resize(height=height)
    return clip.resize(width=width)


def _clip_crop(clip, *, x1: int, width: int, version: int):
    if version == 2:
        return clip.cropped(x1=x1, width=width)
    return clip.crop(x1=x1, width=width)


def _clip_subclip(clip, start: float, end: float, version: int):
    if version == 2:
        return clip.subclipped(start, end)
    return clip.subclip(start, end)


def _clip_set_audio(video, audio, version: int):
    if version == 2:
        return video.with_audio(audio)
    return video.set_audio(audio)


def resize_to_portrait(clip, version: int, target_w: int = TARGET_W, target_h: int = TARGET_H):
    clip = _clip_resize(clip, height=target_h, version=version)
    if clip.w < target_w:
        clip = _clip_resize(clip, width=target_w, version=version)
    x_center = clip.w / 2
    x1 = int(x_center - target_w / 2)
    return _clip_crop(clip, x1=x1, width=target_w, version=version)


def assemble_video(clip_paths: list[Path], audio_path: Path, output_path: Path) -> None:
    log("5", "Assembling 9:16 vertical video with moviepy...")
    AudioFileClip, VideoFileClip, concatenate_videoclips, mp_version = _import_moviepy()
    log("5", f"Using moviepy v{mp_version}.x API.")

    audio = AudioFileClip(str(audio_path))
    target_duration = audio.duration
    log("5", f"Target duration: {target_duration:.2f}s")

    processed = []
    video = None
    try:
        for path in clip_paths:
            clip = VideoFileClip(str(path))
            clip = resize_to_portrait(clip, mp_version)
            if clip.duration > 8:
                clip = _clip_subclip(clip, 0, 8, mp_version)
            processed.append(clip)

        if not processed:
            raise RuntimeError("No valid clips to assemble.")

        segments = []
        total = 0.0
        idx = 0
        while total < target_duration and idx < 500:
            clip = processed[idx % len(processed)]
            remaining = target_duration - total
            use_duration = min(clip.duration, remaining)
            segment = _clip_subclip(clip, 0, use_duration, mp_version)
            segments.append(segment)
            total += segment.duration
            idx += 1

        concat_kwargs = {"method": "compose"} if mp_version == 1 else {}
        video = concatenate_videoclips(segments, **concat_kwargs)
        if video.duration > target_duration:
            video = _clip_subclip(video, 0, target_duration, mp_version)
        video = _clip_set_audio(video, audio, mp_version)

        log("5", f"Exporting {output_path} at {FPS}fps...")
        video.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            logger=None,
        )
        log("5", "Video export complete.")
    except Exception as exc:
        raise RuntimeError(f"Video assembly failed: {exc}") from exc
    finally:
        audio.close()
        if video is not None:
            try:
                video.close()
            except Exception:
                pass
        for clip in processed:
            try:
                clip.close()
            except Exception:
                pass


def save_title(topic: str) -> None:
    log("6", f"Saving topic to {TITLE_PATH}...")
    TITLE_PATH.write_text(topic.strip(), encoding="utf-8")
    log("6", "Title saved.")


def main() -> int:
    print("=== YouTube Shorts Creator — starting pipeline ===", flush=True)
    try:
        topic = pick_trending_topic()
        script = generate_script(topic)
        print(f"[script] {script}\n", flush=True)
        text_to_speech(script)
        clips = fetch_pexels_clips(topic)
        assemble_video(clips, VOICE_PATH, SHORT_PATH)
        save_title(topic)
        log("done", f"Created {SHORT_PATH} and {TITLE_PATH}. Run uploader.py next.")
        return 0
    except Exception as exc:
        log("error", str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
