# clasificador_por_contenido.py
# -*- coding: utf-8 -*-

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Config:
    input_dir: Path
    base_output_dir: Path
    action: str                 # "move" o "copy"
    dry_run: bool
    recursive: bool
    encoding_list: List[str]
    line_prefix_regex: str      # regex para extraer carpeta desde una línea
    scan_max_lines: int         # cuántas líneas leer por archivo (0 = todo)
    priority: str               # "first" o "most_frequent"
    no_match_dest: str
    allowed_extensions: List[str]  # [".txt", ".csv", ".log"] o ["*"]


def normalize_ext(ext: str) -> str:
    ext = ext.strip().lower()
    if ext in ("*", ".*"):
        return "*"
    if not ext.startswith("."):
        ext = "." + ext
    return ext


def load_config(path: Path) -> Config:
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    return Config(
        input_dir=Path(cfg["input_dir"]).expanduser().resolve(),
        base_output_dir=Path(cfg["base_output_dir"]).expanduser().resolve(),
        action=cfg.get("action", "move").strip().lower(),
        dry_run=bool(cfg.get("dry_run", False)),
        recursive=bool(cfg.get("recursive", False)),
        encoding_list=list(cfg.get("encoding_list", ["utf-8", "utf-8-sig", "cp1252", "latin-1"])),
        line_prefix_regex=cfg.get("line_prefix_regex", r"^\s*(\d{2,5})-"),
        scan_max_lines=int(cfg.get("scan_max_lines", 300)),
        priority=cfg.get("priority", "first").strip().lower(),  # first | most_frequent
        no_match_dest=cfg.get("no_match_dest", "_NO_CLASIFICADO"),
        allowed_extensions=[normalize_ext(e) for e in cfg.get("allowed_extensions", ["*"])],
    )


def iter_files(input_dir: Path, recursive: bool):
    if recursive:
        return [p for p in input_dir.rglob("*") if p.is_file()]
    return [p for p in input_dir.iterdir() if p.is_file()]


def unique_destination_path(dest_dir: Path, original_name: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidate = dest_dir / original_name
    if not candidate.exists():
        return candidate

    stem = Path(original_name).stem
    suf = Path(original_name).suffix
    i = 1
    while True:
        candidate = dest_dir / f"{stem} ({i}){suf}"
        if not candidate.exists():
            return candidate
        i += 1


def log_line(log_path: Path, line: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def ext_allowed(file_path: Path, allowed_extensions: List[str]) -> bool:
    if "*" in allowed_extensions:
        return True
    return file_path.suffix.lower() in allowed_extensions


def read_text_best_effort(file_path: Path, encodings: List[str]) -> Optional[str]:
    for enc in encodings:
        try:
            return file_path.read_text(encoding=enc, errors="strict")
        except Exception:
            continue
    try:
        return file_path.read_text(encoding=encodings[0], errors="replace")
    except Exception:
        return None


def extract_folder_code_from_content(
    text: str,
    line_prefix_regex: str,
    scan_max_lines: int,
    priority: str
) -> Optional[str]:
    pattern = re.compile(line_prefix_regex, flags=re.IGNORECASE)

    lines = text.splitlines()
    if scan_max_lines and scan_max_lines > 0:
        lines = lines[:scan_max_lines]

    matches: List[str] = []
    for line in lines:
        m = pattern.search(line)
        if m:
            matches.append(m.group(1))
            if priority == "first":
                return m.group(1)

    if not matches:
        return None

    if priority == "most_frequent":
        freq: Dict[str, int] = {}
        for c in matches:
            freq[c] = freq.get(c, 0) + 1
        best = sorted(freq.items(), key=lambda x: (-x[1], matches.index(x[0])))[0][0]
        return best

    return matches[0]


def main():
    parser = argparse.ArgumentParser(
        description="Clasifica archivos por código (ej: 600, 200, 500) leído desde el CONTENIDO del archivo."
    )
    parser.add_argument("--config", required=True, help="Ruta a config.json")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    cfg = load_config(config_path)

    if cfg.action not in ("move", "copy"):
        raise ValueError("config.action debe ser 'move' o 'copy'")

    if cfg.priority not in ("first", "most_frequent"):
        raise ValueError("config.priority debe ser 'first' o 'most_frequent'")

    if not cfg.input_dir.exists():
        raise FileNotFoundError(f"No existe input_dir: {cfg.input_dir}")

    cfg.base_output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = cfg.base_output_dir / "_logs" / f"clasificacion_{timestamp}.log"

    files = iter_files(cfg.input_dir, cfg.recursive)

    log_line(log_path, f"CONFIG: {config_path}")
    log_line(log_path, f"INPUT : {cfg.input_dir}")
    log_line(log_path, f"OUTPUT: {cfg.base_output_dir}")
    log_line(log_path, f"ACTION: {cfg.action} | DRY_RUN: {cfg.dry_run} | RECURSIVE: {cfg.recursive}")
    log_line(log_path, f"REGEX : {cfg.line_prefix_regex} | MAX_LINES: {cfg.scan_max_lines} | PRIORITY: {cfg.priority}")
    log_line(log_path, "-" * 90)

    processed = 0
    moved = 0
    skipped_ext = 0
    no_match = 0
    read_fail = 0

    for fpath in files:
        if not ext_allowed(fpath, cfg.allowed_extensions):
            skipped_ext += 1
            log_line(log_path, f"SKIP(EXT): {fpath}")
            continue

        text = read_text_best_effort(fpath, cfg.encoding_list)
        if text is None:
            read_fail += 1
            dest_dir = cfg.base_output_dir / cfg.no_match_dest
            dest_path = unique_destination_path(dest_dir, fpath.name)
            if cfg.dry_run:
                log_line(log_path, f"DRYRUN [READ_FAIL] {fpath} -> {dest_path}")
            else:
                try:
                    if cfg.action == "move":
                        shutil.move(str(fpath), str(dest_path))
                    else:
                        shutil.copy2(str(fpath), str(dest_path))
                    moved += 1
                    log_line(log_path, f"OK     [READ_FAIL] {fpath} -> {dest_path}")
                except Exception as e:
                    log_line(log_path, f"ERROR  [READ_FAIL] {fpath} -> {dest_path} | {e}")
            processed += 1
            continue

        code = extract_folder_code_from_content(
            text=text,
            line_prefix_regex=cfg.line_prefix_regex,
            scan_max_lines=cfg.scan_max_lines,
            priority=cfg.priority
        )

        if code is None:
            no_match += 1
            dest_dir = cfg.base_output_dir / cfg.no_match_dest
            tag = "NO_MATCH"
        else:
            dest_dir = cfg.base_output_dir / code
            tag = code

        dest_path = unique_destination_path(dest_dir, fpath.name)

        if cfg.dry_run:
            log_line(log_path, f"DRYRUN [{tag}] {fpath} -> {dest_path}")
        else:
            try:
                if cfg.action == "move":
                    shutil.move(str(fpath), str(dest_path))
                else:
                    shutil.copy2(str(fpath), str(dest_path))
                moved += 1
                log_line(log_path, f"OK     [{tag}] {fpath} -> {dest_path}")
            except Exception as e:
                log_line(log_path, f"ERROR  [{tag}] {fpath} -> {dest_path} | {e}")

        processed += 1

    log_line(log_path, "-" * 90)
    log_line(log_path, f"RESUMEN: total={len(files)} procesados={processed} movidos/copiados={moved} "
                       f"skip_ext={skipped_ext} no_match={no_match} read_fail={read_fail}")
    print(f"Listo. Log: {log_path}")
    print(f"Total: {len(files)} | Procesados: {processed} | Movidos/Copiados: {moved}")
    print(f"Skip ext: {skipped_ext} | No match: {no_match} | Read fail: {read_fail}")


if __name__ == "__main__":
    main()
