import socket
import threading
import re
import json
import time

import hardware

# Default ports (match the sample app)
TCP_PORT = 5001
UDP_PORT = 5002


def _udp_broadcast(udp_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    msg = json.dumps({"service": "SimVital", "port": TCP_PORT})

    while True:
        try:
            sock.sendto(msg.encode(), ("<broadcast>", udp_port))
        except Exception:
            pass
        time.sleep(1)


def _tcp_server(manager, tcp_port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", tcp_port))
    server.listen(1)

    print("Remote control: waiting for phone...")
    conn, addr = server.accept()
    print("Remote control: phone connected:", addr)

    # low-latency
    try:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass

    conn.setblocking(False)
    buffer = ""

    # Use background emitter to avoid blocking recv loop; throttle rate with emit_interval
    last_emit_time = 0.0
    emit_interval = 0.5  # seconds (2 Hz, very low to prevent GUI stalls during slider drags)
    last_emitted_pv = {}  # track last emitted to skip duplicates
    min_change = 2  # only emit if value changed by at least this amount
    latest_pv = None
    pv_lock = threading.Lock()
    pv_cond = threading.Condition(pv_lock)

    # smoothing state
    smoothed = {}
    alpha = 0.3  # smoothing factor (0-1), higher = less smoothing
    keys_to_smooth = ["HR", "RR", "SpO2", "BP:SYS", "BP:DYS", "TEMP"]

    # track last seen ecg mode for this connection to avoid repeated triggers
    last_ecg_mode = None

    def _emit_worker():
        nonlocal last_emit_time, latest_pv, last_emitted_pv
        while True:
            with pv_cond:
                if latest_pv is None:
                    pv_cond.wait(timeout=emit_interval)
                pv_to_send = latest_pv
                latest_pv = None
            if pv_to_send is None:
                continue

            # Apply exponential smoothing to numeric fields before emitting
            send_pv = pv_to_send.copy()
            for key in keys_to_smooth:
                raw = pv_to_send.get(key)
                if raw is None:
                    continue
                m = re.search(r"-?\d+(?:\.\d+)?", str(raw))
                if not m:
                    continue
                try:
                    val = float(m.group(0))
                except Exception:
                    continue

                prev = smoothed.get(key)
                if prev is None:
                    smoothed[key] = val
                    out = val
                else:
                    out = prev + alpha * (val - prev)
                    smoothed[key] = out

                if key == "TEMP":
                    send_pv[key] = f"{out:.1f}"
                else:
                    send_pv[key] = str(int(round(out)))

            # Skip emit if no significant change from last sent values (deduplication)
            skip_emit = True
            for key in ["HR", "RR", "SpO2", "BP:SYS", "BP:DYS"]:
                try:
                    curr = float(re.search(r"-?\d+", send_pv.get(key, "0")).group(0))
                    last = float(re.search(r"-?\d+", last_emitted_pv.get(key, "0")).group(0))
                    if abs(curr - last) >= min_change:
                        skip_emit = False
                        break
                except Exception:
                    pass
            
            if skip_emit:
                continue

            try:
                if manager is not None:
                    manager.valuesUpdated.emit(send_pv)
                    last_emitted_pv = send_pv.copy()
            except Exception:
                pass

    if manager is not None:
        t_emit = threading.Thread(target=_emit_worker, daemon=True)
        t_emit.start()

    while True:
        try:
            data = conn.recv(4096).decode()
            if not data:
                break

            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                except Exception:
                    continue

                # Map incoming keys to hardware.prev_values
                # Accept either numeric or string values
                pv = hardware.prev_values
                updated = False

                if "hr" in parsed:
                    if parsed["hr"] is not None:
                        pv["HR"] = str(parsed["hr"])
                        updated = True
                if "rr" in parsed:
                    if parsed["rr"] is not None:
                        pv["RR"] = str(parsed["rr"])
                        updated = True
                if "spo2" in parsed:
                    if parsed["spo2"] is not None:
                        pv["SpO2"] = str(parsed["spo2"])
                        updated = True
                if "temp" in parsed:
                    if parsed["temp"] is not None:
                        pv["TEMP"] = str(parsed["temp"])
                        updated = True
                # Blood pressure may come as 'bp' ("120/80" or numeric)
                # or as separate 'bp_sys' and 'bp_dys' fields from the app.
                if "bp" in parsed or "bp_sys" in parsed or "bp_dys" in parsed:
                    try:
                        # Prefer explicit fields when present
                        if "bp_sys" in parsed or "bp_dys" in parsed:
                            sys_v = parsed.get("bp_sys")
                            dys_v = parsed.get("bp_dys")
                            if sys_v is not None:
                                pv["BP:SYS"] = str(sys_v)
                                updated = True
                            if dys_v is not None:
                                pv["BP:DYS"] = str(dys_v)
                                updated = True
                        else:
                            bp = parsed["bp"]
                            if isinstance(bp, str) and "/" in bp:
                                s, d = bp.split("/", 1)
                                pv["BP:SYS"] = s.strip()
                                pv["BP:DYS"] = d.strip()
                                updated = True
                            else:
                                val = int(bp)
                                pv["BP:SYS"] = str(val)
                                pv["BP:DYS"] = str(int(val * 0.66))
                                updated = True
                    except Exception:
                        pass

                if "nabp_sys" in parsed or "nabp_dys" in parsed:
                    try:
                        if "nabp_sys" in parsed:
                            pv["NABP:SYS"] = str(parsed["nabp_sys"])
                            updated = True
                        if "nabp_dys" in parsed:
                            pv["NABP:DYS"] = str(parsed["nabp_dys"])
                            updated = True
                    except Exception:
                        pass

                if "cvp" in parsed:
                    try:
                        pv["CVP"] = str(parsed["cvp"])
                        updated = True
                    except Exception:
                        pass

                if "pap_sys" in parsed or "pap_dys" in parsed:
                    try:
                        if "pap_sys" in parsed:
                            pv["PAP:SYS"] = str(parsed["pap_sys"])
                            updated = True
                        if "pap_dys" in parsed:
                            pv["PAP:DYS"] = str(parsed["pap_dys"])
                            updated = True
                    except Exception:
                        pass

                # Queue latest values for background emitter (non-blocking)
                if updated and manager is not None:
                    with pv_cond:
                        latest_pv = pv.copy()
                        pv_cond.notify()

                # Handle ECG mode -> map to scenarios
                # Only trigger when 'ecg' actually changes to avoid repeated audio from the app
                if "ecg" in parsed and manager is not None:
                    try:
                        ecg_mode = int(parsed["ecg"])
                        mapping = {1: 0, 2: 1, 3: 2}  # Normal, Bradycardia, Tachycardia
                        name_map = {1: "Normal", 2: "Bradycardia", 3: "Tachycardia"}
                        if ecg_mode in mapping:
                            # Only call set_scenario when mode changed since last message
                            if ecg_mode != last_ecg_mode:
                                last_ecg_mode = ecg_mode
                                # Log the app-triggered ECG change for debugging
                                try:
                                    print(f"Remote control: ECG change -> {name_map.get(ecg_mode, '?')} (mode {ecg_mode}) from {addr}")
                                except Exception:
                                    print(f"Remote control: ECG change -> mode {ecg_mode}")
                                manager.set_scenario(mapping[ecg_mode])
                    except Exception:
                        pass

        except BlockingIOError:
            time.sleep(0.001)
            continue
        except Exception as e:
            print("Remote control TCP error:", e)
            break


def start_remote_control(manager=None, tcp_port=TCP_PORT, udp_port=UDP_PORT):
    """Start UDP advertiser and TCP server in background threads.

    The `manager` parameter is optional; if provided the module will call
    `manager.valuesUpdated.emit()` and `manager.set_scenario()` when commands arrive.
    """
    t1 = threading.Thread(target=_udp_broadcast, args=(udp_port,), daemon=True)
    t1.start()

    t2 = threading.Thread(target=_tcp_server, args=(manager, tcp_port), daemon=True)
    t2.start()

    print(f"Remote control: started (TCP {tcp_port}, UDP advert {udp_port})")


if __name__ == "__main__":
    # quick local test
    start_remote_control(None)
    while True:
        time.sleep(1)
