"""dashboard.py - UI Streamlit untuk Content-Based Organizer.

Install:  pip install streamlit
Jalankan (dari folder yang berisi content_organizer.py & test_workspace):
    streamlit run dashboard.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

import content_organizer as co

st.set_page_config(page_title="Local File Organizer Agent", layout="wide")

DEFAULT_MODELS = ["qwen2.5:7b", "qwen3.5:9b"]
LOG_PATH = co.WORKSPACE / ".move_log.json"

ss = st.session_state
ss.setdefault("cats_raw", "")
ss.setdefault("plan", None)
ss.setdefault("stats", None)
ss.setdefault("history", [])


# ---------------- Helper ----------------
def installed_models() -> list:
    try:
        import ollama
        names = [m.model for m in ollama.list().models]
        return names or DEFAULT_MODELS
    except Exception:
        return DEFAULT_MODELS


def list_files() -> list:
    if not co.WORKSPACE.exists():
        return []
    return sorted(f for f in co.WORKSPACE.iterdir() if f.is_file() and not f.name.startswith("."))


def apply_model(name: str):
    co.MODEL = name
    co.llm = co._make_llm()  # analyze_content membaca variabel global llm saat dipanggil


def parse_cats(raw: str) -> list:
    return [c.strip() for c in raw.split(",") if c.strip()]


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Pengaturan")
    models = installed_models()
    default_idx = models.index(co.MODEL) if co.MODEL in models else 0
    model = st.selectbox("Model Ollama", models, index=default_idx)
    min_conf = st.slider("Ambang confidence", 0.0, 1.0, float(co.MIN_CONFIDENCE), 0.05,
                         help="Di bawah angka ini file masuk 'Perlu Ditinjau'")
    snippet_chars = st.slider("Panjang cuplikan (karakter)", 200, 2000, int(co.SNIPPET_CHARS), 100,
                              help="Makin pendek = makin cepat & hemat token")
    st.caption(f"Folder kerja: {co.WORKSPACE}")

    st.divider()
    if st.button("Reset workspace dari backup"):
        res = subprocess.run([sys.executable, "reset_workspace.py"], capture_output=True, text=True,
                             cwd=Path(__file__).parent)
        if res.returncode == 0:
            ss.plan, ss.stats = None, None
            st.success("Workspace dikembalikan.")
            st.rerun()
        else:
            st.error(res.stderr[-600:] or "Reset gagal")

st.title("Local File & Workspace Organizer Agent")
st.caption("Klasifikasi file berdasarkan isi, memakai LLM lokal (Ollama). Data tidak keluar dari komputer.")

files = list_files()

# ---------------- 1. Scan ----------------
st.subheader("1. File di workspace")
if not files:
    st.info("Tidak ada file lepas di test_workspace. Gunakan tombol reset di sidebar.")
else:
    scan_df = pd.DataFrame({
        "File": [f.name for f in files],
        "Tipe": [f.suffix.lower() or "-" for f in files],
        "Ukuran (KB)": [round(f.stat().st_size / 1024, 1) for f in files],
        "Jalur": ["LLM (isi file)" if f.suffix.lower() in (".txt", ".md", ".pdf", ".docx")
                  else "Aturan ekstensi" for f in files],
    })
    st.dataframe(scan_df, hide_index=True)

# ---------------- 2. Kategori ----------------
st.subheader("2. Tentukan kategori")
mode = st.radio("Cara menentukan kategori", ["Ketik sendiri", "Diusulkan AI"], horizontal=True)
if mode == "Diusulkan AI" and st.button("Minta usulan kategori dari AI", disabled=not files):
    apply_model(model)
    with st.spinner("AI membaca cuplikan file..."):
        samples = []
        for f in files:
            snip = co.extract_text(f, 300)
            if snip:
                samples.append((f.name, snip))
            if len(samples) >= 8:
                break
        ss.cats_raw = ", ".join(co.propose_categories(samples))
raw = st.text_input("Daftar kategori (pisahkan dengan koma)", key="cats_raw",
                    placeholder="Jurnal AI, Ekonomi, SCADA")
categories = parse_cats(raw)
if categories:
    st.write("Kategori dipakai:", " | ".join(f"`{c}`" for c in categories))

# ---------------- 3. Analisis ----------------
st.subheader("3. Analisis isi file")
if st.button("Mulai analisis", type="primary", disabled=not (files and categories)):
    apply_model(model)
    co.MIN_CONFIDENCE = min_conf
    plan, bar = [], st.progress(0.0, text="Memulai...")
    total_start = time.perf_counter()
    for i, f in enumerate(files):
        t0 = time.perf_counter()
        snippet = co.extract_text(f, snippet_chars)
        if snippet:
            a = co.analyze_content(f.name, snippet, categories)
            row = (a.category, a.confidence, "LLM", a.summary)
        else:
            row = (co.ext_category(f), 1.0, "Ekstensi", "")
        plan.append({
            "Pindah": True, "File": f.name, "Kategori": row[0],
            "Confidence": round(row[1], 2), "Metode": row[2],
            "Waktu (dtk)": round(time.perf_counter() - t0, 1), "Ringkasan": row[3],
        })
        bar.progress((i + 1) / len(files), text=f"{f.name} -> {row[0]}")
    total = time.perf_counter() - total_start
    bar.empty()

    llm_rows = [r for r in plan if r["Metode"] == "LLM"]
    ss.plan = plan
    ss.stats = {
        "Model": model, "Total (dtk)": round(total, 1), "File": len(plan),
        "File via LLM": len(llm_rows),
        "Rata-rata per file LLM (dtk)": round(sum(r["Waktu (dtk)"] for r in llm_rows) / len(llm_rows), 1)
        if llm_rows else 0,
        "Perlu Ditinjau": sum(1 for r in plan if r["Kategori"] == co.REVIEW_FOLDER),
    }
    ss.history.append(ss.stats)

# ---------------- 4. Rencana (dry-run) ----------------
if ss.plan:
    st.subheader("4. Rencana pemindahan (dry-run)")
    s = ss.stats
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total waktu", f"{s['Total (dtk)']} dtk")
    c2.metric("Rata-rata per file LLM", f"{s['Rata-rata per file LLM (dtk)']} dtk")
    c3.metric("File via LLM", f"{s['File via LLM']} / {s['File']}")
    c4.metric("Perlu Ditinjau", s["Perlu Ditinjau"])

    options = sorted(set(categories) | {co.REVIEW_FOLDER, "Others"} | set(co.EXT_RULES.keys())
                     | {r["Kategori"] for r in ss.plan})
    st.caption("Kategori bisa diubah manual lewat dropdown. Hilangkan centang untuk melewati file.")
    edited = st.data_editor(
        pd.DataFrame(ss.plan), hide_index=True, key="plan_editor",
        disabled=["File", "Confidence", "Metode", "Waktu (dtk)", "Ringkasan"],
        column_config={
            "Pindah": st.column_config.CheckboxColumn("Pindah"),
            "Kategori": st.column_config.SelectboxColumn("Kategori", options=options, required=True),
            "Ringkasan": st.column_config.TextColumn("Ringkasan", width="large"),
        },
    )
    st.bar_chart(edited[edited["Pindah"]]["Kategori"].value_counts())

    # ---------------- 5. Eksekusi ----------------
    st.subheader("5. Eksekusi")
    confirm = st.checkbox("Saya sudah memeriksa rencana di atas")
    if st.button("Pindahkan file", disabled=not confirm):
        log, errors = [], []
        for _, r in edited[edited["Pindah"]].iterrows():
            src = co.WORKSPACE / r["File"]
            try:
                dest = co.safe_move(src, r["Kategori"])
                log.append({"from": str(src), "to": str(dest)})
            except Exception as e:
                errors.append(f"{r['File']}: {e}")
        LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
        ss.plan = None
        st.success(f"{len(log)} file dipindahkan.")
        if errors:
            st.error("Gagal:\n" + "\n".join(errors))
        else:
            st.rerun()

# ---------------- Undo ----------------
st.divider()
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Undo")
    if LOG_PATH.exists():
        if st.button("Kembalikan pemindahan terakhir"):
            entries, restored = json.loads(LOG_PATH.read_text(encoding="utf-8")), 0
            for e in entries:
                src, dst = Path(e["to"]), Path(e["from"])
                if src.exists() and not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    src.rename(dst)
                    restored += 1
                    try:
                        src.parent.rmdir()  # hapus folder kategori bila kosong
                    except OSError:
                        pass
            LOG_PATH.unlink()
            st.success(f"{restored} file dikembalikan.")
            st.rerun()
    else:
        st.caption("Belum ada pemindahan yang bisa dibatalkan.")

# ---------------- Riwayat perbandingan model ----------------
with col_b:
    st.subheader("Riwayat run (perbandingan model)")
    if ss.history:
        hist = pd.DataFrame(ss.history)
        st.dataframe(hist, hide_index=True)
        st.download_button("Unduh CSV", hist.to_csv(index=False).encode("utf-8"),
                           "riwayat_run.csv", "text/csv")
    else:
        st.caption("Jalankan analisis dengan beberapa model untuk membandingkan waktu.")
