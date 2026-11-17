"""
Script: generate_docs_and_excel.py
Deskripsi:
  Membuat file data terstruktur dan dokumen referensi dalam berbagai format:
  1. Excel (.xlsx)      -> data/partner_settlement_directory.xlsx
  2. PDF (.pdf)         -> knowledge_base/SOP_Penanganan_Transaksi_Gagal.pdf
  3. Word (.docx)       -> knowledge_base/Kebijakan_Refund_dan_Chargeback.docx
  4. Plain Text (.txt)  -> knowledge_base/Laporan_Insiden_BCA_VA_Oktober_2024.txt

Tujuannya untuk mendukung 100% cakupan format file analitik & operasional enterprise
(SQL, CSV, Excel, PDF, DOCX, TXT).
"""

import os
import pandas as pd
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Pastikan folder tujuan ada
os.makedirs("data", exist_ok=True)
os.makedirs("knowledge_base", exist_ok=True)


def create_excel_partner_directory():
    """Membuat file Excel (.xlsx) dengan 2 sheet: Parameter Partner & Kontak NOC."""
    print("📊 1. Membuat file Excel: data/partner_settlement_directory.xlsx ...")
    
    # Sheet 1: SLA dan Limit Transaksi
    sla_data = {
        "Partner_Name": ["BCA", "MANDIRI", "BNI", "BRI", "GOPAY", "OVO", "DANA", "VISA", "MASTERCARD"],
        "Channel_Type": ["VIRTUAL_ACCOUNT", "VIRTUAL_ACCOUNT", "VIRTUAL_ACCOUNT", "VIRTUAL_ACCOUNT", "QRIS", "QRIS", "E_WALLET", "CREDIT_CARD", "CREDIT_CARD"],
        "Max_Daily_Limit_IDR": [1000000000, 1000000000, 750000000, 500000000, 20000000, 20000000, 20000000, 50000000, 50000000],
        "Timeout_Threshold_ms": [10000, 10000, 10000, 12000, 5000, 5000, 5000, 8000, 8000],
        "Settlement_Cutoff": ["23:00 WIB", "23:00 WIB", "22:00 WIB", "21:30 WIB", "Real-Time", "Real-Time", "Real-Time", "D+2", "D+2"],
        "Target_SLA_Success_Rate": ["99.5%", "99.0%", "98.5%", "98.0%", "99.5%", "99.0%", "99.0%", "99.2%", "99.2%"]
    }
    df_sla = pd.DataFrame(sla_data)

    # Sheet 2: Kontak Darurat Partner (NOC Escalation)
    contact_data = {
        "Partner_Name": ["BCA", "MANDIRI", "BNI", "BRI", "GOPAY", "OVO", "VISA"],
        "PIC_Department": ["Merchant Solution / NOC", "Digital Banking Ops", "Fintech Support", "E-Channel NOC", "Merchant Care", "Partner Integration", "Risk & Security"],
        "Email_Hotline": ["noc.gateway@bca.co.id", "support.api@bankmandiri.co.id", "merchant@bni.co.id", "callnoc@bri.co.id", "partner@gopay.com", "ops@ovo.id", "support@visa.com"],
        "Emergency_Phone": ["021-500888", "021-529977", "021-578999", "021-579888", "021-298500", "021-298600", "+1-800-847-2911"],
        "Service_Hours": ["24/7", "24/7", "24/7", "24/7", "24/7", "08:00 - 22:00", "24/7"]
    }
    df_contact = pd.DataFrame(contact_data)

    excel_path = os.path.join("data", "partner_settlement_directory.xlsx")
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df_sla.to_excel(writer, sheet_name="SLA_and_Limits", index=False)
        df_contact.to_excel(writer, sheet_name="Emergency_Contacts", index=False)
        
    print(f"   ✅ File Excel selesai dibuat di {excel_path}")


def create_pdf_sop():
    """Membuat file dokumen PDF (.pdf): SOP Penanganan Transaksi Gagal."""
    print("📄 2. Membuat file PDF: knowledge_base/SOP_Penanganan_Transaksi_Gagal.pdf ...")
    
    pdf_path = os.path.join("knowledge_base", "SOP_Penanganan_Transaksi_Gagal.pdf")
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E3A8A'),
        spaceAfter=14
    )
    heading2_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#2563EB'),
        spaceBefore=12,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['BodyText'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#1F2937'),
        spaceAfter=6
    )

    story = []

    # Judul Dokumen
    story.append(Paragraph("STANDAR OPERASIONAL PROSEDUR (SOP)", title_style))
    story.append(Paragraph("<b>Nomor Dokumen:</b> SOP-OPS-FIN-2024-V2<br/><b>Judul:</b> Penanganan Transaksi Gagal, Timeout, dan Pending<br/><b>Divisi:</b> Merchant Operations & Network Engineering<br/><b>Tanggal Efektif:</b> 1 Januari 2024", body_style))
    story.append(Spacer(1, 10))

    # Bab 1
    story.append(Paragraph("1. Tujuan dan Ruang Lingkup", heading2_style))
    story.append(Paragraph("SOP ini mengatur tata cara standar bagi tim Customer Support (L1) dan Operations Engineer (L2) dalam menangani insiden kegagalan transaksi pembayaran multi-channel (Virtual Account, QRIS, Kartu Kredit, dan E-Wallet).", body_style))

    # Bab 2: Tabel Kode Error dengan Text-Wrapping (Menggunakan Paragraph agar tidak tumpang tindih)
    story.append(Paragraph("2. Prosedur Penanganan Berdasarkan Kode Error (Error Code)", heading2_style))
    
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['BodyText'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#1F2937')
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['BodyText'],
        fontSize=8.5,
        leading=11,
        textColor=colors.whitesmoke,
        fontName='Helvetica-Bold'
    )

    raw_table_data = [
        [
            "Kode Error", 
            "Penyebab Umum", 
            "Tindakan Tim Support / L1", 
            "Eskalasi ke L2"
        ],
        [
            "ERR_BANK_TIMEOUT",
            "Server partner bank tidak merespons dalam batas waktu (>10 detik)",
            "Cek status mutasi perbankan; lakukan pengecekan status transaksi manual di portal partner.",
            "Jika terjadi > 5 transaksi dalam 10 menit, eskalasikan ke L2 untuk investigasi switch gateway."
        ],
        [
            "ERR_INSUFFICIENT_FUNDS",
            "Saldo rekening nasabah tidak mencukupi untuk nominal transaksi",
            "Informasikan kepada nasabah untuk melakukan top up saldo. Transaksi tidak dapat diulang otomatis.",
            "Tidak perlu eskalasi (kesalahan pengguna)."
        ],
        [
            "ERR_INVALID_PIN",
            "PIN atau OTP dimasukkan salah melebihi batas percobaan",
            "Arahkan pengguna mereset PIN pada aplikasi bank terkait.",
            "Tidak perlu eskalasi."
        ],
        [
            "ERR_SYSTEM_DOWNTIME",
            "Mitra pembayaran sedang melakukan maintenance terjadwal atau gangguan total",
            "Tampilkan pengumuman pemeliharaan sistem di aplikasi merchant; aktifkan jalur fallback jika tersedia.",
            "Wajib eskalasi segera ke Tim Network Operations Center (NOC)."
        ]
    ]

    # Bungkus teks setiap sel dengan Paragraph agar membungkus baris (word-wrap) rapi
    formatted_table_data = []
    for row_idx, row in enumerate(raw_table_data):
        formatted_row = []
        for cell in row:
            if row_idx == 0:
                formatted_row.append(Paragraph(cell, table_header_style))
            else:
                formatted_row.append(Paragraph(cell, table_cell_style))
        formatted_table_data.append(formatted_row)

    # Lebar total halaman printable (Letter = 612 - margin kiri/kanan 80 = 532)
    t = Table(formatted_table_data, colWidths=[110, 130, 162, 130])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # Bab 3
    story.append(Paragraph("3. Prosedur Transaksi Menggantung (Status PENDING > 15 Menit)", heading2_style))
    story.append(Paragraph("1. Jika transaksi berada pada status PENDING melebihi SLA 15 menit, tim L1 wajib melakukan *inquiry status* ke API partner.<br/>2. Apabila partner menyatakan transaksi <b>SUCCESS</b> namun di sistem internal masih PENDING: lakukan sinkronisasi data manual (Manual Reconciliation Update).<br/>3. Apabila partner menyatakan transaksi <b>EXPIRED / FAILED</b>: ubah status di sistem menjadi FAILED dan rilis pesanan merchant.", body_style))

    # Bab 4
    story.append(Paragraph("4. Matriks Eskalasi", heading2_style))
    story.append(Paragraph("• <b>Level 1 (Helpdesk):</b> Merespons komplain merchant maksimal dalam 5 menit.<br/>• <b>Level 2 (Ops Engineer):</b> Mengambil alih kasus jika error rate di satu channel melebihi 5% dalam kurun waktu 15 menit berturut-turut.<br/>• <b>Level 3 (VP Engineering / Partner NOC):</b> Terlibat jika terjadi total outage pada partner tier-1 (BCA, Mandiri) melebihi 30 menit.", body_style))

    doc.build(story)
    print(f"   ✅ File PDF selesai dibuat di {pdf_path}")


def create_docx_refund_policy():
    """Membuat file dokumen Word (.docx): Kebijakan Refund & Dispute."""
    print("📝 3. Membuat file DOCX: knowledge_base/Kebijakan_Refund_dan_Chargeback.docx ...")
    
    doc = Document()
    
    # Header Dokumen
    title = doc.add_heading("KEBIJAKAN PENGEMBALIAN DANA (REFUND) & SENGKETA TRANSAKSI", level=1)
    title.runs[0].font.color.rgb = RGBColor(30, 58, 138)
    
    doc.add_paragraph("Nomor Kebijakan: POL-FIN-REFUND-2024\nDivisi: Finance Operations & Compliance\nRevisi Terakhir: 15 Agustus 2024")
    doc.add_paragraph("---------------------------------------------------------------------------------")
    
    # Seksi 1: Standar Waktu Pengembalian Dana
    doc.add_heading("1. Batas Waktu Pengembalian Dana (SLA Refund) Berdasarkan Metode Pembayaran", level=2)
    doc.add_paragraph(
        "Pengembalian dana kepada pelanggan yang mengalami transaksi gagal atau pembatalan pesanan diatur dengan ketentuan waktu sebagai berikut:"
    )
    
    p1 = doc.add_paragraph()
    p1.add_run("• Virtual Account (BCA, Mandiri, BNI, BRI):\n").bold = True
    p1.add_run("  Dana dikembalikan ke rekening asal nasabah dalam waktu 1x24 jam kerja setelah verifikasi mutasi rekening koran berhasil.")
    
    p2 = doc.add_paragraph()
    p2.add_run("• QRIS & E-Wallet (GoPay, OVO, DANA, ShopeePay):\n").bold = True
    p2.add_run("  Pengembalian dana diproses secara real-time hingga maksimal 1x24 jam kerja langsung ke saldo akun e-wallet pengguna.")
    
    p3 = doc.add_paragraph()
    p3.add_run("• Kartu Kredit (Visa, Mastercard, JCB):\n").bold = True
    p3.add_run("  Pengembalian dana membutuhkan waktu 7 hingga 14 hari kerja tergantung pada siklus penagihan (billing cycle) bank penerbit kartu.")

    # Seksi 2: Penanganan Kasus Potong Saldo tapi Status Gagal
    doc.add_heading("2. Prosedur Kasus Khusus: Saldo Terpotong Namun Transaksi Status Gagal", level=2)
    doc.add_paragraph(
        "Jika nasabah melaporkan saldo telah didebit namun status transaksi di sistem tercatat FAILED (sering terjadi akibat ERR_BANK_TIMEOUT):\n"
        "1. Petugas operasional wajib meminta bukti mutasi rekening nasabah (rekening koran / screenshot mobile banking).\n"
        "2. Cocokkan ID referensi bank (RRN / Retrieval Reference Number) dengan log transaksi internal.\n"
        "3. Lakukan proses 'Auto-Reversal' ke sistem perbankan. Jika settlement harian sudah ditutup, proses melalui mekanisme manual refund transfer dalam 1x24 jam."
    )

    docx_path = os.path.join("knowledge_base", "Kebijakan_Refund_dan_Chargeback.docx")
    doc.save(docx_path)
    print(f"   ✅ File DOCX selesai dibuat di {docx_path}")


def create_txt_incident_report():
    """Membuat file teks (.txt): Laporan Post-Mortem Insiden BCA VA Oktober 2024."""
    print("📋 4. Membuat file TXT: knowledge_base/Laporan_Insiden_BCA_VA_Oktober_2024.txt ...")
    
    content = """================================================================================
LAPORAN POST-MORTEM INSIDEN TEKNIS (INCIDENT POST-MORTEM REPORT)
PT INTEGRASI PEMBAYARAN DIGITAL - NETWORK OPERATIONS CENTER
================================================================================

ID Insiden       : INC-20241015-BCA-VA-TIMEOUT
Tingkat Keparahan: SEV-1 (High Impact - Major Financial Anomaly)
Layanan Terdampak: Channel VIRTUAL_ACCOUNT (Mitra Bank: BCA)
Waktu Mulai      : Selasa, 15 Oktober 2024, Pukul 10:15 WIB
Waktu Selesai    : Minggu, 20 Oktober 2024, Pukul 18:00 WIB
Durasi Gangguan  : 5 Hari 7 Jam 45 Menit
Lead Investigator: Tim Infrastructure & Payment Gateway Core

--------------------------------------------------------------------------------
1. RINGKASAN EKSEKUTIF (EXECUTIVE SUMMARY)
--------------------------------------------------------------------------------
Pada rentang tanggal 15 hingga 20 Oktober 2024, sistem monitoring transaksi mendeteksi 
lonjakan signifikan pada rasio kegagalan (Failure Rate) khusus pada channel VIRTUAL_ACCOUNT 
dengan mitra perbankan BCA. 

Metrik Dampak Utama:
- Rasio Kegagalan (Failure Rate) BCA VA melonjak dari rata-rata normal 3.2% menjadi 48.7%.
- Kode error yang mendominasi kegagalan: ERR_BANK_TIMEOUT (>94% dari seluruh kegagalan).
- Rata-rata waktu respons transaksi (Response Time Latency) melonjak drastis dari 
  normal 420 ms menjadi 18.500 ms - 26.000 ms sebelum akhirnya mengalami socket timeout.
- Channel lain (QRIS, Kartu Kredit, E-Wallet) dan partner bank lain (Mandiri, BNI) 
  tetap beroperasi normal pada tingkat keberhasilan 96% - 98%.

--------------------------------------------------------------------------------
2. AKAR PERMASALAHAN (ROOT CAUSE ANALYSIS)
--------------------------------------------------------------------------------
Berdasarkan hasil investigasi bersama dan klarifikasi resmi dari Network Operations Center (NOC) Bank BCA:
1. Mitra perbankan BCA sedang melakukan peningkatan arsitektur sistem inti (Core Banking Upgrade) 
   dari protokol Gateway v3.1 ke Gateway v4.0 pada datacenter primer mereka.
2. Proses migrasi tersebut menyebabkan kemacetan antrean (packet queue congestion) dan packet loss 
   pada port API callback payment notification menuju payment gateway eksternal.
3. Server internal kita mengalami socket read timeout setelah menunggu respon lebih dari 15 detik, 
   sehingga transaksi otomatis ditandai sebagai FAILED dengan kode error ERR_BANK_TIMEOUT.

--------------------------------------------------------------------------------
3. TINDAKAN PENANGANAN & MITIGASI (MITIGATION STEPS)
--------------------------------------------------------------------------------
1. Tanggal 16 Oktober 2024 14:00 WIB:
   Tim IT melakukan konfigurasi penyesuaian socket timeout dari 15 detik menjadi 30 detik 
   untuk mengurangi transaksi yang gugur sebelum callback diterima.
2. Tanggal 17 Oktober 2024 09:00 WIB:
   Mengaktifkan perutean jalur cadangan (Secondary Disaster Recovery Gateway Connector) 
   bekerja sama dengan tim infrastruktur BCA.
3. Tanggal 20 Oktober 2024 18:00 WIB:
   Mitra BCA menyelesaikan stabilisasi gateway v4.0. Latensi transaksi kembali normal 
   ke angka 380 ms dan rasio keberhasilan transaksi BCA VA pulih ke 96.5%.

--------------------------------------------------------------------------------
4. STATUS REKONSILIASI DANA
--------------------------------------------------------------------------------
Sebanyak 384 transaksi nasabah yang sempat mengalami pemotongan saldo namun berstatus 
FAILED telah diselesaikan melalui prosedur sinkronisasi mutasi bank dan auto-reversal 
sesuai dengan SOP-OPS-FIN-2024-V2.
================================================================================
"""

    txt_path = os.path.join("knowledge_base", "Laporan_Insiden_BCA_VA_Oktober_2024.txt")
    with open(txt_path, mode="w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"   ✅ File TXT selesai dibuat di {txt_path}")


def main():
    print("🚀 Memulai pembuatan file data & dokumen multi-format...")
    create_excel_partner_directory()
    create_pdf_sop()
    create_docx_refund_policy()
    create_txt_incident_report()
    print("\n🎉 SEMUA FORMAT DATA & DOKUMEN TELAH BERHASIL DIBUAT!")
    print("   - SQL    : Database PostgreSQL di Docker")
    print("   - CSV    : data/transactions.csv")
    print("   - EXCEL  : data/partner_settlement_directory.xlsx")
    print("   - PDF    : knowledge_base/SOP_Penanganan_Transaksi_Gagal.pdf")
    print("   - DOCX   : knowledge_base/Kebijakan_Refund_dan_Chargeback.docx")
    print("   - TXT    : knowledge_base/Laporan_Insiden_BCA_VA_Oktober_2024.txt")


if __name__ == "__main__":
    main()
