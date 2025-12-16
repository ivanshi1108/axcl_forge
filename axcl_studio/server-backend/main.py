from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from typing import Dict, Any, List, Optional
import threading
import time
import re
import base64
import os
import shutil
import datetime
import asyncio
import subprocess
import pty
import select
import termios
import fcntl
import signal
import struct
from pathlib import Path
import io

DEFAULT_YOLO_MODEL_PATH = os.environ.get("DEFAULT_YOLO_MODEL_PATH", "/root/file_storage/models/yolov5s.axmodel")
STORAGE_DIR = os.environ.get("STORAGE_DIR", "/root/file_storage")
TRASH_DIR = os.path.join(STORAGE_DIR, ".trash")
NPU_ENABLE_PATH = "/proc/ax_proc/npu/enable"
NPU_TOP_PATH = "/proc/ax_proc/npu/top"
THERMAL_TEMP_PATH = "/sys/class/thermal/thermal_zone0/temp"


def _get_ramdisk_usage():
    """Get ramdisk (/dev/root) usage via df."""
    try:
        output = subprocess.check_output(["df", "/"], text=True)
        lines = output.strip().splitlines()
        if len(lines) < 2:
            return None
        parts = lines[1].split()
        if len(parts) < 6:
            return None
        filesystem, size_kb, used_kb, avail_kb, percent, mount = parts[:6]
        return {
          "filesystem": filesystem,
          "size_kb": int(size_kb),
          "used_kb": int(used_kb),
          "avail_kb": int(avail_kb),
          "used_percent": percent.strip('%'),
          "mount": mount
        }
    except Exception:
        return None

if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)
if not os.path.exists(TRASH_DIR):
    os.makedirs(TRASH_DIR)

try:
    import numpy as np
except ImportError as _np_exc:
    np = None  # type: ignore[assignment]
    _numpy_import_error = str(_np_exc)
else:
    _numpy_import_error = None

try:
    import axengine as _axengine_module
except ImportError as _axe_exc:
    _axengine_module = None  # type: ignore[assignment]
    _axengine_import_error = str(_axe_exc)
else:
    _axengine_import_error = None

_providers_import_error: Optional[str] = None
try:
    from axengine import get_available_providers as _ax_get_available_providers
    from axengine import get_all_providers as _ax_get_all_providers
    from axengine import axclrt_provider_name as _axclrt_provider_name
    from axengine import axengine_provider_name as _axengine_provider_name
except ImportError as _prov_exc:
    _providers_import_error = str(_prov_exc)
    _ax_get_available_providers = None  # type: ignore[assignment]
    _ax_get_all_providers = None  # type: ignore[assignment]
    _axclrt_provider_name = None  # type: ignore[assignment]
    _axengine_provider_name = None  # type: ignore[assignment]
else:
    _providers_import_error = None

try:
    from yolov5_runner import run_detection as _yolov5_run_detection
    from yolov5_runner import CLASS_NAMES as _yolov5_class_names
except ImportError as _runner_exc:
    _yolov5_run_detection = None  # type: ignore[assignment]
    _yolov5_class_names = []  # type: ignore[assignment]
    _yolov5_runner_error = str(_runner_exc)
else:
    _yolov5_runner_error = None


app = FastAPI()

# Unified system status API
@app.get("/system/status")
def get_system_status():
    # CMM memory
    cmm_mem = get_cmm_mem()
    # OS memory
    os_mem = get_os_mem()
    # RAMDisk
    ramdisk = get_ramdisk_usage()
    # CPU
    cpu = get_cpu_usage()
    # NPU
    npu = get_npu_usage()
    # Temperature
    temperature = get_temperature()
    return {
        "cmm_mem": cmm_mem,
        "os_mem": os_mem,
        "ramdisk": ramdisk,
        "cpu": cpu,
        "npu": npu,
        "temperature": temperature
    }


def _enable_npu_monitor():
    """Enable NPU utilization reporting if proc entry is available."""
    try:
        with open(NPU_ENABLE_PATH, "w") as f:
            f.write("1")
    except Exception as exc:  # noqa: BLE001
        # Just log, does not affect service startup
        print(f"NPU monitor enable failed: {exc}")

# Allow all origins CORS for frontend local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_stats: Dict[str, Dict[str, Any]] = {}
stats_lock = threading.Lock()
cpu_lock = threading.Lock()

cpu_stats: Dict[str, Any] = {
    "usage_percent": 0.0,
    "timestamp": None,
    "history": []  # type: ignore[list-item]
}
_cpu_prev_total = None
_cpu_prev_idle = None
_cpu_thread_started = False

def record_api_usage(path: str, client_ip: str, duration_ms: float):
    now = int(time.time())
    with stats_lock:
        if path not in api_stats:
            api_stats[path] = {
                "count": 0,
                "last_time": 0,
                "last_ip": "",
                "last_duration_ms": 0.0,
                "avg_duration_ms": 0.0
            }
        api_stats[path]["count"] += 1
        api_stats[path]["last_time"] = now
        api_stats[path]["last_ip"] = client_ip
        api_stats[path]["last_duration_ms"] = duration_ms
        # Average duration
        prev_avg = api_stats[path]["avg_duration_ms"]
        n = api_stats[path]["count"]
        api_stats[path]["avg_duration_ms"] = (prev_avg * (n-1) + duration_ms) / n

# General middleware to count all API calls
@app.middleware("http")
async def stats_middleware(request: Request, call_next):
    import time as _time
    start = _time.perf_counter()
    response = await call_next(request)
    duration_ms = (_time.perf_counter() - start) * 1000
    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"
    # Only count custom APIs (not /docs, /openapi, etc.)
    if not path.startswith("/docs") and not path.startswith("/openapi") and not path.startswith("/redoc"):
        record_api_usage(path, client_ip, duration_ms)
    return response

@app.get("/hello")
def hello():
    return {"message": "hello world"}

# Statistics API
@app.get("/stats")
def get_stats():
    with stats_lock:
        # Return all API statistics
        return api_stats

# CMM memory statistics API
@app.get("/cmm_mem")
def get_cmm_mem():
    info = {"total_kb": None, "used_kb": None}
    try:
        with open("/proc/ax_proc/mem_cmm_info", "r") as f:
            lines = f.readlines()
        for line in reversed(lines):
            if line.startswith(" total size="):
                # Example: total size=10485760KB(10240MB),used=283228KB(276MB + 604KB),remain=10202532KB(9963MB + 420KB),partition_number=1,block_number=41
                m = re.search(r"total size=(\d+)KB.*used=(\d+)KB", line)
                if m:
                    info["total_kb"] = int(m.group(1))
                    info["used_kb"] = int(m.group(2))
                break
    except Exception as e:
        info["error"] = str(e)
    return info

# OS memory statistics API
@app.get("/os_mem")
def get_os_mem():
    info = {"total_kb": None, "available_kb": None}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    info["total_kb"] = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    info["available_kb"] = int(line.split()[1])
                if info["total_kb"] is not None and info["available_kb"] is not None:
                    break
    except Exception as e:
        info["error"] = str(e)
    return info


@app.get("/ramdisk")
def get_ramdisk_usage():
    info = _get_ramdisk_usage()
    if info is None:
        return {"error": "ramdisk usage unavailable"}
    return info

# CPU usage statistics thread
def _read_cpu_times():
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        if not line.startswith("cpu "):
            return None
        parts = line.split()
        values = list(map(int, parts[1:]))
        idle = values[3] + values[4] if len(values) > 4 else values[3]
        total = sum(values)
        return total, idle
    except Exception:
        return None


def _cpu_sampler():
    global _cpu_prev_total, _cpu_prev_idle
    while True:
        data = _read_cpu_times()
        if data is not None:
            total, idle = data
            if _cpu_prev_total is not None and total > _cpu_prev_total:
                total_diff = total - _cpu_prev_total
                idle_diff = idle - _cpu_prev_idle if _cpu_prev_idle is not None else 0
                usage = 0.0
                if total_diff > 0:
                    usage = max(0.0, min(100.0, (1 - idle_diff / total_diff) * 100))
                ts = int(time.time())
                with cpu_lock:
                    cpu_stats["usage_percent"] = usage
                    cpu_stats["timestamp"] = ts
                    history: List[Dict[str, Any]] = cpu_stats.setdefault("history", [])  # type: ignore[assignment]
                    history.append({"timestamp": ts, "usage_percent": usage})
                    if len(history) > 120:
                        del history[:-120]
            _cpu_prev_total = total
            _cpu_prev_idle = idle
        time.sleep(5)


def _ensure_cpu_thread():
    global _cpu_thread_started
    if not _cpu_thread_started:
        thread = threading.Thread(target=_cpu_sampler, daemon=True)
        thread.start()
        _cpu_thread_started = True



@app.get("/cpu_usage")
def get_cpu_usage():
    _ensure_cpu_thread()
    with cpu_lock:
        stats = cpu_stats.copy()
        if not stats.get("history"):
            # If no history data, return initial 0 value
            current_time = time.time()
            stats["history"] = [{"usage_percent": 0, "timestamp": current_time}]
            stats["usage_percent"] = 0
            stats["timestamp"] = current_time
        return stats


def _read_npu_top() -> Dict[str, Any]:
    try:
        with open(NPU_TOP_PATH, "r") as f:
            content = f.read().strip()
    except Exception as exc:  # noqa: BLE001
        return {"percent": None, "raw": "", "error": str(exc)}

    if "nputop info is empty" in content:
        return {"percent": 0.0, "raw": content}

    if "nputop info not updated" in content:
        return {"percent": 0.0, "raw": content}

    m = re.search(r"utilization:(\d+)%", content)
    if m:
        return {"percent": float(m.group(1)), "raw": content}

    return {"percent": None, "raw": content, "error": "utilization not found"}


@app.get("/npu_usage")
def get_npu_usage():
    """Get NPU utilization from /proc."""
    data = _read_npu_top()
    data["timestamp"] = int(time.time())
    return data



@app.get("/temperature")
def get_temperature():
    """Get board temperature in Celsius with 0.1 precision."""
    try:
        with open(THERMAL_TEMP_PATH, "r") as f:
            raw = f.read().strip()
        milli_c = int(raw)
        celsius = round(milli_c / 1000, 1)
        return {"celsius": celsius, "raw": raw, "timestamp": int(time.time())}
    except Exception as exc:  # noqa: BLE001
        return {"celsius": None, "raw": "", "error": str(exc), "timestamp": int(time.time())}


@app.get("/providers")
def get_providers():
    if _providers_import_error is not None:
        return {
            "available": [],
            "all": [],
            "error": _providers_import_error,
            "default_model_path": DEFAULT_YOLO_MODEL_PATH,
            "default_provider": _axengine_provider_name or "AUTO"
        }
    if _ax_get_available_providers is None or _ax_get_all_providers is None:
        return {
            "available": [],
            "all": [],
            "error": "axengine provider helpers unavailable",
            "default_model_path": DEFAULT_YOLO_MODEL_PATH,
            "default_provider": _axengine_provider_name or "AUTO"
        }
    available = list(_ax_get_available_providers())
    preferred_order: List[str] = []
    for name in (_axengine_provider_name, _axclrt_provider_name):
        if name and name in available and name not in preferred_order:
            preferred_order.append(name)
    for name in available:
        if name not in preferred_order:
            preferred_order.append(name)
    return {
        "available": preferred_order,
        "all": _ax_get_all_providers(),
        "default_model_path": DEFAULT_YOLO_MODEL_PATH,
        "default_provider": _axengine_provider_name or "AUTO"
    }


def _ensure_yolo_ready():
    issues: List[str] = []
    if _axengine_import_error:
        issues.append(f"axengine 导入失败: {_axengine_import_error}")
    if _numpy_import_error:
        issues.append(f"numpy 导入失败: {_numpy_import_error}")
    if _yolov5_runner_error:
        issues.append(f"yolov5 推理模块导入失败: {_yolov5_runner_error}")
    if _axengine_provider_name is None or _axclrt_provider_name is None:
        issues.append("缺少 axengine 推理引擎标识")
    if _axengine_module is None:
        issues.append("axengine 模块不可用")
    if _ax_get_available_providers is None or _ax_get_all_providers is None:
        issues.append("无法获取推理引擎列表")
    if _yolov5_run_detection is None:
        issues.append("yolov5 推理逻辑不可用")
    if issues:
        raise HTTPException(status_code=500, detail="; ".join(issues))


def _run_yolov5_inference(
    model_path: Optional[str],
    image_bytes: bytes,
    repeat: int,
    provider: str,
    device_id: int,
    is_raw: bool = False,
    origin_width: Optional[int] = None,
    origin_height: Optional[int] = None
) -> Dict[str, Any]:
    _ensure_yolo_ready()
    assert _axengine_module is not None
    assert np is not None
    assert _ax_get_available_providers is not None
    assert _yolov5_run_detection is not None

    if repeat < 1 or repeat > 1000000:
        raise HTTPException(status_code=400, detail="repeat 需在 1 到 1000000 之间")
    if device_id < 0:
        raise HTTPException(status_code=400, detail="device_id 不能为负数")

    model_path_trimmed = (model_path or "").strip() if model_path is not None else ""
    chosen_model_path = model_path_trimmed or (DEFAULT_YOLO_MODEL_PATH or "")

    if not chosen_model_path:
        raise HTTPException(status_code=400, detail="模型路径未提供，且未配置默认路径")

    model_path_obj = Path(chosen_model_path)
    if not model_path_obj.exists() or not model_path_obj.is_file():
        raise HTTPException(status_code=400, detail=f"模型文件不存在: {chosen_model_path}")

    if not image_bytes:
        raise HTTPException(status_code=400, detail="未接收到图片数据")

    preprocessed_input = None
    origin_shape = None

    if is_raw:
        if origin_width is None or origin_height is None:
            raise HTTPException(status_code=400, detail="Raw 模式需要提供 origin_width 和 origin_height")
        try:
            # Assume frontend sends 640x640x3 RGB data
            np_array = np.frombuffer(image_bytes, dtype=np.uint8)
            # Check if data size matches expected (640*640*3 = 1228800)
            expected_size = 640 * 640 * 3
            if np_array.size != expected_size:
                 raise HTTPException(status_code=400, detail=f"Raw data size mismatch, expected {expected_size}, actual {np_array.size}")
            
            preprocessed_input = np_array.reshape(1, 640, 640, 3)
            origin_shape = (origin_height, origin_width)
        except Exception as e:
             raise HTTPException(status_code=400, detail=f"解析 Raw 数据失败: {e}")
    else:
        raise HTTPException(status_code=400, detail="后端不再支持非 Raw 模式的图片处理，请确保前端已开启预处理")

    available = _ax_get_available_providers()
    provider_choice = provider or "AUTO"

    if provider_choice != "AUTO" and provider_choice not in available:
        raise HTTPException(status_code=400, detail=f"推理引擎 {provider_choice} 不可用，当前可用: {available}")

    session = None
    last_error: Optional[Exception] = None
    if provider_choice == "AUTO":
        candidate_providers: List[Any] = []
        if _axengine_provider_name and _axengine_provider_name in available:
            candidate_providers.append(_axengine_provider_name)
        if _axclrt_provider_name and _axclrt_provider_name in available:
            candidate_providers.append((_axclrt_provider_name, {"device_id": device_id}))
        if not candidate_providers:
            candidate_providers.append(None)

        for candidate in candidate_providers:
            try:
                if candidate is None:
                    session = _axengine_module.InferenceSession(str(model_path_obj))
                elif isinstance(candidate, tuple):
                    session = _axengine_module.InferenceSession(str(model_path_obj), providers=[candidate])
                else:
                    session = _axengine_module.InferenceSession(str(model_path_obj), providers=[candidate])
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                continue
        if session is None:
            error_msg = "无法初始化任何推理引擎"
            if last_error is not None:
                error_msg += f": {last_error}"
            raise HTTPException(status_code=500, detail=error_msg) from last_error
    else:
        try:
            if provider_choice == _axclrt_provider_name:
                config = [(_axclrt_provider_name, {"device_id": device_id})]
            elif provider_choice == _axengine_provider_name:
                config = [_axengine_provider_name]
            else:
                raise HTTPException(status_code=400, detail=f"不支持的推理引擎: {provider_choice}")
            session = _axengine_module.InferenceSession(str(model_path_obj), providers=config)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"推理引擎 {provider_choice} 初始化失败: {exc}") from exc

    try:
        det_array, metrics, _, logs_raw = _yolov5_run_detection(
            session, 
            inputs=preprocessed_input,
            origin_shape=origin_shape,
            repeat=repeat
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"推理执行失败: {exc}") from exc

    detections_payload: List[Dict[str, Any]] = []
    class_names = _yolov5_class_names or []
    for row in det_array:
        cls_idx = int(row[5]) if row.shape[0] >= 6 else -1
        label = class_names[cls_idx] if 0 <= cls_idx < len(class_names) else str(cls_idx)
        detections_payload.append({
            "label": label,
            "score": float(row[4]) if row.shape[0] >= 5 else 0.0,
            "box": [float(row[0]), float(row[1]), float(row[2]), float(row[3])]
        })

    return {
        "success": True,
        "metrics": metrics,
        "detections": detections_payload,
        "image": None,
        "logs": logs_raw,
        "provider": provider_choice,
        "repeat": repeat,
        "model_path": str(model_path_obj)
    }


@app.post("/yolov5/run")
async def run_yolov5(
    model_path: Optional[str] = Form(None),
    provider: str = Form("AUTO"),
    repeat: int = Form(1),
    device_id: int = Form(0),
    is_raw: bool = Form(False),
    origin_width: Optional[int] = Form(None),
    origin_height: Optional[int] = Form(None),
    image: UploadFile = File(...)
):
    try:
        image_bytes = await image.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {exc}") from exc

    result = await run_in_threadpool(
        _run_yolov5_inference,
        model_path,
        image_bytes,
        repeat,
        provider,
        device_id,
        is_raw,
        origin_width,
        origin_height
    )
    return result


import mimetypes

# Initialize MIME types
mimetypes.init()
mimetypes.add_type('video/mp4', '.mp4')
mimetypes.add_type('video/webm', '.webm')
mimetypes.add_type('video/ogg', '.ogg')
# Text/code files
mimetypes.add_type('text/plain', '.py')
mimetypes.add_type('text/plain', '.c')
mimetypes.add_type('text/plain', '.h')
mimetypes.add_type('text/plain', '.cpp')
mimetypes.add_type('text/plain', '.hpp')
mimetypes.add_type('text/plain', '.js')
mimetypes.add_type('text/plain', '.json')
mimetypes.add_type('text/plain', '.vue')
mimetypes.add_type('text/plain', '.log')
mimetypes.add_type('text/plain', '.md')
mimetypes.add_type('text/plain', '.yaml')
mimetypes.add_type('text/plain', '.yml')
mimetypes.add_type('text/plain', '.sh')
mimetypes.add_type('text/plain', '.pdb') # Assume PDB is text format
mimetypes.add_type('application/pdf', '.pdf')

# Helper function: safe path check
def get_safe_path(path: str):
    # Remove leading /
    if path.startswith("/"):
        path = path[1:]
    # Remove .. to prevent directory traversal
    path = path.replace("..", "")
    full_path = os.path.join(STORAGE_DIR, path)
    return full_path


def _dir_size(target: str, skip_trash: bool = True) -> int:
    """Compute total size of file or directory. Optionally skip .trash when traversing root."""
    if not os.path.exists(target):
        return 0
    if os.path.isfile(target):
        return os.path.getsize(target)

    total = 0
    for root, dirs, files in os.walk(target):
        if skip_trash and ".trash" in dirs:
            dirs.remove(".trash")
        for name in files:
            try:
                fp = os.path.join(root, name)
                total += os.path.getsize(fp)
            except OSError:
                continue
    return total

# File management API
@app.get("/files")
def list_files(path: str = Query("", description="Subdirectory path")):
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR, exist_ok=True)
    if not os.path.exists(TRASH_DIR):
        os.makedirs(TRASH_DIR, exist_ok=True)
    full_path = get_safe_path(path)
    if not os.path.exists(full_path):
        return []
    
    files = []
    try:
        for entry in os.scandir(full_path):
            # Hide trash directory and hidden files
            if entry.name == ".trash" or entry.name.startswith("."):
                continue
                
            stat = entry.stat()
            files.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": stat.st_size if not entry.is_dir() else 0,
                "mtime": stat.st_mtime,
                "mtime_str": datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
    except OSError:
        return []
    
    # Sort: directories first, then by time descending
    files.sort(key=lambda x: (not x["is_dir"], -x["mtime"]))
    return files


@app.get("/files/trash")
def list_trash():
    if not os.path.exists(TRASH_DIR):
        os.makedirs(TRASH_DIR, exist_ok=True)

    items = []
    try:
        for entry in os.scandir(TRASH_DIR):
            stat = entry.stat()
            size_val = _dir_size(entry.path, skip_trash=False) if entry.is_dir() else stat.st_size
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": size_val,
                "mtime": stat.st_mtime,
                "mtime_str": datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
    except OSError:
        return []

    items.sort(key=lambda x: (not x["is_dir"], -x["mtime"]))
    return items


@app.delete("/files/trash/clear")
def clear_trash():
    if not os.path.exists(TRASH_DIR):
        os.makedirs(TRASH_DIR, exist_ok=True)
        return {"status": "success", "message": "Trash already empty"}

    try:
        for entry in os.scandir(TRASH_DIR):
            path = entry.path
            try:
                if entry.is_dir():
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"清空回收站失败: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"清空回收站失败: {exc}") from exc

    return {"status": "success", "message": "Trash cleared"}


@app.get("/files/size")
def get_dir_size(path: str = Query("", description="Subdirectory path")):
    full_path = get_safe_path(path)
    include_trash = path.startswith(".trash") or path.startswith("/.trash")
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Path not found")

    size_val = _dir_size(full_path, skip_trash=not include_trash)
    return {"path": path, "size_bytes": size_val}

@app.post("/files/upload")
def upload_file(file: UploadFile = File(...), path: str = Form("")):
    full_dir_path = get_safe_path(path)
    if not os.path.exists(full_dir_path):
        os.makedirs(full_dir_path)
        
    filepath = os.path.join(full_dir_path, file.filename)
    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    return {"filename": file.filename, "status": "success"}

@app.get("/files/download")
def download_file(path: str = Query(..., description="File path"), inline: bool = False):
    full_path = get_safe_path(path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    filename = os.path.basename(full_path)
    ext = os.path.splitext(filename)[1].lower()

    # HEIC/HEIF real-time conversion logic
    if inline and _heic_supported and ext in ['.heic', '.heif']:
        try:
            img = Image.open(full_path)
            # Convert to RGB
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            import io
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85)
            img_byte_arr.seek(0)
            
            return Response(content=img_byte_arr.getvalue(), media_type="image/jpeg")
        except Exception as e:
            print(f"HEIC conversion failed: {e}")
            # If conversion fails, fallback to original file sending
            pass

    media_type, _ = mimetypes.guess_type(full_path)
    return FileResponse(
        full_path, 
        filename=filename if not inline else None,
        media_type=media_type,
        content_disposition_type="inline" if inline else "attachment"
    )

@app.delete("/files")
def delete_file(path: str = Query(..., description="File or directory path")):
    full_path = get_safe_path(path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Path not found")
    
    # Prevent deleting trash itself
    if full_path == TRASH_DIR or full_path.startswith(TRASH_DIR):
         raise HTTPException(status_code=403, detail="Cannot delete trash directly via this API")
    try:
        # Permanent delete: remove file or directory
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")
    return {"status": "success", "message": "Deleted"}


@app.post("/files/trash/restore")
def restore_from_trash(name: str = Query(..., description="Name inside trash")):
    if not os.path.exists(TRASH_DIR):
        raise HTTPException(status_code=404, detail="Trash not found")

    src_path = os.path.join(TRASH_DIR, name)
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail="Trash item not found")

    dest_path = os.path.join(STORAGE_DIR, name.split("_", 1)[-1] if "_" in name else name)
    try:
        # Ensure destination directory exists
        os.makedirs(STORAGE_DIR, exist_ok=True)
        if os.path.exists(dest_path):
            raise HTTPException(status_code=400, detail="目标已存在，无法恢复")
        shutil.move(src_path, dest_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"恢复失败: {exc}") from exc
    return {"status": "success"}

@app.post("/files/mkdir")
def create_directory(path: str = Form(""), name: str = Form(...)):
    full_dir_path = get_safe_path(path)
    new_dir_path = os.path.join(full_dir_path, name)
    if os.path.exists(new_dir_path):
        raise HTTPException(status_code=400, detail="Directory already exists")
    try:
        os.makedirs(new_dir_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mkdir failed: {str(e)}")
    return {"status": "success"}

@app.post("/files/rename")
def rename_item(path: str = Form(...), new_name: str = Form(...)):
    full_path = get_safe_path(path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Item not found")
    
    parent_dir = os.path.dirname(full_path)
    new_path = os.path.join(parent_dir, new_name)
    
    if os.path.exists(new_path):
        raise HTTPException(status_code=400, detail="Target name already exists")
        
    try:
        os.rename(full_path, new_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rename failed: {str(e)}")
    return {"status": "success"}

# WebSocket terminal session management
active_terminals: Dict[str, Dict[str, Any]] = {}
terminal_lock = threading.Lock()

@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    """WebSocket terminal session"""
    await websocket.accept()
    
    # Generate session ID
    session_id = f"terminal_{int(time.time())}_{id(websocket)}"
    
    try:
        # Create pseudo terminal
        master_fd, slave_fd = pty.openpty()
        
        # Set terminal attributes
        attrs = termios.tcgetattr(slave_fd)
        attrs[6][termios.VMIN] = 1  # Minimum character count
        attrs[6][termios.VTIME] = 0  # Timeout
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
        
        # Start login shell to load system/user config (including completion)
        process = subprocess.Popen(
            ["/bin/bash", "-l"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
            cwd="/root",
            env=dict(os.environ,
                    TERM="xterm-256color",
                    COLUMNS="80",
                    LINES="24",
                    LANG="C.UTF-8",
                    LC_ALL="C.UTF-8",
                    LC_CTYPE="C.UTF-8" )
        )
        
        # Set non-blocking mode
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        
        # Store session information
        with terminal_lock:
            active_terminals[session_id] = {
                "process": process,
                "master_fd": master_fd,
                "slave_fd": slave_fd,
                "websocket": websocket,
                "last_activity": time.time()
            }
        
        # Send welcome message
        await websocket.send_json({
            "type": "output",
            "data": "\r\nWelcome to axcl Virtual Terminal\r\nType 'help' for available commands, 'exit' to quit\r\n\r\n$ "
        })
        
        # Main loop
        while True:
            try:
                # Check if process is still alive
                if process.poll() is not None:
                    await websocket.send_json({
                        "type": "output",
                        "data": "\r\n[Process exited]\r\n"
                    })
                    break
                
                # Read terminal output
                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.1)
                    if ready:
                        output = os.read(master_fd, 1024).decode('utf-8', errors='replace')
                        if output:
                            await websocket.send_json({
                                "type": "output",
                                "data": output
                            })
                except (OSError, BlockingIOError):
                    pass
                
                # Check WebSocket messages
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=0.1)
                    
                    if message["type"] == "input":
                        # Send input to terminal
                        data = message["data"]
                        if data:  # Only process non-empty input
                            os.write(master_fd, data.encode('utf-8'))
                    
                    elif message["type"] == "resize":
                        # Handle terminal size adjustment
                        cols = message.get("cols", 80)
                        rows = message.get("rows", 24)
                        try:
                            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, 
                                      struct.pack('HHHH', rows, cols, 0, 0))
                            os.kill(process.pid, signal.SIGWINCH)
                        except:
                            pass
                    
                    # Update activity time
                    with terminal_lock:
                        if session_id in active_terminals:
                            active_terminals[session_id]["last_activity"] = time.time()
                            
                except asyncio.TimeoutError:
                    continue
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"Terminal session error: {e}")
                break
    
    finally:
        # Clean up resources
        with terminal_lock:
            if session_id in active_terminals:
                terminal_info = active_terminals[session_id]
                try:
                    if terminal_info["process"] and terminal_info["process"].poll() is None:
                        os.killpg(os.getpgid(terminal_info["process"].pid), signal.SIGTERM)
                        terminal_info["process"].wait(timeout=2)
                except:
                    pass
                
                try:
                    os.close(terminal_info["master_fd"])
                    os.close(terminal_info["slave_fd"])
                except:
                    pass
                
                del active_terminals[session_id]

@app.get("/terminal/sessions")
def get_terminal_sessions():
    """Get active terminal sessions"""
    with terminal_lock:
        sessions = []
        for session_id, info in active_terminals.items():
            sessions.append({
                "session_id": session_id,
                "pid": info["process"].pid if info["process"] else None,
                "last_activity": info["last_activity"]
            })
        return {"sessions": sessions}

@app.delete("/terminal/session/{session_id}")
def kill_terminal_session(session_id: str):
    """Terminate specified terminal session"""
    with terminal_lock:
        if session_id not in active_terminals:
            raise HTTPException(status_code=404, detail="Session not found")
        
        terminal_info = active_terminals[session_id]
        try:
            if terminal_info["process"] and terminal_info["process"].poll() is None:
                os.killpg(os.getpgid(terminal_info["process"].pid), signal.SIGKILL)
        except:
            pass
        
        return {"status": "terminated"}

# Periodically clean up inactive terminal sessions
def cleanup_inactive_terminals():
    """Clean up inactive terminal sessions (inactive for more than 30 minutes)"""
    while True:
        time.sleep(300)  # Check every 5 minutes
        
        current_time = time.time()
        to_remove = []
        
        with terminal_lock:
            for session_id, info in active_terminals.items():
                if current_time - info["last_activity"] > 1800:  # 30 minutes
                    to_remove.append(session_id)
            
            for session_id in to_remove:
                terminal_info = active_terminals[session_id]
                try:
                    if terminal_info["process"] and terminal_info["process"].poll() is None:
                        os.killpg(os.getpgid(terminal_info["process"].pid), signal.SIGTERM)
                        terminal_info["process"].wait(timeout=2)
                except:
                    pass
                
                try:
                    os.close(terminal_info["master_fd"])
                    os.close(terminal_info["slave_fd"])
                except:
                    pass
                
                del active_terminals[session_id]
                print(f"Cleaned up inactive terminal session: {session_id}")

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_inactive_terminals, daemon=True)
cleanup_thread.start()

_enable_npu_monitor()
_ensure_cpu_thread()

# DEV: uvicorn main:app --host 0.0.0.0 --port 8018