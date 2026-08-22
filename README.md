# XAUUSD Multi-Agent AI Trading System

**ระบบ Multi-Agent AI Trading สำหรับทองคำ (XAUUSD)**  
ออกแบบโดยเน้น **Risk-Adjusted Return** และ **ควบคุม Drawdown** เป็นหลัก

> Senior Quantitative Developer & AI Agent Architect style  
> Python + MetaTrader 5 + LINE Thai Notifier

**Repository**: https://github.com/Gotji253/xauusd-multi-agent-trading  
**Visibility**: Public

---

## รันบนเบราว์เซอร์ได้ทันที (ไม่มี PC ก็ได้)

โปรเจกต์นี้รองรับ **GitHub Codespaces** แล้ว

### วิธีเปิด (ใช้มือถือหรือคอมเครื่องไหนก็ได้)

1. เข้า https://github.com/Gotji253/xauusd-multi-agent-trading
2. กดปุ่มสีเขียว **<> Code**
3. เลือกแท็บ **Codespaces**
4. กด **Create codespace on main**
5. รอ 1–3 นาที → ได้ VS Code บนคลาวด์พร้อมใช้งาน

หลังเปิดแล้วรันคำสั่งนี้ใน Terminal ได้เลย:

```bash
pytest tests/ -v
python main.py
```

> หมายเหตุ: Codespaces เป็น Linux → ใช้พัฒนา Logic / Backtest / Unit Test ได้เต็มที่  
> การส่งออเดอร์จริงต้องใช้ Windows VPS + MetaTrader5

---

## เป้าหมายหลัก

1. **Technical Analysis Agent** — วิเคราะห์แนวโน้ม, EMA, RSI, ATR และ Price Action ของ XAUUSD
2. **Risk Management Agent** — คำนวณ Position Sizing จาก % Risk Per Trade, Dynamic SL/TP, ควบคุม Daily Drawdown
3. **Execution Agent** — เชื่อมต่อ MT5 API สำหรับเปิด/ปิดออเดอร์อัตโนมัติ
4. **LINE Thai Notifier Agent** — แจ้งเตือนแบบภาษาไทยที่อ่านง่าย ชัดเจน

ระบบถูกออกแบบให้มี **Positive Expectancy** และป้องกันการขาดทุนหนักเป็นอันดับหนึ่ง

---

## สถาปัตยกรรม

```
Orchestrator (Supervisor)
├── Technical Analysis Agent
├── Risk Management Agent
├── Execution Agent (MT5)
└── LINE Thai Notifier Agent
```

### จุดเด่นด้านความเสี่ยง
- Risk Per Trade: 0.5% – 1.0% ของ Equity
- Max Daily Drawdown Halt
- Max Consecutive Losses
- ATR-based Stop Loss + Trailing
- Session Filter (London / New York)
- Spread Filter

---

## โครงสร้างโปรเจกต์

```
xauusd-multi-agent-trading/
├── agents/                  # Multi-Agent modules
├── core/                    # Indicators, Data Feed, Signal, Position Manager
├── config/                  # Settings + Risk rules
├── tests/                   # Unit tests (MT5 fully mocked)
├── utils/
├── .devcontainer/           # GitHub Codespaces config
├── .github/workflows/       # CI/CD
├── main.py
└── requirements.txt
```

---

## การติดตั้ง (Local / VPS)

```bash
git clone https://github.com/Gotji253/xauusd-multi-agent-trading.git
cd xauusd-multi-agent-trading

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### สำหรับ Live / Paper Trading บน Windows หรือ Windows VPS
```bash
pip install MetaTrader5
```
> **หมายเหตุสำคัญ**: แพ็กเกจ `MetaTrader5` รองรับเฉพาะ **Windows** เท่านั้น  
> ดังนั้นใน GitHub Actions / Codespaces (Linux) จะใช้ Mock แทน

คัดลอกไฟล์ environment:
```bash
cp .env.example .env
# แก้ไขค่า MT5 และ LINE Token
```

---

## การรัน Tests

```bash
pytest tests/ -v --cov=agents --cov=core
```

---

## GitHub Actions CI

ทุกครั้งที่ Push หรือเปิด Pull Request จะรันอัตโนมัติ:
- Ruff (Lint)
- MyPy (Type check)
- Pytest + Coverage

ดูผลได้ที่แท็บ **Actions**

---

## ความปลอดภัย

- **ห้าม** commit ไฟล์ `.env` หรือ credentials จริง
- ใช้ GitHub Secrets สำหรับ Production
- Risk Management เป็นหัวใจของระบบ — อย่าลดกฎความเสี่ยงโดยไม่ผ่าน Backtest

---

## สถานะปัจจุบัน

- [x] โครงสร้างโปรเจกต์
- [x] GitHub Actions CI (รองรับ Ubuntu)
- [x] GitHub Codespaces (รันบนเบราว์เซอร์ได้)
- [x] Mock MT5 สำหรับ Unit Test
- [x] Risk Management Agent (logic พื้นฐานพร้อม + ผ่าน Unit Test)
- [x] LINE Thai Notifier (ข้อความภาษาไทย + mock mode)
- [ ] Technical Analysis Agent (logic เต็ม)
- [ ] Execution Agent (เชื่อม MT5 จริง)
- [ ] Backtesting Engine
- [ ] Paper Trading / Live

---

## คำเตือนสำคัญ

การเทรดมีความเสี่ยงสูง ระบบนี้ไม่ได้รับประกันกำไร  
ใช้เพื่อการศึกษาและพัฒนาเท่านั้น ก่อนใช้งานจริงต้องผ่าน Backtest + Paper Trading อย่างน้อย 1–2 เดือน

---

**พัฒนาอย่างต่อเนื่อง (Iterative Development)**  
โฟกัสที่ Risk-Adjusted Return และควบคุม Drawdown เป็นอันดับแรก
