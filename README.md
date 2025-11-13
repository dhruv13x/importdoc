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

> **Advanced Import Diagnostic Tool for Python**  
Deep, automated import analysis for Python projects — with subprocess-safe imports, circular dependency detection, auto-fix suggestions, AST-based symbol resolution, and CI-ready JSON output.

---

## 🚀 Features

| Capability | Description |
|----------|-------------|
🔍 **Import graph discovery** | Recursively maps and validates imports across a project  
🧠 **AST-based analysis** | Detects missing imports, wrong module paths, and unresolved symbols  
⚡ **Subprocess safe imports** | Imports each module in a sandboxed subprocess (timeout safe)  
🛑 **Circular import detection** | Identifies dependency cycles with stack traces  
🛠️ **Automated fix suggestions** | Suggest proper import paths + generate JSON patches  
📊 **JSON diagnostic mode** | CI-friendly structured reports  
📦 **Cache & telemetry** | Optional cache + performance metrics  
🛡️ **Safe mode** | Avoids dangerous imports outside venv by default  
📈 **Graph export** | DOT dependency graph generation (Graphviz)  

---

## 📦 Installation

### PyPI

```bash
pip install importdoc

Development (editable)

pip uninstall importdoc -y
pip install -e .


---

🔧 CLI Usage

Basic usage

importdoc your_package

Running in a project dir

importdoc your_package --dir .

Allow root (CI / Docker)

importdoc your_package --allow-root

Enable full diagnostics

importdoc your_package --verbose --enable-cache --enable-telemetry

JSON output (CI pipelines)

importdoc your_package --json > import_report.json

Auto-fix suggestions

importdoc your_package --generate-fixes --fix-output fixes.json

Dependency graph (Graphviz)

importdoc your_package --graph --dot-file imports.dot
dot -Tpng imports.dot -o graph.png


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

⚙️ Options Summary

Flag	Purpose

--continue-on-error	Never stop on failures
--parallel N	Parallel subprocess imports
--json	JSON report mode
--graph	Create DOT graph
--no-safe-mode	Allow global environment imports
--enable-cache	Speed up repeated runs
--dev-trace	Debug import chain tracing


Run full help:

importdoc --help


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

🤝 Contributing

PRs & issues welcome!


---

📄 License

MIT © 2025


---

⭐ Support

If you find this tool useful:

pip install importdoc

And give the repo a ⭐ on GitHub!

https://github.com/dhruv13x/importdoc
