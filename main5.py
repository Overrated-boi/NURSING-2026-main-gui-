import sys,subprocess
import threading
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout,QHBoxLayout,QWidget,
                            QFrame, QSizePolicy,QLabel,QGridLayout,QSpacerItem,QGraphicsView, QGraphicsScene, QGraphicsProxyWidget)
from PyQt6.QtCore import Qt,QRect,QTimer
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import numpy as np
from PyQt6.QtGui import QRegion,QKeyEvent,QGuiApplication,QColor,QPainter
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget, QMessageBox
)
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QFileDialog 
from PyQt6.QtCore import QObject, pyqtSignal 
# from waveforms import waveform_scenarios 
from hardware import prev_values,read_serial,start_reader 

from recorder import ScenarioRecorder 
from waveforms2 import generate_waveforms_for_scenario, waveform_scenarios 
# from wavefrommath import generate_waveforms_for_scenario, waveform_scenarios 
from PyQt6.QtWidgets import QGraphicsOpacityEffect 
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
from PyQt6.QtCore import QParallelAnimationGroup, QTimer 

from loading_screen import LoadingScreen
from PyQt6.QtWidgets import QApplication 
import time
from debug_utils import DebugFooter

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import QUrl

import hardware
# How many beats you want visible at once

#UPDATE WAVEFORMS : 10 and 2

BEATS_VISIBLE = 6
DISPLAY_SAMPLES = 500          # points shown per strip (your existing y_display length)
DEFAULT_HR = 72
DEFAULT_FS = 500

def process_data(data):
    """
    Accepts either:
      - dict {'time': array, 'waveform': array}, or
      - Nx2 numpy array [[t,y], ...]
    Returns (t_normalized, y_normalized)
    """
    if isinstance(data, dict):
        t = np.asarray(data['time'])
        y = np.asarray(data['waveform'])
    else:
        arr = np.asarray(data)
        t = arr[:, 0]
        y = arr[:, 1]

    t = t - t.min()
    y = (y - y.min()) / (y.max() - y.min() + 1e-9) * 2 - 1
    return t, y

def build_static_strip(single_beat, hr, fs, beats_visible=20):
    """
    Build a fixed ECG strip from one beat template.
    Does not move. The mask controls scrolling.
    """
    period = int(fs * 60.0 / hr)  # samples per beat

    # Resize single beat to exactly one cardiac cycle
    single_beat_resized = np.interp(
        np.linspace(0, len(single_beat)-1, period),
        np.arange(len(single_beat)),
        single_beat
    )

    # Repeat beats to create long strip
    strip = np.tile(single_beat_resized, beats_visible)

    return strip


# def beats_from_hr(hr):
#     try:
#         hr = int(hr)  # convert from string to int
#         if hr < 61:
#             return 6
#         elif hr <= 70:
#             return 7
#         elif hr <= 80:
#             return 8
#         elif hr <= 90:
#             return 9
#         elif hr <= 100:
#             return 10
#         else:
#             return 10  # cap at 10
#     except:
#         return 6  # fallback if HR is "--" or invalid


class ScenarioManager(QObject):
    scenarioChanged = pyqtSignal(int)
    ecgScenarioChanged = pyqtSignal(str, int)
    valuesUpdated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.current_scenario = "Normal"
        self.prev_values = prev_values

    def set_scenario(self, index):
        self.current_scenario = index
        self.scenarioChanged.emit(index)

class GlitchOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(parent.geometry())
            
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(1200)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.setEasingCurve(QEasingCurve.Type.OutExpo)
        self.anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(0.1)
        painter.fillRect(self.rect(), QColor(255, 255, 255))  # White flicker
        for _ in range(20):
            y = np.random.randint(0, self.height())
            h = np.random.randint(1, 6)
            painter.fillRect(0, y, self.width(), h, QColor(255, 0, 255, 100))  # Magenta glitch lines
            

class MultiGraphMonitor(QMainWindow):
    def __init__(self,cropped=False, scenario_manager=None):
        super().__init__()
        self.setWindowTitle("Multi-Graph Monitor")
        self.showFullScreen()  
        self.setStyleSheet("background-color: black; border: none;")

        self.recorder = ScenarioRecorder()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_hardware_button)
        self.timer.start(200)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        self.scenarios = list(waveform_scenarios.keys())  
        self.current_scenario = 0  
        self.next_scenario = None  
        self.mask_position = 0  
        self.transition_alpha = 0 

        self._playback_timers = []
        self._play_start_time = 0

        self.manager = scenario_manager
        if self.manager:
            self.manager.scenarioChanged.connect(self.change_scenario)
        self.container = QWidget(self)
        self.container.setStyleSheet("background-color: black; border: none;")
        self.setCentralWidget(self.container)

        self.main_layout = QVBoxLayout()  
        self.main_layout.setContentsMargins(0, 0, 0, 0) 
        self.main_layout.setSpacing(0)  
        self.container.setLayout(self.main_layout)

        self.top_layout = QHBoxLayout()
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(0)

        self.graph_container = QFrame()
        self.graph_container.setStyleSheet("background-color: black; border:  none;") 
        self.graph_container.setFixedSize(1110, 600)  

        mask_region = QRegion(QRect(0, 0, 1200, 650)) 

        self.graph_container.setMask(mask_region)

        self.container_layout = QGridLayout()
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        self.graph_container.setLayout(self.container_layout)

        self.RightValuesBox = QFrame()
        self.RightValuesBox.setStyleSheet("background-color: black; border: none;") 
        self.RightValuesBox.setFixedSize(206, 650) 

        self.value_layout = QVBoxLayout()
        self.value_layout.setContentsMargins(0, 0, 0, 0) 
        self.value_layout.setSpacing(0)  

        self.hr_label = QLabel("--")
        self.rr_label = QLabel("--")
        self.spo2_label = QLabel("--%")
        self.bp_label = QLabel("--") 

        self.hr_label.setFixedHeight(323)
        self.spo2_label.setFixedHeight(108)
        self.rr_label.setFixedHeight(109)
        self.bp_label.setFixedHeight(106)

        for label in [self.hr_label, self.spo2_label, self.rr_label, self.bp_label]:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hr_label.setStyleSheet("""
            color: lime;
            font-family: 'Arial Black', 'DIN Alternate Bold', sans-serif;
            font-size: 100px;
            border: none;
        """)
        self.rr_label.setStyleSheet("""
            color: yellow;
            font-family: 'Arial Black', 'Roboto Bold', sans-serif;
            font-size: 75px;
            border: none;
        """)
        self.spo2_label.setStyleSheet("""
            color: deepskyblue;
            font-family: 'Arial Black', 'Roboto Bold', sans-serif;
            font-size: 60px;
            border: none;
        """)
        self.bp_label.setStyleSheet("""
            color: red;
            font-family: 'Arial Black', 'Roboto Bold', sans-serif;
            font-size: 48px;
            border: none;
        """)

        self.value_layout.addWidget(self.hr_label, alignment=Qt.AlignmentFlag.AlignTop)
        self.value_layout.addWidget(self.rr_label, alignment=Qt.AlignmentFlag.AlignTop)
        self.value_layout.addWidget(self.spo2_label, alignment=Qt.AlignmentFlag.AlignTop)
        self.value_layout.addWidget(self.bp_label, alignment=Qt.AlignmentFlag.AlignTop)

        self.RightValuesBox.setLayout(self.value_layout)

        self.RightStaffBox = QFrame()
        self.RightStaffBox.setStyleSheet("background-color: black; none")
        self.RightStaffBox.setFixedSize(100, 650)  

        self.hr_range = QLabel("HR\n60–100")
        self.rr_range = QLabel("RR\n12–20")
        self.spo2_range = QLabel("SpO2\n90–95%")
        self.bp_range = QLabel("BP\n90-120\n60-90")

        self.hr_range.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hr_range.setStyleSheet("""
            color: lime;
            font-family: 'Arial Black', 'DIN Alternate Bold', sans-serif;
            font-size: 30px;  /* Same font size as your hr_label */
            border: none;
        """)

        self.rr_range.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rr_range.setStyleSheet("""
            color: yellow;
            font-family: 'Arial Black', 'Roboto Bold', sans-serif;
            font-size: 28px;  /* Same font size as your rr_label */
            border: none;
        """)

        self.spo2_range.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spo2_range.setStyleSheet("""
            color: deepskyblue;
            font-family: 'Arial Black', 'Roboto Bold', sans-serif;
            font-size: 22px;  /* Same font size as your spo2_label */
            border: none;
        """)

        self.bp_range.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bp_range.setStyleSheet("""
            color: red;
            font-family: 'Arial Black', 'Roboto Bold', sans-serif;
            font-size: 20px;  /* Same font size as your bp_label */
            border: none;
        """)

        self.hr_range.setFixedHeight(323)  
        self.rr_range.setFixedHeight(109)  
        self.spo2_range.setFixedHeight(108)
        self.bp_range.setFixedHeight(106)  

        staff_layout = QVBoxLayout()
        staff_layout.setContentsMargins(0, 0, 0, 0)
        staff_layout.setSpacing(0)

        staff_layout.addWidget(self.hr_range)
        staff_layout.addWidget(self.rr_range)
        staff_layout.addWidget(self.spo2_range)
        staff_layout.addWidget(self.bp_range)

        self.RightStaffBox.setLayout(staff_layout)

        self.right_side_layout = QHBoxLayout()
        self.right_side_layout.setContentsMargins(0, 0, 0, 0)
        self.right_side_layout.setSpacing(0)

        self.right_side_widget = QWidget()
        self.right_side_widget.setLayout(self.right_side_layout)

        self.right_side_layout.addWidget(self.RightValuesBox)
        if not cropped:
            self.right_side_layout.addWidget(self.RightStaffBox)

        # Label stack on the left of graph container
        self.graph_label_column = QFrame()
        self.graph_label_column.setFixedWidth(120)
        self.graph_label_column.setStyleSheet("background-color: black; border: none;")
        label_layout = QVBoxLayout()
        label_layout.setContentsMargins(0, 0, 20, 0)
        label_layout.setSpacing(0)

        self.graph_labels = [("ECG I", "lime"), ("ECG II", "lime"), ("ECG III", "lime"),
                            ("RR", "yellow"), ("SPO2", "deepskyblue"), ("BP", "red")]

        row_height = self.graph_container.height() // len(self.graph_labels)

        for text, color in self.graph_labels:
            label = QLabel(text)
            label.setFixedHeight(row_height)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setStyleSheet(f"""
                color: {color};
                font-size: 35px;
                font-weight: bold;
                font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif;
                background-color: black;
                border: none;
            """)

            label_layout.addWidget(label)

        self.graph_label_column.setLayout(label_layout)

        # Add both label column and graph container to layout
        self.graph_layout_with_labels = QHBoxLayout()
        self.graph_layout_with_labels.setContentsMargins(0, 0, 0, 0)
        self.graph_layout_with_labels.setSpacing(0)
        self.graph_layout_with_labels.addWidget(self.graph_label_column)
        self.graph_layout_with_labels.addWidget(self.graph_container)

        self.top_layout.addLayout(self.graph_layout_with_labels)

        self.top_layout.addWidget(self.right_side_widget, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self.bottom_container = QFrame()
        self.bottom_container.setStyleSheet("background-color: black; border:  none;")  
        self.bottom_container.setFixedHeight(114)  

        self.bottom_layout = QHBoxLayout()
        self.bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_layout.setSpacing(0)  

        self.temp_label = QLabel("--")
        self.nabp_label = QLabel("120/80")
        self.cvp_label = QLabel("8 mmHg")
        self.rr_bottom_label = QLabel("16")
        self.pap_label = QLabel("25/10")

        self.temp_label.setFixedSize(438, 151)
        self.nabp_label.setFixedSize(390, 151)
        self.cvp_label.setFixedSize(400, 151)
        self.rr_bottom_label.setFixedSize(124, 151)
        self.pap_label.setFixedSize(180, 151)

        for label in [ self.nabp_label, self.cvp_label, self.rr_bottom_label, self.pap_label,self.temp_label]:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.temp_label.setStyleSheet("""
                color: cyan;
                font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
                font-size: 46px;
                font-weight: bold;
                border: none;
                background-color: black;
            """)
        self.nabp_label.setStyleSheet("""
            color: orange;
            font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
            font-size: 50px;
            border: none;
            background-color: black;""")
        self.cvp_label.setStyleSheet("""
            color: lightblue;
            font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
            font-size: 48px;
            border: none;
        """)

        self.pap_label.setStyleSheet("""
            color: magenta;
            font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
            font-size: 50px;
            border: none;
        """)
        self.rr_bottom_label.setStyleSheet("""
            color: yellow;
            font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
            font-size: 49px;
            border: none;
        """)
        

        spacer = QSpacerItem(50, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.bottom_layout.addItem(spacer)  

        self.bottom_layout.addWidget(self.temp_label)
        self.bottom_layout.addWidget(self.nabp_label)
        self.bottom_layout.addWidget(self.cvp_label)
        self.bottom_layout.addWidget(self.rr_bottom_label)
        self.bottom_layout.addWidget(self.pap_label)

        self.bottom_container.setLayout(self.bottom_layout)

        self.main_layout.addLayout(self.top_layout)  
        self.main_layout.addWidget(self.bottom_container,alignment=Qt.AlignmentFlag.AlignTop)  

        self.footer_container = QFrame()
        self.footer_container.setStyleSheet("background-color: black; border: none;")  
        self.footer_container.setFixedHeight(50)  

        self.footer_layout = QHBoxLayout()
        self.footer_layout.setContentsMargins(0, 0, 0, 0)
        self.footer_layout.setSpacing(0)
        self.footer_container.setLayout(self.footer_layout)

        # --- Temp container with REC on the left and value on the right ---
        self.temp_range = QWidget()
        self.temp_range.setFixedSize(438, 70)
        self.temp_range.setStyleSheet("background-color: black;")

        temp_layout = QHBoxLayout()
        temp_layout.setContentsMargins(10, 0, 10, 0)
        temp_layout.setSpacing(10)

        self.recording_indicator = QLabel("● REC")
        # Fade effect
        self.rec_opacity = QGraphicsOpacityEffect()
        self.recording_indicator.setGraphicsEffect(self.rec_opacity)

        self.rec_blink_anim = QPropertyAnimation(self.rec_opacity, b"opacity")
        self.rec_blink_anim.setDuration(1000)  # 1 second cycle
        self.rec_blink_anim.setStartValue(1.0)
        self.rec_blink_anim.setEndValue(0.0)
        self.rec_blink_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.rec_blink_anim.setLoopCount(-1)  # Loop forever

        self.recording_indicator.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.recording_indicator.setStyleSheet("""
            color: red;
            font-size: 22px;
            font-weight: bold;
            background-color: black;
            border: none;
        """)
        self.recording_indicator.hide()

        self.play_indicator = QLabel("▶ PLAY")
                # Fade effect
        self.play_opacity = QGraphicsOpacityEffect()
        self.play_indicator.setGraphicsEffect(self.play_opacity)

        self.play_blink_anim = QPropertyAnimation(self.play_opacity, b"opacity")
        self.play_blink_anim.setDuration(1000)  # 1 second cycle
        self.play_blink_anim.setStartValue(1.0)
        self.play_blink_anim.setEndValue(0.0)
        self.play_blink_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.play_blink_anim.setLoopCount(-1)  # Loop forever

        self.play_indicator.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.play_indicator.setStyleSheet("""
            color: lime;                /* or whatever color you like */
            font-size: 22px;
            font-weight: bold;
            background-color: black;    
            border: none;
        """)
        self.play_indicator.hide()

        self.temp_value_label = QLabel("--")
        self.temp_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.temp_value_label.setStyleSheet("""
            color: cyan;
            font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
            font-size: 26px;
            font-weight: bold;
            border: none;
            background-color: black;
        """)

        # add a stretch BEFORE and AFTER your widgets
        temp_layout.addStretch(1)
        temp_layout.addWidget(self.recording_indicator)
        temp_layout.addWidget(self.play_indicator)
        temp_layout.addWidget(self.temp_value_label)
        temp_layout.addStretch(1)

        # vertically center them
        temp_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.temp_range.setLayout(temp_layout)


        # --- The rest of the footer labels as usual ---
        self.nabp_range = QLabel("--")
        self.cvp_range = QLabel("--")
        self.rr_bottom_range = QLabel("--")
        self.pap_range = QLabel("--")

        self.nabp_range.setFixedSize(390, 70)
        self.cvp_range.setFixedSize(400, 70)
        self.rr_bottom_range.setFixedSize(124, 70)
        self.pap_range.setFixedSize(180, 70)

        for label in [self.nabp_range, self.cvp_range, self.rr_bottom_range, self.pap_range]:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.nabp_range.setStyleSheet("""
            color: orange;
            font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
            font-size: 28px;
            border: none;
            background-color: black;
        """)
        self.cvp_range.setStyleSheet("""
            color: lightblue;
            font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
            font-size: 26px;
            border: none;
            background-color: black;
        """)
        self.rr_bottom_range.setStyleSheet("""
            color: yellow;
            font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
            font-size: 26px;
            border: none;
            background-color: black;
        """)
        self.pap_range.setStyleSheet("""
            color: magenta;
            font-family: 'Roboto Medium', 'Arial', 'Verdana', sans-serif;
            font-size: 28px;
            border: none;
            background-color: black;
        """)

        # --- Add to layout ---
        self.footer_layout.addWidget(self.temp_range)
        self.footer_layout.addWidget(self.nabp_range)
        self.footer_layout.addWidget(self.cvp_range)
        self.footer_layout.addWidget(self.rr_bottom_range)
        self.footer_layout.addWidget(self.pap_range)

        if not cropped:
            self.main_layout.addWidget(self.footer_container, alignment=Qt.AlignmentFlag.AlignBottom)
            self.footer_box = DebugFooter()
            self.main_layout.addWidget(self.footer_box)
            #self.footer_box.show_message("Simulation initialized successfully.")
                        
        self.thread = threading.Thread(target=read_serial, daemon=True)
        self.thread.start()

        if not cropped:  # 🔴 only staff GUI updates hardware values
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.update_display)
            self.timer.start(500)

        self.graph_colors = {
            "ECG1": "lime",
            "ECG2": "lime",
            "ECG3": "lime",
            "Resp": "yellow",
            "SpO2": "deepskyblue",
            "BP": "red"
        }

        self.graphs = []
        self.index = 3
        self.update_waveforms()  
                
        self.ani = FuncAnimation(self.graphs[0][0], self.update_graphs, interval=50, blit=False, cache_frame_data=False)

    def switch_scenario_global(self, index):
        """Switch scenario in both staff and mirror windows."""
        self.change_scenario(index)  # update staff_gui

        if hasattr(self, "mirror_window") and self.mirror_window is not None:
            self.mirror_window.change_scenario(index)  # update mirror

    def update_ecg_only(self, scenario_name, hr):
        """Update only the ECG leads without touching other graphs."""
        data_dict = generate_waveforms_for_scenario(scenario_name, hr=hr, fs=DEFAULT_FS)

        for i, (name, d) in enumerate(data_dict.items()):
            if name.startswith("ECG"):   # only update ECG leads
                _, y_norm = process_data(d)
                ring = build_static_strip(
                    y_norm, hr=hr, fs=DEFAULT_FS, beats_visible=BEATS_VISIBLE
                )
                self.next_waveforms[i] = ring
                if not np.array_equal(ring, self.current_waveforms[i]):
                    self.switch_requested_flags[i] = True

        print(f"[ECG Only] Switched ECG leads to: {scenario_name} (HR={hr})")

    def request_scenario_switch(self, scenario_name, hr=None, delay_ms=150):
            """
            Request a scenario switch. Generates new rings for the requested scenario,
            and schedules them to be applied after delay_ms.
            """
            if hr is None:
                hr = DEFAULT_HR

            try:
                new_data = generate_waveforms_for_scenario(scenario_name, hr=hr, fs=DEFAULT_FS)
            except Exception as e:
                print("Failed to generate waveforms for scenario:", e)
                return

            new_rings_by_name = {}
            for name, d in new_data.items():
                _, y_norm = process_data(d)
                ring = build_static_strip(y_norm, hr=hr, fs=DEFAULT_FS, beats_visible=BEATS_VISIBLE)
                new_rings_by_name[name] = ring

            def apply_switch():
                # Replace current waveforms with new scenario rings
                for i, (fig, ax, canvas, line, ring, y_display) in enumerate(self.graphs):
                    chosen_ring = None

                    # match by common waveform keys
                    for try_key in ("ECG I", "ECG II", "ECG III",
                                    "ECG1", "ECG2", "ECG3",
                                    "Resp", "RR", "SpO2", "SPO2", "BP"):
                        if try_key in new_rings_by_name:
                            chosen_ring = new_rings_by_name.pop(try_key, None)
                            break

                    if chosen_ring is None and len(new_rings_by_name) > 0:
                        key, chosen_ring = new_rings_by_name.popitem()

                    if chosen_ring is not None:
                        self.next_waveforms[i] = chosen_ring.copy()
                        if not np.array_equal(self.next_waveforms[i], self.current_waveforms[i]):
                            self.switch_requested_flags[i] = True

                # print(f"Applied switch -> {scenario_name}")

            QTimer.singleShot(delay_ms, apply_switch)

    def change_scenario(self, index):
        """Called by the ScenarioManager."""
        self.current_scenario = index
        scenario_name = self.scenarios[index] if 0 <= index < len(self.scenarios) else "Normal"

        if scenario_name == "Normal":
            hr = 75
        elif scenario_name == "Bradycardia":
            hr = 40
        elif scenario_name == "Tachycardia":
            hr = 120
        else:
            hr = DEFAULT_HR

        self.request_scenario_switch(scenario_name, hr=hr, delay_ms=150)
        print(f"Scenario changed to: {scenario_name}")

    def update_display(self):
        """Updates UI labels with new values."""
        self.hr_label.setText(f"{prev_values['HR']}")
        self.rr_label.setText(f"{prev_values['RR']}")
        self.spo2_label.setText(f"{prev_values['SpO2']} %")
        self.bp_label.setText(f"{prev_values['BP:SYS']}/{prev_values['BP:DYS']}")
        self.temp_label.setText(f"{prev_values['TEMP']}°C")
    
        try:
            temp = float(prev_values['TEMP'])
            self.temp_value_label.setText(f"Temp: {temp:.1f}°C")
        except Exception:
            self.temp_value_label.setText("Temp: 37-39°C")

        try:
            sys = int(prev_values['BP:SYS'])
            dys = int(prev_values['BP:DYS'])
            self.nabp_range.setText(f"NABP: {sys}/{dys}")
        except Exception:
            self.nabp_range.setText("BP: 110/80")

        try:
            cvp = int(prev_values['HR']) % 15
            self.cvp_range.setText(f"CVP: {cvp} mmHg")
        except Exception:
            self.cvp_range.setText("CVP: 6 mmHg")

        try:
            rr = int(prev_values['RR'])
            self.rr_bottom_range.setText(f"RR: {rr}")
        except Exception:
            self.rr_bottom_range.setText("RR: 10-40")

        try:
            spo2 = int(prev_values['SpO2'])
            pap_sys = 25 + spo2 % 10
            pap_dys = 10 + spo2 % 5
            self.pap_range.setText(f"PAP: {pap_sys}/{pap_dys}")
        except Exception:
            self.pap_range.setText("PAP: 18mmHg")
        self.recorder.record_step(prev_values)
        self.recorder.record_step(prev_values, scenario=self.scenarios[self.current_scenario])
        if self.manager:
            self.manager.valuesUpdated.emit(prev_values.copy())

    def update_ui_with_data(self, values):
        self.hr_label.setText(f"{values['HR']}")
        self.rr_label.setText(f"{values['RR']}")
        self.spo2_label.setText(f"{values['SpO2']} %")
        self.bp_label.setText(f"{values['BP:SYS']}/{values['BP:DYS']}")
        self.temp_label.setText(f"{values['TEMP']}°C")

        # Footer values (mirroring update_display logic)
        try:
            temp = float(values['TEMP'])
            self.temp_value_label.setText(f"Temp: {temp:.1f}°C")
        except Exception:
            self.temp_value_label.setText("Temp: 37-39°C")

        try:
            sys = int(values['BP:SYS'])
            dys = int(values['BP:DYS'])
            self.nabp_range.setText(f"NABP: {sys}/{dys}")
        except Exception:
            self.nabp_range.setText("BP: 110/80")

        try:
            cvp = int(values['HR']) % 15
            self.cvp_range.setText(f"CVP: {cvp} mmHg")
        except Exception:
            self.cvp_range.setText("CVP: 6 mmHg")

        try:
            rr = int(values['RR'])
            self.rr_bottom_range.setText(f"RR: {rr}")
        except Exception:
            self.rr_bottom_range.setText("RR: 10-40")

        try:
            spo2 = int(values['SpO2'])
            pap_sys = 25 + spo2 % 10
            pap_dys = 10 + spo2 % 5
            self.pap_range.setText(f"PAP: {pap_sys}/{pap_dys}")
        except Exception:
            self.pap_range.setText("PAP: 18mmHg")
            
            
            
    import numpy as np





    def update_waveforms(self):
        """Updates the displayed waveforms based on the current scenario with smooth blending."""
        # Clear existing waveform UI
        for i in reversed(range(self.container_layout.count())):
            widget = self.container_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        self.graphs.clear()
        scenario_name = self.scenarios[self.current_scenario]

        # ✅ Generate multi-beat arrays here
        data_dict = generate_waveforms_for_scenario(
            scenario_name,
            hr=DEFAULT_HR,
            fs=DEFAULT_FS,
            # num_beats=BEATS_VISIBLE * 1  # long enough source to build the ring
        )

        # Rebuild waveform graphs
        for name, d in data_dict.items():
            frame = QFrame()
            frame.setStyleSheet("border: none; background-color: black;")
            frame_layout = QVBoxLayout()
            frame_layout.setContentsMargins(0,0,0,0)
            frame.setLayout(frame_layout)

            fig, ax = plt.subplots(figsize=(6, 2))
            fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
            canvas = FigureCanvas(fig)
            frame_layout.addWidget(canvas)

            fig.patch.set_facecolor("black")
            ax.set_facecolor("black")
            ax.set_ylim(-1.2, 1.2)
            ax.set_xlim(0, 1000)
            ax.axis("off")

            color = self.graph_colors.get(name, "white")
            line, = ax.plot([], [], color, linewidth=2)

            # Normalize then build a dense ring that shows many beats per window
            _, y_norm = process_data(d)
            ring = build_static_strip(y_norm, hr=DEFAULT_HR, fs=DEFAULT_FS,
                                        beats_visible=BEATS_VISIBLE)

            y_display = np.zeros(DISPLAY_SAMPLES)
            self.graphs.append((fig, ax, canvas, line, ring, y_display))
            self.container_layout.addWidget(frame)

        # Initialize / update animation state
        new_waveforms = [ring for *_, ring, __ in self.graphs]  # extract rings

        if not hasattr(self, "full_waveforms"):
            self.full_waveforms = [r.copy() for r in new_waveforms]
            self.current_waveforms = [r.copy() for r in new_waveforms]
            self.next_waveforms = [r.copy() for r in new_waveforms]
            self.switch_requested_flags = [False] * len(self.graphs)
            self.mask_positions = [0] * len(self.graphs)
            self.buffer_size = DISPLAY_SAMPLES
            self.blend_width = 10
            self.scroll_speed = 2   # speed of scrolling
            self.blend_in_progress = [False] * len(self.graphs)
            self.blend_start_pos = [0] * len(self.graphs)
        else:
            self.next_waveforms = [r.copy() for r in new_waveforms]
            for i in range(len(self.graphs)):
                if not np.array_equal(self.next_waveforms[i], self.current_waveforms[i]):
                    self.switch_requested_flags[i] = True

        print(f"Transitioning to scenario: {scenario_name}")
        
    def play_recording(self, filepath="recorded_scenario.json"):
        try:
            data = self.recorder.load_recording(filepath)
        except Exception as e:
            print(f"Failed to load recording: {e}")
            return

        if not data:
            print("No data to play.")
            return

        self.recording_indicator.hide()
        self.play_indicator.show()
        #self.footer_box.slider.setVisible(True)
        self.footer_box.show_slider_with_animation()

        self._playback_data = sorted(data, key=lambda f: f["time"])
        self._current_frame_index = 0
        self._is_playing = True

        max_time = self._playback_data[-1]["time"]
        self.footer_box.set_max_duration(max_time)
        self._start_time = time.time()
        self._play_start_offset = 0

        def apply_frame_if_needed(current_time):
            while (
                self._current_frame_index < len(self._playback_data)
                and self._playback_data[self._current_frame_index]["time"] <= current_time
            ):
                frame = self._playback_data[self._current_frame_index]
                self._current_frame_index += 1

                QTimer.singleShot(0, lambda f=frame: apply_frame(f))  # yield UI thread

        def apply_frame(frame):
            scenario = frame.get("scenario")
            if scenario and scenario in self.scenarios:
                idx = self.scenarios.index(scenario)
                if self.manager:
                    self.manager.set_scenario(idx)
                else:
                    self.change_scenario(idx)
            self.update_ui_with_data(frame["values"])

        def playback_loop():
            if not self._is_playing:
                return
            elapsed = time.time() - self._start_time
            current_time = elapsed + self._play_start_offset

            apply_frame_if_needed(current_time)
            self.footer_box.update_slider_position(int(current_time * 1000))

            if current_time < max_time:
                QTimer.singleShot(16, playback_loop)  # ~60 FPS
            else:
                end_playback()

        def end_playback():
            self._is_playing = False
            self.play_indicator.hide()
            self.footer_box.slider.setVisible(False)

        def seek_to(seconds):
            self._play_start_offset = seconds
            self._start_time = time.time()
            self._current_frame_index = 0

            # Fast-forward to frame before this second
            for i, frame in enumerate(self._playback_data):
                if frame["time"] <= seconds:
                    self._current_frame_index = i
                else:
                    break
            apply_frame(self._playback_data[self._current_frame_index])
            playback_loop()

        self.footer_box.seek_callback = seek_to
        seek_to(0)

        print(f"Playing back from {filepath}")

    def launch_new_app(self):
        QApplication.quit()
        subprocess.Popen([sys.executable, "cpr65air.py"])

    def check_hardware_button(self):
        """Check if Arduino button pressed and switch graph."""

        btn = hardware.button_scenario
        if btn is None:
            return

        mapping = {
            "ECG1": "Normal",
            "ECG2": "Bradycardia",
            "ECG3": "Tachycardia",
        }

        scenario_name = mapping.get(btn)

        # 🔊 Always handle audio first
        if btn == "ECG1":
            self.player.setSource(QUrl.fromLocalFile("audio.mp3"))
            self.player.play()
            print("Audio for NORMAL playing...")

        elif btn == "ECG2":
            self.player.setSource(QUrl.fromLocalFile("audio1.mp3"))
            self.player.play()
            print("Audio for BRADYCARDIA playing...")

        elif btn == "ECG3":
            self.player.pause()
            print("Audio paused (TACHYCARDIA).")

        # 📊 Then handle graph switching (only if different)
        if scenario_name:
            idx = self.scenarios.index(scenario_name)
            if self.current_scenario != idx:
                self.current_scenario = idx 
                print(f"Graph switched → {scenario_name}")
                self.switch_graph(scenario_name)

        # Reset for next press
        hardware.button_scenario = None


    def switch_graph(self, scenario_name):
        """The same logic from keyPressEvent, but reusable."""
        if scenario_name == "Normal":
            hr = 75
        elif scenario_name == "Bradycardia":
            hr = 40
        elif scenario_name == "Tachycardia":
            hr = 120
        else:
            hr = DEFAULT_HR

        data_dict = generate_waveforms_for_scenario(
            scenario_name, hr=hr, fs=DEFAULT_FS
        )

        for i, (name, d) in enumerate(data_dict.items()):
            if name.startswith("ECG"):
                _, y_norm = process_data(d)
                ring = build_static_strip(
                    y_norm, hr=hr, fs=DEFAULT_FS, beats_visible=BEATS_VISIBLE
                )
                self.next_waveforms[i] = ring
                if not np.array_equal(ring, self.current_waveforms[i]):
                    self.switch_requested_flags[i] = True

            print(f"Switched ECG leads to scenario: {scenario_name}")

    def keyPressEvent(self, event):
        key = event.key()

        if Qt.Key.Key_1 <= key <= Qt.Key.Key_5:
            scenario_index = key - Qt.Key.Key_1

            if scenario_index < len(self.scenarios):
                scenario_name = self.scenarios[scenario_index]

                # HR depending on scenario
                if scenario_name == "Normal":
                    hr = 75
                elif scenario_name == "Bradycardia":
                    hr = 40
                elif scenario_name == "Tachycardia":
                    hr = 120
                else:
                    hr = DEFAULT_HR

                # 🔑 Broadcast to both staff & student via manager
                if self.manager:
                    self.manager.ecgScenarioChanged.emit(scenario_name, hr)
                    
        if key == Qt.Key.Key_P:  # Only for key "1"
            self.player.setSource(QUrl.fromLocalFile("audio.mp3"))
            self.player.play()
            print("Audio playing...")
            print("Audio playing...")
        elif key == Qt.Key.Key_K:  # Pause/Resume audio
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
                print("Audio paused")
                print("Audio paused")
            elif self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
                self.player.play()
                print("Audio resumed")
                print("Audio resumed")

        elif key == Qt.Key.Key_R:
            self.recorder.start_recording()
            self.play_indicator.hide()
            self.recording_indicator.show()
            self.rec_blink_anim.start()

        elif key == Qt.Key.Key_S:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Recording",
                "recording.json",
                "JSON Files (*.json)"
            )
            if file_path:
                if not file_path.endswith(".json"):
                    file_path += ".json"
                self.recorder.stop_recording(file_path)
                print(f"Saved recording as: {file_path}")
            else:
                self.recorder.stop_recording()
                print("Save cancelled, using default filename.")

            self.rec_blink_anim.stop()
            self.recording_indicator.hide()

        elif key == Qt.Key.Key_L:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select a Recording File",
                "",
                "JSON Files (*.json)"
            )
            if file_path:
                self.recording_indicator.hide()
                self.play_indicator.show()
                self.play_blink_anim.start()
                self.play_recording(file_path)
                self.play_blink_anim.start()

        elif key == Qt.Key.Key_C:
            print("Glitch transition before switching to cpr65air.py...")

            self.glitch = GlitchOverlay(self)
            self.glitch.show()

            # Delay launch until glitch effect finishes
            QTimer.singleShot(1500, self.launch_new_app)
        elif key == Qt.Key.Key_U:
            print("HR is increased by 10")

    def update_graphs(self, frame):
        for i, (_, ax, canvas, line, ring, y_display) in enumerate(self.graphs):
            # Initialize data structures if missing (same as before)
            if not hasattr(self, "full_waveforms"):
                self.full_waveforms = [np.tile(y, 200) for _, _, _, _, y, _ in self.graphs]
                self.current_waveforms = [r.copy() for r in self.full_waveforms]
                self.next_waveforms = [r.copy() for r in self.full_waveforms]
                self.switch_requested_flags = [False] * len(self.graphs)
                self.mask_positions = [0] * len(self.graphs)
                self.buffer_size = len(y_display)
                self.blend_width = 100
                self.scroll_speed = 3
                self.blend_in_progress = [False] * len(self.graphs)
                self.blend_start_pos = [0] * len(self.graphs)

            # advance mask position only (this creates the illusion of motion)
            prev_pos = self.mask_positions[i]
            self.mask_positions[i] = (self.mask_positions[i] + self.scroll_speed) % self.buffer_size
            pos = self.mask_positions[i]

            # ------------------ Important change ------------------
            # Don't rotate the waveform. Keep the displayed waveform static:
            # use the first buffer_size samples from the currently blended waveform.
            display_wave = self.current_waveforms[i][: self.buffer_size]
            y_display[:] = display_wave  # keep y_display for compatibility with rest of code
            # ------------------------------------------------------

            # blending logic (if a switch to next_waveforms was requested)
            if self.switch_requested_flags[i]:
                if not self.blend_in_progress[i]:
                    self.blend_in_progress[i] = True
                    self.blend_start_pos[i] = pos

                half_width = self.blend_width // 2
                start_bl = max(pos - half_width, 0)
                end_bl = min(pos + half_width, self.buffer_size)
                alpha = np.linspace(0, 1, end_bl - start_bl) if end_bl > start_bl else []

                for j, a in enumerate(alpha):
                    idx = start_bl + j
                    if idx < self.buffer_size:
                        current = self.current_waveforms[i][idx]
                        target = self.next_waveforms[i][idx % len(self.next_waveforms[i])]
                        self.current_waveforms[i][idx ] = (1 - a) * current + a * target

                # finish blend when mask passes blend start (keeps your previous condition)
                if prev_pos > pos and pos >= self.blend_start_pos[i]:
                    self.current_waveforms[i] = np.copy(self.next_waveforms[i])
                    self.full_waveforms[i] = np.copy(self.next_waveforms[i])
                    self.switch_requested_flags[i] = False
                    self.blend_in_progress[i] = False

            # draw the static waveform
            x_vals = np.linspace(0, 1000, len(y_display))
            line.set_data(x_vals, y_display)

            # draw the moving black scanning bar (mask) on top to simulate motion
            transition_width = 4
            # mask position mapped into buffer window coordinates
            # mask_center = pos % self.buffer_size
            mask_start = max(0, pos - transition_width)
            mask_end = min(len(y_display), pos + transition_width)

            # remove previous mask artists (if any) and re-draw
            for artist in ax.lines[1:]:
                artist.remove()
            ax.plot(x_vals[mask_start:mask_end], y_display[mask_start:mask_end], color="black", linewidth=5)

            canvas.draw()
        self.index += 1


class CustomGraphicsView(QGraphicsView):
    def __init__(self, monitor_widget, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.monitor_widget = monitor_widget
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    def keyPressEvent(self, event):
        if self.monitor_widget:
            self.monitor_widget.keyPressEvent(event)
        else:
            super().keyPressEvent(event)

FOOTER_HEIGHT = 100

def run_dual_monitor_gui():
    app = QApplication(sys.argv)
    screens = QGuiApplication.screens()
    manager = ScenarioManager()

    if len(screens) < 2:
        reply = QMessageBox.question(
            None,
            "Mirror Screen Not Found",
            "No mirror screen detected.\nDo you want to continue on the primary screen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.No:
            sys.exit() 
        else:
            staff_screen = screens[0]
            staff_gui = MultiGraphMonitor(scenario_manager=manager, cropped=False)
            staff_gui.setGeometry(staff_screen.geometry())

            # ✅ connect signals even in single-screen mode
            manager.scenarioChanged.connect(staff_gui.change_scenario)
            manager.ecgScenarioChanged.connect(staff_gui.update_ecg_only)

            staff_gui.showFullScreen()
            sys.exit(app.exec())

    staff_screen = screens[0]
    student_screen = screens[1]

    # staff (full layout)
    staff_gui = MultiGraphMonitor(scenario_manager=manager, cropped=False)
    staff_gui.setGeometry(staff_screen.geometry())
    staff_gui.showFullScreen()

    # student (cropped layout)
    student_gui_original = MultiGraphMonitor(scenario_manager=manager, cropped=True)

    # ✅ connect signals (both screens)
    manager.scenarioChanged.connect(staff_gui.change_scenario)
    manager.scenarioChanged.connect(student_gui_original.change_scenario)
    manager.ecgScenarioChanged.connect(staff_gui.update_ecg_only)
    manager.ecgScenarioChanged.connect(student_gui_original.update_ecg_only)

    manager.valuesUpdated.connect(student_gui_original.update_ui_with_data)
    # student graphics proxy
    scene = QGraphicsScene()
    proxy = QGraphicsProxyWidget()
    proxy.setWidget(student_gui_original)
    scene.addItem(proxy)

    student_gui = CustomGraphicsView(student_gui_original)
    student_gui.setScene(scene)

    screen_rect = student_screen.geometry()
    target_width = screen_rect.width()
    target_height = screen_rect.height()
    student_gui.setGeometry(screen_rect)

    original_size = student_gui_original.size()
    scale_x = target_width / original_size.width()
    scale_y = target_height / original_size.height()
    scale_factor = min(scale_x, scale_y)

    student_gui.resetTransform()
    student_gui.scale(scale_factor, scale_factor)
    student_gui.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    app = QApplication(sys.argv)

    loading = LoadingScreen()
    loading.show()
    app.processEvents()  # makes sure the loading screen is shown

    # Simulate heavy load (or do real setup here if needed)
    time.sleep(3)  # you can skip this if all real loading happens inside dual monitor gui

    loading.close()
    run_dual_monitor_gui()
