from __future__ import annotations

import argparse
import json


def _audit(args) -> None:
    import pandas as pd

    from .define import spec
    from .eval import audit
    from .logs import read_logs

    logs = read_logs(args.work_orders, args.assets, args.complaints, args.code_book, args.weeks)
    defs = spec.builtin()
    L, index = audit.site_windows(defs, logs.wo_norm, logs.complaints, logs.assets, args.site, logs.n_weeks)
    if args.cmd == "audit-sample":
        plan = audit.plan_sample(defs, L, index, args.site, args.n, args.seed)
        plan.to_csv(args.out, index=False)
        print(
            f"확인표 {len(plan)}건을 {args.out} 에 썼다. confirmed 열에 1(4주 안에 고장 있었음) 또는 0(없었음)을 적어 audit-estimate 에 넘긴다"
        )
    else:
        res = audit.estimate_from_sample(defs, L, index, pd.read_csv(args.sample))
        print(json.dumps(res, ensure_ascii=False, indent=1))


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
    for name, text in (
        ("audit-sample", "현장에서 확인할 설비·주 표본(확인표) 만들기"),
        ("audit-estimate", "확인표로 정의별 정밀도·재현율 추정"),
    ):
        a = sub.add_parser(name, help=text)
        a.add_argument("--work-orders", required=True)
        a.add_argument("--assets", required=True)
        a.add_argument("--complaints")
        a.add_argument("--code-book")
        a.add_argument("--weeks", type=int, help="관측 기간(주). 없으면 마지막 기록의 날짜로 정함")
        a.add_argument("--site", required=True, type=int)
        if name == "audit-sample":
            a.add_argument("-n", type=int, default=80, help="확인할 건수")
            a.add_argument("--seed", type=int, default=0)
            a.add_argument("-o", "--out", required=True, help="확인표 CSV")
        else:
            a.add_argument("--sample", required=True, help="confirmed 열을 채운 확인표 CSV")
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
    elif args.cmd in ("audit-sample", "audit-estimate"):
        _audit(args)
    elif args.cmd == "definitions":
        from .define import spec

        for name, d in spec.builtin().items():
            print(f"{name}\t{d.description}")


if __name__ == "__main__":
    main()
