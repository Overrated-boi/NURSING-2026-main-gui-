import numpy as np
import math

def _repeat_beats(single_beat, period, fs, num_beats):
    t = np.linspace(0, num_beats * period, int(num_beats * period * fs), endpoint=False)
    waveform = np.tile(single_beat, num_beats)
    return t, waveform

# ---------------- ECG Leads normal ----------------
def generate_lead1_ecg_pattern(hr, fs, num_beats=5):
    period = 60.0 / hr
    t1 = np.linspace(0, period, int(period * fs), endpoint=False)
    p = 0.15*np.exp(-((t1-0.1*period)**2)/(2*(0.02**2)))
    q = -0.1*np.exp(-((t1-0.2*period)**2)/(2*(0.008**2)))
    r = 1.0*np.exp(-((t1-0.23*period)**2)/(2*(0.006**2)))
    s = -0.15*np.exp(-((t1-0.27*period)**2)/(2*(0.008**2)))
    t = 0.25*np.exp(-((t1-0.4*period)**2)/(2*(0.03**2)))
    return _repeat_beats(p+q+r+s+t, period, fs, num_beats)

def generate_lead2_ecg_pattern(hr, fs, num_beats=5):
    period = 60.0 / hr
    t1 = np.linspace(0, period, int(period * fs), endpoint=False)
    p = 0.25*np.exp(-((t1-0.1*period)**2)/(2*(0.04**2)))
    q = -0.15*np.exp(-((t1-0.2*period)**2)/(2*(0.01**2)))
    r = 1.0*np.exp(-((t1-0.22*period)**2)/(2*(0.012**2)))
    s = -0.25*np.exp(-((t1-0.26*period)**2)/(2*(0.015**2)))
    t = 0.35*np.exp(-((t1-0.4*period)**2)/(2*(0.05**2)))
    return _repeat_beats(p+q+r+s+t, period, fs, num_beats)



def generate_lead1_v_ecg_pattern(hr, fs, num_beats=5):
    period = 60.0 / hr
    t1 = np.linspace(0, period, int(period * fs), endpoint=False)
    p_pos = 0.15*np.exp(-((t1-0.1*period)**2)/(2*(0.03**2)))
    p_neg = -0.15*np.exp(-((t1-0.14*period)**2)/(2*(0.03**2)))
    r = 0.25*np.exp(-((t1-0.22*period)**2)/(2*(0.01**2)))
    s = -0.7*np.exp(-((t1-0.26*period)**2)/(2*(0.02**2)))
    t = 0.2*np.exp(-((t1-0.4*period)**2)/(2*(0.04**2)))
    return _repeat_beats(p_pos+p_neg+r+s+t, period, fs, num_beats)

def generate_rr_wave(hr, fs, num_beats=5):
    duration = 30   # scale duration with HR
    t = np.array([i/fs for i in range(int(fs*duration))])
    f = 0.40  # fixed RR = 15 breaths/min
    wave = np.cos(2 * math.pi * f * t + math.pi)
    blip = np.zeros_like(wave)
    T = 1/f
    for i in range(int(duration * f) + 1):
        center = i*T + 0.02*T
        blip += 0.1 * np.exp(-((t - center)**2) / (0.06*T)**2)
    return t, wave + blip

def generate_spo2_wave(hr, fs, num_beats=20):
    # x_single = np.linspace(0, 2*np.pi, 500, endpoint=False)
    x = np.linspace(0, 2 * np.pi, 500)
    def icp_waveform_segment(x_val):
        p1 = 1.5 * np.sin(x_val)
        p2_raw = np.sin(x_val - np.pi/4)
        flat_factor = 1 / (1 + np.exp(-5 * (x_val - np.pi/4)))
        p2 = 0.0 * (p2_raw**2) * flat_factor
        p3 = 0.1 * np.sin(x_val - np.pi/2) * (1 - np.cos(x_val/2))
        return (p1 + p2 + p3) * np.exp(-x_val/5) + 0.5 * np.sin(x_val*2)

    # # Generate one cycle
    # y_single = np.array([icp_waveform_segment(val) for val in x_single])

    # # Tile cycles continuously
    # full_y = np.tile(y_single, num_beats)
    # full_x = np.linspace(0, num_beats * 2*np.pi, len(full_y), endpoint=False)
    num_repetitions = 11
    full_x_spo2 = np.linspace(-1, num_repetitions * 2 * np.pi-1, 500 * num_repetitions, endpoint=False)
    full_y_spo2 = np.array([icp_waveform_segment(val % (2 * np.pi)) for val in full_x_spo2])


    return full_x_spo2, full_y_spo2 + 1.5


def generate_bp_wave(hr, fs, num_beats=20):
    # x_single = np.linspace(0, 2*np.pi, 500, endpoint=False)

    def bp_waveform_segment(x_val):
        p1 = 1.5 * np.sin(x_val)
        p2_raw = np.sin(x_val - np.pi/2)
        flat_factor = 1 / (1 + np.exp(-5 * (x_val - np.pi/4)))
        p2 = 0.5 * (p2_raw**2) * flat_factor
        p3 = 0.7 * np.sin(x_val - np.pi/2) * (1 - np.cos(x_val/2))
        return (p1 + p2 + p3) * np.exp(-x_val/5) + 0.5 * np.sin(x_val*2)

    # One cycle
    # y_single = np.array([bp_waveform_segment(val) for val in x_single])

    # # Tile cycles
    # full_y = np.tile(y_single, num_beats)
    # full_x = np.linspace(0, num_beats * 2*np.pi, len(full_y), endpoint=False)
    num_repetitions_bp = 10
    full_x = np.linspace(-1, num_repetitions_bp * 2 * np.pi-1, 500 * num_repetitions_bp,endpoint=False)
    full_y = np.array([bp_waveform_segment(val % (2 * np.pi)) for val in full_x])
    return full_x, full_y + 1.5



#--------->brady function <------------------
def generate_brady_lead1(hr, fs,num_beats=5):
    period = 60.0 / hr
    t_single_beat = np.linspace(0, period, int(period * fs))
    
    P = 0.2 * np.exp(-((t_single_beat - 0.50) ** 2) / (2 * 0.015 ** 2))
    Q = -0.08 * np.exp(-((t_single_beat - 0.39) ** 2) / (2 * 0.015 ** 2))
    R = 0.4 * np.exp(-((t_single_beat - 0.36) ** 2) / (2 * 0.01 ** 2))
    S = -0.06 * np.exp(-((t_single_beat - 0.25) ** 2) / (2 * 0.01 ** 2))
    T = 0.1 * np.exp(-((t_single_beat - 0.2) ** 2) / (2 * 0.06 ** 2))

    
    single_heartbeat = P + Q + R + S + T
    return _repeat_beats(single_heartbeat, period, fs, num_beats)

def generate_brady_lead2(hr, fs,num_beats=5):
    period = 60.0 / hr
    t_single_beat = np.linspace(0, period, int(period * fs))
    
    P = 0.2 * np.exp(-((t_single_beat - 0.60) ** 2) / (2 * 0.08 ** 2))
    Q = -0.08 * np.exp(-((t_single_beat - 0.39) ** 2) / (2 * 0.015 ** 2))
    R = 0.8 * np.exp(-((t_single_beat - 0.40) ** 2) / (2 * 0.01 ** 2))
    S = -0.06 * np.exp(-((t_single_beat - 0.40) ** 2) / (2 * 0.01 ** 2))
    T = 0.1 * np.exp(-((t_single_beat - 0.2) ** 2) / (2 * 0.06 ** 2))

    
    single_heartbeat = P + Q + R + S + T
    return _repeat_beats(single_heartbeat, period, fs, num_beats)

def generate_brady_lead3(hr, fs,num_beats=5):
    period = 60.0 / hr
    t_single_beat = np.linspace(0, period, int(period * fs))
    
      
    P = -0.2 * np.exp(-((t_single_beat - 0.83) ** 2) / (2 * 0.04 ** 2))
    Q = 0.08 * np.exp(-((t_single_beat - 0.39) ** 2) / (2 * 0.015 ** 2))
    R = -0.8 * np.exp(-((t_single_beat - 0.45) ** 2) / (2 * 0.015 ** 2))
    S = 0.06 * np.exp(-((t_single_beat - 0.40) ** 2) / (2 * 0.01 ** 2))
    T = 0.05 * np.exp(-((t_single_beat - 0.20) ** 2) / (2 * 0.04 ** 2))


    
    single_heartbeat = P + Q + R + S + T
    return _repeat_beats(single_heartbeat, period, fs, num_beats)

#--------trachy-----------------------------

def generate_trachy_lead1(hr, fs,num_beats=5):
    period = 60.0 / hr
    t_single_beat = np.linspace(0, period, int(period * fs))
    
    P = 0.2 * np.exp(-((t_single_beat - 0.50) ** 2) / (2 * 0.015 ** 2))
    Q = -0.08 * np.exp(-((t_single_beat - 0.39) ** 2) / (2 * 0.015 ** 2))
    R = 0.4 * np.exp(-((t_single_beat - 0.36) ** 2) / (2 * 0.01 ** 2))
    S = -0.06 * np.exp(-((t_single_beat - 0.25) ** 2) / (2 * 0.01 ** 2))
    T = 0.1 * np.exp(-((t_single_beat - 0.2) ** 2) / (2 * 0.06 ** 2))

    
    single_heartbeat = P + Q + R + S + T
    return _repeat_beats(single_heartbeat, period, fs, num_beats)

def generate_trachy_lead2(hr, fs,num_beats=5):
    period = 60.0 / hr
    t_single_beat = np.linspace(0, period, int(period * fs))
    
    P = 0.2 * np.exp(-((t_single_beat - 0.60) ** 2) / (2 * 0.08 ** 2))
    Q = -0.08 * np.exp(-((t_single_beat - 0.39) ** 2) / (2 * 0.015 ** 2))
    R = 0.8 * np.exp(-((t_single_beat - 0.40) ** 2) / (2 * 0.01 ** 2))
    S = -0.06 * np.exp(-((t_single_beat - 0.40) ** 2) / (2 * 0.01 ** 2))
    T = 0.1 * np.exp(-((t_single_beat - 0.2) ** 2) / (2 * 0.06 ** 2))

    
    single_heartbeat = P + Q + R + S + T
    return _repeat_beats(single_heartbeat, period, fs, num_beats)

def generate_trachy_lead3(hr, fs,num_beats=5):
    period = 60.0 / hr
    t_single_beat = np.linspace(0, period, int(period * fs))
    
      
    P = -0.2 * np.exp(-((t_single_beat - 0.83) ** 2) / (2 * 0.04 ** 2))
    Q = 0.08 * np.exp(-((t_single_beat - 0.39) ** 2) / (2 * 0.015 ** 2))
    R = -0.8 * np.exp(-((t_single_beat - 0.45) ** 2) / (2 * 0.015 ** 2))
    S = 0.06 * np.exp(-((t_single_beat - 0.40) ** 2) / (2 * 0.01 ** 2))
    T = 0.05 * np.exp(-((t_single_beat - 0.20) ** 2) / (2 * 0.04 ** 2))


    
    single_heartbeat = P + Q + R + S + T
    return _repeat_beats(single_heartbeat, period, fs, num_beats)

# ---------------- Scenario Mapping ----------------
waveform_scenarios = {
    "Normal": {
        "ECG1": generate_lead1_ecg_pattern,
        "ECG2": generate_lead2_ecg_pattern,
        "ECG3": generate_lead1_v_ecg_pattern,
        "Resp": generate_rr_wave,
        "SpO2": generate_spo2_wave,
        "BP":   generate_bp_wave,
    },
    "Bradycardia":{
         "ECG1": generate_brady_lead1,
        "ECG2": generate_brady_lead2,
        "ECG3": generate_brady_lead3,
        "Resp": generate_rr_wave,
        "SpO2": generate_spo2_wave,
        "BP":   generate_bp_wave,
        
    },
      "Tachycardia":{
         "ECG1": generate_trachy_lead1,
        "ECG2": generate_trachy_lead2,
        "ECG3": generate_trachy_lead3,
        "Resp": generate_rr_wave,
        "SpO2": generate_spo2_wave,
        "BP":   generate_bp_wave,
        
    }
    
}

def generate_waveforms_for_scenario(scenario_name, hr, fs, num_beats=5):
    data = {}
    scenario = waveform_scenarios.get(scenario_name)
    if not scenario:
        raise ValueError(f"Scenario '{scenario_name}' not found")
    for signal_name, gen in scenario.items():
        t, y = gen(hr, fs, num_beats=num_beats)
        data[signal_name] = {"time": t, "waveform": y}
    return data
