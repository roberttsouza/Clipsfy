from flask import Flask, render_template, request, jsonify
import os
import subprocess
import yt_dlp
import whisper
import google.generativeai as genai
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Inicializar o Flask
app = Flask(__name__)

# Pasta para salvar os vídeos baixados
DOWNLOADS_DIR = "downloads"
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)

# Função para baixar vídeos do YouTube usando yt-dlp
def download_youtube_video(video_url, output_path="downloads"):
    try:
        print(f"Baixando vídeo: {video_url}")  # Log
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',  # Melhor qualidade disponível
            'outtmpl': f'{output_path}/%(title)s.%(ext)s',  # Nome do arquivo de saída
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_title = info.get("title", "Título Indisponível")
            video_path = ydl.prepare_filename(info)
            print(f"Vídeo baixado: {video_path}")  # Log
            return video_title, video_path
    except Exception as e:
        print(f"Erro ao baixar vídeo: {str(e)}")  # Log
        return None, None

# Função para extrair áudio usando FFmpeg
def extract_audio(video_path, audio_output_path="audio.mp3"):
    try:
        print(f"Extraindo áudio de: {video_path}")  # Log
        subprocess.run([
            "ffmpeg", "-i", video_path, "-q:a", "0", "-map", "a", audio_output_path
        ], check=True)
        print(f"Áudio extraído: {audio_output_path}")  # Log
        return audio_output_path
    except Exception as e:
        print(f"Erro ao extrair áudio: {e}")  # Log
        return None

# Função para transcrever o áudio usando Whisper
def transcribe_audio(audio_path):
    try:
        print(f"Transcrevendo áudio: {audio_path}")  # Log
        model = whisper.load_model("base")  # Modelo "base" é suficiente para a maioria dos casos
        result = model.transcribe(audio_path)
        transcription = result["text"]
        print(f"Transcrição concluída: {transcription[:100]}...")  # Log apenas os primeiros 100 caracteres
        return transcription
    except Exception as e:
        print(f"Erro ao transcrever áudio: {e}")  # Log
        return None

# Função para analisar a transcrição com a Gemini API usando google-generativeai
def analyze_transcription(transcription):
    api_key = os.getenv("GEMINI_API_KEY")  # Buscar a chave de API do .env
    if not api_key:
        print("Erro: Chave de API da Gemini não encontrada.")
        return None
    
    try:
        # Configurar a Gemini API
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        
        # Prompt aprimorado com categoria de política
        prompt = f"""
        Você é um assistente especializado em análise de vídeos. Sua tarefa é analisar a seguinte transcrição de um vídeo e identificar os melhores momentos, classificando-os em categorias específicas. Retorne os momentos identificados juntamente com seus timestamps aproximados.

        ### Categorias de Momentos:
        1. **Momentos Emocionantes ou Impactantes**:
           - Eventos que causam forte reação emocional, como discursos inspiradores, cenas dramáticas ou revelações importantes.
           
        2. **Momentos Engraçados ou Divertidos**:
           - Piadas, situações cômicas ou interações que provocam risadas.
           
        3. **Informações Importantes ou Insights Úteis**:
           - Dados relevantes, explicações técnicas, conselhos práticos ou insights que agreguem valor ao conteúdo.
           
        4. **Momentos Surpreendentes ou Inesperados**:
           - Eventos inesperados, reviravoltas ou acontecimentos fora do comum.

        5. **Momentos Políticos Relevantes**:
           - Discussões sobre políticas públicas, decisões governamentais, discursos de líderes políticos, debates ou análises críticas sobre questões políticas.
           - Exemplos: Propostas de lei, declarações controversas, promessas eleitorais ou discussões sobre impactos sociais/econômicos.

        ### Formato de Resposta:
        Retorne os momentos identificados no seguinte formato:
        - Categoria: [Nome da Categoria]
          - Timestamp: [HH:MM:SS - HH:MM:SS]
          - Descrição: [Breve descrição do momento]

        ### Transcrição do Vídeo:
        {transcription}

        Por favor, analise a transcrição acima e retorne os momentos mais relevantes nas categorias especificadas.
        """
        
        # Gerar resposta
        response = model.generate_content(prompt)
        analysis = response.text
        print(f"Análise concluída: {analysis[:100]}...")  # Log
        return analysis
    except Exception as e:
        print(f"Erro ao chamar a Gemini API: {str(e)}")
        return None

# Função para obter a duração total do vídeo
def get_video_duration(video_path):
    """
    Obtém a duração total do vídeo em segundos.
    
    :param video_path: Caminho do vídeo.
    :return: Duração total do vídeo em segundos.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-i", video_path, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        duration = float(result.stdout.decode("utf-8").strip())
        return duration
    except Exception as e:
        print(f"Erro ao obter duração do vídeo: {str(e)}")
        return None

# Função para gerar clipes com base nos timestamps
def generate_clips(video_path, analysis, clip_format, clip_duration):
    """
    Gera clipes com base nos timestamps identificados na análise, respeitando o formato e a duração escolhidos.
    
    :param video_path: Caminho do vídeo original.
    :param analysis: Texto da análise contendo os timestamps.
    :param clip_format: Formato do clipe ("9:16", "1:1", "16:9").
    :param clip_duration: Duração do clipe ("<30s", "30s-59s", etc.).
    :return: Lista de caminhos para os clipes gerados.
    """
    clips = []
    try:
        # Mapear o formato para as dimensões do FFmpeg
        format_mapping = {
            "9:16": "720x1280",  # Vertical
            "1:1": "1080x1080",  # Quadrado
            "16:9": "1920x1080"  # Widescreen
        }
        resolution = format_mapping.get(clip_format, "1920x1080")  # Padrão: 16:9

        # Mapear a duração para um intervalo mínimo e máximo em segundos
        duration_mapping = {
            "<30s": (1, 30),        # Entre 1 segundo e 30 segundos
            "30s-59s": (30, 60),    # Entre 30 segundos e 1 minuto
            "90s-3m": (90, 180),    # Entre 1 minuto e 30 segundos e 3 minutos
            "3m-5m": (180, 300),    # Entre 3 minutos e 5 minutos
            "5m-10m": (300, 600),   # Entre 5 minutos e 10 minutos
            "10m-15m": (600, 900),  # Entre 10 minutos e 15 minutos
            "15m-20m": (900, 1200), # Entre 15 minutos e 20 minutos
            "20m-25m": (1200, 1500) # Entre 20 minutos e 25 minutos
        }
        min_duration, max_duration = duration_mapping.get(clip_duration, (30, 60))  # Padrão: 30 a 60 segundos

        # Obter a duração total do vídeo
        total_duration = get_video_duration(video_path)
        if not total_duration:
            print("Erro: Não foi possível obter a duração do vídeo.")
            return []

        # Exemplo de parse simples para extrair timestamps e descrições
        lines = analysis.split("\n")
        for i, line in enumerate(lines):
            if "Timestamp:" in line:
                # Extrair o intervalo de tempo
                timestamp_range = line.split("Timestamp:")[1].strip()
                
                # Remover caracteres indesejados (como "**")
                timestamp_range = timestamp_range.replace("**", "").strip()
                
                # Dividir o intervalo em start_time e end_time
                try:
                    start_time, end_time = timestamp_range.split("-")
                    start_time = start_time.strip()
                    end_time = end_time.strip()
                except ValueError:
                    print(f"Erro ao dividir timestamp: {timestamp_range}")
                    continue
                
                # Converter timestamps para segundos
                start_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time.split(":"))))
                end_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(end_time.split(":"))))
                
                # Validar os timestamps
                if start_seconds >= end_seconds or start_seconds >= total_duration:
                    print(f"Timestamp inválido: start={start_time}, end={end_time}")
                    continue
                
                # Ajustar o clipe para respeitar a duração mínima e máxima
                clip_length = end_seconds - start_seconds
                if clip_length < min_duration:
                    # Estender o clipe para atingir a duração mínima
                    end_seconds = start_seconds + min_duration
                elif clip_length > max_duration:
                    # Truncar o clipe para respeitar a duração máxima
                    end_seconds = start_seconds + max_duration
                
                # Garantir que o end_time não exceda a duração total do vídeo
                if end_seconds > total_duration:
                    end_seconds = total_duration
                    end_time = f"{end_seconds // 3600:02}:{(end_seconds % 3600) // 60:02}:{end_seconds % 60:02}"
                else:
                    end_time = f"{end_seconds // 3600:02}:{(end_seconds % 3600) // 60:02}:{end_seconds % 60:02}"
                
                # Nome do arquivo do clipe
                clip_path = f"{DOWNLOADS_DIR}/clip_{i + 1}.mp4"
                
                # Comando FFmpeg para cortar e redimensionar o vídeo
                subprocess.run([
                    "ffmpeg", "-i", video_path,
                    "-ss", start_time,
                    "-to", end_time,
                    "-vf", f"scale={resolution},setsar=1:1",  # Redimensiona e corrige a proporção
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    "-c:a", "aac",
                    clip_path
                ], check=True)
                
                clips.append(clip_path)
        
        print(f"Clipes gerados: {clips}")  # Log
        return clips
    except Exception as e:
        print(f"Erro ao gerar clipes: {str(e)}")  # Log
        return []

# Rota principal (página inicial)
@app.route("/")
def index():
    return render_template("index.html")

# Rota para processar o vídeo
@app.route("/process", methods=["POST"])
def process_video():
    video_url = request.form.get("video_url")
    clip_format = request.form.get("clip_format")  # Novo campo: formato do clipe
    clip_duration = request.form.get("clip_duration")  # Novo campo: duração do clipe
    
    if not video_url:
        return jsonify({"error": "URL do vídeo não fornecida"}), 400

    try:
        print(f"Processando vídeo: {video_url}")  # Log
        
        # Baixar o vídeo usando yt-dlp
        video_title, video_path = download_youtube_video(video_url)
        if not video_path:
            return jsonify({"error": "Falha ao baixar vídeo"}), 500
        
        # Extrair áudio
        audio_path = extract_audio(video_path, audio_output_path=f"{DOWNLOADS_DIR}/audio.mp3")
        if not audio_path:
            return jsonify({"error": "Falha ao extrair áudio"}), 500
        
        # Transcrever o áudio
        transcription = transcribe_audio(audio_path)
        if not transcription:
            return jsonify({"error": "Falha ao transcrever áudio"}), 500
        
        # Analisar a transcrição com a Gemini API
        analysis = analyze_transcription(transcription)
        if not analysis:
            return jsonify({"error": "Falha ao analisar transcrição"}), 500
        
        # Gerar clipes com base na análise, formato e duração
        clips = generate_clips(video_path, analysis, clip_format, clip_duration)
        
        # Retornar o caminho do vídeo, áudio, transcrição, análise e clipes
        return jsonify({
            "message": "Vídeo, áudio, transcrição, análise e clipes processados com sucesso!",
            "video_title": video_title,
            "video_path": video_path,
            "audio_path": audio_path,
            "transcription": transcription,
            "analysis": analysis,
            "clips": clips
        })
    except Exception as e:
        print(f"Erro no servidor: {str(e)}")  # Log
        return jsonify({"error": str(e)}), 500

# Executar o servidor Flask
if __name__ == "__main__":
    app.run(debug=True)