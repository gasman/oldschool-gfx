# oldschool-gfx

A script for preparing videos for presentation in Revision's oldschool graphics compo. Given source images in any reasonable format, or a 1080p video capture of the entry, generates a video file suitable for the bigscreen, consisting of

* 10 seconds of the final image
* 5 seconds of each work stage
* 10 seconds of the final image again

## Installation

Check out this repo. Install [ffmpeg and ffprobe](https://ffmpeg.org/download.html) so that they're available on the default path. Install the python libraries [pillow](https://pillow.readthedocs.io/en/stable/) and [pyrecoil](https://pypi.org/project/pyrecoil/) into a Python 3 environment (anything above 3.6 should work, but the newer the better). pyrecoil is optional, but needed for source files in .iff or .lbm format.

## Usage

Unpack each entry into its own subfolder (conventionally named `0123-mygreatpicture` with the entry number), and rename input files with prefixes as follows:

* P-my_great_picture.mp4 for the final image
* W1-stage1.png, W2-stage2.png etc for the workstages

Each input file can be either a video (in 1920x1080) or an image (in any resolution).

Then run: `./render.py path/to/folder`

Multiple paths are accepted.

This will output a video `00-0123-mygreatpicture.mp4` with the following properties:

* 1080p, h264 high profile
* same framerate as the source video, or 25fps if all sources are images
* source images scaled with integer nearest-neighbour rescaling if there's an integer multiple that covers >=80% of the target width or height, or the Hamming algorithm scaled to full width or height if not.
