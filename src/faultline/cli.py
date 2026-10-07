from __future__ import annotations

import argparse
import json


def main() -> None:
    ap = argparse.ArgumentParser(prog="faultline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="API와 콘솔 실행 (http://localhost:8000)")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="127.0.0.1")
    q = sub.add_parser("quality", help="작업지시 CSV 품질 점검 (JSON 출력)")
    q.add_argument("csv")
    q.add_argument("--code-book", help='{"A1": "emergency"} 형식의 JSON 파일')
    e = sub.add_parser("evaluate", help="고장 정의 YAML 을 데모 세계에 적용해 라벨 품질을 잰다 (JSON 출력)")
    e.add_argument("definition")
    e.add_argument("--train", action="store_true", help="그 라벨로 모형도 학습해 진짜 성능을 잰다")
    sub.add_parser("definitions", help="내장 정의 목록")
    args = ap.parse_args()
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("faultline.api.main:app", host=args.host, port=args.port)
    elif args.cmd == "quality":
        import pandas as pd

        from .quality.contract import coerce_days, quality_report

        wo = coerce_days(pd.read_csv(args.csv))
        book = None
        if args.code_book:
            raw = json.load(open(args.code_book, encoding="utf-8"))
            book = {int(s): raw for s in wo["site"].unique()}
        print(
            json.dumps(
                quality_report(wo, None, None, book, int(wo["created_day"].max() // 7) + 1),
                ensure_ascii=False,
                indent=1,
            )
        )
    elif args.cmd == "evaluate":
        from .api import demo
        from .define import spec

        print(
            json.dumps(
                demo.evaluate_definition(spec.load_file(args.definition), args.train),
                ensure_ascii=False,
                indent=1,
                default=float,
            )
        )
    elif args.cmd == "definitions":
        from .define import spec

        for name, d in spec.builtin().items():
            print(f"{name}\t{d.description}")


if __name__ == "__main__":
    main()
