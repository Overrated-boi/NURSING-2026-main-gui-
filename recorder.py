# scenario_recorder.py

import json
import time
import datetime

class ScenarioRecorder:
    def __init__(self):
        self.recording = False
        self.current_record = []
        self.start_time = None

    def start_recording(self):
        self.recording = True
        self.start_time = time.time()
        self.current_record = []
        print("[REC] Started recording")

    def stop_recording(self, filename=None):
        self.recording = False
        if not filename:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.json"

        with open(filename, 'w') as f:
            json.dump(self.current_record, f, indent=2)
        print(f"[REC] Recording stopped and saved to {filename}")

    def record_step(self, values: dict, scenario=None):
        if self.recording:
            timestamp = time.time() - self.start_time
            self.current_record.append({
                "time": timestamp,
                "values": values.copy(),
                "scenario": scenario
            })


    def load_recording(self, filename):
        with open(filename, 'r') as f:
            return json.load(f)
