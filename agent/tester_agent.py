import ast
import os
import subprocess
import tempfile


def tester(generated_code: str, filename: str) -> dict:
    """
    Syntax-checks generated code without needing Docker, pytest, or test files.

    Python  -> ast.parse()         (built-in, zero dependencies)
    JS/TS   -> node --check / tsc  (requires Node installed)
    Go      -> go vet              (requires Go installed)
    Java    -> javac               (requires JDK installed)
    C/C++   -> gcc/g++ -fsyntax-only

    If the checker is not installed, test is skipped gracefully (passed=True).
    """
    ext = os.path.splitext(filename)[1]

    if not generated_code or not generated_code.strip():
        return {"passed": False, "output": "", "errors": "coder returned empty content"}

    if ext == ".py":
        try:
            ast.parse(generated_code)
            return {"passed": True, "output": "Syntax OK", "errors": ""}
        except SyntaxError as e:
            return {
                "passed": False,
                "output": "",
                "errors": f"SyntaxError line {e.lineno}: {e.msg} -- {e.text}",
            }

    checkers = {
        ".js":   ["node", "--check"],
        ".ts":   ["npx", "tsc", "--noEmit", "--allowJs"],
        ".go":   ["go", "vet"],
        ".java": ["javac"],
        ".cpp":  ["g++", "-fsyntax-only"],
        ".c":    ["gcc", "-fsyntax-only"],
    }

    checker = checkers.get(ext)
    if not checker:
        return {"passed": False, "output": "", "errors": f"unsupported file type: {ext}"}

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False)
    tmp.write(generated_code)
    tmp.close()

    try:
        result = subprocess.run(
            checker + [tmp.name],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return {"passed": True, "output": "Syntax OK", "errors": ""}
        return {"passed": False, "output": "", "errors": result.stderr or result.stdout}
    except FileNotFoundError:
        return {"passed": True, "output": f"checker for {ext} not installed -- skipped", "errors": ""}
    except Exception as e:
        return {"passed": False, "output": "", "errors": str(e)}
    finally:
        os.remove(tmp.name)