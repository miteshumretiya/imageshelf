# ImageShelf – Design Specification (Task 1)

## 1.1 Application purpose

People keep thousands of photos spread across phone backups, downloads and old folders. The same photo often exists several times under different names, and it is hard to see what a folder actually contains.

**ImageShelf** is a desktop catalogue for a local folder of images. It builds a browsable "shelf" of thumbnails, reports each image's size and shape, finds duplicate photos so space can be freed, and lets the user enjoy the collection as a slideshow with music.

- **Intended user:** a home user or student with a large, messy personal photo collection. They are comfortable with a desktop app, but are not a programmer.
- **Main purpose:** catalogue, browse and de-duplicate photos without uploading them anywhere.

Scanning hundreds of large photos (hashing every byte and decoding images for thumbnails) takes long enough to freeze a GUI. The app therefore does this work in the background with progress feedback.

## 1.2 Functional requirements

| ID | Requirement |
|---|---|
| FR1 | The user shall be able to choose a folder and catalogue all supported images in it (JPEG, PNG, GIF, BMP, WEBP, TIFF), optionally including sub-folders. |
| FR2 | The system shall show the images as a thumbnail shelf and as a sortable details table (name, dimensions, format, size, modified date, hash, folder). |
| FR3 | The user shall be able to search images by name and filter them by shape (landscape, portrait, square). |
| FR4 | The system shall process images in the background, showing progress, keeping the window responsive, and allowing the user to cancel. |
| FR5 | The system shall detect duplicate images by content (SHA-256), highlight them, offer a "duplicates only" filter and report the space wasted by copies. |
| FR6 | The user shall be able to preview the selected image with its details. |
| FR7 | The user shall be able to run a slideshow of the visible images at a chosen interval, with optional background music they select. |
| FR8 | The system shall notify the user with a message and a sound when processing finishes. |
| FR9 | The user shall be able to configure worker threads, sub-folder scanning and a maximum file size, with invalid values rejected. |
| FR10 | The system shall list unreadable or damaged files in an Errors tab without stopping the scan. |
| FR11 | The user shall be able to export the catalogue to a CSV file. |

## 1.3 GUI design (wireframe)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ File  Scan  View  Help                                              (menus) │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Open][Rescan][Cancel] | [Shelf][Details] | [Search by name…] [All shapes ▾] │
│ [Show duplicates only] | [Export]                                  (toolbar) │
├───────────────────────────────────────────────┬──────────────────────────────┤
│ Folder: C:\Users\me\Pictures                  │ [Preview] [Summary] [Errors] │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐           │ ┌──────────────────────────┐ │
│ │thumb │ │thumb │ │thumb │ │thumb │  SHELF    │ │                          │ │
│ └──────┘ └──────┘ └──────┘ └──────┘  (grid)   │ │      selected image      │ │
│  a.jpg    b.jpg    c.png    d.jpg             │ │                          │ │
│ ┌──────┐ ┌──────┐   … or DETAILS table:       │ └──────────────────────────┘ │
│ │thumb │ │thumb │   Name|Dims|Format|Size|…   │ name · 4000×3000 · 2.1 MB    │
│ └──────┘ └──────┘   (duplicates highlighted)  │ ┌─ Slideshow ──────────────┐ │
│                                               │ │[▶ Start] every [3 s]     │ │
│                                               │ │[Choose music…] Vol ──●── │ │
│                                               │ └──────────────────────────┘ │
├───────────────────────────────────────────────┴──────────────────────────────┤
│ Processed 120 of 300 images…                    120 images  [████░░░░] 40%  │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Main window:** the left part (grid or table) and the right part (tabs) are separated by a draggable splitter.
- **Dialogs:**
  - folder chooser
  - music file chooser
  - Settings dialog (worker threads, sub-folders, maximum MB)
  - Save CSV
  - error and warning message boxes
  - "Scan finished" notification
- **Navigation:**
  - menus, toolbar and keyboard shortcuts (Ctrl+O, F5, Esc, Ctrl+1/2, Ctrl+D, F11)
  - double-click opens the Preview tab
- **Feedback:** status-bar messages, progress bar, image count, Summary tab, Errors tab.

## 1.4 Architecture

The application uses **MVC adapted to Qt's model/view framework**:

```
             user actions                     custom signals
  ┌────────────────┐    calls    ┌──────────────────┐  (queued)  ┌───────────────────────┐
  │ VIEW           │ ──────────▶ │ CONTROLLER       │ ◀───────── │ WORKERS               │
  │ MainWindow     │             │ MainController   │            │ ScanJob (QRunnable)   │
  │ PreviewPanel   │ ◀────────── │ - start/cancel   │ ─────────▶ │ + ThreadPoolExecutor  │
  │ SettingsDialog │   signals   │ - export         │   starts   └──────────┬────────────┘
  └───────┬────────┘             └────────┬─────────┘                       │ uses
          │ displays                      │ updates                         ▼
  ┌───────▼───────────────────────────────▼──────────┐       ┌───────────────────────────┐
  │ MODEL                                            │       │ SERVICES (business logic) │
  │ ImageTableModel + ImageFilterProxyModel (Qt)     │       │ image_service, thumbnailer│
  │ ImageItem, ScanSummary, AppSettings (dataclasses)│       │ ResultsStore (locked)     │
  └──────────────────────────────────────────────────┘       └───────────────────────────┘
```

- **Model:** the data classes and the Qt table model. The model knows nothing about widgets.
- **Services:** all processing logic (validation, scanning, hashing, thumbnails, duplicates, export). It has no widgets and is unit-tested directly.
- **View:** builds widgets and displays data. Its slots are short: they read input, call the controller and update the display.
- **Controller:**
  - validates requests and starts or cancels workers
  - receives worker results (in the GUI thread) and updates the model
  - re-emits custom signals that the view listens to
- **Workers:** run the slow work off the GUI thread. They only communicate through signals and the lock-protected `ResultsStore`.

**Why this structure:** logic can be tested without a GUI, threads never touch widgets, and the shelf and table can share one model. Swapping the view (for example, adding a third view) needs no change to the logic.
