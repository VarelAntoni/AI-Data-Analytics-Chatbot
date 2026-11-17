"""
Script: seed_data.py
Deskripsi:
  Menghasilkan 20.000 data transaksi sintetis realistis ke dalam database PostgreSQL.
  Skenario: Operasional Payment Gateway (Mei 2024 - Oktober 2024).
  
Injected Anomaly (Skenario Investigasi Masalah):
  Pada tanggal 15 - 20 Oktober 2024, terjadi lonjakan kegagalan transaksi khusus pada:
  - Channel: VIRTUAL_ACCOUNT
  - Partner: BCA
  - Error Code: ERR_BANK_TIMEOUT
  - Response Time: Melonjak tinggi (15.000 - 25.000 ms)
  
"""

import os
import random
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# 1. Load konfigurasi dari file .env
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "analytics_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgrespassword")


# 2. Definisi Master Data Kategori dan Opsi Pembayaran
CHANNELS = {
    "VIRTUAL_ACCOUNT": ["BCA", "MANDIRI", "BNI", "BRI"],
    "QRIS": ["GOPAY", "OVO", "DANA", "SHOPEEPAY"],
    "CREDIT_CARD": ["VISA", "MASTERCARD", "JCB"],
    "E_WALLET": ["GOPAY", "OVO", "DANA"]
}

MERCHANT_CATEGORIES = ["E_COMMERCE", "GAMING", "TRAVEL", "UTILITY", "FOOD_BEVERAGE"]

# Error code umum pada hari normal
NORMAL_ERRORS = [
    "ERR_INSUFFICIENT_FUNDS",
    "ERR_INVALID_PIN",
    "ERR_CARD_DECLINED",
    "ERR_USER_CANCELLED"
]


def create_table_if_not_exists(cursor):
    """Membuat tabel 'transactions' jika belum ada."""
    create_query = """
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id VARCHAR(50) PRIMARY KEY,
        timestamp TIMESTAMP NOT NULL,
        channel VARCHAR(30) NOT NULL,
        payment_partner VARCHAR(30) NOT NULL,
        merchant_category VARCHAR(30) NOT NULL,
        amount NUMERIC(15, 2) NOT NULL,
        status VARCHAR(20) NOT NULL,
        error_code VARCHAR(50),
        response_time_ms INTEGER NOT NULL
    );
    
    CREATE INDEX IF NOT EXISTS idx_trx_timestamp ON transactions(timestamp);
    CREATE INDEX IF NOT EXISTS idx_trx_channel ON transactions(channel);
    CREATE INDEX IF NOT EXISTS idx_trx_status ON transactions(status);
    CREATE INDEX IF NOT EXISTS idx_trx_partner ON transactions(payment_partner);
    """
    cursor.execute(create_query)


def generate_synthetic_transactions(total_records=20000):
    """Menghasilkan list tuple data transaksi dengan skenario anomali terinjeksi."""
    print(f"🔄 Menghasilkan {total_records} data transaksi realistis...")

    # Rentang waktu: 1 Mei 2024 sampai 31 Oktober 2024 (6 bulan)
    start_date = datetime(2024, 5, 1, 0, 0, 0)
    end_date = datetime(2024, 10, 31, 23, 59, 59)
    total_seconds = int((end_date - start_date).total_seconds())

    # Rentang tanggal insiden khusus (15 - 20 Oktober 2024)
    incident_start = datetime(2024, 10, 15, 0, 0, 0)
    incident_end = datetime(2024, 10, 20, 23, 59, 59)

    records = []

    for i in range(1, total_records + 1):
        trx_id = f"TRX-2024-{i:06d}"
        random_seconds = random.randint(0, total_seconds)
        trx_time = start_date + timedelta(seconds=random_seconds)

        # Pilih Channel & Partner
        channel = random.choice(list(CHANNELS.keys()))
        partner = random.choice(CHANNELS[channel])
        merchant_cat = random.choice(MERCHANT_CATEGORIES)

        # Nominal transaksi acak sesuai kategori
        if merchant_cat == "TRAVEL":
            amount = round(random.uniform(500000, 5000000), 2)
        elif merchant_cat == "GAMING":
            amount = round(random.uniform(20000, 300000), 2)
        else:
            amount = round(random.uniform(25000, 1500000), 2)

        # Cek apakah transaksi berada pada masa insiden (15-20 Okt 2024 pada BCA VA)
        is_incident_period = incident_start <= trx_time <= incident_end
        is_target_partner = (channel == "VIRTUAL_ACCOUNT" and partner == "BCA")

        if is_incident_period and is_target_partner:
            # === SKENARIO ANOMALI INSIDEN ===
            # Pada periode ini, 50% transaksi BCA VA gagal karena TIMEOUT
            if random.random() < 0.50:
                status = "FAILED"
                error_code = "ERR_BANK_TIMEOUT"
                response_time_ms = random.randint(15000, 28000)  # Sangat lambat (15-28 detik)
            else:
                status = "SUCCESS"
                error_code = None
                response_time_ms = random.randint(3000, 8000)
        else:
            # === SKENARIO NORMAL HARI BIASA ===
            # Normal: 95% Sukses, 4% Gagal, 1% Pending
            dice = random.random()
            if dice < 0.95:
                status = "SUCCESS"
                error_code = None
                response_time_ms = random.randint(150, 800)
            elif dice < 0.99:
                status = "FAILED"
                error_code = random.choice(NORMAL_ERRORS)
                response_time_ms = random.randint(200, 1200)
            else:
                status = "PENDING"
                error_code = None
                response_time_ms = random.randint(1000, 3500)

        records.append((
            trx_id,
            trx_time,
            channel,
            partner,
            merchant_cat,
            amount,
            status,
            error_code,
            response_time_ms
        ))

    return records


def main():
    print("🔌 Menghubungkan ke PostgreSQL di Docker...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = False
        cursor = conn.cursor()

        print("📋 Menyiapkan tabel 'transactions'...")
        create_table_if_not_exists(cursor)

        # Kosongkan tabel jika sudah ada data lama agar bersih
        cursor.execute("TRUNCATE TABLE transactions;")

        # Generate data
        data = generate_synthetic_transactions(total_records=20000)

        insert_query = """
        INSERT INTO transactions (
            transaction_id, timestamp, channel, payment_partner,
            merchant_category, amount, status, error_code, response_time_ms
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """

        print("💾 Memasukkan 20.000 data ke database (Bulk Insert)...")
        execute_batch(cursor, insert_query, data, page_size=2000)
        conn.commit()

        # Ekspor salinan ke file data/transactions.csv agar bisa diinspeksi secara visual
        import csv
        os.makedirs("data", exist_ok=True)
        csv_path = os.path.join("data", "transactions.csv")
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "transaction_id", "timestamp", "channel", "payment_partner",
                "merchant_category", "amount", "status", "error_code", "response_time_ms"
            ])
            writer.writerows(data)
        print(f"📁 Salinan file CSV berhasil disimpan di: {csv_path}")

        print("✅ SUKSES! 20.000 data transaksi berhasil dimasukkan ke PostgreSQL dan CSV.")
        
        # Cek sekilas jumlah data
        cursor.execute("SELECT status, COUNT(*) FROM transactions GROUP BY status;")
        results = cursor.fetchall()
        print("\n📊 Ringkasan Data Transaksi:")
        for status, count in results:
            print(f"   - {status}: {count:,} transaksi")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Terjadi kesalahan saat seeding data: {e}")


if __name__ == "__main__":
    main()
