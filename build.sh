#!/bin/bash
apt-get update && apt-get install -y ffmpeg
pip install --no-cache-dir -r requirements.txt
pip install yt-dlp
