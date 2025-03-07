# Clipsfy - Video Clip Generator

Clipsfy is a powerful application that automatically generates engaging video clips from longer videos. It uses AI to analyze video content and extract the most interesting moments, making it perfect for content creators, podcasters, and video editors.

## Key Features

- 🎥 Automatic clip generation from long videos
- 🤖 AI-powered content analysis
- ⏱️ Precise timestamp detection
- 🎬 Multiple clip formats (9:16, 1:1, 16:9)
- 🕒 Customizable clip durations
- 📝 Automatic transcription and captioning
- 🌐 YouTube video processing
- 💾 Local video file support
- 🗂️ Organized clip management

## Installation

### Prerequisites
- Python 3.8+
- FFmpeg
- Whisper (AI transcription)
- Gemini API key

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/roberttsouza/Clipsfy.git
   cd clipsfy
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   Create a `.env` file in the project root with the following content:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_key
   GEMINI_API_KEY=your_gemini_api_key
   ```

   ⚠️ **Security Warning:** Never commit your `.env` file to version control. The file is already included in `.gitignore` to prevent accidental exposure of sensitive credentials. Always keep your API keys and secrets private.
# Clipsfy - Video Clip Generator

Clipsfy is a powerful application that automatically generates engaging video clips from longer videos. It uses AI to analyze video content and extract the most interesting moments, making it perfect for content creators, podcasters, and video editors.

## Key Features

- 🎥 Automatic clip generation from long videos
- 🤖 AI-powered content analysis
- ⏱️ Precise timestamp detection
- 🎬 Multiple clip formats (9:16, 1:1, 16:9)
- 🕒 Customizable clip durations
- 📝 Automatic transcription and captioning
- 🌐 YouTube video processing
- 💾 Local video file support
- 🗂️ Organized clip management

## Installation

### Prerequisites
- Python 3.8+
- FFmpeg
- Whisper (AI transcription)
- Gemini API key

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/roberttsouza/Clipsfy.git
   cd clipsfy
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   Create a `.env` file with the following content:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_key
   GEMINI_API_KEY=your_gemini_api_key
   ```

4. Install FFmpeg:
   - On macOS: `brew install ffmpeg`
   - On Ubuntu: `sudo apt install ffmpeg`
   - On Windows: Download from https://ffmpeg.org/

## Usage

### Web Interface
1. Start the Flask server:
   ```bash
   python app.py
   ```
2. Access the web interface at `http://localhost:5000`

### Processing Videos
1. Upload a local video file or provide a YouTube URL
2. Select clip format and duration
3. View and download generated clips

### API Endpoints
- `POST /process` - Process a video
  Parameters:
  - `video_url` (optional): YouTube URL
  - `video_file` (optional): Uploaded video file
  - `clip_format`: 9:16, 1:1, or 16:9
  - `clip_duration`: short, medium, or long

## Configuration

### Environment Variables
| Variable         | Description                          |
|------------------|--------------------------------------|
| SUPABASE_URL     | Supabase project URL                 |
| SUPABASE_KEY     | Supabase API key                     |
| GEMINI_API_KEY   | Gemini API key for AI analysis       |

### File Structure
```
clipsfy/
├── app.py            # Main application
├── requirements.txt  # Python dependencies
├── downloads/        # Temporary video storage
├── static/           # Static files (CSS, JS)
│   └── clips/        # Generated clips
├── templates/        # HTML templates
└── .env              # Environment variables
```

## Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a new branch (`git checkout -b feature/YourFeature`)
3. Commit your changes (`git commit -m 'Add some feature'`)
4. Push to the branch (`git push origin feature/YourFeature`)
5. Create a new Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
