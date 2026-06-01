#!/usr/bin/env python3
"""
Automated LLM Inference Experiment Runner
==========================================
Runs all 80 inference combinations (2 models x 10 reports x 4 prompt types)
through the Ollama API with explicit context clearing between every run.

CAF-2024-001 and CAF-2025-002 are real anonymized safety reports.
All other reports are synthetic.

Captures inference metrics (TPS, latency, token counts) directly from the
Ollama API and system metrics (CPU utilisation, RAM usage) by sampling
/proc/stat and /proc/meminfo in a background thread for the duration of
each run.

Eliminates context bleed risk and manual handling errors.

Usage:
    python3 run_experiment.py

Repository layout expected:
    reports/          - one .txt file per report, named by report ID
    prompts/          - prompts.csv with columns: prompt_type, instruction
    ground_truth/     - see ground_truth/README.md
    results/          - created automatically on first run
      responses/      - one .txt file per inference run

Output:
    results/results.csv       - all metrics
    results/responses/        - individual response text files
    results/experiment.log    - run log

Requirements:
    - Ollama running on localhost:11434
    - LLaMA 3.1 (llama3.1:latest) and Qwen 2.5 32B (qwen2.5:32b) pulled
    - Python 3 with standard library only (no external dependencies)
    - Linux host (reads from /proc; the rest of the script is portable)

Author: Inusah Mohammed
Karelia University of Applied Sciences
Joensuu, Finland
LinkedIn: https://www.linkedin.com/in/inusah-mohammed/
"""

import json
import urllib.request
import urllib.error
import csv
import os
import sys
import time
import threading
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://localhost:11434/api/generate"
REPORTS_DIR  = os.path.join(os.path.dirname(__file__), "reports")
PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "prompts", "prompts.csv")
RESULTS_DIR  = os.path.join(os.path.dirname(__file__), "results")
RESPONSE_DIR = os.path.join(RESULTS_DIR, "responses")
RESULTS_CSV  = os.path.join(RESULTS_DIR, "results.csv")
LOG_FILE     = os.path.join(RESULTS_DIR, "experiment.log")

SAMPLE_INTERVAL = 1.0  # seconds between system metric samples during a run

MODELS = [
    "llama3.1:latest",
    "qwen2.5:32b",
]

# ─── DATA LOADING ─────────────────────────────────────────────────────────────

def load_reports(reports_dir):
    """Load all .txt report files from reports_dir.

    Returns an ordered dict {report_id: report_text}.
    Report ID is the filename without extension.
    Files are sorted alphabetically for reproducible run ordering.
    """
    reports = {}
    if not os.path.isdir(reports_dir):
        print(f"ERROR: Reports directory not found: {reports_dir}")
        sys.exit(1)

    files = sorted(f for f in os.listdir(reports_dir) if f.endswith(".txt"))
    if not files:
        print(f"ERROR: No .txt files found in {reports_dir}")
        sys.exit(1)

    for fname in files:
        report_id = os.path.splitext(fname)[0]
        path = os.path.join(reports_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            reports[report_id] = f.read().strip()

    return reports


def load_prompts(prompts_file):
    """Load prompt types and instructions from prompts CSV.

    Returns an ordered dict {prompt_type: instruction}.
    CSV must have columns: prompt_type, instruction.
    Row order is preserved for reproducible run ordering.
    """
    prompts = {}
    if not os.path.isfile(prompts_file):
        print(f"ERROR: Prompts file not found: {prompts_file}")
        sys.exit(1)

    with open(prompts_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prompts[row["prompt_type"]] = row["instruction"]

    if not prompts:
        print(f"ERROR: No prompts loaded from {prompts_file}")
        sys.exit(1)

    return prompts

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def log(msg):
    """Print to console AND append to log file with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def call_ollama(model, prompt, keep_alive=0):
    """Send a prompt to Ollama with explicit context clearing.

    keep_alive=0 means the model is unloaded from memory immediately after
    the request, which guarantees no context carries over to the next call.
    This is the critical fix for the context bleed problem.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def safe_filename(s):
    """Convert any string to a safe filename."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)


# ─── SYSTEM METRICS SAMPLING ──────────────────────────────────────────────────
# Reads /proc directly so we don't depend on vmstat/free being available
# and so we get the same numbers a parallel monitoring session would see.

def _read_cpu_times():
    """Return (idle, total) jiffies from /proc/stat aggregate cpu line."""
    with open("/proc/stat") as f:
        parts = f.readline().split()
    values = [int(x) for x in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)  # idle + iowait
    total = sum(values)
    return idle, total


def _read_mem_kb():
    """Return (used_kb, total_kb) from /proc/meminfo using MemTotal - MemAvailable."""
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            info[key.strip()] = int(rest.strip().split()[0])
    total = info["MemTotal"]
    available = info.get("MemAvailable", info["MemFree"])
    used = total - available
    return used, total


class SystemMonitor:
    """Background thread that samples CPU% and RAM usage at fixed intervals.

    CPU% is computed across the whole machine (all cores, weighted average).
    RAM is reported in GB. The baseline is captured at start() and the model
    footprint is computed as peak_used - baseline_used.
    """

    def __init__(self, interval=SAMPLE_INTERVAL):
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._cpu_samples = []
        self._ram_used_samples_kb = []
        self._baseline_used_kb = 0
        self._mem_total_kb = 0

    def start(self):
        self._stop.clear()
        self._cpu_samples = []
        self._ram_used_samples_kb = []
        self._baseline_used_kb, self._mem_total_kb = _read_mem_kb()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        prev_idle, prev_total = _read_cpu_times()
        while not self._stop.is_set():
            time.sleep(self.interval)
            idle, total = _read_cpu_times()
            d_idle = idle - prev_idle
            d_total = total - prev_total
            cpu_pct = 100.0 * (1 - (d_idle / d_total)) if d_total > 0 else 0.0
            self._cpu_samples.append(cpu_pct)
            prev_idle, prev_total = idle, total
            used_kb, _ = _read_mem_kb()
            self._ram_used_samples_kb.append(used_kb)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def summary(self):
        """Return dict of peak/mean CPU% and peak RAM (GB) and model footprint (GB)."""
        peak_cpu = max(self._cpu_samples) if self._cpu_samples else 0.0
        mean_cpu = sum(self._cpu_samples) / len(self._cpu_samples) if self._cpu_samples else 0.0
        peak_ram_kb = max(self._ram_used_samples_kb) if self._ram_used_samples_kb else self._baseline_used_kb
        baseline_gb  = self._baseline_used_kb / (1024 * 1024)
        peak_ram_gb  = peak_ram_kb / (1024 * 1024)
        footprint_gb = (peak_ram_kb - self._baseline_used_kb) / (1024 * 1024)
        total_ram_gb = self._mem_total_kb / (1024 * 1024)
        return {
            "peak_cpu_pct":     round(peak_cpu, 1),
            "mean_cpu_pct":     round(mean_cpu, 1),
            "baseline_ram_gb":  round(baseline_gb, 2),
            "peak_ram_gb":      round(peak_ram_gb, 2),
            "model_footprint_gb": round(footprint_gb, 2),
            "total_ram_gb":     round(total_ram_gb, 2),
            "samples":          len(self._cpu_samples),
        }


# ─── OUTPUT HANDLING ──────────────────────────────────────────────────────────

def setup():
    """Create output directories and initialise CSV with headers."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(RESPONSE_DIR, exist_ok=True)
    with open(RESULTS_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Run", "Model", "Report_ID", "Prompt_Type",
            "Tokens_Per_Second", "Total_Time_Seconds",
            "Tokens_Generated", "Prompt_Tokens",
            "Eval_Duration_ns", "Load_Duration_ns",
            "Peak_CPU_Pct", "Mean_CPU_Pct",
            "Baseline_RAM_GB", "Peak_RAM_GB", "Model_Footprint_GB",
            "Sample_Count", "Timestamp",
        ])
    open(LOG_FILE, "w").close()


def append_result(row):
    with open(RESULTS_CSV, "a", newline="") as f:
        csv.writer(f).writerow(row)


def save_response(run_id, model, report_id, prompt_type, response_text):
    fname = f"{run_id:02d}_{safe_filename(model)}_{report_id}_{safe_filename(prompt_type)}.txt"
    path = os.path.join(RESPONSE_DIR, fname)
    with open(path, "w") as f:
        f.write(f"Run: {run_id}\n")
        f.write(f"Model: {model}\n")
        f.write(f"Report: {report_id}\n")
        f.write(f"Prompt type: {prompt_type}\n")
        f.write("=" * 70 + "\n\n")
        f.write(response_text)


# ─── MAIN EXPERIMENT LOOP ─────────────────────────────────────────────────────

def main():
    reports      = load_reports(REPORTS_DIR)
    prompt_types = load_prompts(PROMPTS_FILE)

    setup()
    log("=" * 70)
    log("AUTOMATED LLM INFERENCE EXPERIMENT")
    log(f"Models:        {MODELS}")
    log(f"Reports:       {len(reports)} loaded from {REPORTS_DIR}")
    log(f"Prompt types:  {len(prompt_types)} loaded from {PROMPTS_FILE}")
    log(f"Total runs:    {len(MODELS) * len(reports) * len(prompt_types)}")
    log(f"Output:        {RESULTS_DIR}")
    log("=" * 70)

    run_id     = 0
    total_runs = len(MODELS) * len(reports) * len(prompt_types)

    for model in MODELS:
        log(f"\n>>> Starting model: {model}")

        for report_id, report_text in reports.items():
            for prompt_type, prompt_instruction in prompt_types.items():
                run_id += 1
                full_prompt = f"{prompt_instruction}\n\nReport: {report_text}"

                log(f"  Run {run_id}/{total_runs}: {model} | {report_id} | {prompt_type}")

                # Start system monitoring BEFORE the inference call so the
                # baseline RAM reading reflects pre-load state and the first
                # CPU sample captures the loading spike.
                monitor = SystemMonitor()
                monitor.start()

                t0 = time.time()
                try:
                    result = call_ollama(model, full_prompt, keep_alive=0)
                except urllib.error.URLError as e:
                    log(f"    ERROR: {e}. Retrying in 30s...")
                    monitor.stop()
                    time.sleep(30)
                    monitor = SystemMonitor()
                    monitor.start()
                    try:
                        result = call_ollama(model, full_prompt, keep_alive=0)
                    except Exception as e2:
                        monitor.stop()
                        log(f"    FAILED on retry: {e2}. Skipping run.")
                        append_result([
                            run_id, model, report_id, prompt_type,
                            "ERROR", "ERROR", "ERROR", "ERROR",
                            "ERROR", "ERROR",
                            "ERROR", "ERROR", "ERROR", "ERROR", "ERROR",
                            0, datetime.now().isoformat(),
                        ])
                        continue

                wall = time.time() - t0
                monitor.stop()
                sys_metrics = monitor.summary()

                eval_count    = result.get("eval_count", 0)
                eval_duration = result.get("eval_duration", 1)
                prompt_count  = result.get("prompt_eval_count", 0)
                total_dur     = result.get("total_duration", 0)
                load_dur      = result.get("load_duration", 0)
                response      = result.get("response", "")

                tps     = round(eval_count / (eval_duration / 1e9), 2) if eval_duration > 0 else 0
                total_s = round(total_dur / 1e9, 2)

                log(f"    -> TPS={tps} Time={total_s}s Tokens={eval_count} "
                    f"(wall={wall:.1f}s) CPU_peak={sys_metrics['peak_cpu_pct']}% "
                    f"RAM_peak={sys_metrics['peak_ram_gb']}GB "
                    f"Footprint={sys_metrics['model_footprint_gb']}GB")

                append_result([
                    run_id, model, report_id, prompt_type,
                    tps, total_s, eval_count, prompt_count,
                    eval_duration, load_dur,
                    sys_metrics["peak_cpu_pct"], sys_metrics["mean_cpu_pct"],
                    sys_metrics["baseline_ram_gb"], sys_metrics["peak_ram_gb"],
                    sys_metrics["model_footprint_gb"],
                    sys_metrics["samples"], datetime.now().isoformat(),
                ])
                save_response(run_id, model, report_id, prompt_type, response)

                # Small pause between runs lets the OS release any pending I/O
                # and gives a clean separation between runs in the log.
                # keep_alive=0 already unloaded the model, so RAM settles
                # before the next baseline is taken.
                time.sleep(2)

        log(f">>> Completed model: {model}")

    log("\n" + "=" * 70)
    log(f"EXPERIMENT COMPLETE — {run_id} runs")
    log(f"Results CSV:  {RESULTS_CSV}")
    log(f"Responses:    {RESPONSE_DIR}/")
    log(f"Log:          {LOG_FILE}")
    log("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n!! INTERRUPTED BY USER")
        sys.exit(1)
    except Exception as e:
        log(f"\n!! FATAL ERROR: {e}")
        raise
