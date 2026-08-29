(() => {
    const POLL_INTERVAL_MS = 3000;
    const DOWNLOAD_CHECK_DELAY_MS = 5000;
    const queuePanel = document.querySelector("[data-download-queue]");
    const queueTitle = queuePanel?.querySelector("[data-queue-title]");
    const queueMessage = queuePanel?.querySelector("[data-queue-message]");
    const queueStats = queuePanel?.querySelector("[data-queue-stats]");
    const queuePosition = queuePanel?.querySelector("[data-queue-position]");
    const queueActive = queuePanel?.querySelector("[data-queue-active]");
    const queueSlots = queuePanel?.querySelector("[data-queue-slots]");
    const queueWaiting = queuePanel?.querySelector("[data-queue-waiting]");
    const cancelButton = queuePanel?.querySelector("[data-queue-cancel]");
    const retryButton = queuePanel?.querySelector("[data-queue-retry]");

    let queueContext = null;
    let pollTimer = null;
    let fallbackClientId = null;

    function makeClientId() {
        if (window.crypto?.randomUUID) return window.crypto.randomUUID();
        return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }

    function getClientId() {
        try {
            let clientId = window.sessionStorage.getItem("model-hub-download-client");
            if (!clientId) {
                clientId = makeClientId();
                window.sessionStorage.setItem("model-hub-download-client", clientId);
            }
            return clientId;
        } catch (_error) {
            fallbackClientId ||= makeClientId();
            return fallbackClientId;
        }
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || "Máy chủ không thể xử lý hàng đợi.");
        }
        return data;
    }

    function clearPollTimer() {
        if (pollTimer !== null) {
            window.clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    function showPanel() {
        if (!queuePanel) return;
        queuePanel.hidden = false;
        queuePanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function updateStats(snapshot) {
        if (!queueStats) return;
        queueStats.hidden = false;
        queuePosition.textContent = snapshot.ready ? "Đã tới lượt" : String(snapshot.position || "—");
        queueActive.textContent = String(snapshot.active ?? "—");
        queueSlots.textContent = String(snapshot.slots ?? "—");
        queueWaiting.textContent = String(snapshot.waiting ?? "—");
    }

    function setPanelState({ title, message, showStats = true, cancelLabel = "Hủy xếp hàng", retry = false }) {
        showPanel();
        queueTitle.textContent = title;
        queueMessage.textContent = message;
        queueStats.hidden = !showStats;
        cancelButton.textContent = cancelLabel;
        cancelButton.hidden = false;
        retryButton.hidden = !retry;
    }

    function showFailure(message) {
        clearPollTimer();
        queueContext = null;
        setPanelState({
            title: "Không thể xếp hàng",
            message,
            showStats: false,
            cancelLabel: "Đóng",
        });
    }

    function scheduleStatusCheck(delay = POLL_INTERVAL_MS) {
        clearPollTimer();
        pollTimer = window.setTimeout(checkStatus, delay);
    }

    function startDownload() {
        if (!queueContext?.ticket) return;
        queueContext.phase = "downloading";
        const downloadUrl = new URL(queueContext.downloadUrl, window.location.href);
        downloadUrl.searchParams.set("ticket", queueContext.ticket);

        setPanelState({
            title: "Đã tới lượt của bạn",
            message: "Tệp đang được gửi tới trình duyệt. Không đóng trang này cho tới khi tải bắt đầu.",
            cancelLabel: "Đang tải…",
        });
        cancelButton.hidden = true;
        window.location.assign(downloadUrl.toString());
        scheduleStatusCheck(DOWNLOAD_CHECK_DELAY_MS);
    }

    function handleSnapshot(snapshot) {
        if (!queueContext) return;

        if (snapshot.expired) {
            const wasDownloading = queueContext.phase === "downloading";
            clearPollTimer();
            queueContext = null;
            setPanelState({
                title: wasDownloading ? "Tải xuống đã hoàn tất" : "Phiên xếp hàng đã hết hạn",
                message: wasDownloading
                    ? "Slot tải đã được trả lại cho người tiếp theo."
                    : "Hãy bấm lại nút tải để nhận ticket mới.",
                showStats: false,
                cancelLabel: "Đóng",
            });
            return;
        }

        updateStats(snapshot);

        if (snapshot.downloading) {
            queueContext.phase = "downloading";
            setPanelState({
                title: "Đang tải xuống",
                message: "Máy chủ đang truyền tệp cho bạn. Slot sẽ tự động chuyển cho người tiếp theo khi kết thúc.",
            });
            cancelButton.hidden = true;
            scheduleStatusCheck();
            return;
        }

        if (!snapshot.ready) {
            queueContext.phase = "waiting";
            setPanelState({
                title: "Bạn đang trong hàng đợi",
                message: `Bạn đang ở vị trí ${snapshot.position} trong danh sách chờ. Trang sẽ tự bắt đầu tải khi tới lượt.`,
            });
            scheduleStatusCheck();
            return;
        }

        if (queueContext.phase === "downloading") {
            setPanelState({
                title: "Kết nối tải đã dừng",
                message: "Bạn có thể tải tiếp bằng ticket hiện tại hoặc rời hàng đợi.",
                cancelLabel: "Rời hàng đợi",
                retry: true,
            });
            return;
        }

        startDownload();
    }

    async function checkStatus() {
        if (!queueContext?.ticket) return;
        try {
            const query = new URLSearchParams({ ticket: queueContext.ticket });
            const snapshot = await requestJson(`/queue/status?${query}`);
            handleSnapshot(snapshot);
        } catch (_error) {
            if (!queueContext) return;
            queueMessage.textContent = "Mất kết nối với máy chủ; đang thử lại…";
            scheduleStatusCheck();
        }
    }

    async function joinQueue(downloadUrl) {
        clearPollTimer();
        queueContext = { downloadUrl, phase: "joining", ticket: null };
        setPanelState({
            title: "Đang xếp hàng",
            message: "Đang lấy ticket từ máy chủ…",
            showStats: false,
        });

        try {
            const snapshot = await requestJson("/queue/join", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ client_id: getClientId() }),
            });
            if (!queueContext) return;
            queueContext.ticket = snapshot.ticket;
            handleSnapshot(snapshot);
        } catch (error) {
            showFailure(error.message);
        }
    }

    async function leaveQueue() {
        clearPollTimer();
        const ticket = queueContext?.ticket;
        queueContext = null;
        if (ticket) {
            const query = new URLSearchParams({ ticket });
            try {
                await requestJson(`/queue/leave?${query}`, { method: "POST" });
            } catch (_error) {
                // Ticket van tu het han neu client mat ket noi.
            }
        }
        queuePanel.hidden = true;
    }

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
            download.dataset.queueRequired = option.dataset.queueRequired;
            download.classList.toggle("button-disabled", !isAvailable);
            download.setAttribute("aria-disabled", String(!isAvailable));
        }

        select.addEventListener("change", updateSelection);
    });

    document.querySelectorAll("[data-download-link]").forEach((link) => {
        link.addEventListener("click", (event) => {
            if (link.getAttribute("aria-disabled") === "true") {
                event.preventDefault();
                return;
            }
            if (link.dataset.queueRequired !== "true") return;

            event.preventDefault();
            if (queueContext) {
                showPanel();
                return;
            }
            joinQueue(link.href);
        });
    });

    cancelButton?.addEventListener("click", leaveQueue);
    retryButton?.addEventListener("click", () => {
        retryButton.hidden = true;
        startDownload();
    });
})();
