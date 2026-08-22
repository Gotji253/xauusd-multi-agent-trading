# GitHub Codespaces สำหรับโปรเจกต์นี้

คุณสามารถรันและพัฒนาโปรเจกต์นี้ได้ทั้งหมดผ่านเบราว์เซอร์ โดยไม่ต้องมีคอมพิวเตอร์ส่วนตัว

## วิธีเปิด Codespaces (จากมือถือหรือคอมพิวเตอร์ใดก็ได้)

1. ไปที่ Repository → https://github.com/Gotji253/xauusd-multi-agent-trading
2. กดปุ่มสีเขียว **<> Code**
3. เลือกแท็บ **Codespaces**
4. กด **Create codespace on main**
5. รอประมาณ 1–3 นาที (ครั้งแรกจะนานหน่อยเพราะติดตั้ง dependencies)

หลังจากนั้นคุณจะได้ VS Code เต็มรูปแบบทำงานบนคลาวด์

## คำสั่งที่ใช้บ่อยใน Terminal ของ Codespaces

```bash
# รันทดสอบทั้งหมด
pytest tests/ -v

# รัน main.py
python main.py

# ตรวจสอบ lint
ruff check .
```

## หมายเหตุ

- MetaTrader5 ติดตั้งไม่ได้บน Codespaces (เพราะเป็น Linux) → ใช้สำหรับพัฒนา Logic, Backtest, Unit Test เท่านั้น
- เมื่อพร้อมรันจริง ให้ย้ายไป Windows VPS
