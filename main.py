import os
import uuid
import subprocess
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright


app = FastAPI(title="AI Quote Renderer")

OUTPUT_DIR = Path("/tmp/renders")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RENDERER_KEY = os.getenv("RENDERER_KEY")


class RenderRequest(BaseModel):
    quote: str
    author: str | None = None
    template: str = "minimal_center"
    alignment: str = "center"
    animation: str = "slow_zoom"
    duration_seconds: int = 8
    text_color: str = "white"
    font_family: str = "Inter"
    background_url: str | None = None


@app.get("/")
def health():
    return {
        "status": "ok",
        "service": "quote-renderer"
    }


@app.post("/render")
async def render(
    request: RenderRequest,
    x_renderer_key: str | None = Header(default=None)
):

    if RENDERER_KEY and x_renderer_key != RENDERER_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid renderer key"
        )

    render_id = str(uuid.uuid4())

    image_path = OUTPUT_DIR / f"{render_id}.png"
    html_path = OUTPUT_DIR / f"{render_id}.html"
    video_path = OUTPUT_DIR / f"{render_id}.mp4"

    background = request.background_url or ""

    author_html = ""

    if request.author:
        author_html = f"""
        <div class="author">
            — {request.author}
        </div>
        """

    html = f"""
    <!DOCTYPE html>

    <html>
    <head>

    <meta charset="UTF-8">

    <style>

    @import url(
        'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap'
    );

    * {{
        box-sizing: border-box;
    }}

    html, body {{
        margin: 0;
        width: 100%;
        height: 100%;
        overflow: hidden;
        font-family: '{request.font_family}', Inter, sans-serif;
    }}

    .canvas {{
        width: 1080px;
        height: 1920px;

        display: flex;

        align-items: center;

        justify-content: center;

        text-align: {request.alignment};

        position: relative;

        overflow: hidden;

        background:
            linear-gradient(
                rgba(0,0,0,0.45),
                rgba(0,0,0,0.45)
            ),
            url("{background}");

        background-size: cover;

        background-position: center;
    }}

    .content {{
        position: relative;

        z-index: 2;

        width: 82%;

        color: {request.text_color};

        animation: zoom {request.duration_seconds}s ease-in-out infinite alternate;
    }}

    .quote {{
        font-size: 64px;

        line-height: 1.25;

        font-weight: 600;

        text-shadow:
            0 4px 20px rgba(0,0,0,0.5);
    }}

    .author {{
        margin-top: 45px;

        font-size: 32px;

        opacity: 0.85;
    }}

    @keyframes zoom {{

        from {{
            transform: scale(1);
        }}

        to {{
            transform: scale(1.08);
        }}

    }}

    </style>

    </head>

    <body>

        <div class="canvas">

            <div class="content">

                <div class="quote">
                    {request.quote}
                </div>

                {author_html}

            </div>

        </div>

    </body>

    </html>
    """

    html_path.write_text(html, encoding="utf-8")

    # -----------------------------
    # Generate PNG
    # -----------------------------

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1080,
                "height": 1920
            },
            device_scale_factor=1
        )

        await page.goto(
            f"file://{html_path}",
            wait_until="networkidle"
        )

        await page.screenshot(
            path=str(image_path),
            full_page=True
        )

        await browser.close()

    # -----------------------------
    # Generate MP4
    # -----------------------------

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(request.duration_seconds),
            "-vf",
            "scale=1080:1920",
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(video_path)
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    return {
        "success": True,
        "render_id": render_id,
        "image_path": f"/files/{render_id}.png",
        "video_path": f"/files/{render_id}.mp4"
    }


@app.get("/files/{filename}")
async def get_file(filename: str):

    path = OUTPUT_DIR / filename

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    return FileResponse(path)