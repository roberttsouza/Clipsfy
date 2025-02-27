// Funções de alternância das abas
function setupTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-pane');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remover classe ativa de todos os botões
            tabButtons.forEach(btn => btn.classList.remove('active'));
            
            // Adicionar classe ativa ao botão clicado
            button.classList.add('active');
            
            // Ocultar todos os painéis de conteúdo
            tabContents.forEach(content => content.classList.remove('active'));
            
            // Mostrar o painel de conteúdo correspondente
            const tabId = button.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
            
            // Limpar campos da outra aba
            if (tabId === 'youtube-tab') {
                document.getElementById('video-file').value = "";
                document.getElementById('file-name').textContent = "Nenhum arquivo selecionado";
            } else {
                document.getElementById('video-url').value = "";
            }
        });
    });
}

// Funções de upload de arquivo
function setupFileUpload() {
    const fileInput = document.getElementById('video-file');
    const fileNameDisplay = document.getElementById('file-name');
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            fileNameDisplay.textContent = e.target.files[0].name;
        } else {
            fileNameDisplay.textContent = "Nenhum arquivo selecionado";
        }
    });
}

// Funções de alternância da transcrição
function setupTranscriptToggle() {
    document.addEventListener('click', (e) => {
        if (e.target && e.target.classList.contains('toggle-transcript')) {
            const transcriptDiv = e.target.closest('.clip-card').querySelector('.clip-transcript');
            transcriptDiv.classList.toggle('hidden');
            
            // Alterar texto do botão
            if (transcriptDiv.classList.contains('hidden')) {
                e.target.textContent = 'Ver Transcrição';
            } else {
                e.target.textContent = 'Ocultar Transcrição';
            }
        }
    });
}

// Gerenciamento do formulário e barra de progresso
function setupFormSubmission() {
    const form = document.getElementById('clip-form');
    const progressContainer = document.querySelector('.progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    const resultsSection = document.getElementById('results');
    
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            // Validar o formulário
            const youtubeTab = document.getElementById('youtube-tab');
            const fileTab = document.getElementById('file-tab');
            const videoUrl = document.getElementById('video-url').value;
            const videoFile = document.getElementById('video-file').files[0];
            
            if (youtubeTab.classList.contains('active') && !videoUrl) {
                alert('Por favor, forneça um link de vídeo do YouTube.');
                return;
            }
            
            if (fileTab.classList.contains('active') && !videoFile) {
                alert('Por favor, selecione um arquivo de vídeo.');
                return;
            }
            
            // Exibir progresso
            progressContainer.style.display = 'block';
            progressBar.style.width = '0%';
            progressBar.textContent = '0%';
            progressStatus.textContent = 'Iniciando processamento...';
            resultsSection.style.display = 'none';
            
            try {
                // Criar FormData para o envio
                const formData = new FormData(form);
                
                // Remover campo não relevante dependendo da aba ativa
                if (youtubeTab.classList.contains('active') && formData.has('video_file')) {
                    formData.delete('video_file');
                }
                
                if (fileTab.classList.contains('active') && formData.has('video_url')) {
                    formData.delete('video_url');
                }
                
                // Iniciar envio
                progressStatus.textContent = 'Enviando vídeo...';
                updateProgress(10);
                
                // Enviar o formulário
                const response = await fetch('/process', {
                    method: 'POST',
                    body: formData
                });
                
                // Verificar resposta
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Ocorreu um erro ao processar o vídeo.');
                }
                
                updateProgress(30);
                progressStatus.textContent = 'Processando vídeo...';
                
                // Para simular o progresso (já que o servidor não informa progresso real)
                let progress = 30;
                const progressInterval = setInterval(() => {
                    progress += Math.random() * 5;
                    if (progress > 90) {
                        progress = 90;
                        clearInterval(progressInterval);
                    }
                    updateProgress(progress);
                }, 2000);
                
                // Obter resposta HTML
                const htmlResponse = await response.text();
                
                // Simular finalização do processamento
                clearInterval(progressInterval);
                updateProgress(100);
                progressStatus.textContent = 'Concluído!';
                
                // Atualizar a página com os resultados
                setTimeout(() => {
                    document.documentElement.innerHTML = htmlResponse;
                    // Reconfigurar manipuladores de eventos após atualização do DOM
                    setupEventHandlers();
                }, 1000);
                
            } catch (error) {
                progressContainer.style.display = 'none';
                alert(error.message || 'Ocorreu um erro ao processar o vídeo');
                console.error(error);
            }
        });
    }
}

// Helper para atualizar a barra de progresso
function updateProgress(percent) {
    const progressBar = document.getElementById('progress-bar');
    if (progressBar) {
        progressBar.style.width = `${percent}%`;
        progressBar.textContent = `${Math.round(percent)}%`;
        progressBar.setAttribute('aria-valuenow', percent);
    }
}

// Configurar todos os manipuladores de eventos
function setupEventHandlers() {
    setupTabs();
    setupFileUpload();
    setupTranscriptToggle();
    setupFormSubmission();
}

// Inicializar quando o DOM estiver carregado
document.addEventListener('DOMContentLoaded', setupEventHandlers);