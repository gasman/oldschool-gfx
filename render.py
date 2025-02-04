#!/usr/bin/env python

import json
import re
import subprocess
import sys
from pathlib import Path
from PIL import Image

OUTPUT_SIZE = (1920, 1080)

# fall back on non-integer scaling if integer scaling is less than this
# fraction of the screen
MIN_SCALED_SIZE = 0.8

DEFAULT_FRAME_RATE = 25

recoil_image_extensions = ['.iff', '.lbm', '.pic']
image_extensions = ['.png', '.gif', '.jpg', '.jpeg', '.iff', '.tif', '.pcx']
video_extensions = ['.mkv', '.mp4', '.avi']

TEMP_FILE_PREFIX = "RENDERTEMP-"
FONT_FILENAME = "dejavusans.ttf"

FRAME_RATE = None


def check_video_metadata(path):
    global FRAME_RATE
    # check that resolution matches OUTPUT_SIZE
    ffprobe = subprocess.run([
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(path),
    ], stdout=subprocess.PIPE)
    video_data = json.loads(ffprobe.stdout)
    video_stream_data = None
    for stream in video_data['streams']:
        if stream['codec_type'] == 'video':
            video_stream_data = stream
            break

    if video_stream_data is None:
        raise Exception(f"No video stream found in {path.name}")

    video_size = (video_stream_data['width'], video_stream_data['height'])
    if video_size != OUTPUT_SIZE:
        raise Exception(f"Incorrect video dimensions - expected {OUTPUT_SIZE!r}, got {video_size!r}")

    (frame_rate_num, frame_rate_denom) = video_stream_data['r_frame_rate'].split('/')
    frame_rate = int(frame_rate_num) / int(frame_rate_denom)
    if FRAME_RATE is None:
        FRAME_RATE = frame_rate
    elif FRAME_RATE != frame_rate:
        raise Exception(f"Found multiple videos with different frame rates - {FRAME_RATE} vs {frame_rate}")


def convert_slide(path, duration, frame_rate, label=None):
    img = None

    if path.suffix in recoil_image_extensions:
        from recoil import RecoilImage
        img = RecoilImage(str(path)).to_pil()
    elif path.suffix in image_extensions:
        img = Image.open(str(path))

    if label:
        filter_opts = [
            "-vf",
            f"drawtext=text='{label}':fontfile={FONT_FILENAME}:fontcolor=white:fontsize=48:borderw=2:x=w-text_w-40:y=40"
        ]
    else:
        filter_opts = []

    if img:
        img = img.convert('RGB')
        input_width, input_height = img.size
        target_width, target_height = OUTPUT_SIZE
        scale = min(
            int(target_width / input_width),
            int(target_height / input_height)
        )
        output_width = input_width * scale
        output_height = input_height * scale
        if (
            output_width >= target_width * MIN_SCALED_SIZE
            or output_height >= target_height * MIN_SCALED_SIZE
        ):
            # integer resize is OK
            img = img.resize((output_width, output_height), Image.NEAREST)
        else:
            # use non-integer resize
            scale = min(
                target_width / input_width,
                target_height / input_height
            )
            output_width = round(input_width * scale)
            output_height = round(input_height * scale)
            img = img.resize((output_width, output_height), Image.HAMMING)

        # letterbox / pillarbox
        final_img = Image.new('RGB', OUTPUT_SIZE)
        final_img.paste(img, (
            (target_width - output_width) // 2,
            (target_height - output_height) // 2,
        ))

        output_image_path = path.parent / f"{TEMP_FILE_PREFIX}{path.stem}.png"
        final_img.save(str(output_image_path))

        output_video_path = path.parent / f"{TEMP_FILE_PREFIX}{path.stem}.mkv"

        subprocess.run([
            "ffmpeg",
            "-y",
            "-r", str(frame_rate),
            "-loop", "1",
            "-i", str(output_image_path),
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-c:v", "ffv1",
            *filter_opts,
            str(output_video_path)
        ])

        return output_video_path
    elif path.suffix in video_extensions:
        output_video_path = path.parent / f"{TEMP_FILE_PREFIX}{path.stem}.mkv"

        subprocess.run([
            "ffmpeg",
            "-y",
            "-r", str(frame_rate),
            "-i", str(path),
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-c:v", "ffv1",
            *filter_opts,
            str(output_video_path)
        ])

        return output_video_path
    else:
        raise Exception(f"Unrecognised file type {path.suffix}: {path.name!r}")


workdir = Path(sys.argv[1])
if not workdir.is_dir():
    raise Exception(f"{workdir} is not a valid directory name")

pic_path = None
workstage_paths = []

for path in workdir.iterdir():
    if not re.match(r'(P|W\d+)-', path.name):
        continue
    if not path.is_file():
        continue

    if path.name.startswith('P'):
        if pic_path:
            raise Exception("Multiple picture (P-foo.png) files found")
        pic_path = path

    elif path.name.startswith('W'):
        workstage_paths.append(path)

if not pic_path:
    raise Exception("No picture (P-foo.png) file found")

workstage_paths.sort(key=lambda path: path.name)

all_paths = [pic_path] + workstage_paths

for path in all_paths:
    if path.suffix in video_extensions:
        check_video_metadata(path)

# fall back on DEFAULT_FRAME_RATE if no videos were provided as input
final_frame_rate = FRAME_RATE or DEFAULT_FRAME_RATE

pic_out_path = convert_slide(pic_path, 10, final_frame_rate)
workstage_out_paths = [
    convert_slide(
        path, 5, final_frame_rate, label=f"Stage {i+1}/{len(workstage_paths)}"
    )
    for i, path in enumerate(workstage_paths)
]

playlist_path = workdir / f"{TEMP_FILE_PREFIX}playlist.txt"

with playlist_path.open(mode='w') as playlist:
    print("ffconcat version 1.0\n", file=playlist)
    print(f"file {pic_out_path.name}", file=playlist)
    for path in workstage_out_paths:
        print(f"file {path.name}", file=playlist)
    print(f"file {pic_out_path.name}", file=playlist)

concat_path = workdir / f"{TEMP_FILE_PREFIX}concat.mkv"

subprocess.run([
    "ffmpeg",
    "-y",
    "-f", "concat", "-i", str(playlist_path),
    "-c", "copy",
    str(concat_path),
])

final_video_filename = f"00-{workdir.name}.mp4"
subprocess.run([
    "ffmpeg",
    "-y",
    "-i", str(concat_path),
    "-pix_fmt", "yuv420p",
    "-c:v", "libx264",
    "-profile:v", "high",
    "-b:v", "10M",
    final_video_filename,
])

# delete temp files
for path in workdir.iterdir():
    if path.name.startswith(TEMP_FILE_PREFIX):
        path.unlink()
