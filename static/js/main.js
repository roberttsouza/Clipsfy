 // Ocultar a barra de progresso inicialmente
 const progressDiv = document.querySelector(".progress");
 progressDiv.style.display = "none";

document.getElementById("clip-form").addEventListener("submit", async function (e) {
    e.preventDefault();

    // Exibir mensagem de carregamento e barra de progresso
    const resultsDiv = document.getElementById("results");
    resultsDiv.style.display = "none";
    const progressBar = document.getElementById("progress-bar");

    // Add a slight delay before showing progress bar
    setTimeout(() => {
        progressDiv.style.display = "block";
        progressBar.style.width = "0%";
        progressBar.textContent = "0%";
    }, 500);

    // Enviar os dados do formulário para o backend
    const formData = new FormData(this);
    const response = await fetch("/process", {
        method: "POST",
        body: formData
    });

    const reader = response.body.getReader();
    let receivedLength = 0;
    let chunks = [];

    while (true) {
        const { done, value } = await reader.read();

        if (done) {
            break;
        }

        chunks.push(value);
        receivedLength += value.length;

        // Atualizar a barra de progresso
        const progress = (receivedLength / 1000000) * 100;
        setTimeout(() => {
            progressBar.style.width = `${progress}%`;
            progressBar.textContent = `${progress.toFixed(2)}%`;
        }, 100);
    }

    let chunksAll = new Uint8Array(receivedLength);
    let position = 0;
    for (let chunk of chunks) {
        chunksAll.set(chunk, position);
        position += chunk.length;
    }

    let result = new TextDecoder("utf-8").decode(chunksAll);
    const data = JSON.parse(result);

    if (data.error) {
        alert(`Erro: ${data.error}`);
        return;
    }

    // Exibir os clipes gerados
    const clipsContainer = document.getElementById("clips-container");
    clipsContainer.innerHTML = "";

    data.clips.forEach(clipUrl => {
        const videoElement = document.createElement("video");
        videoElement.src = clipUrl;
        videoElement.controls = true;
        videoElement.width = 300;

        const downloadLink = document.createElement("a");
        downloadLink.href = clipUrl;
        downloadLink.textContent = "Download Clip";
        downloadLink.download = clipUrl.substring(clipUrl.lastIndexOf('/') + 1);
        downloadLink.style.display = "block";
        downloadLink.className = "download-link";

        clipsContainer.appendChild(videoElement);
        clipsContainer.appendChild(downloadLink);
    });

    resultsDiv.style.display = "block";
    progressDiv.style.display = "none";
});
