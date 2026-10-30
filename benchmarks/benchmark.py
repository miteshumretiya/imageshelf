"""Task 8 - performance and parallelism investigation.

Compares sequential, threaded (ThreadPoolExecutor) and multi-process
(ProcessPoolExecutor) execution for two workloads on the same set of photos:

  A. analyse  - the app's real pipeline: SHA-256 + reading size + JPEG thumbnail.
                hashlib and Qt's image decoder are C code that release Python's GIL
                while they work, so THREADS can run them in parallel.
  B. py-stats - average brightness computed with a pure-Python loop over the pixels.
                Pure-Python code holds the GIL, so threads cannot run it in parallel;
                only separate PROCESSES can (each has its own interpreter and GIL).

It also runs a PLINQ-style "parallel query" and estimates the parallel fraction for
Amdahl's Law from the measured speed-ups.

Usage:
    python benchmarks/benchmark.py                  # creates big_images/ (40 photos) if missing
    python benchmarks/benchmark.py my_photos --repeats 5 --workers 2,4,8
Results are printed and saved to benchmarks/results.md.
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import platform
import statistics
import subprocess
import sys
import time
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QSize  # noqa: E402
from PyQt6.QtGui import QImage, QImageReader  # noqa: E402

from app.services.image_service import analyse_file, scan_folder  # noqa: E402
from app.services.thumbnailer import read_image_info  # noqa: E402


# ----------------------------------------------------------------------------- workloads
def analyse_task(path: str) -> tuple[str, int, int, str]:
    """Workload A: exactly what the app does per image (returns picklable data only)."""
    item = analyse_file(path)
    return item.name, item.width, item.height, item.sha256


def brightness_task(path: str) -> tuple[str, float, float]:
    """Workload B: decode a 1000x750 greyscale copy, then compute brightness, contrast and a
    histogram in a pure-Python loop (most of the time is spent in Python bytecode)."""
    reader = QImageReader(path)
    reader.setScaledSize(QSize(1000, 750))
    image = reader.read().convertToFormat(QImage.Format.Format_Grayscale8)
    data = image.constBits().asstring(image.sizeInBytes())
    total = squares = 0
    histogram = [0] * 256
    for value in data:          # deliberately pure Python: CPU-bound and holds the GIL
        total += value
        squares += value * value
        histogram[value] += 1
    n = max(len(data), 1)
    mean = total / n
    return Path(path).name, mean, (squares / n - mean * mean) ** 0.5


def is_readable(path: Path) -> bool:
    """Skip files the app would list in its Errors tab (e.g. the sample set's deliberate
    empty.png and broken.jpg): they raise ValueError and would stop the timing runs."""
    try:
        read_image_info(path)
    except ValueError:
        print(f"Skipping unreadable file: {path}")
        return False
    return True


WORKLOADS = {"analyse (hash + thumbnail)": analyse_task,
             "py-stats (pure-Python loop)": brightness_task}


# ----------------------------------------------------------------------------- timing
def make_pool(approach: str, workers: int) -> Executor:
    if approach == "threads":
        return ThreadPoolExecutor(max_workers=workers)
    # "spawn" starts each worker as a fresh Python process. It is the default on Windows
    # and macOS; on Linux the default "fork" can copy Qt's internal locks in a locked
    # state and freeze the child, so we always use spawn. Start-up cost = overhead.
    return ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))


def run_once(task, paths: list[str], approach: str, workers: int) -> float:
    start = time.perf_counter()
    if approach == "sequential":
        for path in paths:
            task(path)
    else:
        with make_pool(approach, workers) as pool:
            list(pool.map(task, paths, chunksize=1 if approach == "threads" else 2))
    return time.perf_counter() - start


def measure(task, paths, approach, workers, repeats) -> float:
    run_once(task, paths[:4], approach, workers)  # warm-up (disk cache, pool start-up code)
    return statistics.mean(run_once(task, paths, approach, workers) for _ in range(repeats))


def amdahl_parallel_fraction(speedup: float, n: int) -> float:
    """Solve Amdahl's Law S = 1 / ((1-P) + P/N) for P."""
    if n <= 1 or speedup <= 1:
        return 0.0
    return min(1.0, (1 - 1 / speedup) / (1 - 1 / n))


def amdahl_speedup(p: float, n: float) -> float:
    return 1 / ((1 - p) + p / n)


# ----------------------------------------------------------------------------- PLINQ-style query
def parallel_query(paths: list[str], workers: int) -> tuple[list[tuple[str, float]], float]:
    """Python equivalent of:
         paths.AsParallel().Select(Brightness).Where(b => b > 100).OrderByDescending(b).Take(5)
    pool.map is the parallel Select; the filter/sort run afterwards on the results.
    """
    start = time.perf_counter()
    with make_pool("processes", workers) as pool:
        results = pool.map(brightness_task, paths, chunksize=2)        # .AsParallel().Select()
        bright = [r for r in results if r[1] > 100]                     # .Where()
    top = [(name, mean) for name, mean, _std in sorted(bright, key=lambda r: r[1], reverse=True)[:5]]          # .OrderByDescending().Take(5)
    return top, time.perf_counter() - start


# ----------------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", default=str(ROOT / "big_images"))
    parser.add_argument("--create", type=int, default=40,
                        help="number of 12 MP photos to create if the folder is missing")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", default="2,4,8")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        print(f"Creating {args.create} large test photos in {folder} …")
        subprocess.run([sys.executable, str(ROOT / "tools" / "make_sample_images.py"),
                        str(folder), "--big", str(args.create), "--only-big"], check=True)

    paths = [str(p) for p in scan_folder(folder) if is_readable(p)]
    if not paths:
        sys.exit(f"No images found in {folder}")
    worker_counts = [int(w) for w in args.workers.split(",")]
    cpus = os.cpu_count() or 1
    size_mb = sum(Path(p).stat().st_size for p in paths) / 1024 ** 2

    lines = ["# ImageShelf performance results", "",
             f"- Machine: {platform.processor() or platform.machine()}, {cpus} logical CPUs, "
             f"{platform.system()} {platform.release()}",
             f"- Python {platform.python_version()}",
             f"- Data: {len(paths)} images, {size_mb:.0f} MB in total",
             f"- Each time is the mean of {args.repeats} runs (after a warm-up run), "
             "measured with time.perf_counter()", ""]

    best: dict[str, tuple[float, int, str]] = {}
    for name, task in WORKLOADS.items():
        print(f"\n== {name}")
        baseline = measure(task, paths, "sequential", 1, args.repeats)
        rows = [("sequential", 1, baseline)]
        print(f"   sequential           {baseline:7.3f} s")
        for approach in ("threads", "processes"):
            for n in worker_counts:
                t = measure(task, paths, approach, n, args.repeats)
                rows.append((approach, n, t))
                print(f"   {approach:<10} x{n:<2}       {t:7.3f} s   speed-up {baseline / t:4.2f}x")

        lines += [f"## Workload: {name}", "",
                  "| Approach | Workers | Mean time (s) | Speed-up | Efficiency |",
                  "|---|---:|---:|---:|---:|"]
        for approach, n, t in rows:
            s = baseline / t
            lines.append(f"| {approach} | {n} | {t:.3f} | {s:.2f}x | {s / n:.0%} |")
        lines.append("")
        approach, n, t = min(rows[1:], key=lambda r: r[2])
        best[name] = (baseline / t, n, approach)

    lines += ["## Amdahl's Law estimate", "",
              "Amdahl's Law: S(N) = 1 / ((1 − P) + P / N), where P is the parallel fraction.",
              "Solving for P from the best measured speed-up gives:", "",
              "| Workload | Best approach | Measured speed-up | Estimated P | "
              "Predicted S with 16 workers | Maximum possible S (N → ∞) |",
              "|---|---|---:|---:|---:|---:|"]
    for name, (s, n, approach) in best.items():
        p = amdahl_parallel_fraction(s, n)
        max_s = "∞" if p >= 1 else f"{1 / (1 - p):.1f}x"
        lines.append(f"| {name} | {approach} x{n} | {s:.2f}x | {p:.2f} | "
                     f"{amdahl_speedup(p, 16):.2f}x | {max_s} |")
    lines.append("")

    top, q_time = parallel_query(paths, max(worker_counts))
    lines += ["## Parallel query (PLINQ-style)", "",
              "`paths.AsParallel().Select(Brightness).Where(b > 100).OrderByDescending(b).Take(5)` "
              f"written with `ProcessPoolExecutor.map` took {q_time:.3f} s. Brightest images:", ""]
    lines += [f"- {name}: {value:.1f}" for name, value in top] or ["- (none above 100)"]
    lines.append("")

    report = "\n".join(lines)
    out = ROOT / "benchmarks" / "results.md"
    out.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Saved to {out}")


if __name__ == "__main__":  # required on Windows/macOS for ProcessPoolExecutor (spawn)
    main()
