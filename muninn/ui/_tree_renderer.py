#!/usr/bin/env python3
"""Render un arbre scanné sur sa nouvelle image cyberpunk.
Usage: python render_tree.py scans/yggdrasil-engine.json"""

from PIL import Image, ImageDraw, ImageFont
import json, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(ROOT, "templates")
TGT_W, TGT_H = 1024, 1536

# Real ground level per family (measured from ChatGPT images)
FAMILY_SOL_Y = {
    "conifere": 890,
    "feuillu":  720,
    "baobab":   895,
    "palmier":  885,
    "buisson":  730,
    "liane":    815,
}

# Positions baobab 1024x1536 — NOW using dynamic remap per family
# Generic slot templates (relative: 0.0=top, 1.0=ground for aerial; 0.0=ground, 1.0=bottom for roots)
AERIAL_SLOTS = {
    "C":   [{"rx": 0.50, "ry": 0.05}, {"rx": 0.47, "ry": 0.08}],
    "F":   [{"rx": 0.55, "ry": 0.18}, {"rx": 0.42, "ry": 0.20}],
    "b":   [{"rx": 0.54, "ry": 0.32}, {"rx": 0.44, "ry": 0.34}, {"rx": 0.60, "ry": 0.36}],
    "B":   [{"rx": 0.53, "ry": 0.50}, {"rx": 0.43, "ry": 0.52}, {"rx": 0.62, "ry": 0.56}],
    "T":   [{"rx": 0.50, "ry": 0.80}],
}

ROOT_SLOTS = {
    "R-1": [{"rx": 0.58, "ry": 0.10}, {"rx": 0.40, "ry": 0.12}, {"rx": 0.63, "ry": 0.15}],
    "R-2": [{"rx": 0.62, "ry": 0.28}, {"rx": 0.36, "ry": 0.30}],
    "R-3": [{"rx": 0.67, "ry": 0.45}, {"rx": 0.30, "ry": 0.48}, {"rx": 0.72, "ry": 0.50}],
    "R-4": [{"rx": 0.72, "ry": 0.65}, {"rx": 0.25, "ry": 0.68}],
    "R-5": [{"rx": 0.76, "ry": 0.82}, {"rx": 0.22, "ry": 0.85}],
}


def get_slot_px(family, level, index):
    """Convert relative slot to absolute pixel position."""
    sol_y = FAMILY_SOL_Y.get(family, 750)
    air_top = 90
    air_bot = sol_y - 30
    und_top = sol_y + 30
    und_bot = TGT_H - 80

    if level in AERIAL_SLOTS:
        slots = AERIAL_SLOTS[level]
        slot = slots[index % len(slots)]
        x = int(slot["rx"] * TGT_W)
        y = int(air_top + slot["ry"] * (air_bot - air_top))
        return x, y
    elif level in ROOT_SLOTS:
        slots = ROOT_SLOTS[level]
        slot = slots[index % len(slots)]
        x = int(slot["rx"] * TGT_W)
        y = int(und_top + slot["ry"] * (und_bot - und_top))
        return x, y
    else:
        return TGT_W // 2, sol_y

# Map scan levels to skeleton levels
LEVEL_MAP = {
    "C": "C",    # Cime (tests/CI)
    "F": "F",    # Feuilles (features)
    "b": "b",    # Rameaux (sub-modules)
    "B": "B",    # Branches
    "T": "T",    # Tronc
    "R": "R-1",  # Racines (generic maps to R-1 by default)
}

COLORS = {
    "C": (40, 200, 98), "F": (50, 181, 85), "b": (56, 160, 72),
    "B": (61, 138, 58), "T": (90, 154, 53),
    "R-1": (154, 116, 83), "R-2": (138, 99, 68), "R-3": (122, 82, 53),
    "R-4": (107, 66, 38), "R-5": (92, 51, 23),
}

STATUS_RING = {
    "done": (40, 200, 98),       # vert
    "wip":  (220, 180, 40),      # ambre
    "todo": (200, 60, 60),       # rouge
    "skip": (100, 100, 100),     # gris
}


def get_depth_level(node):
    """Map node depth to root sublevel."""
    depth = node.get("depth", 0)
    if depth == -5: return "R-5"
    if depth == -4: return "R-4"
    if depth == -3: return "R-3"
    if depth == -2: return "R-2"
    if depth == -1: return "R-1"
    return None


def draw_glow_ring(draw, cx, cy, r, color, alpha_outer=50, ring_w=6):
    for i in range(ring_w, 0, -1):
        a = int(alpha_outer * (1 - i / ring_w))
        rr = r + ring_w + i
        draw.ellipse([(cx-rr, cy-rr), (cx+rr, cy+rr)],
                     fill=None, outline=(*color, a), width=1)
    rr = r + 2
    draw.ellipse([(cx-rr, cy-rr), (cx+rr, cy+rr)],
                 fill=None, outline=(*color, 120), width=2)


def render(scan_path, output_path=None):
    with open(scan_path) as f:
        tree = json.load(f)

    family = tree.get("family", "buisson")
    nodes = tree.get("nodes", [])
    name = tree.get("idea", "?").replace("[scanned] ", "")
    scale = tree.get("scale", {})

    # Load cyberpunk image
    bg_path = os.path.join(TEMPLATES, f"{family}_final.png")
    if not os.path.exists(bg_path):
        bg_path = os.path.join(TEMPLATES, f"{family}_chatgpt_raw.png")
    if not os.path.exists(bg_path):
        print(f"❌ No image for family {family}")
        return

    bg = Image.open(bg_path).convert("RGBA")
    if bg.size != (TGT_W, TGT_H):
        bg = bg.resize((TGT_W, TGT_H), Image.LANCZOS)

    overlay = Image.new("RGBA", (TGT_W, TGT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 12)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 10)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 16)
    except:
        font = font_sm = font_title = ImageFont.load_default()

    # Assign positions to nodes
    slot_usage = {}
    placed = []

    for node in nodes:
        level = node.get("level", "B")
        skel_level = LEVEL_MAP.get(level, level)

        # Root nodes: use depth to determine sublevel
        if level == "R":
            dl = get_depth_level(node)
            if dl:
                skel_level = dl

        if skel_level not in AERIAL_SLOTS and skel_level not in ROOT_SLOTS:
            skel_level = "B"  # fallback

        idx = slot_usage.get(skel_level, 0)
        slot_usage[skel_level] = idx + 1

        px, py = get_slot_px(family, skel_level, idx)
        placed.append({**node, "px": px, "py": py, "skel_level": skel_level})

    # Ground line at real SOL_Y
    sol_y = FAMILY_SOL_Y.get(family, 750)
    for i in range(6):
        a = 150 - i * 22
        draw.line([(0, sol_y + i - 3), (TGT_W, sol_y + i - 3)],
                  fill=(200, 160, 30, max(a, 15)), width=1)

    # Draw nodes
    for n in placed:
        cx, cy = n["px"], n["py"]
        status = n.get("status", "done")
        skel = n["skel_level"]
        col = COLORS.get(skel, (200, 200, 200))
        ring_col = STATUS_RING.get(status, (200, 200, 200))
        conf = n.get("confidence", 80)
        r = max(10, int(14 * (conf / 100)))

        # Glow ring colored by status
        draw_glow_ring(draw, cx, cy, r, ring_col, alpha_outer=60, ring_w=8)

        # Node fill colored by level
        draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)],
                     fill=(*col, 220),
                     outline=(*ring_col, 240), width=3)

        # Inner highlight
        hr = max(3, r // 3)
        draw.ellipse([(cx-hr-1, cy-hr-2), (cx+hr-1, cy+hr-2)],
                     fill=(255, 255, 255, 100))

        # Status icon
        if status == "done":
            icon = "✓"
        elif status == "todo":
            icon = "✗"
        elif status == "wip":
            icon = "~"
        else:
            icon = "·"

        # Label card
        label = n.get("label", "?")
        # Truncate long labels
        if len(label) > 35:
            label = label[:32] + "..."

        tw = draw.textlength(label, font=font_sm) if hasattr(draw, 'textlength') else len(label) * 7
        pad_h, pad_v = 8, 4
        tx = cx - tw / 2
        ty = cy - r - 24

        # Card background
        box = [(tx - pad_h, ty - pad_v), (tx + tw + pad_h, ty + 14 + pad_v)]
        draw.rounded_rectangle(box, radius=5, fill=(20, 20, 20, 210),
                               outline=(*ring_col, 140), width=2)

        # Status dot in label
        draw.text((tx - 2, ty), label, fill=(*col, 250), font=font_sm)

    # Title bar top
    title = f"🌳 {name.upper()}"
    phase = tree.get("phase", "?")
    scale_label = scale.get("label", "")

    # Top banner
    draw.rounded_rectangle([(20, 20), (TGT_W - 20, 85)], radius=8,
                           fill=(18, 18, 18, 220),
                           outline=(139, 105, 20, 120), width=2)
    draw.text((40, 28), title, fill=(220, 200, 160, 250), font=font_title)
    draw.text((40, 52), f"Phase: {phase}  |  {scale_label}", fill=(160, 150, 130, 200), font=font_sm)

    # Stats bar bottom
    stats = tree.get("stats", {})
    total_files = stats.get("total_files", 0)
    total_lines = stats.get("total_code_lines", 0)
    langs = ", ".join(stats.get("languages", {}).keys())

    draw.rounded_rectangle([(20, TGT_H - 70), (TGT_W - 20, TGT_H - 20)], radius=8,
                           fill=(18, 18, 18, 220),
                           outline=(139, 105, 20, 120), width=2)
    draw.text((40, TGT_H - 62),
              f"{total_files} fichiers  |  {total_lines} lignes  |  {langs}",
              fill=(160, 150, 130, 200), font=font_sm)

    found = sum(1 for n in nodes if n.get("status") == "done")
    missing = sum(1 for n in nodes if n.get("status") == "todo")
    draw.text((40, TGT_H - 44),
              f"✅ {found} trouvés   🔴 {missing} manquants",
              fill=(160, 150, 130, 200), font=font_sm)

    # Legend
    legend_y = 100
    draw.rounded_rectangle([(TGT_W - 180, legend_y), (TGT_W - 20, legend_y + 80)],
                           radius=6, fill=(18, 18, 18, 200),
                           outline=(139, 105, 20, 80), width=1)
    draw.text((TGT_W - 170, legend_y + 5), "LÉGENDE", fill=(139, 105, 20, 180), font=font_sm)

    for i, (status, color) in enumerate([("done", (40, 200, 98)),
                                           ("todo", (200, 60, 60)),
                                           ("wip", (220, 180, 40))]):
        y = legend_y + 22 + i * 18
        draw.ellipse([(TGT_W - 170, y), (TGT_W - 158, y + 12)], fill=(*color, 220))
        draw.text((TGT_W - 150, y - 1), status.upper(), fill=(200, 190, 170, 200), font=font_sm)

    # Composite
    result = Image.alpha_composite(bg, overlay)

    if not output_path:
        output_path = os.path.join(TEMPLATES, f"{name}_tree_render.png")

    result.save(output_path)
    print(f"  ✅ Rendu: {output_path}")
    return output_path


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "scans/yggdrasil-engine.json"
    render(path)
