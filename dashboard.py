"""dashboard.py - UI Streamlit untuk Content-Based Organizer.

Install:  pip install streamlit
Jalankan (dari folder proyek):
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

st.set_page_config(page_title="Organizer", layout="wide", initial_sidebar_state="collapsed")

DEFAULT_MODELS = ["qwen2.5:7b", "qwen3.5:9b"]
DEMO_WORKSPACE = (Path(__file__).parent / "test_workspace").resolve()

ss = st.session_state
ss.setdefault("cats_raw", "")
ss.setdefault("plan", None)
ss.setdefault("stats", None)
ss.setdefault("history", [])
ss.setdefault("folder_path", "")

picked = ss.pop("_picked_folder", None)
if picked:
    ss.folder_path = picked
flash = ss.pop("_flash", None)


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


def move_log_path() -> Path:
    return co.WORKSPACE / ".move_log.json"


def _pick_folder_macos(initial: str) -> str | None:
    """Buka dialog folder macOS. '' artinya dibatalkan, None artinya gagal."""
    script = """
on run argv
    try
        POSIX path of (choose folder with prompt "Pilih folder yang ingin dirapikan" default location POSIX file (item 1 of argv))
    on error number -128
        ""
    end try
end run
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script, initial],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip().rstrip("/")


def pick_folder() -> str | None:
    initial = (ss.get("folder_path") or "").strip()
    initial_path = Path(initial).expanduser() if initial else Path.home()
    if not initial_path.is_dir():
        initial_path = Path.home()
    if sys.platform == "darwin":
        return _pick_folder_macos(str(initial_path))
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(initialdir=str(initial_path))
    except Exception:
        path = ""
    finally:
        root.destroy()
    return path or ""


def apply_model(name: str):
    co.MODEL = name
    co.llm = co._make_llm()  # analyze_content membaca variabel global llm saat dipanggil


def parse_cats(raw: str) -> list:
    return [c.strip() for c in raw.split(",") if c.strip()]


def reset_current_folder():
    if not (ss.get("folder_path") or "").strip():
        st.error("Pilih folder atau masukan path folder yang ingin dirapihkan")
        return
    try:
        target = co.set_workspace(ss.folder_path)
    except ValueError as e:
        st.error(str(e))
        return
    ss.plan, ss.stats = None, None
    if target == DEMO_WORKSPACE:
        res = subprocess.run(
            [sys.executable, "reset_workspace.py"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
        )
        if res.returncode != 0:
            st.error(res.stderr[-600:] or "Reset gagal")
            return
        ss._flash = f"Folder demo dikembalikan: {target}"
    else:
        restored = co.undo_moves(target)
        ss._flash = (
            f"{restored} file dikembalikan ke {target}."
            if restored
            else "Tidak ada pemindahan yang bisa di-reset di folder ini."
        )
    st.rerun()


st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;1,500&display=swap');
    html, body, .stApp, [data-testid="stAppViewContainer"] {
      background: #c5ced6 !important;
      font-family: Inter, sans-serif;
    }
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
    #MainMenu, footer, [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
      display: none !important;
    }
    .block-container { max-width: 1120px; padding: 28px 20px 40px; }
    .st-key-shell {
      background: #fff;
      border-radius: 28px;
      overflow: hidden;
      box-shadow: 0 28px 70px rgba(20, 32, 51, 0.18);
      gap: 0 !important;
      padding: 0 !important;
    }
    .st-key-hero {
      gap: 0.35rem !important;
      padding: 22px 28px 26px;
      background:
        radial-gradient(1px 1px at 12% 22%, rgba(255,255,255,.75) 50%, transparent 52%),
        radial-gradient(1px 1px at 28% 48%, rgba(255,255,255,.45) 50%, transparent 52%),
        radial-gradient(1.4px 1.4px at 63% 18%, rgba(255,255,255,.7) 50%, transparent 52%),
        radial-gradient(1px 1px at 78% 42%, rgba(255,255,255,.5) 50%, transparent 52%),
        radial-gradient(1px 1px at 88% 24%, rgba(255,255,255,.65) 50%, transparent 52%),
        radial-gradient(ellipse 90% 55% at 50% 115%, rgba(120, 190, 255, .72), transparent 58%),
        linear-gradient(180deg, #07101f 0%, #0b2f72 46%, #3b8cff 82%, #e7f2ff 100%);
    }
    .st-key-topbar {
      width: 100% !important;
      display: grid !important;
      grid-template-columns: 1fr auto 1fr;
      align-items: center !important;
    }
    .st-key-topbar > div:nth-child(1) { justify-self: start; }
    .st-key-topbar > div:nth-child(3) { justify-self: end; }
    .brand { display: flex; align-items: center; gap: 10px; color: #fff; font-weight: 600; letter-spacing: -0.03em; }
    .links { display: flex; justify-content: center; gap: 22px; }
    .links a { color: rgba(255,255,255,.88); text-decoration: none; font-size: 14px; font-weight: 500; }
    .hero-copy { text-align: center; padding: 28px 8px 8px; }
    .badge {
      display: inline-flex; align-items: center; gap: 8px;
      border: 1px solid rgba(255,255,255,.35); color: #fff;
      border-radius: 999px; padding: 4px 12px 4px 4px; font-size: 13px;
      background: rgba(8, 20, 48, .25);
    }
    .badge b {
      background: #fff; color: #12315c; border-radius: 999px;
      padding: 2px 8px; font-size: 11px; letter-spacing: .04em;
    }
    .hero-copy h1 {
      color: #fff; font-size: 64px; line-height: .98; letter-spacing: -0.045em;
      font-weight: 600; margin: 18px 0 12px;
    }
    .hero-copy h1 em { font-style: italic; font-weight: 500; }
    .hero-copy p {
      color: rgba(255,255,255,.88); font-size: 16px; line-height: 1.45;
      max-width: 520px; margin: 0 auto;
    }
    .st-key-composer {
      background: #fff; border-radius: 22px; padding: 8px 8px 8px 18px;
      box-shadow: 0 16px 40px rgba(16, 42, 92, .16); margin-top: 22px;
      align-items: center !important;
    }
    .st-key-composer [data-testid="stTextInput"] input {
      border: none !important; background: transparent !important;
      color: #1c314f !important; font-size: 15px; padding-left: 0;
      box-shadow: none !important;
    }
    .st-key-composer [data-testid="stTextInputRootElement"] {
      border: none !important; background: transparent !important;
    }
    .st-key-hero [data-testid="stCaptionContainer"] p { color: rgba(255,255,255,.8); text-align: center; }
    .st-key-composer button {
      background: #1f6fff !important; color: #fff !important; border: none !important;
      border-radius: 999px !important; width: 46px; min-width: 46px; height: 46px;
      font-size: 0 !important; box-shadow: none; padding: 0 !important;
    }
    .st-key-composer [data-testid="stIconMaterial"] {
      font-size: 22px !important; color: #fff;
    }
    .st-key-composer button [data-testid="stMarkdownContainer"] {
      display: none !important;
    }
    .st-key-topbar button {
      background: #fff !important; color: #12243f !important; border: none !important;
      border-radius: 999px !important; padding: 0 16px !important; height: 36px;
      font-weight: 600 !important; font-size: 14px !important; width: auto;
    }
    .st-key-stage { padding: 8px 32px 32px; background: #fff; }
    .lower { display: grid; grid-template-columns: 1.3fr .9fr; gap: 24px; align-items: end; padding: 18px 0 8px; }
    .lower h2 { color: #16315c; font-size: 42px; line-height: 1.02; letter-spacing: -0.045em; font-weight: 600; margin: 0; }
    .lower h2 span { color: #1f6fff; }
    .stats { display: grid; grid-template-columns: 1fr 1fr; }
    .stat { padding: 0 8px 0 18px; border-left: 1px solid #e4ebf3; }
    .spark { display: block; width: 14px; height: 14px; margin-bottom: 10px; }
    .num { color: #16315c; font-size: 48px; letter-spacing: -0.05em; font-weight: 600; line-height: 1; }
    .lbl { color: #7b8ba0; font-size: 13px; margin-top: 6px; }
    .st-key-stage h3 { color: #16315c; letter-spacing: -0.03em; font-weight: 600; }
    .st-key-stage button, .st-key-stage [data-testid="stDownloadButton"] button {
      border-radius: 999px !important; border: 1px solid #d7e1ec !important;
      background: #fff !important; color: #16315c !important; font-weight: 600 !important;
    }
    .st-key-stage button[kind="primary"],
    .st-key-stage [data-testid="stBaseButton-primary"] {
      background: #12243f !important; color: #fff !important; border-color: #12243f !important;
    }
    div[data-testid="stAlert"] { border-radius: 16px; border: none; }
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] { border-radius: 16px; overflow: hidden; }
    @media (max-width: 640px) {
      .hero-copy h1 { font-size: 40px; }
      .lower, .stats { grid-template-columns: 1fr; }
      .lower h2 { font-size: 32px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

folder_error = None
active = None
entered_path = (ss.get("folder_path") or "").strip()
if entered_path:
    try:
        active = co.set_workspace(entered_path)
    except ValueError as e:
        folder_error = str(e)

if ss.get("active_folder") != (str(active) if active else None):
    ss.plan = None
    ss.stats = None
    ss.active_folder = str(active) if active else None

with st.container(key="shell"):
    with st.container(key="hero"):
        with st.container(key="topbar", horizontal=True, vertical_alignment="center"):
            st.markdown(
                """
                <div class="brand">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="12" cy="12" r="8.2" stroke="white" stroke-width="1.6"/>
                    <path d="M15 7.2a6.2 6.2 0 1 0 .2 9.7" stroke="white" stroke-width="1.6" stroke-linecap="round"/>
                  </svg>
                  <span>Organizer</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div class="links">
                  <a href="#files">File</a>
                  <a href="#kategori">Kategori</a>
                  <a href="#analisis">Analisis</a>
                  <a href="#riwayat">Riwayat</a>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Reset folder", help="Mengembalikan file di folder yang path-nya sedang diisi. Folder demo disalin ulang dari backup."):
                reset_current_folder()

        st.markdown(
            """
            <div class="hero-copy">
              <div class="badge"><b>NEW</b> Model lokal, data tetap di komputer</div>
              <h1>Rapikan folder,<br><em>powered by AI</em></h1>
              <p>Pilih folder, baca isinya, lalu pindahkan file setelah Anda menyetujui rencananya.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="composer", horizontal=True, vertical_alignment="center"):
            st.text_input(
                "Folder yang ingin dirapikan",
                key="folder_path",
                label_visibility="collapsed",
                placeholder="Pilih folder atau masukan path folder yang ingin dirapihkan",
                help="Path absolut atau relatif. Hanya file yang langsung ada di folder ini yang dipindai.",
            )
            if st.button("Pilih folder", icon=":material/folder_open:", help="Pilih folder dari komputer"):
                chosen = pick_folder()
                if chosen:
                    ss._picked_folder = chosen
                    ss.plan, ss.stats = None, None
                    st.rerun()
                elif chosen is None:
                    st.warning("Pemilih folder tidak tersedia. Tempel path di kolom di samping.")
        if folder_error:
            st.error(folder_error)

    with st.container(key="stage"):
        if flash:
            st.success(flash)

        files = list_files() if active else []
        categories_preview = parse_cats(ss.get("cats_raw", ""))
        st.markdown(
            f"""
            <div class="lower">
              <h2>Platform perapi file<br><span>berbasis AI lokal</span><br>untuk folder Anda</h2>
              <div class="stats">
                <div class="stat">
                  <svg class="spark" viewBox="0 0 16 16" fill="none"><path d="M8 1.5l1.1 4.2L13.5 7 9.1 8.3 8 12.5 6.9 8.3 2.5 7l4.4-1.3L8 1.5z" fill="#1f6fff"/></svg>
                  <div class="num">{len(files)}</div>
                  <div class="lbl">File siap dirapikan</div>
                </div>
                <div class="stat">
                  <svg class="spark" viewBox="0 0 16 16" fill="none"><path d="M8 1.5l1.1 4.2L13.5 7 9.1 8.3 8 12.5 6.9 8.3 2.5 7l4.4-1.3L8 1.5z" fill="#1f6fff"/></svg>
                  <div class="num">{len(categories_preview)}</div>
                  <div class="lbl">Kategori dipilih</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        models = installed_models()
        default_idx = models.index(co.MODEL) if co.MODEL in models else 0
        set_model, set_conf, set_snip = st.columns(3)
        with set_model:
            model = st.selectbox("Model Ollama", models, index=default_idx)
        with set_conf:
            min_conf = st.slider("Ambang confidence", 0.0, 1.0, float(co.MIN_CONFIDENCE), 0.05,
                                 help="Di bawah angka ini file masuk 'Perlu Ditinjau'")
        with set_snip:
            snippet_chars = st.slider("Panjang cuplikan", 200, 2000, int(co.SNIPPET_CHARS), 100,
                                      help="Makin pendek = makin cepat dan hemat token")

        # ---------------- 1. Scan ----------------
        st.markdown('<div id="files"></div>', unsafe_allow_html=True)
        st.subheader("File di folder")
        if active and not folder_error:
            st.caption("Hanya file yang langsung ada di folder ini. Isi subfolder tidak dipindai.")
        if not entered_path:
            st.info("Pilih folder atau masukan path folder yang ingin dirapihkan")
        elif folder_error:
            st.info("Pilih folder yang valid untuk melihat filenya.")
        elif not files:
            st.info(f"Tidak ada file lepas di {active}. Untuk mengembalikan file yang sudah dipindahkan, gunakan Reset folder.")
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
        st.markdown('<div id="kategori"></div>', unsafe_allow_html=True)
        st.subheader("Tentukan kategori")
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
        st.markdown('<div id="analisis"></div>', unsafe_allow_html=True)
        st.subheader("Analisis isi file")
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
            st.subheader("Rencana pemindahan")
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
            st.subheader("Eksekusi")
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
                move_log_path().write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
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
            log_path = move_log_path()
            if active and log_path.exists():
                if st.button("Kembalikan pemindahan terakhir"):
                    restored = co.undo_moves(active)
                    ss._flash = f"{restored} file dikembalikan."
                    st.rerun()
            else:
                st.caption("Belum ada pemindahan yang bisa dibatalkan.")

        # ---------------- Riwayat perbandingan model ----------------
        with col_b:
            st.markdown('<div id="riwayat"></div>', unsafe_allow_html=True)
            st.subheader("Riwayat run")
            if ss.history:
                hist = pd.DataFrame(ss.history)
                st.dataframe(hist, hide_index=True)
                st.download_button("Unduh CSV", hist.to_csv(index=False).encode("utf-8"),
                                   "riwayat_run.csv", "text/csv")
            else:
                st.caption("Jalankan analisis dengan beberapa model untuk membandingkan waktu.")
