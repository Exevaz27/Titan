import os
from pathlib import Path
from PIL import Image, ImageDraw

ASSETS_DIR = Path(__file__).parent.parent / "assets"

# Paletas de color cyberpunk según estado
THEMES = {
    "idle": {
        "primary": (0, 240, 255),      # Cian neón
        "glow": (0, 180, 230),
        "core": (10, 20, 35),
        "accent": (255, 255, 255)
    },
    "listening": {
        "primary": (0, 255, 120),      # Verde esmeralda escucha
        "glow": (0, 200, 80),
        "core": (10, 35, 20),
        "accent": (255, 255, 255)
    },
    "processing": {
        "primary": (255, 190, 10),     # Amarillo ámbar pensamiento
        "glow": (240, 140, 0),
        "core": (35, 28, 10),
        "accent": (255, 255, 255)
    },
    "speaking": {
        "primary": (217, 70, 239),     # Violeta/magenta voz
        "glow": (168, 85, 247),
        "core": (32, 10, 38),
        "accent": (255, 255, 255)
    },
    "rebel": {
        "primary": (255, 30, 70),      # Rojo furia rebelde
        "glow": (200, 10, 40),
        "core": (40, 10, 15),
        "accent": (255, 255, 255)
    }
}

def draw_titan_badge(state="idle", size=256) -> Image.Image:
    """Dibuja el núcleo cibernético de Titán con supersampling 2x para bordes ultra nítidos"""
    scale = 2
    dim = size * scale
    img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    theme = THEMES.get(state, THEMES["idle"])
    primary = theme["primary"]
    glow = theme["glow"]
    core_bg = theme["core"]
    accent = theme["accent"]

    center = dim // 2
    r_outer = int(dim * 0.44)
    r_mid = int(dim * 0.35)
    r_core = int(dim * 0.22)

    # 1. Base circular oscura con tinte de estado
    draw.ellipse(
        [center - r_outer, center - r_outer, center + r_outer, center + r_outer],
        fill=core_bg,
        outline=(*glow, 160),
        width=int(6 * scale)
    )

    # 2. Anillo de energía exterior
    draw.ellipse(
        [center - r_mid, center - r_mid, center + r_mid, center + r_mid],
        fill=None,
        outline=(*primary, 240),
        width=int(10 * scale)
    )

    # 3. Núcleo central pulsante
    draw.ellipse(
        [center - r_core, center - r_core, center + r_core, center + r_core],
        fill=(*primary, 230),
        outline=accent,
        width=int(4 * scale)
    )

    # 4. Detalles distintivos por estado
    if state == "rebel":
        # Cejas afiladas enojadas
        w_brow = int(28 * scale)
        y_brow = center - int(12 * scale)
        draw.line([center - w_brow, y_brow - int(10 * scale), center - int(4 * scale), y_brow + int(4 * scale)], fill=accent, width=int(5 * scale))
        draw.line([center + int(4 * scale), y_brow + int(4 * scale), center + w_brow, y_brow - int(10 * scale)], fill=accent, width=int(5 * scale))
    elif state == "listening":
        # Ondas laterales de audio
        r_wave = int(dim * 0.48)
        draw.arc([center - r_wave, center - r_wave, center + r_wave, center + r_wave], start=-40, end=40, fill=(*primary, 200), width=int(4 * scale))
        draw.arc([center - r_wave, center - r_wave, center + r_wave, center + r_wave], start=140, end=220, fill=(*primary, 200), width=int(4 * scale))
    else:
        # Destello de brillo especular
        r_gleam = int(5 * scale)
        draw.ellipse([center - int(7 * scale), center - int(7 * scale), center - int(7 * scale) + r_gleam, center - int(7 * scale) + r_gleam], fill=(255, 255, 255, 240))

    # Downsampling con filtro LANCZOS para máxima calidad
    return img.resize((size, size), Image.Resampling.LANCZOS)

def generate_all_icons():
    """Genera todos los iconos de Titán y el paquete .ico oficial de Windows"""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Generar PNGs por estado
    for state in THEMES.keys():
        icon_img = draw_titan_badge(state, size=256)
        out_png = ASSETS_DIR / f"titan_{state}.png"
        icon_img.save(out_png, format="PNG")
        print(f"[OK] Generado: {out_png.name}")

    # 2. Generar titan.ico multirresolución oficial de Windows (16, 32, 48, 64, 128, 256)
    base_img = draw_titan_badge("idle", size=256)
    ico_path = ASSETS_DIR / "titan.ico"
    base_img.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print(f"[OK] Generado paquete Windows ICO: {ico_path.name}")

    # 3. Copiar a static para favicon web
    static_ico = Path(__file__).parent.parent / "server" / "static" / "favicon.ico"
    base_img.save(static_ico, format="ICO", sizes=[(32, 32), (48, 48)])

if __name__ == "__main__":
    generate_all_icons()
