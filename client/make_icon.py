"""
Sm_AICoder 아이콘 생성 — Pillow 12.x 호환
256x256으로 그린 뒤 ICO 멀티사이즈로 저장한다.
"""
from PIL import Image, ImageDraw
import os


BG     = (13,  17,  23,  255)
BORDER = (88,  166, 255, 255)
BLUE   = (88,  166, 255, 255)
WHITE  = (230, 237, 243, 255)
GLOW   = (88,  166, 255, 80)


def draw_icon(size: int) -> Image.Image:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    r = size // 6
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BG)

    lw = max(1, size // 28)
    draw.rounded_rectangle(
        [lw, lw, size - lw - 1, size - lw - 1],
        radius=r, outline=BORDER, width=lw,
    )

    cx, cy = size // 2, size // 2
    gr = int(size * 0.38)
    draw.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], fill=GLOW)

    mid = size * 0.50
    lh  = size * 0.22
    m   = size * 0.13
    tip = size * 0.09
    sw  = max(1, int(size * 0.055))

    lx = m + tip * 0.6
    draw.line([(lx + tip, mid - lh), (lx, mid), (lx + tip, mid + lh)],
              fill=BLUE, width=sw, joint="round")

    rx = size - m - tip * 0.6
    draw.line([(rx - tip, mid - lh), (rx, mid), (rx - tip, mid + lh)],
              fill=BLUE, width=sw, joint="round")

    sx1, sy1 = size * 0.42, mid + lh * 0.85
    sx2, sy2 = size * 0.58, mid - lh * 0.85
    draw.line([(sx1, sy1), (sx2, sy2)], fill=WHITE, width=sw)

    return img


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")

    # 256으로 그린 뒤 각 사이즈로 직접 리사이즈
    sizes = [256, 128, 64, 48, 32, 24, 16]
    images = [draw_icon(s) for s in sizes]

    # Pillow 12.x: 첫 번째 이미지로 save, append_images 로 나머지 추가
    images[0].save(
        out,
        format="ICO",
        append_images=images[1:],
    )

    # 저장 검증
    check = Image.open(out)
    saved = check.info.get("sizes", set())
    print(f"아이콘 생성 완료: {out}")
    print(f"포함된 사이즈: {sorted(saved, reverse=True)}")


if __name__ == "__main__":
    main()
