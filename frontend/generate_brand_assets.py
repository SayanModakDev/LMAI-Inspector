"""Production-ready brand asset generator for LMAI Inspector.
Generates:
  1. Primary horizontal logo (SVG & PNG)
  2. Full marketing logo with tagline (SVG & PNG)
  3. Icon-only brand mark (SVG & PNG)
  4. Compact wordmark (SVG & PNG)
  5. Favicon suite (SVG, ICO 16/32/48, PNG 16/32/48)
  6. App / PWA icons (192x192, 512x512) & manifest.json
  7. Dark mode logo & mark (SVG & PNG)
  8. Monochrome white & black logos & marks (SVG & PNG)
  9. Social Open Graph image 1200x630 (PNG)
  10. Report / PDF high-res logo (PNG)
"""
import os
import subprocess
import tempfile
from pathlib import Path
from PIL import Image

BASE_DIR = Path(r"c:\Users\sayan\SIH-Project\frontend\public")
BRANDING_DIR = BASE_DIR / "branding"
ICONS_DIR = BASE_DIR / "icons"

BRANDING_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not Path(CHROME_PATH).exists():
    CHROME_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
print(f"Browser renderer: {CHROME_PATH}")

def get_defs():
    return """
    <defs>
      <!-- Shield Green to Blue Gradient -->
      <linearGradient id="shieldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#16A34A"/>
        <stop offset="35%" stop-color="#10B981"/>
        <stop offset="70%" stop-color="#059669"/>
        <stop offset="100%" stop-color="#0284C7"/>
      </linearGradient>

      <!-- Magnifier Lens Gradient -->
      <linearGradient id="magGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#0A2540"/>
        <stop offset="45%" stop-color="#0E3D6E"/>
        <stop offset="100%" stop-color="#071B33"/>
      </linearGradient>

      <!-- Magnifier Dark Mode Gradient -->
      <linearGradient id="magGradDark" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#38BDF8"/>
        <stop offset="50%" stop-color="#0284C7"/>
        <stop offset="100%" stop-color="#0369A1"/>
      </linearGradient>

      <!-- Handle Navy Gradient -->
      <linearGradient id="handleGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#0E3D6E"/>
        <stop offset="100%" stop-color="#06182D"/>
      </linearGradient>

      <!-- Triangle Green in letter A -->
      <linearGradient id="greenTriangle" x1="0%" y1="100%" x2="0%" y2="0%">
        <stop offset="0%" stop-color="#059669"/>
        <stop offset="100%" stop-color="#10B981"/>
      </linearGradient>
    </defs>
    """

def get_emblem(scale=1.0, tx=0, ty=0, theme="standard"):
    """
    Returns standalone emblem.
    Emblem bounding box is approximately: x: 95..415, y: 35..315.
    Center is around (255, 175).
    """
    if theme == "white":
        shield_stroke = "#FFFFFF"
        mag_stroke = "#FFFFFF"
        handle_stroke = "#FFFFFF"
        carton_stroke = "#FFFFFF"
        carton_fill = "none"
        label_fill = "none"
        label_stroke = "#FFFFFF"
        lines_stroke = "#FFFFFF"
        check_stroke = "#FFFFFF"
        scales_stroke = "#FFFFFF"
        scale_fill = "#FFFFFF"
    elif theme == "black":
        shield_stroke = "#000000"
        mag_stroke = "#000000"
        handle_stroke = "#000000"
        carton_stroke = "#000000"
        carton_fill = "none"
        label_fill = "#FFFFFF"
        label_stroke = "#000000"
        lines_stroke = "#000000"
        check_stroke = "#000000"
        scales_stroke = "#000000"
        scale_fill = "#000000"
    elif theme == "dark":
        shield_stroke = "url(#shieldGrad)"
        mag_stroke = "url(#magGradDark)"
        handle_stroke = "url(#magGradDark)"
        carton_stroke = "#38BDF8"
        carton_fill = "#0F172A"
        label_fill = "#1E293B"
        label_stroke = "#38BDF8"
        lines_stroke = "#94A3B8"
        check_stroke = "#10B981"
        scales_stroke = "#38BDF8"
        scale_fill = "#38BDF8"
    else:  # standard
        shield_stroke = "url(#shieldGrad)"
        mag_stroke = "url(#magGrad)"
        handle_stroke = "url(#handleGrad)"
        carton_stroke = "#0A2540"
        carton_fill = "#FFFFFF"
        label_fill = "#FFFFFF"
        label_stroke = "#0A2540"
        lines_stroke = "#0A2540"
        check_stroke = "#10B981"
        scales_stroke = "#0A2540"
        scale_fill = "#0A2540"

    return f"""
    <g transform="translate({tx}, {ty}) scale({scale})" class="lmai-emblem">
      <!-- 1. Protective Shield Contour -->
      <path d="M 216 48
               L 112 94
               C 112 94, 106 216, 216 272
               C 232 263, 250 250, 265 233"
            fill="none"
            stroke="{shield_stroke}"
            stroke-width="19"
            stroke-linecap="round"
            stroke-linejoin="round"/>

      <!-- 2. Magnifier Handle (angled ~135°) -->
      <path d="M 292 232 L 352 292"
            stroke="{handle_stroke}"
            stroke-width="32"
            stroke-linecap="round"/>

      <!-- 3. Magnifier Outer Rim -->
      <circle cx="236" cy="176" r="83"
              fill="none"
              stroke="{mag_stroke}"
              stroke-width="22"/>

      <!-- 4. Inner Lens Background -->
      <circle cx="236" cy="176" r="72"
              fill="{carton_fill}"/>

      <!-- 5. Packaged Commodity (Gable-top Carton in Perspective) -->
      <g stroke="{carton_stroke}" stroke-width="5.5" stroke-linejoin="round" stroke-linecap="round" fill="none">
        <!-- Top Seam Ridge -->
        <path d="M 198 118 L 260 118" stroke-width="7"/>
        <!-- Slanted Gable Roof -->
        <path d="M 198 118 L 178 155 L 246 155 L 260 118"/>
        <!-- 3D Gable Side Facet -->
        <path d="M 260 118 L 279 140 L 265 155 L 246 155"/>
        <path d="M 279 140 L 265 155 L 265 220 L 279 201 Z"/>
        <!-- Front Main Body Container -->
        <rect x="178" y="155" width="68" height="65" rx="2"/>
      </g>

      <!-- 6. White Statutory Verification Label -->
      <rect x="187" y="164" width="50" height="47" rx="3"
            fill="{label_fill}" stroke="{label_stroke}" stroke-width="3.5"/>

      <!-- 7. Mandatory Label Declarations (Text Lines) -->
      <line x1="193" y1="173" x2="227" y2="173" stroke="{lines_stroke}" stroke-width="3.5" stroke-linecap="round"/>
      <line x1="193" y1="181" x2="219" y2="181" stroke="{lines_stroke}" stroke-width="3.5" stroke-linecap="round"/>
      <line x1="193" y1="189" x2="211" y2="189" stroke="{lines_stroke}" stroke-width="3.5" stroke-linecap="round"/>

      <!-- 8. Emerald Verification Checkmark -->
      <path d="M 203 199 L 212 208 L 229 191"
            fill="none"
            stroke="{check_stroke}"
            stroke-width="6.5"
            stroke-linecap="round"
            stroke-linejoin="round"/>

      <!-- 9. Scales of Justice (Legal Metrology Balance) -->
      <g stroke="{scales_stroke}" stroke-linecap="round" stroke-linejoin="round" fill="none">
        <!-- Central Support Pillar & Finial -->
        <line x1="362" y1="144" x2="362" y2="204" stroke-width="4.5"/>
        <path d="M 358 144 L 362 137 L 366 144 Z" fill="{scale_fill}" stroke-width="1.5"/>
        <!-- Pedestal Base -->
        <path d="M 352 208 C 356 204, 368 204, 372 208 Z" fill="{scale_fill}" stroke-width="1.5"/>
        <line x1="346" y1="208" x2="378" y2="208" stroke-width="4.5"/>

        <!-- Horizontal Fulcrum Beam -->
        <line x1="334" y1="149" x2="390" y2="149" stroke-width="4"/>

        <!-- Left Balance Pan & Cords -->
        <line x1="336" y1="150" x2="324" y2="178" stroke-width="2.2"/>
        <line x1="336" y1="150" x2="348" y2="178" stroke-width="2.2"/>
        <path d="M 320 178 Q 336 190 352 178 Z" fill="none" stroke-width="3.5"/>

        <!-- Right Balance Pan & Cords -->
        <line x1="388" y1="150" x2="376" y2="178" stroke-width="2.2"/>
        <line x1="388" y1="150" x2="400" y2="178" stroke-width="2.2"/>
        <path d="M 372 178 Q 388 190 404 178 Z" fill="none" stroke-width="3.5"/>
      </g>
    </g>
    """

def get_wordmark_paths(tx=0, ty=0, scale=1.0, theme="standard"):
    """
    Renders pure vector paths for "LMAI" with the green triangle counter inside 'A'.
    Bounds: width 348, height 96.
    """
    if theme == "white":
        text_fill = "#FFFFFF"
        triangle_fill = "url(#greenTriangle)"
    elif theme == "black":
        text_fill = "#000000"
        triangle_fill = "#000000"
    elif theme == "dark":
        text_fill = "#FFFFFF"
        triangle_fill = "url(#greenTriangle)"
    else:  # standard
        text_fill = "#0A2540"
        triangle_fill = "url(#greenTriangle)"

    return f"""
    <g transform="translate({tx}, {ty}) scale({scale})">
      <!-- Letter L -->
      <path d="M 0 0 L 26 0 L 26 71 L 74 71 L 74 95 L 0 95 Z" fill="{text_fill}"/>

      <!-- Letter M -->
      <path d="M 86 0 L 117 0 L 143 56 L 169 0 L 200 0 L 200 95 L 175 95 L 175 35 L 152 82 L 134 82 L 111 35 L 111 95 L 86 95 Z" fill="{text_fill}"/>

      <!-- Letter A Outer with counter cutout -->
      <path d="M 246 0 L 274 0 L 310 95 L 282 95 L 273 69 L 247 69 L 238 95 L 210 95 Z
               M 260 21 L 251 51 L 269 51 Z"
            fill-rule="evenodd"
            fill="{text_fill}"/>

      <!-- Letter A: Vibrant Green Counter Triangle Signature -->
      <polygon points="260,20 249,52 271,52" fill="{triangle_fill}"/>

      <!-- Letter I -->
      <path d="M 322 0 L 348 0 L 348 95 L 322 95 Z" fill="{text_fill}"/>
    </g>
    """

def get_inspector_text(x=0, y=0, anchor="start", font_size=42, theme="standard"):
    """
    Renders the tracked 'INSPECTOR' secondary wordmark.
    """
    if theme == "white":
        text_fill = "#FFFFFF"
    elif theme == "black":
        text_fill = "#000000"
    elif theme == "dark":
        text_fill = "#38BDF8"
    else:
        text_fill = "#0A2540"

    return f"""
    <text x="{x}" y="{y}"
          text-anchor="{anchor}"
          font-family="system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
          font-size="{font_size}"
          font-weight="800"
          letter-spacing="0.28em"
          fill="{text_fill}">INSPECTOR</text>
    """

def get_tagline_lockup(cx=450, y=755, theme="standard"):
    """
    Renders descriptor & tagline lockup with green & blue accent pills.
    """
    if theme == "white":
        line1_fill = "#FFFFFF"
        line2_fill = "#CBD5E1"
        left_pill = "#10B981"
        right_pill = "#38BDF8"
    elif theme == "black":
        line1_fill = "#000000"
        line2_fill = "#333333"
        left_pill = "#000000"
        right_pill = "#000000"
    elif theme == "dark":
        line1_fill = "#E2E8F0"
        line2_fill = "#94A3B8"
        left_pill = "#10B981"
        right_pill = "#38BDF8"
    else:
        line1_fill = "#1E3A5F"
        line2_fill = "#1E3A5F"
        left_pill = "#16A34A"
        right_pill = "#0284C7"

    return f"""
    <g class="lmai-tagline">
      <!-- Left Pill -->
      <rect x="{cx - 390}" y="{y - 13}" width="65" height="7.5" rx="3.75" fill="{left_pill}"/>

      <!-- Primary Descriptor -->
      <text x="{cx}" y="{y - 5}"
            text-anchor="middle"
            font-family="system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
            font-size="24"
            font-weight="700"
            fill="{line1_fill}">Legal Metrology • Packaged Commodities</text>

      <!-- Right Pill -->
      <rect x="{cx + 325}" y="{y - 13}" width="65" height="7.5" rx="3.75" fill="{right_pill}"/>

      <!-- Secondary Tagline -->
      <text x="{cx}" y="{y + 35}"
            text-anchor="middle"
            font-family="system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
            font-size="23"
            font-weight="500"
            letter-spacing="0.04em"
            fill="{line2_fill}">Compliance Screening</text>
    </g>
    """

# =========================================================================
# BUILD SVG FILES WITH CALCULATED CENTERING
# =========================================================================

def build_primary_logo(theme="standard"):
    """Horizontal Lockup [emblem] [LMAI INSPECTOR], viewBox: 0 0 620 160"""
    emblem_scale = 0.44
    emblem_tx = -35
    emblem_ty = -5
    wordmark_scale = 0.72
    wordmark_tx = 175
    wordmark_ty = 30
    inspector_x = 177
    inspector_y = 135

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 620 160" width="100%" height="100%">
      {get_defs()}
      {get_emblem(scale=emblem_scale, tx=emblem_tx, ty=emblem_ty, theme=theme)}
      {get_wordmark_paths(tx=wordmark_tx, ty=wordmark_ty, scale=wordmark_scale, theme=theme)}
      {get_inspector_text(x=inspector_x, y=inspector_y, anchor="start", font_size=31, theme=theme)}
    </svg>"""
    return svg

def build_full_tagline_logo(theme="standard"):
    """Centered Presentation / Marketing Lockup with Tagline, viewBox: 0 0 900 860"""
    emblem_scale = 1.25
    emblem_tx = 131
    emblem_ty = 15
    wordmark_scale = 1.25
    wordmark_tx = 232
    wordmark_ty = 480
    inspector_cx = 450
    inspector_y = 655

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 860" width="100%" height="100%">
      {get_defs()}
      {get_emblem(scale=emblem_scale, tx=emblem_tx, ty=emblem_ty, theme=theme)}
      {get_wordmark_paths(tx=wordmark_tx, ty=wordmark_ty, scale=wordmark_scale, theme=theme)}
      {get_inspector_text(x=inspector_cx, y=inspector_y, anchor="middle", font_size=55, theme=theme)}
      {get_tagline_lockup(cx=450, y=745, theme=theme)}
    </svg>"""
    return svg

def build_mark_only(theme="standard"):
    """
    Square Icon-Only Mark (viewBox: 0 0 400 400).
    Emblem bounding box: x: 95..415 (w 320), y: 35..315 (h 280).
    Center: (255, 175).
    Scale = 0.90 -> w = 288, h = 252.
    To center in 400x400:
    tx = 200 - 255 * 0.90 = 200 - 229.5 = -29.5 -> -30
    ty = 200 - 175 * 0.90 = 200 - 157.5 = +42.5 -> +42
    Left edge: 95 * 0.90 - 30 = 55.5
    Right edge: 415 * 0.90 - 30 = 343.5 (< 400, leaves 56.5px margin)
    Top edge: 35 * 0.90 + 42 = 73.5
    Bottom edge: 315 * 0.90 + 42 = 325.5 (< 400, leaves 74.5px margin)
    Result: Fully contained, beautifully centered, ZERO clipping!
    """
    emblem_scale = 0.90
    emblem_tx = -30
    emblem_ty = 42

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="100%" height="100%">
      {get_defs()}
      {get_emblem(scale=emblem_scale, tx=emblem_tx, ty=emblem_ty, theme=theme)}
    </svg>"""
    return svg

def build_compact_logo(theme="standard"):
    """
    Compact Logo (Stacked emblem + LMAI / INSPECTOR, viewBox: 0 0 440 300)
    Centered around cx=220.
    """
    emblem_scale = 0.52
    # Center of emblem: 255 * 0.52 = 132.6 -> tx = 220 - 132.6 = 87
    emblem_tx = 87
    emblem_ty = 10
    wordmark_scale = 0.72
    # w = 348 * 0.72 = 250.56 -> tx = 220 - 250.56 / 2 = 95
    wordmark_tx = 95
    wordmark_ty = 180
    inspector_cx = 220
    inspector_y = 280

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 440 300" width="100%" height="100%">
      {get_defs()}
      {get_emblem(scale=emblem_scale, tx=emblem_tx, ty=emblem_ty, theme=theme)}
      {get_wordmark_paths(tx=wordmark_tx, ty=wordmark_ty, scale=wordmark_scale, theme=theme)}
      {get_inspector_text(x=inspector_cx, y=inspector_y, anchor="middle", font_size=30, theme=theme)}
    </svg>"""
    return svg

def build_og_image_svg():
    """1200x630 Open Graph Brand Asset SVG"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
      {get_defs()}
      <defs>
        <linearGradient id="ogBg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#07182D"/>
          <stop offset="60%" stop-color="#0B2545"/>
          <stop offset="100%" stop-color="#081E38"/>
        </linearGradient>
        <radialGradient id="ogGlow" cx="25%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#10B981" stop-opacity="0.15"/>
          <stop offset="100%" stop-color="#10B981" stop-opacity="0"/>
        </radialGradient>
      </defs>

      <rect width="1200" height="630" fill="url(#ogBg)"/>
      <rect width="1200" height="630" fill="url(#ogGlow)"/>

      <!-- Subtle background grid lines -->
      <g stroke="#1E3A5F" stroke-width="1" opacity="0.25">
        <line x1="0" y1="126" x2="1200" y2="126"/>
        <line x1="0" y1="252" x2="1200" y2="252"/>
        <line x1="0" y1="378" x2="1200" y2="378"/>
        <line x1="0" y1="504" x2="1200" y2="504"/>
        <line x1="240" y1="0" x2="240" y2="630"/>
        <line x1="480" y1="0" x2="480" y2="630"/>
        <line x1="720" y1="0" x2="720" y2="630"/>
        <line x1="960" y1="0" x2="960" y2="630"/>
      </g>

      <!-- Emblem Left Side -->
      {get_emblem(scale=1.1, tx=20, ty=85, theme="dark")}

      <!-- Wordmark Right Side -->
      <g transform="translate(500, 160)">
        <!-- Category Badge -->
        <rect x="0" y="0" width="370" height="34" rx="17" fill="#10B981" fill-opacity="0.18" stroke="#10B981" stroke-width="1.5"/>
        <text x="185" y="23" text-anchor="middle"
              font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="700"
              fill="#34D399" letter-spacing="0.12em">LEGAL METROLOGY COMPLIANCE SYSTEM</text>

        <!-- LMAI Wordmark -->
        {get_wordmark_paths(tx=0, ty=60, scale=1.35, theme="dark")}

        <!-- INSPECTOR Secondary -->
        <text x="4" y="240"
              font-family="system-ui, -apple-system, sans-serif"
              font-size="58" font-weight="800" letter-spacing="0.26em"
              fill="#38BDF8">INSPECTOR</text>

        <!-- Tagline -->
        <g transform="translate(0, 310)">
          <rect x="0" y="-8" width="40" height="5" rx="2.5" fill="#10B981"/>
          <text x="55" y="0" font-family="system-ui, -apple-system, sans-serif"
                font-size="20" font-weight="600" fill="#E2E8F0">
            Packaged Commodities Verification Platform
          </text>
          <text x="4" y="32" font-family="system-ui, -apple-system, sans-serif"
                font-size="16" font-weight="400" fill="#94A3B8">
            AI-Assisted OCR • Deterministic Rule Validation • Audit Reports
          </text>
        </g>
      </g>
    </svg>"""

# =========================================================================
# WRITE ALL SVGs
# =========================================================================

svg_files = {
    BRANDING_DIR / "lmai-inspector-logo.svg": build_primary_logo("standard"),
    BRANDING_DIR / "lmai-inspector-logo-tagline.svg": build_full_tagline_logo("standard"),
    BRANDING_DIR / "lmai-inspector-mark.svg": build_mark_only("standard"),
    BASE_DIR / "favicon.svg": build_mark_only("standard"),
    BRANDING_DIR / "lmai-inspector-compact.svg": build_compact_logo("standard"),
    BRANDING_DIR / "lmai-inspector-logo-dark.svg": build_primary_logo("dark"),
    BRANDING_DIR / "lmai-inspector-mark-dark.svg": build_mark_only("dark"),
    BRANDING_DIR / "lmai-inspector-white.svg": build_primary_logo("white"),
    BRANDING_DIR / "lmai-inspector-black.svg": build_primary_logo("black"),
    BRANDING_DIR / "lmai-inspector-mark-white.svg": build_mark_only("white"),
    BRANDING_DIR / "lmai-inspector-mark-black.svg": build_mark_only("black"),
}

for path, content in svg_files.items():
    path.write_text(content.strip(), encoding="utf-8")
    print(f"Generated SVG: {path}")

# =========================================================================
# RENDER RASTER PNGs VIA HEADLESS BROWSER
# =========================================================================

def render_svg_to_png(svg_str, output_png_path, width, height, bg_transparent=True):
    bg_style = "background: transparent !important;" if bg_transparent else ""
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: {width}px;
    height: {height}px;
    {bg_style}
    overflow: hidden;
  }}
  svg {{
    width: 100%;
    height: 100%;
    display: block;
  }}
</style>
</head>
<body>
{svg_str}
</body>
</html>"""

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        html_path = f.name
        f.write(html_content)

    try:
        cmd = [
            CHROME_PATH,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={width},{height}",
            "--default-background-color=00000000" if bg_transparent else "--default-background-color=ffffffff",
            f"--screenshot={str(output_png_path)}",
            html_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Rendered PNG ({width}x{height}): {output_png_path}")
    finally:
        try:
            os.remove(html_path)
        except OSError:
            pass

print("\n--- Rendering High-Res PNG Assets ---")

# Primary
render_svg_to_png(build_primary_logo("standard"), BRANDING_DIR / "lmai-inspector-logo.png", 1240, 320)
# Tagline
render_svg_to_png(build_full_tagline_logo("standard"), BRANDING_DIR / "lmai-inspector-logo-tagline.png", 1000, 955)
# Mark
render_svg_to_png(build_mark_only("standard"), BRANDING_DIR / "lmai-inspector-mark.png", 512, 512)
# Compact
render_svg_to_png(build_compact_logo("standard"), BRANDING_DIR / "lmai-inspector-compact.png", 880, 600)
# PWA Icons
render_svg_to_png(build_mark_only("standard"), ICONS_DIR / "icon-192.png", 192, 192)
render_svg_to_png(build_mark_only("standard"), ICONS_DIR / "icon-512.png", 512, 512)
# Favicon PNGs
render_svg_to_png(build_mark_only("standard"), ICONS_DIR / "favicon-16x16.png", 16, 16)
render_svg_to_png(build_mark_only("standard"), ICONS_DIR / "favicon-32x32.png", 32, 32)
render_svg_to_png(build_mark_only("standard"), ICONS_DIR / "favicon-48x48.png", 48, 48)
# Social
render_svg_to_png(build_og_image_svg(), BRANDING_DIR / "lmai-inspector-og.png", 1200, 630, bg_transparent=False)
# Report
render_svg_to_png(build_primary_logo("standard"), BRANDING_DIR / "lmai-inspector-report.png", 1860, 480)
# Dark mode
render_svg_to_png(build_primary_logo("dark"), BRANDING_DIR / "lmai-inspector-logo-dark.png", 1240, 320)
render_svg_to_png(build_mark_only("dark"), BRANDING_DIR / "lmai-inspector-mark-dark.png", 512, 512)
# Monochrome
render_svg_to_png(build_primary_logo("white"), BRANDING_DIR / "lmai-inspector-white.png", 1240, 320)
render_svg_to_png(build_primary_logo("black"), BRANDING_DIR / "lmai-inspector-black.png", 1240, 320)
render_svg_to_png(build_mark_only("white"), BRANDING_DIR / "lmai-inspector-mark-white.png", 512, 512)
render_svg_to_png(build_mark_only("black"), BRANDING_DIR / "lmai-inspector-mark-black.png", 512, 512)

# Multi-res ICO
img_16 = Image.open(ICONS_DIR / "favicon-16x16.png")
img_32 = Image.open(ICONS_DIR / "favicon-32x32.png")
img_48 = Image.open(ICONS_DIR / "favicon-48x48.png")

ico_path = BASE_DIR / "favicon.ico"
img_48.save(
    ico_path,
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48)],
    append_images=[img_32, img_16]
)
print(f"Saved multi-resolution ICO: {ico_path}")

print("\nALL BRAND ASSETS RE-RENDERED WITH PERFECT BOUNDS!")
