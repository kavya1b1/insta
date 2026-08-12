import html
import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="AI Quote Renderer",
    version="1.0.0",
    description="Renders AI-generated quotes into images and videos."
)


# ============================================================
# CONFIGURATION
# ============================================================

OUTPUT_DIR = Path("/tmp/renders")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RENDERER_KEY = os.getenv("RENDERER_KEY")

MAX_DURATION_SECONDS = 60
MIN_DURATION_SECONDS = 1


# ============================================================
# REQUEST MODEL
# ============================================================

class RenderRequest(BaseModel):
    quote: str = Field(..., min_length=1, max_length=2000)

    author: str | None = Field(
        default=None,
        max_length=200
    )

    template: str = Field(
        default="minimal_center",
        max_length=50
    )

    alignment: str = Field(
        default="center",
        max_length=20
    )

    animation: str = Field(
        default="slow_zoom",
        max_length=50
    )

    duration_seconds: int = Field(
        default=8,
        ge=MIN_DURATION_SECONDS,
        le=MAX_DURATION_SECONDS
    )

    text_color: str = Field(
        default="white",
        max_length=30
    )

    font_family: str = Field(
        default="Inter",
        max_length=100
    )

    background_url: str | None = Field(
        default=None,
        max_length=2000
    )


# ============================================================
# HELPERS
# ============================================================

def validate_alignment(alignment: str) -> str:
    """
    Prevent invalid CSS alignment values.
    """

    allowed = {
        "left",
        "center",
        "right"
    }

    if alignment not in allowed:
        return "center"

    return alignment


def validate_background_url(background_url: str | None) -> str:
    """
    Validate background URL.

    Empty background is allowed.
    HTTP/HTTPS URLs are allowed.
    """

    if not background_url:
        return ""

    try:
        parsed = urlparse(background_url)

        if parsed.scheme not in {"http", "https"}:
            return ""

        if not parsed.netloc:
            return ""

        return background_url

    except Exception:
        return ""


def safe_css_value(value: str, default: str) -> str:
    """
    Prevent basic CSS injection through request values.
    """

    if not value:
        return default

    dangerous = [
        ";",
        "{",
        "}",
        "<",
        ">",
        "\n",
        "\r"
    ]

    for character in dangerous:
        if character in value:
            return default

    return value


def log_error(title: str, error: Exception):
    """
    Consistent server-side error logging.
    """

    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print(f"Error type: {type(error).__name__}")
    print(f"Error: {error}")
    print("=" * 70 + "\n")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
async def health():
    return {
        "status": "ok",
        "service": "quote-renderer",
        "version": "1.0.0"
    }


# ============================================================
# RENDER ENDPOINT
# ============================================================

@app.post("/render")
async def render(
    request: RenderRequest,
    x_renderer_key: str | None = Header(default=None)
):

    # --------------------------------------------------------
    # AUTHENTICATION
    # --------------------------------------------------------

    if not RENDERER_KEY:
        print(
            "WARNING: RENDERER_KEY environment variable "
            "is not configured."
        )

    if RENDERER_KEY and x_renderer_key != RENDERER_KEY:

        raise HTTPException(
            status_code=401,
            detail="Invalid renderer key"
        )

    # --------------------------------------------------------
    # GENERATE UNIQUE FILE NAMES
    # --------------------------------------------------------

    render_id = str(uuid.uuid4())

    image_path = OUTPUT_DIR / f"{render_id}.png"
    html_path = OUTPUT_DIR / f"{render_id}.html"
    video_path = OUTPUT_DIR / f"{render_id}.mp4"

    # --------------------------------------------------------
    # SANITIZE INPUT
    # --------------------------------------------------------

    quote = html.escape(request.quote.strip())

    author = (
        html.escape(request.author.strip())
        if request.author
        else None
    )

    alignment = validate_alignment(
        request.alignment
    )

    background_url = validate_background_url(
        request.background_url
    )

    text_color = safe_css_value(
        request.text_color,
        "white"
    )

    font_family = safe_css_value(
        request.font_family,
        "Inter"
    )

    duration = request.duration_seconds

    # --------------------------------------------------------
    # AUTHOR HTML
    # --------------------------------------------------------

    author_html = ""

    if author:

        author_html = f"""
        <div class="author">
            — {author}
        </div>
        """

    # --------------------------------------------------------
    # BACKGROUND
    # --------------------------------------------------------

    if background_url:

        background_css = f"""
        background:
            linear-gradient(
                rgba(0, 0, 0, 0.45),
                rgba(0, 0, 0, 0.45)
            ),
            url("{background_url}");

        background-size: cover;
        background-position: center;
        """

    else:

        background_css = """
        background:
            linear-gradient(
                135deg,
                #111111,
                #222222
            );
        """

    # --------------------------------------------------------
    # HTML TEMPLATE
    # --------------------------------------------------------

    page_html = f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0"
>

<title>AI Quote</title>

<style>

* {{
    box-sizing: border-box;
}}

html,
body {{
    margin: 0;
    padding: 0;

    width: 100%;
    height: 100%;

    overflow: hidden;

    font-family:
        "{font_family}",
        "Inter",
        Arial,
        sans-serif;

    background: #111;
}}

body {{
    display: flex;
    align-items: center;
    justify-content: center;
}}

.canvas {{

    width: 1080px;
    height: 1920px;

    position: relative;

    display: flex;

    align-items: center;
    justify-content: center;

    overflow: hidden;

    text-align: {alignment};

    {background_css}
}}

.content {{

    position: relative;

    z-index: 2;

    width: 82%;

    color: {text_color};

    animation:
        zoom {duration}s
        ease-in-out
        infinite
        alternate;
}}

.quote {{

    font-size: 64px;

    line-height: 1.25;

    font-weight: 600;

    letter-spacing: -0.5px;

    text-shadow:
        0 4px 20px
        rgba(0, 0, 0, 0.55);

    word-wrap: break-word;

    overflow-wrap: break-word;
}}

.author {{

    margin-top: 45px;

    font-size: 32px;

    line-height: 1.3;

    opacity: 0.85;

    text-shadow:
        0 3px 12px
        rgba(0, 0, 0, 0.45);
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
            {quote}
        </div>

        {author_html}

    </div>

</div>

</body>

</html>
"""

    # --------------------------------------------------------
    # WRITE HTML
    # --------------------------------------------------------

    try:

        html_path.write_text(
            page_html,
            encoding="utf-8"
        )

    except Exception as error:

        log_error(
            "HTML FILE CREATION FAILED",
            error
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to create render HTML."
        )

    # ========================================================
    # PLAYWRIGHT / PNG
    # ========================================================

    try:

        print(
            f"[{render_id}] Starting Playwright..."
        )

        async with async_playwright() as playwright:

            # ------------------------------------------------
            # Launch Chromium
            # ------------------------------------------------

            browser = await playwright.chromium.launch(
                headless=True,

                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-zygote"
                ]
            )

            # ------------------------------------------------
            # Browser Page
            # ------------------------------------------------

            page = await browser.new_page(
                viewport={
                    "width": 1080,
                    "height": 1920
                },

                device_scale_factor=1
            )

            # ------------------------------------------------
            # Load HTML
            # ------------------------------------------------

            await page.goto(
                f"file://{html_path}",
                wait_until="networkidle",
                timeout=30000
            )

            # ------------------------------------------------
            # Wait For Fonts
            # ------------------------------------------------

            try:

                await page.evaluate(
                    """
                    async () => {
                        if (document.fonts) {
                            await document.fonts.ready;
                        }
                    }
                    """
                )

            except Exception as font_error:

                print(
                    f"[{render_id}] "
                    f"Font loading warning: {font_error}"
                )

            # ------------------------------------------------
            # Screenshot
            # ------------------------------------------------

            await page.screenshot(
                path=str(image_path),
                full_page=True,
                type="png"
            )

            # ------------------------------------------------
            # Close Browser
            # ------------------------------------------------

            await browser.close()

        print(
            f"[{render_id}] PNG created: "
            f"{image_path}"
        )

    except Exception as error:

        log_error(
            "PLAYWRIGHT / PNG GENERATION FAILED",
            error
        )

        # Cleanup

        try:
            if html_path.exists():
                html_path.unlink()

        except Exception:
            pass

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to generate image. "
                f"Renderer error: {str(error)}"
            )
        )

    # ========================================================
    # FFMPEG / MP4
    # ========================================================

    try:

        print(
            f"[{render_id}] Starting FFmpeg..."
        )

        ffmpeg_command = [
            "ffmpeg",

            "-y",

            "-loop",
            "1",

            "-i",
            str(image_path),

            "-t",
            str(duration),

            "-vf",
            "scale=1080:1920",

            "-r",
            "30",

            "-pix_fmt",
            "yuv420p",

            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-crf",
            "23",

            "-movflags",
            "+faststart",

            str(video_path)
        ]

        result = subprocess.run(
            ffmpeg_command,

            check=False,

            capture_output=True,

            text=True,

            timeout=120
        )

        # ----------------------------------------------------
        # Check FFmpeg result
        # ----------------------------------------------------

        if result.returncode != 0:

            print(
                f"[{render_id}] FFmpeg stdout:"
            )

            print(result.stdout)

            print(
                f"[{render_id}] FFmpeg stderr:"
            )

            print(result.stderr)

            raise RuntimeError(
                "FFmpeg failed with exit code "
                f"{result.returncode}: "
                f"{result.stderr[-1000:]}"
            )

        print(
            f"[{render_id}] MP4 created: "
            f"{video_path}"
        )

    except FileNotFoundError as error:

        log_error(
            "FFMPEG NOT FOUND",
            error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "FFmpeg is not installed "
                "in the Docker container."
            )
        )

    except subprocess.TimeoutExpired as error:

        log_error(
            "FFMPEG TIMEOUT",
            error
        )

        raise HTTPException(
            status_code=500,
            detail="FFmpeg rendering timed out."
        )

    except Exception as error:

        log_error(
            "FFMPEG VIDEO GENERATION FAILED",
            error
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to generate video. "
                f"FFmpeg error: {str(error)}"
            )
        )

    # ========================================================
    # VERIFY OUTPUT FILES
    # ========================================================

    if not image_path.exists():

        raise HTTPException(
            status_code=500,
            detail="Image file was not created."
        )

    if not video_path.exists():

        raise HTTPException(
            status_code=500,
            detail="Video file was not created."
        )

    # ========================================================
    # SUCCESS RESPONSE
    # ========================================================

    print(
        f"[{render_id}] Rendering completed successfully."
    )

    return {
        "success": True,

        "render_id": render_id,

        "image_path":
            f"/files/{render_id}.png",

        "video_path":
            f"/files/{render_id}.mp4",

        "image_url":
            f"/files/{render_id}.png",

        "video_url":
            f"/files/{render_id}.mp4"
    }


# ============================================================
# FILE DOWNLOAD ENDPOINT
# ============================================================

@app.get("/files/{filename}")
async def get_file(filename: str):

    # --------------------------------------------------------
    # Security: prevent path traversal
    # --------------------------------------------------------

    requested_path = Path(filename)

    if (
        requested_path.name != filename
        or ".." in requested_path.parts
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid filename."
        )

    path = OUTPUT_DIR / filename

    # --------------------------------------------------------
    # File existence
    # --------------------------------------------------------

    if not path.exists():

        raise HTTPException(
            status_code=404,
            detail="File not found."
        )

    # --------------------------------------------------------
    # Make sure it is a file
    # --------------------------------------------------------

    if not path.is_file():

        raise HTTPException(
            status_code=404,
            detail="Requested resource is not a file."
        )

    return FileResponse(
        path=str(path)
    )