#!/usr/bin/env python3
"""使用微調後的PP-OCRv5模型偵測古琴減字譜候選字框。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "configs/guqin_PP-OCRv5_mobile_det.yml"
DEFAULT_MODEL = ROOT / "model/best_accuracy.pdparams"


def main() -> int:
    parser = argparse.ArgumentParser(description="古琴減字譜候選字框偵測")
    parser.add_argument("input", type=Path, help="一張影像或包含影像的資料夾")
    parser.add_argument("--paddle-dir", type=Path, required=True, help="PaddleOCR原始碼資料夾")
    parser.add_argument("--output", type=Path, default=ROOT / "output", help="輸出資料夾")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()

    input_path = args.input.resolve()
    paddle_dir = args.paddle_dir.resolve()
    config = args.config.resolve()
    model = args.model.resolve()
    infer_script = paddle_dir / "tools/infer_det.py"
    for path, label in (
        (input_path, "輸入影像"), (infer_script, "PaddleOCR推論程式"),
        (config, "設定檔"), (model, "模型權重"),
    ):
        if not path.exists():
            if path == model:
                parser.error(f"找不到{label}：{path}\n請先執行：python assemble_model.py")
            parser.error(f"找不到{label}：{path}")

    args.output.mkdir(parents=True, exist_ok=True)
    result_file = (args.output / "predictions.txt").resolve()
    # PaddleOCR的checkpoints參數使用不含.pdparams的前綴。
    checkpoint = model.with_suffix("") if model.suffix == ".pdparams" else model
    command = [
        sys.executable, str(infer_script), "-c", str(config), "-o",
        f"Global.infer_img={input_path}",
        f"Global.checkpoints={checkpoint}",
        f"Global.save_res_path={result_file}",
    ]
    print("執行：", " ".join(command))
    subprocess.run(command, cwd=paddle_dir, check=True)
    print(f"完成。座標結果：{result_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
