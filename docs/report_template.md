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
- *What goes wrong without a lock:* `processed += 1` is a read, an add and a write. Two threads can read the same value, so one update is lost; the progress bar would never reach 100% and the totals would be wrong. A reader could also see the counter and the list out of step. `benchmarks/race_condition_demo.py` shows this: **TODO** paste your result, e.g. "expected 16000, got 2000 without the lock, 16000 with it".
- *Mechanism:* every access happens inside `with self._lock:` (a `threading.Lock`). This makes "append + increment" one indivisible step, and `snapshot()` returns consistent copies. The automated test `test_concurrent_writers_lose_no_updates` (8 threads × 2,000 writes) confirms no update is lost.
- The other shared state is protected in other ways:
  - the cancel flag is a `threading.Event`, which is thread-safe
  - the model and widgets are owned by the GUI thread
  - the GUI is reached only through queued signals

**Performance implications.** More workers help until the disk or CPU is saturated (section 8). Emitting one signal per image is simple, but for tens of thousands of images, batching results would reduce GUI updates (see 15.7).

## 8. Performance and parallelism investigation (Task 8)
Run `python benchmarks/benchmark.py` and paste `benchmarks/results.md` here. **TODO** paste your table.

Example from the development machine (2 CPUs, 12 photos, 2 workers):

| Workload | Sequential | Threads ×2 | Processes ×2 |
|---|---:|---:|---:|
| A. analyse (hash + thumbnail) | 0.289 s | 0.145 s (1.99×) | 0.267 s (1.08×) |
| B. py-stats (pure-Python loop) | 1.286 s | 1.221 s (1.05×) | 0.854 s (1.51×) |

**Why the results differ.**
- **Workload A:** most of its time is in C code that releases the GIL, so threads run truly in parallel and nearly double the speed. Processes are slower here because each process must start a new Python and import PyQt (spawn start-up), and the results must be pickled back. That overhead outweighs the gain on a small job.
- **Workload B:** pure-Python bytecode holds the GIL, so two threads take turns and gain almost nothing. Only separate processes, each with its own interpreter and GIL, run it in parallel.
- **Rule of thumb:**
  - I/O-bound work, or work done in C libraries: use threads.
  - CPU-bound pure-Python work: use processes.
  - In both cases, overhead (start-up, data transfer, waiting on the slowest task) eats into the gain.

**Amdahl's Law.** S(N) = 1 / ((1 − P) + P/N).
- Example: if 90% of a scan can run in parallel (P = 0.9) and 10% cannot (listing the folder, building the summary, updating the GUI), then 4 workers give 1 / (0.1 + 0.225) = **3.08×**.
- Infinitely many workers give at most 1 / 0.1 = **10×**.
- The sequential 10% sets the ceiling.
- From your measured speed-up, the script estimates P and predicts 16 workers. **TODO** comment on your numbers.

**Scalability.** Speed-up flattens once workers exceed CPU cores (CPU-bound work) or once the disk is saturated (I/O-bound work), and very small jobs can get slower because of overhead.

**Parallel query (PLINQ concept).** PLINQ's `source.AsParallel().Select(f).Where(p).OrderBy(k)` splits a query over the cores automatically. The Python equivalent used here (`parallel_query` in the benchmark) is `ProcessPoolExecutor.map(f, source)`, which acts as the parallel `Select`, followed by an ordinary filter and sort on the results. Like PLINQ, it is declarative over a collection, splits the data into chunks across workers, and returns results in the original order.

## 15.5 Testing
- **Test plan:** `docs/test_plan.md`, covering requirement-driven tests R01–R16, criteria-driven tests C01–C13 (normal, boundary, invalid and exceptional) and packaging tests P01–P02.
- **Automated:** 109 pytest tests in 5 files. **TODO** screenshot of `python -m pytest -v` on your machine.
- **Manual:** **TODO** fill in the Actual and Pass/Fail columns and add screenshots (R07 responsiveness, R08 cancel, R13 music, R15 errors at minimum).
- **Defects and corrections:** `docs/defect_log.md` (D1–D5, plus any you find).

## 15.6 Source-control workflow
**TODO**:
- branches you created (`feature/...`), with a screenshot of `git log --oneline --graph --all`
- the merges
- the controlled conflict: which file and line, the conflict markers, how you resolved it
- remote activity: push, pull request, merge and pull on GitHub (screenshots)

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
- Only 2 CPUs were available on the development machine.

**Alternative approaches:**
- `QThread` with a moved worker object instead of `QRunnable`
- `QtConcurrent`-style mapping
- `asyncio` (a poor fit, since the work is CPU and disk, not network)
- multiprocessing for thumbnails (better for pure-Python work, but `QImage` cannot be pickled and has start-up costs)

**TODO:** technical problems you faced, and what you learned.

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
