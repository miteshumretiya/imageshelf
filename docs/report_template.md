# ImageShelf – Technical Report (Task 15)

> Lines marked **TODO** need your own results or words. Sections 15.2–15.4 describe the code as it is; check that they match what you submit. Declare any AI assistance as your module's policy requires.

## 15.1 System overview
ImageShelf is a PyQt6 desktop catalogue for a local folder of photos. It builds a thumbnail "shelf" and a sortable details table, and finds duplicate photos by SHA-256 content hash, reporting the space they waste. It also previews images and plays slideshows with user-chosen background music. Slow work (hashing every byte and decoding images for thumbnails) runs in the background, with progress, cancellation and a completion notification. See `docs/design_spec.md` for the purpose, the requirements FR1–FR11 and the wireframe.

## 15.2 Architecture (MVC / separation of concerns)

| Layer | Module(s) | Responsibility |
|---|---|---|
| Model | `models/image_item.py`, `models/image_table_model.py` | Data classes (`ImageItem`, `ScanSummary`, `AppSettings`). `ImageTableModel` (a `QAbstractTableModel`) and `ImageFilterProxyModel` feed both views. |
| Services | `services/image_service.py`, `thumbnailer.py`, `results_store.py` | All processing logic: validation, scanning, hashing, thumbnails, duplicates, summary, export. No widgets. |
| View | `views/main_window.py`, `preview_panel.py`, `settings_dialog.py` | Widgets, layout and display. Slots only read input, call the controller and update the display. |
| Controller | `controllers/main_controller.py` | Validates requests, starts and cancels the worker, turns worker results into model updates, and exposes custom signals (`scan_started`, `progress_changed`, `scan_finished`, `scan_failed`, …). |
| Workers | `workers/scan_worker.py` | `ScanJob` (`QRunnable`) plus a `ThreadPoolExecutor` doing the slow work. |

Main decisions:
1. I used Qt's model/view framework rather than a textbook MVC, because one `QAbstractTableModel` behind one proxy can drive *two* views (`QListView` in icon mode and `QTableView`). Search, filters, sorting and even the selection model are shared, so the views can never disagree.
2. The filter rule (`matches_filter`) lives in the services layer and the proxy simply calls it. This keeps the rule testable without Qt.
3. Validation is done twice: in the dialog (for an immediate message) and in the controller (so bad settings can never start a scan).

## 15.3 GUI design decisions
- **Shelf plus Details** instead of one view. Thumbnails suit browsing photos, while a table suits sorting by size or dimensions. Both views are toggled with Ctrl+1/2, the toolbar or the View menu.
- **Splitter with tabs on the right** (Preview, Summary, Errors). Information stays one click away without extra windows. The splitter lets users give more room to the grid or to the preview.
- **Feedback:**
  - The progress bar starts in "busy" mode while files are listed, then shows exact progress.
  - The status bar explains what is happening.
  - Actions that make no sense during a scan are disabled; only Cancel is enabled.
- **Non-blocking "Scan finished" message box** (`open()` rather than `exec()`) plus a sound, so a user working elsewhere notices that the scan is done.
- **Duplicates highlighted in orange** in both views, with tooltips explaining why.
- **Standard shortcuts** (Ctrl+O, F5, Esc, Ctrl+E) and standard icons, for familiarity.
- **Settings dialog stays open on invalid input**, with the bad field selected.
- TODO: add a screenshot of the Shelf view and the Details view.

## 15.4 Concurrency design

**Problem.** Scanning 300 photos means reading every byte for SHA-256 and decoding each image for a thumbnail. Done in the GUI thread, this freezes the window for seconds: no repaint, no Cancel, and the operating system reports "Not responding".

**Technique.**
1. The controller starts one `ScanJob` (`QRunnable`) on a `QThreadPool`.
2. The job lists the folder, then processes the images in parallel with a `ThreadPoolExecutor` (*N* worker threads, set in Settings).
3. Threads are effective here because `hashlib` and Qt's JPEG decoder are C/C++ code that **release the GIL**, so several images really are processed at the same time (see section 8).
4. Thumbnails are made as `QImage` with `QImageReader.setScaledSize`. `QImage` is safe in worker threads; `QPixmap` is not, so pixmaps and icons are created only in the GUI thread, inside `data()`.

**Transferring results safely.** Workers emit signals from a `ScanSignals` object that lives in the GUI thread. Qt therefore delivers them as *queued* events, and the slots (`_on_item_ready`, `_on_finished`) run in the GUI thread. As a result, only the GUI thread ever touches the table model or widgets (controlled ownership). Errors in a single file are caught per file and reported with `file_failed`. An unexpected failure of the whole job is caught and reported with `failed`, so the GUI never stays stuck in "busy".

**Cancellation.** A `threading.Event` is checked before each file and between every 1 MB chunk while hashing, so even a huge file stops quickly.

**Synchronisation (Task 7).**
- *Shared resource:* `ResultsStore`, which holds the item list, the error list and the processed counter. All N worker threads write to it.
- *What goes wrong without a lock:* `processed += 1` is a read, an add and a write. Two threads can read the same value, so one update is lost; the progress bar would never reach 100% and the totals would be wrong. A reader could also see the counter and the list out of step. `benchmarks/race_condition_demo.py` shows this. On my PC (8 threads × 2,000 increments): **without the lock, expected 16000, got 2029, so 13,971 updates were lost (0.04 s); with the lock, expected 16000, got 16000, so none were lost (0.05 s).** The lock costs almost no time but makes the result correct. The exact number lost changes from run to run, which is typical of a race condition.
- *Mechanism:* every access happens inside `with self._lock:` (a `threading.Lock`). This makes "append + increment" one indivisible step, and `snapshot()` returns consistent copies. The automated test `test_concurrent_writers_lose_no_updates` (8 threads × 2,000 writes) confirms no update is lost.
- The other shared state is protected in other ways:
  - the cancel flag is a `threading.Event`, which is thread-safe
  - the model and widgets are owned by the GUI thread
  - the GUI is reached only through queued signals

**Performance implications.** More workers help until the disk or CPU is saturated (section 8). Emitting one signal per image is simple, but for tens of thousands of images, batching results would reduce GUI updates (see 15.7).

## 8. Performance and parallelism investigation (Task 8)
Measured with `python benchmarks/benchmark.py` on `big_images` (created with `python tools/make_sample_images.py big_images --big 60`); the two deliberately damaged sample files are skipped (defect D7). Results from `benchmarks/results.md` on my PC:

- Machine: Intel64 Family 6 Model 158 Stepping 13, GenuineIntel, 8 logical CPUs, Windows 11
- Python 3.12.10
- Data: 77 images, 39 MB in total
- Each time is the mean of 3 runs (after a warm-up run), measured with `time.perf_counter()`. Each timed run includes starting and stopping its pool.

**Workload A: analyse (hash + thumbnail)**

| Approach | Workers | Mean time (s) | Speed-up | Efficiency |
|---|---:|---:|---:|---:|
| sequential | 1 | 0.992 | 1.00x | 100% |
| threads | 2 | 0.525 | 1.89x | 94% |
| threads | 4 | 0.296 | 3.35x | 84% |
| threads | 8 | 0.185 | 5.35x | 67% |
| processes | 2 | 0.734 | 1.35x | 68% |
| processes | 4 | 0.530 | 1.87x | 47% |
| processes | 8 | 0.529 | 1.88x | 23% |

**Workload B: py-stats (pure-Python loop)**

| Approach | Workers | Mean time (s) | Speed-up | Efficiency |
|---|---:|---:|---:|---:|
| sequential | 1 | 8.854 | 1.00x | 100% |
| threads | 2 | 7.340 | 1.21x | 60% |
| threads | 4 | 7.437 | 1.19x | 30% |
| threads | 8 | 7.429 | 1.19x | 15% |
| processes | 2 | 4.964 | 1.78x | 89% |
| processes | 4 | 2.824 | 3.14x | 78% |
| processes | 8 | 1.887 | 4.69x | 59% |

**Amdahl's Law estimate (calculated by the script)**

| Workload | Best approach | Measured speed-up | Estimated P | Predicted S with 16 workers | Maximum possible S (N → ∞) |
|---|---|---:|---:|---:|---:|
| analyse (hash + thumbnail) | threads x8 | 5.35x | 0.93 | 7.76x | 14.1x |
| py-stats (pure-Python loop) | processes x8 | 4.69x | 0.90 | 6.37x | 9.9x |

**Why the results differ (my numbers).**
- **Workload A, threads scale well:** 1.89× with 2 threads (94% efficiency), 3.35× with 4 and 5.35× with 8. Most of the time is spent in `hashlib` and Qt's JPEG decoder, which are C/C++ code that release the GIL, so the threads really work at the same time. Efficiency falls to 67% at 8 threads because each file still runs some Python code that holds the GIL, the disk is shared, and 8 threads already use all 8 logical CPUs.
- **Workload A, processes do not:** only 1.35× (2), 1.87× (4) and 1.88× (8), so 4 → 8 processes gained nothing. With `spawn`, every worker starts a new Python interpreter and imports PyQt6, and each result is pickled back to the main process. The whole job takes only about 1 s, so this fixed overhead is a large share of it.
- **Workload B, threads barely help:** about 1.2× with 2, 4 or 8 threads. The pixel loop is Python bytecode, which holds the GIL, so the threads take turns. The small gain comes from decoding the image before the loop, which is C++ code that releases the GIL.
- **Workload B, processes scale:** 1.78× (2), 3.14× (4) and 4.69× (8). Each process has its own interpreter and its own GIL, so the loop really runs in parallel, and the job (about 8.9 s) is long enough to hide most of the start-up cost. Efficiency still falls from 89% to 59% at 8 processes because of start-up, pickling and the main process sharing the same 8 CPUs.
- **Rule of thumb:**
  - I/O-bound work, or work done in C libraries: use threads.
  - CPU-bound pure-Python work: use processes.
  - In both cases, overhead (start-up, data transfer, waiting on the slowest task) eats into the gain.

**Amdahl's Law.** S(N) = 1 / ((1 − P) + P/N).
- Example: if 90% of a scan can run in parallel (P = 0.9) and 10% cannot (listing the folder, building the summary, updating the GUI), then 4 workers give 1 / (0.1 + 0.225) = **3.08×**.
- Infinitely many workers give at most 1 / 0.1 = **10×**.
- The sequential 10% sets the ceiling.
- **My numbers:** for workload A the best result, 5.35× with 8 threads, gives P ≈ 0.93, so about 7% of the time behaves as serial work. Amdahl's Law then predicts 7.76× with 16 workers and at most about 14× however many workers are added. For workload B, 4.69× with 8 processes gives P ≈ 0.90, a prediction of 6.37× with 16 workers and a ceiling of about 10×.
- These predictions are optimistic. The estimate treats all overhead (process start-up, pickling, disk reads and the Python part of each task) as a fixed serial share, but with processes the start-up cost grows with every worker added. This PC also has only 8 logical CPUs, so 16 CPU-bound workers would share 8 cores and could not reach 7.76× or 6.37×. Workload A's processes already show this limit: going from 4 to 8 processes gave no gain.

**Scalability.** Speed-up flattens once workers exceed CPU cores (CPU-bound work) or once the disk is saturated (I/O-bound work), and very small jobs can get slower because of overhead.

**Parallel query (PLINQ concept).** PLINQ's `source.AsParallel().Select(f).Where(p).OrderBy(k)` splits a query over the cores automatically. The Python equivalent used here (`parallel_query` in the benchmark) is `ProcessPoolExecutor.map(f, source)`, which acts as the parallel `Select`, followed by an ordinary filter and sort on the results. Like PLINQ, it is declarative over a collection, splits the data into chunks across workers, and returns results in the original order. On my PC the query (8 processes) took 1.972 s. The five brightest images were tiny.png (159.0), IMG_0054.jpg (151.7), IMG_0013.jpg (150.9), IMG_0010.jpg (150.1) and IMG_0016.jpg (148.2).

## 15.5 Testing
- **Test plan:** `docs/test_plan.md`, covering requirement-driven tests R01–R16, criteria-driven tests C01–C13 (normal, boundary, invalid and exceptional) and packaging tests P01–P02.
- **Automated:** 109 pytest tests in 5 files. On my PC (Windows 11, Python 3.12.10, PyQt6 6.12.0, pytest 9.2.0), `python -m pytest -v` reports **109 passed** in under 1 second. **TODO** screenshot of `python -m pytest -v` on your machine.
- **Manual:** **TODO** fill in the Actual and Pass/Fail columns and add screenshots (R07 responsiveness, R08 cancel, R13 music, R15 errors at minimum).
- **Defects and corrections:** full details (cause, retest, outcome) are in `docs/defect_log.md`. Summary:

| ID | Problem | Correction |
|---|---|---|
| D1 | Shelf thumbnails appeared as thin cropped strips without names. | Removed `setUniformItemSizes(True)`, so each item is measured properly. |
| D2 | The test suite froze about 1 run in 4 (a GIL deadlock inside `QSignalSpy.wait()`). | Wrote `SignalCatcher`, which waits by pumping events from Python; 10/10 runs pass. |
| D3 | The benchmark froze at the first multi-process run on Linux (`fork` copied Qt's locked locks). | The process pool uses the `spawn` start method. |
| D4 | The "pure-Python" workload ran 1.9× faster with threads, so it was not really GIL-bound. | Rewrote the workload so most of its time is Python bytecode. |
| D5 | Start-up crash on Linux with no sound server (PipeWire backend). | Documented the `QT_AUDIO_BACKEND=pulseaudio` workaround; the tests set it on Linux. |
| D6 | On Windows `python main.py sample_images` opened no window, although pytest passed. | The commands had been run from the parent folder; ran them from the project folder and made the README say so. |
| D7 | `benchmark.py` crashed on the sample set's deliberately damaged files. | The benchmark skips files the app itself reports as unreadable. |
| D8 | With no Qt multimedia backend, slideshow music failed silently. | The music controls are disabled with a clear message; the slideshow and chime still work. |

## 15.6 Source-control workflow
The repository is in the project folder (the one with `main.py`); the author name and e-mail are set for this repository with `git config`.

**Branches and merges.** Each part of the system was committed on its own branch and merged into `main` with `git merge --no-ff`. Every merge therefore appears as a merge commit, and the graph shows where each part came from.

| Branch | Commits on the branch | Merged into `main` as |
|---|---|---|
| `feature/threaded-processing` | `5d25b57` feat: add thread-safe results store and background scan worker | `662ab58` |
| `feature/gui` | `dd3f903` feat: add main window with shelf/details views, slideshow music and controller | `011a8d1` |
| `feature/performance` | `f161590` feat: add sequential vs threads vs processes benchmark and parallel query | `43f2631` |
| `fix/windows-issues` | `a95b069` fix: skip deliberately damaged sample files in the benchmark (D7); `846f0d6` fix: disable slideshow music with a clear message when Qt has no multimedia backend (D8); `18303d4` fix: tell users to run commands from the project folder (D6) | `fc7fb71` |
| `feature/version-beta` | `4a79d97` chore: mark version as 1.1.0 beta | `1638fd8` (with a conflict, see below) |

Commits made directly on `main`:
- `88ee726` docs: add design specification and project setup
- `f78eb2d` feat: add image model and processing services with unit tests
- `e186348` build: add PyInstaller spec, test plan and defect log
- `0dd76d0` chore: bump patch version to 1.0.1
- this report's "docs: complete report sections" commit

Each `fix:` commit corrects exactly one defect from the defect log, so the history shows each problem and its correction separately.

**TODO** screenshot of `git log --oneline --graph --all`.

**Controlled conflict.**
- On `feature/version-beta`, line 3 of `app/__init__.py` was changed from `__version__ = "1.0.0"` to `__version__ = "1.1.0-beta"` (`4a79d97`). On `main`, the same line was changed to `__version__ = "1.0.1"` (`0dd76d0`).
- `git merge feature/version-beta` stopped with `CONFLICT (content): Merge conflict in app/__init__.py`, and `git status` listed the file as "both modified". Git wrote both versions into the file:

```
<<<<<<< HEAD
__version__ = "1.0.1"
=======
__version__ = "1.1.0-beta"
>>>>>>> feature/version-beta
```

- The lines between `<<<<<<< HEAD` and `=======` are `main`'s version; the lines between `=======` and `>>>>>>> feature/version-beta` are the branch's version.
- I resolved it by keeping one line, `__version__ = "1.1.0"` (the minor-version step from the beta branch, without the beta label), and deleting the markers. Then I ran `git add app/__init__.py` and `git commit -m "Merge feature/version-beta: resolve version conflict"` (`1638fd8`). Help → About now shows version 1.1.0.

**TODO** remote activity: push, pull request, merge and pull on GitHub (screenshots).

## 15.7 Evaluation
**Strengths:**
- Responsive UI with real parallelism.
- Clear separation of concerns, with 109 automated tests.
- Two synchronised views from one model.
- Multimedia with a genuine purpose (slideshow music).
- Damaged files are handled without stopping the scan.

**Limitations and possible improvements:**
- Results are not saved between sessions: a cache, for example SQLite, would avoid re-scanning.
- Duplicates must be byte-identical; resized or re-saved copies are missed. A perceptual hash would catch them.
- One signal per image: batching would help with very large folders.
- There is no "delete duplicate" action, to avoid accidental data loss; it could be added with the Recycle Bin and a confirmation.
- The benchmark was run on one PC only (8 logical CPUs); hardware with more cores or a slower disk would give different speed-ups.

**Alternative approaches:**
- `QThread` with a moved worker object instead of `QRunnable`
- `QtConcurrent`-style mapping
- `asyncio` (a poor fit, since the work is CPU and disk, not network)
- multiprocessing for thumbnails (better for pure-Python work, but `QImage` cannot be pickled and has start-up costs)

**Technical problems and what I learned** *(draft – edit in your own words)*
- **Passing tests did not prove the app worked.** All 109 tests passed, yet `python main.py sample_images` opened no window on Windows. I had run the commands from the parent folder, so Python could not find `main.py`, while pytest still found the tests in sub-folders (D6). I learned that relative paths depend on the current folder, and that my tests never build the main window, so a quick start-up check of the real app is still needed.
- **Test data broke a tool that was not written for it.** The benchmark crashed on the deliberately damaged sample files (D7). The app already handled them, but the benchmark did not, so I made it skip unreadable files in the same way the app does.
- **Optional features should fail visibly.** Without a Qt multimedia backend, `QMediaPlayer` failed without emitting any error signal, so the user never saw a message (D8). Checking `isAvailable()` at start-up turned a silent failure into a clear one.
- **Measuring confirmed the theory.** Threads gave 5.35× for the hash and thumbnail work but only about 1.2× for the pure-Python loop, while processes gave 4.69× there. Seeing the GIL and the process start-up cost in my own numbers made the choice between threads and processes concrete.
- **Debugging method.** Before changing any code, I reproduced each problem and found where it stopped (`python -X faulthandler`, step-by-step logging). Then I made the smallest fix and retested it.

## 15.8 Presentation – suggested slides (8–10)
1. Title and problem: messy photo folders.
2. Demo plan, then the app's main features (screenshot).
3. Architecture diagram (from the design spec).
4. Concurrency: threads, queued signals and cancel (diagram).
5. Synchronisation: the race demo numbers, before and after the lock.
6. Performance table and Amdahl calculation.
7. Testing: pytest screenshot, test plan extract, one defect story (D2 is a good one).
8. Git graph: branches, merges, the conflict.
9. Packaging: the dist folder and the app running.
10. Evaluation and improvements.

**Live demo order:**
1. Open `big_images`.
2. Interact with the window during the scan.
3. Cancel, then F5.
4. Show duplicates only.
5. Run the slideshow with music.
6. Show the Errors tab.
7. Export CSV.
8. Run `pytest`.
9. Launch the `.exe`.
