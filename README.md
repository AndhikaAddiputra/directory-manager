# Local File & Workspace Organizer Agent

Agent AI lokal (Ollama + LangChain) yang memindai `test_workspace/`, meringkas file teks, lalu memindahkan file ke subfolder `Documents`, `Images`, `Code`, `Archives`, atau `Others`.

## Setup
Butuh Python 3.10+ dan [Ollama](https://ollama.com/download).

```bash
ollama pull qwen2.5:7b

# Mac
python3.13 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
py -3.13 -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

## Menjalankan
```bash
python reset_workspace.py   # kembalikan test_workspace ke kondisi berantakan
python main.py              # jalankan agent
```

## Struktur
- `tools.py`: tool `scan_directory`, `read_text_file`, `move_file` (dibatasi hanya di dalam `test_workspace`)
- `agent.py`: LLM lokal + agent LangChain (`create_agent`)
- `main.py`: CLI orchestrator. Scan folder, lalu menjalankan agent per file dengan konteks terpisah (lebih andal untuk model lokal 7B), plus verifier yang mengecek hasil dan meminta agent mencoba lagi kalau file belum pindah
- `reset_workspace.py`: menyalin ulang data dummy dari `test_workspace_backup/`
