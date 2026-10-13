"""
Professional Windows Desktop Stylesheet for David Assistant.
Implements a refined, high-contrast dark theme with Segoe UI typography,
subtle borders, and clear state styling.
"""

MAIN_STYLESHEET = """
QMainWindow {
    background-color: #0f111a;
    color: #e2e8f0;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
}

QWidget {
    color: #e2e8f0;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
}

/* Header Area */
#headerWidget {
    background-color: #141724;
    border-bottom: 1px solid #232738;
    padding: 8px 16px;
}

#appTitle {
    font-size: 16px;
    font-weight: 600;
    color: #f8fafc;
    letter-spacing: 0.3px;
}

#appSubtitle {
    font-size: 11px;
    color: #94a3b8;
}

/* Status Badge */
#statusBadge {
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 500;
    border: 1px solid #334155;
    background-color: #1e293b;
    color: #94a3b8;
}

/* Conversation Scroll Area */
#conversationScroll {
    background-color: #0f111a;
    border: none;
}

#conversationContainer {
    background-color: #0f111a;
}

/* Message Bubbles */
.user-bubble {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 10px 14px;
    color: #f1f5f9;
}

.assistant-bubble {
    background-color: #161a29;
    border: 1px solid #242a3d;
    border-radius: 12px;
    padding: 12px 16px;
    color: #e2e8f0;
}

/* Input Area */
#inputContainer {
    background-color: #141724;
    border-top: 1px solid #232738;
    padding: 12px 16px;
}

#messageInput {
    background-color: #1a1e2e;
    border: 1px solid #2c3247;
    border-radius: 8px;
    padding: 8px 12px;
    color: #f8fafc;
    font-size: 13px;
    selection-background-color: #3b82f6;
}

#messageInput:focus {
    border: 1px solid #3b82f6;
    background-color: #1c2133;
}

/* Buttons */
QPushButton {
    background-color: #1e2336;
    border: 1px solid #2d334d;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
    color: #e2e8f0;
}

QPushButton:hover {
    background-color: #272d45;
    border-color: #3e4768;
}

QPushButton:pressed {
    background-color: #181b2a;
}

QPushButton:disabled {
    background-color: #131622;
    border-color: #1d2030;
    color: #64748b;
}

/* Primary Action Button (Send) */
#sendButton {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: 600;
}

#sendButton:hover {
    background-color: #1d4ed8;
    border-color: #60a5fa;
}

#sendButton:pressed {
    background-color: #1e40af;
}

#sendButton:disabled {
    background-color: #1e293b;
    border-color: #334155;
    color: #64748b;
}

/* Microphone Button */
#micButton {
    background-color: #1e2336;
    border: 1px solid #3b82f6;
    color: #60a5fa;
    font-weight: 600;
}

#micButton:hover {
    background-color: #2563eb;
    color: #ffffff;
}

#micButton[recording="true"] {
    background-color: #dc2626;
    border-color: #ef4444;
    color: #ffffff;
}

/* Cancel / Stop Button */
#stopButton {
    background-color: #451a1a;
    border: 1px solid #7f1d1d;
    color: #fca5a5;
}

#stopButton:hover {
    background-color: #7f1d1d;
    color: #ffffff;
}

#stopButton:disabled {
    background-color: #161822;
    border-color: #222636;
    color: #555b70;
}

/* Settings Dialog */
QDialog {
    background-color: #11131d;
    color: #e2e8f0;
}

QTabWidget::pane {
    border: 1px solid #232738;
    background-color: #141724;
    border-radius: 6px;
    padding: 12px;
}

QTabBar::tab {
    background-color: #11131d;
    color: #94a3b8;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    padding: 8px 16px;
    margin-right: 4px;
    font-weight: 500;
}

QTabBar::tab:selected {
    color: #f8fafc;
    border-bottom: 2px solid #3b82f6;
    background-color: #141724;
}

QTabBar::tab:hover:!selected {
    color: #cbd5e1;
    background-color: #171a28;
}

QGroupBox {
    border: 1px solid #232738;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 16px;
    font-weight: 600;
    color: #94a3b8;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}

QComboBox {
    background-color: #1a1e2e;
    border: 1px solid #2c3247;
    border-radius: 6px;
    padding: 6px 12px;
    color: #f8fafc;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #1a1e2e;
    border: 1px solid #2c3247;
    selection-background-color: #2563eb;
    color: #f8fafc;
}

QCheckBox {
    spacing: 8px;
    color: #e2e8f0;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #3b4259;
    background-color: #1a1e2e;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border-color: #3b82f6;
}

/* Sleek Scrollbars */
QScrollBar:vertical {
    border: none;
    background-color: #0f111a;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #252a3d;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: #3b4361;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
