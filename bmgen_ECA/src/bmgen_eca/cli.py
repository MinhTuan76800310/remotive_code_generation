"""CLI: parse / generate / verify / errors."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bmgen_eca.diagnostics import (
    ERROR_CATALOG,
    format_diag,
    format_report_footer,
    has_errors,
)
from bmgen_eca.pipeline import compile_yaml, generate
from bmgen_eca.verify import verify_package


def _emit_diags(diags) -> None:
    for d in diags:
        print(format_diag(d), file=sys.stderr)
    print(format_report_footer(diags), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bmgen-eca")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="compile YAML without writing code")
    p_parse.add_argument("yaml_file", type=Path)

    p_gen = sub.add_parser("generate", help="compile YAML and write BM package")
    p_gen.add_argument("yaml_file", type=Path)
    p_gen.add_argument("--out", type=Path, required=True, help="output root directory")

    p_ver = sub.add_parser("verify", help="ast-parse generated package")
    p_ver.add_argument("package_dir", type=Path)

    sub.add_parser("errors", help="list frozen diagnostic codes")

    args = parser.parse_args(argv)

    if args.cmd == "errors":
        for code, meta in ERROR_CATALOG.items():
            print(f"{code}\t{meta['severity'].value}\t{meta['when']}\t{meta['help']}")
        return 0

    if args.cmd == "parse":
        ir, diags = compile_yaml(args.yaml_file)
        _emit_diags(diags)
        if ir is None or has_errors(diags):
            return 1
        return 0

    if args.cmd == "generate":
        pkg, diags = generate(args.yaml_file, args.out)
        _emit_diags(diags)
        if pkg is None or has_errors(diags):
            return 1
        print(f"wrote {pkg}")
        return 0

    if args.cmd == "verify":
        diags = verify_package(args.package_dir)
        _emit_diags(diags)
        if has_errors(diags):
            return 1
        return 0

    parser.error(f"unknown command: {args.cmd}")
    return 2
