# ImageShelf – Software Test Plan (Tasks 9, 10, 11)

**Test data:** `python tools/make_sample_images.py sample_images` creates a known set:
- 17 readable images (9 landscape, 5 portrait, 3 square, including a 1×1 pixel image)
- 2 duplicate groups (landscape_01 ×3, portrait_02 ×2)
- 2 bad files (`empty.png`, `broken.jpg`)
- 1 non-image (`notes.txt`)
- slideshow music

`--big 60` adds 60 large photos for the background-processing tests.

## Part A – Automated tests (run: `python -m pytest -v`)

| Test file | What it verifies | Why it is automated |
|---|---|---|
| `tests/test_image_service.py` | Format detection, orientation, folder validation, scanning (recursive / non-recursive / size limit / empty), SHA-256 including chunk boundaries and cancel, analysing real, empty, damaged, missing and unsupported files, duplicates, summary totals, filter rules, size formatting, settings and music validation, CSV export | Pure logic with exact expected results; quick to re-run after every change |
| `tests/test_thumbnailer.py` | Thumbnail sizing (landscape, portrait, square, never enlarged, 1×1, extremely thin, invalid input), reading real image sizes, loading full images | Boundary arithmetic is easy to get wrong |
| `tests/test_results_store.py` | Counts, snapshot copies, reset, and **8 threads × 2,000 simultaneous writes lose no updates** | Proves the lock works; a person cannot reliably test a race condition by hand |
| `tests/test_table_model.py` | Rows and columns, display text, thumbnail decoration, duplicate highlight, invalid indexes, search, orientation and duplicate filters, numeric sorting | Model behaviour that both views depend on |
| `tests/test_controller.py` | Real background scans: results, errors, progress reaches 100%, non-recursive setting, invalid folder and settings, second scan rejected while busy, cancel, export | Checks the threads and signals end to end without a person watching |

**Result (development machine): 109 passed in about 0.5 s, 10 runs in a row.** Re-run on your own machine and screenshot the output for your evidence.

**What stays manual, and why:** how the GUI looks and feels, dialogs, mouse and keyboard navigation, whether the window *feels* responsive during a scan, and whether sound is heard. These need human judgement, real hardware (speakers) and a real screen.

## Part B – Requirements-driven tests (from FR1–FR11)

Fill in **Actual** and **Pass/Fail** when you run each test, and take a screenshot for each.

| ID | Req | Purpose | Input / conditions | Expected result | Actual | Pass/Fail |
|---|---|---|---|---|---|---|
| R01 | FR1 | Catalogue a folder with sub-folders | Open Folder → `sample_images` (default settings) | 17 images listed; `notes.txt` not listed; status says scan complete | | |
| R02 | FR1, FR9 | Sub-folders can be excluded | Settings → untick "Include sub-folders" → Rescan | Only images directly in `sample_images` are listed (0, because all images are in sub-folders) | | |
| R03 | FR2 | Both views show the same data | Ctrl+1 then Ctrl+2; select an image in one view | Shelf shows thumbnails and names; Details shows all 7 columns; the selection is kept when switching | | |
| R04 | FR2 | Sorting is numeric | Details view → click the Size, then Dimensions headers | Ordered by real bytes and pixels (e.g. 1.0 KB before 81 KB) | | |
| R05 | FR3 | Search | Type `land` in the search box | Only names containing "land" are shown; counter shows "x of 17 images" | | |
| R06 | FR3 | Shape filter | Choose Portrait, then Square | Only portrait / only square images shown (Square includes `tiny.png`) | | |
| R07 | FR4 | Progress and responsiveness | Scan `big_images` (60 large photos); while it runs, drag the window, type in search, switch views | Progress bar advances; the window keeps reacting the whole time | | |
| R08 | FR4 | Cancel | Start a scan of `big_images`, press Esc / Cancel after about 2 s | Scan stops quickly; summary says "Cancelled"; buttons are enabled again | | |
| R09 | FR4 | Restart after cancel | After R08 press F5 (Rescan) | A full scan runs to completion | | |
| R10 | FR5 | Duplicate detection | Scan `sample_images`, tick "Show duplicates only" | 5 images in 2 groups highlighted; Summary shows wasted space greater than 0 | | |
| R11 | FR6 | Preview | Click several images | The large preview and details (dimensions, format, size, shape, path) update | | |
| R12 | FR7 | Slideshow | Start slideshow, 2 s interval | The next image is selected every 2 s and wraps to the first at the end | | |
| R13 | FR7 | Slideshow music | Choose music… → `music/slideshow_music.wav` → Start, then Stop, then Start | Music plays, pauses with Stop and resumes with Start; Volume slider changes loudness | | |
| R14 | FR8 | Completion notification | Finish any scan | "Scan finished" message, and a chime is heard | | |
| R15 | FR10 | Damaged files | Scan `sample_images` → Errors tab | `empty.png` (empty) and `broken.jpg` (not readable) listed; the scan still completed | | |
| R16 | FR11 | Export | File → Export CSV… → save → open in Excel or Notepad | Header and one row per image, with a duplicate yes/no column | | |

## Part C – Criteria-driven tests (normal / boundary / invalid / exceptional)

| ID | Category | Purpose | Input / conditions | Expected result | Actual | Pass/Fail |
|---|---|---|---|---|---|---|
| C01 | Normal | Valid settings | Workers 8, max size 50 → OK | Dialog closes; "Settings saved" in status bar | | |
| C02 | Boundary | Smallest and largest workers | Workers spin box: try 0 and 33 | Spin box stops at 1 and 32 | | |
| C03 | Boundary | Max size limits | Max size `1` (valid), `100000` (valid), `100001` | First two accepted; third rejected with a message | | |
| C04 | Invalid | Non-numeric max size | Max size `abc`, then `1.5`, then `-5` | Warning message; dialog stays open with the field selected | | |
| C05 | Boundary | Empty folder | Scan an empty folder | "No supported images were found" message; no crash | | |
| C06 | Boundary | 1×1 pixel image | Find `tiny.png` | Shown as 1 × 1, Square, with a thumbnail | | |
| C07 | Invalid | Wrong music file | Choose music… → pick a `.jpg` | Warning "not a supported audio file"; slideshow unaffected | | |
| C08 | Invalid | Slideshow with no images | Before any scan (or with search `zzz`) press Start slideshow | Message "There are no images to show"; button returns to Start | | |
| C09 | Invalid | Export with nothing loaded | Export CSV before scanning | "Scan a folder first" message | | |
| C10 | Exceptional | Folder deleted before scan | Rename a folder after choosing it, then press F5 | "The folder does not exist" warning; app keeps working | | |
| C11 | Exceptional | Export to a read-only or locked file | Export over a CSV that is open in Excel | "Export failed" message with the reason; no crash | | |
| C12 | Exceptional | Quit during a scan | Close the window while `big_images` is scanning | Asks "Cancel it and quit?"; No keeps running; Yes closes cleanly | | |
| C13 | Exceptional | Music file is damaged | Rename a `.jpg` to `.mp3`, choose it as music, start the slideshow | "Music cannot be played" text; slideshow continues silently | | |

## Part D – Packaged application tests (Task 14)

| ID | Purpose | Conditions | Expected result | Actual | Pass/Fail |
|---|---|---|---|---|---|
| P01 | Build | `pyinstaller imageshelf.spec` | `dist/ImageShelf/` created without errors | | |
| P02 | Runs without Python | Run `dist/ImageShelf/ImageShelf.exe` (ideally on another PC) | Window opens; repeat R01, R13, R14 | | |
