#!/usr/bin/env python3
"""ทดสอบการเชื่อมต่อ OANDA API (ไม่ส่งออเดอร์)"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from core.oanda_client import OandaClient
from agents.execution import ExecutionAgent


def main() -> None:
    api_key = os.getenv("OANDA_API_KEY", "")
    account_id = os.getenv("OANDA_ACCOUNT_ID", "")
    env = os.getenv("OANDA_ENVIRONMENT", "practice")

    print("=" * 60)
    print("OANDA Connection Test (no order send)")
    print("=" * 60)
    print(f"Environment : {env}")
    print(f"API key set : {'yes' if api_key else 'NO'}")
    print(f"Account ID  : {account_id or '(empty)'}")

    client = OandaClient(api_key=api_key, account_id=account_id, environment=env)
    agent = ExecutionAgent(oanda_client=client, mode="auto")
    print(f"Agent mode  : {agent.mode}")
    result = agent.test_connection()
    print("-" * 40)
    for k, v in result.items():
        print(f"  {k}: {v}")
    print("-" * 40)

    if result.get("success") and agent.mode == "oanda":
        pricing = client.get_pricing(["XAU_USD"])
        if pricing.get("ok"):
            prices = (pricing.get("data") or {}).get("prices") or []
            if prices:
                p = prices[0]
                bids = p.get("bids") or [{}]
                asks = p.get("asks") or [{}]
                print(f"XAU_USD bid={bids[0].get('price')} ask={asks[0].get('price')}")
        print("\nOK: API ready (no order sent)")
    elif agent.mode == "mock":
        print("\nMock mode — set OANDA_API_KEY + OANDA_ACCOUNT_ID in .env")
        print(agent.place_order("XAU_USD", "BUY", 1.0, 2500.0, 2600.0))
    else:
        print("\nConnection failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
