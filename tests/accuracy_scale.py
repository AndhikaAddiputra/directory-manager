"""Uji akurasi aturan kategori dan pemindahan file pada 100, 1.000, dan 10.000 file.

Ground truth ada di skrip ini, terpisah dari EXT_MAP / EXT_RULES.
Yang diukur: klasifikasi ekstensi dan file benar-benar mendarat di folder yang benar.
Klasifikasi isi oleh LLM tidak dijalankan.
"""
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import content_organizer as co
import tools

# Spesifikasi independen. Huruf besar dicek terpisah lewat .lower() di tools.
SPEC = {
    "Documents": [".txt", ".md", ".pdf", ".docx", ".pptx"],
    "Images": [".png", ".jpg", ".heic", ".svg"],
    "Videos": [".mp4", ".mov", ".hvc", ".mkv", ".webm", ".m4v"],
    "Audio": [".mp3", ".wav", ".flac", ".m4a", ".aac"],
    "Code": [".py", ".ts", ".tsx", ".js"],
    "Data": [".csv", ".xlsx", ".json"],
    "Archives": [".zip", ".7z", ".gz"],
    "Others": [".xyz", ".bin", ""],
}
FLAT = [(cat, ext) for cat, exts in SPEC.items() for ext in exts]
SIZES = (100, 1000, 10000)


def expected_category(name: str) -> str:
    suffix = Path(name).suffix.lower()
    for cat, ext in FLAT:
        if ext == suffix:
            return cat
    return "Others"


def make_names(n: int) -> list[tuple[str, str]]:
    rows = []
    for i in range(n):
        cat, ext = FLAT[i % len(FLAT)]
        suffix = ext.upper() if i % 11 == 0 and ext else ext
        rows.append((f"file_{i:05d}{suffix}", cat))
    return rows


def classify(names: list[tuple[str, str]], predict) -> dict:
    started = time.perf_counter()
    wrong = []
    for name, truth in names:
        got = predict(Path(name))
        if got != truth:
            wrong.append({"file": name, "expected": truth, "got": got})
    elapsed = time.perf_counter() - started
    total = len(names)
    correct = total - len(wrong)
    return {
        "correct": correct,
        "total": total,
        "accuracy": correct / total,
        "wrong": wrong[:20],
        "wrong_count": len(wrong),
        "seconds": round(elapsed, 4),
    }


def place_files(folder: Path, names: list[tuple[str, str]]) -> None:
    for name, _ in names:
        (folder / name).write_bytes(b"x")


def run_move(folder: Path, names: list[tuple[str, str]], engine: str) -> dict:
    if engine == "tools":
        tools.set_workspace(folder)
        move = lambda src, cat: tools.move_file.invoke({"source_path": str(src), "category": cat})
        predict = tools._saran_kategori
    else:
        co.set_workspace(folder)
        move = lambda src, cat: str(co.safe_move(src, cat))
        predict = co.ext_category

    started = time.perf_counter()
    errors = []
    for name, _ in names:
        src = folder / name
        cat = predict(src)
        try:
            result = move(src, cat)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        if engine == "tools" and not str(result).endswith(f"dipindahkan ke {cat}/"):
            errors.append(f"{name}: {result}")
    elapsed = time.perf_counter() - started

    misplaced = []
    missing = 0
    for name, truth in names:
        dest = folder / truth / name
        if dest.is_file():
            continue
        missing += 1
        found = [p.parent.name for p in folder.rglob(name) if p.is_file()]
        if found and found[0] != truth:
            misplaced.append({"file": name, "expected": truth, "found": found[0]})
    root = folder.resolve()
    leftover = [
        p.name for p in root.iterdir() if p.is_file() and not p.name.startswith(".")
    ]
    escaped = [
        str(p)
        for p in root.rglob("*")
        if p.is_file() and root not in p.resolve().parents
    ]
    ok = len(names) - missing
    return {
        "engine": engine,
        "moved_ok": ok,
        "total": len(names),
        "accuracy": ok / len(names),
        "missing": missing,
        "misplaced": misplaced[:20],
        "leftover_root": len(leftover),
        "escaped": len(escaped),
        "errors": errors[:10],
        "error_count": len(errors),
        "seconds": round(elapsed, 4),
        "files_per_second": round(len(names) / elapsed, 1) if elapsed else None,
    }


def safety_checks() -> dict:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        inside = folder / "catatan.txt"
        inside.write_text("halo", encoding="utf-8")
        outside = folder.parent / f"di-luar-{folder.name}.txt"
        outside.write_text("no", encoding="utf-8")
        co.set_workspace(folder)
        tools.set_workspace(folder)
        blocked_co = False
        try:
            co.safe_move(outside, "Documents")
        except ValueError:
            blocked_co = True
        blocked_tools = "di luar" in tools.move_file.invoke(
            {"source_path": str(outside), "category": "Documents"}
        )
        outside.unlink(missing_ok=True)
        return {
            "content_organizer_blocks_escape": blocked_co,
            "tools_blocks_escape": blocked_tools,
            "inside_still_there": inside.is_file(),
        }


def main() -> None:
    original_tools = tools.WORKSPACE
    original_co = co.WORKSPACE
    report = {"sizes": [], "safety": safety_checks(), "spec_extensions": len(FLAT)}
    try:
        for n in SIZES:
            names = make_names(n)
            tools_cls = classify(names, tools._saran_kategori)
            co_cls = classify(names, co.ext_category)
            disagree = sum(
                tools._saran_kategori(Path(name)) != co.ext_category(Path(name))
                for name, _ in names
            )
            with tempfile.TemporaryDirectory(prefix=f"acc-tools-{n}-") as raw:
                folder = Path(raw)
                place_files(folder, names)
                tools_move = run_move(folder, names, "tools")
            with tempfile.TemporaryDirectory(prefix=f"acc-co-{n}-") as raw:
                folder = Path(raw)
                place_files(folder, names)
                co_move = run_move(folder, names, "content_organizer")
            report["sizes"].append(
                {
                    "n": n,
                    "tools_classify": tools_cls,
                    "organizer_classify": co_cls,
                    "classifier_disagreements": disagree,
                    "tools_move": tools_move,
                    "organizer_move": co_move,
                }
            )
            print(
                f"n={n} classify tools={tools_cls['accuracy']:.3f} "
                f"organizer={co_cls['accuracy']:.3f} "
                f"move tools={tools_move['accuracy']:.3f} ({tools_move['seconds']}s) "
                f"organizer={co_move['accuracy']:.3f} ({co_move['seconds']}s)",
                flush=True,
            )
    finally:
        tools.WORKSPACE = original_tools
        co.WORKSPACE = original_co
    out = Path(__file__).with_name("accuracy_scale_report.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
