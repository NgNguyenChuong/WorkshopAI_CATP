(() => {
    const form = document.querySelector("#upload-form");
    const input = document.querySelector("#submission-file");
    const dropZone = document.querySelector("#drop-zone");
    const selectedFile = document.querySelector("#selected-file");
    const selectedSummary = document.querySelector("#selected-file-summary");
    const selectedSize = document.querySelector("#selected-file-size");
    const selectedList = document.querySelector("#selected-file-list");
    const removeButton = document.querySelector("#remove-file");
    const clearButton = document.querySelector("#clear-file");
    const fileError = document.querySelector("#file-error");
    const submitButton = document.querySelector("#submit-upload");

    if (!form || !input || !dropZone) return;

    const maxBytes = Number(input.dataset.maxBytes);
    const maxFiles = Number(input.dataset.maxFiles);

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
        selectedSummary.textContent = "";
        selectedSize.textContent = "";
        selectedList.replaceChildren();
        clearButton.disabled = true;
        dropZone.hidden = false;
        clearError();
    }

    function validateFiles(files) {
        if (!files.length) return "Vui lòng chọn ít nhất một file cần nộp.";
        if (files.length > maxFiles) return `Mỗi lần chỉ được chọn tối đa ${maxFiles} file.`;

        const emptyFile = files.find((file) => file.size === 0);
        if (emptyFile) return `File “${emptyFile.name}” không được để trống.`;

        const totalBytes = files.reduce((total, file) => total + file.size, 0);
        if (totalBytes > maxBytes) {
            return `Tổng dung lượng file vượt quá giới hạn ${Math.round(maxBytes / 1024 / 1024)} MB.`;
        }
        return "";
    }

    function displayFiles(fileList) {
        const files = Array.from(fileList);
        const error = validateFiles(files);
        if (error) {
            clearFile();
            showError(error);
            return false;
        }
        clearError();
        const totalBytes = files.reduce((total, file) => total + file.size, 0);
        selectedSummary.textContent = `${files.length} file đã chọn`;
        selectedSize.textContent = `Tổng dung lượng: ${formatSize(totalBytes)}`;
        selectedList.replaceChildren(
            ...files.map((file) => {
                const item = document.createElement("li");
                const name = document.createElement("span");
                const size = document.createElement("small");
                name.textContent = file.name;
                size.textContent = formatSize(file.size);
                item.append(name, size);
                return item;
            }),
        );
        selectedFile.hidden = false;
        dropZone.hidden = true;
        clearButton.disabled = false;
        return true;
    }

    input.addEventListener("change", () => displayFiles(input.files));

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
        const files = Array.from(event.dataTransfer.files);
        if (!files.length) return;
        const transfer = new DataTransfer();
        files.forEach((file) => transfer.items.add(file));
        input.files = transfer.files;
        displayFiles(input.files);
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
        const error = validateFiles(Array.from(input.files));
        if (error) {
            event.preventDefault();
            showError(error);
            if (!input.files.length) dropZone.hidden = false;
            return;
        }

        submitButton.disabled = true;
        submitButton.setAttribute("aria-busy", "true");
    });
})();
