"""Create repeatable demo accounts, videos and a small sample playlist."""

import os
import shutil
import subprocess
import tempfile
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Comment, Like, Playlist, PlaylistVideo, Subscription, User, Video
from app.services.storage import ensure_bucket, upload_file


DEMO_USERS = [
    ("demo", "demo@streamhub.local", "DemoPass123!", "user"),
    ("moderator", "moderator@streamhub.local", "ModerPass123!", "moderator"),
    ("admin", "admin@streamhub.local", "AdminPass123!", "admin"),
]

# The first item uses the bundled authored clip. The remaining clips are
# short, locally generated visual demos, so the project works without remote media.
DEMO_VIDEOS = [
    {
        "title": "Космос ближе, чем кажется",
        "description": "Научпоп · Космос и астрономия. Демонстрационный авторский ролик StreamHub о нашей голубой планете.",
        "theme": "space", "accent": "#55a7ff", "tag": "КОСМОС", "views": 12840,
    },
    {
        "title": "Как работает видеохостинг",
        "description": "Технологии · Образование. Разбираемся, как видео проходит путь от загрузки до просмотра.",
        "theme": "network", "accent": "#9b8cff", "tag": "ТЕХНОЛОГИИ", "views": 9840,
    },
    {
        "title": "Тестовое видео: природа",
        "description": "Природа · Путешествия. Короткая демонстрация видеоплеера и качества изображения.",
        "theme": "forest", "accent": "#6cd6a0", "tag": "ПРИРОДА", "views": 7120,
    },
    {
        "title": "Как нейросеть учится распознавать изображения",
        "description": "Научпоп · Технологии · Искусственный интеллект. Простая визуализация обучения нейронной сети на примерах.",
        "theme": "neural", "accent": "#6bd8e8", "tag": "ИСКУССТВЕННЫЙ ИНТЕЛЛЕКТ", "views": 6240,
    },
    {
        "title": "Почему океан светится ночью?",
        "description": "Научпоп · Природа. Биолюминесценция, планктон и удивительные явления ночного океана.",
        "theme": "ocean", "accent": "#4bd4ee", "tag": "ПРИРОДА", "views": 5830,
    },
    {
        "title": "Как появляется северное сияние",
        "description": "Научпоп · История науки · Природа. Солнечный ветер, магнитное поле Земли и полярные огни.",
        "theme": "aurora", "accent": "#7be6b0", "tag": "НАУЧПОП", "views": 4890,
    },
    {
        "title": "Что скрывают вулканы: путь магмы",
        "description": "Образование · Природа. Демонстрационная схема вулкана, магматических камер и движения плит.",
        "theme": "volcano", "accent": "#ff986b", "tag": "ГЕОЛОГИЯ", "views": 3910,
    },
    {
        "title": "Путешествие к краю Солнечной системы",
        "description": "Космос · Путешествия · Научпоп. Планеты, ледяные миры и дальние рубежи нашей системы.",
        "theme": "planets", "accent": "#d0a5ff", "tag": "КОСМОС", "views": 3280,
    },
    {
        "title": "Изобретения, изменившие повседневную жизнь",
        "description": "История · Образование · Технологии. Несколько идей и открытий, повлиявших на привычный мир.",
        "theme": "inventions", "accent": "#ffc76e", "tag": "ИСТОРИЯ", "views": 2750,
    },
]

_PALETTES = {
    "space": ((7, 15, 43), (20, 65, 116)),
    "network": ((16, 15, 48), (66, 43, 104)),
    "forest": ((8, 35, 37), (20, 96, 67)),
    "neural": ((8, 28, 48), (25, 69, 100)),
    "ocean": ((3, 24, 52), (0, 93, 133)),
    "aurora": ((8, 22, 43), (30, 62, 79)),
    "volcano": ((35, 13, 18), (112, 39, 25)),
    "planets": ((15, 14, 45), (65, 38, 94)),
    "inventions": ((38, 26, 12), (111, 65, 25)),
}


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _gradient(size, top, bottom):
    width, height = size
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(round(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        for x in range(width):
            pixels[x, y] = color
    return image


def create_cover(path: str, title: str, tag: str, accent: str, theme: str):
    """Paint a distinct 16:9 illustrated thumbnail using only local assets."""
    width, height = 1280, 720
    top, bottom = _PALETTES.get(theme, _PALETTES["space"])
    image = _gradient((width, height), top, bottom).convert("RGBA")
    art = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(art)
    accent_rgb = tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5))

    # Fine stars / particles add texture without relying on external images.
    for index in range(95):
        x = (index * 173 + 59) % width
        y = (index * 97 + 23) % height
        radius = 1 + (index % 3)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*accent_rgb, 100 + index % 120))

    if theme in {"space", "planets"}:
        cx, cy = 930, 350
        for radius, alpha in [(248, 18), (208, 26), (170, 36)]:
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(*accent_rgb, alpha), width=3)
        draw.ellipse((cx - 118, cy - 118, cx + 118, cy + 118), fill=(65, 124, 190, 230), outline=(190, 225, 255, 200), width=5)
        draw.ellipse((cx - 85, cy - 80, cx + 35, cy + 55), fill=(120, 181, 220, 115))
        if theme == "planets":
            draw.ellipse((cx - 215, cy - 65, cx + 215, cy + 68), outline=(*accent_rgb, 210), width=17)
            draw.ellipse((cx - 55, cy - 55, cx + 55, cy + 55), fill=(178, 137, 230, 245))
    elif theme in {"network", "neural"}:
        nodes = [(790, 140), (1000, 115), (1150, 245), (860, 330), (1050, 440), (1190, 570), (770, 560), (950, 630)]
        links = [(0, 1), (0, 3), (1, 2), (1, 3), (1, 4), (2, 4), (2, 5), (3, 4), (3, 6), (4, 5), (4, 7), (6, 7)]
        for a, b in links:
            draw.line((*nodes[a], *nodes[b]), fill=(*accent_rgb, 115), width=4)
        for index, (x, y) in enumerate(nodes):
            radius = 16 + (index % 3) * 5
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*accent_rgb, 210), outline=(235, 250, 255, 230), width=3)
    elif theme == "ocean":
        for row in range(7):
            points = []
            for x in range(580, 1300, 12):
                import math
                y = 210 + row * 62 + math.sin(x / 74 + row * .72) * (17 + row * 3)
                points.append((x, int(y)))
            draw.line(points, fill=(*accent_rgb, 145 - row * 10), width=8)
        for index in range(34):
            x = 630 + (index * 89) % 600
            y = 180 + (index * 61) % 470
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(185, 255, 248, 220))
    elif theme == "aurora":
        for band in range(8):
            x = 650 + band * 75
            points = [(x + int(18 * __import__("math").sin(y / 48 + band)), y) for y in range(35, 690, 9)]
            draw.line(points, fill=(*accent_rgb, 95 + band * 10), width=28)
        art = art.filter(ImageFilter.GaussianBlur(15))
    elif theme == "volcano":
        draw.polygon([(570, 640), (760, 250), (870, 360), (1010, 175), (1275, 640)], fill=(65, 34, 37, 245))
        draw.polygon([(910, 320), (1010, 175), (1110, 360), (1035, 325)], fill=(255, 111, 63, 210))
        draw.line([(1008, 188), (1022, 275), (1062, 360), (1090, 470)], fill=(255, 130, 67, 230), width=16)
        for index in range(14):
            x = 860 + index * 29
            y = 150 + (index * 47) % 180
            draw.ellipse((x, y, x + 9, y + 9), fill=(255, 190, 94, 210))
    elif theme == "forest":
        for index in range(19):
            x = 620 + index * 38
            base = 650 - (index % 4) * 25
            draw.polygon([(x, base), (x + 55, 170 + (index % 5) * 36), (x + 110, base)], fill=(18 + index % 4 * 5, 83 + index % 5 * 9, 68 + index % 3 * 8, 180))
            draw.line((x + 55, base, x + 55, base - 145), fill=(145, 192, 122, 100), width=7)
    elif theme == "inventions":
        # A large stylised light bulb with rays represents ideas and discovery.
        cx, cy = 990, 335
        draw.ellipse((cx - 145, cy - 165, cx + 145, cy + 125), outline=(*accent_rgb, 225), width=22)
        draw.arc((cx - 88, cy + 38, cx + 88, cy + 190), 0, 180, fill=(*accent_rgb, 230), width=18)
        draw.line((cx - 65, cy + 88, cx + 65, cy + 88), fill=(255, 238, 190, 220), width=13)
        for angle in range(0, 360, 45):
            import math
            x1 = cx + int(190 * math.cos(math.radians(angle)))
            y1 = cy + int(205 * math.sin(math.radians(angle)))
            x2 = cx + int(250 * math.cos(math.radians(angle)))
            y2 = cy + int(260 * math.sin(math.radians(angle)))
            draw.line((x1, y1, x2, y2), fill=(*accent_rgb, 180), width=10)

    image = Image.alpha_composite(image, art)
    shade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for x in range(760):
        alpha = int(155 * (1 - x / 760))
        shade_draw.line((x, 0, x, height), fill=(0, 0, 0, alpha))
    image = Image.alpha_composite(image, shade)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 65, 410, 119), radius=18, fill=(255, 255, 255, 24), outline=(255, 255, 255, 70), width=2)
    draw.text((94, 78), f"STREAMHUB  /  {tag}", font=_font(23, True), fill=(245, 248, 255, 245))

    lines = textwrap.wrap(title, width=25)
    title_font = _font(61 if len(lines) <= 2 else 52, True)
    y = 205 if len(lines) <= 2 else 175
    for line in lines[:3]:
        draw.text((72, y), line, font=title_font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 100))
        y += title_font.size + 16

    draw.rounded_rectangle((72, 600, 310, 655), radius=17, fill=(*accent_rgb, 230))
    draw.text((96, 612), "СМОТРЕТЬ ВИДЕО", font=_font(20, True), fill=(8, 15, 28, 255))
    opaque = Image.new("RGBA", (width, height), (8, 10, 18, 255))
    opaque.alpha_composite(image)
    opaque.convert("RGB").save(path, "JPEG", quality=91, optimize=True)


def create_motion_clip(cover_path: str, output_path: str, duration: int = 12):
    """Create a lightweight MP4 demo clip with a subtle camera push-in."""
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", "24", "-i", cover_path,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(duration),
        "-vf", "zoompan=z='min(zoom+0.00012,1.025)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=24,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
        "-c:a", "aac", "-b:a", "64k", "-shortest", "-movflags", "+faststart", output_path,
    ], check=True, timeout=120)


def _extract_thumbnail(video_path: str, thumb_path: str):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video_path,
        "-frames:v", "1", "-q:v", "3", thumb_path,
    ], check=True, timeout=30)


def seed():
    ensure_bucket()
    db: Session = SessionLocal()
    try:
        users = {}
        for username, email, password, role in DEMO_USERS:
            user = db.query(User).filter_by(username=username).first()
            if not user:
                user = User(
                    username=username, email=email, hashed_password=hash_password(password),
                    role=role, bio="Демонстрационный канал StreamHub",
                )
                db.add(user)
                db.flush()
            users[username] = user
        db.commit()

        # Add only missing titles. This also enriches an already populated database.
        existing_titles = {title for (title,) in db.query(Video.title).all()}
        with tempfile.TemporaryDirectory(prefix="streamhub-seed-") as workdir:
            bundled_demo = os.path.join(os.path.dirname(__file__), "..", "media", "space-journey.mp4")
            for index, item in enumerate(DEMO_VIDEOS, 1):
                if item["title"] in existing_titles:
                    continue
                raw = os.path.join(workdir, f"sample-{index}.mp4")
                thumb = os.path.join(workdir, f"sample-{index}.jpg")
                if index == 1 and os.path.exists(bundled_demo):
                    shutil.copyfile(bundled_demo, raw)
                    _extract_thumbnail(raw, thumb)
                    clip_duration = 6.0
                else:
                    create_cover(thumb, item["title"], item["tag"], item["accent"], item["theme"])
                    create_motion_clip(thumb, raw)
                    clip_duration = 12.0

                owner = users["moderator"] if index == 2 else users["demo"]
                video = Video(
                    owner_id=owner.id, title=item["title"], description=item["description"],
                    visibility="public", status="ready",
                    original_key=f"seed/original-{index}.mp4",
                    processed_key=f"seed/processed-{index}.mp4",
                    thumbnail_key=f"seed/thumbnail-{index}.jpg",
                    duration=clip_duration, views=item["views"],
                )
                db.add(video)
                db.flush()
                upload_file(raw, video.original_key, "video/mp4")
                upload_file(raw, video.processed_key, "video/mp4")
                upload_file(thumb, video.thumbnail_key, "image/jpeg")
            db.commit()

        videos = db.query(Video).order_by(Video.id.asc()).all()
        if videos and not db.query(Comment).first():
            db.add(Comment(video_id=videos[0].id, user_id=users["moderator"].id, body="Отлично, плеер работает!"))
            db.add(Comment(video_id=videos[0].id, user_id=users["demo"].id, body="Добро пожаловать на канал."))
            db.add(Like(video_id=videos[0].id, user_id=users["moderator"].id))
            db.add(Subscription(subscriber_id=users["moderator"].id, channel_id=users["demo"].id))
            db.commit()

        if not db.query(Playlist).first():
            playlist = Playlist(owner_id=users["demo"].id, title="Мой плейлист", description="Демо-подборка", visibility="public")
            db.add(playlist)
            db.flush()
            if videos:
                db.add(PlaylistVideo(playlist_id=playlist.id, video_id=videos[0].id, position=0))
            db.commit()
        print("Demo data is ready. Accounts: demo / moderator / admin (see README).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
