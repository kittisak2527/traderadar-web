"""สร้าง Pine Script mrM Local OI สำเร็จรูป (logic เดียวกับ buildPine ของ mrM OI Desk)

- template: pine/template.pine (คัดลอกจาก OI Desk · v1.5)
- ใส่ snapshot ล่าสุดของทุกสินทรัพย์ลง DATA_EMBED, DATA_2 … DATA_12 (ก้อนละ ≤ 3,400 ตัวอักษร ตัดที่ขอบแถว)
- ปรับค่าเริ่มต้นสัญญา futures (Auto basis) ให้ตรงกับ underlying ของ series อัตโนมัติ
- ห้ามแก้ลำดับ plot ท้ายไฟล์ ("LOI", "OI #1"…"OI #5", "OI ทิศ") เพราะ mrM Flow OB อ่านตามลำดับ
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
TPL = ROOT / "pine" / "template.pine"
OUT = ROOT / "pine" / "mrM_LOI_latest.pine"
CHUNK, NCHUNK = 3400, 12
TH = ZoneInfo("Asia/Bangkok")
MONTHS = "FGHJKMNQUVXZ"

# ช่อง input futures ใน template → (prefix ของ TradingView)
FUT_INPUT = {"GOLD": ("iFutG", "COMEX:GC"), "EUR": ("iFutE", "CME:6E"), "BTC": ("iFutB", "CME:BTC")}


def chunk_data(data: str) -> list[str]:
    bar = data.find("|")
    head = data[: bar + 1] if bar >= 0 else data
    rows = data[bar + 1:].split("/") if bar >= 0 and len(data) > bar + 1 else []
    chunks, cur, cnt = [], head, 0
    for r in rows:
        add = ("" if cnt == 0 else "/") + r
        if cnt > 0 and len(cur) + len(add) > CHUNK:
            chunks.append(cur)
            cur, cnt = r, 1
            continue
        cur += add
        cnt += 1
    chunks.append(cur)
    return chunks


def fut_symbol(asset: str, fut_code: str | None) -> str | None:
    """GCZ6 → COMEX:GCZ2026 · 6EZ6 → CME:6EZ2026 · BTCX6 → CME:BTCX2026"""
    if not fut_code:
        return None
    m = re.match(r"^(GC|6E|BTC)([FGHJKMNQUVXZ])(\d)$", fut_code)
    if not m:
        return None
    y = datetime.now(TH).year
    yr = y - y % 10 + int(m.group(3))
    if yr < y - 1:
        yr += 10
    return f"{FUT_INPUT[asset][1]}{m.group(2)}{yr}"


def build(snaps: list[dict]) -> str:
    """snaps: [{asset, series, loi, t_ms, n_rows, fut}] ตัวแรกคือสินทรัพย์ที่เพิ่งอัปเดต"""
    tpl = TPL.read_text(encoding="utf-8")
    chunks = [c for s in snaps for c in chunk_data(s["loi"])]
    if len(chunks) > NCHUNK:
        raise ValueError(f"ข้อมูลยาวเกิน {NCHUNK} ก้อน")
    meta = ["ข้อมูลจาก mrM OI Desk (เวลาไทย):"] + [
        f"{s['asset']} {s['series']} · snapshot {datetime.fromtimestamp(s['t_ms'] / 1000, TH):%d %b %Y %H:%M} · {s['n_rows']} strike"
        for s in snaps]
    meta.append(f"สร้างอัตโนมัติโดย Trade Radar · {datetime.now(TH):%d %b %Y %H:%M}")
    lines = ["// @@DATA_START"] + ["// " + m for m in meta]
    for i in range(NCHUNK):
        name = "DATA_EMBED" if i == 0 else f"DATA_{i + 1}"
        val = chunks[i] if i < len(chunks) else ""
        pieces = [val[j:j + 380] for j in range(0, len(val), 380)] or [""]
        for j, p in enumerate(pieces):
            lines.append((f'string {name} = "' if j == 0 else '     "') + p + '"' + (" +" if j < len(pieces) - 1 else ""))
    lines.append("// @@DATA_END")
    out = re.sub(r"// @@DATA_START[\s\S]*?// @@DATA_END", lambda _: "\n".join(lines), tpl, count=1)
    # roll ค่าเริ่มต้นสัญญา futures ตาม underlying ของ series
    for s in snaps:
        sym = fut_symbol(s["asset"], s.get("fut"))
        if sym:
            var = FUT_INPUT[s["asset"]][0]
            out = re.sub(rf'(string {var}\s*=\s*input\.symbol\(")[^"]+(")', rf"\g<1>{sym}\g<2>", out, count=1)
    return out


def write(snaps: list[dict]) -> Path:
    OUT.write_text(build(snaps), encoding="utf-8")
    return OUT
