# 📡 Trade Radar Web — คู่มือขึ้น Vercel แบบละเอียด

Trade Radar เวอร์ชันเว็บ (ย้ายจาก Streamlit บนเครื่อง) ใช้ logic ชุดเดียวกับ `TradeRadar_portable` ที่ปรับปรุงแล้ว:
หกเหลี่ยมทิศทาง · หกเหลี่ยม Entry Edge (E1–E6) · Options OI (mrM OI Desk) · ดาวน์โหลด Pine mrM Local OI

| ส่วน | บนเครื่อง (Streamlit) | บนเว็บ (Vercel) |
|---|---|---|
| หน้าจอ | Streamlit | HTML + Plotly (เปิดจากมือถือได้) |
| ข้อมูล OI ทอง/EUR | ไฟล์ `oi_data/` | **Vercel Blob** (ที่เก็บไฟล์ของ Vercel ในบัญชีเดิม) |
| BTC (Deribit) | Task Scheduler ทุก 1 ชม. | ดึงเองตอนเปิดหน้าเว็บ (แคช 30 นาที) ไม่ต้องตั้งเวลา |
| นำเข้า LOI1 | `autofetch.py --import` | วางในหน้าเว็บ หรือให้ Claude ส่งเข้า `/api/oi` (ต้องมี Admin token) |
| Pine | ไฟล์ `pine/mrM_LOI_latest.pine` | ปุ่มดาวน์โหลด (สร้างใหม่ทุกครั้งจากข้อมูลล่าสุด) |

---

## ขั้นที่ 1 · อัปโหลดโค้ดขึ้น GitHub

1. เปิด https://github.com/new
2. **Repository name:** `traderadar-web` · เลือก **Private** (แนะนำ เพราะมีข้อมูล OI ตั้งต้นของคุณ) → กด **Create repository**
3. ในหน้า repo ว่าง กดลิงก์ **uploading an existing file**
4. เปิดโฟลเดอร์ `Desktop\usd-forecast-desk\traderadar-web` บนเครื่อง → **เลือกทุกอย่างข้างใน** แล้วลากไปวางในหน้า GitHub ต้องมีครบดังนี้:
   ```
   index.html  README.md  requirements.txt  vercel.json  dev_server.py  .gitignore  .vercelignore
   api/index.py
   api/_tr/   (ไฟล์ .py ทั้งหมด + โฟลเดอร์ pine/ และ seed/)
   static/app.js  static/style.css
   ```
   > ⚠️ `index.html` ต้องอยู่ชั้นบนสุดของ repo (อย่าลากตัวโฟลเดอร์ `traderadar-web` ทั้งก้อน)
   > ถ้าไฟล์ที่ขึ้นต้นด้วยจุด (`.gitignore`, `.vercelignore`) ลากไม่ติด ข้ามได้ ไม่กระทบการทำงาน
5. เลื่อนลงล่าง กด **Commit changes** → รอจนเห็นไฟล์ครบในหน้า repo (ตรวจว่ามีโฟลเดอร์ `api/_tr/seed` และ `api/_tr/pine`)

## ขั้นที่ 2 · สร้างโปรเจกต์บน Vercel

1. เปิด https://vercel.com/new (บัญชีเดียวกับ 4 desk)
2. ส่วน **Import Git Repository** → หา `traderadar-web` → กด **Import**
   (ถ้าไม่เห็น repo: กด **Adjust GitHub App Permissions** → เพิ่มสิทธิ์ให้ repo นี้)
3. หน้าตั้งค่า:
   - **Project Name:** `traderadar-web`
   - **Application Preset / Framework:** **Other** (ถ้าขึ้นคำเตือน *configuration mismatch* ไม่ต้องสนใจ)
   - **Root Directory:** `./`
   - Build and Output Settings / Environment Variables: **ยังไม่ต้องแก้**
4. กด **Deploy** → รอประมาณ 1–2 นาที จนขึ้น Congratulations
5. ทดสอบ: เปิด `https://<ชื่อโปรเจกต์>.vercel.app/api/health` ต้องเห็น
   ```json
   {"ok": true, "storage": "local"}
   ```
   (`local` = ยังไม่ได้เชื่อม Blob ซึ่งถูกต้องในขั้นนี้)
6. เปิดหน้าแรก `https://<ชื่อโปรเจกต์>.vercel.app` — **ครั้งแรกใช้เวลา 20–40 วินาที** เพราะต้องดึงข้อมูลมหภาค/ยีลด์/COT ครั้งแรก ครั้งต่อไปจะเร็วขึ้นมาก

> โปรเจกต์นี้ตั้ง `"regions": ["sin1"]` ไว้ใน `vercel.json` แล้ว (รันที่สิงคโปร์ เพราะ Binance บล็อก IP สหรัฐฯ) — แพลนฟรีเลือกได้ 1 region และไม่กระทบโปรเจกต์อื่น

## ขั้นที่ 3 · เชื่อม Vercel Blob (ที่เก็บข้อมูล OI ถาวร)

ไม่ต้องสมัครที่ไหนเพิ่ม ใช้บัญชี Vercel เดิม

1. เข้าโปรเจกต์ `traderadar-web` บน Vercel → แท็บ **Storage** (เมนูด้านบน)
2. กด **Create Database** (หรือ **Create**) → เลือก **Blob** → **Continue**
3. ตั้งชื่อ store เช่น `traderadar-oi` → **Create**
4. หน้าถัดไปให้ **Connect** กับโปรเจกต์ `traderadar-web` → ติ๊ก Environments ให้ครบ (**Production**, **Preview**, **Development**) → **Connect**
   - Vercel จะเพิ่มตัวแปร `BLOB_READ_WRITE_TOKEN` ให้โปรเจกต์อัตโนมัติ (ดูได้ที่ Settings → Environment Variables)
5. **Redeploy** เพื่อให้ตัวแปรใหม่มีผล: แท็บ **Deployments** → deployment บนสุด → ปุ่ม **⋯** → **Redeploy** → **Redeploy**
6. ตรวจ: เปิด `/api/health` ต้องเห็น `"storage": "vercel-blob"`
7. ในหน้าเว็บ เลื่อนลงไปการ์ด **⏱️ สถานะข้อมูล OI** → กด **ทดสอบที่เก็บข้อมูล** ต้องขึ้น **✅ เขียน/อ่านได้**
   - ถ้าขึ้น ❌ ให้คัดลอกข้อความ error มาให้ Claude ดู

## ขั้นที่ 4 · ตั้ง Admin token (รหัสสำหรับนำเข้า OI)

กันไม่ให้คนอื่นเขียนข้อมูล OI ทับ (คนที่เปิดดูหน้าเว็บอ่านได้อย่างเดียว)

1. สร้างรหัสสุ่ม — เปิด PowerShell แล้วรัน:
   ```powershell
   -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object { [char]$_ })
   ```
   คัดลอกผลลัพธ์ (ตัวอักษร 40 ตัว) เก็บไว้ในที่ปลอดภัย
2. Vercel → โปรเจกต์ → **Settings** → **Environment Variables**
   - **Key:** `TR_ADMIN_TOKEN`
   - **Value:** วางรหัสจากข้อ 1
   - Environments: ติ๊กทั้งหมด → **Save**
3. **Redeploy** อีกครั้ง (เหมือนขั้นที่ 3 ข้อ 5)

## ขั้นที่ 5 · นำเข้า OI ทอง / EUR

ข้อมูลตั้งต้น (OI วันที่ 20 พ.ย.) ติดมากับโค้ดแล้ว หน้าเว็บจึงใช้งานได้ทันที เมื่อมี OI ชุดใหม่:

**วิธี A — วางในหน้าเว็บ**
1. ดึง OI ด้วย gold-oi-fetch ตามปกติ → คัดลอกสตริง `LOI1;a=…`
2. หน้าเว็บ → การ์ด **📥 นำเข้า OI · 📜 Pine** → เปิด "วางสตริง LOI1…"
3. วางสตริง (วางหลายบรรทัดพร้อมกันได้) · ใส่สัญญา เช่น `GCZ6` / `6EZ6` และวันที่ OI (ไม่บังคับ แต่ช่วยให้ระบบแจ้งเตือนรอบถัดไปถูก)
4. ใส่ Admin token (ครั้งแรกครั้งเดียว เบราว์เซอร์จะจำไว้) → **บันทึก OI**

**วิธี B — ให้ Claude ส่งให้หลังดึง OI** (คำสั่งที่ Claude จะใช้)
```powershell
$body = @{ loi = (Get-Content loi.txt -Raw); fut = "GCZ6"; oi_date = "2026-11-23" } | ConvertTo-Json
Invoke-RestMethod "https://<ชื่อโปรเจกต์>.vercel.app/api/oi" -Method Post -ContentType "application/json" -Headers @{ "x-admin-token" = $env:TR_ADMIN_TOKEN } -Body $body
```
(ตั้ง `$env:TR_ADMIN_TOKEN` บนเครื่องก่อน หรือบอก Claude ให้ถามรหัสตอนส่ง)

**CME BTC (ไม่บังคับ):** ถ้าต้องการรวม OI ของ CME BTC เข้ากับ Deribit ส่ง JSON `{series, fut, oi_date, exp_date, rows:[[strike, call, put], …]}` ไปที่ `POST /api/cme-btc` ด้วย token เดียวกัน

## ขั้นที่ 6 · Pine Script
หน้าเว็บ → **⬇️ ดาวน์โหลด Pine** → TradingView → Pine Editor → เปิด mrM Local OI → เลือกทั้งหมด → วางทับ → Save (alert ต้องสร้างใหม่)
ไฟล์สร้างใหม่ทุกครั้งที่กด จากข้อมูล OI ล่าสุดทั้ง 3 สินทรัพย์ และปรับสัญญา futures ตามรอบให้อัตโนมัติ

---

## การใช้งานประจำวัน
- เลือกสินทรัพย์จากการ์ดด้านบน · timeframe 15m / 1h / 4h / 1d · ฝั่ง อัตโนมัติ / BUY / SELL
- หน้าเว็บรีเฟรชเองตามที่ตั้ง (ค่าเริ่มต้น 60 วินาที) · ปุ่ม **วิธีอ่าน** มีคำอธิบายทุกส่วน
- การ์ด **สถานะข้อมูล OI** ขึ้น 🔔 เมื่อถึงเวลาดึง OI ทอง/EUR ใหม่ (หลังเที่ยงคืนชิคาโก ≈ 13:00 น. ไทย) หรือ series หมดอายุ → สั่ง Claude "ดึง OI ทอง / EUR"

## แก้ปัญหา
| อาการ | สาเหตุ / ทางแก้ |
|---|---|
| เปิดครั้งแรกช้า 20–40 วินาที | ปกติ (ฟังก์ชันเพิ่งตื่น + ดึงข้อมูลครั้งแรก) ครั้งต่อไปเร็วขึ้น |
| การ์ดสินทรัพย์ขึ้น "โหลดไม่ได้" | แหล่งข้อมูลล่มชั่วคราว กด **วิเคราะห์ใหม่** · ถ้ายังไม่ได้ ดู log ที่ Vercel → Deployments → **Logs** |
| หมายเหตุ "Binance Futures" ในแหล่งที่โหลดไม่ได้ | Binance บล็อก — ตรวจว่า `vercel.json` มี `"regions": ["sin1"]` (ราคา BTC จะสลับไปใช้ Yahoo อัตโนมัติ) |
| สถานะที่เก็บข้อมูลเป็น "ชั่วคราว" | ยังไม่ได้เชื่อม Blob หรือยังไม่ได้ Redeploy หลังเชื่อม (ขั้นที่ 3) |
| นำเข้า OI แล้วขึ้น 401 | Admin token ไม่ตรงกับ `TR_ADMIN_TOKEN` |
| นำเข้า OI แล้วขึ้น 503 "ยังไม่ได้ตั้งค่า TR_ADMIN_TOKEN" | ทำขั้นที่ 4 แล้ว Redeploy |

## รันบนเครื่อง (ทดสอบ)
```powershell
pip install fastapi uvicorn pandas numpy requests
python dev_server.py
```
เปิด http://localhost:8000 (ไม่มี Blob จะเก็บข้อมูลในโฟลเดอร์ชั่วคราวของเครื่อง)

## โครงสร้าง
```
index.html · static/app.js · static/style.css      หน้าเว็บ (Plotly)
api/index.py                                       FastAPI: /api/analysis /api/status /api/oi /api/cme-btc /api/pine
api/_tr/service.py                                 รวม logic เป็น JSON (ยกจาก app.py / pipeline.py)
api/_tr/scoring.py edges.py oi.py indicators.py config.py pine_gen.py deribit_fetch.py   logic เดียวกับเวอร์ชันเครื่อง
api/_tr/data.py                                    ดึงข้อมูล (ไม่ใช้ yfinance)
api/_tr/store.py                                   Vercel Blob / ที่เก็บชั่วคราว
api/_tr/pine/template.pine · api/_tr/seed/         template Pine + ข้อมูล OI ตั้งต้น
```

> เครื่องมือช่วยวิเคราะห์เท่านั้น ไม่ใช่คำแนะนำการลงทุน · น้ำหนักแต่ละแกนยังไม่ผ่านการ backtest
