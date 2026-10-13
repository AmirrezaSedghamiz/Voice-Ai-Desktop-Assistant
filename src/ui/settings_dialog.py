"""
Settings Dialog for David Assistant:
Provides clear, modular configuration for Voice, Privacy, Performance, and Application behavior.
"""

import logging
from typing import Callable
import psutil
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.audio.recorder import AudioRecorder
from src.ui.config import UiConfig

logger = logging.getLogger("assistant.ui.settings")


class SettingsDialog(QDialog):
    """Configuration dialog with Voice, Privacy, Performance, and Application tabs."""

    def __init__(
        self,
        config: UiConfig,
        on_pause_wake_cb: Callable[[], None] | None = None,
        on_resume_wake_cb: Callable[[], None] | None = None,
        is_wake_paused: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.config = config
        self.on_pause_wake_cb = on_pause_wake_cb
        self.on_resume_wake_cb = on_resume_wake_cb
        self.is_wake_paused = is_wake_paused

        self.setWindowTitle("Settings - David Assistant")
        self.resize(520, 440)
        self.setMinimumSize(480, 400)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self._init_voice_tab()
        self._init_privacy_tab()
        self._init_performance_tab()
        self._init_app_tab()

        # Dialog Buttons (OK, Cancel)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _init_voice_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # Wake-word group
        ww_group = QGroupBox("Wake-Word Activation")
        ww_layout = QVBoxLayout(ww_group)

        self.ww_checkbox = QCheckBox("Enable background wake-word activation")
        self.ww_checkbox.setChecked(self.config.wake_word_enabled)
        ww_layout.addWidget(self.ww_checkbox)

        phrase_label = QLabel("Configured phrase: <b>'Activate David'</b> (Vosk Kaldi recognizer)")
        phrase_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        ww_layout.addWidget(phrase_label)

        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("Mic sensitivity:"))
        self.thresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.thresh_slider.setRange(1, 100)
        # map 0.001 - 0.05 to slider 1 - 100
        val = int(self.config.wake_energy_threshold * 2000)
        self.thresh_slider.setValue(max(1, min(100, val)))
        thresh_layout.addWidget(self.thresh_slider)
        ww_layout.addLayout(thresh_layout)

        layout.addWidget(ww_group)

        # Devices group
        dev_group = QGroupBox("Audio Devices & Voice Output")
        dev_form = QFormLayout(dev_group)
        dev_form.setSpacing(10)

        # Populate input devices
        self.input_combo = QComboBox()
        self.input_combo.addItem("System Default", None)
        devices = AudioRecorder.list_input_devices()
        current_idx = 0
        for dev in devices:
            idx = dev["index"]
            name = dev["name"]
            self.input_combo.addItem(f"[{idx}] {name}", idx)
            if self.config.input_device_index == idx:
                current_idx = self.input_combo.count() - 1
        self.input_combo.setCurrentIndex(current_idx)
        dev_form.addRow("Microphone:", self.input_combo)

        # Voice Trigger Mode
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Voice Activity Detection (Hands-Free)", "vad")
        self.mode_combo.addItem("Push-to-Talk (Manual)", "ptt")
        self.mode_combo.setCurrentIndex(0 if self.config.trigger_mode == "vad" else 1)
        dev_form.addRow("Trigger Mode:", self.mode_combo)

        # Spoken responses
        self.tts_checkbox = QCheckBox("Enable spoken voice responses (Piper TTS)")
        self.tts_checkbox.setChecked(self.config.tts_enabled)
        dev_form.addRow("", self.tts_checkbox)

        layout.addWidget(dev_group)
        layout.addStretch()
        self.tabs.addTab(tab, "Voice")

    def _init_privacy_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        # Audio Security & Boundary Group
        sec_group = QGroupBox("Privacy & Hardware Boundary")
        sec_layout = QVBoxLayout(sec_group)
        sec_layout.setSpacing(10)

        info1 = QLabel(
            "<b>100% Local Inference:</b> All speech recognition, keyword detection, "
            "LLM reasoning, and text-to-speech run entirely on this computer. "
            "No audio or text is ever sent over the internet."
        )
        info1.setWordWrap(True)
        info1.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        sec_layout.addWidget(info1)

        info2 = QLabel(
            "<b>Zero Audio Retention:</b> Microphone data is held in temporary memory buffers "
            "only during active processing and discarded immediately. No recording files are kept."
        )
        info2.setWordWrap(True)
        info2.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        sec_layout.addWidget(info2)

        layout.addWidget(sec_group)

        # Quick Control
        ctrl_group = QGroupBox("Quick Microphone Control")
        ctrl_layout = QVBoxLayout(ctrl_group)

        self.pause_btn = QPushButton("Pause Wake-Word Listening Now" if not self.is_wake_paused else "Resume Wake-Word Listening")
        self.pause_btn.setStyleSheet("padding: 8px 16px; font-weight: 600;")
        self.pause_btn.clicked.connect(self._toggle_wake_pause)
        ctrl_layout.addWidget(self.pause_btn)

        layout.addWidget(ctrl_group)
        layout.addStretch()
        self.tabs.addTab(tab, "Privacy")

    def _toggle_wake_pause(self) -> None:
        if self.is_wake_paused:
            if self.on_resume_wake_cb:
                self.on_resume_wake_cb()
            self.is_wake_paused = False
            self.pause_btn.setText("Pause Wake-Word Listening Now")
        else:
            if self.on_pause_wake_cb:
                self.on_pause_wake_cb()
            self.is_wake_paused = True
            self.pause_btn.setText("Resume Wake-Word Listening")

    def _init_performance_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        perf_group = QGroupBox("Resource Telemetry")
        perf_layout = QFormLayout(perf_group)
        perf_layout.setSpacing(12)

        cpu_pct = psutil.cpu_percent(interval=None)
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setRange(0, 100)
        self.cpu_bar.setValue(int(cpu_pct))
        perf_layout.addRow("CPU Usage:", self.cpu_bar)

        mem = psutil.virtual_memory()
        mem_gb = mem.used / (1024**3)
        total_gb = mem.total / (1024**3)
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        self.ram_bar.setValue(int(mem.percent))
        perf_layout.addRow(f"RAM ({mem_gb:.1f} GB / {total_gb:.1f} GB):", self.ram_bar)

        backend_info = QLabel("Local Qwen3 1.7B (llama-server: 127.0.0.1:8080)")
        backend_info.setStyleSheet("color: #38bdf8; font-weight: 500;")
        perf_layout.addRow("Reasoning Engine:", backend_info)

        layout.addWidget(perf_group)
        layout.addStretch()
        self.tabs.addTab(tab, "Performance")

    def _init_app_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        app_group = QGroupBox("Window & Tray Preferences")
        app_layout = QVBoxLayout(app_group)
        app_layout.setSpacing(10)

        self.tray_close_checkbox = QCheckBox("Minimize to system tray on window close")
        self.tray_close_checkbox.setChecked(self.config.minimize_to_tray_on_close)
        app_layout.addWidget(self.tray_close_checkbox)

        self.start_min_checkbox = QCheckBox("Start minimized to system tray on launch")
        self.start_min_checkbox.setChecked(self.config.start_minimized)
        app_layout.addWidget(self.start_min_checkbox)

        layout.addWidget(app_group)
        layout.addStretch()
        self.tabs.addTab(tab, "Application")

    def _save_and_accept(self) -> None:
        # Update config fields
        self.config.wake_word_enabled = self.ww_checkbox.isChecked()
        self.config.wake_energy_threshold = max(0.002, self.thresh_slider.value() / 2000.0)
        self.config.input_device_index = self.input_combo.currentData()
        self.config.trigger_mode = self.mode_combo.currentData() or "vad"
        self.config.tts_enabled = self.tts_checkbox.isChecked()
        self.config.minimize_to_tray_on_close = self.tray_close_checkbox.isChecked()
        self.config.start_minimized = self.start_min_checkbox.isChecked()

        self.config.save()
        self.accept()
