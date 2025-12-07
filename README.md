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
> Advanced Python import diagnostic tool with deep analysis, subprocess isolation, auto-fixing suggestions, and CI-ready enforcement.

---

## ⚡ Quick Start (The "5-Minute Rule")

### Prerequisites
- **Python**: 3.10+
- **Dependencies**: `jsonschema`, `tqdm`, `rich` (installed automatically)

### Install
```bash
pip install importdoc
```

### Run
To start diagnosing your package immediately:
```bash
importdoc <your_package_name>
```

### Demo
Copy and paste this snippet to audit your package and generate a visual report:

```bash
# Install importdoc
pip install importdoc

# Run a full diagnostic check with verbose output
importdoc my_awesome_package --verbose

# Generate an interactive HTML graph of your import structure
importdoc my_awesome_package --html
```

---

## ✨ Features

### Core Capabilities
- **Import Graph Discovery**: Recursively maps and validates imports across your entire project.
- **Subprocess Isolation**: Imports each module in a sandboxed subprocess to prevent crashes and ensure timeout safety.
- **Circular Dependency Detection**: Identifies dependency cycles with detailed stack traces.

### Performance & Security
- **Smart Caching**: Speeds up subsequent runs by caching analysis results (`--enable-cache`).
- **Parallel Execution**: runs imports in parallel for large codebases (`--parallel`).
- **Safe Mode**: Enforces execution within a virtual environment to prevent system pollution.

### Advanced Analysis
- **Auto-Fix Suggestions**: Suggests proper import paths and generates JSON patches for auto-fixing errors.
- **AST-Based Resolution**: "God Level" analysis parses source code to find undefined symbols and correct import paths.
- **Interactive Reports**: Generates self-contained HTML reports for exploring import graphs visually.
- **CI-Ready JSON**: Provides structured JSON output for easy integration with CI/CD pipelines.

---

## 🛠️ Configuration

You can configure `importdoc` using CLI arguments or a configuration file (`pyproject.toml` or `.importdoc.rc`).

### CLI Arguments

| Argument | Description | Default |
| :--- | :--- | :--- |
| `package` | The root package to diagnose. | Required |
| `--dir` | The directory of the package (adds parent to `sys.path`). | `None` |
| `--config` | Path to config file (implicit: `pyproject.toml` or `.importdoc.rc`). | Auto |
| `--verbose` | Enables detailed and extensive output. | `False` |
| `--json` | Outputs the diagnosis in JSON format. | `False` |
| `--html` | Generates an interactive HTML report. | `False` |
| `--graph` | Generates a DOT graph of import dependencies. | `False` |
| `--dot-file` | Path to the output DOT file. | `None` |
| `--timeout` | Timeout in seconds for each import. | `0` (None) |
| `--parallel` | Number of parallel imports to run. | `0` (Sequential) |
| `--enable-cache` | Enables caching of results. | `False` |
| `--generate-fixes` | Generates automated fixes for import errors. | `False` |
| `--fix-output` | Output file for automated fixes (JSON). | `None` |
| `--continue-on-error`| Continues diagnosis even after encountering errors. | `False` |
| `--dry-run` | Discovers modules without actually importing them. | `False` |
| `--dev-mode` | Enables developer mode for additional diagnostics. | `False` |

### Configuration File (`pyproject.toml`)

You can persist your configuration in `pyproject.toml` under the `[tool.importdoc]` section:

```toml
[tool.importdoc]
verbose = true
timeout = 5
enable_cache = true
exclude_patterns = ["tests/*", "migrations/*"]
```

---

## 🏗️ Architecture

### Directory Tree

```text
src/
└── importdoc/
    ├── cli.py             # CLI Entry Point
    ├── banner.py          # Logo & Branding
    └── modules/
        ├── diagnostics.py # Core Controller (Orchestrator)
        ├── discovery.py   # File & Module Discovery
        ├── runner.py      # Subprocess Execution Logic
        ├── analysis.py    # AST & Error Analysis
        ├── reporting.py   # JSON/HTML/Console Output
        ├── config.py      # Configuration Loader
        ├── cache.py       # Caching Mechanism
        ├── autofix.py     # Fix Generation Logic
        └── ...
```

### High-Level Flow

1.  **CLI**: Parses arguments and loads configuration.
2.  **Discovery**: Scans the file system to find all Python modules in the target package.
3.  **Runner**: Iterates through discovered modules, spawning isolated subprocesses to import them safely.
4.  **Analysis**: Captures stdout/stderr from subprocesses. If an import fails, `analysis.py` inspects the error and AST to determine the root cause (e.g., circular dependency, missing symbol).
5.  **Reporting**: Aggregates results and outputs them to the console, JSON file, or HTML report.

---

## 🐞 Troubleshooting

### Common Issues

| Error Message | Possible Cause | Solution |
| :--- | :--- | :--- |
| `ModuleNotFoundError` | The package root is not in `sys.path`. | Use the `--dir` argument to specify the package location. |
| `ImportError: cannot import name...` | Circular dependency or wrong path. | Run with `--graph` to visualize cycles or `--generate-fixes` to see suggestions. |
| `TimeoutError` | Module takes too long to import. | Increase the timeout using `--timeout <seconds>`. |
| `PermissionError` | Running as root (not recommended). | Use `--allow-root` if absolutely necessary. |

### Debug Mode

If you are facing unexpected behavior, enable verbose logging and developer traces:

```bash
importdoc my_package --verbose --dev-mode --dev-trace
```

---

## 🤝 Contributing

We welcome contributions! Please check out our [CONTRIBUTING.md](CONTRIBUTING.md) (if available) or follow the steps below.

### Dev Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/dhruv13x/importdoc.git
    cd importdoc
    ```

2.  **Install dependencies**:
    ```bash
    pip install .[dev]
    ```

3.  **Run Tests**:
    ```bash
    python -m pytest
    ```

---

## 🗺️ Roadmap

We are constantly improving `importdoc`. Here is a glimpse of what's coming:

-   **Phase 1 (Done)**: Subprocess isolation, Circular dependency detection, JSON/HTML output.
-   **Phase 2 (Current)**: Performance optimization (Caching, Parallelism), Configuration files.
-   **Phase 3 (Next)**: Plugin architecture, IDE integrations (VS Code), GitHub Actions support.
-   **Phase 4 (Vision)**: AI-powered architectural refactoring and predictive dependency analysis.

See [ROADMAP.md](ROADMAP.md) for the full detailed plan.
