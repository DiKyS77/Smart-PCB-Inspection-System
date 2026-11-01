"""Indonesian/English interface text; stored data and form values stay unchanged."""
import re
from urllib.parse import urlencode, urlsplit

from flask import abort, has_request_context, redirect, request, session


_PAIRS = """
Dashboard|Dasbor
Admin Dashboard|Dasbor Admin
Administration|Administrasi
Administrator|Administrator
Technician|Teknisi
Technicians|Teknisi
Technician workspace|Ruang kerja teknisi
Inspection workspace|Ruang kerja inspeksi
PCB Inspection Management|Manajemen Inspeksi PCB
Main navigation|Navigasi utama
Workspace navigation|Navigasi ruang kerja
Account menu|Menu akun
Language|Bahasa
Change language|Ganti bahasa
Settings|Pengaturan
Logout|Keluar
User|Pengguna
Menu|Menu
Open navigation|Buka navigasi
Close navigation|Tutup navigasi
Close workspace navigation|Tutup navigasi ruang kerja
Records table, scroll horizontally to see all columns|Tabel catatan, geser mendatar untuk melihat semua kolom
Sign in|Masuk
Sign in — PCB Inspect|Masuk — PCB Inspect
Welcome back.|Selamat datang kembali.
Sign in to continue your work.|Masuk untuk melanjutkan pekerjaan Anda.
Your inspection|Ruang kerja
workspace.|inspeksi Anda.
Review boards, record defects, and keep track of the work that follows.|Periksa PCB, catat cacat, dan pantau penanganan hasil inspeksi.
SMART PCB INSPECTION SYSTEM|SISTEM INSPEKSI PCB CERDAS
Smart PCB Inspection System|Sistem Inspeksi PCB Cerdas
ID or username|ID atau nama pengguna
Enter your ID or username|Masukkan ID atau nama pengguna
Password|Kata sandi
Enter your password|Masukkan kata sandi
Show password|Tampilkan kata sandi
Hide password|Sembunyikan kata sandi
Use the account provided by your administrator.|Gunakan akun yang diberikan oleh administrator Anda.
PCB Inspect — Circuit Board Inspection|PCB Inspect — Inspeksi Papan Sirkuit
How it works|Cara kerja
For everyday PCB checks|Untuk pemeriksaan PCB sehari-hari
PCB checks,|Pemeriksaan PCB,
all in one place.|dalam satu tempat.
Upload a board image, review defects, and keep a record of what needs attention. Everything you need for the next inspection.|Unggah gambar PCB, tinjau cacat, dan catat bagian yang perlu ditangani. Semua kebutuhan inspeksi tersedia dalam satu tempat.
Start an inspection|Mulai inspeksi
A little less paperwork. A clearer inspection history.|Pencatatan lebih praktis. Riwayat inspeksi lebih jelas.
Board inspection|Inspeksi PCB
EXAMPLE / 01|CONTOH / 01
Open circuit|Jalur terputus
Visual inspection|Inspeksi visual
Locate defects. Review the details.|Temukan cacat. Tinjau detailnya.
Illustrative preview|Pratinjau ilustrasi
Illustration of PCB traces with a highlighted open circuit. This is an example, not a live inspection.|Ilustrasi jalur PCB dengan jalur terputus yang disorot. Ini adalah contoh, bukan inspeksi langsung.
Inspection workflow|Alur inspeksi
Choose your board.|Pilih PCB Anda.
Add a PCB ID and upload an image for inspection.|Masukkan ID PCB dan unggah gambar untuk diperiksa.
Review the results.|Tinjau hasilnya.
Review detected defects and their locations on the board.|Tinjau cacat yang terdeteksi dan lokasinya pada PCB.
Track the next step.|Pantau langkah berikutnya.
Update follow-up status, revisit records, and export reports.|Perbarui status penanganan, lihat kembali catatan, dan ekspor laporan.
Overview|Ringkasan
Overview of your PCB defect detection activity.|Ringkasan aktivitas deteksi cacat PCB Anda.
Real-time overview of technician performance and PCB inspection quality.|Ringkasan kinerja teknisi dan kualitas inspeksi PCB terkini.
Admin Dashboard — PCB Defect Detection|Dasbor Admin — Deteksi Cacat PCB
Dashboard — PCB Defect Detection|Dasbor — Deteksi Cacat PCB
Total Detections|Total Deteksi
All time|Sepanjang waktu
All detections|Semua deteksi
PCB Inspected|PCB Diperiksa
Registered Technicians|Teknisi Terdaftar
Active Technicians|Teknisi Aktif
Registered|Terdaftar
Active|Aktif
Inactive|Tidak aktif
Registered users|Pengguna terdaftar
Top Defect|Cacat Terbanyak
Most frequent type|Jenis paling sering ditemukan
Most common defect|Cacat paling umum
Most frequent|Paling sering ditemukan
Defect Summary|Ringkasan Cacat
Count and percentage per defect type|Jumlah dan persentase tiap jenis cacat
Count and percentage per type|Jumlah dan persentase tiap jenis
Defect Distribution|Distribusi Cacat
Defect Breakdown|Rincian Cacat
Proportion by defect type|Proporsi berdasarkan jenis cacat
Proportion of each defect type|Proporsi tiap jenis cacat
Proportion of each defect type — total|Proporsi tiap jenis cacat — total
Percentage breakdown of each defect type|Rincian persentase tiap jenis cacat
% of total detections|% dari total deteksi
Daily Detections|Deteksi Harian
Daily detection count over time|Jumlah deteksi harian dari waktu ke waktu
Detection Trend|Tren Deteksi
Detection volume over time|Jumlah deteksi dari waktu ke waktu
Insights|Wawasan
Key observations from your detection history|Temuan utama dari riwayat deteksi Anda
Defect types found|Jenis cacat ditemukan
detected in your inspection history.|terdeteksi dalam riwayat inspeksi Anda.
is the most frequent defect in your detections.|merupakan cacat yang paling sering ditemukan.
Top 5 Technicians|5 Teknisi Teratas
Ranked by detection count|Diurutkan berdasarkan jumlah deteksi
Recent Activity|Aktivitas Terbaru
Recent Detections|Deteksi Terbaru
Latest detection|Deteksi terakhir
Latest 6 detections across all technicians|6 deteksi terbaru dari seluruh teknisi
Last 6 detection results|6 hasil deteksi terakhir
View All|Lihat Semua
View Report|Lihat Laporan
No detections yet.|Belum ada deteksi.
No detection yet|Belum ada deteksi
No defect data available.|Belum ada data cacat.
No defect data available yet.|Belum ada data cacat.
No data to display yet.|Belum ada data untuk ditampilkan.
No defects recorded yet.|Belum ada cacat yang tercatat.
No technician data yet.|Belum ada data teknisi.
No defect data yet. Run a detection to see the breakdown here.|Belum ada data cacat. Jalankan deteksi untuk melihat rinciannya di sini.
No detection history yet.|Belum ada riwayat deteksi.
Run your first detection →|Jalankan deteksi pertama →
Detection|Deteksi
History|Riwayat
Report|Laporan
Reports|Laporan
Detection — PCB Defect Detection|Deteksi — Deteksi Cacat PCB
History — PCB Defect Detection|Riwayat — Deteksi Cacat PCB
Report — PCB Defect Detection|Laporan — Deteksi Cacat PCB
Admin Report — PCB Defect Detection|Laporan Admin — Deteksi Cacat PCB
Detection Detail — PCB Defect Detection|Detail Deteksi — Deteksi Cacat PCB
Manage User — PCB Defect Detection|Kelola Pengguna — Deteksi Cacat PCB
New inspection|Inspeksi baru
Your inspections|Inspeksi Anda
Upload a PCB image to run YOLO defect detection.|Unggah gambar PCB untuk menjalankan deteksi cacat YOLO.
Upload Image|Unggah Gambar
Upload|Unggah
PCB ID|ID PCB
Original Image|Gambar Asli
Original|Asli
Image|Gambar
File Name|Nama File
Browse File|Pilih File
Drag|Seret
drop or click to choose|lepaskan atau klik untuk memilih
JPG / JPEG / PNG — max 10 MB|JPG / JPEG / PNG — maks. 10 MB
Supports JPG, PNG, JPEG|Mendukung JPG, PNG, JPEG
Max size 10 MB|Ukuran maks. 10 MB
Preview|Pratinjau
Run Detection|Jalankan Deteksi
Detect Again|Deteksi Ulang
Inspection details|Detail inspeksi
Inspection history|Riwayat inspeksi
Detection History|Riwayat Deteksi
Detection Log|Log Deteksi
Detection Result|Hasil Deteksi
Detection result|Hasil deteksi
Detection Status|Status Deteksi
Defect Type|Jenis Cacat
Result|Hasil
Image not available|Gambar tidak tersedia
Not available|Tidak tersedia
No detection records found|Tidak ditemukan catatan deteksi
No data for the selected period.|Tidak ada data pada periode yang dipilih.
Date|Tanggal
Time|Waktu
Date & Time|Tanggal & Waktu
Status|Status
Action|Aksi
Actions|Aksi
Detail|Detail
Back to History|Kembali ke Riwayat
Full result for detection record #|Hasil lengkap untuk catatan deteksi #
Record ID|ID Catatan
Recorded on|Dicatat pada
Last run on|Terakhir dijalankan pada
Resolution|Resolusi
Objects detected|Objek terdeteksi
Preprocess|Praproses
Preprocessing|Prapemrosesan
Postprocess|Pascaproses
Inference|Inferensi
Scanning|Memindai
AI is analyzing your PCB. Please wait.|AI sedang menganalisis PCB Anda. Mohon tunggu.
Uploading image...|Mengunggah gambar...
Resizing to 640×640...|Mengubah ukuran menjadi 640×640...
Normalizing pixel values...|Menormalisasi nilai piksel...
Extracting feature maps...|Mengekstrak peta fitur...
Running YOLO inference...|Menjalankan inferensi YOLO...
Finalizing results...|Menyelesaikan hasil...
View steps|Lihat tahapan
How the inspection works|Cara kerja inspeksi
Resize|Ubah ukuran
Resized|Diubah ukurannya
Resized 640 × 640|Diubah menjadi 640 × 640
Original vs resized input to the model|Gambar asli dan gambar masukan model yang telah diubah ukurannya
Normalize|Normalisasi
Normalized|Dinormalisasi
Image Normalization|Normalisasi Gambar
Normalized: 0.0 – 1.0|Dinormalisasi: 0,0 – 1,0
Raw pixel: 0 – 255|Piksel asli: 0 – 255
Pixel values scaled before entering YOLOv8|Nilai piksel diskalakan sebelum masuk ke YOLOv8
Dividing each pixel by 255 ensures uniform scale for stable model inference.|Pembagian tiap piksel dengan 255 menghasilkan skala seragam untuk inferensi model yang stabil.
Feature|Fitur
Features|Fitur
Feature Map|Peta Fitur
Extraction|Ekstraksi
Backbone feature extraction output (before detection head)|Hasil ekstraksi fitur backbone sebelum tahap deteksi
Bright areas indicate high feature response — likely defect candidates.|Area terang menunjukkan respons fitur yang tinggi dan dapat menjadi kandidat lokasi cacat.
Cropped Defect Regions|Potongan Area Cacat
Each detected bounding box cropped from the original image|Setiap kotak deteksi dipotong dari gambar asli
YOLOv8 inference output with bounding boxes|Hasil inferensi YOLOv8 beserta kotak deteksi
Upload a PCB image above and click|Unggah gambar PCB di atas lalu klik
to start.|untuk memulai.
Filter|Filter
Filter Report|Filter Laporan
Select date range to narrow down results|Pilih rentang tanggal untuk membatasi hasil
From|Dari
To|Sampai
Until|Hingga
Download CSV|Unduh CSV
Download XLSX|Unduh XLSX
Statistics and summary of PCB defect detection results.|Statistik dan ringkasan hasil deteksi cacat PCB.
Detection history, defect breakdown, and CSV export.|Riwayat deteksi, rincian cacat, dan ekspor CSV.
Most recent 15 detections|15 deteksi terbaru
for the selected date range|pada rentang tanggal yang dipilih
for the selected date range.|pada rentang tanggal yang dipilih.
Filter PCB units|Filter unit PCB
Search PCB ID or type|Cari PCB ID atau jenis
Example: PCB-001|Contoh: PCB-001
Example: PCB-01|Contoh: PCB-01
PCB type|Jenis PCB
All types|Semua jenis
All statuses|Semua status
All verifications|Semua verifikasi
Work status|Status pengerjaan
Latest inspection verification|Verifikasi inspeksi terbaru
Apply filters|Terapkan filter
Reset|Reset
Download filtered CSV|Unduh CSV sesuai filter
Status summaries follow the filters. Verification in this list applies only to the latest inspection of each PCB.|Ringkasan status mengikuti filter. Verifikasi di daftar ini hanya untuk inspeksi terbaru setiap PCB.
PCB units ·|Unit PCB ·
PCB / Technician|PCB / Teknisi
Work progress|Pengerjaan
Latest AI result|Hasil AI terbaru
Technician verification|Verifikasi teknisi
Open details →|Buka detail →
No PCB units match the filters. Units appear automatically when a technician saves an inspection. Previous inspections are included.|Belum ada unit sesuai filter. Unit otomatis muncul setelah teknisi menyimpan inspeksi. Data inspeksi lama juga ikut ditampilkan.
Search PCB IDs, track work, and review technician verification. Each row represents one technician's PCB; reinspections stay connected.|Telusuri PCB ID, pantau pekerjaan, dan lihat verifikasi teknisi. Satu baris adalah satu PCB milik satu teknisi; inspeksi ulang tetap terhubung.
Manage PCB types|Kelola jenis PCB
Units use PCB IDs assigned by technicians. Administrators can assign PCB types in the unit details.|Identitas unit memakai PCB ID dari teknisi. Jenis PCB dapat ditentukan admin melalui detail unit.
Add PCB type|Tambah jenis PCB
Temperature Sensor PCB|PCB Sensor Suhu
Type name|Nama jenis
Description|Deskripsi
Save|Simpan
PCB type list|Daftar jenis PCB
No PCB types yet.|Belum ada jenis PCB.
Completed means the inspection work is finished; it does not guarantee a defect-free PCB. AI results and human corrections are recorded separately.|Selesai berarti tindak lanjut selesai, bukan jaminan PCB bebas cacat. Hasil AI dan koreksi manusia dicatat terpisah.
No PCB ID|PCB tanpa ID
Technician unavailable|Teknisi tidak tersedia
Type not assigned|Jenis belum ditentukan
Priority|Prioritas
Low|Rendah
Medium|Sedang
High|Tinggi
Waiting|Menunggu
In progress|Dikerjakan
Reinspection required|Perlu Inspeksi Ulang
Completed|Selesai
Not reviewed|Belum ditinjau
Under review|Sedang diperiksa
Repair required|Perlu perbaikan
Not verified|Belum diverifikasi
Confirmed|Dikonfirmasi
Corrected|Dikoreksi
Inspection Status|Status Tindak Lanjut
Save inspection updates|Simpan pembaruan inspeksi
My PCB inspections|PCB & Tindak Lanjut Saya
Inspection #|Inspeksi #
linked inspections · Unit status:|inspeksi terhubung · Status unit:
Manage inspection|pengelolaan inspeksi
Grouping|Pengelompokan
Type|Jenis
Verification|Verifikasi
Decision|Keputusan
Correct main defect type (for corrections)|Jenis cacat utama yang benar (untuk koreksi)
Select when correcting|Pilih jika mengoreksi
Reason / notes (required for corrections)|Alasan / catatan (wajib untuk koreksi)
Save verification|Simpan verifikasi
Inspect again →|Lakukan inspeksi ulang →
Action notes / reinspection reason|Catatan tindakan / alasan inspeksi ulang
Verify the latest inspection before completing the unit. A new inspection after Completed or Reinspection required reopens the unit as In progress.|Untuk status Selesai, hasil inspeksi terbaru harus sudah diverifikasi teknisi. Inspeksi baru setelah Selesai atau Perlu Inspeksi Ulang akan membuka kembali status Dikerjakan.
Change history|Jejak perubahan
Shows who made changes, when, and the before/after values. Verification never replaces the original AI prediction.|Menampilkan pelaku, waktu, serta nilai sebelum dan sesudah perubahan. Prediksi AI asli tidak diganti oleh verifikasi.
No changes recorded yet.|Belum ada perubahan yang dicatat.
Before|Sebelum
After|Sesudah
Change|Perubahan
By|Oleh
No inspections yet.|Belum ada inspeksi.
Not assigned|Belum ditentukan
Technician notes:|Catatan teknisi:
Verification saved again without content changes.|Verifikasi disimpan kembali tanpa perubahan isi.
· Correction result:|· Hasil koreksi:
· inspection #|· inspeksi #
to review results, update status, and verify AI predictions.|untuk melihat hasil, memperbarui status, dan memverifikasi prediksi AI.
PCB inspection results — click|Hasil inspeksi PCB — klik
Search PCB ID or work status…|Cari PCB ID atau status tindakan…
Search by PCB ID, defect type, or inspection status|Cari berdasarkan PCB ID, jenis cacat, atau status tindak lanjut
No records match this PCB ID or keyword.|Tidak ada catatan yang cocok dengan PCB ID atau kata kunci tersebut.
Add, edit, activate, or remove technician accounts.|Tambah, ubah, aktifkan, atau hapus akun teknisi.
Add Technician|Tambah Teknisi
Edit Technician|Ubah Teknisi
User List|Daftar Pengguna
Username|Nama pengguna
Role|Peran
Add|Tambah
Edit|Ubah
Delete|Hapus
Activate|Aktifkan
Deactivate|Nonaktifkan
Cancel|Batal
Close|Tutup
Save Changes|Simpan Perubahan
Enter username|Masukkan nama pengguna
Search username…|Cari nama pengguna…
Re-enter password|Masukkan ulang kata sandi
Confirm Password|Konfirmasi Kata Sandi
Confirm new password|Konfirmasi kata sandi baru
Leave blank to keep current password|Biarkan kosong untuk mempertahankan kata sandi saat ini
Letters + numbers required|Wajib berisi huruf dan angka
No users match your search.|Tidak ada pengguna yang cocok dengan pencarian.
No users registered yet.|Belum ada pengguna terdaftar.
Back to workspace|Kembali ke ruang kerja
Change password|Ganti kata sandi
Please change your account password securely.|Ganti kata sandi akun Anda dengan aman.
Old Password|Kata Sandi Lama
New Password|Kata Sandi Baru
Save Password|Simpan Kata Sandi
Incorrect ID or password.|ID atau kata sandi salah.
ID must be numeric.|ID harus berupa angka.
Username cannot be empty.|Nama pengguna tidak boleh kosong.
Password and confirmation do not match.|Kata sandi dan konfirmasi tidak cocok.
Passwords do not match.|Kata sandi tidak cocok.
Password and confirmation are required.|Kata sandi dan konfirmasi wajib diisi.
Password must contain letters and numbers.|Kata sandi harus berisi huruf dan angka.
Password must contain letters and numbers!|Kata sandi harus berisi huruf dan angka!
Password must be at least 6 characters!|Kata sandi minimal 6 karakter!
Password confirmation does not match!|Konfirmasi kata sandi tidak cocok!
Technician updated successfully.|Data teknisi berhasil diperbarui.
Technician deleted successfully.|Teknisi berhasil dihapus.
Technician added successfully.|Teknisi berhasil ditambahkan.
Technician activated successfully.|Teknisi berhasil diaktifkan.
Technician deactivated successfully.|Teknisi berhasil dinonaktifkan.
An error occurred while updating the technician.|Terjadi kesalahan saat memperbarui teknisi.
An error occurred while updating the technician status.|Terjadi kesalahan saat memperbarui status teknisi.
You cannot delete your own account.|Anda tidak dapat menghapus akun sendiri.
Please enter a PCB ID.|Masukkan ID PCB.
PCB ID must be 100 characters or fewer.|ID PCB maksimal 100 karakter.
Unsupported file type. Use PNG, JPG, or JPEG.|Jenis file tidak didukung. Gunakan PNG, JPG, atau JPEG.
Could not read the uploaded image.|Gambar yang diunggah tidak dapat dibaca.
Detection failed. Please try again.|Deteksi gagal. Silakan coba lagi.
Detection completed, but the result could not be saved.|Deteksi selesai, tetapi hasilnya gagal disimpan.
Please select a start date or end date.|Pilih tanggal awal atau tanggal akhir.
Old password is incorrect.|Kata sandi lama salah.
File must be JPG, JPEG, or PNG.|File harus berformat JPG, JPEG, atau PNG.
Maximum file size is 10 MB.|Ukuran file maksimal 10 MB.
Original PCB image not found. Please upload it again.|Gambar asli PCB tidak ditemukan. Unggah gambar kembali.
Select an image to register a new PCB ID.|Pilih gambar untuk mendaftarkan PCB ID baru.
The image must be PNG or JPEG.|Format gambar harus PNG atau JPEG.
This PCB ID is already registered. Remove the selected file to use its original saved image.|PCB ID ini sudah terdaftar. Hapus file yang dipilih agar deteksi memakai gambar awal yang tersimpan untuk ID ini.
This PCB ID is already in use, but its original image is unavailable. Use a new PCB ID or restore the original image.|PCB ID ini sudah digunakan, tetapi gambar aslinya tidak tersedia. Gunakan ID PCB baru atau pulihkan gambar aslinya.
The form expired. Reload the page and try again.|Form kedaluwarsa. Muat ulang halaman lalu coba kembali.
Name is required (maximum 100 characters); description is limited to 500 characters.|Nama wajib diisi, maksimal 100 karakter; deskripsi maksimal 500 karakter.
Data added successfully.|Data berhasil ditambahkan.
This PCB type already exists.|Nama jenis PCB sudah tersedia.
Invalid status or notes longer than 2000 characters.|Status tidak valid atau catatan melebihi 2000 karakter.
Provide a reason for reinspection.|Isi alasan inspeksi ulang.
Verify the latest inspection results before completing the unit.|Verifikasi hasil inspeksi terbaru terlebih dahulu sebelum menyelesaikan unit.
PCB type not found.|Jenis PCB tidak ditemukan.
Inspection updates saved.|Tindak lanjut berhasil disimpan.
Invalid verification or notes too long.|Verifikasi tidak valid atau catatan terlalu panjang.
Corrections require a defect type and reason.|Koreksi wajib memiliki jenis cacat dan alasan.
The correction must differ from the AI result; use Confirmed if the result is correct.|Koreksi harus berbeda dari hasil AI; gunakan Dikonfirmasi jika sesuai.
Verification saved. The original AI prediction is preserved.|Verifikasi tersimpan. Prediksi AI asli tetap dipertahankan.
Inspection update|Tindak lanjut
New inspection recorded|Inspeksi baru
Detections|Deteksi
records|catatan
record|catatan
total record|total catatan
detections|deteksi
registered|terdaftar
account|akun
type|jenis
trends|tren
inspections|inspeksi
inspection management|pengelolaan inspeksi
verification|verifikasi
unit|unit
yet.|saat ini.
No Defect|Tidak Ada Cacat
NORMAL|NORMAL
DEFECT|CACAT
missing_resistor|Resistor hilang
missing_buzzer|Buzzer hilang
mouse_bite|Cacat gerigi
spur|Tonjolan tembaga
missing_hole|Lubang hilang
short|Hubung singkat
open_circuit|Jalur terputus
spurious_copper|Sisa tembaga
Showing {start}–{end} of {total} records|Menampilkan {start}–{end} dari {total} catatan
Delete "{username}"? This cannot be undone.|Hapus "{username}"? Tindakan ini tidak dapat dibatalkan.
Please select both start date and end date.|Pilih tanggal awal dan tanggal akhir.
Start date cannot be after end date.|Tanggal awal tidak boleh melewati tanggal akhir.
Please select a start date or end date before submitting.|Pilih tanggal awal atau tanggal akhir sebelum mengirim.
Processing...|Memproses...
Unknown|Tidak diketahui
PCB unit|Unit PCB
Technician reactivated successfully.|Teknisi berhasil diaktifkan kembali.
ID already exists. Use another ID.|ID sudah digunakan. Gunakan ID lain.
An error occurred while adding the technician.|Terjadi kesalahan saat menambahkan teknisi.
Inspection ID|ID Inspeksi
Follow-up Status|Status Pengerjaan
Main AI result|Hasil AI utama
Latest verification|Verifikasi terbaru
Technician correction|Koreksi teknisi
Pagination|Navigasi halaman
Previous page|Halaman sebelumnya
Next page|Halaman berikutnya
Page {page}|Halaman {page}
"""

TRANSLATIONS = dict(line.split('|', 1) for line in _PAIRS.strip().splitlines())
_REVERSE = {value: key for key, value in TRANSLATIONS.items()}
_ALIASES = {
    'admin': ('Administrator', 'Administrator'),
    'technician': ('Technician', 'Teknisi'),
    'teknisi': ('Technician', 'Teknisi'),
    'Simpan tindak lanjut': ('Save inspection updates', 'Simpan pembaruan inspeksi'),
    'tindak lanjut': ('inspection management', 'pengelolaan inspeksi'),
    'Manajemen Inspeksi PCB — PCB Inspect': ('PCB Inspection Management — PCB Inspect', 'Manajemen Inspeksi PCB — PCB Inspect'),
    '· Manajemen Inspeksi — PCB Inspect': ('· Inspection Management — PCB Inspect', '· Manajemen Inspeksi — PCB Inspect'),
    'e.g. 1001': ('e.g. 1001', 'contoh: 1001'),
    'e.g. Adela': ('e.g. Adela', 'contoh: Adela'),
    's': ('s', ''),
    'Tanpa PCB ID': ('No PCB ID', 'Tanpa PCB ID'),
    'Tindak lanjut': ('Inspection update', 'Pembaruan inspeksi'),
    'Tindak lanjut berhasil disimpan.': ('Inspection updates saved.', 'Pembaruan inspeksi berhasil disimpan.'),
}
for _defect in ('missing_resistor', 'missing_buzzer', 'mouse_bite', 'spur',
                'missing_hole', 'short', 'open_circuit', 'spurious_copper'):
    _label = _defect.replace('_', ' ').capitalize()
    _ALIASES[_defect] = (_label, TRANSLATIONS[_defect])
    _ALIASES[_defect.replace('_', ' ')] = (_label, TRANSLATIONS[_defect])
    _ALIASES[_label.title()] = (_label.title(), TRANSLATIONS[_defect])

_MONTHS = {'Jan': 'Jan', 'Feb': 'Feb', 'Mar': 'Mar', 'Apr': 'Apr', 'May': 'Mei',
           'Jun': 'Jun', 'Jul': 'Jul', 'Aug': 'Agu', 'Sep': 'Sep', 'Oct': 'Okt',
           'Nov': 'Nov', 'Dec': 'Des', 'January': 'Januari', 'February': 'Februari',
           'March': 'Maret', 'April': 'April', 'June': 'Juni', 'July': 'Juli',
           'August': 'Agustus', 'September': 'September', 'October': 'Oktober',
           'November': 'November', 'December': 'Desember'}


def current_language():
    return session.get('language', 'id') if has_request_context() else 'id'


def translate(text, **values):
    if not isinstance(text, str):
        return text
    language = current_language()
    key = re.sub(r'\s+', ' ', text).strip()
    if key in _ALIASES:
        result = _ALIASES[key][language == 'id']
    elif language == 'id':
        result = TRANSLATIONS.get(key, text)
    else:
        result = _REVERSE.get(key, text)
    if result == text and key.endswith(':'):
        result = str(translate(key[:-1])) + ':'
    if language == 'id' and re.fullmatch(r'\d{1,2} [A-Za-z]+ \d{4}', key):
        day, month, year = key.split()
        result = f'{day} {_MONTHS.get(month, month)} {year}'
    return result.format(**values) if values else result


def init_languages(app):
    @app.context_processor
    def language_context():
        language = current_language()
        sources = set(TRANSLATIONS) | set(_REVERSE) | set(_ALIASES)
        language_next = request.full_path.rstrip('?')
        if request.method == 'POST' and request.endpoint in ('admin_report', 'technician_report'):
            dates = {name: request.form.get(name, '') for name in ('start_date', 'end_date')}
            language_next = request.path + '?' + urlencode(dates)
        return dict(_=translate, language=language, language_next=language_next,
                    browser_translations={key: translate(key) for key in sources})

    @app.post('/language')
    def set_language():
        language = request.form.get('language')
        if language not in ('id', 'en'):
            abort(400)
        session['language'] = language
        destination = request.form.get('next', '/')
        try:
            parts = urlsplit(destination)
        except ValueError:
            return redirect('/', code=303)
        if (parts.scheme or parts.netloc or not destination.startswith('/')
                or destination.startswith('//') or '\\' in destination
                or any(ord(char) < 32 for char in destination)):
            destination = '/'
        return redirect(destination, code=303)
