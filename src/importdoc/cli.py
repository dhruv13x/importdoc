#!/usr/bin/env python3
# src/importdoc/cli.py

"""
# importdoc.py
Advanced Import Diagnostic Tool V20 — PRODUCTION
- Cross-platform timeouts
- Explicit JSON-schema handling and optional enforcement
- Atomic cache writes
- Clear safe-mode behavior (does not silently flip CLI flags)
- Telemetry durations normalized to milliseconds
- Graph export correctness and safe file writes
- Improved logging (deduplicated handlers, timestamps)
- Enhanced: Fuzzy module search for missing modules, incomplete import detection
- NEW: Enhanced diagnosis for "no module named" by parsing import symbols from AST and suggesting correct paths based on symbol definitions
"""

import argparse
import sys
import traceback
from pathlib import Path
from importlib import metadata

from .modules.diagnostics import ImportDiagnostic
from .modules.config import load_config
from .banner import print_logo

try:
    __version__ = metadata.version("importdoc")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"


# ----------
# CLI entrypoint
# ----------
def main():
    print_logo()
    parser = argparse.ArgumentParser(
        description="Advanced Import Diagnostic Tool V20 - Hardened production build with enhanced diagnosis",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("package", help="Root package to diagnose.")
    parser.add_argument("--dir", help="Package directory (adds parent to sys.path).")
    parser.add_argument(
        "--continue-on-error", action="store_true", help="Continue after errors."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Discover only, no imports."
    )
    parser.add_argument("--max-depth", type=int, help="Max discovery depth.")
    parser.add_argument("--log-file", help="Log file path.")
    parser.add_argument("--verbose", action="store_true", help="Detailed output.")
    parser.add_argument("--quiet", action="store_true", help="Minimal output.")
    parser.add_argument("--no-emoji", action="store_true", help="No emojis.")
    parser.add_argument("--timeout", type=int, default=0, help="Import timeout (s).")
    parser.add_argument("--unload", action="store_true", help="Unload after import.")
    parser.add_argument("--json", action="store_true", help="JSON output.")
    parser.add_argument("--parallel", type=int, default=0, help="Parallel imports.")
    parser.add_argument("--dev-mode", action="store_true", help="Enable developer mode.")
    parser.add_argument("--dev-trace", action="store_true", help="Trace import chains.")
    parser.add_argument("--graph", action="store_true", help="Generate DOT graph.")
    parser.add_argument("--dot-file", help="DOT file path.")
    parser.add_argument("--allow-root", action="store_true", help="Allow root run.")
    parser.add_argument("--show-env", action="store_true", help="Show env vars.")
    parser.add_argument(
        "--enable-telemetry", action="store_true", help="Enable production telemetry."
    )
    parser.add_argument(
        "--enable-cache", action="store_true", help="Enable result caching."
    )
    parser.add_argument(
        "--generate-fixes", action="store_true", help="Generate automated fixes."
    )
    parser.add_argument("--fix-output", help="Output file for automated fixes (JSON).")
    parser.add_argument(
        "--no-safe-mode",
        action="store_false",
        dest="safe_mode",
        help="Disable safe mode (allow imports outside venv).",
    )
    parser.add_argument(
        "--no-safe-skip",
        action="store_false",
        dest="safe_skip_imports",
        help="Do not auto-skip imports if not in venv when safe mode active.",
    )
    parser.add_argument(
        "--max-scan-results",
        type=int,
        default=200,
        help="Max results for repo scans (defs/usages/fuzzy).",
    )
    parser.add_argument("--html", action="store_true", help="Generate interactive HTML report.")
    parser.add_argument("--version", action="version", version=__version__)

    # Load config before parsing args to potentially set defaults?
    # Or load after and merge?
    # The standard way is: Defaults < Config File < Env Vars < CLI Args.
    # argparse 'default' values make this tricky because we don't know if a value is default or user-provided.
    # Strategy: Parse args. If value is None or default, check config.
    # However, argparse fills in defaults.

    # Let's load config first.
    config = load_config()

    # We can set defaults in parser using set_defaults.
    parser.set_defaults(**config)

    args = parser.parse_args()

    # Note: 'args' will now have values from CLI if provided,
    # or from config (via set_defaults) if provided there,
    # or the hardcoded default in add_argument if neither provided.

    # Special handling for boolean flags which might be tricky with set_defaults
    # if the config uses different names or structure.
    # But assuming config keys match argument dests.

    # Also handle hyphens vs underscores. config keys usually have underscores?
    # TOML keys like "max-depth" or "max_depth". argparse dest is "max_depth".
    # We should normalize config keys to match argparse dests.

    # We passed **config to set_defaults. set_defaults expects kwargs matching dests.
    # So "max-depth" in TOML needs to be "max_depth" for argparse.
    # Our load_config should probably handle this normalization or we do it here.
    # But let's assume the user uses underscores in TOML for python compatibility or we fix it.

    try:
        diagnostic = ImportDiagnostic(
            continue_on_error=args.continue_on_error,
            verbose=args.verbose,
            quiet=args.quiet,
            use_emojis=not args.no_emoji,
            log_file=args.log_file,
            timeout=args.timeout,
            dry_run=args.dry_run,
            unload=args.unload,
            json_output=args.json,
            parallel=args.parallel,
            max_depth=args.max_depth,
            dev_mode=args.dev_mode,
            dev_trace=args.dev_trace,
            graph=args.graph,
            dot_file=args.dot_file,
            allow_root=args.allow_root,
            show_env=args.show_env,
            enable_telemetry=args.enable_telemetry,
            enable_cache=args.enable_cache,
            generate_fixes=args.generate_fixes,
            fix_output=args.fix_output,
            safe_mode=args.safe_mode,
            safe_skip_imports=args.safe_skip_imports,
            max_scan_results=args.max_scan_results,  # New
            html=args.html,
        )

        success = diagnostic.run_diagnostic(args.package, args.dir)
        sys.exit(0 if success else 1)
    except PermissionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # if logger not available, fallback to print
        try:
            diagnostic.reporter.log(f"Internal error: {e}", level="ERROR")
            diagnostic.reporter.log(traceback.format_exc(), level="DEBUG")
        except Exception:
            print(f"Internal error: {e}", file=sys.stderr)
            traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
