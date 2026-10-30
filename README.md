# ImageShelf

ImageShelf is a desktop image catalogue built with Python and PyQt6. Point it at a folder of photos and it builds a "shelf" of thumbnails in the background, finds duplicate photos (identical content under different names or folders), shows each image in a preview panel, and plays a slideshow with your own background music.

## Features

- **Two views of the same data:** a Shelf (thumbnail grid) and a Details table (sortable by name, dimensions, size, date…).
- **Background scanning:** hashing, size reading and thumbnail creation run on worker threads with a progress bar and a Cancel button. The window stays responsive.
- **Duplicate finder:** identical files are highlighted, with a "duplicates only" filter and a count of wasted space.
- **Search and filters:** by name and by shape (landscape, portrait, square).
- **Slideshow with music (QtMultimedia):** `QMediaPlayer` + `QAudioOutput`, plus a sound notification (`QSoundEffect`) when a scan finishes.
- **Other features:** CSV export, a settings dialog with validation, and an Errors tab for unreadable files.

## Requirements

- Python 3.10 or newer (tested with 3.13)
- Dependencies listed in `requirements.txt`: PyQt6 (to run), pytest (to test), PyInstaller (to package)

## Setup

Windows (PowerShell):

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python tools/make_sample_images.py sample_images   # optional: creates test photos + music
python main.py                                      # then File → Open Folder… → sample_images
python main.py sample_images                        # or start scanning a folder immediately
```

To see the progress bar and Cancel working, create a slow folder:

```bash
python tools/make_sample_images.py big_images --big 60
```

Slideshow music: in the Preview tab click **Choose music…** and pick `sample_images/music/slideshow_music.wav`, then **Start slideshow**.

## Tests

```bash
python -m pytest -v
```

There are 109 automated tests: services, thumbnails, the thread-safe store, the Qt model/proxy, and the controller running real background scans. They run without opening any windows.

## Performance investigation

```bash
python benchmarks/benchmark.py              # creates big_images/ if needed, writes benchmarks/results.md
python benchmarks/race_condition_demo.py    # shows lost updates without a lock
```

## Build a standalone app (PyInstaller)

```bash
pyinstaller imageshelf.spec
```

The output is `dist/ImageShelf/`. Copy that whole folder to another computer and run `ImageShelf.exe` (Windows) or `ImageShelf` (macOS/Linux). No Python is needed on that computer.

## Project structure

```
main.py                         entry point (creates model, controller, window)
app/models/image_item.py        data classes: ImageItem, ScanSummary, AppSettings
app/models/image_table_model.py Qt model + filter/sort proxy feeding both views
app/services/image_service.py   validation, scanning, hashing, duplicates, export
app/services/thumbnailer.py     image size + thumbnails (QImageReader, thread-safe)
app/services/results_store.py   lock-protected shared results (synchronisation)
app/workers/scan_worker.py      QRunnable + ThreadPoolExecutor background scan
app/controllers/main_controller.py  connects view, model and workers (custom signals)
app/views/                      main window, preview/slideshow panel, settings dialog
tests/                          pytest suite
benchmarks/                     performance + race-condition scripts
tools/make_sample_images.py     generates test photos and music
docs/                           design spec, test plan, defect log, report template
imageshelf.spec                 PyInstaller build configuration
```

## Troubleshooting

- **No sound:** check the system volume, and that the selected music file plays in another app.
- **Linux without a sound server crashes at start:** run with `QT_AUDIO_BACKEND=pulseaudio python main.py`.
- **`ModuleNotFoundError: PyQt6`:** activate the virtual environment first.
