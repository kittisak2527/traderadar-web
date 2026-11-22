"""Trade Radar Web — API บน Vercel (FastAPI)

GET  /api/health
GET  /api/analysis?asset=XAUUSD&tf=4h&side=auto      วิเคราะห์ 1 สินทรัพย์
GET  /api/status                                     สถานะ OI + ที่เก็บข้อมูล (?check=1 = ทดสอบเขียน/อ่าน Blob)
POST /api/oi            (header X-Admin-Token)       นำเข้าสตริง LOI1 จาก gold-oi-fetch
POST /api/cme-btc       (header X-Admin-Token)       นำเข้า CME BTC OI (JSON) ไว้รวมกับ Deribit
GET  /api/pine                                       ดาวน์โหลด Pine mrM Local OI จากข้อมูลล่าสุด
"""
import hmac
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tr"))

from fastapi import FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse, PlainTextResponse  # noqa: E402

import service  # noqa: E402
import store  # noqa: E402

app = FastAPI(title="Trade Radar Web")


def _auth(token: str | None):
    want = os.environ.get("TR_ADMIN_TOKEN", "").strip()
    if not want:
        raise HTTPException(503, "ยังไม่ได้ตั้งค่า TR_ADMIN_TOKEN ใน Environment Variables ของ Vercel")
    if not token or not hmac.compare_digest(token.strip(), want):
        raise HTTPException(401, "รหัสผู้ดูแล (Admin token) ไม่ถูกต้อง")


@app.get("/api/health")
def health():
    return {"ok": True, "storage": store.backend()}


@app.get("/api/analysis")
def analysis(asset: str = "XAUUSD", tf: str = "4h", side: str = "auto"):
    try:
        out = service.analyze(asset.upper(), tf, side)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"{type(e).__name__}: {str(e)[:200]}"}, status_code=503)
    return JSONResponse(out, headers={"Cache-Control": "public, max-age=0, s-maxage=30, stale-while-revalidate=120"})


@app.get("/api/status")
def status(check: int = 0):
    out = service.status()
    if check:
        out["selftest"] = store.self_test()
    return JSONResponse(out, headers={"Cache-Control": "no-store"})


@app.post("/api/oi")
async def import_oi(request: Request, x_admin_token: str | None = Header(default=None)):
    _auth(x_admin_token)
    ctype = request.headers.get("content-type", "")
    if "json" in ctype:
        body = await request.json()
        text, fut, oi_date = body.get("loi", ""), body.get("fut"), body.get("oi_date")
    else:
        text = (await request.body()).decode("utf-8")
        fut, oi_date = request.query_params.get("fut"), request.query_params.get("oi_date")
    try:
        saved = service.import_loi(text, fut, oi_date)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"อ่านข้อมูล LOI1 ไม่ได้: {e}")
    if not saved:
        raise HTTPException(400, "ไม่พบสตริง LOI1 ในข้อมูลที่ส่งมา")
    return {"saved": saved, "storage": store.backend()}


@app.post("/api/cme-btc")
async def import_cme(request: Request, x_admin_token: str | None = Header(default=None)):
    _auth(x_admin_token)
    obj = await request.json()
    for k in ("series", "exp_date", "rows"):
        if k not in obj:
            raise HTTPException(400, f"ขาดฟิลด์ {k}")
    service.import_cme_btc(obj)
    return {"ok": True}


@app.get("/api/pine")
def pine():
    try:
        code, assets = service.pine()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, str(e))
    return PlainTextResponse(code, headers={"Content-Disposition": 'attachment; filename="mrM_LOI_latest.pine"',
                                            "X-Assets": ", ".join(assets).encode("ascii", "ignore").decode(), "Cache-Control": "no-store"})
