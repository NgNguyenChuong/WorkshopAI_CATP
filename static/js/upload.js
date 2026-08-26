(() => {
    const form = document.querySelector("#upload-form");
    const input = document.querySelector("#submission-file");
    const dropZone = document.querySelector("#drop-zone");
    const selectedFile = document.querySelector("#selected-file");
    const selectedName = document.querySelector("#selected-file-name");
    const selectedSize = document.querySelector("#selected-file-size");
    const removeButton = document.querySelector("#remove-file");
    const clearButton = document.querySelector("#clear-file");
    const fileError = document.querySelector("#file-error");

    if (!form || !input || !dropZone) return;

    const maxBytes = Number(input.dataset.maxBytes);

    function formatSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        const units = ["KB", "MB", "GB"];
        let size = bytes / 1024;
        let unit = units[0];
        for (let index = 1; index < units.length && size >= 1024; index += 1) {
            size /= 1024;
            unit = units[index];
        }
        return `${size.toFixed(1)} ${unit}`;
    }

    function showError(message) {
        fileError.textContent = message;
        fileError.hidden = false;
        dropZone.classList.add("drop-zone-error");
    }

    function clearError() {
        fileError.textContent = "";
        fileError.hidden = true;
        dropZone.classList.remove("drop-zone-error");
    }

    function clearFile() {
        input.value = "";
        selectedFile.hidden = true;
        selectedName.textContent = "";
        selectedSize.textContent = "";
        clearButton.disabled = true;
        dropZone.hidden = false;
        clearError();
    }

    function validateFile(file) {
        if (!file) return "Vui lòng chọn file .zip cần nộp.";
        if (!file.name.toLowerCase().endsWith(".zip")) return "Chỉ chấp nhận file có đuôi .zip.";
        if (file.size > maxBytes) return `File vượt quá giới hạn ${Math.round(maxBytes / 1024 / 1024)} MB.`;
        if (file.size === 0) return "File không được để trống.";
        return "";
    }

    function displayFile(file) {
        const error = validateFile(file);
        if (error) {
            clearFile();
            showError(error);
            return false;
        }
        clearError();
        selectedName.textContent = file.name;
        selectedSize.textContent = formatSize(file.size);
        selectedFile.hidden = false;
        dropZone.hidden = true;
        clearButton.disabled = false;
        return true;
    }

    input.addEventListener("change", () => displayFile(input.files[0]));

    ["dragenter", "dragover"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.add("drag-over");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.remove("drag-over");
        });
    });

    dropZone.addEventListener("drop", (event) => {
        const file = event.dataTransfer.files[0];
        if (!file) return;
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        displayFile(file);
    });

    dropZone.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            input.click();
        }
    });

    removeButton.addEventListener("click", clearFile);
    clearButton.addEventListener("click", clearFile);

    form.addEventListener("submit", (event) => {
        const file = input.files[0];
        const error = validateFile(file);
        if (error) {
            event.preventDefault();
            showError(error);
            if (!file) dropZone.hidden = false;
        }
    });
})();
