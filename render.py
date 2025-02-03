#!/usr/bin/env python

import json
import os
import re
import subprocess
import sys
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

FRAME_RATE = None


def check_video_metadata(filename):
    global FRAME_RATE
    # check that resolution matches OUTPUT_SIZE
    ffprobe = subprocess.run([
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        filename
    ], stdout=subprocess.PIPE)
    video_data = json.loads(ffprobe.stdout)
    video_stream_data = None
    for stream in video_data['streams']:
        if stream['codec_type'] == 'video':
            video_stream_data = stream
            break

    if video_stream_data is None:
        raise Exception(f"No video stream found in {filename}")

    video_size = (video_stream_data['width'], video_stream_data['height'])
    if video_size != OUTPUT_SIZE:
        raise Exception(f"Incorrect video dimensions - expected {OUTPUT_SIZE!r}, got {video_size!r}")

    (frame_rate_num, frame_rate_denom) = video_stream_data['r_frame_rate'].split('/')
    frame_rate = int(frame_rate_num) / int(frame_rate_denom)
    if FRAME_RATE is None:
        FRAME_RATE = frame_rate
    elif FRAME_RATE != frame_rate:
        raise Exception(f"Found multiple videos with different frame rates - {FRAME_RATE} vs {frame_rate}")


def convert_slide(filename, duration, frame_rate):
    file_root, file_ext = os.path.splitext(filename)
    img = None

    if file_ext in recoil_image_extensions:
        from recoil import RecoilImage
        img = RecoilImage(filename).to_pil()
    elif file_ext in image_extensions:
        img = Image.open(filename)

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

        output_image_filename = f"{TEMP_FILE_PREFIX}{file_root}.png"
        final_img.save(output_image_filename)

        output_video_filename = f"{TEMP_FILE_PREFIX}{file_root}.mkv"

        subprocess.run([
            "ffmpeg",
            "-y",
            "-r", str(frame_rate),
            "-loop", "1",
            "-i", output_image_filename,
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-c:v", "ffv1",
            output_video_filename
        ])

        return output_video_filename
    elif file_ext in video_extensions:
        output_video_filename = f"{TEMP_FILE_PREFIX}{file_root}.mkv"

        subprocess.run([
            "ffmpeg",
            "-y",
            "-r", str(frame_rate),
            "-i", filename,
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-c:v", "ffv1",
            output_video_filename
        ])

        return output_video_filename
    else:
        raise Exception(f"Unrecognised file type {file_ext}: {filename!r}")


pic_filename = None
workstage_filenames = []

for filename in os.listdir('.'):
    if not re.match(r'(P|W\d)-', filename):
        continue
    if not os.path.isfile(filename):
        continue

    if filename.startswith('P'):
        if pic_filename:
            raise Exception("Multiple picture (P-foo.png) files found")
        pic_filename = filename

    elif filename.startswith('W'):
        workstage_filenames.append(filename)

if not pic_filename:
    raise Exception("No picture (P-foo.png) file found")

workstage_filenames.sort()

all_filenames = [pic_filename] + workstage_filenames

for filename in all_filenames:
    file_root, file_ext = os.path.splitext(filename)
    if file_ext in video_extensions:
        check_video_metadata(filename)

# fall back on DEFAULT_FRAME_RATE if no videos were provided as input
final_frame_rate = FRAME_RATE or DEFAULT_FRAME_RATE

pic_out_filename = convert_slide(pic_filename, 10, final_frame_rate)
workstage_out_filenames = [
    convert_slide(filename, 5, final_frame_rate) for filename in workstage_filenames
]

playlist_filename = f"{TEMP_FILE_PREFIX}playlist.txt"

with open(playlist_filename, 'w') as playlist:
    print("ffconcat version 1.0\n", file=playlist)
    print(f"file {pic_out_filename}", file=playlist)
    for filename in workstage_out_filenames:
        print(f"file {filename}", file=playlist)
    print(f"file {pic_out_filename}", file=playlist)

concat_filename = f"{TEMP_FILE_PREFIX}concat.mkv"

subprocess.run([
    "ffmpeg",
    "-y",
    "-f", "concat", "-i", playlist_filename,
    "-pix_fmt", "yuv420p",
    "-c:v", "ffv1",
    concat_filename
])

subprocess.run([
    "ffmpeg",
    "-y",
    "-i", concat_filename,
    "-pix_fmt", "yuv420p",
    "-c:v", "libx264",
    "-profile:v", "high",
    "-b:v", "10M",
    sys.argv[1]
])

# delete temp files
for filename in os.listdir('.'):
    if filename.startswith(TEMP_FILE_PREFIX):
        os.remove(filename)
 
