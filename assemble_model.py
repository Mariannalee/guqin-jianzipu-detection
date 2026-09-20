#!/usr/bin/env python3
"""合併GitHub上的分割檔，還原PP-OCRv5模型權重。"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARTS = ROOT / "model_parts"
OUTPUT = ROOT / "model/best_accuracy.pdparams"
EXPECTED_SHA256 = "f8a907b9d3f3079fe31d7c4f567a3fb0bd2f394ae1490e711d41ac51a7cd276f"


def main() -> None:
    parts = sorted(PARTS.glob("best_accuracy.pdparams.part-*"))
    if not parts:
        raise SystemExit(f"找不到模型分割檔：{PARTS}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with OUTPUT.open("wb") as target:
        for part in parts:
            data = part.read_bytes()
            target.write(data)
            digest.update(data)
    actual = digest.hexdigest()
    if actual != EXPECTED_SHA256:
        OUTPUT.unlink(missing_ok=True)
        raise SystemExit(f"模型驗證失敗：{actual}")
    print(f"模型已還原：{OUTPUT}")
    print(f"SHA-256：{actual}")


if __name__ == "__main__":
    main()
