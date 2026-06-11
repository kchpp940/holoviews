#!/usr/bin/env python
import subprocess
import sys
import os

def main():
    os.chdir("/Users/pkcha/holoviews")
    
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "holoviews/tests/core/test_theme.py",
        "-v",
        "--no-header",
        "-x"
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print()
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    for line in process.stdout:
        print(line, end="")
    
    process.wait()
    print()
    print(f"Exit code: {process.returncode}")
    
    return process.returncode

if __name__ == "__main__":
    sys.exit(main())
