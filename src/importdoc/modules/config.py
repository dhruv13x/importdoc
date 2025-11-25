# src/importdoc/modules/config.py

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Pattern

@dataclass
class DiagnosticConfig:
    continue_on_error: bool = False
    verbose: bool = False
    quiet: bool = False
    exclude_patterns: Optional[List[str]] = None
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

    # Computed fields
    exclude_regexes: List[Pattern] = field(init=False, default_factory=list)

    def __post_init__(self):
        # Root check
        if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0 and not self.allow_root:
            raise PermissionError(
                "Refusing to run as root (use --allow-root to override)."
            )
        
        # Compile regexes
        if self.exclude_patterns:
            self.exclude_regexes = [re.compile(p) for p in self.exclude_patterns]
        else:
            self.exclude_regexes = []
