# Model Hub

Ứng dụng web nội bộ bằng Flask để điều hướng, tải model AI/LM Studio, tải tệp được chia sẻ và nộp bài tập dạng `.zip`.

Frontend dùng HTML5, CSS3 và JavaScript thuần; không có bước build.

Các file từ 100 MB trở lên đi qua hàng đợi tải xuống. Mỗi trình duyệt nhận một ticket, thấy vị trí hiện tại và tự bắt đầu tải khi có slot trống. Mặc định máy chủ cho tối đa 10 ticket tải đồng thời.

## Yêu cầu

- Python 3
- Flask 3.x
- Waitress 3.x
- Mạng LAN nếu muốn truy cập từ máy khác

## Cài đặt

```bash
python -m pip install -r requirements.txt
```

## Chạy ứng dụng

```bash
python server.py
```

Ứng dụng bind trên `0.0.0.0:8080`. Khi khởi động, terminal sẽ in ra địa chỉ local và địa chỉ LAN:

```text
http://127.0.0.1:8080
http://<LOCAL_IP>:8080
```

Máy khác trong cùng mạng có thể mở địa chỉ LAN được in ra.

## Cấu trúc dự án

```text
server.py                 # Flask backend và cấu hình model
templates/                # Các trang HTML
static/css/style.css      # Giao diện
static/js/upload.js       # Tương tác upload
static/js/download.js     # Dropdown LM Studio và giao diện hàng đợi
queue_manager.py          # Hàng đợi tải file thread-safe
storage/models/           # Các archive/model được phép tải
storage/files/            # Các tệp công khai trên trang tải tệp
storage/submissions/      # Bài nộp và metadata
```

## Chuẩn bị model để tải

Các file model được chuẩn bị thủ công, không được ZIP trong lúc người dùng tải. Đặt archive đúng tên đã khai báo trong `MODELS` tại `storage/models/`.

Với Gemma, hãy tự tạo archive chứa cấu trúc thư mục sau:

```text
gemma3-high-model.zip
└── gemma/
    └── gemma3/
        └── gemma-3-4b-it-Q4_K_M.gguf
```

Sau khi tải, người dùng giải nén rồi đặt cả thư mục `gemma` vào thư mục models của LM Studio.

Model cấu hình trong `server.py` có dạng:

```python
{
    "id": "model2",
    "name": "Gemma 3 - Máy mạnh",
    "description": "Phiên bản lớn hơn, dành cho máy có cấu hình mạnh.",
    "filename": "gemma3-high-model.zip",
    "format": "ZIP",
    "requirement": "RAM 16GB+",
    "button_label": "Tải Model 2 (.zip)",
}
```

Dung lượng trên trang được lấy tự động từ archive thực tế. Nếu file chưa có, nút tải sẽ bị vô hiệu hóa và trang hiển thị thông báo rõ ràng.

## LM Studio

LM Studio có dropdown chọn phiên bản:

- macOS Apple Silicon: file `.dmg`;
- Windows 64-bit: file `.exe`.

Các file cài đặt cũng phải nằm trong `storage/models/` và có tên khớp với cấu hình trong `MODELS`.

## Tệp được chia sẻ

Đặt tệp cần chia sẻ trực tiếp vào `storage/files/`. Trang `/files` tự động hiển thị tên, định dạng, dung lượng và thời gian cập nhật của từng tệp. Thư mục con và file ẩn không được công khai.

Tệp dưới 100 MB được tải trực tiếp. Tệp từ 100 MB trở lên sử dụng chung hàng đợi tải xuống với model.

## Nộp bài tập

Trang `/upload` yêu cầu họ tên, MSSV, tên bài tập và file `.zip`. Server kiểm tra lại:

- file có tồn tại và đúng đuôi `.zip`;
- tên file không chứa đường dẫn nguy hiểm;
- file không vượt quá `MAX_UPLOAD_MB` (mặc định 200 MB);
- nội dung là ZIP hợp lệ;
- các trường thông tin bắt buộc không bị bỏ trống.

ZIP không được giải nén hoặc thực thi. Mỗi bài nộp được lưu riêng:

```text
storage/submissions/<submission_id>/
├── submission.zip
└── metadata.json
```

## Các route chính

```text
/                            Trang chủ
/download                    Trang tải model
/download/<model_id>         Tải archive model
/download/lm-studio/macos    Tải LM Studio cho macOS
/download/lm-studio/windows  Tải LM Studio cho Windows
/files                       Danh sách tệp được chia sẻ
/files/<filename>            Tải một tệp trong storage/files
/upload                      Trang nộp bài
/queue/join                  Nhận ticket tải xuống
/queue/status                Poll trạng thái/vị trí ticket
/queue/leave                 Hủy ticket và trả slot
```

## Lưu ý vận hành

- Đây là ứng dụng mạng nội bộ và chưa có xác thực người dùng.
- Cần đảm bảo đủ dung lượng cho archive model và bài nộp.
- Tốc độ tải nhiều model đồng thời phụ thuộc vào băng thông LAN, Wi-Fi và ổ đĩa máy chủ.
- Chỉ các file được khai báo rõ trong `MODELS` mới được phép tải.
