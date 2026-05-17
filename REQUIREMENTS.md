# UPDATED REQUIREMENTS: CLASH OF CLANS AUTO BOT (PRO VERSION)

## 1. Project Overview
- **Name:** CoC Master Auto Bot
- **Purpose:** Xây dựng một hệ thống tự động hóa chơi game Clash of Clans (CoC) qua ADB/Scrcpy hoạt động 24/7, an toàn tuyệt đối (Anti-ban), hiệu năng cao và có khả năng ra quyết định theo thời gian thực (Real-time decision making).
- **Architecture Pattern:** Sử dụng mô hình **Screen Object Model** kết hợp với **Task Queue** (thay vì cấu trúc kịch bản YAML tĩnh). Phân tách rõ ràng giữa Core (Động cơ), Screens (Giao diện), Tasks (Nhiệm vụ) và Config (Cài đặt).

## 2. Technical Stack
- **Ngôn ngữ:** Python 3.9+
- **Thao tác thiết bị:** `scrcpy-client` / `pure-python-adb` (Ưu tiên giao thức HID của scrcpy hoặc `minitouch` để gửi lệnh cảm ứng đa điểm cấp độ phần cứng, tuyệt đối hạn chế dùng `adb shell input` để tránh bị nhà phát hành phát hiện).
- **Computer Vision:** `opencv-python` (Nhận diện UI tĩnh), `numpy`.
- **OCR:** `easyocr` hoặc `pytesseract` (Đọc tài nguyên, cấp độ lính).
- **Cấu hình:** `json` (Chứa biến số, không chứa logic).

## 3. Directory Structure (Cấu trúc thư mục yêu cầu)
Dự án phải tuân thủ nghiêm ngặt cấu trúc sau:
```text
coc_bot/
├── main.py                 # Điểm khởi chạy (Bot Brain)
├── settings.json           # Cấu hình biến số (gold threshold, delays...)
├── core/                   # [ENGINE]
│   ├── device.py           # Kết nối thiết bị (Scrcpy/ADB), lấy ảnh 30-60FPS.
│   ├── vision.py           # Template matching (có Cache trên RAM), OCR.
│   ├── humanize.py         # Anti-ban: Bezier curve swipe, Jitter tap, random delay.
│   └── ui_manager.py       # Wrapper API (click, wait_until_appears, click_if_exists).
├── screens/                # [SCREEN OBJECTS]
│   ├── base_screen.py      # Class gốc, chứa logic xử lý popup, reconnect.
│   ├── home_screen.py      # Xử lý: Thu hoạch, mở menu, nâng cấp.
│   ├── battle_screen.py    # Xử lý: Đọc tài nguyên, thả quân, end battle.
│   └── train_screen.py     # Xử lý: Quick train, kiểm tra số lượng lính.
├── tasks/                  # [TASK QUEUE]
│   ├── farm_task.py        # Logic: Quét nhà (Next) -> Thỏa mãn -> Đánh.
│   ├── daily_task.py       # Logic: Xin lính, thu thập tài nguyên.
├── assets/                 # [RESOURCES]
│   ├── ui/                 # Ảnh các nút (btn_next, btn_attack, btn_close).
│   └── buildings/          # Ảnh mỏ vàng, kho chứa.
└── logs/                   # Log chạy và save lỗi.
```

## 4. Core Features & Optimizations (Yêu cầu bắt buộc khi code)

### 4.1. Core & Performance (Tốc độ)
- **FR-01 Fast Screencap:** Trích xuất khung hình qua Scrcpy/Bộ nhớ đệm thay vì ghi file cứng. Đảm bảo tốc độ quét tối thiểu 10 FPS.
- **FR-02 Asset Caching:** Khi khởi tạo hệ thống, toàn bộ ảnh trong thư mục assets/ phải được load sẵn vào RAM dưới dạng Dictionary để OpenCV xử lý tức thì, cấm dùng cv2.imread() trong vòng lặp game.
- **FR-03 Smart Waiting:** Thay vì dùng time.sleep(), hệ thống bắt buộc dùng ui_manager.wait_until_appears(image, timeout). Đang chờ mà thấy ảnh thì đi tiếp luôn.

### 4.2. Anti-Ban & Humanization (Chống phát hiện)
- **FR-04 Human Jitter:** Mọi thao tác tap(x, y) phải được cộng/trừ ngẫu nhiên một khoảng radius (ví dụ ±5 pixel). Không bao giờ tap đúng tâm.
- **FR-05 Hardware-level Input:** Gửi thao tác qua HID của Scrcpy hoặc chèn trực tiếp vào /dev/input/event (Minitouch). Tránh xa cờ "Virtual Input" của ADB.
- **FR-06 Bezier Swipe:** Khi thả quân thành dải (Line drop), tọa độ vuốt không được là một đường thẳng toán học. Phải có độ cong ngẫu nhiên và vận tốc thay đổi (chậm-nhanh-chậm).
- **FR-07 Non-linear Delays:** Khoảng thời gian giữa các hành động phải được sinh ngẫu nhiên random.uniform(min, max) lấy từ settings.json.

### 4.3. Screen Object Model (Tầng Giao diện)
- **FR-08 Screen Identification:** Mỗi class trong screens/ phải có một hàm is_current_screen() để xác nhận môi trường hiện tại dựa trên các Anchor Image (ví dụ: màn hình Home phải có nút Shop).
- **FR-09 Popup Handling:** BaseScreen phải chứa hàm close_popups() liên tục quét các nút [X] hoặc [Okay] ẩn để dọn dẹp màn hình trước khi làm tác vụ chính.

### 4.4. Tasks & Bot Brain (Tầng Logic)
- **FR-10 Variable Isolation:** Các thông số quyết định như (tối thiểu vàng đi cướp: 500,000, tên loại lính cần train) không được viết cứng vào file Python, phải đọc từ settings.json.
- **FR-11 Fail-safe Recovery:** Nếu Bot nhận diện mình đang ở một màn hình "Lạ" (không xác định được), nó phải chụp màn hình lưu vào folder logs/debug/ và thử bấm nút Back hoặc Restart game để khôi phục trạng thái.
- **FR-12 State Machine Loop:** Main loop trong main.py sẽ xoay vòng các tác vụ: Khôi phục kết nối (nếu đứt) -> Đóng popup -> Chạy Daily Task (Thu hoạch, Xin lính) -> Chạy Farm Task (Nếu quân đầy).

## 5. Development Instructions for AI Code Generator
Hãy bắt đầu code dự án theo thứ tự sau:

1. **Milestone 1:** Khởi tạo cấu trúc thư mục, tạo file settings.json. Code thư mục core/ (Bao gồm device.py với tính năng chụp màn hình RAM + vision.py có Asset Caching + ui_manager.py chứa Smart Waiting & Jitter).
2. **Milestone 2:** Viết BaseScreen và HomeScreen để bot tự nhận diện đang ở nhà chính và thực hiện hàm thu hoạch Vàng/Elixir.