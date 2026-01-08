import sys
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QSlider, QTextEdit
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve

class DebugFooter(QFrame):
    def __init__(self, height=100):
        super().__init__()
        self.setFixedHeight(height)
        self.setStyleSheet("background-color: black; border: none;")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(5)

        # --- Top line: label + slider
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel("---> Debug Info (Staff Only) :")
        self.label.setFixedHeight(20)
        self._set_label_style("blue")
        self.label.setStyleSheet("background-color: black; color: blue; font-size: 18px; font-family: Consolas, monospace;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(0)
        self.slider.setFixedHeight(10)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 2px;
                background: #ccc;  /* bright gray */
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                background: #ccc;  /* bright gray */
                width: 6px;
                margin: -4px 0;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #ccc;  /* bright gray */
                border-radius: 1px;
            }
            QSlider::add-page:horizontal {
                background: #333;
                border-radius: 1px;
            }
        """)


        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)

        top_layout.addWidget(self.label, 1)
        top_layout.addWidget(self.slider, 3)

        # --- Bottom: Text area for logs
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: black; color: lime; font-family: Consolas; font-size: 12px;")

        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.log_area)

        self.setLayout(main_layout)

        self.user_seeking = False
        self.seek_callback = None
        self.slider.setVisible(False)

        # --- Fade-in effect for slider ---
        self.slider_opacity = QGraphicsOpacityEffect()
        self.slider.setGraphicsEffect(self.slider_opacity)
        self.slider_opacity.setOpacity(0)

        self.slider_fade_in = QPropertyAnimation(self.slider_opacity, b"opacity")
        self.slider_fade_in.setDuration(600)  # Duration in ms
        self.slider_fade_in.setStartValue(0)
        self.slider_fade_in.setEndValue(1)
        self.slider_fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)


        # Redirect stdout and stderr
        sys.stdout = self
        sys.stderr = self
        
    def show_slider_with_animation(self):
        self.slider.setVisible(True)
        self.slider_opacity.setOpacity(0)  # Reset opacity
        self.slider_fade_in.start()

    def write(self, message):
        if not message.strip():
            return
        self.log_area.append(message.strip())
        self.log_area.verticalScrollBar().setValue(
            self.log_area.verticalScrollBar().maximum()
        )

    def flush(self):
        pass

    def show_message(self, text, color="white"):
        self.label.setText(text)
        self._set_label_style(color)

    def _set_label_style(self, color):
        self.label.setStyleSheet(f"""
            color: {color};
            font-size: 20px;
            font-family: Consolas, monospace;
        """)

    def set_max_duration(self, seconds):
        self.slider.setMaximum(int(seconds * 1000))

    def update_slider_position(self, ms):
        if not self.user_seeking:
            self.slider.setValue(ms)

    def _on_slider_moved(self, value):
        if self.seek_callback:
            self.seek_callback(value / 1000.0)

    def _on_slider_pressed(self):
        self.user_seeking = True

    def _on_slider_released(self):
        self.user_seeking = False
