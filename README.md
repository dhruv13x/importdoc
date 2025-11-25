<div align="center">
  <img src="https://raw.githubusercontent.com/dhruv13x/importdoc/main/importdoc_logo.png" alt="importdoc logo" width="200"/>
</div>

<div align="center">

<!-- Package Info -->
[![PyPI version](https://img.shields.io/pypi/v/importdoc.svg)](https://pypi.org/project/importdoc/)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
![Wheel](https://img.shields.io/pypi/wheel/importdoc.svg)
[![Release](https://img.shields.io/badge/release-PyPI-blue)](https://pypi.org/project/importdoc/)

<!-- Build & Quality -->
[![Build status](https://github.com/dhruv13x/importdoc/actions/workflows/publish.yml/badge.svg)](https://github.com/dhruv13x/importdoc/actions/workflows/publish.yml)
[![Codecov](https://codecov.io/gh/dhruv13x/importdoc/graph/badge.svg)](https://codecov.io/gh/dhruv13x/importdoc)
[![Test Coverage](https://img.shields.io/badge/coverage-90%25%2B-brightgreen.svg)](https://github.com/dhruv13x/importdoc/actions/workflows/test.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/badge/linting-ruff-yellow.svg)](https://github.com/astral-sh/ruff)
![Security](https://img.shields.io/badge/security-CodeQL-blue.svg)

<!-- Usage -->
![Downloads](https://img.shields.io/pypi/dm/importdoc.svg)
![OS](https://img.shields.io/badge/os-Linux%20%7C%20macOS%20%7C%20Windows-blue.svg)
[![Python Versions](https://img.shields.io/pypi/pyversions/importdoc.svg)](https://pypi.org/project/importdoc/)

<!-- License -->
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<!-- Docs -->
[![Docs](https://img.shields.io/badge/docs-latest-brightgreen.svg)](https://your-docs-link)

</div>


# importdoc

> **Production-Ready Import Diagnostic Tool for Python**
A hardened diagnostic tool for deep, automated import analysis in Python projects. It features subprocess-safe imports, circular dependency detection, auto-fix suggestions, AST-based symbol resolution, and CI-ready JSON output.

---

## 🚀 Quick Start (User View):

### Prerequisites
- Python 3.10+
- `jsonschema`
- `tqdm`
- `rich`

### One-Command Installation

```bash
pip install importdoc
```

### Usage Example

```bash
importdoc your_package
```

## ✨ Key Features

- 🔍 **Import graph discovery**: Recursively maps and validates imports across a project.
- 🧠 **AST-based analysis**: Detects missing imports, wrong module paths, and unresolved symbols.
- ⚡ **Subprocess safe imports**: Imports each module in a sandboxed subprocess, making it timeout-safe.
- 🛑 **Circular import detection**: Identifies dependency cycles with detailed stack traces.
- 🛠️ **Automated fix suggestions**: Suggests proper import paths and generates JSON patches for auto-fixing.
- 📊 **JSON diagnostic mode**: Provides CI-friendly structured reports for easy integration.
- 📦 **Cache & telemetry**: Includes an optional cache and performance metrics to speed up subsequent runs.
- 🛡️ **Safe mode**: Avoids dangerous imports outside the virtual environment by default.
- 📈 **Graph export**: Generates a DOT dependency graph for visualization with Graphviz.
- **Enhanced `no module named` diagnosis**: **God Level** Parses import symbols from the AST to suggest correct paths based on symbol definitions, providing more accurate and actionable insights.


---

🧪 Example Output (Success)

🎉 ALL MODULES IMPORTED SUCCESSFULLY!
✨ Production-ready: No import issues detected

🚨 Example Output (Import Error)

🚨 FAILED TO IMPORT: myapp.models.user
🔥 ROOT CAUSE: ImportError: cannot import name 'Profile' from 'myapp.profile'
📊 Evidence:
  - myapp/profile.py:15: class Profile
💡 Suggested Fixes:
  1. from myapp.profile import Profile
🧠 Confidence: 9/10


---

⚙️ Configuration & Advanced Usage (Dev View)

### CLI/API Table

| Argument | Description | Default |
|---|---|---|
| `package` | The root package to diagnose. | N/A |
| `--dir` | The directory of the package, which adds the parent to `sys.path`. | N/A |
| `--continue-on-error` | Continues the diagnosis even after encountering errors. | `False` |
| `--dry-run` | Discovers modules without actually importing them. | `False` |
| `--max-depth` | The maximum depth for module discovery. | N/A |
| `--log-file` | The path to the log file. | N/A |
| `--verbose` | Enables detailed and extensive output. | `False` |
| `--quiet` | Minimizes the output to only essential information. | `False` |
| `--no-emoji` | Disables the use of emojis in the output. | `False` |
| `--timeout` | The timeout in seconds for each import. | `0` |
| `--unload` | Unloads modules after they are imported. | `False` |
| `--json` | Outputs the diagnosis in JSON format. | `False` |
| `--parallel` | The number of parallel imports to run. | `0` |
| `--dev-mode` | Enables developer mode for additional diagnostics. | `False` |
| `--dev-trace` | Traces the import chains for debugging. | `False` |
| `--graph` | Generates a DOT graph of the import dependencies. | `False` |
| `--dot-file` | The path to the output DOT file. | N/A |
| `--allow-root` | Allows the tool to be run as the root user. | `False` |
| `--show-env` | Shows the environment variables at the start. | `False` |
| `--enable-telemetry` | Enables production telemetry for performance tracking. | `False` |
| `--enable-cache` | Enables caching of results to speed up subsequent runs. | `False` |
| `--generate-fixes` | Generates automated fixes for import errors. | `False` |
| `--fix-output` | The output file for the automated fixes in JSON format. | N/A |
| `--no-safe-mode` | Disables safe mode, allowing imports from outside the virtual environment. | `False` |
| `--no-safe-skip` | Does not auto-skip imports when not in a virtual environment with safe mode active. | `False` |
| `--max-scan-results` | The maximum number of results for repository scans. | `200` |
| `--version` | Shows the version of the tool. | N/A |

> **Note**: For a full list of options, run `importdoc --help`.

---

### 🏗️ Architecture

```
importdoc/
├── src/
│   └── importdoc/
│       ├── __init__.py
│       ├── cli.py         # CLI entry point and argument parsing
│       └── modules/
│           ├── diagnostics.py # Core diagnostic logic
│           └── ...        # Other utility modules
└── pyproject.toml     # Project metadata and dependencies
```

The core logic resides in `src/importdoc/modules/diagnostics.py`, which is responsible for import analysis, subprocess management, and report generation. The CLI entry point, `src/importdoc/cli.py`, handles argument parsing and initializes the diagnostic process.

---

### 🗺️ Roadmap

- **Completed**:
  - [x] Subprocess-safe imports
  - [x] Circular dependency detection
  - [x] AST-based symbol resolution
  - [x] Automated fix suggestions
  - [x] CI-ready JSON output

- **Upcoming**:
  - [ ] Interactive HTML reports
  - [ ] Plugin architecture for custom checks
  - [ ] Deeper integration with IDEs

---

🛡️ CI/CD Usage

GitHub Actions

- name: Run import diagnostics
  run: importdoc mypkg --json --continue-on-error > import_report.json


---

🧠 When to Use importdoc

Situation	importdoc saves you

❓ Random import failures	✅ Pinpoints real source
🔁 Circular imports	✅ Finds cycles with stack trace
⚙️ Large refactors	✅ Detects broken import paths
🤖 CI safety	✅ Reports without executing package runtime logic
📦 Package release testing	✅ Ensures import reliability



---

🧩 Project Structure Example

yourproject/
 ├─ src/
 │   └─ yourpackage/
 │       ├─ __init__.py
 │       ├─ ...
 └─ tests/

Run:

importdoc yourpackage --dir ./src


---

### 🤝 Contributing & License

Contributions are welcome! Please feel free to submit a pull request or open an issue.

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

⭐ Support

If you find this tool useful:

pip install importdoc

And give the repo a ⭐ on GitHub!

https://github.com/dhruv13x/importdoc
