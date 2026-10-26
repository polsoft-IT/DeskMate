import sys
import json
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QPushButton,
    QLineEdit, QHBoxLayout, QFrame, QMessageBox
)
from PyQt6.QtGui import QClipboard, QFont, QIcon, QPixmap, QPainter, QColor, QBrush
from PyQt6.QtCore import Qt, QSize

# Default character set (5x5 grid)
DEFAULT_CHARS = [
    '™', '№', '₠', '₧', '§',
    '©', '®', '℗', '✓', '✕',
    '⌁', '↯', '♪', '∞', '↳',
    '⌜', '⌝', '⌞', '⌟', '±',
    '‼', '⁇', '⁈', '←', '→'
]
SETTINGS_FILE = "character_settings.json"

class CharacterPicker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Character Picker")
        # Create and set window icon
        self.setWindowIcon(self.create_icon())
        self.setFixedSize(280, 330)  # Absolute minimum size
        self.editing_mode = False
        self.edit_widgets = []
        self.chars = self.load_settings()
        self.char_buttons = []
        self.init_ui()
    
    def create_icon(self):
        """Create a simple custom icon for the window"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background circle
        painter.setBrush(QBrush(QColor("#2c3e50")))
        painter.setPen(Qt.GlobalColor.transparent)
        painter.drawEllipse(4, 4, 56, 56)
        
        # Draw a character symbol (simple '™' inspired icon)
        painter.setPen(QColor("#ecf0f1"))
        painter.setFont(QFont('Arial', 28, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "™")
        painter.end()
        
        return QIcon(pixmap)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QGridLayout(central_widget)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # Create 5x5 character grid
        font = QFont('Arial', 20)
        for i in range(5):
            for j in range(5):
                idx = i * 5 + j
                char = self.chars[idx]
                btn = QPushButton(char)
                btn.setFont(font)
                btn.setFixedSize(42, 42)
                btn.clicked.connect(lambda checked, index=idx: self.on_char_click(index))
                main_layout.addWidget(btn, i, j)
                self.char_buttons.append(btn)

        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator, 5, 0, 1, 5)

        # Toolbar - centered layout
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        toolbar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Edit/Save button
        self.edit_btn = QPushButton("✏️ Edit")
        self.edit_btn.setFixedHeight(26)
        self.edit_btn.clicked.connect(self.toggle_edit_mode)
        toolbar.addWidget(self.edit_btn)

        # Cancel button (initially hidden)
        self.cancel_btn = QPushButton("❌ Cancel")
        self.cancel_btn.setFixedHeight(26)
        self.cancel_btn.clicked.connect(self.cancel_edit_mode)
        self.cancel_btn.hide()
        toolbar.addWidget(self.cancel_btn)

        # Character Map button
        self.charmap_btn = QPushButton("⌨️ Character Map")
        self.charmap_btn.setFixedHeight(26)
        self.charmap_btn.clicked.connect(self.open_system_charmap)
        toolbar.addWidget(self.charmap_btn)

        # Add toolbar to main layout with minimal spacing
        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar)
        main_layout.addWidget(toolbar_widget, 6, 0, 1, 5)
        main_layout.setVerticalSpacing(6)

    def load_settings(self):
        """Load saved characters from settings file or use defaults"""
        settings_path = Path(SETTINGS_FILE)
        if settings_path.exists():
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    if isinstance(saved, list) and len(saved) == 25:
                        return saved
            except:
                pass
        return DEFAULT_CHARS.copy()

    def save_settings(self):
        """Save current characters to settings file"""
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.chars, f, ensure_ascii=False, indent=2)

    def on_char_click(self, index):
        """Copy character to clipboard when clicked"""
        if not self.editing_mode:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.chars[index])

    def toggle_edit_mode(self):
        """Toggle edit mode on/off"""
        self.editing_mode = not self.editing_mode
        
        if self.editing_mode:
            # Enter edit mode
            self.edit_widgets = []
            # Hide character buttons and create edit fields
            for i, btn in enumerate(self.char_buttons):
                btn.hide()
                # Create edit field
                edit = QLineEdit(self.chars[i])
                edit.setMaxLength(1)
                edit.setFixedSize(42, 42)
                edit.setFont(QFont('Arial', 20))
                edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
                # Find the main layout and replace the button
                main_layout = self.centralWidget().layout()
                main_layout.addWidget(edit, i//5, i%5)
                self.edit_widgets.append(edit)
            
            # Update UI
            self.edit_btn.setText("💾 Save")
            self.cancel_btn.show()
            self.charmap_btn.hide()
        else:
            # Exit edit mode - save changes
            new_chars = []
            valid = True
            for edit in self.edit_widgets:
                text = edit.text().strip()
                if text:
                    new_chars.append(text)
                else:
                    valid = False
                    break
            
            if not valid:
                QMessageBox.warning(self, "Warning", "All fields must contain a character!")
                return
            
            # Update characters and save
            self.chars = new_chars
            self.save_settings()
            
            # Restore buttons
            for i, edit in enumerate(self.edit_widgets):
                edit.deleteLater()
                self.char_buttons[i].setText(self.chars[i])
                self.char_buttons[i].show()
            
            # Reset UI
            self.editing_mode = False
            self.edit_widgets = []
            self.edit_btn.setText("✏️ Edit")
            self.cancel_btn.hide()
            self.charmap_btn.show()

    def cancel_edit_mode(self):
        """Cancel edit mode - restore original values without saving"""
        # Destroy all edit widgets and restore original buttons
        for i, edit in enumerate(self.edit_widgets):
            edit.deleteLater()
            self.char_buttons[i].setText(self.chars[i])
            self.char_buttons[i].show()
        
        # Reset UI state
        self.editing_mode = False
        self.edit_widgets = []
        self.edit_btn.setText("✏️ Edit")
        self.cancel_btn.hide()
        self.charmap_btn.show()

    def open_system_charmap(self):
        """Open Windows system character map (charmap.exe)"""
        try:
            subprocess.Popen(["charmap.exe"], creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open Character Map: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CharacterPicker()
    window.show()
    sys.exit(app.exec())