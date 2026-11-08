from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QLineEdit, QTextEdit, QMessageBox, QProgressBar,
    QGroupBox, QFormLayout
)

APP_NAME = "AUTO VIỆT HÓA GAME"
RELEASES_API = "https://api.github.com/repos/bbepis/XUnity.AutoTranslator/releases/latest"
UPSTREAM_RELEASES = "https://github.com/bbepis/XUnity.AutoTranslator/releases"


def detect_unity(game_dir: Path) -> tuple[str, str | None]:
    """Return (runtime, game-data directory). Detection is heuristic and conservative."""
    for data_dir in game_dir.glob("*_Data"):
        if not data_dir.is_dir():
            continue
        managed = data_dir / "Managed"
        il2cpp = data_dir / "il2cpp_data"
        root_gameassembly = game_dir / "GameAssembly.dll"
        if il2cpp.exists() or root_gameassembly.exists():
            return "IL2CPP", str(data_dir)
        if managed.exists():
            return "Mono", str(data_dir)
    return "Không xác định", None


class Worker(QThread):
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, game_dir: Path):
        super().__init__()
        self.game_dir = game_dir

    def run(self):
        try:
            self.log.emit("Đang lấy metadata bản phát hành chính thức của XUnity…")
            response = requests.get(RELEASES_API, timeout=30)
            response.raise_for_status()
            release = response.json()
            assets = release.get("assets", [])
            # Use only compiled release assets. Never download the source archives.
            candidates = [
                a for a in assets
                if "reipatcher" in a.get("name", "").lower()
                and a.get("name", "").lower().endswith(".zip")
            ]
            if not candidates:
                raise RuntimeError(
                    "Không tìm thấy gói ReiPatcher ZIP trong release mới nhất. "
                    "Mở trang Releases để kiểm tra thủ công."
                )
            asset = candidates[0]
            self.log.emit(f"Đã chọn gói nhị phân: {asset['name']}")
            with tempfile.TemporaryDirectory(prefix="autoviethoa_") as tmp:
                archive = Path(tmp) / "plugin.zip"
                self.log.emit("Đang tải gói từ GitHub Releases (không tải source code)…")
                with requests.get(asset["browser_download_url"], stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with archive.open("wb") as f:
                        for chunk in r.iter_content(1024 * 256):
                            if chunk:
                                f.write(chunk)
                extract = Path(tmp) / "extract"
                extract.mkdir()
                with zipfile.ZipFile(archive) as zf:
                    # Reject path traversal entries.
                    for item in zf.infolist():
                        target = (extract / item.filename).resolve()
                        if extract.resolve() not in target.parents and target != extract.resolve():
                            raise RuntimeError("Gói ZIP chứa đường dẫn không an toàn; đã hủy.")
                    zf.extractall(extract)

                # Back up every destination file before replacing it.
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                backup_root = self.game_dir / "AutoVietHoa_Backups" / stamp
                manifest = []
                files = [p for p in extract.rglob("*") if p.is_file()]
                if not files:
                    raise RuntimeError("Gói tải về không chứa tệp cài đặt.")
                for src in files:
                    rel = src.relative_to(extract)
                    dest = self.game_dir / rel
                    if dest.exists():
                        if dest.is_dir():
                            raise RuntimeError(f"Không thể ghi đè thư mục: {dest}")
                        backup = backup_root / rel
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(dest, backup)
                        manifest.append({"path": str(rel), "backup": str(backup.relative_to(self.game_dir))})
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)

                state_dir = self.game_dir / "AutoVietHoa_Backups"
                state_dir.mkdir(exist_ok=True)
                state_file = state_dir / f"install-{stamp}.json"
                state_file.write_text(json.dumps({
                    "installed_at": stamp, "release": release.get("tag_name"),
                    "asset": asset["name"], "backup_dir": str(backup_root.relative_to(self.game_dir)),
                    "overwritten": manifest, "installed_files": [str(p.relative_to(extract)) for p in files]
                }, ensure_ascii=False, indent=2), encoding="utf-8")

                # Launch known ReiPatcher setup helpers only after explicit user action in UI
                # is not possible from this background worker. The user can run it from Explorer.
                helpers = list(self.game_dir.glob("Setup*.exe")) + list(self.game_dir.glob("Setup*.bat"))
                msg = "Đã chép gói và tạo bản sao lưu. "
                if helpers:
                    msg += "Tìm thấy trình cài đặt: " + ", ".join(p.name for p in helpers)
                else:
                    msg += "Không thấy Setup helper ở thư mục gốc; xem nội dung gói và hướng dẫn upstream."
                self.done.emit(True, msg)
        except Exception as exc:
            self.done.emit(False, str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(900, 650)
        self.game_dir: Path | None = None
        self.worker = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("AUTO VIỆT HÓA GAME")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel("Trình quản lý cài đặt XUnity AutoTranslator cho game Unity — tải gói phát hành, không tải mã nguồn.")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        group = QGroupBox("1. Chọn thư mục game")
        form = QFormLayout(group)
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Chọn thư mục chứa file .exe của game…")
        browse = QPushButton("Duyệt…")
        browse.clicked.connect(self.choose_folder)
        row.addWidget(self.path_edit)
        row.addWidget(browse)
        form.addRow("Đường dẫn:", row)
        self.detect_label = QLabel("Chưa quét")
        form.addRow("Engine:", self.detect_label)
        layout.addWidget(group)

        actions = QGroupBox("2. Cài đặt và quản lý")
        action_layout = QVBoxLayout(actions)
        buttons = QHBoxLayout()
        self.install_btn = QPushButton("Tải & cài XUnity")
        self.install_btn.clicked.connect(self.install)
        self.open_translation_btn = QPushButton("Mở thư mục bản dịch")
        self.open_translation_btn.clicked.connect(self.open_translation)
        self.rollback_btn = QPushButton("Hoàn tác cài đặt gần nhất")
        self.rollback_btn.clicked.connect(self.rollback)
        buttons.addWidget(self.install_btn)
        buttons.addWidget(self.open_translation_btn)
        buttons.addWidget(self.rollback_btn)
        action_layout.addLayout(buttons)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        action_layout.addWidget(self.progress)
        layout.addWidget(actions)

        guide = QLabel(
            "Lưu ý: bản MVP chỉ tự động cài gói ReiPatcher cho Unity Mono. "
            "IL2CPP được nhận diện nhưng chưa tự cài vì cần gói/runtime tương thích riêng. "
            "Không dùng với game online có anti-cheat. Việc dịch tự động cần endpoint dịch; "
            "bản thân XUnity không kèm mô hình dịch offline chất lượng cao."
        )
        guide.setWordWrap(True)
        guide.setStyleSheet("color: #b36b00; padding: 8px;")
        layout.addWidget(guide)

        layout.addWidget(QLabel("Nhật ký hoạt động"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)
        self.log("Sẵn sàng. Chọn thư mục game Unity để bắt đầu.")

    def log(self, message: str):
        self.log_view.append(message)

    def choose_folder(self):
        selected = QFileDialog.getExistingDirectory(self, "Chọn thư mục game")
        if not selected:
            return
        self.game_dir = Path(selected)
        self.path_edit.setText(selected)
        runtime, data_dir = detect_unity(self.game_dir)
        self.detect_label.setText(f"{runtime}" + (f" — {Path(data_dir).name}" if data_dir else ""))
        self.log(f"Đã chọn: {selected}")
        if runtime == "IL2CPP":
            self.log("Phát hiện IL2CPP: không cài gói Mono. Hỗ trợ IL2CPP đang để ngoài MVP.")
        elif runtime == "Không xác định":
            self.log("Không nhận diện được cấu trúc Unity tiêu chuẩn. Hãy chọn đúng thư mục game.")

    def install(self):
        if not self.game_dir or not self.game_dir.exists():
            QMessageBox.warning(self, "Thiếu thư mục", "Hãy chọn thư mục game trước.")
            return
        runtime, _ = detect_unity(self.game_dir)
        if runtime != "Mono":
            QMessageBox.warning(self, "Chưa hỗ trợ", f"Engine nhận diện: {runtime}. MVP chỉ cài cho Unity Mono.")
            return
        answer = QMessageBox.question(
            self, "Xác nhận cài đặt",
            "Ứng dụng sẽ tải gói nhị phân từ GitHub Releases và chép vào thư mục game. "
            "Các tệp bị ghi đè sẽ được sao lưu. Bạn có muốn tiếp tục?",
            QMessageBox.Yes | QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        self.install_btn.setEnabled(False)
        self.progress.show()
        self.worker = Worker(self.game_dir)
        self.worker.log.connect(self.log)
        self.worker.done.connect(self.install_finished)
        self.worker.start()

    def install_finished(self, ok: bool, message: str):
        self.progress.hide()
        self.install_btn.setEnabled(True)
        self.log(message)
        if ok:
            QMessageBox.information(self, "Hoàn tất", message)
        else:
            QMessageBox.critical(self, "Cài đặt thất bại", message)

    def open_translation(self):
        if not self.game_dir:
            QMessageBox.warning(self, "Chưa chọn game", "Hãy chọn thư mục game.")
            return
        candidates = [
            self.game_dir / "Translation",
            self.game_dir / "BepInEx" / "Translation",
            self.game_dir / "AutoTranslator"
        ]
        target = next((p for p in candidates if p.exists()), self.game_dir)
        os.startfile(str(target)) if os.name == "nt" else subprocess.Popen(["xdg-open", str(target)])

    def rollback(self):
        if not self.game_dir:
            QMessageBox.warning(self, "Chưa chọn game", "Hãy chọn thư mục game.")
            return
        state_dir = self.game_dir / "AutoVietHoa_Backups"
        states = sorted(state_dir.glob("install-*.json"), reverse=True) if state_dir.exists() else []
        if not states:
            QMessageBox.information(self, "Không có bản sao lưu", "Không tìm thấy lịch sử cài đặt.")
            return
        state_file = states[0]
        state = json.loads(state_file.read_text(encoding="utf-8"))
        if QMessageBox.question(self, "Xác nhận hoàn tác", f"Hoàn tác lần cài {state.get('installed_at')}?") != QMessageBox.Yes:
            return
        # Restore overwritten files. Newly installed files are removed only if still present.
        for rel in state.get("installed_files", []):
            target = self.game_dir / rel
            if target.is_file():
                target.unlink()
        for item in state.get("overwritten", []):
            backup = self.game_dir / item["backup"]
            target = self.game_dir / item["path"]
            if backup.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
        self.log(f"Đã hoàn tác theo manifest: {state_file.name}")
        QMessageBox.information(self, "Hoàn tất", "Đã khôi phục các tệp được ghi đè và xóa tệp cài mới theo manifest.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
