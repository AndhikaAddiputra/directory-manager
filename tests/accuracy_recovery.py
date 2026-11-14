"""Skenario pemulihan, benturan nama, dan batas folder.

Ukuran 100, 1.000, dan 10.000 file. Yang diukur:
- isi file sama persis setelah dipindah lalu dikembalikan lewat .move_log.json
- file yang sudah ada di folder tujuan tidak ditimpa
- path di luar folder, symlink keluar, dan log undo yang diubah tidak membocorkan file

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

SIZES = (100, 1000, 10000)
SPEC = [
    ("Documents", ".txt"),
    ("Images", ".png"),
    ("Videos", ".mp4"),
    ("Audio", ".wav"),
    ("Code", ".py"),
    ("Data", ".csv"),
    ("Archives", ".zip"),
    ("Others", ".bin"),
]


def names_for(n: int) -> list[tuple[str, str, bytes]]:
    rows = []
    for i in range(n):
        cat, ext = SPEC[i % len(SPEC)]
        name = f"berkas_{i:05d}{ext}"
        rows.append((name, cat, f"isi-{i:05d}".encode()))
    return rows


def place(folder: Path, rows: list[tuple[str, str, bytes]]) -> None:
    for name, _, payload in rows:
        (folder / name).write_bytes(payload)


def organize(folder: Path, rows: list[tuple[str, str, bytes]], engine: str) -> list[dict]:
    log = []
    if engine == "tools":
        tools.set_workspace(folder)
        move = lambda src, cat: tools.move_file.invoke(
            {"source_path": str(src), "category": cat}
        )
    else:
        co.set_workspace(folder)
        move = lambda src, cat: str(co.safe_move(src, cat))
    for name, cat, _ in rows:
        src = folder / name
        original = str(src.resolve())
        move(src, cat)
        dest = folder / cat / name
        if dest.is_file() and not src.exists():
            log.append({"from": original, "to": str(dest.resolve())})
    (folder / ".move_log.json").write_text(
        json.dumps(log, ensure_ascii=False), encoding="utf-8"
    )
    return log


def undo_case(n: int, engine: str) -> dict:
    rows = names_for(n)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"undo-{engine}-{n}-") as raw:
        folder = Path(raw)
        place(folder, rows)
        log = organize(folder, rows, engine)
        moved_ok = 0
        for name, cat, payload in rows:
            dest = folder / cat / name
            if dest.is_file() and dest.read_bytes() == payload:
                moved_ok += 1
        restored = co.undo_moves(folder)
        matched = 0
        for name, _, payload in rows:
            path = folder / name
            if path.is_file() and path.read_bytes() == payload:
                matched += 1
        dirs_left = [p.name for p in folder.iterdir() if p.is_dir()]
        log_removed = not (folder / ".move_log.json").exists()
        again = co.undo_moves(folder)
        elapsed = time.perf_counter() - started
    return {
        "n": n,
        "engine": engine,
        "logged": len(log),
        "moved_bytes_ok": moved_ok,
        "restored": restored,
        "bytes_match": matched,
        "accuracy": matched / n,
        "dirs_left": dirs_left,
        "log_removed": log_removed,
        "second_undo": again,
        "seconds": round(elapsed, 4),
    }


def collision_case(engine: str, n: int = 100, planted: int = 10) -> dict:
    rows = names_for(n)
    with tempfile.TemporaryDirectory(prefix=f"tabrak-{engine}-") as raw:
        folder = Path(raw)
        place(folder, rows)
        kept = {}
        for name, cat, _ in rows[:planted]:
            dest = folder / cat / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            payload = f"LAMA-{name}".encode()
            dest.write_bytes(payload)
            kept[name] = (cat, payload)
        if engine == "tools":
            tools.set_workspace(folder)
            skipped = 0
            for name, cat, _ in rows:
                msg = tools.move_file.invoke(
                    {"source_path": str(folder / name), "category": cat}
                )
                if str(msg).startswith("Dilewati"):
                    skipped += 1
            strategy = "dilewati"
        else:
            co.set_workspace(folder)
            renamed = 0
            for name, cat, payload in rows:
                src = folder / name
                if not src.exists():
                    continue
                dest = co.safe_move(src, cat)
                if dest.name != name and dest.read_bytes() == payload:
                    renamed += 1
            skipped = renamed
            strategy = "diberi akhiran _1"
        old_intact = sum(
            1
            for name, (cat, payload) in kept.items()
            if (folder / cat / name).is_file()
            and (folder / cat / name).read_bytes() == payload
        )
        new_intact = 0
        for name, _, payload in rows[:planted]:
            if engine == "tools":
                src = folder / name
                if src.is_file() and src.read_bytes() == payload:
                    new_intact += 1
            else:
                cat = rows[[r[0] for r in rows].index(name)][1]
                copy = folder / cat / f"{Path(name).stem}_1{Path(name).suffix}"
                if copy.is_file() and copy.read_bytes() == payload:
                    new_intact += 1
    return {
        "engine": engine,
        "n": n,
        "planted": planted,
        "strategy": strategy,
        "handled": skipped,
        "old_content_intact": old_intact,
        "new_content_intact": new_intact,
        "passed": skipped == planted and old_intact == planted and new_intact == planted,
    }


def check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": passed, "detail": detail}


def boundary_cases() -> list[dict]:
    checks = []
    with tempfile.TemporaryDirectory(prefix="batas-") as raw:
        folder = Path(raw)
        folder.mkdir(exist_ok=True)
        inside = folder / "catatan.txt"
        inside.write_text("di dalam", encoding="utf-8")
        outside = folder.parent / f"di-luar-{folder.name}.txt"
        outside.write_bytes(b"JANGAN")
        tools.set_workspace(folder)
        co.set_workspace(folder)

        msg = tools.move_file.invoke(
            {"source_path": str(outside), "category": "Documents"}
        )
        blocked_tools = "di luar" in str(msg) and outside.read_bytes() == b"JANGAN"
        checks.append(check("tools menolak file di luar folder", blocked_tools, str(msg)))

        blocked_co = False
        try:
            co.safe_move(outside, "Documents")
        except ValueError as exc:
            blocked_co = outside.read_bytes() == b"JANGAN" and "luar" in str(exc)
        checks.append(
            check("content organizer menolak file di luar folder", blocked_co, "ValueError")
        )

        link = folder / "tautan.txt"
        link.symlink_to(outside)
        link_tools = tools.move_file.invoke(
            {"source_path": str(link), "category": "Documents"}
        )
        checks.append(
            check(
                "tools menolak symlink yang mengarah ke luar",
                "di luar" in str(link_tools) and outside.read_bytes() == b"JANGAN",
                str(link_tools),
            )
        )
        link_co = False
        try:
            co.safe_move(link, "Documents")
        except ValueError:
            link_co = outside.read_bytes() == b"JANGAN" and link.is_symlink()
        checks.append(
            check("content organizer menolak symlink yang mengarah ke luar", link_co, "")
        )

        bad = tools.move_file.invoke(
            {"source_path": str(inside), "category": "../tmp"}
        )
        checks.append(
            check(
                "tools menolak kategori yang tidak dikenal",
                "tidak valid" in str(bad) and inside.is_file(),
                str(bad),
            )
        )
        escaped = co.safe_move(inside, "../../tmp")
        checks.append(
            check(
                "kategori berisi ../ tetap di dalam folder",
                folder.resolve() in escaped.resolve().parents
                and escaped.read_text(encoding="utf-8") == "di dalam"
                and not (folder.parent / "tmp").exists(),
                str(escaped.resolve().relative_to(folder.resolve())),
            )
        )

        root_tools = False
        try:
            tools.set_workspace("/")
        except ValueError:
            root_tools = True
        root_co = False
        try:
            co.set_workspace("/")
        except ValueError:
            root_co = True
        tools.set_workspace(folder)
        co.set_workspace(folder)
        checks.append(check("folder root ditolak", root_tools and root_co, ""))

        (folder / ".rahasia.txt").write_text("sembunyi", encoding="utf-8")
        (folder / "terlihat.txt").write_text("tampil", encoding="utf-8")
        listing = tools.scan_directory.invoke({"folder_path": str(folder)})
        checks.append(
            check(
                "scan melewati file tersembunyi",
                "terlihat.txt" in listing and ".rahasia" not in listing,
                listing.splitlines()[-1] if listing else "",
            )
        )

        long_text = "a" * 1500
        (folder / "panjang.txt").write_text(long_text, encoding="utf-8")
        read_back = tools.read_text_file.invoke({"file_path": str(folder / "panjang.txt")})
        checks.append(
            check(
                "pembacaan teks dipotong di 1000 karakter",
                read_back == "a" * 1000,
                f"panjang {len(read_back)}",
            )
        )
        pdf = folder / "bukan.txt.pdf"
        pdf.write_bytes(b"%PDF")
        pdf_msg = tools.read_text_file.invoke({"file_path": str(pdf)})
        checks.append(
            check(
                "read_text_file menolak selain .txt dan .md",
                "Hanya file .txt dan .md" in pdf_msg,
                pdf_msg,
            )
        )

        forged_outside = folder.parent / f"bocor-{folder.name}.txt"
        log_path = folder / ".move_log.json"
        log_path.write_text(
            json.dumps(
                [{"from": str(forged_outside), "to": str(folder / "terlihat.txt")}]
            ),
            encoding="utf-8",
        )
        restored = co.undo_moves(folder)
        checks.append(
            check(
                "log undo palsu tidak menulis file ke luar folder",
                restored == 0
                and not forged_outside.exists()
                and (folder / "terlihat.txt").is_file(),
                f"dikembalikan {restored}",
            )
        )

        empty = folder / "kosong"
        empty.mkdir()
        tools.set_workspace(empty)
        empty_msg = tools.scan_directory.invoke({"folder_path": str(empty)})
        checks.append(
            check(
                "folder kosong dilaporkan kosong",
                empty_msg == "Folder kosong, tidak ada file untuk dirapikan.",
                empty_msg,
            )
        )
        missing = tools.move_file.invoke(
            {"source_path": str(empty / "tidak-ada.txt"), "category": "Documents"}
        )
        checks.append(
            check(
                "file yang tidak ada tidak dipindahkan",
                "tidak ditemukan" in missing,
                missing,
            )
        )
        outside.unlink(missing_ok=True)
    return checks


def main() -> None:
    original_tools = tools.WORKSPACE
    original_co = co.WORKSPACE
    report = {"undo": [], "collision": [], "boundaries": []}
    try:
        for n in SIZES:
            for engine in ("tools", "content_organizer"):
                row = undo_case(n, engine)
                report["undo"].append(row)
                print(
                    f"undo n={n} {engine} match={row['bytes_match']}/{n} "
                    f"dirs={row['dirs_left'] or '-'} {row['seconds']}s",
                    flush=True,
                )
        for engine in ("tools", "content_organizer"):
            row = collision_case(engine)
            report["collision"].append(row)
            print(
                f"collision {engine} {row['strategy']} "
                f"old={row['old_content_intact']} new={row['new_content_intact']} "
                f"passed={row['passed']}",
                flush=True,
            )
        report["boundaries"] = boundary_cases()
        passed = sum(1 for item in report["boundaries"] if item["passed"])
        print(f"boundaries {passed}/{len(report['boundaries'])}", flush=True)
        for item in report["boundaries"]:
            if not item["passed"]:
                print(f"  GAGAL {item['name']}: {item['detail']}", flush=True)
    finally:
        tools.WORKSPACE = original_tools
        co.WORKSPACE = original_co
    out = Path(__file__).with_name("accuracy_recovery_report.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
