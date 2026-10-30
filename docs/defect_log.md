# Defect Log (Task 12)

Real problems found while building and testing ImageShelf. Add a row each time you find and fix a problem, and commit each fix separately with a message such as `fix: …` so the Git history shows the correction.

| ID | Problem (symptom) | Probable cause | Correction | Retest | Outcome |
|---|---|---|---|---|---|
| D1 | The Shelf view showed thumbnails as thin cropped strips, with no file names under them. | `setUniformItemSizes(True)` made the view calculate every item's size once, from the first item, before its thumbnail and text were available. | Removed `setUniformItemSizes(True)`, so each item is measured properly. | Rescanned `sample_images` and checked the shelf screenshot. | Fixed: full thumbnails with names. |
| D2 | The automated test suite froze about 1 run in 4 (always in a controller test). | PyQt's `QSignalSpy.wait()` keeps Python's GIL while it blocks. The worker thread needed the GIL to finish emitting its `finished` signal, so the two threads waited on each other (deadlock). | Wrote `SignalCatcher` in `tests/conftest.py`, which waits by calling `processEvents()` from Python and so releases the GIL. | Ran the full suite 10 times in a row. | Fixed: 10/10 runs pass (109 tests). |
| D3 | The benchmark froze at the first multi-process run on Linux. | On Linux, Python starts worker processes with `fork()`, which copies Qt's internal locks in a locked state into the child. | Created the process pool with the `spawn` start method (the default on Windows and macOS). | Re-ran `benchmark.py`. | Fixed: completes on all platforms. |
| D4 | The "pure-Python" benchmark workload ran 1.9× faster with 2 threads, which should not happen for GIL-bound code. | About half of that workload's time was JPEG decoding inside Qt (C++), which releases the GIL, so it was not really pure-Python work. | Made the workload mostly Python (brightness, contrast and histogram loop over a 1000×750 copy). | Re-ran the benchmark. | Fixed: threads ≈1.05× vs processes ≈1.5×, as GIL theory predicts. |
| D5 | The app crashed at start-up in a Linux environment with no sound server. | Qt's PipeWire audio backend crashes when no audio service is running. | Documented the `QT_AUDIO_BACKEND=pulseaudio` workaround in the README; the tests set it automatically on Linux. | Ran the app and the tests on the same machine. | Workaround works. |
| D6 | | | | | |
