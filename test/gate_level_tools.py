#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
INFO_YAML = REPO_ROOT / "info.yaml"
STAGED_NETLIST = TEST_DIR / "gate_level_netlist.v"


def top_module() -> str:
    text = INFO_YAML.read_text(encoding="utf-8")
    match = re.search(r'^\s*top_module:\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not find top_module in {INFO_YAML}")
    return match.group(1)


def gate_netlist_candidates() -> list[Path]:
    top = top_module()
    candidates: list[Path] = []

    if STAGED_NETLIST.exists():
        candidates.append(STAGED_NETLIST)

    patterns = [
        f"runs/*/final/pnl/{top}.pnl.v",
        f"runs/*/results/placement/{top}.pnl.v",
        f"tt_submission/{top}.v",
        f"runs/*/results/placement/{top}.nl.v",
        f"runs/*/results/synthesis/{top}.v",
    ]

    for pattern in patterns:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if path.is_file() and path not in candidates:
                candidates.append(path)

    return candidates


def best_gate_netlist_source() -> Path | None:
    for path in gate_netlist_candidates():
        if path != STAGED_NETLIST:
            return path
    if STAGED_NETLIST.exists():
        return STAGED_NETLIST
    return None


def stage_gate_netlist() -> Path:
    source = best_gate_netlist_source()
    if source is None:
        raise FileNotFoundError(
            "No gate-level netlist found. Expected one of: "
            "runs/*/final/pnl/<top>.pnl.v, runs/*/results/placement/<top>.pnl.v, "
            "tt_submission/<top>.v, runs/*/results/placement/<top>.nl.v, "
            "runs/*/results/synthesis/<top>.v, or an existing test/gate_level_netlist.v"
        )

    if source != STAGED_NETLIST:
        shutil.copy2(source, STAGED_NETLIST)
    return STAGED_NETLIST


def netlist_has_power_pins(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    head = "\n".join(text.splitlines()[:200])
    return "VPWR" in head and "VGND" in head


def candidate_pdk_roots() -> list[Path]:
    roots: list[Path] = []

    if os.environ.get("SKY130A"):
        roots.append(Path(os.environ["SKY130A"]))

    if os.environ.get("PDK_ROOT"):
        for variant in ("sky130A", "sky130B"):
            roots.append(Path(os.environ["PDK_ROOT"]) / variant)

    home = Path.home()
    for variant in ("sky130A", "sky130B"):
        roots.append(home / ".volare" / variant)
        roots.append(Path("/usr/share/pdk") / variant)

    ciel_root = home / ".ciel" / "ciel" / "sky130" / "versions"
    if ciel_root.is_dir():
        for version_dir in sorted(ciel_root.iterdir()):
            for variant in ("sky130A", "sky130B"):
                roots.append(version_dir / variant)

    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        unique.append(root)
    return unique


def find_pdk_file(relative_path: str) -> Path | None:
    for root in candidate_pdk_roots():
        candidate = root / relative_path
        if candidate.is_file():
            return candidate
    return None


def require_pdk_file(relative_path: str) -> Path:
    result = find_pdk_file(relative_path)
    if result is None:
        raise FileNotFoundError(
            f"Could not locate {relative_path}. Set SKY130A or PDK_ROOT, or install the sky130 PDK."
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "top-module",
            "find-netlist",
            "stage-netlist",
            "netlist-has-power-pins",
            "sim-models",
            "liberty",
        ),
    )
    args = parser.parse_args()

    try:
        if args.command == "top-module":
            print(top_module())
            return 0

        if args.command == "find-netlist":
            path = best_gate_netlist_source()
            if path is None:
                return 1
            print(path)
            return 0

        if args.command == "stage-netlist":
            print(stage_gate_netlist())
            return 0

        if args.command == "netlist-has-power-pins":
            path = best_gate_netlist_source()
            if path is None:
                return 1
            print("1" if netlist_has_power_pins(path) else "0")
            return 0

        if args.command == "sim-models":
            print(require_pdk_file("libs.ref/sky130_fd_sc_hd/verilog/primitives.v"))
            print(require_pdk_file("libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v"))
            return 0

        if args.command == "liberty":
            print(require_pdk_file("libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"))
            return 0

    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
