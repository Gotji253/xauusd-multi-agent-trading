#!/usr/bin/env python3
"""ทดสอบเชื่อมต่อ Binance (ไม่ส่งออเดอร์ ถ้าไม่ใส่ --order)"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from core.binance_client import BinanceClient
from agents.execution import ExecutionAgent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--order",
        action="store_true",
        help="ส่ง MARKET order ขนาดเล็กมาก (ระวัง: ใช้ของจริงถ้า environment=live)",
    )
    parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"])
    parser.add_argument("--qty", type=float, default=0.0, help="override quantity BTC")
    args = parser.parse_args()

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    env = os.getenv("BINANCE_ENVIRONMENT", "testnet")
    scale = float(os.getenv("BINANCE_QTY_SCALE", "0.001"))

    print("=" * 60)
    print("Binance Connection Test")
    print("=" * 60)
    print(f"Environment : {env}")
    print(f"API key set : {'yes' if api_key else 'NO'}")
    print(f"Secret set  : {'yes' if api_secret else 'NO'}")

    base_url = os.getenv("BINANCE_BASE_URL", "") or None
    client = BinanceClient(
        api_key=api_key, api_secret=api_secret, environment=env, base_url=base_url
    )
    agent = ExecutionAgent(
        binance_client=client,
        mode="binance" if client.is_configured else "mock",
        default_units_scale=scale,
        default_symbol="BTCUSDT",
    )
    print(f"Agent mode  : {agent.mode}")

    result = agent.test_connection()
    print("-" * 40)
    for k, v in result.items():
        print(f"  {k}: {v}")
    print("-" * 40)

    if not result.get("success"):
        if agent.mode == "mock":
            print("\nMock mode — ใส่ BINANCE_API_KEY + BINANCE_API_SECRET ใน .env")
            print(agent.place_order("BTCUSDT", "BUY", 1.0))
            return
        print("\nConnection failed")
        sys.exit(1)

    print("\nOK: connected (no order unless --order)")

    if args.order:
        qty_lot = 1.0
        if args.qty > 0:
            agent.default_units_scale = 1.0
            qty_lot = args.qty
        print(f"\nSending MARKET {args.side} ...")
        order = agent.place_order("BTCUSDT", args.side, qty_lot)
        print(order)
        if not order.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()
