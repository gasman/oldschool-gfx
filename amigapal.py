#!/usr/bin/env python

import sys
from pathlib import Path
from PIL import Image

for filename in sys.argv[1:]:
    path = Path(filename)

    recoil_image_extensions = ['.iff', '.lbm', '.pic']

    if path.suffix in recoil_image_extensions:
        from recoil import RecoilImage
        img = RecoilImage(str(path)).to_pil()
    else:
        img = Image.open(str(path))

    if img.width > 320 or img.height > 256:
        print(f"{filename} exceeds 320x256 - {img.width}x{img.height}")
        continue

    flat_palette = img.getpalette('RGB')
    colors = img.getcolors()

    if flat_palette:
        # palette is returned as [r, g, b, r, g, b, ...] - convert to [(r, g, b), ...]
        palette = [tuple(flat_palette[i:i+3]) for i in range(0, len(flat_palette), 3)]
        used_palette = {palette[i] for count, i in colors}
    else:
        used_palette = {color for count, color in colors}

    if len(used_palette) > 32:
        print(f"{filename} uses {len(used_palette)} colors - maximum is 32")
        continue

    # For the palette to be OCS compliant, either:
    # all RGB values must be divisible by 16 (e.g. #102030), or
    # all RGB values must be divisible by 17 (e.g. #112233)

    palette_is_mod16 = all(
        all(c % 16 == 0 for c in color)
        for color in used_palette
    )
    palette_is_mod17 = all(
        all(c % 17 == 0 for c in color)
        for color in used_palette
    )

    # print palette as hex
    #for color in used_palette:
    #    print(f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}")


    if palette_is_mod16 or palette_is_mod17:
        print(f"{filename} is certified OCS-friendly! ({img.width}x{img.height}, {len(used_palette)} colors)")
        continue

    if not flat_palette:
        img = img.quantize(dither=Image.NONE, colors=32)

    if path.suffix in recoil_image_extensions:
        # save a PNG of the original image for reference
        orig_outfile = f"{path.stem}.ORIG.png"
        img.save(orig_outfile)

    fixed_palette = [round(c / 17) * 17 for c in img.getpalette('RGB')]
    img.putpalette(fixed_palette, 'RGB')
    outfile = f"{path.stem}.OCS.png"
    img.save(outfile)
    print(f"{filename} contains non-OCS colors :-( Fixed version saved as {outfile}")
