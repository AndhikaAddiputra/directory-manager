"""content_organizer.py
Tambahan untuk proyek: klasifikasi + ringkasan file berdasarkan ISI.
File ini berdiri sendiri (tidak mengubah main.py / agent.py yang lama).

Install tambahan:  pip install pypdf python-docx
Jalankan:  python content_organizer.py [path-folder]
"""
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

# ---------------- Konfigurasi ----------------
WORKSPACE = Path("./test_workspace").resolve()
MODEL = "qwen3.5:9b"          # ganti ke "qwen3.5:9b" untuk perbandingan
SNIPPET_CHARS = 800           # cuplikan isi yang dikirim ke LLM (hemat token)
MIN_CONFIDENCE = 0.6          # di bawah ini -> masuk folder "Perlu Ditinjau"
REVIEW_FOLDER = "Perlu Ditinjau"

# File non-teks diputuskan lewat aturan ekstensi (tanpa LLM = cepat & hemat)
EXT_RULES = {
    "Documents": {".txt", ".md", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".rtf", ".odt"},
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff", ".heic", ".ico"},
    "Videos": {
        ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".wmv", ".flv",
        ".mpeg", ".mpg", ".3gp", ".m2ts", ".vob", ".ogv",
        ".hevc", ".hvc", ".h265", ".h264",
    },
    "Audio": {
        ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".oga", ".opus",
        ".wma", ".aiff", ".aif", ".alac", ".mid", ".midi", ".amr",
    },
    "Code": {".py", ".js", ".ts", ".tsx", ".mts", ".cts", ".jsx", ".java", ".c", ".cpp", ".h", ".html", ".css"},
    "Data": {".csv", ".tsv", ".xlsx", ".xls", ".json", ".xml"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
}

def set_workspace(path: str | Path) -> Path:
    """Ganti folder yang dirapikan. Pemindahan tetap hanya di dalam folder ini."""
    global WORKSPACE
    p = Path(path).expanduser()
    if not str(p).strip():
        raise ValueError("Path folder kosong.")
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    if not p.exists():
        raise ValueError(f"Folder tidak ditemukan: {p}")
    if not p.is_dir():
        raise ValueError(f"Bukan folder: {p}")
    if p == Path(p.anchor):
        raise ValueError("Folder root tidak boleh dipilih.")
    WORKSPACE = p
    return WORKSPACE


def _make_llm() -> ChatOllama:
    try:  # matikan mode thinking bila didukung (relevan untuk qwen3.x)
        return ChatOllama(model=MODEL, temperature=0, num_ctx=4096, reasoning=False)
    except Exception:
        return ChatOllama(model=MODEL, temperature=0, num_ctx=4096)


llm = _make_llm()


# ---------------- Skema output LLM ----------------
class FileAnalysis(BaseModel):
    category: str = Field(description="Tepat salah satu kategori dari daftar yang diberikan")
    confidence: float = Field(description="Keyakinan 0.0 sampai 1.0")
    summary: str = Field(description="Ringkasan isi 1-2 kalimat dalam Bahasa Indonesia")


class CategoryProposal(BaseModel):
    categories: List[str] = Field(description="3 sampai 8 nama kategori folder yang singkat")


# ---------------- Tool 1: ekstraksi teks ----------------
def extract_text(path: Path, max_chars: int = SNIPPET_CHARS) -> str:
    """Ambil cuplikan teks dari .txt/.md/.pdf/.docx. Kosong bila tidak bisa dibaca."""
    ext = path.suffix.lower()
    try:
        if ext in (".txt", ".md"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(max_chars * 4)
        elif ext == ".pdf":
            from pypdf import PdfReader
            pages = PdfReader(str(path)).pages[:3]
            text = " ".join((p.extract_text() or "") for p in pages)
        elif ext == ".docx":
            from docx import Document
            text = " ".join(p.text for p in Document(str(path)).paragraphs[:40])
        else:
            return ""
    except Exception:
        return ""
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


# ---------------- Tool 2: analisis isi (klasifikasi + ringkasan, 1 panggilan LLM) ----------------
def analyze_content(filename: str, snippet: str, categories: List[str]) -> FileAnalysis:
    prompt = (
        "Kamu mengklasifikasikan dokumen berdasarkan isinya.\n"
        f"Kategori yang diizinkan: {', '.join(categories)}\n"
        "Pilih TEPAT satu kategori dari daftar itu. Jika tidak ada yang cocok, "
        "beri confidence rendah.\n"
        f"Nama file: {filename}\n"
        f"Cuplikan isi: {snippet}"
    )
    try:
        result = llm.with_structured_output(FileAnalysis).invoke(prompt)
    except Exception as e:
        return FileAnalysis(category=REVIEW_FOLDER, confidence=0.0, summary=f"(gagal analisis: {e})")

    # validasi: kategori harus ada di daftar (cegah kategori halusinasi)
    lookup = {c.lower(): c for c in categories}
    category = lookup.get(result.category.strip().lower())
    if category is None or result.confidence < MIN_CONFIDENCE:
        category = REVIEW_FOLDER
    return FileAnalysis(category=category, confidence=result.confidence, summary=result.summary)


# ---------------- Tool 3: usulan kategori dari AI ----------------
def propose_categories(samples: List[tuple]) -> List[str]:
    joined = "\n".join(f"- {name}: {snip[:300]}" for name, snip in samples)
    prompt = (
        "Berikut cuplikan beberapa file. Usulkan 3 sampai 8 nama kategori folder "
        "yang singkat dan mewakili topik-topik ini (contoh: Jurnal AI, Novel, Ekonomi, Medis).\n"
        f"{joined}"
    )
    try:
        result = llm.with_structured_output(CategoryProposal).invoke(prompt)
        return [c.strip() for c in result.categories if c.strip()]
    except Exception:
        return []


# ---------------- Opsional: bungkus sebagai tool LangChain untuk agent ----------------
CURRENT_CATEGORIES: List[str] = []


@tool
def analyze_file_content(file_path: str) -> str:
    """Membaca isi file teks/PDF/DOCX di test_workspace, lalu mengembalikan kategori,
    confidence, dan ringkasan 1-2 kalimat. Input: path lengkap file."""
    path = Path(file_path).resolve()
    if WORKSPACE not in path.parents:
        return "Akses ditolak: di luar folder yang dipilih"
    snippet = extract_text(path)
    if not snippet:
        return "File tidak berisi teks yang bisa dibaca"
    a = analyze_content(path.name, snippet, CURRENT_CATEGORIES or [REVIEW_FOLDER])
    return json.dumps(a.model_dump(), ensure_ascii=False)


# ---------------- Util: kategori awal (human-in-the-loop) ----------------
def ask_categories(files: List[Path]) -> List[str]:
    print("\nPilih cara menentukan kategori:")
    print("  1. Ketik sendiri (pisahkan dengan koma)")
    print("  2. Usulkan AI dari isi file, lalu saya setujui/edit")
    mode = input("Pilihan [1/2]: ").strip()

    if mode == "2":
        samples = []
        for f in files:
            snip = extract_text(f, 300)
            if snip:
                samples.append((f.name, snip))
            if len(samples) >= 8:
                break
        proposed = propose_categories(samples)
        print(f"\nUsulan AI: {', '.join(proposed) if proposed else '(kosong)'}")
        edited = input("Tekan Enter untuk setuju, atau ketik daftar baru (pisah koma): ").strip()
        cats = [c.strip() for c in edited.split(",") if c.strip()] if edited else proposed
    else:
        raw = input("Kategori (contoh: Jurnal AI, Buku Politik, Novel, Medis): ")
        cats = [c.strip() for c in raw.split(",") if c.strip()]

    if not cats:
        cats = ["Dokumen Umum"]
    return cats

# ---------------- Util: pemindahan aman ----------------
def _clean_folder(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", name).strip() or REVIEW_FOLDER

def safe_move(src: Path, category: str) -> Path:
    src = src.resolve()
    if WORKSPACE not in src.parents:
        raise ValueError("File di luar folder yang dipilih")
    dest_dir = WORKSPACE / _clean_folder(category)
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / src.name
    n = 1
    while dest.exists():  # jangan menimpa file yang sudah ada
        dest = dest_dir / f"{src.stem}_{n}{src.suffix}"
        n += 1
    shutil.move(str(src), str(dest))
    return dest

def _inside(workspace: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def undo_moves(workspace: Path | None = None) -> int:
    """Kembalikan file sesuai .move_log.json di dalam folder yang dipilih."""
    workspace = (workspace or WORKSPACE).resolve()
    log_path = workspace / ".move_log.json"
    if not log_path.is_file():
        return 0
    try:
        entries = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    restored = 0
    for entry in reversed(entries):
        src, dst = Path(entry["to"]), Path(entry["from"])
        if not _inside(workspace, src) or not _inside(workspace, dst):
            continue
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            restored += 1
            try:
                if src.parent != workspace:
                    src.parent.rmdir()
            except OSError:
                pass
    log_path.unlink(missing_ok=True)
    return restored


def ext_category(path: Path) -> str:
    ext = path.suffix.lower()
    for folder, exts in EXT_RULES.items():
        if ext in exts:
            return folder
    return "Others"

# ---------------- Orkestrasi ----------------
def main():
    print("=== CONTENT-BASED ORGANIZER ===")
    try:
        if len(sys.argv) > 1:
            set_workspace(sys.argv[1])
        else:
            raw = input(f"Path folder yang ingin dirapikan [{WORKSPACE}]: ").strip()
            if raw:
                set_workspace(raw)
    except ValueError as e:
        print(e)
        return
    print(f"Folder: {WORKSPACE}")
    files = sorted(f for f in WORKSPACE.iterdir() if f.is_file() and not f.name.startswith("."))
    if not files:
        print(f"Tidak ada file lepas di {WORKSPACE}.")
        return

    categories = ask_categories(files)
    CURRENT_CATEGORIES[:] = categories
    print(f"\nKategori dipakai: {', '.join(categories)}\n")

    # 1) Analisis semua file -> rencana (belum ada yang dipindah)
    plan = []
    total_start = time.perf_counter()
    for f in files:
        t0 = time.perf_counter()
        snippet = extract_text(f)
        if snippet:
            a = analyze_content(f.name, snippet, categories)
            plan.append((f, a.category, a.confidence, a.summary))
            how = "LLM"
        else:
            plan.append((f, ext_category(f), 1.0, ""))
            how = "ekstensi"
        print(f"  [{how}] {f.name} -> {plan[-1][1]}  ({time.perf_counter() - t0:.1f} dtk)")
    print(f"\nTotal waktu analisis: {time.perf_counter() - total_start:.1f} dtk")

    # 2) Dry-run: tampilkan rencana, minta konfirmasi
    print("\n=== RENCANA PEMINDAHAN ===")
    for f, cat, conf, summ in plan:
        print(f"- {f.name} -> {cat} (confidence {conf:.2f})")
        if summ:
            print(f"    ringkasan: {summ}")
    if input("\nLanjutkan memindahkan? [y/N]: ").strip().lower() != "y":
        print("Dibatalkan. Tidak ada file yang dipindah.")
        return

    # 3) Eksekusi + simpan log untuk undo
    log = []
    for f, cat, _, _ in plan:
        original = str(f)
        dest = safe_move(f, cat)
        log.append({"from": original, "to": str(dest)})
    (WORKSPACE / ".move_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSelesai. {len(log)} file dipindahkan. Log undo: {WORKSPACE / '.move_log.json'}")


if __name__ == "__main__":
    main()
