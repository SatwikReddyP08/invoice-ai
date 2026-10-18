import sys
import os
import shutil
import platform
import ctypes

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]

print("=== System Info ===")
print("OS:", platform.system(), platform.release(), platform.version())
print("Machine:", platform.machine(), platform.processor())
print("Python Executable:", sys.executable)
print("Python Version:", sys.version)

print("\n=== Memory & Disk ===")
stat = MEMORYSTATUSEX()
stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
print(f"Total RAM: {stat.ullTotalPhys / (1024**3):.2f} GB")
print(f"Available RAM: {stat.ullAvailPhys / (1024**3):.2f} GB")

for drive in ["C:\\", "F:\\"]:
    if os.path.exists(drive):
        usage = shutil.disk_usage(drive)
        print(f"Drive {drive} - Total: {usage.total / (1024**3):.2f} GB, Free: {usage.free / (1024**3):.2f} GB")

print("\n=== Accelerator / PyTorch / CUDA Check ===")
try:
    import torch
    print("PyTorch Version:", torch.__version__)
    print("CUDA Available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("Device Count:", torch.cuda.device_count())
        print("Device Name:", torch.cuda.get_device_name(0))
        print(f"Allocated VRAM: {torch.cuda.memory_allocated(0)/(1024**2):.2f} MB")
        print(f"Reserved VRAM: {torch.cuda.memory_reserved(0)/(1024**2):.2f} MB")
except ImportError as e:
    print("PyTorch not installed in this environment:", e)

try:
    import subprocess
    smi = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
    if smi.returncode == 0:
        print("\nnvidia-smi output:\n", smi.stdout[:500])
    else:
        print("\nnvidia-smi returned non-zero code:", smi.returncode)
except Exception as e:
    print("nvidia-smi check failed:", e)
