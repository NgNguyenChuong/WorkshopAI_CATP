import json
import os
import secrets
import socket
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "storage" / "models"
SUBMISSIONS_DIR = BASE_DIR / "storage" / "submissions"

MAX_UPLOAD_MB = 200
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# Thay doi cac gia tri o day khi can cap nhat model.
MODELS = [
    {
        "id": "model1",
        "name": "Gemma 3 - Máy yếu",
        "description": "Phiên bản nhẹ, phù hợp với máy cấu hình thấp.",
        "filename": "gemma-3-1b-it-Q4_K_M.gguf",
        "format": "GGUF",
        "requirement": "RAM 8GB+",
        "button_label": "Tải Model 1",
    },
    {
        "id": "model2",
        "name": "Gemma 3 - Máy mạnh",
        "description": "Phiên bản lớn hơn, dành cho máy có cấu hình mạnh.",
        "filename": "gemma-3-4b-it-Q4_K_M.gguf",
        "format": "GGUF",
        "requirement": "RAM 16GB+",
        "button_label": "Tải Model 2",
    },
    {
        "id": "lm-studio",
        "name": "LM Studio",
        "description": "Ứng dụng giúp tải và chạy model AI trên máy cá nhân.",
        "filename": "LM-Studio-0.4.21-2-x64.exe",
        "format": "EXE",
        "requirement": "Windows 64-bit",
        "button_label": "Tải LM Studio",
    },
]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def ensure_storage_directories():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
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
        path = model_path(model)
        item["available"] = bool(path and path.is_file())
        item["size"] = format_file_size(path.stat().st_size) if item["available"] else None
        result.append(item)
    return result


def validation_error(message, status=400, form_data=None):
    return (
        render_template(
            "upload.html",
            active_page="upload",
            error=message,
            form_data=form_data or {},
            max_upload_mb=MAX_UPLOAD_MB,
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
    if Path(filename).suffix.lower() != ".zip":
        return False
    return bool(secure_filename(filename))


def new_submission_directory():
    for _ in range(10):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        submission_id = f"{timestamp}_{secrets.token_hex(3)}"
        directory = SUBMISSIONS_DIR / submission_id
        try:
            directory.mkdir()
            return submission_id, directory
        except FileExistsError:
            continue
    raise RuntimeError("Không thể tạo mã bài nộp duy nhất.")


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


@app.get("/download/<model_id>")
def download_model(model_id):
    model = next((item for item in MODELS if item["id"] == model_id), None)
    path = model_path(model) if model else None

    if model is None:
        return (
            render_template(
                "download.html",
                active_page="download",
                models=model_view_data(),
                error="Model được yêu cầu không tồn tại.",
            ),
            404,
        )

    if path is None or not path.is_file():
        return (
            render_template(
                "download.html",
                active_page="download",
                models=model_view_data(),
                error=f"Tệp {model['filename']} hiện chưa có trên máy chủ.",
            ),
            404,
        )

    return send_file(
        path,
        as_attachment=True,
        download_name=model["filename"],
        conditional=True,
    )


@app.route("/upload", methods=["GET", "POST"])
def upload_page():
    if request.method == "GET":
        return render_template(
            "upload.html",
            active_page="upload",
            max_upload_mb=MAX_UPLOAD_MB,
        )

    form_data = {
        "student_name": request.form.get("student_name", "").strip(),
        "student_id": request.form.get("student_id", "").strip(),
        "assignment": request.form.get("assignment", "").strip(),
    }

    student_name, error = clean_text(form_data["student_name"], "họ và tên", 120)
    if error:
        return validation_error(error, form_data=form_data)

    student_id, error = clean_text(form_data["student_id"], "MSSV", 50)
    if error:
        return validation_error(error, form_data=form_data)

    assignment, error = clean_text(form_data["assignment"], "tên bài tập", 120)
    if error:
        return validation_error(error, form_data=form_data)

    uploaded_file = request.files.get("submission_file")
    if uploaded_file is None or not uploaded_file.filename:
        return validation_error("Vui lòng chọn file .zip cần nộp.", form_data=form_data)

    original_filename = uploaded_file.filename
    if not valid_upload_filename(original_filename):
        return validation_error(
            "Tên file không hợp lệ. Chỉ chấp nhận file có đuôi .zip và không chứa đường dẫn.",
            form_data=form_data,
        )

    ensure_storage_directories()
    temp_path = None
    submission_dir = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".upload-", suffix=".tmp", dir=SUBMISSIONS_DIR, delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
            uploaded_file.save(temp_file)

        uploaded_size = temp_path.stat().st_size
        if uploaded_size > MAX_UPLOAD_BYTES:
            return validation_error(
                f"File vượt quá giới hạn {MAX_UPLOAD_MB} MB.",
                status=413,
                form_data=form_data,
            )
        if uploaded_size == 0 or not zipfile.is_zipfile(temp_path):
            return validation_error(
                "File đã chọn không phải là file ZIP hợp lệ.",
                form_data=form_data,
            )

        submission_id, submission_dir = new_submission_directory()
        stored_path = submission_dir / "submission.zip"
        os.replace(temp_path, stored_path)
        temp_path = None

        uploaded_at = datetime.now().astimezone().isoformat(timespec="seconds")
        metadata = {
            "submission_id": submission_id,
            "student_name": student_name,
            "student_id": student_id,
            "assignment": assignment,
            "original_filename": original_filename,
            "stored_filename": "submission.zip",
            "uploaded_at": uploaded_at,
        }
        metadata_path = submission_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return render_template(
            "upload.html",
            active_page="upload",
            success=True,
            submission_id=submission_id,
            max_upload_mb=MAX_UPLOAD_MB,
        )
    except RequestEntityTooLarge:
        raise
    except Exception:
        if submission_dir is not None:
            for child in submission_dir.iterdir():
                child.unlink(missing_ok=True)
            submission_dir.rmdir()
        return validation_error(
            "Không thể lưu bài nộp. Vui lòng thử lại.",
            status=500,
            form_data=form_data,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@app.errorhandler(413)
def upload_too_large(_error):
    return validation_error(
        f"File vượt quá giới hạn {MAX_UPLOAD_MB} MB.",
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


if __name__ == "__main__":
    ensure_storage_directories()
    lan_ip = detect_lan_ip()
    print("Model Hub running on:")
    print("http://127.0.0.1:8080")
    print(f"LAN: http://{lan_ip}:8080")
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
