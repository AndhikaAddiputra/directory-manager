# Directory Manager

Aplikasi perapi folder yang berjalan sepenuhnya di komputer sendiri. Model bahasanya dilayani oleh [Ollama](https://ollama.com/download). Tidak ada berkas yang dikirim ke layanan awan. Yang dipindai hanya file yang terletak langsung di folder yang dipilih. Isi subfolder tidak ikut.

Repositori: https://github.com/AndhikaAddiputra/directory-manager

Ada dua jalur yang berdiri sendiri.

| Jalur | Masuk | Model bawaan | Yang memutuskan kategori |
|---|---|---|---|
| Agen CLI | `python main.py` | `qwen2.5:7b` | Saran ekstensi dari `tools.py`. File `.txt` dan `.md` dibaca lalu diringkas. |
| Organizer isi | `streamlit run dashboard.py` atau `python content_organizer.py` | `qwen3.5:9b` | File yang ada teksnya diklasifikasi ke kategori yang diketik pengguna. File lain memakai aturan ekstensi. |

`main.py` tidak memanggil `content_organizer.py`. Dashboard tidak memanggil agen di `agent.py`.

## Isi proyek

| Berkas | Peran |
|---|---|
| `main.py` | Orchestrator CLI. Meminta path, memindai folder, lalu menjalankan agen sekali untuk setiap file. |
| `agent.py` | Agen LangChain (`create_agent`) dengan tiga tool dan prompt sistem berbahasa Indonesia. |
| `tools.py` | Tool `scan_directory`, `read_text_file`, dan `move_file`, plus batas folder kerja. |
| `content_organizer.py` | Ekstraksi teks, klasifikasi isi, usulan kategori, pemindahan aman, dan undo. |
| `dashboard.py` | Antarmuka Streamlit. Nama tampilan: Organizer. |
| `reset_workspace.py` | Menghapus `test_workspace/` lalu menyalin ulang `test_workspace_backup/`. |
| `test_workspace_backup/` | Kondisi demo yang berantakan. |
| `.streamlit/config.toml` | Tema terang dashboard. |
| `requirements.txt` | Dependensi agen. Paket dashboard belum tercantum di sini. |
| `tests/accuracy_scale.py` | Uji kategori dan pemindahan pada 100, 1.000, dan 10.000 file. |
| `tests/accuracy_recovery.py` | Uji undo, benturan nama, dan batas folder. |
| `README.md` | Petunjuk singkat versi awal. Daftar kategorinya sudah tertinggal dari kode sekarang. |

`venv/` tidak ikut ke git.

## Menjalankan

Python yang dipakai di mesin ini adalah 3.13. README menyebut 3.10 ke atas.

```bash
ollama pull qwen2.5:7b
ollama pull qwen3.5:9b

python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install streamlit pandas pypdf python-docx
```

`qwen2.5:7b` untuk agen CLI. `qwen3.5:9b` untuk dashboard dan `content_organizer.py`. Keduanya harus sudah ada di Ollama sebelum analisis isi dijalankan.

```bash
python main.py
python content_organizer.py
python content_organizer.py /path/ke/folder
streamlit run dashboard.py
python reset_workspace.py
python tests/accuracy_scale.py
python tests/accuracy_recovery.py
```

Dari folder proyek, pemanggilan yang setara memakai `./venv/bin/python` dan `./venv/bin/streamlit` tanpa mengaktifkan venv. Streamlit memakai port bawaan 8501.

## Batas folder

Kedua jalur menolak folder yang sama.

- Path kosong.
- Path yang tidak ada, atau yang bukan folder.
- Path relatif diselesaikan terhadap direktori kerja saat ini, lalu dijadikan absolut.
- `~` dikembangkan.
- Akar filesystem, misalnya `/`, ditolak.
- Pemindahan hanya boleh menuju lokasi di dalam folder yang sudah dipilih.

Di `tools.py`, path relatif pada tool dianggap relatif terhadap folder kerja. Kalau path yang sudah diselesaikan tidak berada di dalam folder itu, tool mengembalikan kalimat akses ditolak dan tidak melempar ke luar. `safe_move` di content organizer melempar `ValueError`.

File yang namanya diawali titik tidak dipindai. `.move_log.json` dan `.rahasia.txt` tidak muncul di daftar. Isi subfolder juga tidak dipindai. File yang sudah masuk `Documents/` atau kategori lain tidak diangkat kembali ke akar oleh scan.

## Jalur agen CLI

Alurnya ada di `main.py`.

1. Pengguna mengisi path. Kosong berarti `test_workspace/` di samping `main.py`.
2. `scan_directory` mengembalikan satu baris per file: path lengkap, ekstensi, saran kategori, dan tanda bahwa `.txt` atau `.md` wajib dibaca.
3. Setiap baris menjadi satu percakapan baru. Konteksnya sengaja pendek supaya model 7B tidak kehilangan instruksi.
4. Agen boleh memanggil tool sendiri. `recursion_limit` satu file adalah 12.
5. Verifier tanpa model mengecek apakah nama file itu masih ada di akar. Kalau masih, agen diminta memanggil `move_file` lagi, paling banyak dua kali.
6. Laporan akhir menandai setiap file `OK` atau `GAGAL`, lalu mengulang daftar file yang masih tertinggal di akar.

Prompt sistem di `agent.py` menyuruh model mengikuti saran kategori dari hasil scan, membaca `.txt` dan `.md` sebelum meringkas, dan tidak menebak isi. Ringkasan yang diharapkan satu kalimat, dari teks yang benar-benar dibaca.

Model agen: `ChatOllama`, `qwen2.5:7b`, `temperature=0`, `num_ctx=8192`.

### Tool

`scan_directory(folder_path)` hanya membaca satu tingkat. Folder kosong mengembalikan kalimat bahwa tidak ada file untuk dirapikan.

`read_text_file(file_path)` hanya menerima `.txt` dan `.md`. File lain ditolak. Isi dipotong di 1000 karakter. Encoding yang rusak diabaikan per karakter.

`move_file(source_path, category)` hanya menerima kategori tetap:

`Documents`, `Images`, `Videos`, `Audio`, `Code`, `Data`, `Archives`, `Others`.

Kategori lain ditolak dan file tidak bergerak. Folder tujuan dibuat kalau belum ada. Kalau nama yang sama sudah ada di tujuan, file dilewati. Isi yang lama tidak ditimpa, dan file baru tetap di tempatnya. Kalau berhasil, kembaliannya `{nama} dipindahkan ke {kategori}/`.

Agen ini tidak menulis `.move_log.json` dan tidak punya undo. Mengembalikan demo hanya lewat `reset_workspace.py`, dan itu menghapus seluruh `test_workspace/`.

## Jalur organizer isi

`content_organizer.py` mengerjakan klasifikasi. Dashboard dan CLI-nya memakai fungsi yang sama.

### Ekstraksi teks

`extract_text` hanya mengisi cuplikan untuk empat jenis file.

| Ekstensi | Cara baca | Batas sebelum dipotong |
|---|---|---|
| `.txt`, `.md` | UTF-8, kesalahan diabaikan | Empat kali panjang cuplikan, lalu dipotong |
| `.pdf` | `pypdf`, tiga halaman pertama | Teks halaman digabung |
| `.docx` | `python-docx`, 40 paragraf pertama | Teks paragraf digabung |

Jenis lain, file rusak, atau hasil kosong mengembalikan string kosong. Spasi berlebih diratakan. Panjang akhir mengikuti `SNIPPET_CHARS`, bawaan 800 karakter. Di dashboard, slider cuplikan berjalan dari 200 sampai 2000, langkah 100.

### Klasifikasi

Kalau cuplikan tidak kosong, satu panggilan terstruktur ke Ollama menghasilkan `FileAnalysis`: kategori, confidence antara 0 dan 1, dan ringkasan satu sampai dua kalimat berbahasa Indonesia. Kategori harus tepat satu dari daftar yang diberikan pengguna. Pencocokan nama kategori tidak memedulikan huruf besar.

Dua kondisi mengirim file ke folder `Perlu Ditinjau`.

- Nama kategori dari model tidak ada di daftar.
- Confidence di bawah ambang. Bawaan `MIN_CONFIDENCE` adalah 0.6. Dashboard mengubahnya lewat slider 0 sampai 1, langkah 0.05.

Kalau panggilan model gagal, hasilnya juga `Perlu Ditinjau` dengan confidence 0 dan ringkasan yang memuat pesan gagal.

Kalau cuplikan kosong, kategori diambil dari aturan ekstensi dengan confidence 1.0 dan tanpa ringkasan. Tidak ada panggilan model. `.txt` yang kosong tetap jatuh ke `Documents` lewat aturan ekstensi, karena tidak ada teks yang bisa dikirim.

Usulan kategori memakai paling banyak delapan file yang berhasil diekstrak, masing-masing 300 karakter. Model diminta mengusulkan 3 sampai 8 nama folder yang singkat. Di CLI, pengguna bisa menerima usulan itu atau mengetik daftar baru. Daftar kosong menjadi satu kategori, `Dokumen Umum`.

### CLI content organizer

```bash
python content_organizer.py
python content_organizer.py /path/ke/folder
```

Tanpa argumen, path bawaan adalah `./test_workspace`, lalu program menanyakan path. Urutannya: pilih kategori, analisis semua file tanpa memindahkan apa pun, tampilkan rencana, minta konfirmasi `y`. Selain `y`, tidak ada file yang pindah. Kalau dilanjutkan, setiap pemindahan dicatat di `{folder}/.move_log.json`.

### Dashboard

Halaman memakai Streamlit, layout lebar, sidebar disembunyikan. Saat pertama dibuka, kolom path kosong. Placeholder-nya:

`Pilih folder atau masukan path folder yang ingin dirapihkan`

Tidak ada pengalihan otomatis ke `test_workspace`.

Bagian atas kartu adalah hero biru dengan merek Organizer, tautan jangkar File, Kategori, Analisis, dan Riwayat, serta tombol Reset folder. Judulnya "Rapikan folder, powered by AI". Di bawahnya ada kolom path dan tombol ikon folder.

Di macOS, tombol itu menjalankan `osascript` dengan dialog `choose folder`. Membatalkan dialog tidak menampilkan peringatan. Kalau pemilih gagal, muncul peringatan untuk menempel path. Di sistem lain, pemilih memakai tkinter. Lingkungan virtual proyek ini tidak memuat `_tkinter`, jadi di luar macOS tombol itu bisa jatuh ke peringatan yang sama. Path tetap bisa diketik.

Path yang tidak valid menampilkan pesan dari `set_workspace` dan tidak mengubah daftar file. Mengganti folder yang aktif menghapus rencana analisis yang sedang tersimpan.

Angka di bawah hero adalah jumlah file lepas dan jumlah kategori yang sudah diketik. Belum ada path berarti jumlah file nol.

Pengaturan analisis ada di tiga kolom: model Ollama, ambang confidence, dan panjang cuplikan. Daftar model diambil dari paket Python `ollama` kalau terpasang dan daemon-nya menjawab. Kalau tidak, pilihannya `qwen2.5:7b` dan `qwen3.5:9b`.

Tabel file menampilkan nama, tipe, ukuran dalam KB, dan jalur keputusan. `.txt`, `.md`, `.pdf`, dan `.docx` ditandai "LLM (isi file)". Sisanya "Aturan ekstensi".

Kategori bisa diketik sendiri, dipisah koma, atau diminta dari model lewat tombol usulan. Analisis tidak bisa dimulai sebelum ada file dan ada sedikitnya satu kategori.

Selama analisis, progress menampilkan nama file dan kategori sementaranya. Selesai, rencana muncul sebagai tabel yang bisa diedit.

- Centang `Pindah` bisa dihilangkan untuk melewati file.
- Kategori bisa diganti dari dropdown. Isinya gabungan kategori pengguna, `Perlu Ditinjau`, `Others`, kunci aturan ekstensi, dan kategori yang sudah ada di rencana.
- Nama file, confidence, metode, waktu, dan ringkasan tidak bisa diedit.
- Grafik batang menghitung file yang masih dicentang per kategori.

Empat metrik menyertai rencana: waktu total, rata-rata detik per file yang lewat LLM, jumlah file LLM dibanding seluruh file, dan jumlah `Perlu Ditinjau`.

Pemindahan membutuhkan centang "Saya sudah memeriksa rencana di atas". Setiap keberhasilan ditambah ke log. Log lama ditimpa. Halaman kemudian dimuat ulang. File yang gagal tidak menggagalkan file lain, dan pesan gagalnya tetap tampil.

Setelah ada file yang berhasil dipindahkan, bagian Laporan pemindahan muncul. Ringkasannya menyebut folder yang baru dibuat dan jumlah file di setiap folder tujuan. Tombol **Unduh laporan** mengunduh `laporan-pemindahan.md`. Isi berkas itu: folder yang dibuat pada pemindahan ini, lalu daftar lengkap berkas di setiap folder tujuan. Berkas yang baru dipindahkan ditandai "dipindahkan sekarang". Berkas yang sudah ada di folder itu tetap tercantum tanpa tanda. Laporan hilang dari halaman kalau folder diganti, di-reset, atau pemindahan dibatalkan.

Riwayat run hanya hidup di `session_state` selama tab itu terbuka. Isinya bisa diunduh sebagai `riwayat_run.csv`. Menutup tab mengosongkannya. Riwayat tidak menulis ke disk.

Tema di `.streamlit/config.toml` memakai latar `#c5ced6`, primer `#12315c`, teks `#12243f`, dan toolbar mode viewer. Kartu, hero, dan tipografi diatur di CSS dalam `dashboard.py`.

## Aturan ekstensi

Huruf besar tidak berpengaruh. `.MP4` dan `.mp4` sama. Yang dilihat hanya sufiks terakhir, jadi `laporan.final.pdf` adalah `.pdf`, dan `arsip.tar.gz` adalah `.gz`.

`tools.py` dan `content_organizer.py` memakai peta yang sama, dengan satu perbedaan: `.ipynb` ada di Code pada `tools.py`, dan tidak ada di peta content organizer. Di organizer, `.ipynb` masuk `Others`.

### Documents

`.txt` `.md` `.pdf` `.doc` `.docx` `.ppt` `.pptx` `.rtf` `.odt`

Di organizer, aturan ini hanya dipakai kalau teks tidak bisa diambil. PDF dan DOCX yang ada teksnya mengikuti kategori pengguna.

### Images

`.png` `.jpg` `.jpeg` `.gif` `.webp` `.svg` `.bmp` `.tif` `.tiff` `.heic` `.ico`

### Videos

`.mp4` `.mov` `.m4v` `.avi` `.mkv` `.webm` `.wmv` `.flv` `.mpeg` `.mpg` `.3gp` `.m2ts` `.vob` `.ogv` `.hevc` `.hvc` `.h265` `.h264`

`.ts` dan `.mts` bukan video. Keduanya ada di Code. Transport stream video adalah `.m2ts`.

### Audio

`.mp3` `.wav` `.flac` `.aac` `.m4a` `.ogg` `.oga` `.opus` `.wma` `.aiff` `.aif` `.alac` `.mid` `.midi` `.amr`

### Code

`.py` `.js` `.ts` `.tsx` `.mts` `.cts` `.jsx` `.java` `.c` `.cpp` `.h` `.html` `.css`

Ditambah `.ipynb` hanya di `tools.py`.

### Data

`.csv` `.tsv` `.xlsx` `.xls` `.json` `.xml`

CSV dan spreadsheet tidak lagi masuk Documents.

### Archives

`.zip` `.rar` `.tar` `.gz` `.bz2` `.7z`

### Others

Semua sufiks yang tidak ada di peta, termasuk file tanpa ekstensi.

## Pemindahan di content organizer

`safe_move` menyelesaikan path sumber lebih dulu. Symlink yang mengarah ke luar folder ditolak, dan berkas di luar itu tidak berubah. Nama kategori dibersihkan dari karakter `\ / : * ? " < > |`. Nama yang kosong setelah dibersihkan menjadi `Perlu Ditinjau`. Karena garis miring dihapus, kategori seperti `../../tmp` menjadi nama folder `....tmp` di dalam folder kerja, bukan path di luar.

Kalau tujuan sudah ada, file tidak ditimpa. Nama baru memakai `{nama}_{angka}{ekstensi}`, mulai dari 1. Isi file lama tetap di nama aslinya.

`tools.move_file` tidak menambahkan akhiran. Nama yang bentrok dilewati.

## Undo dan reset

Log undo berbentuk daftar JSON. Setiap entri punya `from` (path sebelum pindah) dan `to` (path sesudah pindah).

`undo_moves` membaca log, memproses dari entri terakhir, dan hanya memindahkan kalau kedua path berada di dalam folder kerja. Tujuan tidak boleh sudah ada. Folder tujuan dibuat kalau perlu. Setelah file kembali, folder kategori yang kosong dihapus. Log kemudian dihapus. Undo kedua pada log yang sudah hilang mengembalikan 0. Entri yang JSON-nya rusak membuat fungsi mengembalikan 0 tanpa memindahkan apa pun. Entri yang mengarah ke luar folder diabaikan.

Dashboard punya dua tombol yang berbeda.

**Reset folder**, di hero, mengikuti path yang sedang terisi dan tidak mengubah isi kolom itu.

- Path kosong menampilkan placeholder sebagai error.
- Path yang sama dengan `test_workspace/` proyek menjalankan `reset_workspace.py`.
- Path lain memanggil `undo_moves`. Kalau tidak ada log, pesannya menyatakan tidak ada pemindahan yang bisa di-reset.

**Kembalikan pemindahan terakhir**, di bagian bawah, hanya muncul kalau folder aktif punya `.move_log.json`. Tombol itu selalu memakai `undo_moves`, termasuk untuk folder demo.

`reset_workspace.py` menghapus `test_workspace/` seluruhnya, lalu menyalin `test_workspace_backup/`. File yang dibuat di dalam demo setelah backup, dan subfolder hasil percobaan, ikut hilang. Salinan cadangan tidak diubah.

Isi cadangan:

| Berkas | Isi |
|---|---|
| `catatan_kuliah.txt` | Satu kalimat tentang agent, tool, dan context engineering. |
| `ide_hackathon.md` | Ide agent lokal untuk merapikan folder. |
| `script_python.py` | `print('halo dari script python')` |
| `laporan.pdf` | PDF dummy. |
| `arsip_tugas.zip` | Arsip dummy. |
| `data_mentah.csv` | Satu baris teks `data dummy`. |

`test_workspace/` yang ada di kerja sekarang boleh sudah berbeda dari cadangan, karena folder itu dipakai untuk percobaan.

## Pengujian

Kedua skenario tidak memanggil Ollama. Yang diukur adalah aturan ekstensi, pemindahan, undo, dan penolakan path. Keakuratan kategori yang dipilih model untuk isi teks belum diukur.

Skenario dijalankan 14 November 2026 pada folder sementara. Folder itu dihapus setelah setiap kasus. Angka di bawah berasal dari `tests/accuracy_scale_report.json` dan `tests/accuracy_recovery_report.json`.

### Kategori dan pemindahan

Ground truth ditulis di skrip uji, terpisah dari peta di kode. Campuran mencakup dokumen, gambar, video (termasuk `.mov` dan `.hvc`), audio, kode, data, arsip, dan ekstensi yang tidak dikenal. Sebagian sufiks memakai huruf besar.

| File | Mesin | Klasifikasi benar | Mendarat benar | Sisa di akar | Keluar folder | Waktu pindah |
|---|---|---|---|---|---|---|
| 100 | tools.py | 100 / 100 | 100 / 100 | 0 | 0 | 0,025 dtk |
| 100 | content organizer | 100 / 100 | 100 / 100 | 0 | 0 | 0,014 dtk |
| 1.000 | tools.py | 1.000 / 1.000 | 1.000 / 1.000 | 0 | 0 | 0,256 dtk |
| 1.000 | content organizer | 1.000 / 1.000 | 1.000 / 1.000 | 0 | 0 | 0,126 dtk |
| 10.000 | tools.py | 10.000 / 10.000 | 10.000 / 10.000 | 0 | 0 | 2,634 dtk |
| 10.000 | content organizer | 10.000 / 10.000 | 10.000 / 10.000 | 0 | 0 | 1,394 dtk |

Dua mesin tidak berbeda kategori pada file mana pun di uji ini. Keduanya menolak file yang berada di luar folder. Laju pemindahan sekitar 3.800 file per detik untuk `tools.py` dan sekitar 7.200 sampai 7.900 untuk content organizer, pada 10.000 file.

### Undo, benturan, dan batas

Setiap file punya isi unik. Setelah pindah, byte-nya dibandingkan. Setelah undo, byte di path asal dibandingkan lagi. Folder kategori kosong hilang, dan log terhapus.

| File | Mesin | Isi utuh setelah undo | Undo kedua | Waktu pindah + cek + undo |
|---|---|---|---|---|
| 100 | tools.py | 100 / 100 | 0 | 0,074 dtk |
| 100 | content organizer | 100 / 100 | 0 | 0,059 dtk |
| 1.000 | tools.py | 1.000 / 1.000 | 0 | 0,727 dtk |
| 1.000 | content organizer | 1.000 / 1.000 | 0 | 0,566 dtk |
| 10.000 | tools.py | 10.000 / 10.000 | 0 | 7,379 dtk |
| 10.000 | content organizer | 10.000 / 10.000 | 0 | 5,897 dtk |

Pada 100 file dengan 10 nama yang sudah ada di tujuan, isi lama dan isi baru keduanya utuh. `tools.py` melewatkan file baru. Content organizer menyimpan file baru sebagai nama berakhiran `_1`.

Tiga belas pemeriksaan batas lulus.

- File di luar folder ditolak kedua mesin, dan isinya tidak berubah.
- Symlink yang mengarah ke luar ditolak kedua mesin.
- `tools.py` menolak kategori yang tidak ada di daftar.
- Kategori content organizer yang memuat `../` tetap menghasilkan file di dalam folder kerja.
- Akar filesystem ditolak kedua mesin.
- Scan tidak menampilkan file tersembunyi.
- `read_text_file` memotong di 1000 karakter.
- `read_text_file` menolak selain `.txt` dan `.md`.
- Log undo yang mengarahkan tujuan ke luar folder tidak menulis berkas apa pun.
- Folder kosong dilaporkan kosong.
- File yang tidak ada tidak dipindahkan.

## Ketergantungan

`requirements.txt` mengunci paket agen:

- `langchain==1.4.9`
- `langchain-core==1.7.6`
- `langchain-ollama==1.1.0`
- `langgraph==1.2.20`

Dashboard dan ekstraksi dokumen membutuhkan paket yang sudah dipasang di `venv` tetapi belum ditulis di `requirements.txt`: `streamlit`, `pandas`, `pypdf`, dan `python-docx`. Mendaftar model yang terpasang membutuhkan paket Python `ollama`. Tanpa paket itu, dashboard tetap membuka dua nama model bawaan. Daemon Ollama tetap diperlukan saat analisis LLM benar-benar dijalankan.

## Batas yang sengaja ada

- Tidak ada pemindaian rekursif.
- Agen CLI tidak membaca PDF atau DOCX, dan tidak bisa undo per file.
- Reset demo bersifat merusak: seluruh `test_workspace/` diganti salinan cadangan.
- Reset folder biasa hanya mengembalikan apa yang tercatat di log terakhir. Pemindahan manual di luar aplikasi tidak bisa dibatalkan dari tombol itu.
- Dua mesin berbeda pada nama yang bentrok dan pada `.ipynb`.
- Kategori berbasis isi baru akurat sejauh model dan cuplikan yang dikirim. Uji otomatis belum mengukur bagian itu.
- Riwayat perbandingan model hilang ketika sesi Streamlit berakhir.
- Perubahan kode Python tidak selalu langsung terlihat di dashboard yang sudah berjalan. Proses Streamlit perlu dijalankan ulang.
