# GitHub Codespaces สำหรับโปรเจกต์นี้

รันและพัฒนาผ่านเบราว์เซอร์ได้ โดยไม่ต้องมี PC

## เปิด Codespaces

1. เปิด https://github.com/Gotji253/xauusd-multi-agent-trading
2. กด **<> Code** → แท็บ **Codespaces**
3. กด **Create codespace on main** (หรือเปิดอันที่มีอยู่)
4. รอ 1–3 นาทีให้ `postCreateCommand` ติดตั้ง dependencies

## ทดสอบเชื่อมต่อ Binance Testnet (ใน Terminal ของ Codespaces)

### 1) ตั้งค่า secrets ใน Codespaces (อย่า commit)

ใน Terminal:

```bash
cat > .env << 'EOF'
BINANCE_API_KEY=วาง_API_KEY_ตรงนี้
BINANCE_API_SECRET=วาง_API_SECRET_ตรงนี้
BINANCE_ENVIRONMENT=testnet
SYMBOL=BTCUSDT
EOF
```

หรือ export ชั่วคราว:

```bash
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
export BINANCE_ENVIRONMENT=testnet
```

> ใช้ key จาก https://testnet.binance.vision เท่านั้น

### 2) รันทดสอบเชื่อมต่อ (ไม่ส่งออเดอร์จริง)

```bash
python scripts/test_binance_tpsl.py --dry-run
```

ถ้าสำเร็จจะเห็น `success: True` และ `PASS: connection + order validation OK`

### 3) (ทางเลือก) ส่งออเดอร์ + TP/SL บน testnet แล้ว cleanup

```bash
python scripts/test_binance_tpsl.py --live-order --cleanup --qty 0.001
```

## คำสั่งอื่นที่ใช้บ่อย

```bash
pytest tests/ -v
python main.py
python scripts/test_binance_connection.py
```

## หมายเหตุสำคัญ

- **Codespaces อาจเจอ HTTP 451 (restricted location)** เหมือน GitHub Actions
  เพราะ VM อยู่บนคลาวด์ที่ Binance บล็อก
  ถ้าเจอ ให้รันจากเครือข่ายที่เข้า Binance ได้ (มือถือ/PC ในไทย หรือ VPS)
- MetaTrader5 ใช้บน Windows เท่านั้น — บน Codespaces ใช้ mock / OANDA / Binance API
- อย่า commit ไฟล์ `.env` ที่มี API key
