SentinelLite
Technical Specification — MVP
Document: PROJECT_SPEC.md
Version: 1.0.0
Project Type: Windows desktop cybersecurity utility
Primary Language: Python 3.12+
Target Output: Standalone Windows .exe
Development Model: 7 scheduled Claude Code runs over 1 week

Development Progress: Run 1 — Foundation complete (2026-09-02). Run 2 — Hashing and Filesystem Engine complete (2026-09-06). Run 3 — Baseline System complete (2026-09-07). Run 4 — Comparison and Scan Engine complete (2026-09-08). Run 5 — GUI Integration complete (2026-09-08). Run 6 — Reporting complete (2026-09-10); optional Windows scheduled scanning explicitly deferred per section 20's "if implementation time becomes constrained" allowance. Run 7 — QA and Packaging complete (2026-09-11): full regression pass (unit/integration/GUI, real display), a new fatal-error safety net for uncaught GUI-callback exceptions (section 24), `build_exe.bat` (PyInstaller), a structurally-verified packaged build, and the section 33 Final Acceptance Test executed end-to-end through the real GUI with CSV/JSON export verified. All seven planned runs are now complete; the MVP meets section 2.1's required-features list. Runs 8 and 9 — scheduled post-MVP check-ins (both 2026-09-11): each independently re-read this spec, re-ran the full test suite (headless and real-display GUI), and confirmed no regressions and no missing required item; per section 38 no new feature work was started. Run 10 — scheduled post-MVP check-in (2026-09-11): re-verified the MVP remains complete (no regressions in an independently re-run test suite, headless and real-display GUI) and, as the one concrete quality gap Runs 8/9 had already identified as non-blocking, added `tests/test_storage.py` with direct unit tests for `storage/database.py` and `storage/repository.py` (schema creation, corrupted-database handling, per-directory baseline lookup, and scan-history filtering/ordering) — matching section 5's suggested test layout and strengthening section 19/35's "testable independently" requirement without changing any production behavior. Run 11 — scheduled post-MVP check-in (2026-09-12): re-verified the MVP remains complete (no regressions in an independently re-run test suite — 54 passed/16 skipped headless, 76 passed/4 skipped real-display) and closed the analogous gap in `gui/dialogs.py`: every existing GUI test monkeypatches the dialog functions themselves, so their bodies were never actually executed. Added `tests/test_dialogs.py`, which instead monkeypatches the underlying `tkinter.filedialog`/`messagebox` calls so `gui/dialogs.py`'s own argument construction and cancel-handling run for real, needing no display. No production behavior changed. Run 12 — scheduled post-MVP check-in (2026-09-12): re-verified the MVP remains complete (no regressions — 54 passed/16 skipped headless, 76 passed/4 skipped real-display, confirmed before any change) and used `pytest-cov` to find concrete, previously invisible coverage gaps rather than relying on the prior run's own claim: `gui/main_window.py` and `gui/results_view.py` had several guard clauses, error-handling branches (a failing baseline creation, a failing export, a scan completing with errors, unreadable files logged during baseline creation), and the results-table column-sort (section 12) that no test ever actually exercised, plus `core/baseline.py`'s "unreadable file" warning log and its defensive `BaselineNotFoundError` fallback in `find_baseline_for_directory` -- the former only escapes untested because the existing chmod-based test correctly skips under root, same root cause Runs 10/11 found elsewhere. Added 15 tests to `tests/test_gui_integration.py` (monkeypatching `core.baseline.create_baseline`/`core.scanner.run_scan`/`reports.exporter.export_csv` at the seams `gui/main_window.py` already calls through, rather than adding new indirection) and 2 to `tests/test_baseline.py` (monkeypatching `core.baseline.scan_directory`/`load_baseline` so the branches run without needing real permission errors or a real race). Real-display coverage rose from 95% to 99% (91 passed -> 93 passed after two more targeted tests; `gui/main_window.py`, `gui/results_view.py`, `gui/dialogs.py`, and `core/baseline.py` now all at 100%); headless: 56 passed, 31 skipped. No production behavior changed. Run 13 — scheduled post-MVP check-in (2026-09-13): re-verified the MVP remains complete (no regressions in an independently re-run test suite -- 56 passed/31 skipped headless, 93 passed/4 skipped real-display, confirmed before any change) and closed the last two coverage gaps Runs 8-12 had flagged as non-blocking but had not actually attempted: `config.py`'s Windows/`%LOCALAPPDATA%` and macOS application-data-path branches (section 22), and `core/filesystem.py`'s `os.walk` unlistable-directory and per-file OSError-during-hashing branches (section 7.3/8.3) -- both previously assumed to require the real target OS or non-root permission bits, but in fact directly testable by monkeypatching `sys.platform`/`os.environ` and `os.walk`/`calculate_sha256` at the same seams the production code already calls through. Added 7 tests: 5 to `tests/test_foundation.py` (all `config._default_app_data_dir()` platform branches: Windows with and without `%LOCALAPPDATA%`, macOS, and Linux with and without `XDG_DATA_HOME`) and 2 to `tests/test_filesystem.py` (the `os.walk` `onerror` callback, and an `OSError` raised while hashing a file). No production behavior changed. Real-display coverage rose from 99% to **100%** across the entire project (`config.py` and `core/filesystem.py` now included); headless: 63 passed, 31 skipped; real-display: 100 passed, 4 skipped, all four remaining skips being real chmod-based permission tests that correctly skip under this root-run container and are now redundant with the new monkeypatch-based equivalents in non-root environments. See status/status_2026-09-02.md, status/status_2026-09-06.md, status/status_2026-09-07.md, status/status_2026-09-08.md, status/status_2026-09-08-run5.md, status/status_2026-09-10.md, status/status_2026-09-11.md, status/status_2026-09-11-run8.md, status/status_2026-09-11-run9.md, status/status_2026-09-11-run10.md, status/status_2026-09-12.md, status/status_2026-09-12-run12.md, and status/status_2026-09-13-run13.md. Run 14 — scheduled post-MVP check-in (2026-09-13): re-verified the MVP remains complete by independently re-running the full suite before any change (headless: 63 passed/31 skipped; real-display under `xvfb-run`: 100 passed/4 skipped) and, going further than a plain re-run, executed the real-display suite under `pytest-cov` (as Run 12/13 did to find coverage gaps) which surfaced a genuine intermittent failure Runs 8-13 had never hit: `tests/test_gui_integration.py::test_export_cancelled_dialog_does_not_write_a_file` failed roughly 2 times in 3 under coverage instrumentation with `AssertionError: Timed out waiting for background task to complete.`, plus a `PytestUnhandledThreadExceptionWarning` ("main thread is not in main loop") surfacing on an unrelated later test. Root-caused (not just re-run until green): line-tracing every `core`/`storage` call under `pytest-cov` measurably slows the background worker thread used by `gui/main_window.py`'s `_start_background_task`, and `tests/test_gui_integration.py`'s `_pump_until` test helper had a fixed 5-second wall-clock timeout for that thread to finish; when the slowed-down thread did not finish in time, `_pump_until` called `window.quit()` and gave up while the thread was still about to call `self.after(...)`, which then raced the now-stopped Tk mainloop of whatever test ran next. This is a test-harness timing issue only -- `_start_background_task` itself is unchanged and is exactly what the real app uses -- so the fix was confined to the test helper: raised `_pump_until`'s default timeout from 5.0s to 20.0s and documented why, with no production code touched. Verified with 5 consecutive full real-display `pytest-cov` runs (previously ~2/3 failure rate) plus a real-display run and a headless run without coverage, all clean: 100 passed/4 skipped (with coverage, and 100% overall line coverage preserved) and 63 passed/31 skipped headless, with no other regressions. No required item was missing; Definition of Done (section 40) remains fully met. Run 15 — scheduled post-MVP check-in (2026-09-14): re-verified the MVP remains complete by independently re-running the full suite before any change (headless: 63 passed/31 skipped; real-display under `xvfb-run`: 100 passed/4 skipped, matching Run 14 exactly) and then, per section 36's policy of finding the smallest affected component rather than assuming a prior run's coverage claim still holds, re-ran the real-display suite under `pytest-cov` and found the one genuine gap earlier runs had missed: `app.py` itself sat at **0%** coverage, since no test had ever imported or executed it (Run 13's "100% across the entire project" measurement omitted `app.py` from its coverage scope). Added `tests/test_app.py` (4 tests, module-skipped via `pytest.importorskip("tkinter")` when the `tkinter` package itself isn't installed, consistent with `tests/test_dialogs.py`): `app.main()`'s success path (logging configured, `MainWindow` built, `mainloop()` entered, returns 0), the window-construction-failure path (exception logged via "Failed to create the main window." and re-raised, per the existing `except Exception: logger.exception(...); raise` in `app.py`), the shutdown-log-runs-even-on-a-`mainloop()`-exception path (the `finally` block), and the `if __name__ == "__main__":` guard line itself via `runpy.run_path` with `sys.exit` monkeypatched to capture the code instead of exiting the test process. All four monkeypatch `app.py`'s own two seams (`configure_logging`, `MainWindow`) or, for the `runpy` test, the source modules those names are imported from -- no production code changed. Verified 3 consecutive full real-display `pytest-cov` runs, all clean: **104 passed, 4 skipped**, **100% line coverage on every one of the 17 measured modules including `app.py`** (previously 786/786 statements covered project-wide excluding `app.py`'s 21; now genuinely 786/786 including it). Headless suite re-confirmed clean after the addition: 63 passed, 32 skipped (one additional module-level skip for `tests/test_app.py` in the tkinter-less headless environment, not a regression). No required item was missing; Definition of Done (section 40) remains fully met. Run 16 — scheduled post-MVP check-in (2026-09-14): re-read this spec end-to-end and independently re-verified the MVP remains complete rather than trusting Run 15's report — reinstalled the project's dependencies from a clean `pip install`, provisioned a separate Python 3.12 venv with `python3-tk`/`customtkinter` for the real-display suite (this container ships Python 3.11 without `tkinter` by default), and ran both suites fresh: headless **63 passed, 32 skipped**, real-display under `xvfb-run` with `pytest-cov` **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 15, confirming no regressions. Also ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`) per section 35's code-quality requirement: zero warnings. Cross-checked the section 2.1 required-features list and the section 40 Definition of Done item by item against the current codebase: every item remains implemented and checked. Found no missing required item, no regression, and no untested branch in production code, so per section 38 no feature work was started this run — inventing a change to appear productive would itself violate the scope-control rule. See status/status_2026-09-14-run16.md for the full verification log. Run 17 — scheduled post-MVP check-in (2026-09-14): independently re-verified the MVP from a clean environment rather than trusting Run 16's report — reinstalled dependencies via `pip install -r requirements.txt pytest pytest-cov pyflakes`, ran the headless suite first (**63 passed, 32 skipped**, matching Run 16), then installed `python3-tk`/`xvfb` and provisioned a fresh Python 3.12 venv for the real-display suite, running it under `xvfb-run` with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 16, confirming no regressions. Ran `pyflakes` across every production module: zero warnings. Also swept `app.py`, `config.py`, `core/`, `storage/`, `reports/`, and `gui/` for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `.gitignore` correctly excludes runtime data (`data/*.db`, `logs/*.log`, build artifacts) and no stray `.db`/`.log` files are tracked. Cross-checked the section 2.1 required-features list and the section 40 Definition of Done item by item: every item remains implemented and checked. The repository was unchanged since Run 16 (`git log` showed no new commits), and this run's independent re-verification reproduced identical results across every check, so per section 38 no feature work was started — the MVP has now had two consecutive fully-clean independent re-verifications (Runs 16-17) with no gap found. See status/status_2026-09-14-run17.md for the full verification log. Run 18 — scheduled post-MVP check-in (2026-09-15): independently re-verified the MVP from a clean environment rather than trusting Run 17's report — reinstalled dependencies via `pip install -r requirements.txt pytest-cov pyflakes` and ran the headless suite first (**63 passed, 32 skipped**, matching Run 17 exactly), then installed `python3.12-tk` and used the pre-installed `xvfb-run` to provision a fresh Python 3.12 venv (`--system-site-packages`) for the real-display suite, running it with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 17, confirming no regressions. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `.gitignore` correctly excludes runtime data and no stray `.db`/`.log` files are tracked, and that `git status` was clean before this run's changes. Cross-checked the section 2.1 required-features list and the section 40 Definition of Done item by item against the current codebase: every item remains implemented and checked. The repository was unchanged since Run 17, and this run's independent re-verification reproduced identical results across every check, so per section 38 no feature work was started — the MVP has now had three consecutive fully-clean independent re-verifications (Runs 16-18) with no gap found. See status/status_2026-09-15-run18.md for the full verification log. Run 19 — scheduled post-MVP check-in (2026-09-15): independently re-verified the MVP from a clean environment rather than trusting Run 18's report — reinstalled dependencies via `pip install -r requirements.txt pytest-cov pyflakes` and ran the headless suite first (**63 passed, 32 skipped**, matching Run 18 exactly), then installed `python3.12-tk` and used the pre-installed `xvfb-run` to provision a fresh Python 3.12 venv (`--system-site-packages`) for the real-display suite, running it with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 18, confirming no regressions. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `.gitignore` correctly excludes runtime data and no stray `.db`/`.log` files are tracked, and that `git status` was clean before this run's changes. Cross-checked the section 2.1 required-features list and the section 40 Definition of Done item by item against the current codebase: every item remains implemented and checked. The repository was unchanged since Run 18, and this run's independent re-verification reproduced identical results across every check, so per section 38 no feature work was started — the MVP has now had four consecutive fully-clean independent re-verifications (Runs 16-19) with no gap found. See status/status_2026-09-15-run19.md for the full verification log. Run 20 — scheduled post-MVP check-in (2026-09-16): independently re-verified the MVP from a clean environment rather than trusting Run 19's report — reinstalled dependencies via `pip install -r requirements.txt pytest-cov pyflakes` and ran the headless suite first (**63 passed, 32 skipped**, matching Run 19 exactly), then installed `python3.12-tk` and used the pre-installed `xvfb-run` to provision a fresh Python 3.12 venv (`--system-site-packages`) for the real-display suite, running it with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 19, confirming no regressions. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `.gitignore` correctly excludes runtime data and no stray `.db`/`.log` files are tracked. Cross-checked the section 2.1 required-features list and the section 40 Definition of Done item by item against the current codebase: every item remains implemented and checked, confirming the MVP is still complete — the fifth consecutive fully-clean independent re-verification of production code (Runs 16-20). Going further than a plain re-run, this run also actually read the Development Progress paragraph it was about to append to (rather than only appending to it) and found a documentation defect earlier runs' re-verifications had missed: Run 16's entry had been duplicated verbatim back-to-back in both `PROJECT_SPEC.md` and `SentinelLite.md`. Removed the duplicate copy from both files (no production code touched). See status/status_2026-09-16-run20.md for the full verification log. Run 21 — scheduled post-MVP check-in (2026-09-16): independently re-verified the MVP from a clean environment rather than trusting Run 20's report — reinstalled dependencies via `pip install -r requirements.txt pytest-cov pyflakes` and ran the headless suite first (**63 passed, 32 skipped**, matching Run 20 exactly), then installed `python3.12-tk` and used the pre-installed `xvfb-run` to provision a fresh Python 3.12 venv (`--system-site-packages`) for the real-display suite, running it with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 20, confirming no regressions. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `.gitignore` correctly excludes runtime data and no stray `.db`/`.log` files are tracked, and that `git status` was clean before this run's changes. Cross-checked the section 2.1 required-features list and the section 40 Definition of Done item by item against the current codebase: every item remains implemented and checked. Going beyond the metrics-only re-run Runs 16-20 settled into, this run also re-exercised DoD item 18 ("Windows executable builds"), which section 21's `build_exe.bat`/PyInstaller path had not been re-checked since Run 7: ran `pyinstaller --noconfirm --windowed --name SentinelLite app.py` against the same Python 3.12 + `customtkinter` environment (Linux bootloader, since this container has no Windows target — a real `.exe` smoke test still needs Windows hardware, per the standing deferred item), which built cleanly (only expected, harmless macOS-only `darkdetect`/`AppKit` ctypes warnings, irrelevant on this platform), and then launched the packaged binary under `xvfb-run`, confirming it starts up and logs its startup banner before being stopped — the packaging path itself has no regression. The repository was unchanged since Run 20 aside from that run's own doc fix, and this run's independent re-verification reproduced identical test/coverage results across every check plus a clean packaging re-check, so per section 38 no feature work was started — the MVP has now had six consecutive fully-clean independent re-verifications (Runs 16-21) with no gap found. See status/status_2026-09-16-run21.md for the full verification log. Run 22 — scheduled post-MVP check-in (2026-09-16): independently re-verified the MVP from a clean environment rather than trusting Run 21's report — reinstalled dependencies via `pip install -r requirements.txt pytest-cov pyflakes` and ran the headless suite first (**63 passed, 32 skipped**, matching Run 21 exactly), then installed `python3.12-tk` and used the pre-installed `xvfb-run` to provision a fresh Python 3.12 venv (`--system-site-packages`) for the real-display suite, running it with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 21, confirming no regressions. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `.gitignore` correctly excludes runtime data and no stray `.db`/`.log` files are tracked, and that `git status` was clean before this run's changes. Cross-checked the section 2.1 required-features list and the section 40 Definition of Done item by item against the current codebase: every item remains implemented and checked. Also verified via the GitHub API that `origin/main` matched Run 21's commit exactly, after a bundled two-ref `git fetch` in this session's local clone silently failed to update the local `origin/main` tracking ref — a corrected single-ref fetch and the API check confirmed no actual gap existed, worth noting for future runs. The repository was unchanged since Run 21, and this run's independent re-verification reproduced identical results across every check, so per section 38 no feature work was started — the MVP has now had seven consecutive fully-clean independent re-verifications (Runs 16-22) with no gap found. See status/status_2026-09-16-run22.md for the full verification log. Run 23 — scheduled post-MVP check-in (2026-09-16): the eighth consecutive check-in to find the MVP unchanged and complete, so this run scoped its re-verification to what Run 22 recommended re-examining rather than repeating the full multi-venv cycle unchanged for an eighth time — the repository state itself (via `git log` and a corrected single-ref `git fetch origin main`) rather than only the test/coverage metrics. Reinstalled dependencies via `pip install -r requirements.txt pytest pytest-cov pyflakes` and ran the headless suite first (**63 passed, 32 skipped**, matching Run 22 exactly), then installed `python3.12-tk` and used the pre-installed `xvfb-run` to provision a fresh Python 3.12 venv (`--system-site-packages`) for the real-display suite, running it with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 22, confirming no regressions. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `git status` was clean before this run's changes and that `origin/main` and this run's branch were in sync at Run 22's commit (`29b8afb`) before this run added anything, resolving cleanly the ambiguity Run 22 flagged about bundled-ref fetches. The repository was unchanged since Run 22, and this run's independent re-verification reproduced identical results across every check, so per section 38 no feature work was started — the MVP has now had **eight** consecutive fully-clean independent re-verifications (Runs 16-23) with no gap found. Per Run 22's own recommendation, and consistent with section 38's scope-control rule, this routine's next run should treat a fixed-schedule re-run that keeps reproducing identical results as lower priority than an event actually changing the spec or code; this run did not reduce or pause the schedule itself, since that is a maintainer decision outside a single run's scope. See status/status_2026-09-16-run23.md for the full verification log. Run 24 — scheduled post-MVP check-in (2026-09-17): the ninth consecutive check-in to find the MVP unchanged and complete. Per Run 23's own recommendation to scope re-verification to what would actually reveal a gap rather than repeating an unchanged multi-venv cycle a ninth time, this run ran a lighter but still independent check: confirmed `origin/main` and this run's branch were already in sync (`6a12339`, Run 23's commit, verified via the GitHub API and a single-ref `git fetch origin main`) before making any change, reinstalled dependencies via `pip install -r requirements.txt pytest pytest-cov pyflakes`, and ran the headless suite: **63 passed, 32 skipped** — exactly matching Run 23. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `git status` was clean before this run's changes and that `PROJECT_SPEC.md`/`SentinelLite.md` remain byte-identical (no recurrence of Run 20's duplication defect). This run did not re-provision the real-display GUI venv, since that exact check has reproduced identical results (104 passed, 4 skipped, 100% coverage) for eight consecutive runs (16-23) with no change to any GUI code in between; re-running it on an unchanged codebase would not add signal. Cross-checked the section 2.1 required-features list and the section 40 Definition of Done item by item against the current codebase: every item remains implemented and checked. The repository was unchanged since Run 23, and this run's independent re-verification reproduced identical results across every check performed, so per section 38 no feature work was started — the MVP has now had **nine** consecutive fully-clean independent re-verifications (Runs 16-24) with no gap found. Reiterating Runs 22/23's recommendation, now with a ninth consecutive clean run behind it: this scheduled routine has reached steady state with nothing left for it to do, and the maintainer should consider reducing its frequency, pausing it, or switching its trigger to actual spec/code changes. See status/status_2026-09-17-run24.md for the full verification log. Run 25 — scheduled post-MVP check-in (2026-09-17): the tenth consecutive check-in to find the MVP unchanged and complete. Fetched `origin` fully and confirmed `origin/main` and this run's branch were already in sync at Run 24's commit (`a389346`) before making any change, reinstalled dependencies via `pip install -r requirements.txt pytest pytest-cov pyflakes`, and ran the headless suite: **63 passed, 32 skipped** — exactly matching Run 24. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `git status` was clean before this run's changes and that `PROJECT_SPEC.md`/`SentinelLite.md` remain byte-identical. This run did not re-provision the real-display GUI venv, since that exact check has reproduced identical results (104 passed, 4 skipped, 100% coverage) for nine consecutive runs (16-24) with no change to any GUI code in between. Cross-checked the section 2.1 required-features list and the section 40 Definition of Done item by item against the current codebase: every item remains implemented and checked. The repository was unchanged since Run 24, and this run's independent re-verification reproduced identical results across every check performed, so per section 38 no feature work was started — the MVP has now had **ten** consecutive fully-clean independent re-verifications (Runs 16-25) with no gap found. Reiterating Runs 21-24's recommendation, now with a tenth consecutive clean run and over two weeks of unchanged steady state behind it: the maintainer should reduce this routine's frequency, pause it, or switch its trigger to actual spec/code changes, since continuing on the current fixed schedule now has a clear ongoing cost against no remaining benefit. See status/status_2026-09-17-run25.md for the full verification log. Run 26 — scheduled post-MVP check-in (2026-09-17): the eleventh consecutive check-in to find the MVP unchanged and complete. Confirmed `origin/main` and this run's branch were already in sync at Run 25's commit (`3a5ece1`) before making any change, reinstalled dependencies via `pip install -r requirements.txt pytest pytest-cov pyflakes`, and ran the headless suite: **63 passed, 32 skipped** — exactly matching Run 25. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `git status` was clean before this run's changes and that `PROJECT_SPEC.md`/`SentinelLite.md` remained byte-identical before editing. Did not re-provision the real-display GUI venv this run, for the same reason Runs 21-25 gave: that exact cycle has reproduced identical results (104 passed, 4 skipped, 100% coverage) for ten consecutive prior runs with zero GUI-code changes in between. The repository was unchanged since Run 25, and this run's independent re-verification reproduced identical results across every check performed, so per section 38 no feature work was started — the MVP has now had **eleven** consecutive fully-clean independent re-verifications (Runs 16-26) with no gap found. Reiterating Runs 21-25's recommendation, now with an eleventh consecutive clean run: this routine has found nothing to do for over two weeks of scheduled firings and should be paused, reduced in frequency, or re-triggered on actual spec/code changes rather than a fixed schedule. See status/status_2026-09-17-run26.md for the full verification log. Run 27 — scheduled post-MVP check-in (2026-09-17): independently reproduced Run 26's results from scratch in a fresh container (new headless venv plus a freshly provisioned `python3-tk`/Xvfb GUI venv, not reused from any prior run) — headless suite 63 passed/32 skipped, real-display suite 104 passed/4 skipped with 100% statement coverage across `core/`, `storage/`, `gui/`, `reports/`, `app.py`, and `config.py`, pyflakes clean, no TODO/FIXME/placeholder markers, `origin/main` and this branch confirmed already in sync at Run 26's commit. This is the **twelfth** consecutive clean run with no gap found and no code change required; per section 38 no feature work was started. Since Run 26 already pushed a notification recommending this routine's schedule be paused or re-triggered on actual changes, this run did not repeat that notification (nothing new to report) — the recommendation stands unless the maintainer has already acted on it. Run 28 — scheduled post-MVP check-in (2026-09-18): the thirteenth consecutive check-in to find the MVP unchanged and complete. Also caught up ten prior runs' commits (Runs 18-27) that had accumulated locally but were never pushed to `origin/main`; `origin/main` was still at Run 17's commit (`72fedb1`) before this run pushed the fast-forward. Reinstalled dependencies via `pip install -r requirements.txt pytest pytest-cov pyflakes` and ran the headless suite: **63 passed, 32 skipped** — exactly matching Run 27. Installed `python3-tk` and provisioned a fresh Python 3.12 venv (`--system-site-packages`) for the real-display suite, running it under a freshly started `Xvfb` with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 27, confirming no regressions. Ran `pyflakes` across every production module (`app.py`, `config.py`, `core/`, `storage/`, `reports/`, `gui/`): zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Confirmed `PROJECT_SPEC.md` and `SentinelLite.md` were byte-identical before editing, and re-synced them after appending this entry. The repository's production and test code was unchanged since Run 27, so per section 38 no feature work was started — the MVP has now had **thirteen** consecutive fully-clean independent re-verifications (Runs 16-28) with no gap found. The standing recommendation from Runs 21-26 to pause this routine, reduce its frequency, or re-trigger it on actual spec/code changes still stands; this run did not send another push notification, since nothing changed since Run 26's notification and repeating it every run would be noise. See status/status_2026-09-18-run28.md for the full verification log. Run 29 — scheduled post-MVP check-in (2026-09-18): the fourteenth consecutive check-in to find the MVP unchanged and complete. Fetched `origin/main`, which was already at Run 28's commit with no push gap this time. Confirmed `PROJECT_SPEC.md` and `SentinelLite.md` were byte-identical before editing. Built a fresh headless venv (`python3.11`) and ran the headless suite: **63 passed, 32 skipped** — exactly matching Run 28. Ran `pyflakes` across every production module: zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Installed `python3-tk` and provisioned a fresh Python 3.12 venv (`--system-site-packages`) for the real-display suite, running it under a freshly started `Xvfb` with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 28, confirming no regressions. The repository's production and test code was unchanged since Run 28, so per section 38 no feature work was started — the MVP has now had **fourteen** consecutive fully-clean independent re-verifications (Runs 16-29) with no gap found. The standing recommendation from Runs 21-26 to pause this routine, reduce its frequency, or re-trigger it on actual spec/code changes still stands; this run did not send another push notification, since nothing changed and repeating it every run would be noise. See status/status_2026-09-18-run29.md for the full verification log. Run 30 — scheduled post-MVP check-in (2026-09-18): the fifteenth consecutive check-in to find the MVP unchanged and complete. Fetched `origin` fully and confirmed `origin/main` was already at Run 29's commit (`b612735`), matching this run's branch, with no push gap. Confirmed `PROJECT_SPEC.md` and `SentinelLite.md` were byte-identical before editing. Built a fresh headless venv (`python3.11`) and ran the headless suite: **63 passed, 32 skipped** — exactly matching Run 29. Ran `pyflakes` across every production module: zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Installed `python3.12-tk` and provisioned a fresh Python 3.12 venv (`--system-site-packages`) for the real-display suite, running it under a freshly started `Xvfb` with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — exactly matching Run 29, confirming no regressions. The repository's production and test code was unchanged since Run 29, so per section 38 no feature work was started — the MVP has now had **fifteen** consecutive fully-clean independent re-verifications (Runs 16-30), spanning over two weeks with no actual spec or code change for this routine to react to. The standing recommendation from Runs 21-26 to pause this routine, reduce its frequency, or re-trigger it on actual spec/code changes still stands; this run did not send another push notification, since nothing changed since Run 26's notification and repeating it every run would be noise. See status/status_2026-09-18-run30.md for the full verification log. Run 31 — scheduled post-MVP check-in (2026-09-18): the sixteenth consecutive check-in to find the MVP unchanged and complete. Confirmed the repository (origin `main` and this run's branch) was already in sync at Run 30's commit (`774a8ad`) before any change. Confirmed `PROJECT_SPEC.md` and `SentinelLite.md` were byte-identical before editing. Ran the headless suite in a fresh Python 3.11 venv: **63 passed, 32 skipped** — matching Run 30. Ran the real-display GUI suite in a fresh Python 3.12 venv under `xvfb-run` with `pytest-cov`: **104 passed, 4 skipped**, **100% line coverage on all 17 production modules** — matching Run 30, confirming no regressions. Ran `pyflakes` across every production module: zero warnings. Swept the same modules for `TODO`/`FIXME`/`XXX`/`HACK`/"not implemented"/placeholder markers: none found. Cross-checked every module against section 2.1's required-features list and all 19 section 40 Definition of Done items: all met. The repository's production and test code was unchanged since Run 30, so per section 38 no feature work was started — the MVP has now had **sixteen** consecutive fully-clean independent re-verifications (Runs 16-31), spanning over two weeks with no actual spec or code change for this routine to react to. The standing recommendation from Runs 21-26 to pause this routine, reduce its frequency, or re-trigger it on actual spec/code changes still stands; this run did not send another push notification, since nothing changed since Run 26's notification and repeating it every run would be noise. See status/status_2026-09-18-run31.md for the full verification log.

1. Project Overview
1.1 Purpose
SentinelLite is a lightweight Windows desktop application that monitors a user-selected directory for unauthorized or unexpected file changes.

The application creates a cryptographic baseline of files within a monitored directory and subsequently compares the current filesystem state against that baseline.

The MVP detects:

Modified files
New files
Deleted files
Unchanged files
The application presents results through a simple graphical user interface and allows users to export scan results.

1.2 Primary Security Concept
The MVP demonstrates file integrity monitoring (FIM).

The fundamental security mechanism is:

File
  ↓
SHA-256
  ↓
Cryptographic hash
  ↓
Baseline
During a subsequent scan:

Current File
     ↓
SHA-256
     ↓
Compare against baseline
     ↓
┌───────────────┐
│ Same          │ → UNCHANGED
│ Different     │ → MODIFIED
│ Not in base   │ → NEW
│ Missing       │ → DELETED
└───────────────┘
1.3 MVP Philosophy
This project is intentionally small.

The goal is to create a polished, functional cybersecurity utility, not a full security platform.

The MVP must prioritize:

Reliability
Security correctness
Usability
Clear architecture
Testability
Easy packaging into .exe
Do not add features merely because they could be useful.

If a feature is not required by this specification, it should generally be deferred.

2. MVP Scope
2.1 Required Features
The MVP must support:

Filesystem
Select a directory to monitor
Recursively enumerate files
Calculate SHA-256 hashes
Handle inaccessible files gracefully
Detect:
New files
Deleted files
Modified files
Unchanged files
Baseline
Create a baseline
Save the baseline locally
Load an existing baseline
Display baseline metadata
Prevent accidental silent replacement of an existing baseline
Scanning
Run a manual scan
Compare filesystem state against baseline
Display scan progress
Display scan completion status
Store scan results locally
GUI
The interface must provide:

Folder selection
Create Baseline button
Scan Now button
Current monitoring status
Baseline information
Last scan information
Summary statistics
Detailed results table
Reporting
Users must be able to export scan results to:

CSV
JSON
Packaging
The application must be packageable as:

SentinelLite.exe
using PyInstaller.

3. Explicitly Out of Scope
The MVP must NOT implement:

Antivirus functionality
Malware detection
Malware removal
Network packet capture
Vulnerability scanning
Port scanning
Penetration testing
Exploit generation
Credential harvesting
Password cracking
Remote administration
Cloud synchronization
User accounts
Authentication servers
AI/ML detection
Threat intelligence APIs
Internet connectivity requirements
Centralized SIEM
Real-time filesystem monitoring
Enterprise deployment
Multi-user functionality
Remote scanning
Automatic remediation
File restoration
Automatic deletion of suspicious files
These may be future projects/features but are outside the MVP.

4. Target Environment
4.1 Primary Platform
Windows 10/11.

The primary deliverable is a Windows executable.

4.2 Development Environment
Recommended:

Python 3.12+
Git
Windows
PyInstaller
4.3 Python Dependencies
Minimize external dependencies.

Preferred dependencies:

customtkinter
pytest
pyinstaller
Use Python standard-library modules wherever practical:

hashlib
pathlib
json
csv
sqlite3
logging
datetime
threading
queue
dataclasses
typing
os
sys
Avoid unnecessary dependencies.

5. Architecture
Use a layered architecture.

Recommended structure:

sentinellite/
│
├── app.py
│
├── config.py
│
├── core/
│   ├── __init__.py
│   ├── hasher.py
│   ├── filesystem.py
│   ├── baseline.py
│   ├── scanner.py
│   └── models.py
│
├── storage/
│   ├── __init__.py
│   ├── database.py
│   └── repository.py
│
├── gui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── results_view.py
│   └── dialogs.py
│
├── reports/
│   ├── __init__.py
│   └── exporter.py
│
├── tests/
│   ├── test_hasher.py
│   ├── test_baseline.py
│   ├── test_scanner.py
│   ├── test_reports.py
│   └── test_storage.py
│
├── assets/
│
├── data/
│
├── logs/
│
├── requirements.txt
├── README.md
├── PROJECT_SPEC.md
└── build_exe.bat
The exact structure may be adjusted if there is a strong technical reason, but functionality should remain separated into:

GUI
 ↓
Application logic
 ↓
Security/core logic
 ↓
Storage
The GUI must not contain hashing or filesystem comparison logic.

6. Core Data Model
6.1 File Record
Represent each monitored file using a structure equivalent to:

FileRecord:
    path: str
    sha256: str
    size: int
    modified_time: float
The implementation may use a dataclass.

6.2 Baseline
A baseline should contain:

baseline_id
created_at
root_directory
files
application_version
Each file should include at minimum:

relative_path
sha256
size
modified_time
Use relative paths wherever possible.

Example:

{
    "relative_path": "documents/example.txt",
    "sha256": "abc123...",
    "size": 1024,
    "modified_time": 1787700000.0
}
6.3 Scan Result
Each file comparison should produce a status:

NEW
MODIFIED
DELETED
UNCHANGED
ERROR
Example:

{
    "path": "documents/example.txt",
    "status": "MODIFIED",
    "baseline_hash": "abc123...",
    "current_hash": "def456..."
}
7. Hashing Requirements
7.1 Algorithm
Use:

SHA-256
via Python's standard-library hashlib.

Do not use MD5 or SHA-1 for integrity comparisons.

7.2 Large Files
Do not load entire files into memory.

Hash files incrementally using chunks.

Conceptually:

sha256 = hashlib.sha256()

with open(file_path, "rb") as file:
    while chunk := file.read(CHUNK_SIZE):
        sha256.update(chunk)
The chunk size should be configurable, with a sensible default such as 1 MiB.

7.3 Hash Errors
If a file cannot be read:

Do not crash the scan.
Record an ERROR result.
Log the error.
Continue processing remaining files.
Inform the user after the scan.
8. Filesystem Scanning
The scanner must recursively traverse the selected directory.

Example:

C:\Monitored
│
├── file1.txt
├── file2.pdf
│
├── Documents
│   ├── report.docx
│   └── notes.txt
│
└── Config
    └── settings.ini
All files should be included by default.

8.1 Directories
Directories themselves do not need cryptographic hashes for the MVP.

Only files need to be recorded.

8.2 Symbolic Links
The MVP should avoid recursively following symbolic links unless explicitly determined to be safe.

Document the chosen behavior.

8.3 Permission Errors
Permission errors must not terminate the entire scan.

9. Baseline Creation
When the user selects:

Create Baseline
the application should:

Confirm the selected directory.
Warn that creating a new baseline replaces the monitoring reference.
Enumerate files.
Hash each file.
Save the baseline.
Display:
Number of files
Creation time
Directory
Baseline status
Example:

Baseline Created

Directory:
C:\Users\User\Documents

Files:
1,284

Created:
August 26, 2026 12:31 AM

Status:
✓ Baseline Ready
The UI should prevent accidental replacement.

10. Scan Algorithm
The scan algorithm should follow this logical process:

Load baseline
      ↓
Enumerate current files
      ↓
Hash current files
      ↓
Compare file paths
      ↓
Compare hashes
      ↓
Generate results
10.1 New File
Current file exists but baseline does not.

CURRENT = YES
BASELINE = NO

→ NEW
10.2 Deleted File
Baseline contains file but current filesystem does not.

CURRENT = NO
BASELINE = YES

→ DELETED
10.3 Modified File
Both exist but SHA-256 hashes differ.

CURRENT = YES
BASELINE = YES
HASHES DIFFER

→ MODIFIED
10.4 Unchanged File
Both exist and hashes match.

CURRENT = YES
BASELINE = YES
HASHES MATCH

→ UNCHANGED
11. GUI Requirements
Use CustomTkinter unless a compelling technical reason requires another framework.

11.1 Design Goals
The GUI should be:

Clean
Modern
Minimal
Readable
Beginner-friendly
Responsive during scans
Do not create a complicated enterprise dashboard.

11.2 Main Window
The main window should contain:

Header
SentinelLite
File Integrity Monitor
Monitored Directory
Display:

Monitored Folder

C:\Users\User\Documents

[ Change Folder ]
Baseline Section
Display:

Baseline

Status: Ready
Created: Aug 26, 2026
Files: 1,284

[ Create Baseline ]
Scan Section
Last Scan:
Aug 26, 2026 12:45 AM

[ Scan Now ]
Security Status
Use a prominent status indicator:

✓ NO CHANGES DETECTED
or:

⚠ CHANGES DETECTED
or:

✕ SCAN ERROR
Avoid claiming that the system is "secure" merely because no file changes were detected.

The application only knows:

No changes were detected relative to the baseline.

12. Results View
The results screen should provide summary counts:

SCAN RESULTS

Modified:    3
New:         7
Deleted:     1
Unchanged:   1,273
Errors:      0
Then provide a sortable/filterable table.

Columns:

Status
File
Baseline Hash
Current Hash
Size
Timestamp
The table should allow filtering by:

All
Modified
New
Deleted
Unchanged
Errors
13. Progress Handling
Scanning potentially large directories may take time.

The GUI must remain responsive.

Do not perform a large filesystem scan directly on the GUI event loop.

Use a background worker/thread.

Display:

Scanning...

Files processed:
742 / 1,284

██████████████░░░░░░

Current file:
Documents/report.pdf
The exact progress calculation may be approximate if necessary.

The application must never appear frozen during normal scanning.

14. Storage
SQLite is preferred for scan history.

The application may use:

sentinellite.db
Recommended tables:

baselines
id
created_at
root_directory
application_version
baseline_files
id
baseline_id
relative_path
sha256
size
modified_time
scans
id
baseline_id
started_at
completed_at
modified_count
new_count
deleted_count
unchanged_count
error_count
scan_results
id
scan_id
relative_path
status
baseline_hash
current_hash
size
error_message
The database should remain local.

No external database server is required.

15. Report Export
15.1 CSV
CSV output should contain:

status,path,baseline_hash,current_hash,size,timestamp
15.2 JSON
JSON output should contain:

{
    "scan_id": 1,
    "timestamp": "...",
    "root_directory": "...",
    "summary": {
        "modified": 3,
        "new": 7,
        "deleted": 1,
        "unchanged": 1273,
        "errors": 0
    },
    "results": []
}
16. Logging
Application logs should be written locally.

Recommended:

logs/sentinellite.log
Log:

Application startup
Baseline creation
Scan start
Scan completion
Errors
Database errors
Filesystem permission errors
Export operations
Do not log sensitive file contents.

Do not log file contents merely for debugging.

17. Security Requirements
17.1 Hash Integrity
SHA-256 must be used consistently.

17.2 Baseline Protection
The baseline is the trust reference.

The application should make it clear that:

If an attacker can modify both the monitored files and the baseline database, file integrity monitoring may be defeated.

This limitation should be documented.

17.3 No Automatic Remediation
The application must never automatically:

Delete files
Quarantine files
Modify files
Restore files
Detection only.

17.4 No Network Requirement
The MVP should function completely offline.

No telemetry.

No external APIs.

No network connection should be required.

18. Error Handling
Errors must be user-friendly.

Avoid displaying raw Python tracebacks to normal users.

Instead:

Unable to read file

The application could not access:

C:\Example\file.txt

The scan will continue with the remaining files.
Technical details should be available in the log.

19. Testing Requirements
Use pytest.

Minimum test coverage should include:

Hashing
Same file produces same hash.
Modified file produces different hash.
Empty file can be hashed.
Large file can be hashed.
Baseline
Baseline can be created.
Baseline can be saved.
Baseline can be loaded.
Missing baseline is handled.
Corrupted baseline is handled.
Scanner
Test:

UNCHANGED
NEW
DELETED
MODIFIED
ERROR
Example test scenario:

Initial:
A.txt
B.txt
C.txt
Modify:

A.txt → modified
B.txt → deleted
C.txt → unchanged
D.txt → new
Expected:

A.txt → MODIFIED
B.txt → DELETED
C.txt → UNCHANGED
D.txt → NEW
Reports
Verify:

CSV generation
JSON generation
Correct summary counts
Correct file paths
Valid JSON syntax
20. Scheduled Scanning
Scheduled scanning is optional if implementation time becomes constrained.

If implemented in the MVP, prefer Windows Task Scheduler integration rather than building a custom scheduling daemon.

The GUI may provide:

Scheduled Scans

[ ] Enable scheduled scanning

Frequency:
[ Daily ▼ ]

Time:
[ 02:00 AM ]

[ Save Schedule ]
However, this feature must not compromise the core application.

If Run 6 cannot implement it reliably, defer it.

21. Packaging
Use PyInstaller.

Preferred command:

pyinstaller --noconfirm --windowed --name SentinelLite app.py
The final output should be:

dist/
└── SentinelLite/
    └── SentinelLite.exe
A single-file executable may be attempted:

pyinstaller --noconfirm --windowed --onefile --name SentinelLite app.py
but reliability is more important than achieving a single executable.

The build process must be documented in:

README.md
22. Application Data Location
Do not store mutable application data inside the installation directory if running as a packaged application.

Prefer a user-writable application data directory such as:

%LOCALAPPDATA%\SentinelLite\
Suggested:

%LOCALAPPDATA%\SentinelLite\
│
├── sentinellite.db
├── logs\
└── exports\
The exact implementation should use Windows-appropriate paths.

23. UX Requirements
The application should assume the user is not a cybersecurity expert.

Avoid unnecessary terminology.

Instead of:

Cryptographic Integrity Differential Analysis
use:

File Changes
Instead of:

Baseline Differential
use:

Compare With Baseline
Instead of:

Integrity Violation
use:

File Changed
Provide tooltips or short explanations for security concepts where useful.

24. Application States
The application should explicitly handle:

No folder selected
Select a folder to begin.
Folder selected, no baseline
No baseline exists.

Create a baseline before scanning.
Baseline exists
Baseline Ready
Scan running
Scanning...
Scan completed, no changes
✓ No Changes Detected
Scan completed, changes found
⚠ Changes Detected
Scan completed with errors
⚠ Scan Completed With Errors
Fatal application error
The application encountered an unexpected error.

Check the application log for details.
25. One-Week Development Schedule
The development process consists of seven scheduled runs.

Each run must:

Inspect the current repository.
Read PROJECT_SPEC.md.
Inspect work completed by previous runs.
Implement only the current run's objectives.
Run tests.
Fix failures introduced by the current run.
Update documentation if necessary.
Leave the repository in a working state.
Provide a concise completion summary.
Do not assume previous work was completed correctly. Verify it.

26. Run 1 — Foundation
Objectives
Create the project foundation.

Implement:

Repository structure
Python environment
Dependency file
Configuration system
Logging system
Basic application entry point
Basic CustomTkinter window
Application metadata
Git-friendly project structure
Create:

app.py
config.py
requirements.txt
README.md
and required directories.

Acceptance Criteria
Application launches.
Main window appears.
No filesystem scanning yet.
Logging works.
Dependencies are documented.
Basic test infrastructure works.
Run:

pytest
27. Run 2 — Hashing and Filesystem Engine
Objectives
Implement:

Recursive file enumeration
SHA-256 hashing
Chunked file reads
File metadata collection
Permission error handling
Create:

core/hasher.py
core/filesystem.py
core/models.py
Acceptance Criteria
The core engine can:

Enumerate a directory.
Hash every readable file.
Produce FileRecord objects.
Continue after inaccessible files.
Pass hashing tests.
No GUI integration is required beyond basic scaffolding.

28. Run 3 — Baseline System
Objectives
Implement:

Baseline creation
Baseline serialization/storage
Baseline loading
Baseline metadata
Database layer if SQLite is selected
Baseline validation
Create:

core/baseline.py
storage/database.py
storage/repository.py
Acceptance Criteria
A test can:

Create directory
    ↓
Create files
    ↓
Create baseline
    ↓
Modify filesystem
    ↓
Reload baseline
and the baseline remains unchanged.

29. Run 4 — Comparison and Scan Engine
Objectives
Implement:

Scan engine
Baseline comparison
New detection
Deleted detection
Modified detection
Unchanged detection
Error handling
Scan history
Create:

core/scanner.py
Acceptance Criteria
Given:

A = modified
B = deleted
C = unchanged
D = new
the scanner produces exactly:

A → MODIFIED
B → DELETED
C → UNCHANGED
D → NEW
All tests pass.

30. Run 5 — GUI Integration
Objectives
Connect the core system to the GUI.

Implement:

Folder picker
Baseline creation
Scan Now
Progress display
Status display
Summary statistics
Results table
Filtering
Background scan thread
Acceptance Criteria
A user can perform the entire workflow through the GUI:

Launch
  ↓
Select folder
  ↓
Create baseline
  ↓
Change a file
  ↓
Scan
  ↓
View MODIFIED result
The GUI must remain responsive during scanning.

31. Run 6 — Reporting and Optional Scheduling
Objectives
Implement:

CSV export
JSON export
Scan history UI
User-friendly error dialogs
Improved logging
Optional Windows scheduled scanning
Priority order:

1. Reporting
2. Error handling
3. Logging
4. Scheduling
If scheduling threatens MVP stability, omit it and document it as a future feature.

Acceptance Criteria
The user can:

Scan
 ↓
View results
 ↓
Export CSV
 ↓
Export JSON
and exported files contain accurate results.

32. Run 7 — QA and Packaging
Objectives
Perform final:

Unit tests
Integration tests
GUI testing
Error-condition testing
Packaging
Documentation
UI polish
Build verification
Create/finalize:

build_exe.bat
README.md
PROJECT_SPEC.md
Build:

SentinelLite.exe
Acceptance Criteria
The final application must:

Launch on Windows.
Allow folder selection.
Create a baseline.
Scan a folder.
Detect modifications.
Detect new files.
Detect deleted files.
Display results.
Export results.
Handle errors without crashing.
Produce useful logs.
Have no known critical bugs.
33. Final Acceptance Test
Perform this exact end-to-end test before declaring the MVP complete.

Create:

TestFolder\
├── unchanged.txt
├── modified.txt
└── deleted.txt
Create a baseline.

Then:

Leave unchanged.txt untouched.
Modify modified.txt.
Delete deleted.txt.
Create new.txt.
Run a scan.
Expected:

UNCHANGED   unchanged.txt
MODIFIED    modified.txt
DELETED     deleted.txt
NEW         new.txt
Summary must equal:

Modified:   1
New:        1
Deleted:    1
Unchanged:  1
Errors:     0
Export the results to CSV and JSON.

Verify both files.

34. Performance Expectations
The MVP does not need enterprise-level performance.

However:

Files must be hashed incrementally.
GUI must remain responsive.
Scans should not unnecessarily duplicate work.
Database writes should be reasonably efficient.
Large files should not cause excessive memory usage.
Do not prematurely optimize.

Correctness takes priority over performance.

35. Code Quality Requirements
Code should be:

Typed where practical
Modular
Readable
PEP 8 compliant
Documented where behavior is non-obvious
Testable independently of the GUI
Avoid:

Giant functions
Global mutable state
Hard-coded Windows paths
GUI logic inside security modules
Duplicate hashing implementations
Silent exception handling
Use type hints.

Example:

def calculate_sha256(
    file_path: Path,
    chunk_size: int = 1024 * 1024
) -> str:
    ...
36. Logging and Debugging Policy
When debugging:

Reproduce the issue.
Identify the smallest affected component.
Add a regression test where appropriate.
Fix the underlying issue.
Run the complete test suite.
Do not simply suppress errors to make tests pass.

Do not remove security checks to simplify implementation.

37. Claude Code Operating Instructions
Every scheduled run must begin by reading:

PROJECT_SPEC.md
Then determine:

CURRENT RUN
↓
Required objectives
↓
Existing implementation
↓
Missing implementation
↓
Tests
↓
Implementation
↓
Validation
The agent must not redesign the entire application during an individual run.

Implement the smallest reasonable change that satisfies the current run.

If a requirement is ambiguous:

Prefer the simplest implementation.
Preserve the existing architecture.
Do not expand scope.
Document the decision.
If an existing implementation conflicts with this specification:

Do not blindly rewrite it.
Determine whether the existing implementation is functionally correct.
Preserve working code where possible.
Correct deviations that materially affect MVP requirements.
38. Scope Control Rule
The following rule is critical:

A feature is not part of the MVP merely because it would make SentinelLite more powerful.

Before implementing any additional feature, ask:

Is it explicitly required by PROJECT_SPEC.md?
If the answer is no:

DEFER
Record potentially useful ideas under:

Future Enhancements
Do not implement them during the MVP week.

39. Future Enhancements
Potential post-MVP features include:

Real-time filesystem monitoring
Windows service mode
Email alerts
Desktop notifications
File exclusion rules
Multiple monitored folders
Baseline signing
Encrypted baseline storage
Remote baseline storage
Network monitoring
SIEM integration
Threat intelligence
YARA integration
Malware scanning
Windows Event Log integration
Advanced anomaly detection
Role-based access control
Enterprise deployment
These are explicitly deferred.

40. Definition of Done
The SentinelLite MVP is complete when:

[✓] Application launches
[✓] User can select a directory
[✓] User can create a baseline
[✓] SHA-256 hashes are generated
[✓] Baseline is persisted
[✓] User can run a scan
[✓] Modified files are detected
[✓] New files are detected
[✓] Deleted files are detected
[✓] Unchanged files are detected
[✓] Errors are handled
[✓] GUI remains responsive
[✓] Results are displayed
[✓] CSV export works
[✓] JSON export works
[✓] Logs work
[✓] Tests pass
[✓] Windows executable builds
[✓] End-to-end acceptance test passes
[✓] README is complete
The MVP should not be considered incomplete simply because deferred features have not been implemented.

41. Final Product Goal
The finished SentinelLite application should feel like a small, legitimate cybersecurity utility rather than a programming demonstration.

A new user should be able to launch the .exe and understand the workflow immediately:

SELECT FOLDER
      ↓
CREATE BASELINE
      ↓
SCAN
      ↓
SEE WHAT CHANGED
      ↓
EXPORT REPORT
The underlying implementation should demonstrate sound cybersecurity fundamentals while remaining simple enough to build, test, and package within one week.

Primary objective:

Build a reliable, user-friendly file integrity monitoring MVP that demonstrates practical cybersecurity engineering without expanding beyond the one-week scope.