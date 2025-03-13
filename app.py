from flask import Flask, render_template, request, jsonify, redirect, url_for
from supabase import create_client, Client
import os
import subprocess
import yt_dlp
import whisper
import google.generativeai as genai
from dotenv import load_dotenv
import re
import glob
import shutil

# Carregar variáveis de ambiente
load_dotenv()

# Inicializar o Flask
app = Flask(__name__, static_url_path='', static_folder='static')

# Configurar caminho para templates
app.template_folder = 'templates'

# Pasta para salvar os vídeos baixados
DOWNLOADS_DIR = "downloads"
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)

# Configurações do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Função para registrar um novo usuário
def register_user(username, email, password_hash):
    response = supabase.table("users").insert({
        "username": username,
        "email": email,
        "password_hash": password_hash
    }).execute()
    return response.data

# Função para autenticar um usuário
def authenticate_user(email, password_hash):
    response = supabase.table("users").select("*").eq("email", email).eq("password_hash", password_hash).execute()
    return response.data

# Função para salvar clipes no banco de dados
def save_clip(user_id, clip_url, transcription, title):
    response = supabase.table("clips").insert({
        "user_id": user_id,
        "clip_url": clip_url,
        "transcription": transcription,
        "title": title
    }).execute()
    return response.data

# Função para limpar a pasta de downloads
def clean_downloads_folder():
    try:
        for file in os.listdir(DOWNLOADS_DIR):
            file_path = os.path.join(DOWNLOADS_DIR, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        print("Pasta de downloads limpa com sucesso")
        return True
    except Exception as e:
        print(f"Erro ao limpar pasta de downloads: {e}")
        return False

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

# Função para processar um arquivo de vídeo local
def process_local_video(file):
    try:
        # Verificar se o arquivo é um vídeo
        allowed_extensions = {'mp4', 'mov', 'avi', 'mkv', 'webm'}
        if not file.filename.split('.')[-1].lower() in allowed_extensions:
            print(f"Arquivo não é um vídeo: {file.filename}")
            return None, None
        
        # Salvar o arquivo temporariamente
        video_path = os.path.join(DOWNLOADS_DIR, file.filename)
        file.save(video_path)
        print(f"Vídeo salvo localmente: {video_path}")
        
        return file.filename, video_path
    except Exception as e:
        print(f"Erro ao processar vídeo local: {str(e)}")
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
import torch
import cv2
import numpy as np
import face_recognition
from PIL import Image

def extract_faces_from_video(video_path, num_faces=2):
    """Extrai frames com rostos de um vídeo com expressões distintas"""
    try:
        # Abrir o vídeo
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Erro ao abrir o vídeo: {video_path}")
            return None

        face_frames = []
        frame_count = 0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_interval = max(30, total_frames // 100)  # Ajustar intervalo baseado no tamanho do vídeo
        
        # Dicionário para armazenar expressões faciais
        expressions = {
            'neutral': False,
            'happy': False,
            'surprised': False,
            'angry': False
        }
        
        while len(face_frames) < num_faces:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Processar a cada frame_interval frames
            if frame_count % frame_interval == 0:
                # Converter BGR (OpenCV) para RGB (face_recognition)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Detectar rostos e encodings
                face_locations = face_recognition.face_locations(rgb_frame)
                face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                
                for i, (top, right, bottom, left) in enumerate(face_locations):
                    # Verificar se o rosto não está muito próximo
                    face_height = bottom - top
                    face_width = right - left
                    if face_height < frame.shape[0] * 0.3 and face_width < frame.shape[1] * 0.3:
                        # Verificar se o rosto é diferente dos já selecionados
                        is_unique = True
                        for existing_encoding in face_frames:
                            if face_recognition.compare_faces([existing_encoding['encoding']], face_encodings[i])[0]:
                                is_unique = False
                                break
                                
                        if is_unique:
                            # Detectar expressão facial
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                            
                            for (x, y, w, h) in faces:
                                # Analisar expressão facial
                                roi_gray = gray[y:y+h, x:x+w]
                                roi_color = frame[y:y+h, x:x+w]
                                
                                # Detectar sorriso
                                smile = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_smile.xml')
                                smiles = smile.detectMultiScale(roi_gray, 1.8, 20)
                                
                                # Detectar olhos abertos
                                eye = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
                                eyes = eye.detectMultiScale(roi_gray, 1.1, 4)
                                
                                # Classificar expressão
                                if len(smiles) > 0:
                                    expression = 'happy'
                                elif len(eyes) == 0:
                                    expression = 'angry'
                                elif len(eyes) > 1:
                                    expression = 'surprised'
                                else:
                                    expression = 'neutral'
                                
                                # Selecionar rosto se a expressão for nova
                                if not expressions[expression]:
                                    # Adicionar margem de 20% ao redor do rosto
                                    margin = int(max(face_height, face_width) * 0.2)
                                    top = max(0, top - margin)
                                    bottom = min(frame.shape[0], bottom + margin)
                                    left = max(0, left - margin)
                                    right = min(frame.shape[1], right + margin)
                                    
                                    # Recortar e armazenar o frame com o encoding
                                    face_frame = {
                                        'frame': frame[top:bottom, left:right],
                                        'encoding': face_encodings[i],
                                        'expression': expression
                                    }
                                    face_frames.append(face_frame)
                                    expressions[expression] = True
                                    break
                                    
            frame_count += 1
            
            # Se todas as expressões foram capturadas, parar
            if all(expressions.values()):
                break
                
        cap.release()
        return face_frames
        
    except Exception as e:
        print(f"Erro ao extrair rostos do vídeo: {e}")
        return None

def create_thumbnail(face_frames, output_path, thumbnail_height=300):
    """Cria uma thumbnail a partir dos frames com rostos"""
    try:
        if not face_frames or len(face_frames) < 2:
            return False
            
        # Redimensionar as imagens para mesma altura mantendo proporção
        resized_frames = []
        for face_frame in face_frames:
            frame = face_frame['frame']
            height, width = frame.shape[:2]
            aspect_ratio = width / height
            new_width = int(thumbnail_height * aspect_ratio)
            resized_frame = cv2.resize(frame, (new_width, thumbnail_height))
            resized_frames.append(resized_frame)
            
        # Combinar as imagens horizontalmente
        thumbnail = np.hstack(resized_frames)
        
        # Salvar a thumbnail
        cv2.imwrite(output_path, thumbnail)
        return True
        
    except Exception as e:
        print(f"Erro ao criar thumbnail: {e}")
        return False

def transcribe_audio(audio_path):
    try:
        print(f"Transcrevendo áudio: {audio_path}")  # Log
        
        # Verify audio file exists and is not empty
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            print(f"Arquivo de áudio inválido ou vazio: {audio_path}")
            return None

        # Determine the device to use
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Usando dispositivo: {device}")

        # Load the Whisper model
        model = whisper.load_model("base", device=device)
        
        # Transcribe with detailed error handling
        result = model.transcribe(audio_path)
        
        if not result or "text" not in result:
            print("Transcrição falhou: resultado inválido do Whisper")
            return None
            
        transcription = result["text"]
        
        if not transcription or len(transcription.strip()) == 0:
            print("Transcrição falhou: texto vazio")
            return None
            
        print(f"Transcrição concluída: {transcription[:100]}...")  # Log apenas os primeiros 100 caracteres
        return transcription
        
    except Exception as e:
        print(f"Erro ao transcrever áudio: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# Função para analisar a transcrição com a Gemini API usando google-generativeai
def analyze_transcription(transcription):
    api_key = os.getenv("GEMINI_API_KEY")  # Buscar a chave de API do .env
    if not api_key:
        print("Erro: Chave de API da Gemini não encontrada.")
        return None
    
    try:
        # Validate transcription
        if not transcription or len(transcription.strip()) == 0:
            print("Erro: Transcrição vazia ou inválida")
            return None

        # Configurar a Gemini API
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Prompt otimizado para vídeos longos
        prompt = f"""Você é um assistente especializado em análise de vídeos longos e engajamento. Sua tarefa is to analyze the transcription systematically and identify the best moments for clips, ensuring multiple relevant clips are generated.

### Analysis Strategy:
1. **Stratified Analysis**  
   - Divide the video into temporal segments (e.g., every 10 minutes)  
   - Identify the most relevant moments in each segment  

2. **Selection Criteria:**  
   - **Emotional and Impactful Moments**  
     - Inspiring speeches, personal stories, or significant revelations  
   - **Funny and Viral Moments**  
     - Jokes, comedic interactions, or spontaneous remarks with high sharing potential  
   - **Valuable Information and Useful Insights**  
     - Technical explanations, curiosities, practical tips, or solid arguments  
   - **Tense or Surprising Moments**  
     - Plot twists, heated debates, controversial statements, or unexpected events  
   - **Catchphrases and Powerful Hooks**  
     - Short, impactful statements that grab attention  

3. **Minimum Number of Clips:**  
   - Short videos (<30 min): 1-2 clips  
   - Medium videos (30-60 min): 3-5 clips  
   - Long videos (>60 min): 5-10 clips  

### **IMPORTANT:**  
- **Always return multiple clips** distributed throughout the video  
- Prioritize moments that represent different aspects of the content  
- If there are no exceptional moments, select coherent and informative segments  
- Never return an empty response  

### **Response Format:**  
For each identified moment, return in the following format:

Category: [Category Name]
Timestamp: [HH:MM:SS - HH:MM:SS]
Description: [Concise summary of the moment]
Highlight: ["Most striking phrase or dialogue from the segment"]

**Video Transcription:**  
{transcription}

Please systematically analyze the transcription and provide the best moments distributed throughout the video. **Ensure there are multiple relevant clips, especially for long videos.**
        """
        
        # Generate response with error handling
        response = model.generate_content(prompt)
        
        if not response or not response.text:
            print("Erro: Resposta inválida da Gemini API")
            return None
            
        analysis = response.text
        
        if not analysis or len(analysis.strip()) == 0:
            print("Erro: Análise vazia")
            return None
            
        print(f"Análise concluída: {analysis[:100]}...")  # Log
        return analysis
        
    except Exception as e:
        print(f"Erro ao chamar a Gemini API: {str(e)}")
        import traceback
        traceback.print_exc()
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
def generate_clips(video_path, analysis, clip_format, clip_duration, full_transcription):
    """
    Gera clipes com base nos timestamps identificados na análise, respeitando o formato e a duração escolhidos.
    
    :param video_path: Caminho do vídeo original.
    :param analysis: Texto da análise contendo os timestamps.
    :param clip_format: Formato do clipe ("9:16", "1:1", "16:9").
    :param clip_duration: Duração do clipe ("short", "medium", "long").
    :param full_transcription: Transcrição completa do vídeo.
    :return: Lista de dicionários contendo informações dos clipes gerados.
    """
    clips_info = []
    total_duration = get_video_duration(video_path)
    if not total_duration:
        print("Erro: Não foi possível obter a duração do vídeo.")
        return []

    # Mapeamento de formatos para resoluções
    format_to_resolution = {
        "9:16": "720x1280",  # Vertical
        "1:1": "1080x1080",  # Quadrado
        "16:9": "1920x1080"  # Horizontal
    }
    resolution = format_to_resolution.get(clip_format, "1920x1080")  # Padrão para 16:9

    # Mapeamento de durações para segundos
    duration_mapping = {
        "<30s": (1, 30),       # Entre 1 segundo e 30 segundos
        "30s-59s": (30, 60),   # Entre 30 segundos e 1 minuto
        "90s-3m": (90, 180),   # Entre 1 minuto e 30 segundos e 3 minutos
        "3m-5m": (180, 300),   # Entre 3 minutos e 5 minutos
        "5m-10m": (300, 600),  # Entre 5 minutos e 10 minutos
        "10m-15m": (600, 900), # Entre 10 minutos e 15 minutos
        "15m-20m": (900, 1200),# Entre 15 minutos e 20 minutos
        "20m-25m": (1200, 1500) # Entre 20 minutos e 25 minutos
    }
    min_duration, max_duration = duration_mapping.get(clip_duration, (180, 300))  # Padrão para 3-5 minutos

    # Extrair timestamps da análise (formato mais flexível)
    pattern = r"Timestamp:\s*(\d{1,2}:\d{2}:\d{2})\s*-\s*(\d{1,2}:\d{2}:\d{2})"
    matches = re.findall(pattern, analysis)
    print(f"Timestamps encontrados (regex): {matches}")  # Log dos timestamps encontrados

    # Tentar um formato alternativo caso o primeiro não funcione
    if not matches:
        pattern = r"(\d{1,2}:\d{2}:\d{2})\s*-\s*(\d{1,2}:\d{2}:\d{2})"
        matches = re.findall(pattern, analysis)
        print(f"Timestamps encontrados (alternativo): {matches}")

    # Lista para armazenar os clipes com suas informações
    clip_segments = []

    for i, (start_time, end_time) in enumerate(matches):
        try:
            # Converter timestamps para segundos
            start_seconds = sum(int(x) * 60 ** (2 - i) for i, x in enumerate(start_time.split(":")))
            end_seconds = sum(int(x) * 60 ** (2 - i) for i, x in enumerate(end_time.split(":")))

            print(f"Start time: {start_time}, Start seconds: {start_seconds}")  # Log
            print(f"End time: {end_time}, End seconds: {end_seconds}")  # Log

            # Validar timestamps
            if start_seconds >= end_seconds or start_seconds >= total_duration:
                print(f"Timestamp inválido: start={start_time}, end={end_time}")
                continue

            # Ajustar o clipe para respeitar a duração máxima
            clip_length = end_seconds - start_seconds
            # Ajustar o clipe para respeitar a duração mínima e máxima
            if clip_length < min_duration:
                end_seconds = min(start_seconds + min_duration, total_duration)
                clip_length = end_seconds - start_seconds
            if clip_length > max_duration:
                end_seconds = start_seconds + max_duration

            # Garantir que o end_time não exceda a duração total do vídeo
            if end_seconds > total_duration:
                end_seconds = total_duration
                start_seconds = max(0, end_seconds - min_duration) # Ajustar start_seconds se necessário
                
            clip_length = end_seconds - start_seconds

            # Formatar os timestamps corretamente
            start_time_formatted = f"{int(start_seconds // 3600):02}:{int((start_seconds % 3600) // 60):02}:{int(start_seconds % 60):02}"
            end_time_formatted = f"{int(end_seconds // 3600):02}:{int((end_seconds % 3600) // 60):02}:{int(end_seconds % 60):02}"

            # Extrair dados para criar títulos e descrições
            categoria = ""
            descricao = ""
            trecho_destaque = ""
            try:
                # Pesquisar o contexto antes do timestamp atual
                current_section = analysis.split(f"Timestamp: {start_time} - {end_time}")[0]
                last_category_index = current_section.rfind("Categoria:")
                if last_category_index != -1:
                    section_context = current_section[last_category_index:]
                    
                    # Extrair categoria
                    categoria_pattern = r"Categoria:\s*([^\n]+)"
                    categoria_match = re.search(categoria_pattern, section_context)
                    if categoria_match:
                        categoria = categoria_match.group(1).strip()
                    
                    # Extrair descrição
                    descricao_pattern = r"Descrição:\s*([^\n]+)"
                    descricao_match = re.search(descricao_pattern, section_context)
                    if descricao_match:
                        descricao = descricao_match.group(1).strip()
                    
                    # Extrair trecho de destaque
                    trecho_pattern = r"Trecho de Destaque:\s*\"([^\"]+)\""
                    trecho_match = re.search(trecho_pattern, section_context)
                    if trecho_match:
                        trecho_destaque = trecho_match.group(1).strip()
            except Exception as e:
                print(f"Erro ao extrair metadados do clipe: {e}")

            # Adicionar o segmento à lista
            clip_segments.append({
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "start_time_formatted": start_time_formatted,
                "end_time_formatted": end_time_formatted,
                "categoria": categoria,
                "descricao": descricao,
                "trecho_destaque": trecho_destaque
            })
        except Exception as e:
            print(f"Erro ao processar clipe {i + 1}: {str(e)}")
            import traceback
            traceback.print_exc()

    # Ordenar os segmentos por categoria (priorizando categorias importantes)
    clip_segments.sort(key=lambda x: (x["categoria"] != "Informações Valiosas e Insights Úteis" and 
                                      x["categoria"] != "Momentos Emocionantes e Impactantes", 
                                      x["start_seconds"]))

    # Gerar os clipes a partir dos segmentos, evitando sobreposição
    last_end_seconds = 0
    try:
        for i, segment in enumerate(clip_segments):
            start_seconds = segment["start_seconds"]
            end_seconds = segment["end_seconds"]
            start_time_formatted = segment["start_time_formatted"]
            end_time_formatted = segment["end_time_formatted"]

            # Verificar se o segmento se sobrepõe ao clipe anterior
            if start_seconds < last_end_seconds:
                print(f"Segmento {i + 1} sobrepõe o clipe anterior, ignorando.")
                continue

            # Pasta para salvar os clipes
            CLIPS_DIR = "static/clips"
            if not os.path.exists(CLIPS_DIR):
                os.makedirs(CLIPS_DIR)

            # Criar título para o clipe
            clip_title = ""
            if segment.get("trecho_destaque"):
                # Usar o trecho de destaque se disponível
                clip_title = segment["trecho_destaque"]
            elif segment.get("descricao"):
                # Usar a descrição se o trecho não estiver disponível
                clip_title = segment["descricao"]
            else:
                # Usar a categoria como fallback
                clip_title = segment.get("categoria", f"Momento Interessante {i + 1}")
            
            # Criar nome seguro para arquivo
            safe_title = re.sub(r'[\\/*?:"<>|]', "", clip_title).strip()
            safe_title = re.sub(r'\s+', "_", safe_title)  # Substituir espaços por underscores
            import random
            unique_id = hex(random.randint(0, 2**32-1))[2:].zfill(8)  # Gera um hexadecimal de 8 caracteres

            # Nome do arquivo do clipe com título viral
            clip_filename = f"{safe_title}_({i + 1})_{unique_id}.mp4"
            clip_path = os.path.join(CLIPS_DIR, clip_filename)

            # Extrair transcrição específica para este clipe
            clip_transcription = ""
            try:
                # Encontrar a transcrição correspondente ao intervalo de tempo do clipe
                words_with_timestamps = []
                
                # Se tivermos a transcrição completa com timestamps (formato avançado do Whisper)
                if hasattr(full_transcription, 'segments'):
                    for segment in full_transcription.segments:
                        if segment.start >= start_seconds and segment.end <= end_seconds:
                            words_with_timestamps.append(segment.text)
                    clip_transcription = " ".join(words_with_timestamps)
                else:
                    # Caso contrário, usar o trecho de destaque como transcrição
                    clip_transcription = segment.get("trecho_destaque", "")
                
                if not clip_transcription or len(clip_transcription) < 10:
                    # Se a transcrição específica não for adequada, usar o texto completo
                    clip_transcription = full_transcription
            except Exception as e:
                print(f"Erro ao extrair transcrição para o clipe: {e}")
                clip_transcription = full_transcription

            # Comando FFmpeg para cortar e redimensionar o vídeo
            ffmpeg_command = [
                "ffmpeg", "-i", video_path,
                "-ss", start_time_formatted,
                "-to", end_time_formatted,
                "-vf", f"scale={resolution},setsar=1:1",  # Redimensiona e corrige a proporção
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                clip_path
            ]
            print(f"Comando FFmpeg: {' '.join(ffmpeg_command)}")  # Log do comando

            try:
                subprocess.run(ffmpeg_command, check=True)
                
                # Salvar a transcrição em um arquivo de texto
                transcription_filename = clip_path.replace(".mp4", ".txt")
                with open(transcription_filename, "w", encoding="utf-8") as f:
                    f.write(clip_transcription)
                
                # Gerar thumbnail para o clipe
                thumbnail_path = clip_path.replace(".mp4", "_thumbnail.jpg")
                face_frames = extract_faces_from_video(clip_path)
                if face_frames:
                    create_thumbnail(face_frames, thumbnail_path)
                
                # Adicionar informações do clipe à lista de retorno
                clips_info.append({
                    "path": clip_path,
                    "url": f"/static/clips/{os.path.basename(clip_path)}",
                    "title": clip_title,
                    "categoria": segment.get("categoria", ""),
                    "transcription": clip_transcription,
                    "duration": end_seconds - start_seconds,
                    "thumbnail": f"/static/clips/{os.path.basename(thumbnail_path)}" if os.path.exists(thumbnail_path) else None
                })
                
                last_end_seconds = end_seconds
                
            except subprocess.CalledProcessError as e:
                print(f"Erro no FFmpeg: {e}")
                print(f"Código de retorno: {e.returncode}")
                print(f"Saída: {e.output}")
                continue

    except Exception as e:
        print(f"Erro ao processar clipes: {str(e)}")
        print(f"Detalhes do erro: {str(e)}")
        import traceback
        traceback.print_exc()

    print(f"Clipes gerados: {len(clips_info)}")  # Log
    return clips_info

# Rota principal (página inicial)
@app.route("/")
def index():
    # Listar todos os arquivos na pasta de clipes
    clips_dir = os.path.join(app.static_folder, "clips")
    if not os.path.exists(clips_dir):
        os.makedirs(clips_dir)
        
    clip_files = glob.glob(os.path.join(clips_dir, "*.mp4"))

    # Criar uma lista para armazenar os dados dos clipes
    clips_data = []
    for clip_file in clip_files:
        clip_url = f"/static/clips/{os.path.basename(clip_file)}"
        file_name = os.path.basename(clip_file)
        
        # Extrair título do nome do arquivo
        title = file_name.replace(".mp4", "").replace("_", " ")
        # Remover o número de sequência no final do título (ex: "_1")
        title = re.sub(r'_\d+$', '', title)
        # Formatar o título para exibição
        title = " ".join(word.capitalize() for word in title.split())
        
        # Buscar transcrição correspondente
        transcription_file = clip_file.replace(".mp4", ".txt")
        try:
            with open(transcription_file, "r", encoding="utf-8") as f:
                transcription = f.read()
        except FileNotFoundError:
            transcription = "Transcrição não disponível"
        
            # Verificar se existe thumbnail para o clipe
            thumbnail_path = clip_file.replace(".mp4", "_thumbnail.jpg")
            thumbnail_url = f"/static/clips/{os.path.basename(thumbnail_path)}" if os.path.exists(thumbnail_path) else None
            
            clips_data.append({
                "url": clip_url, 
                "title": title,
                "transcription": transcription,
                "thumbnail": thumbnail_url
            })

    # Ordenar clips por nome
    clips_data.sort(key=lambda x: x["title"])

    return render_template("index.html", clips_data=clips_data)

# Rota para processar o vídeo
@app.route("/process", methods=["POST"])
def process_video():
    print("Iniciando processamento do vídeo")  # Log
    
    try:
        # Obter e validar dados do formulário
        data = request.get_json() if request.is_json else request.form
        files = request.files
        
        video_url = data.get("video_url")
        uploaded_file = files.get("video_file")
        clip_format = data.get("clip_format", "16:9")  # Default to 16:9
        clip_duration = data.get("clip_duration", "3m-5m")  # Default to 3-5 minutes
        user_id = data.get("user_id", "anônimo")  # Default to anonymous

        # Validate required parameters
        if not video_url and not uploaded_file:
            print("Nenhuma fonte de vídeo fornecida")
            return jsonify({
                "status": "error",
                "message": "Por favor, forneça um link do YouTube ou faça upload de um arquivo de vídeo"
            }), 400

        # Validate clip format
        valid_formats = ["9:16", "1:1", "16:9"]
        if clip_format not in valid_formats:
            print(f"Formato de clipe inválido: {clip_format}")
            return jsonify({
                "status": "error", 
                "message": f"Formato de clipe inválido. Use um dos seguintes: {', '.join(valid_formats)}"
            }), 400

        # Validate clip duration
        valid_durations = ["<30s", "30s-59s", "90s-3m", "3m-5m", "5m-10m", "10m-15m", "15m-20m", "20m-25m"]
        if clip_duration not in valid_durations:
            print(f"Duração de clipe inválida: {clip_duration}")
            return jsonify({
                "status": "error",
                "message": f"Duração de clipe inválida. Use um dos seguintes: {', '.join(valid_durations)}"
            }), 400

        try:
            # Limpar pasta de downloads antes de processar novo vídeo
            if not clean_downloads_folder():
                print("Falha ao limpar pasta de downloads")
                return jsonify({
                    "status": "error",
                    "message": "Falha ao limpar pasta de downloads"
                }), 500

            # Processar vídeo do YouTube ou vídeo carregado
            if video_url:
                print(f"Processando vídeo do YouTube: {video_url}")
                video_title, video_path = download_youtube_video(video_url)
            else:
                print(f"Processando vídeo carregado: {uploaded_file.filename}")
                video_title, video_path = process_local_video(uploaded_file)
                
            if not video_path:
                print("Falha ao processar o vídeo")
                return jsonify({
                    "status": "error",
                    "message": "Falha ao processar o vídeo"
                }), 500
            print(f"Vídeo processado com sucesso: {video_path}")

            # Extrair áudio
            audio_path = extract_audio(video_path, audio_output_path=f"{DOWNLOADS_DIR}/audio.mp3")
            if not audio_path:
                print("Falha ao extrair áudio")
                return jsonify({
                    "status": "error",
                    "message": "Falha ao extrair áudio"
                }), 500
            print(f"Áudio extraído com sucesso: {audio_path}")

            # Transcrever o áudio
            print("Iniciando transcrição do áudio...")
            transcription = transcribe_audio(audio_path)
            if not transcription:
                print("Falha ao transcrever áudio: resultado vazio")
                return jsonify({
                    "status": "error",
                    "message": "Falha ao transcrever áudio: resultado vazio"
                }), 500
            print(f"Transcrição concluída com sucesso: {transcription[:100]}...")
            print(f"Tamanho da transcrição: {len(transcription)} caracteres")

            # Analisar a transcrição com a Gemini API
            print("Iniciando análise da transcrição...")
            analysis = analyze_transcription(transcription)
            if not analysis:
                print("Falha ao analisar transcrição: resultado vazio")
                return jsonify({
                    "status": "error",
                    "message": "Falha ao analisar transcrição: resultado vazio"
                }), 500
            print(f"Análise concluída com sucesso: {analysis[:100]}...")
            print(f"Tamanho da análise: {len(analysis)} caracteres")

            # Gerar clipes com base na análise, formato e duração
            clips_info = generate_clips(video_path, analysis, clip_format, clip_duration, transcription)
            print(f"Clipes gerados: {len(clips_info)}")

            # Limpar a pasta de downloads após processar os clipes
            if not clean_downloads_folder():
                print("Falha ao limpar pasta de downloads após processamento")
                return jsonify({
                    "status": "error",
                    "message": "Falha ao limpar pasta de downloads"
                }), 500

            # Retornar os clipes gerados
            if not clips_info:
                print("Nenhum clipe adequado foi gerado.")
                return jsonify({
                    "status": "error",
                    "message": "Nenhum clipe adequado foi gerado"
                }), 500
            
            # Preparar dados para exibição
            clips_data = []
            for clip_info in clips_info:
                clips_data.append({
                    "url": clip_info["url"],
                    "title": clip_info["title"],
                    "transcription": clip_info["transcription"],
                    "thumbnail": clip_info.get("thumbnail"),
                    "duration": clip_info.get("duration")
                })
                
            # Salvar no banco de dados se necessário
            if user_id != "anônimo":
                for clip in clips_data:
                    save_clip(user_id, clip["url"], clip["transcription"], clip["title"])
            
            print("Clipes gerados com sucesso")
            return jsonify({
                "status": "success",
                "data": clips_data
            })

        except Exception as e:
            print(f"Erro durante o processamento: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "status": "error",
                "message": f"Erro durante o processamento: {str(e)}"
            }), 500

    except Exception as e:
        print(f"Erro no servidor: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Erro no servidor: {str(e)}"
        }), 500

# Executar o servidor Flask
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
