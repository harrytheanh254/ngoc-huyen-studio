# Ngoc Huyen Studio

**TTS Studio local cho giọng Ngọc Huyền (Piper TTS)** — Chạy hoàn toàn offline, không API, không phí.

## Tính năng
- 🎤 **Text-to-Speech** tiếng Việt giọng Ngọc Huyền (Piper TTS)
- 📝 **Quét từ vay** tự động + kho từ điển động do người dùng quản lý
- 🎬 **Tạo video** từ ảnh + audio + text overlay
- 📁 **Quản lý sản phẩm**: preview (tự xóa >15 ngày), lưu trữ, tải về, đổi tên, gộp file
- 🌐 **Giao diện web** kiểu Vbee Studio — chạy tại `http://127.0.0.1:5000`

## Yêu cầu
- Windows 10/11
- Kết nối internet (lần đầu chạy setup để tải Python, ffmpeg, piper-tts, voice model)

## Cài đặt (Một lần)

### Cách 1: Chạy setup tự động (Khuyên dùng)
```cmd
setup.bat
```
Setup sẽ:
1. Tạo thư mục `%USERPROFILE%\NgocHuyenStudio`
2. Tải & cài Python embeddable
3. Tải & cài ffmpeg
4. Cài `piper-tts` qua pip
5. Tải voice model `ngoc_huyen.onnx` (cần link - xem dưới)
6. Copy toàn bộ source code
7. Tạo shortcut **Ngoc Huyen Studio** trên Desktop

> **Lưu ý voice model**: File `ngoc_huyen.onnx` (~60MB) là model custom của LO.
> Cung cấp link qua tham số:
> ```cmd
> setup.bat /voice "https://your-storage.com/ngoc_huyen.onnx"
> ```
> (File `.json` config sẽ tự tải nếu có `.json` cùng tên)

### Cách 2: Thủ công (nếu setup lỗi)
1. Cài Python 3.12+ → thêm vào PATH
2. Cài ffmpeg → thêm vào PATH
3. `pip install flask flask-cors piper-tts`
4. Copy thư mục `pipeline/`, `templates/`, `static/`, `app.py`, `start.bat` vào thư mục cài đặt
5. Tải voice model `ngoc_huyen.onnx` + `.json` vào thư mục `piper/`
6. Chạy `start.bat`

## Chạy
- Click shortcut **Ngoc Huyen Studio** trên Desktop
- Hoặc chạy `start.bat` trong thư mục cài đặt
- Mở trình duyệt: `http://127.0.0.1:5000`

## Cấu trúc thư mục
```
NgocHuyenStudio/
├── python/              # Python embeddable + pip
├── ffmpeg/              # ffmpeg binaries
├── piper/               # ngoc_huyen.onnx + .json
├── pipeline/            # Mã nguồn TTS (tts_ngochuyen.py, loanwords_*.py, vietnamize.py)
├── app.py               # Flask server
├── templates/           # HTML (index.html)
├── static/              # CSS/JS (nếu có)
├── data/                # loanwords_dynamic.json (kho từ người dùng)
├── preview/             # Audio tạm — TỰ XÓA >15 NGÀY
├── san-pham/            # Audio đã lưu (bền vững)
├── upload_images/       # Ảnh upload cho video
├── video_output/        # Video đã render
├── start.bat            # Launcher (chạy server + mở browser)
└── setup.bat            # Installer
```

## Giao diện
- **Chuyển văn bản**: Nhập text → cài đặt speed/pause/EQ → Tạo audio
- **Sản phẩm**: Danh sách audio preview, tải về, đổi tên, xóa, gộp
- **Kho từ đọc**: Quét từ vay → sửa cách đọc → thêm vào kho
- **Tạo video**: Upload ảnh → chọn audio → ghi text overlay → render MP4
- **Cài đặt**: Speed, pause, EQ, volume, pitch

## Voice Model
File `ngoc_huyen.onnx` + `ngoc_huyen.onnx.json` **KHÔNG** có sẵn trong repo (quá lớn & private).
- Đặt vào thư mục `piper/` trước khi chạy
- Hoặc cung cấp link khi chạy setup:
  ```cmd
  setup.bat /voice "https://your-link/ngoc_huyen.onnx"
  ```

## Loanwords (Kho từ đọc)
- **loanwords_vi.py**: 285+ từ cứng (sex→sét, anime→a ni me, cosplay→cót lay...)
- **loanwords_dynamic.json**: Rỗng ban đầu — người dùng tự quét & thêm
- Quét chỉ lấy từ ≥3 ký tự, bỏ từ chức năng tiếng Anh (the, and, is, to...)

## Tự động dọn dẹp
- Thư mục `preview/`: File audio **tự động xóa sau 15 ngày**
- Thư mục `san-pham/`: Giữ vĩnh viễn (người dùng quản lý)

## Build từ source (Dev)
```cmd
git clone https://github.com/khangglenn/ngoc-huyen-studio.git
cd ngoc-huyen-studio
setup.bat /voice "https://your-storage/ngoc_huyen.onnx"
```

## License
Private use only. Voice model thuộc sở hữu LO.

## Credits
- **Piper TTS**: https://github.com/rhasspy/piper
- **Ngoc Huyen voice**: Custom trained by LO
- **VBEE phonetic rules**: LO design