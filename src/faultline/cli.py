from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser(prog="faultline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="API와 콘솔 실행 (http://localhost:8000)")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="127.0.0.1")
    a = sub.add_parser("audit", help="CSV 로그 감사 (JSON 출력)")
    a.add_argument("csv")
    args = ap.parse_args()
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("faultline.api.main:app", host=args.host, port=args.port)
    elif args.cmd == "audit":
        import json

        import pandas as pd

        from .audit import run_audit

        log = pd.read_csv(args.csv)
        print(json.dumps(run_audit(log), ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
