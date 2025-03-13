# Usar imagem base do Python com suporte completo
FROM python:3.11

# Instalar dependências de sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cmake \
    build-essential \
    libopenblas-dev \
    libopenmpi-dev \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    libavcodec-extra \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libavfilter-dev \
    libdav1d-dev \
    libaom-dev \
    libsvtav1enc-dev \
    libvpx-dev \
    && rm -rf /var/lib/apt/lists/*

# Definir diretório de trabalho
WORKDIR /app

# Copiar arquivos necessários
COPY requirements.txt .
COPY app.py .
COPY static/ ./static/
COPY templates/ ./templates/

# Instalar PyTorch primeiro com suporte a CPU
RUN pip install --no-cache-dir torch torchvision torchaudio

# Instalar demais dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Expor a porta do Flask
EXPOSE 5000

# Comando para rodar a aplicação
CMD ["python", "app.py"]
