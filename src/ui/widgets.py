"""
Custom UI Widgets for David Desktop Assistant:
- ChatBubbleWidget: Clean message bubbles with bi-directional Persian (RTL) / English (LTR) formatting.
- StatusBadgeWidget: Clear, accessible indicator for voice and processing states.
- EmptyStateWidget: Helpful onboarding suggestions for supported capabilities.
"""

import html
import re
from typing import Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

PERSIAN_CHAR_REGEX = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def is_persian_text(text: str) -> bool:
    """Detects whether text contains Persian/Arabic characters."""
    return bool(PERSIAN_CHAR_REGEX.search(text))


def format_chat_html(text: str, is_persian: bool) -> str:
    """
    Formats message content for rich text rendering.
    Enforces correct directionality (RTL for Persian, LTR for English),
    while preserving code spans and technical terms strictly in LTR.
    """
    # Escape raw HTML
    escaped = html.escape(text)

    # Protect inline code blocks `code` to remain strictly LTR monospace
    def replace_code(match):
        code_content = match.group(1)
        return (
            f'<code dir="ltr" style="font-family: Consolas, monospace; '
            f'background-color: #23283b; color: #38bdf8; padding: 2px 5px; '
            f'border-radius: 4px; font-size: 12px;">{code_content}</code>'
        )

    formatted = re.sub(r"`([^`]+)`", replace_code, escaped)

    # Convert newlines to HTML breaks
    formatted = formatted.replace("\n", "<br>")

    direction = "rtl" if is_persian else "ltr"
    align = "right" if is_persian else "left"
    font_family = "Tahoma, 'Segoe UI', sans-serif" if is_persian else "'Segoe UI', sans-serif"

    return (
        f'<div dir="{direction}" style="text-align: {align}; direction: {direction}; '
        f'font-family: {font_family}; font-size: 13px; line-height: 1.5; color: #f1f5f9;">'
        f'{formatted}'
        f'</div>'
    )


class ChatBubbleWidget(QFrame):
    """Message bubble supporting copyable text, RTL/LTR layout, and tool execution badges."""

    def __init__(
        self,
        sender: str,  # "user" | "assistant" | "system"
        text: str,
        tool_info: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.sender = sender
        self.raw_text = text
        self.is_persian = is_persian_text(text)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header: Sender label & direction tag
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        sender_label = QLabel()
        sender_label.setStyleSheet("font-size: 11px; font-weight: 600; text-transform: uppercase;")
        if sender == "user":
            sender_label.setText("You")
            sender_label.setStyleSheet(sender_label.styleSheet() + " color: #60a5fa;")
            self.setStyleSheet(
                "ChatBubbleWidget { background-color: #1a2238; border: 1px solid #2d3b5e; border-radius: 10px; }"
            )
        elif sender == "assistant":
            sender_label.setText("David")
            sender_label.setStyleSheet(sender_label.styleSheet() + " color: #34d399;")
            self.setStyleSheet(
                "ChatBubbleWidget { background-color: #141724; border: 1px solid #232738; border-radius: 10px; }"
            )
        else:
            sender_label.setText("System")
            sender_label.setStyleSheet(sender_label.styleSheet() + " color: #94a3b8;")
            self.setStyleSheet(
                "ChatBubbleWidget { background-color: #11131d; border: 1px dashed #334155; border-radius: 8px; }"
            )

        header_layout.addWidget(sender_label)
        header_layout.addStretch()

        if self.is_persian:
            lang_badge = QLabel("FA")
            lang_badge.setStyleSheet(
                "font-size: 10px; color: #94a3b8; background-color: #1e293b; "
                "border-radius: 3px; padding: 1px 4px;"
            )
            header_layout.addWidget(lang_badge)

        layout.addLayout(header_layout)

        # Message body: QTextBrowser for copyable, select-friendly rich text
        self.browser = QTextBrowser()
        self.browser.setHtml(format_chat_html(text, self.is_persian))
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet("background: transparent; border: none; padding: 0px;")
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # Adjust height based on document contents
        self.browser.document().contentsChanged.connect(self._adjust_height)
        layout.addWidget(self.browser)

        # Optional tool badge
        if tool_info:
            tool_badge = QLabel(f"Tool: {tool_info}")
            tool_badge.setStyleSheet(
                "background-color: #1e293b; color: #38bdf8; font-size: 11px; "
                "padding: 3px 8px; border-radius: 4px; border: 1px solid #334155;"
            )
            layout.addWidget(tool_badge)

    def _adjust_height(self) -> None:
        doc = self.browser.document()
        doc.setTextWidth(self.browser.viewport().width())
        h = int(doc.size().height()) + 8
        self.browser.setFixedHeight(max(24, h))


class StatusBadgeWidget(QLabel):
    """Truthful status indicator with accessible text and clear visual styling."""

    STATES = {
        "idle": ("Idle", "#475569", "#1e293b", "#334155"),
        "wake_listening": ("Listening for 'Activate David'", "#10b981", "#064e3b", "#059669"),
        "wake_detected": ("Wake Phrase Detected!", "#34d399", "#065f46", "#10b981"),
        "recording": ("Recording Request...", "#ef4444", "#450a0a", "#dc2626"),
        "transcribing": ("Transcribing Speech...", "#a855f7", "#3b0764", "#9333ea"),
        "thinking": ("Processing Request...", "#3b82f6", "#172554", "#2563eb"),
        "speaking": ("Speaking Response...", "#06b6d4", "#083344", "#0891b2"),
        "muted": ("Microphone Muted", "#f59e0b", "#451a03", "#d97706"),
        "error": ("Microphone Unavailable", "#f87171", "#450a0a", "#b91c1c"),
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("statusBadge")
        self.set_state("idle")

    def set_state(self, state_key: str, custom_text: str | None = None) -> None:
        label_text, text_color, bg_color, border_color = self.STATES.get(
            state_key, ("Ready", "#94a3b8", "#1e293b", "#334155")
        )
        if custom_text:
            label_text = custom_text

        self.setText(label_text)
        self.setStyleSheet(
            f"border-radius: 12px; padding: 4px 12px; font-size: 12px; font-weight: 600; "
            f"color: {text_color}; background-color: {bg_color}; border: 1px solid {border_color};"
        )


class EmptyStateWidget(QWidget):
    """Empty conversation placeholder with capability suggestion cards."""

    suggestion_clicked = Signal(str)

    SUGGESTIONS = [
        "What can you do on my system?",
        "Remind me to take a break in 30 minutes",
        "Open Notepad",
        "How much battery and CPU do I have left?",
        "لیست کارهای من رو نشون بده",
    ]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 40, 24, 40)

        title = QLabel("David")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #f8fafc; letter-spacing: 0.5px;")
        layout.addWidget(title)

        subtitle = QLabel("Fully local, offline AI assistant with voice and task automation")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px; color: #94a3b8;")
        layout.addWidget(subtitle)

        hint = QLabel("Say 'Activate David' or click a suggested request below:")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 12px; color: #64748b; margin-top: 10px;")
        layout.addWidget(hint)

        # Suggestion cards
        card_container = QVBoxLayout()
        card_container.setSpacing(8)
        for text in self.SUGGESTIONS:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 10px 16px; background-color: #161a29; "
                "border: 1px solid #23283c; border-radius: 8px; color: #cbd5e1; font-size: 12px; } "
                "QPushButton:hover { background-color: #1e243b; border-color: #3b82f6; color: #f8fafc; }"
            )
            btn.clicked.connect(lambda checked=False, t=text: self.suggestion_clicked.emit(t))
            card_container.addWidget(btn)

        layout.addLayout(card_container)
