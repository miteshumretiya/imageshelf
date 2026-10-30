# START HERE: your step-by-step plan

The code, tests, benchmark, build file and document templates are done. What remains is the work only you can do:
- run it
- build the Git history
- test by hand with screenshots
- run the benchmark on your PC
- package it
- finish the report

Follow the steps in order. Commands are for **Windows PowerShell**; Mac/Linux differences are in brackets.

Make a folder called `evidence/` and save every screenshot there with the step number in the name (e.g. `07_progress.png`). The report needs them.

> **Academic honesty:** this starter was produced with AI help. Check your module's AI-use policy and declare it as required. Make sure you can explain every file; you will demo it live.

---

## Step 1 – Set up and run (10 min)

```powershell
cd imageshelf
python -m venv venv
venv\Scripts\activate                 # [Mac/Linux: source venv/bin/activate]
pip install -r requirements.txt
python tools/make_sample_images.py sample_images
python main.py sample_images
```

Try everything once:
- Shelf and Details views (Ctrl+1 / Ctrl+2)
- the search box and the shape filter
- "Show duplicates only"
- the Errors tab
- Preview → Choose music… → `sample_images/music/slideshow_music.wav` → Start slideshow
- File → Export CSV

Then run the tests and **screenshot the result**:

```powershell
python -m pytest -v
```

## Step 2 – Read the code in this order (while committing, step 3)

1. `app/models/image_item.py`: the data
2. `app/services/image_service.py` and `thumbnailer.py`: the logic
3. `app/services/results_store.py`: the **lock** (Task 7)
4. `app/workers/scan_worker.py`: the **threads** (Task 6)
5. `app/controllers/main_controller.py`: the custom signals
6. `app/views/main_window.py` and `preview_panel.py`: the GUI and **QtMultimedia**

The docstring at the top of each file explains what it does and why.

## Step 3 – Build the Git history as you review each part (15 min)

Commit each part *after* you have read and run it. Use the commands exactly. Set your name first:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"

git init -b main
git add .gitignore README.md START_HERE.md requirements.txt docs/design_spec.md
git commit -m "docs: add design specification and project setup"

git add app/__init__.py app/utils.py app/models/__init__.py app/models/image_item.py app/services/__init__.py app/services/image_service.py app/services/thumbnailer.py tests/__init__.py tests/conftest.py tests/test_image_service.py tests/test_thumbnailer.py
git commit -m "feat: add image model and processing services with unit tests"

git switch -c feature/threaded-processing
git add app/services/results_store.py app/workers tests/test_results_store.py benchmarks/race_condition_demo.py
git commit -m "feat: add thread-safe results store and background scan worker"
git switch main
git merge --no-ff feature/threaded-processing -m "Merge branch 'feature/threaded-processing'"

git switch -c feature/gui
git add app/models/image_table_model.py app/controllers app/views main.py assets tools tests/test_table_model.py tests/test_controller.py
git commit -m "feat: add main window with shelf/details views, slideshow music and controller"
git switch main
git merge --no-ff feature/gui -m "Merge branch 'feature/gui'"

git switch -c feature/performance
git add benchmarks/benchmark.py
git commit -m "feat: add sequential vs threads vs processes benchmark and parallel query"
git switch main
git merge --no-ff feature/performance -m "Merge branch 'feature/performance'"

git add imageshelf.spec docs/test_plan.md docs/defect_log.md docs/report_template.md
git commit -m "build: add PyInstaller spec, test plan and defect log"
git status        # should say "nothing to commit"
```

## Step 4 – Controlled merge conflict (5 min). Screenshot every stage.

```powershell
git switch -c feature/version-beta
```
Open `app/__init__.py` and change `__version__ = "1.0.0"` to `__version__ = "1.1.0-beta"`. Save, then:
```powershell
git commit -am "chore: mark version as 1.1.0 beta"
git switch main
```
Open the same file and change the same line to `__version__ = "1.0.1"`. Save, then:
```powershell
git commit -am "chore: bump patch version to 1.0.1"
git merge feature/version-beta          # -> CONFLICT in app/__init__.py  (screenshot)
```
Open `app/__init__.py` and screenshot the `<<<<<<< ======= >>>>>>>` markers. Keep one line (for example `__version__ = "1.1.0"`) and delete the markers. Then:
```powershell
git add app/__init__.py
git commit -m "Merge feature/version-beta: resolve version conflict"
git log --oneline --graph --all          # screenshot
```
Help → About in the app now shows the version you chose.

## Step 5 – GitHub: push, pull request, pull (10 min)

1. On github.com create a **new empty repository** called `imageshelf`. Do not add a README.
2. Push your work:
```powershell
git remote add origin https://github.com/YOUR-USERNAME/imageshelf.git
git push -u origin main
git switch -c feature/evidence
```
3. Add your screenshots folder:
```powershell
git add evidence
git commit -m "docs: add testing evidence"
git push -u origin feature/evidence
```
4. On GitHub click **Compare & pull request**, write a short description, then **Merge**. Screenshot the PR page.
5. Bring the merge back to your PC:
```powershell
git switch main
git pull            # screenshot
```

## Step 6 – Manual testing (20 min)

Open `docs/test_plan.md`. Run each R-test and C-test, fill in **Actual** and **Pass/Fail**, and take a screenshot of the important ones. At minimum: R07, R08, R10, R13, R15 and C04.

For the progress and cancel tests, create a slow folder first. It takes about 1 minute:
```powershell
python tools/make_sample_images.py big_images --big 60
```
If any test fails, that is good material: write it in `docs/defect_log.md` (row D6), fix it, commit with `fix: ...`, and rerun the test.

## Step 7 – Performance investigation (10 min, runs by itself)

```powershell
python benchmarks/race_condition_demo.py      # screenshot: lost updates without the lock
python benchmarks/benchmark.py                # uses big_images, writes benchmarks/results.md
```
Paste the tables into report section 8. Explain *your* numbers using the explanation already in the template: threads help hashing and thumbnails because the GIL is released in C code; only processes help the pure-Python loop. Then do the Amdahl comment.

## Step 8 – Package the app (10 min). Start this, then keep testing while it builds.

```powershell
pyinstaller imageshelf.spec
dist\ImageShelf\ImageShelf.exe sample_images     # [Mac/Linux: ./dist/ImageShelf/ImageShelf]
```
Screenshot the `dist` folder and the running app. If you can, copy `dist\ImageShelf` to another PC and run it there; that is test P02. If the folder is too big to submit, submit screenshots and the `.spec` file as packaging evidence.

## Step 9 – Report and slides (25 min)

Fill in every **TODO** in `docs/report_template.md`. Sections 15.2–15.4 are already written to match the code. Make the 10 slides listed in 15.8 and rehearse the demo order once.

## What to submit (brief: "Assessment 2 Deliverables")

| Deliverable | Where |
|---|---|
| 1. Source code | `app/`, `main.py`, `tools/` |
| 2. Git repository | your GitHub link + `git log --graph` screenshot (or zip including the hidden `.git` folder) |
| 3. Automated tests | `tests/` |
| 4. Test plan and results | `docs/test_plan.md` (filled in) + `evidence/` |
| 5. Technical report | `docs/report_template.md` → export to Word/PDF |
| 6. Performance investigation | `benchmarks/` + `results.md` + report section 8 |
| 7. Packaging | `imageshelf.spec` + `dist` or screenshots |
| 8. README | `README.md` |
