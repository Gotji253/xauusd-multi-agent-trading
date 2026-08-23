#!/usr/bin/env python3
"""ทดสอบ Binance Testnet: connect + MARKET + OCO TP/SL

Exit codes:
  0 = success
  1 = auth/order failure
  2 = wrong environment (not testnet)
  78 = geo-blocked (HTTP 451) — secrets OK แต่ IP ถูกบล็อก
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from core.binance_orders import BinanceOrderExt as BinanceClient

GEO_EXIT = 78


def _must_testnet(env: str) -> None:
    if env.lower() not in ("testnet", "demo"):
        print("ERROR: สคริปต์นี้อนุญาตเฉพาะ BINANCE_ENVIRONMENT=testnet")
        sys.exit(2)


def _is_geo_block(message: str | None) -> bool:
    if not message:
        return False
    m = message.lower()
    return (
        "restricted location" in m
        or "eligibility" in m
        or "451" in m
        or "unavailable from a restricted" in m
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Binance testnet TP/SL integration test")
    parser.add_argument("--dry-run", action="store_true", help="validate via /order/test only")
    parser.add_argument("--live-order", action="store_true", help="send MARKET + OCO on testnet")
    parser.add_argument("--cleanup", action="store_true", help="cancel OCO + market sell")
    parser.add_argument(
        "--allow-geo-block",
        action="store_true",
        help="ถ้าเจอ HTTP 451 ให้ exit 78 แทน fail 1 (ใช้ใน GitHub-hosted runner)",
    )
    parser.add_argument("--symbol", default=os.getenv("SYMBOL", "BTCUSDT"))
    parser.add_argument("--qty", type=float, default=float(os.getenv("BINANCE_TEST_QTY", "0.001")))
    parser.add_argument("--tp-pct", type=float, default=0.02)
    parser.add_argument("--sl-pct", type=float, default=0.015)
    args = parser.parse_args()

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    env = os.getenv("BINANCE_ENVIRONMENT", "testnet")
    base_url = os.getenv("BINANCE_BASE_URL", "") or None
    _must_testnet(env)

    print("=" * 64)
    print("Binance Testnet — Connection + Order + TP/SL (OCO)")
    print("=" * 64)
    print(f"Environment : {env}")
    print(f"Symbol      : {args.symbol}")
    print(f"Qty         : {args.qty}")
    print(f"API key set : {'yes' if api_key else 'NO'} (len={len(api_key)})")
    print(f"Mode        : {'DRY-RUN' if args.dry_run or not args.live_order else 'LIVE-ORDER'}")

    if not api_key or not api_secret:
        print("\nFAIL: ต้องตั้ง BINANCE_API_KEY และ BINANCE_API_SECRET (testnet)")
        return 1

    client = BinanceClient(
        api_key=api_key,
        api_secret=api_secret,
        environment="testnet",
        base_url=base_url,
    )

    print("\n[1] test_connection()")
    conn = client.test_connection()
    for k, v in conn.items():
        print(f"  {k}: {v}")

    if not conn.get("success"):
        msg = str(conn.get("message") or "")
        if _is_geo_block(msg):
            print("\nGEO-BLOCK: Binance บล็อก IP ของ runner (HTTP 451)")
            print("  - Secrets ถูกตั้งแล้ว (key ถูกอ่านได้)")
            print("  - GitHub-hosted runner มักถูกบล็อก")
            print("  - ใช้ self-hosted runner ในไทย หรือรันจากเครือข่ายที่เข้า Binance ได้")
            if args.allow_geo_block:
                print(f"\nEXIT {GEO_EXIT}: geo-blocked (treated as skipped in CI)")
                return GEO_EXIT
            return 1
        print("\nFAIL: เชื่อมต่อไม่สำเร็จ")
        return 1

    print("\n[2] ticker price")
    tick = client.get_ticker_price(args.symbol)
    if not tick.get("ok"):
        err = str(tick.get("error") or "")
        print(f"FAIL: ไม่ได้ราคา — {err}")
        if _is_geo_block(err) and args.allow_geo_block:
            return GEO_EXIT
        return 1
    price = float((tick.get("data") or {}).get("price"))
    print(f"  {args.symbol} = {price}")
    tp = price * (1.0 + args.tp_pct)
    sl = price * (1.0 - args.sl_pct)
    print(f"  planned TP = {tp:.2f} (+{args.tp_pct * 100:.2f}%)")
    print(f"  planned SL = {sl:.2f} (-{args.sl_pct * 100:.2f}%)")

    if not args.live_order:
        print("\n[3] MARKET BUY — dry-run (/order/test)")
        order = client.place_market_order(args.symbol, "BUY", args.qty, test_only=True)
        print(f"  result: {order}")
        if not order.get("success"):
            msg = str(order.get("message") or "")
            if _is_geo_block(msg) and args.allow_geo_block:
                return GEO_EXIT
            print("\nFAIL: order test ไม่ผ่าน")
            return 1
        print("\n[4] OCO skipped in dry-run (ใช้ --live-order)")
        print("\nPASS: connection + order validation OK")
        return 0

    print("\n[3] MARKET BUY — live testnet")
    order = client.place_market_order(args.symbol, "BUY", args.qty, test_only=False)
    print(f"  result: {order}")
    if not order.get("success"):
        print("\nFAIL: market order ไม่ผ่าน")
        return 1

    fill_qty = float(order.get("quantity") or args.qty)
    fills = order.get("fills") or []
    if fills:
        try:
            fill_qty = sum(float(f.get("qty", 0)) for f in fills)
        except Exception:
            pass
    print(f"  fill_qty ≈ {fill_qty}")
    time.sleep(1)

    print("\n[4] OCO SELL with TP/SL")
    oco = client.place_oco_sell_tp_sl(
        symbol=args.symbol,
        quantity=fill_qty,
        take_profit_price=tp,
        stop_loss_price=sl,
    )
    print(f"  result: {oco}")
    if not oco.get("success"):
        print("\nFAIL: วาง OCO TP/SL ไม่สำเร็จ")
        if args.cleanup:
            print(client.place_market_order(args.symbol, "SELL", fill_qty))
        return 1

    order_list_id = oco.get("order_list_id")
    print(f"  orderListId = {order_list_id}")
    print(f"  TP={oco.get('tp_price')}  SL={oco.get('sl_price')}")

    open_orders = client.get_open_orders(args.symbol)
    if open_orders.get("ok"):
        print(f"  open orders count: {len(open_orders.get('data') or [])}")

    if args.cleanup:
        print("\n[5] cleanup")
        if order_list_id is not None:
            print(client.cancel_order_list(args.symbol, int(order_list_id)))
        else:
            print(client.cancel_all_open_orders(args.symbol))
        time.sleep(1)
        print(client.place_market_order(args.symbol, "SELL", fill_qty))

    print("\nPASS: connection + market order + TP/SL OCO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
