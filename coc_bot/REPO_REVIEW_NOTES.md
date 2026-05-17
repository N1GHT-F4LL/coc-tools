# Đánh giá sơ bộ repository — 2026-05-17

Mục tiêu: Bot tự động Clash of Clans (CoC) sử dụng ADB/screencap, Computer Vision và OCR.

Tóm tắt nhanh các điểm chính:

- **Mục đích repo:** Tự động hóa tương tác với CoC qua ADB, nhận diện UI và thực hiện hành động (collect, attack, train...).
- **Cấu trúc:** `core/` (device, vision, humanize, ui_manager), `screens/` (BaseScreen, HomeScreen), `assets/`, `logs/`, `main.py`.

Vấn đề chính cần lưu ý:

1. `core/device.py` có side-effect khi import: tạo instance `device = Device()` và gọi các lệnh ADB (kiểm tra, wake). Nên di chuyển khởi tạo này ra khỏi import-time để tránh hành vi không mong muốn khi import module.
2. Phương thức input hiện dùng `adb shell input` (virtual input). Đây mâu thuẫn với yêu cầu "hardware-level input" trong REQUIREMENTS.md — cần thêm tuỳ chọn scrcpy/HID hoặc minitouch.
3. `vision.load_assets()` dùng `path.stem` làm key, có thể ghi đè nếu nhiều file cùng tên ở thư mục khác nhau. Nên dùng key có namespace (ví dụ `ui/icon_attack` hoặc full relative path).
4. Template matching hiện tại là `cv2.matchTemplate` một scale cố định — dễ vỡ khi độ phân giải hoặc scale thay đổi. Cần multi-scale hoặc feature matching fallback.
5. `Humanize.bezier_curve()` chưa triển khai (trả về list rỗng) — chưa đáp ứng yêu cầu humanization (Bezier swipe).
6. `UIManager.wait_until_appears()` chưa xử lý `device.get_screen()` trả về `None` — cần kiểm tra và retry/backoff, và lưu ảnh debug khi lỗi.

Khuyến nghị ngắn hạn (hành động ưu tiên):

- Di chuyển `device = Device()` khỏi import-time; khởi tạo trong `main.py` và truyền vào `UIManager`/`Vision` khi cần.
- Thêm kiểm tra `None` sau `get_screen()` và log/ghi ảnh debug khi không lấy được màn hình.
- Sửa `vision` để key asset bao gồm relative path, tránh ghi đè tên file.
- Thêm entry `.gitignore` cho folder `coc_bot/logs/` để tránh commit ảnh PNG/bitmap runtime.

Files to ignore (đã thêm vào `.gitignore`):

- `coc_bot/logs/` (bao gồm `coc_bot/logs/debug/`)

Nếu bạn muốn, tôi có thể tiếp tục và thực hiện các sửa code nhỏ: tách khởi tạo `Device`, thêm kiểm tra `None`, và cập nhật `vision` keys. Bạn muốn tôi bắt đầu với phần nào?
