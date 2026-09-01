import json
import os
import secrets
import socket
import tempfile
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from queue_manager import DownloadQueue

download_queue = DownloadQueue(max_concurrent=10)

# Chi xep hang voi file lon. File nho tai thang, khong ton slot.
QUEUE_MIN_BYTES = 100 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "storage" / "models"
FILES_DIR = BASE_DIR / "storage" / "files"
SUBMISSIONS_DIR = BASE_DIR / "storage" / "submissions"

MAX_UPLOAD_MB = 200
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_UPLOAD_FILES = 5

# Bao ve viec cap STT, chon ten file va cap nhat metadata khi Waitress xu ly
# nhieu yeu cau upload tren cac thread khac nhau.
submission_lock = threading.Lock()

# Thay doi cac gia tri o day khi can cap nhat model.
MODELS = [
    {
        "id": "model1",
        "name": "Gemma 3 - 1B",
        "description": "Phiên bản nhẹ, phù hợp với máy cấu hình thấp.",
        "filename": "gemma3-low-model.zip",
        "format": "ZIP",
        "requirement": "RAM 8GB+",
        "button_label": "Tải Model 1 (.zip)",
        "download_note": "Giải nén rồi đặt thư mục gemma vào thư mục models của LM Studio.",
    },
    {
        "id": "model2",
        "name": "Gemma 3 - 4B",
        "description": "Phiên bản lớn hơn, dành cho máy có cấu hình cao.",
        "filename": "gemma3-high-model.zip",
        "format": "ZIP",
        "requirement": "RAM 16GB+",
        "button_label": "Tải Model 2 (.zip)",
        "download_note": "Giải nén rồi đặt thư mục gemma vào thư mục models của LM Studio.",
    },
    {
        "id": "lm-studio",
        "name": "LM Studio",
        "description": "Ứng dụng giúp tải và chạy model AI trên máy cá nhân.",
        "format": "APP",
        "options": [
            {
                "id": "windows",
                "label": "Windows 64-bit",
                "filename": "LM-Studio-0.4.21-2-x64.exe",
                "format": "EXE",
                "requirement": "Windows 64-bit",
                "button_label": "Tải bản Windows",
            },
            {
                "id": "macos",
                "label": "macOS (Apple Silicon)",
                "filename": "LM-Studio-0.4.21-2-arm64.dmg",
                "format": "DMG",
                "requirement": "macOS · Apple Silicon",
                "button_label": "Tải bản macOS",
            },
        ],
    },
]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def ensure_storage_directories():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)


def format_file_size(size_bytes):
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024


def model_path(model):
    """Return a safe path only for a plain filename from MODELS."""
    filename = model.get("filename", "")
    if not filename or Path(filename).name != filename:
        return None

    candidate = (MODELS_DIR / filename).resolve()
    try:
        candidate.relative_to(MODELS_DIR.resolve())
    except ValueError:
        return None
    return candidate


def model_view_data():
    result = []
    for model in MODELS:
        item = dict(model)
        if model.get("options"):
            item["options"] = []
            for option in model["options"]:
                option_item = dict(option)
                path = model_path(option)
                option_item["available"] = bool(path and path.is_file())
                file_size = path.stat().st_size if option_item["available"] else None
                option_item["size"] = format_file_size(file_size) if file_size is not None else None
                option_item["requires_queue"] = bool(file_size is not None and file_size >= QUEUE_MIN_BYTES)
                item["options"].append(option_item)
        else:
            path = model_path(model)
            item["available"] = bool(path and path.is_file())
            file_size = path.stat().st_size if item["available"] else None
            item["size"] = format_file_size(file_size) if file_size is not None else None
            item["requires_queue"] = bool(file_size is not None and file_size >= QUEUE_MIN_BYTES)
        result.append(item)
    return result


def public_file_path(filename):
    """Return a safe path for a visible file directly inside FILES_DIR."""
    if (
        not filename
        or Path(filename).name != filename
        or filename.startswith(".")
        or ":" in filename
        or any(ord(char) < 32 for char in filename)
    ):
        return None

    candidate = (FILES_DIR / filename).resolve()
    try:
        candidate.relative_to(FILES_DIR.resolve())
    except ValueError:
        return None
    return candidate


def public_file_view_data():
    if not FILES_DIR.is_dir():
        return []

    result = []
    for entry in FILES_DIR.iterdir():
        path = public_file_path(entry.name)
        if path is None or not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        result.append(
            {
                "name": path.name,
                "format": path.suffix.lstrip(".").upper() or "FILE",
                "size": format_file_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime)
                .astimezone()
                .strftime("%d/%m/%Y %H:%M"),
                "requires_queue": stat.st_size >= QUEUE_MIN_BYTES,
            }
        )
    return sorted(result, key=lambda item: item["name"].casefold())


def validation_error(message, status=400, form_data=None):
    return (
        render_template(
            "upload.html",
            active_page="upload",
            error=message,
            form_data=form_data or {},
            max_upload_mb=MAX_UPLOAD_MB,
            max_upload_files=MAX_UPLOAD_FILES,
        ),
        status,
    )


def clean_text(value, label, max_length):
    value = (value or "").strip()
    if not value:
        return None, f"Vui lòng nhập {label}."
    if len(value) > max_length:
        return None, f"{label.capitalize()} không được dài quá {max_length} ký tự."
    if any(ord(char) < 32 for char in value):
        return None, f"{label.capitalize()} chứa ký tự không hợp lệ."
    return value, None


def valid_upload_filename(filename):
    if not filename or len(filename) > 255:
        return False
    if "/" in filename or "\\" in filename or any(ord(char) < 32 for char in filename):
        return False
    return filename not in {".", ".."}


def identity_key(value):
    """Normalize text used to recognize the same student on later uploads."""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def student_folder_slug(student_name):
    """Build a readable, filesystem-safe HoVaTen part for the folder name."""
    value = student_name.replace("Đ", "D").replace("đ", "d")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    slug = secure_filename(value).strip("._")
    return slug[:100] or "Nguoi_Dung"


def read_metadata(directory):
    metadata_path = directory / "metadata.json"
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def find_or_create_student_directory(student_name, group):
    """Reuse a student's folder, or allocate the next positive STT."""
    name_key = identity_key(student_name)
    group_key = identity_key(group)
    used_numbers = set()

    for directory in SUBMISSIONS_DIR.iterdir():
        if not directory.is_dir():
            continue

        prefix = directory.name.partition("_")[0]
        if prefix.isdigit() and len(prefix) <= 6:
            used_numbers.add(int(prefix))

        metadata = read_metadata(directory)
        if not metadata or "group" not in metadata:
            continue
        if (
            identity_key(str(metadata.get("student_name", ""))) == name_key
            and identity_key(str(metadata.get("group", ""))) == group_key
        ):
            student_number = metadata.get("student_number")
            if not isinstance(student_number, int) or student_number < 1:
                if not prefix.isdigit():
                    continue
                student_number = int(prefix)
            return student_number, directory, metadata, False

    student_number = 1
    while student_number in used_numbers:
        student_number += 1

    slug = student_folder_slug(student_name)
    while True:
        directory = SUBMISSIONS_DIR / f"{student_number:03d}_{slug}"
        try:
            directory.mkdir()
            break
        except FileExistsError:
            student_number += 1

    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    metadata = {
        "storage_version": 2,
        "student_number": student_number,
        "student_name": student_name,
        "group": group,
        "directory": directory.name,
        "created_at": created_at,
        "updated_at": created_at,
        "uploads": [],
    }
    return student_number, directory, metadata, True


def safe_storage_filename(original_filename, fallback_number):
    safe_name = secure_filename(original_filename)
    safe_extension_name = secure_filename(f"file{Path(original_filename).suffix}")
    safe_suffix = Path(safe_extension_name).suffix
    if safe_suffix and not Path(safe_name).suffix:
        safe_stem = secure_filename(Path(original_filename).stem)
        safe_name = f"{safe_stem or f'file_{fallback_number}'}{safe_suffix}"
    if not safe_name:
        safe_name = f"file_{fallback_number}{safe_suffix}"

    if len(safe_name) > 180:
        suffix = Path(safe_name).suffix[:20]
        stem_limit = max(1, 180 - len(suffix))
        safe_name = f"{Path(safe_name).stem[:stem_limit]}{suffix}"
    return safe_name


def unique_storage_path(directory, filename):
    candidate = directory / filename
    stem = candidate.stem or "file"
    suffix = candidate.suffix
    counter = 2
    reserved_name = "metadata.json"

    while candidate.exists() or candidate.name.casefold() == reserved_name:
        candidate = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def write_metadata_atomic(directory, metadata):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix=".metadata-",
            suffix=".tmp",
            dir=directory,
            encoding="utf-8",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(metadata, temp_file, ensure_ascii=False, indent=2)
        os.replace(temp_path, directory / "metadata.json")
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@app.get("/")
def home():
    return render_template("index.html", active_page="home")


@app.get("/download")
def download_page():
    return render_template(
        "download.html",
        active_page="download",
        models=model_view_data(),
    )


@app.get("/files")
def files_page():
    return render_template(
        "files.html",
        active_page="files",
        files=public_file_view_data(),
    )


def files_error(message, status):
    return (
        render_template(
            "files.html",
            active_page="files",
            files=public_file_view_data(),
            error=message,
        ),
        status,
    )


def download_error(message, status):
    return (
        render_template(
            "download.html",
            active_page="download",
            models=model_view_data(),
            error=message,
        ),
        status,
    )


def send_managed_download(path, filename, queue_denied_response):
    """Send a file directly or reserve a queue slot for large downloads."""
    file_size = path.stat().st_size
    ticket = request.args.get("ticket", "")
    if file_size < QUEUE_MIN_BYTES or request.method == "HEAD":
        return send_file(
            path,
            as_attachment=True,
            download_name=filename,
            conditional=True,
        )

    if not download_queue.begin_download(ticket):
        return queue_denied_response()

    try:
        response = send_file(
            path,
            as_attachment=True,
            download_name=filename,
            conditional=True,
        )
    except Exception:
        download_queue.finish_download(ticket, complete=False)
        raise

    expected = response.content_length if response.content_length is not None else file_size
    completes_file = _response_completes_file(response, file_size)
    response.response = _TrackedStream(
        response.response,
        ticket,
        expected,
        completes_file,
        download_queue,
    )
    response.direct_passthrough = True
    return response


def send_configured_download(model_id, option_id=None):
    model = next((item for item in MODELS if item["id"] == model_id), None)
    target = model
    if model and model.get("options"):
        target = next((item for item in model["options"] if item["id"] == option_id), None)
    elif option_id is not None:
        target = None
    path = model_path(target) if target else None

    if model is None:
        return download_error("Model được yêu cầu không tồn tại.", 404)

    if model.get("options") and target is None:
        return download_error("Phiên bản LM Studio được yêu cầu không tồn tại.", 404)

    if path is None or not path.is_file():
        return download_error(f"Tệp {target['filename']} hiện chưa có trên máy chủ.", 404)

    return send_managed_download(
        path,
        target["filename"],
        lambda: download_error(
            "Chưa tới lượt tải. Vui lòng quay lại trang tải model và bấm nút để xếp hàng.",
            403,
        ),
    )


@app.get("/files/<path:filename>")
def download_public_file(filename):
    path = public_file_path(filename)
    if path is None or not path.is_file():
        return files_error("Tệp được yêu cầu không tồn tại.", 404)

    return send_managed_download(
        path,
        path.name,
        lambda: files_error(
            "Chưa tới lượt tải. Vui lòng quay lại trang tải tệp và bấm nút để xếp hàng.",
            403,
        ),
    )


@app.get("/download/<model_id>")
def download_model(model_id):
    model = next((item for item in MODELS if item["id"] == model_id), None)
    if model and model.get("options"):
        return download_error("Vui lòng chọn phiên bản LM Studio trước khi tải.", 400)
    return send_configured_download(model_id)

@app.get("/queue/stats")
def queue_stats():
    return jsonify(download_queue.stats())

@app.get("/download/<model_id>/<option_id>")
def download_model_option(model_id, option_id):
    return send_configured_download(model_id, option_id)


@app.route("/upload", methods=["GET", "POST"])
def upload_page():
    if request.method == "GET":
        return render_template(
            "upload.html",
            active_page="upload",
            max_upload_mb=MAX_UPLOAD_MB,
            max_upload_files=MAX_UPLOAD_FILES,
        )

    form_data = {
        "student_name": request.form.get("student_name", "").strip(),
        "group": request.form.get("group", "").strip(),
    }

    student_name, error = clean_text(form_data["student_name"], "họ và tên", 120)
    if error:
        return validation_error(error, form_data=form_data)

    group, error = clean_text(form_data["group"], "nhóm", 50)
    if error:
        return validation_error(error, form_data=form_data)

    uploaded_files = [
        uploaded_file
        for uploaded_file in request.files.getlist("submission_files")
        if uploaded_file and uploaded_file.filename
    ]
    if not uploaded_files:
        return validation_error("Vui lòng chọn ít nhất một file cần nộp.", form_data=form_data)
    if len(uploaded_files) > MAX_UPLOAD_FILES:
        return validation_error(
            f"Mỗi lần chỉ được nộp tối đa {MAX_UPLOAD_FILES} file.",
            form_data=form_data,
        )

    for uploaded_file in uploaded_files:
        if not valid_upload_filename(uploaded_file.filename):
            return validation_error(
                f"Tên file “{uploaded_file.filename}” không hợp lệ hoặc chứa đường dẫn.",
                form_data=form_data,
            )

    ensure_storage_directories()
    staged_files = []

    try:
        for uploaded_file in uploaded_files:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".upload-",
                suffix=".tmp",
                dir=SUBMISSIONS_DIR,
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                staged_item = {
                    "temp_path": temp_path,
                    "original_filename": uploaded_file.filename,
                    "size_bytes": 0,
                }
                staged_files.append(staged_item)
                uploaded_file.save(temp_file)

            uploaded_size = temp_path.stat().st_size
            staged_item["size_bytes"] = uploaded_size

            if uploaded_size == 0:
                return validation_error(
                    f"File “{uploaded_file.filename}” không được để trống.",
                    form_data=form_data,
                )

        total_size = sum(item["size_bytes"] for item in staged_files)
        if total_size > MAX_UPLOAD_BYTES:
            return validation_error(
                f"Tổng dung lượng file vượt quá giới hạn {MAX_UPLOAD_MB} MB.",
                status=413,
                form_data=form_data,
            )

        with submission_lock:
            student_number, submission_dir, metadata, created = (
                find_or_create_student_directory(student_name, group)
            )
            moved_paths = []
            try:
                stored_files = []
                for index, item in enumerate(staged_files, start=1):
                    safe_name = safe_storage_filename(item["original_filename"], index)
                    stored_path = unique_storage_path(submission_dir, safe_name)
                    os.replace(item["temp_path"], stored_path)
                    item["temp_path"] = None
                    moved_paths.append(stored_path)
                    stored_files.append(
                        {
                            "original_filename": item["original_filename"],
                            "stored_filename": stored_path.name,
                            "size_bytes": item["size_bytes"],
                        }
                    )

                uploaded_at = datetime.now().astimezone().isoformat(timespec="seconds")
                upload_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{secrets.token_hex(3)}"
                uploads = metadata.get("uploads")
                if not isinstance(uploads, list):
                    uploads = []
                    metadata["uploads"] = uploads
                uploads.append(
                    {
                        "upload_id": upload_id,
                        "uploaded_at": uploaded_at,
                        "files": stored_files,
                    }
                )
                metadata.update(
                    {
                        "storage_version": 2,
                        "student_number": student_number,
                        "student_name": student_name,
                        "group": group,
                        "directory": submission_dir.name,
                        "updated_at": uploaded_at,
                    }
                )
                write_metadata_atomic(submission_dir, metadata)
            except Exception:
                for moved_path in moved_paths:
                    moved_path.unlink(missing_ok=True)
                if created:
                    try:
                        submission_dir.rmdir()
                    except OSError:
                        pass
                raise

        return render_template(
            "upload.html",
            active_page="upload",
            success=True,
            submission_directory=submission_dir.name,
            uploaded_files=stored_files,
            max_upload_mb=MAX_UPLOAD_MB,
            max_upload_files=MAX_UPLOAD_FILES,
        )
    except RequestEntityTooLarge:
        raise
    except Exception:
        return validation_error(
            "Không thể lưu bài nộp. Vui lòng thử lại.",
            status=500,
            form_data=form_data,
        )
    finally:
        for item in staged_files:
            temp_path = item.get("temp_path")
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


@app.errorhandler(413)
def upload_too_large(_error):
    return validation_error(
        f"Tổng dung lượng tải lên vượt quá giới hạn {MAX_UPLOAD_MB} MB.",
        status=413,
    )


@app.errorhandler(404)
def page_not_found(_error):
    return (
        render_template(
            "error.html",
            active_page=None,
            status_code=404,
            title="Không tìm thấy trang",
            message="Đường dẫn bạn yêu cầu không tồn tại.",
        ),
        404,
    )


@app.errorhandler(500)
def internal_error(_error):
    return (
        render_template(
            "error.html",
            active_page=None,
            status_code=500,
            title="Có lỗi xảy ra",
            message="Máy chủ không thể xử lý yêu cầu. Vui lòng thử lại.",
        ),
        500,
    )

@app.post("/queue/join")
def queue_join():
    payload = request.get_json(silent=True) or {}
    client_id = str(payload.get("client_id", "")).strip()
    if len(client_id) > 128 or any(ord(char) < 32 for char in client_id):
        return jsonify({"error": "Mã trình duyệt không hợp lệ."}), 400

    # client_id giup nhieu nguoi sau cung NAT/proxy van co ticket rieng.
    owner_id = f"{request.remote_addr or 'unknown'}:{client_id or 'legacy'}"
    return jsonify(download_queue.join(owner_id))


@app.get("/queue/status")
def queue_status():
    return jsonify(download_queue.status(request.args.get("ticket", "")))


@app.post("/queue/leave")
def queue_leave():
    released = download_queue.leave(request.args.get("ticket", ""))
    return jsonify({"ok": released})


def detect_lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "<LOCAL_IP>"
    finally:
        sock.close()

def _response_completes_file(response, file_size):
    """Return True when this response reaches the end of the requested file."""
    content_range = response.headers.get("Content-Range", "")
    if not content_range:
        return 200 <= response.status_code < 300

    try:
        byte_range, total = content_range.removeprefix("bytes ").split("/", 1)
        _start, end = byte_range.split("-", 1)
        return int(total) == file_size and int(end) + 1 == file_size
    except (TypeError, ValueError):
        return False


class _TrackedStream:
    """Track a file iterable and always return its queue slot on close."""

    def __init__(self, iterable, ticket, expected, completes_file, queue):
        self._iterable = iterable
        self._iterator = iter(iterable)
        self._ticket = ticket
        self._expected = expected
        self._completes_file = completes_file
        self._queue = queue
        self._sent = 0
        self._closed = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self._iterator)
        except StopIteration:
            self.close()
            raise
        self._sent += len(chunk)
        return chunk

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            closer = getattr(self._iterable, "close", None)
            if closer is not None:
                closer()
        finally:
            self._queue.finish_download(
                self._ticket,
                complete=self._completes_file and self._sent >= self._expected,
            )
if __name__ == "__main__":
    ensure_storage_directories()
    lan_ip = detect_lan_ip()
    print(f"LAN: http://{lan_ip}:8080")

    from waitress import serve
    serve(app, host="0.0.0.0", port=8080, threads=32,
          channel_timeout=1800, cleanup_interval=60)
