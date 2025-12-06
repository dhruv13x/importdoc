<div align="center">
  <img src="https://raw.githubusercontent.com/dhruv13x/importdoc/main/importdoc_logo.png" alt="importdoc logo" width="200"/>
</div>

<div align="center">

<!-- Package Info -->
[![PyPI version](https://img.shields.io/pypi/v/importdoc.svg)](https://pypi.org/project/importdoc/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
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
[![Docs](https://img.shields.io/badge/docs-latest-brightgreen.svg)](https://pypi.org/project/importdoc)

</div>

# importdoc

> **Production-Ready Import Diagnostic Tool for Python**
>
> A hardened diagnostic tool for deep, automated import analysis in Python projects. It features subprocess-safe imports, circular dependency detection, auto-fix suggestions, AST-based symbol resolution, and CI-ready JSON output.

---

## 🚀 Quick Start (User View)

### Prerequisites

- Python 3.10+
- `jsonschema`
- `tqdm`
- `rich`
- `tomli` (for Python < 3.11)

### One-Command Installation

```bash
pip install importdoc
```

### Usage Example

```bash
importdoc your_package
```

---

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
- 📊 **Interactive HTML Reports**: Generates self-contained HTML reports for exploring import graphs interactively.
- ⚙️ **Configuration File Support**: Reads settings from `pyproject.toml` or `.importdoc.rc` for easy configuration management.
- **Enhanced `no module named` diagnosis**: **God Level** Parses import symbols from the AST to suggest correct paths based on symbol definitions, providing more accurate and actionable insights.
- 🕵️ **Fuzzy module search**: **God Level** Enhanced search for missing modules and incomplete import detection.
- 🔌 **Plugin Architecture**: Support for custom plugins to extend functionality and implement custom checks.

---

## ⚙️ Configuration & Advanced Usage (Dev View)

### Environment Variables

You can configure `importdoc` behavior using standard environment variables for the underlying tools or shell environment.

### CLI/API Table

| Argument | Description | Default |
| :--- | :--- | :--- |
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
| `--no-safe-skip` | Do not auto-skip imports if not in venv when safe mode active. | `False` |
| `--max-scan-results` | Max results for repo scans (defs/usages/fuzzy). | `200` |
| `--html` | Generates an interactive HTML report of the import graph. | `False` |
| `--version` | Shows the version of the tool. | N/A |

> **Note**: For a full list of options, run `importdoc --help`.

---

## 🏗️ Architecture

```text
importdoc/
├── src/
│   └── importdoc/
│       ├── __init__.py
│       ├── banner.py
│       ├── cli.py             # CLI entry point and argument parsing
│       └── modules/
│           ├── __init__.py
│           ├── analysis.py    # AST analysis logic
│           ├── autofix.py     # Fix generation logic
│           ├── cache.py       # Caching mechanism
│           ├── config.py      # Configuration management
│           ├── diagnostics.py # Core diagnostic controller
│           ├── discovery.py   # Module discovery
│           ├── plugin.py      # Plugin architecture
│           ├── processor.py   # Result processing
│           ├── reporting.py   # Report generation (Text/JSON/HTML)
│           └── ...            # Other utility modules
├── pyproject.toml             # Project metadata and dependencies
└── README.md
```

The core logic resides in `src/importdoc/modules/diagnostics.py`, which is responsible for import analysis, subprocess management, and report generation. The CLI entry point, `src/importdoc/cli.py`, handles argument parsing and initializes the diagnostic process.

---

## 🗺️ Roadmap

> A visionary, integration-oriented plan that categorizes features from **"Core Essentials"** to **"God Level"** ambition.

### Phase 1: Foundation (Q1)
**Focus**: Core functionality, stability, security, and basic usage.
- [x] Subprocess-safe imports
- [x] Circular dependency detection
- [x] AST-based symbol resolution
- [x] CI-ready JSON output
- [x] Enhanced error reporting for common import issues
- [ ] Official support for Python 3.11 and 3.12
- [ ] Comprehensive test suite with 95%+ coverage

### Phase 2: The Standard (Q2)
**Focus**: Feature parity with top competitors, user experience improvements, and robust error handling.
- [x] Interactive HTML reports for visualizing import graphs
- [x] Configuration file support (e.g., `pyproject.toml`)
- [x] Caching of analysis results to speed up subsequent runs
- [ ] Performance optimization for large codebases

### Phase 3: The Ecosystem (Q3-Q4)
**Focus**: Webhooks, API exposure, 3rd party plugins, SDK generation, and extensibility.
- [x] Plugin architecture for custom checks and reporters
- [ ] IDE integration (VS Code, PyCharm) for real-time import diagnostics
- [ ] GitHub Actions integration for automated PR comments
- [ ] Pre-commit hook integration

### Phase 4: The Vision (GOD LEVEL)
**Focus**: "Futuristic" features, AI integration, advanced automation, and industry-disrupting capabilities.
- [ ] AI-powered suggestions for refactoring complex import cycles
- [ ] Predictive dependency analysis to identify potential future conflicts
- [ ] Automated refactoring of import statements across the entire codebase

### The Sandbox (OUT OF THE BOX / OPTIONAL)
**Focus**: Wild, creative, experimental ideas that set the project apart.
- [ ] "Import cost" analysis to identify heavy dependencies
- [ ] Integration with runtime profilers to connect import structure to performance
- [ ] Gamification of code health with import-related achievements

---

## 🤝 Contributing & License

Contributions are welcome! Please feel free to submit a pull request or open an issue.

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

### ⭐ Support

If you find this tool useful:

```bash
pip install importdoc
```

And give the repo a ⭐ on GitHub!

[https://github.com/dhruv13x/importdoc](https://github.com/dhruv13x/importdoc)
