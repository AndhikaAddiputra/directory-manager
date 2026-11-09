from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from tools import scan_directory, read_text_file, move_file

llm = ChatOllama(
    model="qwen2.5:7b",
    temperature=0,
    num_ctx=8192,  # default Ollama kecil; tanpa ini instruksi awal bisa terpotong
)

agent = create_agent(
    model=llm,
    tools=[scan_directory, read_text_file, move_file],
    system_prompt=(
        "Kamu adalah asisten perapi file. Ikuti langkah ini:\n"
        "1. Panggil scan_directory pada folder target.\n"
        "2. Untuk setiap file teks (.txt/.md), panggil read_text_file lalu buat ringkasan "
        "satu kalimat berdasarkan ISI yang benar-benar kamu baca, jangan menebak.\n"
        "3. Pindahkan SETIAP file dengan move_file memakai path lengkap dan 'saran kategori' dari hasil scan.\n"
        "4. Panggil scan_directory sekali lagi untuk memastikan tidak ada file yang tertinggal; "
        "kalau masih ada, pindahkan juga.\n"
        "5. Akhiri dengan laporan singkat dalam Bahasa Indonesia: file apa pindah ke mana, "
        "dan ringkasan isi file teks."
    ),
)
