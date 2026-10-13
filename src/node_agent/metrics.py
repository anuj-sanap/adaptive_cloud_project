"""
metrics.py - Telemetry Metric Collector module using psutil and platform.
Collects CPU, RAM, Disk, Network, Disk I/O, Temperature, Process Count, OS, and Host details.
"""

import os
import time
import socket
import platform
import psutil
from datetime import datetime, timezone


def get_cpu_temperature():
    """
    Attempts to retrieve CPU temperature using psutil sensors.
    Returns float (temperature in °C) if available, or None if unsupported on OS/hardware.
    """
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                for sensor_name, entries in temps.items():
                    for entry in entries:
                        if entry.current is not None and entry.current > 0:
                            return round(entry.current, 1)
    except Exception:
        pass
    return None


def collect_node_telemetry(node_id: str) -> dict:
    """
    Collects live system metrics and returns a standardized telemetry payload dictionary.
    """
    # Host and OS information
    hostname = socket.gethostname()
    os_info = f"{platform.system()} {platform.release()} ({platform.architecture()[0]})"
    timestamp = datetime.now(timezone.utc).isoformat()

    # CPU utilization (%)
    cpu_util = round(psutil.cpu_percent(interval=None), 2)
    cpu_count_logical = psutil.cpu_count(logical=True)
    cpu_count_physical = psutil.cpu_count(logical=False) or cpu_count_logical

    # RAM utilization (%)
    vm = psutil.virtual_memory()
    ram_util = round(vm.percent, 2)
    ram_used_mb = round(vm.used / (1024 * 1024), 2)
    ram_total_mb = round(vm.total / (1024 * 1024), 2)

    # Disk utilization (%)
    disk_path = "C:\\" if platform.system() == "Windows" else "/"
    try:
        du = psutil.disk_usage(disk_path)
        disk_util = round(du.percent, 2)
        disk_used_gb = round(du.used / (1024 ** 3), 2)
        disk_total_gb = round(du.total / (1024 ** 3), 2)
        disk_free_gb = round(du.free / (1024 ** 3), 2)
    except Exception:
        disk_util, disk_used_gb, disk_total_gb, disk_free_gb = None, None, None, None

    # Network I/O counters
    net_io = psutil.net_io_counters()
    net_sent_bytes = net_io.bytes_sent if net_io else None
    net_recv_bytes = net_io.bytes_recv if net_io else None
    net_sent_mb = round(net_sent_bytes / (1024 * 1024), 2) if net_sent_bytes is not None else None
    net_recv_mb = round(net_recv_bytes / (1024 * 1024), 2) if net_recv_bytes is not None else None

    # Disk I/O counters
    disk_io = psutil.disk_io_counters()
    disk_read_bytes = disk_io.read_bytes if disk_io else None
    disk_write_bytes = disk_io.write_bytes if disk_io else None
    disk_read_mb = round(disk_read_bytes / (1024 * 1024), 2) if disk_read_bytes is not None else None
    disk_write_mb = round(disk_write_bytes / (1024 * 1024), 2) if disk_write_bytes is not None else None

    # CPU temperature & process count
    cpu_temp = get_cpu_temperature()
    process_count = len(psutil.pids())

    # Load averages (1-min, 5-min, 15-min) using psutil.getloadavg()
    load_1min, load_5min, load_15min = None, None, None
    if hasattr(psutil, "getloadavg"):
        try:
            loads = psutil.getloadavg()
            if loads and len(loads) == 3:
                load_1min = round(float(loads[0]), 2)
                load_5min = round(float(loads[1]), 2)
                load_15min = round(float(loads[2]), 2)
        except Exception:
            pass

    # Execution / Host uptime duration in seconds
    try:
        boot_time = psutil.boot_time()
        duration_sec = int(time.time() - boot_time)
    except Exception:
        duration_sec = None

    # Node server type / role (configurable via env var, defaults to ComputeNode)
    server_type = os.getenv("NODE_SERVER_TYPE", "ComputeNode")

    payload = {
        "node_id": node_id,
        "hostname": hostname,
        "operating_system": os_info,
        "location_label": os.getenv("NODE_LOCATION_LABEL", "").strip() or None,
        "timestamp": timestamp,
        "metrics": {
            "cpu_utilization": cpu_util,
            "cpu_count_logical": cpu_count_logical,
            "cpu_count_physical": cpu_count_physical,
            "cpu_temperature_c": cpu_temp,
            "ram_utilization": ram_util,
            "ram_used_mb": ram_used_mb,
            "ram_total_mb": ram_total_mb,
            "disk_utilization": disk_util,
            "disk_used_gb": disk_used_gb,
            "disk_total_gb": disk_total_gb,
            "disk_free_gb": disk_free_gb,
            "network_sent_bytes": net_sent_bytes,
            "network_recv_bytes": net_recv_bytes,
            "network_sent_mb": net_sent_mb,
            "network_recv_mb": net_recv_mb,
            "disk_read_bytes": disk_read_bytes,
            "disk_write_bytes": disk_write_bytes,
            "disk_read_mb": disk_read_mb,
            "disk_write_mb": disk_write_mb,
            "process_count": process_count,
            "load_1min": load_1min,
            "load_5min": load_5min,
            "load_15min": load_15min,
            "duration_sec": duration_sec,
            "server_type": server_type
        }
    }
    return payload


if __name__ == "__main__":
    import json
    import socket
    # Call cpu_percent once to initialize baseline
    psutil.cpu_percent(interval=1.0)
    print(json.dumps(collect_node_telemetry(f"node_{socket.gethostname().lower()}"), indent=2))
