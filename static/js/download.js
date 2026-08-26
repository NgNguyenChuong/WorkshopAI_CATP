(() => {
    document.querySelectorAll("[data-platform-picker]").forEach((picker) => {
        const select = picker.querySelector("[data-platform-select]");
        const format = picker.querySelector("[data-platform-format]");
        const size = picker.querySelector("[data-platform-size]");
        const requirement = picker.querySelector("[data-platform-requirement]");
        const download = picker.querySelector("[data-platform-download]");
        const buttonText = picker.querySelector("[data-platform-button]");

        function updateSelection() {
            const option = select.options[select.selectedIndex];
            const isAvailable = !option.disabled;
            format.textContent = option.dataset.format;
            size.textContent = option.dataset.size;
            requirement.textContent = option.dataset.requirement;
            buttonText.textContent = option.dataset.button;
            download.href = isAvailable ? option.dataset.url : "#";
            download.classList.toggle("button-disabled", !isAvailable);
            download.setAttribute("aria-disabled", String(!isAvailable));
        }

        select.addEventListener("change", updateSelection);
        download.addEventListener("click", (event) => {
            if (select.options[select.selectedIndex].disabled) event.preventDefault();
        });
    });
})();
