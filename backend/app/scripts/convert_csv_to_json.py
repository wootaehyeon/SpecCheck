import csv
import json
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "backend" / "data"

CPU_CSV = PROJECT_ROOT / "cpu_benchmark" / "CPU_benchmark_v4.csv"
GPU_CSV = PROJECT_ROOT / "gpu_benchmark" / "GPU_benchmarks_v7.csv"

CPU_JSON = DATA_DIR / "cpu_benchmark.json"
GPU_JSON = DATA_DIR / "gpu_benchmark.json"

def convert_cpu():
    cpu_data = {}
    with open(CPU_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("cpuName", "").strip()
            if not name: continue
            
            try:
                score = int(row.get("cpuMark", 0))
            except ValueError:
                score = 0
            
            try:
                tdp = int(row.get("TDP", 0)) if row.get("TDP") else 0
            except ValueError:
                tdp = 0
                
            try:
                price = float(row.get("price", 0)) if row.get("price") else 0.0
            except ValueError:
                price = 0.0
                
            category = row.get("category", "")
            
            cpu_data[name] = {
                "score": score,
                "price_usd": price,
                "tdp": tdp,
                "category": category
            }
            
    with open(CPU_JSON, "w", encoding="utf-8") as f:
        json.dump(cpu_data, f, indent=4, ensure_ascii=False)
    print(f"Saved {len(cpu_data)} CPUs to {CPU_JSON}")


def convert_gpu():
    gpu_data = {}
    with open(GPU_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("gpuName", "").strip()
            if not name: continue
            
            try:
                score = int(row.get("G3Dmark", 0))
            except ValueError:
                score = 0
            
            try:
                tdp = int(row.get("TDP", 0)) if row.get("TDP") else 0
            except ValueError:
                tdp = 0
                
            try:
                price = float(row.get("price", 0)) if row.get("price") else 0.0
            except ValueError:
                price = 0.0
                
            category = row.get("category", "")
            
            gpu_data[name] = {
                "score": score,
                "price_usd": price,
                "tdp": tdp,
                "category": category
            }
            
    with open(GPU_JSON, "w", encoding="utf-8") as f:
        json.dump(gpu_data, f, indent=4, ensure_ascii=False)
    print(f"Saved {len(gpu_data)} GPUs to {GPU_JSON}")


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    convert_cpu()
    convert_gpu()
