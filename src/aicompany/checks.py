"""Deterministische Prüfungen für Agentenergebnisse (vom Programm, nicht vom Modell ausgeführt).

Generierter Code wird NICHT ausgeführt, sondern statisch geprüft (keine externen Ressourcen,
kein Tracking, keine gefährlichen JS-Konstrukte, keine Geheimnisse, Pflichtseiten vorhanden).
"""
from __future__ import annotations

import re
from pathlib import Path

from .security import SECRET_PATTERNS

FORBIDDEN_CLAIMS = re.compile(
    r"(?i)(testimonial|kundenstimme|kundenbewertung|zufriedene kunden|garantiert(e|er)?\s+(erfolg|umsatz|gewinn)|"
    r"100\s?%\s?(sicher|erfolg|garantie)|nr\.?\s?1\b|bestseller|tausende\s+(zufriedene|nutzer|kunden)|"
    r"★★★★★|5\s?sterne)"
)
EXTERNAL_REF = re.compile(r"""(?i)(src|href|action)\s*=\s*["']\s*(https?:)?//""")
TRACKING = re.compile(r"(?i)(google-analytics|googletagmanager|gtag\(|fbq\(|facebook\.net|hotjar|matomo\.js|clarity\.ms)")
DANGEROUS_JS = re.compile(r"(\beval\s*\(|new\s+Function\s*\(|document\.cookie|innerHTML\s*=\s*[^'\"`])")


def check_claims(text: str) -> list[str]:
    return sorted({m.group(0) for m in FORBIDDEN_CLAIMS.finditer(text or "")})


def static_checks(root: Path, *, required: list[str], allowed_ext: tuple[str, ...]) -> dict:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    files = [p for p in root.rglob("*") if p.is_file()] if root.exists() else []
    rel = {str(p.relative_to(root)): p for p in files}
    missing = [r for r in required if r not in rel]
    add("Pflichtdateien vorhanden", not missing, ", ".join(missing) or "alle vorhanden")
    bad_ext = [r for r, p in rel.items() if p.suffix.lower() not in allowed_ext]
    add("Nur erlaubte Dateitypen", not bad_ext, ", ".join(bad_ext) or "ok")
    ext_refs, tracking, danger, claims, secrets, no_title = [], [], [], [], [], []
    for r, p in rel.items():
        text = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix in (".html", ".css", ".js"):
            ext_refs += [r] if EXTERNAL_REF.search(text.replace("mailto:", "")) else []
            tracking += [r] if TRACKING.search(text) else []
        if p.suffix in (".js", ".html"):
            danger += [r] if DANGEROUS_JS.search(text) else []
        if p.suffix == ".html" and not re.search(r"<title>[^<]+</title>", text):
            no_title.append(r)
        found = check_claims(text)
        if found:
            claims.append(f"{r}: {', '.join(found)}")
        if any(pat.search(text) for pat in SECRET_PATTERNS):
            secrets.append(r)
    add("Keine externen Skripte/Ressourcen", not ext_refs, ", ".join(ext_refs) or "ok")
    add("Kein Tracking", not tracking, ", ".join(tracking) or "ok")
    add("Keine gefährlichen JS-Konstrukte", not danger, ", ".join(danger) or "ok")
    add("HTML-Seiten mit Titel", not no_title, ", ".join(no_title) or "ok")
    add("Keine unzulässigen Werbeaussagen", not claims, "; ".join(claims) or "ok")
    add("Keine Geheimnisse im Code", not secrets, ", ".join(secrets) or "ok")
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "files": sorted(rel)}


# ---------------------------------------------------------------------------
# Python-Codeprüfung für generierte Software (vor jeder Ausführung)
# ---------------------------------------------------------------------------
import ast  # noqa: E402
import sys  # noqa: E402

ALLOWED_THIRD_PARTY = {"fastapi", "starlette", "pydantic", "pydantic_core", "uvicorn", "pytest", "anyio"}
FORBIDDEN_MODULES = {
    "subprocess", "socket", "ctypes", "multiprocessing", "importlib", "pty", "shutil", "signal", "resource",
    "requests", "urllib", "http.client", "httpx", "ftplib", "smtplib", "telnetlib", "paramiko", "asyncio.subprocess",
    "pickle", "marshal", "webbrowser", "winreg", "_winapi",
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint"}
FORBIDDEN_ATTRS = {"system", "popen", "spawnl", "spawnv", "execv", "execl", "fork", "kill", "remove", "rmdir", "unlink",
                   "chmod", "chown", "setuid", "putenv"}
ALLOWED_TEST_IMPORTS = {"fastapi.testclient"}


def scan_python(source: str, filename: str = "<code>") -> list[str]:
    """Statische Sicherheitsprüfung: nur Standardbibliothek + erlaubte Pakete, keine Prozess-/Netzwerk-/Dateisystem-Eingriffe."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"{filename}: Syntaxfehler in Zeile {exc.lineno}: {exc.msg}"]
    problems: list[str] = []
    stdlib = set(sys.stdlib_module_names)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for full in names:
                if isinstance(node, ast.ImportFrom) and node.level:  # relative Importe im eigenen Projekt
                    continue
                top = full.split(".")[0]
                if full in ALLOWED_TEST_IMPORTS:
                    continue
                if full in FORBIDDEN_MODULES or top in FORBIDDEN_MODULES:
                    problems.append(f"{filename}:{node.lineno}: Import '{full}' ist nicht erlaubt")
                elif top not in stdlib and top not in ALLOWED_THIRD_PARTY and top not in ("app", "tests"):
                    problems.append(f"{filename}:{node.lineno}: Paket '{top}' ist nicht freigegeben")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALLS:
                problems.append(f"{filename}:{node.lineno}: Aufruf '{fn.id}()' ist nicht erlaubt")
            if isinstance(fn, ast.Attribute) and fn.attr in FORBIDDEN_ATTRS and isinstance(fn.value, ast.Name) and fn.value.id in ("os", "shutil", "sys"):
                problems.append(f"{filename}:{node.lineno}: Aufruf '{fn.value.id}.{fn.attr}()' ist nicht erlaubt")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if v.startswith(("/etc", "/root", "/home", "C:\\", "~/")) or "../" in v:
                problems.append(f"{filename}:{node.lineno}: Pfad außerhalb des Projekts: {v[:40]}")
    return problems
