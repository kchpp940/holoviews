import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "holoviews/tests/core/test_theme.py", "-v", "--no-header"],
    cwd="/Users/pkcha/holoviews",
    capture_output=True,
    text=True,
    timeout=120
)

print("STDOUT:")
print(result.stdout)
print("\nSTDERR:")
print(result.stderr)
print("\nReturn code:", result.returncode)
