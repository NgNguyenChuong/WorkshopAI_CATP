# Model Hub

Ứng dụng web nội bộ bằng Flask để điều hướng, tải model AI/LM Studio, tải tệp được chia sẻ và nộp bài tập.

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

Trang `/upload` yêu cầu họ tên, nhóm và từ 1 đến 5 file. Có thể nộp hình ảnh, video hoặc các định dạng file khác. Server kiểm tra lại:

- mỗi lần có tối đa `MAX_UPLOAD_FILES` file (mặc định 5);
- tên file không chứa đường dẫn nguy hiểm;
- file không rỗng;
- tổng request không vượt quá `MAX_UPLOAD_MB` (mặc định 200 MB);
- các trường thông tin bắt buộc không bị bỏ trống.

Lần đầu một người dùng nộp bài, hệ thống tự cấp STT và tạo thư mục theo tên. Các lần sau có cùng họ tên và nhóm sẽ dùng lại thư mục đó. File trùng tên được thêm hậu tố `_2`, `_3`, ... thay vì ghi đè:

```text
storage/submissions/001_Nguyen_Van_An/
├── bai-lam.docx
├── video.mp4
├── video_2.mp4
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
