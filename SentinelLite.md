SentinelLite
Technical Specification — MVP
Document: PROJECT_SPEC.md
Version: 1.0.0
Project Type: Windows desktop cybersecurity utility
Primary Language: Python 3.12+
Target Output: Standalone Windows .exe
Development Model: 7 scheduled Claude Code runs over 1 week

Development Progress: Run 1 — Foundation complete (2026-09-02). Run 2 — Hashing and Filesystem Engine complete (2026-09-04). See status/status_2026-09-02.md and status/status_2026-09-04.md. Runs 3-7 not yet started.

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