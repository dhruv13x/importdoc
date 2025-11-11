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
