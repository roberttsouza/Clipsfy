#!/bin/bash
apt-get update && apt-get install -y ffmpeg
pip install -r requirements.txt
pip install yt-dlp
