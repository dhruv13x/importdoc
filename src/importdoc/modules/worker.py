# src/importdoc/modules/worker.py

import json
import subprocess
import sys
import time
import traceback
from typing import Any, Dict, Optional


def import_module_worker(module_name: str, timeout: Optional[int]) -> Dict[str, Any]:
    """
    Run the import in a subprocess using sys.executable and return structured result.
    Guarantees that a long-running or blocking C-extension won't hang the parent process.
    """
    child_code = (
        "import time, importlib, json, traceback, sys\n"
        "start=time.time()\n"
        "try:\n"
        f"    importlib.import_module({module_name!r})\n"
        "    end=time.time()\n"
        "    res={'success':True,'error':None,'tb':None,'time_ms':(end-start)*1000.0}\n"
        "except Exception:\n"
        "    end=time.time()\n"
        "    res={'success':False,'error':str(sys.exc_info()[1]),'tb':traceback.format_exc(),'time_ms':(end-start)*1000.0}\n"
        "sys.stdout.write(json.dumps(res))\n"
    )

    args = [sys.executable, "-c", child_code]
    start = time.time()
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout if timeout and timeout > 0 else None,
            check=False,
        )
        end = time.time()
        stdout = proc.stdout.decode("utf-8", errors="replace").strip()
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        # Try to parse JSON from stdout
        try:
            parsed = json.loads(stdout) if stdout else None
        except Exception:
            parsed = None

        if parsed and isinstance(parsed, dict) and "success" in parsed:
            # child already reports time_ms; but if missing, use measured
            if "time_ms" not in parsed:
                parsed["time_ms"] = (end - start) * 1000.0
            return {
                "success": parsed.get("success", False),
                "error": parsed.get("error"),
                "tb": parsed.get("tb"),
                "time_ms": parsed.get("time_ms", (end - start) * 1000.0),
            }
        else:
            # Child didn't return the expected JSON — treat as failure
            err_text = stderr or stdout or "<no output>"
            return {
                "success": False,
                "error": f"Subprocess failure (non-json output): {err_text}",
                "tb": err_text,
                "time_ms": (end - start) * 1000.0,
            }
    except subprocess.TimeoutExpired as te:
        # kill attempted by subprocess.run when timeout occurs
        end = time.time()
        return {
            "success": False,
            "error": f"Timeout after {timeout}s",
            "tb": f"TimeoutExpired: {te}",
            "time_ms": (end - start) * 1000.0,
        }
    except Exception as e:
        end = time.time()
        return {
            "success": False,
            "error": str(e),
            "tb": traceback.format_exc(),
            "time_ms": (end - start) * 1000.0,
        }
