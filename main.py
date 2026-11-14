"""CLI Local Workspace Organizer Agent.

Alur (orchestrator-workers + isolate context):
1. Orchestrator (kode) memanggil tool scan_directory untuk mendapat daftar file.
2. Untuk SETIAP file, agent dijalankan dengan konteks baru yang kecil dan fokus:
   agent memutuskan sendiri apakah perlu membaca file, membuat ringkasan, dan
   memanggil move_file. Konteks yang pendek membuat model lokal 7B jauh lebih andal.
3. Verifier (kode, tanpa LLM) mengecek apakah file benar-benar pindah;
   kalau belum, agent diberi umpan balik dan mencoba lagi (maksimal 2 kali).
"""
from agent import agent
import tools
from tools import scan_directory, set_workspace


def jalankan(messages):
    """Menjalankan satu putaran agent dan menampilkan setiap langkahnya."""
    state = None
    for state in agent.stream(
        {"messages": messages},
        {"recursion_limit": 12},  # batas langkah per file supaya loop tidak berputar tanpa ujung
        stream_mode="values",
    ):
        msg = state["messages"][-1]
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                print(f"  [Tool call] {tc['name']}({tc['args']})")
        elif msg.type == "tool":
            print(f"  [Hasil] {msg.content[:200]}")
    return state["messages"]


def masih_ada(nama_file):
    return (tools.WORKSPACE / nama_file).is_file()


if __name__ == "__main__":
    print("=== LOCAL WORKSPACE ORGANIZER AGENT ===")
    raw = input(f"Path folder yang ingin dirapikan [{tools.WORKSPACE}]: ").strip()
    if raw:
        try:
            set_workspace(raw)
        except ValueError as e:
            print(e)
            raise SystemExit(1)
    print(f"Folder: {tools.WORKSPACE}")
    hasil_scan = scan_directory.invoke({"folder_path": str(tools.WORKSPACE)})
    print(f"\n[Scan]\n{hasil_scan}\n")
    baris = [b for b in hasil_scan.splitlines() if " | " in b]

    laporan = []
    for b in baris:
        path = b.split(" | ")[0]
        nama = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        print(f"\n>>> Menangani {nama}")
        messages = [{
            "role": "user",
            "content": f"Tangani satu file ini: {b}\n"
                       "Jika file teks, baca dulu dengan read_text_file. Lalu pindahkan dengan "
                       "move_file memakai path lengkap dan saran kategori. Setelah itu jawab "
                       "dengan SATU kalimat: kategori tujuan, dan ringkasan isi jika file teks.",
        }]
        messages = jalankan(messages)

        for percobaan in range(2):  # verifier
            if not masih_ada(nama):
                break
            print(f"  [Verifier] {nama} belum dipindahkan, agent diminta mencoba lagi.")
            messages = jalankan(messages + [{
                "role": "user",
                "content": f"File {nama} masih belum dipindahkan. Panggil move_file sekarang.",
            }])

        status = "OK" if not masih_ada(nama) else "GAGAL"
        laporan.append(f"- [{status}] {nama}: {messages[-1].content.strip()}")

    print("\n=== LAPORAN AKHIR ===")
    print("\n".join(laporan))
    sisa = [f.name for f in tools.WORKSPACE.iterdir() if f.is_file() and not f.name.startswith(".")]
    print("\n[Verifier] Semua file sudah rapi." if not sisa else f"\n[Verifier] Masih tersisa: {sisa}")
