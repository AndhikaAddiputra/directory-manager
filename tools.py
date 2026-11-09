from pathlib import Path
import shutil
from langchain_core.tools import tool

WORKSPACE = Path(__file__).parent.joinpath("test_workspace").resolve()
CATEGORIES = ("Documents", "Images", "Code", "Archives", "Others")
EXT_MAP = {
    "Documents": {".txt", ".md", ".pdf", ".doc", ".docx", ".csv", ".xlsx", ".pptx"},
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"},
    "Code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".html", ".css", ".ipynb"},
    "Archives": {".zip", ".rar", ".tar", ".gz", ".7z"},
}


def _saran_kategori(f: Path) -> str:
    for cat, exts in EXT_MAP.items():
        if f.suffix.lower() in exts:
            return cat
    return "Others"


def _aman(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        # path relatif dianggap relatif terhadap test_workspace
        p = WORKSPACE / p if not str(p).startswith("test_workspace") else WORKSPACE.parent / p
    p = p.resolve()
    if not p.is_relative_to(WORKSPACE):
        raise ValueError(f"Akses ditolak: {path} berada di luar test_workspace")
    return p


@tool
def scan_directory(folder_path: str) -> str:
    """Melihat daftar file di sebuah folder. Mengembalikan path lengkap, ekstensi, dan saran kategori tiap file."""
    try:
        folder = _aman(folder_path)
    except ValueError as e:
        return str(e)
    if not folder.is_dir():
        return "Folder tidak ditemukan."
    files = [f for f in sorted(folder.iterdir()) if f.is_file() and not f.name.startswith(".")]
    if not files:
        return "Folder kosong, tidak ada file untuk dirapikan."
    return "\n".join(
        f"{f} | ekstensi: {f.suffix or '-'} | saran kategori: {_saran_kategori(f)}"
        + (" | file teks: WAJIB dibaca dengan read_text_file" if f.suffix.lower() in (".txt", ".md") else "")
        for f in files
    )


@tool
def read_text_file(file_path: str) -> str:
    """Membaca isi file .txt atau .md (maksimal 1000 karakter) untuk diringkas."""
    try:
        p = _aman(file_path)
    except ValueError as e:
        return str(e)
    if p.suffix.lower() not in (".txt", ".md"):
        return "Hanya file .txt dan .md yang bisa dibaca."
    if not p.exists():
        return f"File {file_path} tidak ditemukan."
    return p.read_text(encoding="utf-8", errors="ignore")[:1000]


@tool
def move_file(source_path: str, category: str) -> str:
    """Memindahkan file ke subfolder kategori di dalam test_workspace.

    Args:
        source_path: Path lengkap file yang akan dipindahkan.
        category: Salah satu dari Documents, Images, Code, Archives, Others.
    """
    if category not in CATEGORIES:
        return f"Kategori '{category}' tidak valid. Pilih salah satu: {', '.join(CATEGORIES)}."
    try:
        src = _aman(source_path)
    except ValueError as e:
        return str(e)
    if not src.is_file():
        return f"File {source_path} tidak ditemukan."
    dest_dir = WORKSPACE / category
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        return f"Dilewati: {dest.name} sudah ada di {category}."
    shutil.move(str(src), str(dest))
    return f"{src.name} dipindahkan ke {category}/"
