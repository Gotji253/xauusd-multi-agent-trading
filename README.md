# XAUUSD Multi-Agent AI Trading System

**ระบบ Multi-Agent AI Trading สำหรับทองคำ (XAUUSD)**  
ออกแบบโดยเน้น **Risk-Adjusted Return** และ **ควบคุม Drawdown** เป็นหลัก

> Senior Quantitative Developer & AI Agent Architect style  
> Python + MetaTrader 5 + LINE Thai Notifier

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
├── .github/workflows/       # CI/CD
├── main.py
└── requirements.txt
```

---

## การติดตั้ง (Local Development)

```bash
git clone https://github.com/Gotji253/xauusd-multi-agent-trading.git
cd xauusd-multi-agent-trading

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

คัดลอกไฟล์ environment:
```bash
cp .env.example .env
# แก้ไขค่า MT5 และ LINE Token
```

---

## การรัน Tests (สำคัญ)

ระบบใช้ **Mock MetaTrader5** ทั้งหมด → รันบน Linux / GitHub Actions ได้โดยไม่ต้องมี MT5 Terminal

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
- [x] GitHub Actions CI
- [x] Mock MT5 สำหรับ Unit Test
- [ ] Technical Analysis Agent (กำลังพัฒนา)
- [ ] Risk Management Agent (กำลังพัฒนา)
- [ ] Execution Agent
- [ ] LINE Thai Notifier
- [ ] Backtesting Engine
- [ ] Paper Trading / Live

---

## คำเตือนสำคัญ

การเทรดมีความเสี่ยงสูง ระบบนี้ไม่ได้รับประกันกำไร  
ใช้เพื่อการศึกษาและพัฒนาเท่านั้น ก่อนใช้งานจริงต้องผ่าน Backtest + Paper Trading อย่างน้อย 1–2 เดือน

---

**พัฒนาอย่างต่อเนื่อง (Iterative Development)**  
โฟกัสที่ Risk-Adjusted Return และควบคุม Drawdown เป็นอันดับแรก
