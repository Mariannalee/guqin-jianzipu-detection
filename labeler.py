#!/usr/bin/env python3
"""依序標註減字譜字圖，保存五欄資料並提供相似圖片建議。"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

FIELDS = ("string1", "string2", "hui1", "hui2", "other")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def natural_key(path: Path):
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", path.name)]


def image_feature(path: Path) -> tuple[str, float]:
    """計算64-bit dHash與墨跡比例，供相似範例檢索。"""
    with Image.open(path) as source:
        gray = ImageOps.exif_transpose(source).convert("L")
        tiny = gray.resize((9, 8), Image.Resampling.LANCZOS)
        pixels = tiny.tobytes()
        value = 0
        for y in range(8):
            for x in range(8):
                value = (value << 1) | int(pixels[y * 9 + x + 1] < pixels[y * 9 + x])
        sample = gray.resize((64, 64), Image.Resampling.BILINEAR)
        ink_ratio = sum(pixel < 180 for pixel in sample.tobytes()) / 4096
    return f"{value:016x}", ink_ratio


def connect_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS images(
            image_id TEXT PRIMARY KEY, position INTEGER NOT NULL UNIQUE,
            dhash TEXT NOT NULL, ink_ratio REAL NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS labels(
            image_id TEXT PRIMARY KEY,
            string1 TEXT DEFAULT '', string2 TEXT DEFAULT '',
            hui1 TEXT DEFAULT '', hui2 TEXT DEFAULT '', other TEXT DEFAULT '',
            confirmed_at TEXT NOT NULL
        )
    """)
    db.execute("CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT)")
    db.commit()
    return db


def index_images(db: sqlite3.Connection, images: list[Path]) -> None:
    known = {row[0] for row in db.execute("SELECT image_id FROM images")}
    for position, path in enumerate(images):
        if path.name in known:
            db.execute("UPDATE images SET position=? WHERE image_id=?", (position, path.name))
            continue
        dhash, ink = image_feature(path)
        db.execute("INSERT INTO images VALUES(?,?,?,?)", (path.name, position, dhash, ink))
        if position % 500 == 0:
            db.commit()
    db.commit()


def export_csv(db: sqlite3.Connection, destination: Path) -> None:
    rows = db.execute("""
        SELECT i.position+1,i.image_id,l.string1,l.string2,l.hui1,l.hui2,
               l.other,l.confirmed_at
        FROM labels l JOIN images i ON i.image_id=l.image_id
        ORDER BY i.position
    """).fetchall()
    temp = destination.with_suffix(destination.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["order", "image", *FIELDS, "confirmed_at"])
        writer.writerows(rows)
    temp.replace(destination)


class Labeler:
    def __init__(self, root, image_dir: Path, db_path: Path, csv_path: Path):
        import tkinter as tk
        from tkinter import ttk
        from PIL import ImageTk

        self.tk, self.ttk, self.ImageTk, self.root = tk, ttk, ImageTk, root
        self.image_dir, self.db_path, self.csv_path = image_dir, db_path, csv_path
        self.db = connect_db(db_path)
        self.images = sorted(
            [path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES],
            key=natural_key,
        )
        if not self.images:
            raise SystemExit(f"資料夾中沒有圖片：{image_dir}")
        index_images(self.db, self.images)
        saved = self.db.execute("SELECT value FROM state WHERE key='position'").fetchone()
        self.index = min(int(saved[0]), len(self.images)-1) if saved else 0
        self.vars = {field: tk.StringVar() for field in FIELDS}
        self.status = tk.StringVar()
        self.suggestion_text = tk.StringVar()
        self.suggestions: list[tuple[str, ...]] = []
        self.photos = []

        root.title("古琴減字譜互動命名工具")
        root.geometry("1100x760")
        root.minsize(900, 650)
        root.protocol("WM_DELETE_WINDOW", self.close)

        header = ttk.Frame(root, padding=10)
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.status, font=("Arial", 14, "bold")).pack(side="left")
        ttk.Button(header, text="下一張未命名", command=self.next_unlabeled).pack(side="right")

        gallery = ttk.Frame(root, padding=8)
        gallery.pack(fill="x")
        self.gallery = []
        for offset in (-2, -1, 0, 1, 2):
            frame = ttk.Frame(gallery)
            frame.pack(side="left", fill="both", expand=True, padx=4)
            title = ttk.Label(frame, anchor="center")
            title.pack(fill="x")
            picture = ttk.Label(frame, anchor="center")
            picture.pack(expand=True)
            self.gallery.append((offset, title, picture))

        form = ttk.LabelFrame(root, text="目前圖片標註", padding=12)
        form.pack(fill="both", expand=True, padx=12, pady=6)
        for row, field in enumerate(FIELDS):
            ttk.Label(form, text=field, width=12).grid(row=row, column=0, sticky="e", padx=4, pady=5)
            entry = ttk.Entry(form, textvariable=self.vars[field], font=("Arial", 14))
            entry.grid(row=row, column=1, sticky="ew", padx=4, pady=5)
            if row == 0:
                self.first_entry = entry
        form.columnconfigure(1, weight=1)

        recommend = ttk.Frame(root, padding=(12, 2))
        recommend.pack(fill="x")
        ttk.Label(recommend, text="相似圖片建議：").pack(side="left")
        ttk.Label(recommend, textvariable=self.suggestion_text).pack(side="left", fill="x", expand=True)
        for number in range(3):
            ttk.Button(recommend, text=f"採用{number+1}",
                       command=lambda n=number: self.use_suggestion(n)).pack(side="right", padx=2)

        controls = ttk.Frame(root, padding=12)
        controls.pack(fill="x")
        ttk.Button(controls, text="← 上一張", command=lambda: self.move(-1)).pack(side="left")
        ttk.Button(controls, text="確認並到下一張（Enter）", command=self.confirm).pack(side="left", expand=True)
        ttk.Button(controls, text="下一張 →", command=lambda: self.move(1)).pack(side="right")
        root.bind("<Left>", lambda _event: self.move(-1))
        root.bind("<Right>", lambda _event: self.move(1))
        root.bind("<Return>", lambda _event: self.confirm())
        self.refresh()

    def labeled(self, image_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM labels WHERE image_id=?", (image_id,)).fetchone() is not None

    def refresh_gallery(self) -> None:
        self.photos.clear()
        for offset, title, picture in self.gallery:
            position = self.index + offset
            if not 0 <= position < len(self.images):
                title.configure(text="")
                picture.configure(image="")
                continue
            path = self.images[position]
            mark = " ✓" if self.labeled(path.name) else ""
            title.configure(text=("目前：" if offset == 0 else f"{offset:+d}：") + path.name + mark)
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                size = (300, 300) if offset == 0 else (150, 150)
                image.thumbnail(size, Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", size, "white")
                canvas.paste(image, ((size[0]-image.width)//2, (size[1]-image.height)//2))
            photo = self.ImageTk.PhotoImage(canvas)
            picture.configure(image=photo)
            self.photos.append(photo)

    def make_suggestions(self) -> None:
        image_id = self.images[self.index].name
        target_row = self.db.execute(
            "SELECT dhash,ink_ratio FROM images WHERE image_id=?", (image_id,)
        ).fetchone()
        rows = self.db.execute("""
            SELECT i.dhash,i.ink_ratio,l.string1,l.string2,l.hui1,l.hui2,l.other
            FROM labels l JOIN images i ON i.image_id=l.image_id
        """).fetchall()
        if not rows:
            self.suggestions = []
            self.suggestion_text.set("尚無已確認範例，請先人工輸入。")
            return
        target_hash, target_ink = int(target_row[0], 16), target_row[1]
        scores = defaultdict(float)
        for dhash, ink, *record in rows:
            distance = (target_hash ^ int(dhash, 16)).bit_count() + abs(target_ink-ink) * 35
            scores[tuple(record)] += 1 / (1 + distance)
        self.suggestions = sorted(scores, key=scores.get, reverse=True)[:3]
        summaries = []
        for record in self.suggestions:
            summaries.append(", ".join(f"{field}={value}" for field, value in zip(FIELDS, record) if value))
        self.suggestion_text.set(" ｜ ".join(summaries))

    def use_suggestion(self, number: int) -> None:
        if number >= len(self.suggestions):
            return
        for field, value in zip(FIELDS, self.suggestions[number]):
            self.vars[field].set(value)

    def refresh(self) -> None:
        current = self.images[self.index].name
        count = self.db.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
        self.status.set(f"第 {self.index+1:,}/{len(self.images):,} 張　{current}　已確認 {count:,} 張")
        self.refresh_gallery()
        record = self.db.execute(
            "SELECT string1,string2,hui1,hui2,other FROM labels WHERE image_id=?", (current,)
        ).fetchone()
        for field, value in zip(FIELDS, record or ("",) * len(FIELDS)):
            self.vars[field].set(value)
        if record:
            self.suggestions = []
            self.suggestion_text.set("此張已確認，可修改後再次確認。")
        else:
            self.make_suggestions()
        self.first_entry.focus_set()

    def save_position(self) -> None:
        self.db.execute("INSERT OR REPLACE INTO state VALUES('position',?)", (str(self.index),))
        self.db.commit()

    def move(self, offset: int) -> None:
        self.index = max(0, min(len(self.images)-1, self.index + offset))
        self.save_position()
        self.refresh()

    def confirm(self) -> None:
        values = [self.vars[field].get().strip() for field in FIELDS]
        if not any(values):
            self.root.bell()
            self.status.set("請至少填寫一個欄位；無法辨認可在other填入不確定。")
            return
        image_id = self.images[self.index].name
        self.db.execute("""
            INSERT OR REPLACE INTO labels
            (image_id,string1,string2,hui1,hui2,other,confirmed_at)
            VALUES(?,?,?,?,?,?,?)
        """, (image_id, *values, datetime.now().isoformat(timespec="seconds")))
        self.db.commit()
        export_csv(self.db, self.csv_path)
        if self.index < len(self.images)-1:
            self.index += 1
        self.save_position()
        self.refresh()

    def next_unlabeled(self) -> None:
        order = list(range(self.index+1, len(self.images))) + list(range(self.index))
        for position in order:
            if not self.labeled(self.images[position].name):
                self.index = position
                self.save_position()
                self.refresh()
                return
        self.status.set("所有圖片都已命名。")

    def close(self) -> None:
        self.save_position()
        export_csv(self.db, self.csv_path)
        self.db.close()
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="古琴減字譜互動命名工具")
    parser.add_argument("images", type=Path, help="依序命名的單字圖片資料夾")
    parser.add_argument("--database", type=Path, help="SQLite位置；預設放在圖片資料夾")
    parser.add_argument("--csv", type=Path, help="CSV位置；預設放在圖片資料夾")
    parser.add_argument("--build-index", action="store_true", help="只建立影像特徵索引，不開啟視窗")
    args = parser.parse_args()
    image_dir = args.images.expanduser().resolve()
    if not image_dir.is_dir():
        parser.error(f"找不到圖片資料夾：{image_dir}")
    db_path = (args.database or image_dir / "guqin_labels.sqlite3").resolve()
    csv_path = (args.csv or image_dir / "guqin_labels.csv").resolve()
    images = sorted(
        [path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES], key=natural_key
    )
    if not images:
        parser.error("圖片資料夾中沒有支援的影像")
    db = connect_db(db_path)
    index_images(db, images)
    db.close()
    if args.build_index:
        print(f"索引完成：{len(images)}張；資料庫：{db_path}")
        return
    import tkinter as tk
    root = tk.Tk()
    Labeler(root, image_dir, db_path, csv_path)
    root.mainloop()


if __name__ == "__main__":
    main()
