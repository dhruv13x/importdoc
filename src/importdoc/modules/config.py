
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class DiagnosticConfig:
    continue_on_error: bool = False
    verbose: bool = False
    quiet: bool = False
    exclude_patterns: List[str] = field(default_factory=list)
    use_emojis: bool = True
    log_file: Optional[str] = None
    timeout: int = 0
    dry_run: bool = False
    unload: bool = False
    json_output: bool = False
    parallel: int = 0
    max_depth: Optional[int] = None
    dev_mode: bool = False
    dev_trace: bool = False
    graph: bool = False
    dot_file: Optional[str] = None
    allow_root: bool = False
    show_env: bool = False
    enable_telemetry: bool = False
    enable_cache: bool = False
    generate_fixes: bool = False
    fix_output: Optional[str] = None
    safe_mode: bool = True
    safe_skip_imports: bool = True
    max_scan_results: int = 200
    html: bool = False
    plugins: List[str] = field(default_factory=list)

    # Internal
    exclude_regexes: List[Pattern] = field(init=False, default_factory=list)

    def __post_init__(self):
        # Restore safety checks
        if not self.allow_root and hasattr(os, "geteuid") and os.geteuid() == 0:
            raise PermissionError(
                "❌ Refusing to run as root. Use --allow-root if you really mean it."
            )

        # Restore regex compilation
        if self.exclude_patterns:
            for pat in self.exclude_patterns:
                try:
                    self.exclude_regexes.append(re.compile(pat))
                except re.error as e:
                    print(
                        f"⚠️ Invalid exclude pattern ignored: '{pat}' ({e})",
                        file=sys.stderr,
                    )


def load_config(root_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from pyproject.toml or .importdoc.rc.
    Prioritize pyproject.toml if both exist (or maybe the other way around?
    Roadmap says "pyproject.toml or .importdoc.rc").

    Returns a dictionary of configuration options.
    """
    if root_dir is None:
        root_dir = Path.cwd()

    config = {}

    # Check pyproject.toml
    pyproject_path = root_dir / "pyproject.toml"
    if pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                if "tool" in data and "importdoc" in data["tool"]:
                    config.update(data["tool"]["importdoc"])
        except Exception as e:
            # We might want to log this but for now silently ignore malformed config
            # or maybe print a warning to stderr?
            # Since this is a library module, maybe we shouldn't print.
            pass

    # Check .importdoc.rc (assuming TOML for now, or INI?)
    # Let's support TOML for consistency.
    rc_path = root_dir / ".importdoc.rc"
    if rc_path.exists():
        try:
            with open(rc_path, "rb") as f:
                data = tomllib.load(f)
                # Assume .importdoc.rc is just the keys directly, or under a section?
                # Let's assume keys directly for .rc file simplicity.
                config.update(data)
        except Exception:
            pass

    # Normalize keys: convert kebab-case to snake_case
    normalized_config = {}
    for k, v in config.items():
        normalized_config[k.replace("-", "_")] = v

    return normalized_config
