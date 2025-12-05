# 🗺️ importdoc Roadmap

> A visionary, integration-oriented plan that categorizes features from **"Core Essentials"** to **"God Level"** ambition.

---

## Phase 1: Foundation (CRITICALLY MUST HAVE)

**Focus**: Core functionality, stability, security, and basic usage.

- [x] **Subprocess-safe imports**: Isolate imports in subprocesses to prevent crashes and handle timeouts.
- [x] **Circular dependency detection**: Identify and report dependency cycles with stack traces.
- [x] **AST-based symbol resolution**: Analyze source code to find undefined symbols and correct import paths.
- [x] **CI-ready JSON output**: Structured output for integration with CI/CD pipelines.
- [x] **Enhanced error reporting**: "Human-readable" diagnosis for `ImportError`, `ModuleNotFoundError`, and `AttributeError`.
- [x] **Safe Mode**: Enforce execution within a virtual environment to prevent system pollution.
- [ ] **Official Python 3.11 & 3.12 Support**: Verify compatibility and add to CI build matrix.
- [ ] **Comprehensive Test Suite**: Increase test coverage to 95%+ (currently targeting 85%).

---

## Phase 2: The Standard (MUST HAVE)

**Focus**: Feature parity with top competitors, user experience improvements, and robust error handling.

- [x] **Caching System**: Speed up subsequent runs by caching analysis results (`--enable-cache`).
- [x] **Performance Optimization**: Parallel import execution (`--parallel`) for large codebases.
- [x] **Automated Fix Generation**: Generate JSON patches for common import errors (`--generate-fixes`).
- [x] **Graph Export**: Generate DOT files for dependency visualization (`--graph`).
- [ ] **Interactive HTML Reports**: Create self-contained HTML reports for exploring import graphs interactively.
- [ ] **Configuration File Support**: Load settings from `pyproject.toml` or `.importdoc.rc` instead of just CLI args.

---

## Phase 3: The Ecosystem (INTEGRATION & SHOULD HAVE)

**Focus**: Webhooks, API exposure, 3rd party plugins, SDK generation, and extensibility.

- [ ] **Plugin Architecture**: Allow users to write custom checks (e.g., "ban imports from module X").
- [ ] **GitHub Actions Integration**: Publish a reusable GitHub Action for easy CI integration.
- [ ] **Pre-commit Hook**: Official `.pre-commit-hooks.yaml` for local development enforcement.
- [ ] **IDE Integration**: VS Code and PyCharm extensions for real-time diagnostics.
- [ ] **Build System Plugins**: Plugins for `hatch`, `poetry`, and `setuptools` to run checks during build.

---

## Phase 4: The Vision (GOD LEVEL)

**Focus**: "Futuristic" features, AI integration, advanced automation, and industry-disrupting capabilities.

- [x] **Enhanced `no module named` Diagnosis**: Analyze AST to suggest correct paths based on defined symbols.
- [x] **Fuzzy Module Search**: "Did you mean?" suggestions for typoed module names.
- [ ] **AI-Powered Refactoring**: Large Language Model integration to suggest architectural refactors for complex cycles.
- [ ] **Predictive Dependency Analysis**: Predict future conflicts based on dependency version trends.
- [ ] **Architectural Drift Detection**: Define "forbidden paths" and alert when architecture violates constraints.
- [ ] **Global Codebase Refactoring**: Apply import fixes across thousands of files safely in one go.

---

## The Sandbox (OUT OF THE BOX / OPTIONAL)

**Focus**: Wild, creative, experimental ideas that set the project apart.

- [ ] **"Import Cost" Analysis**: Measure and report the startup time and memory overhead of each import.
- [ ] **3D Dependency Visualization**: WebGL-based 3D graph of your project's architecture.
- [ ] **Gamification**: Achievements for code health (e.g., "Clean Sweep", "Cycle Breaker").
- [ ] **Runtime Profiler Integration**: Correlate static import structure with actual runtime usage hotspots.
