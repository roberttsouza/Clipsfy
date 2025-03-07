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
app = Flask(__name__)

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

def transcribe_audio(audio_path):
    try:
        print(f"Transcrevendo áudio: {audio_path}")  # Log
        # Determine the device to use
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # Load the Whisper model
        model = whisper.load_model("base", device=device)  # Modelo "base" é suficiente para a maioria dos casos
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
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Prompt otimizado para vídeos longos
        prompt = f"""Você é um assistente especializado em análise de vídeos longos e engajamento. Sua tarefa é analisar sistematicamente a transcrição de um vídeo e identificar os melhores momentos para recortes, garantindo que múltiplos clipes relevantes sejam gerados.

### Estratégia de Análise:
1. **Análise Estratificada**  
   - Divida o vídeo em segmentos temporais (ex: a cada 10 minutos)  
   - Identifique os momentos mais relevantes em cada segmento  

2. **Critérios de Seleção:**  
   - **Momentos Emocionantes e Impactantes**  
     - Discursos inspiradores, histórias pessoais ou revelações marcantes  
   - **Momentos Engraçados e Virais**  
     - Piadas, interações cômicas ou falas espontâneas com alto potencial de compartilhamento  
   - **Informações Valiosas e Insights Úteis**  
     - Explicações técnicas, curiosidades, dicas práticas ou argumentos sólidos  
   - **Momentos de Tensão ou Surpresa**  
     - Reviravoltas, debates acalorados, falas polêmicas ou eventos inesperados  
   - **Frases de Efeito e Ganchos Poderosos**  
     - Declarações curtas e impactantes que prendem a atenção  

3. **Quantidade Mínima de Clipes:**  
   - Vídeos curtos (<30 min): 1-2 clipes  
   - Vídeos médios (30-60 min): 3-5 clipes  
   - Vídeos longos (>60 min): 5-10 clipes  

### **IMPORTANTE:**  
- **Sempre retorne múltiplos clipes** distribuídos ao longo do vídeo  
- Priorize momentos que representem diferentes aspectos do conteúdo  
- Se não houver momentos excepcionais, selecione trechos coerentes e informativos  
- Nunca retorne uma resposta vazia  

### **Formato da Resposta:**  
Para cada momento identificado, retorne no seguinte formato:

Categoria: [Nome da Categoria]
Timestamp: [HH:MM:SS - HH:MM:SS]
Descrição: [Resumo conciso do momento]
Trecho de Destaque: ["Frase ou diálogo mais marcante do trecho"]

**Transcrição do Vídeo:**  
{transcription}

Por favor, analise sistematicamente a transcrição e forneça os melhores momentos distribuídos ao longo do vídeo. **Garanta que haja múltiplos clipes relevantes, especialmente para vídeos longos.**
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
                
                # Adicionar informações do clipe à lista de retorno
                clips_info.append({
                    "path": clip_path,
                    "url": f"/static/clips/{os.path.basename(clip_path)}",
                    "title": clip_title,
                    "categoria": segment.get("categoria", ""),
                    "transcription": clip_transcription,
                    "duration": end_seconds - start_seconds
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
        
        clips_data.append({
            "url": clip_url, 
            "title": title,
            "transcription": transcription
        })

    # Ordenar clips por nome
    clips_data.sort(key=lambda x: x["title"])

    return render_template("index.html", clips_data=clips_data)

# Rota para processar o vídeo
@app.route("/process", methods=["POST"])
def process_video():
    print("Iniciando processamento do vídeo")  # Log
    # Obter dados do formulário
    video_url = request.form.get("video_url")
    uploaded_file = request.files.get("video_file")
    clip_format = request.form.get("clip_format")  # Formato do clipe
    clip_duration = request.form.get("clip_duration")  # Duração do clipe
    user_id = request.form.get("user_id", "anônimo")  # ID do usuário

    # Verificar se pelo menos uma fonte de vídeo foi fornecida
    if not video_url and not uploaded_file:
        print("Nenhuma fonte de vídeo fornecida")
        return jsonify({"error": "Por favor, forneça um link do YouTube ou faça upload de um arquivo de vídeo"}), 400

    try:
        # Limpar pasta de downloads antes de processar novo vídeo
        clean_downloads_folder()
        
        # Processar vídeo do YouTube ou vídeo carregado
        if video_url:
            print(f"Processando vídeo do YouTube: {video_url}")
            video_title, video_path = download_youtube_video(video_url)
        else:
            print(f"Processando vídeo carregado: {uploaded_file.filename}")
            video_title, video_path = process_local_video(uploaded_file)
            
        if not video_path:
            print("Falha ao processar o vídeo")
            return jsonify({"error": "Falha ao processar o vídeo"}), 500
        print(f"Vídeo processado com sucesso: {video_path}")

        # Extrair áudio
        audio_path = extract_audio(video_path, audio_output_path=f"{DOWNLOADS_DIR}/audio.mp3")
        if not audio_path:
            print("Falha ao extrair áudio")
            return jsonify({"error": "Falha ao extrair áudio"}), 500
        print(f"Áudio extraído com sucesso: {audio_path}")

        # Transcrever o áudio
        transcription = transcribe_audio(audio_path)
        if not transcription:
            print("Falha ao transcrever áudio")
            return jsonify({"error": "Falha ao transcrever áudio"}), 500
        print(f"Transcrição concluída com sucesso: {transcription[:100]}...")

        # Analisar a transcrição com a Gemini API
        analysis = analyze_transcription(transcription)
        if not analysis:
            print("Falha ao analisar transcrição")
            return jsonify({"error": "Falha ao analisar transcrição"}), 500
        print(f"Análise concluída com sucesso: {analysis[:100]}...")

        # Gerar clipes com base na análise, formato e duração
        clips_info = generate_clips(video_path, analysis, clip_format, clip_duration, transcription)
        print(f"Clipes gerados: {len(clips_info)}")

        # Limpar a pasta de downloads após processar os clipes
        clean_downloads_folder()

        # Retornar a página inicial com os clipes gerados
        if not clips_info:
            print("Nenhum clipe adequado foi gerado.")
            return jsonify({"error": "Nenhum clipe adequado foi gerado."}), 500
            
        # Preparar dados para exibição
        clips_data = []
        for clip_info in clips_info:
            clips_data.append({
                "url": clip_info["url"],
                "title": clip_info["title"],
                "transcription": clip_info["transcription"]
            })
            
        # Salvar no banco de dados se necessário
        if user_id != "anônimo":
            for clip in clips_data:
                save_clip(user_id, clip["url"], clip["transcription"], clip["title"])
        
        print("Clipes gerados e prontos para exibição")
        return render_template("index.html", clips_data=clips_data)

    except Exception as e:
        print(f"Erro no servidor: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# Executar o servidor Flask
if __name__ == "__main__":
    app.run(debug=True)
