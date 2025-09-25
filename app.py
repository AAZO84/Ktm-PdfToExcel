import io
import re
from datetime import datetime
from typing import Optional

import pdfplumber
import pandas as pd
from fastapi import FastAPI, File, UploadFile, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi import FastAPI
app = FastAPI()


#app = FastAPI(title="PDF a Excel (Facturas)", version="1.0.0")

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def _to_float(num_str: str):
    if not num_str:
        return None
    try:
        return float(num_str.replace(",", ""))
    except Exception:
        return None

def parse_pdf_factura_bytes(pdf_bytes: bytes):
    items, delayed = [], []

    rx_item = re.compile(
        r"^\s*(?P<pos>\d{2,4})\s+(?P<art>[A-Z0-9]+)\s+(?P<desc>.+?)\s+(?P<cant>\d+)\s+(?P<me>[A-Z]{2,3})\s+(?P<precio>[\d,]+\.\d{2})$",
        re.IGNORECASE
    )
    rx_pedido_after  = re.compile(r"\bPedido\s+(?P<num>\d{5,})\b", re.IGNORECASE)
    rx_pedido_before = re.compile(r"\b(?P<num>\d{5,})\s*Pedido\b", re.IGNORECASE)

    rx_pedido_retrasado_header = re.compile(r"Pedido\s+retrasado", re.IGNORECASE)
    rx_pedido_retrasado_end    = re.compile(r"Posiciones\s+en\s+total", re.IGNORECASE)
    rx_delayed_line = re.compile(
        r"^\s*(?P<pos>\d{6})\s+(?P<art>[A-Z0-9]+)\s+(?P<cant>\d+)\s+(?P<desc>.+)$",
        re.IGNORECASE
    )

    last_item_index = None
    in_delayed = False
    current_pedido_forward: Optional[str] = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [l for l in text.splitlines() if _clean(l)]
            for raw in lines:
                line = _clean(raw)

                if rx_pedido_retrasado_header.search(line):
                    in_delayed = True
                    continue
                if in_delayed and rx_pedido_retrasado_end.search(line):
                    in_delayed = False
                    continue
                if in_delayed:
                    mdel = rx_delayed_line.match(line)
                    if mdel:
                        delayed.append({
                            "Pos": mdel.group("pos"),
                            "Número de artículo": mdel.group("art"),
                            "Cantidad abierta": int(mdel.group("cant")),
                            "Denominación": _clean(mdel.group("desc")),
                        })
                    continue

                m_item = rx_item.match(line)
                if m_item:
                    items.append({
                        "Pos": m_item.group("pos"),
                        "Número de artículo": m_item.group("art"),
                        "Denominación": _clean(m_item.group("desc")),
                        "Cantidad": int(m_item.group("cant")),
                        "ME": m_item.group("me"),
                        "Precio Neto (MXN)": _to_float(m_item.group("precio")),
                        "Pedido": current_pedido_forward
                    })
                    last_item_index = len(items) - 1
                    current_pedido_forward = None
                    continue

                m_after = rx_pedido_after.search(line)
                if m_after:
                    num = m_after.group("num")
                    if last_item_index is not None and not items[last_item_index].get("Pedido"):
                        items[last_item_index]["Pedido"] = num
                    else:
                        current_pedido_forward = num
                    continue

                m_before = rx_pedido_before.search(line)
                if m_before:
                    current_pedido_forward = m_before.group("num")
                    if last_item_index is not None and not items[last_item_index].get("Pedido"):
                        items[last_item_index]["Pedido"] = current_pedido_forward
                    continue

    return items, delayed

def exportar_a_excel_bytes(items, delayed, filename_hint="factura_convertida"):
    df_items = pd.DataFrame(items, columns=[
        "Pos", "Número de artículo", "Denominación", "Cantidad", "ME", "Precio Neto (MXN)", "Pedido"
    ])
    df_delayed = pd.DataFrame(delayed, columns=[
        "Pos", "Número de artículo", "Cantidad abierta", "Denominación"
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_items.to_excel(writer, sheet_name="Artículos facturados", index=False)
        df_delayed.to_excel(writer, sheet_name="Pedidos retrasados", index=False)
    output.seek(0)
    return output.read()

@app.get("/", response_class=HTMLResponse)
def form():
    return """
    <html>
      <body>
        <h2>Convertir factura PDF a Excel</h2>
        <form action="/convert" method="post" enctype="multipart/form-data">
          <input type="file" name="file" accept="application/pdf" required />
          <button type="submit">Convertir</button>
        </form>
      </body>
    </html>
    """

@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        return Response(content="Sube un PDF válido.", status_code=400)

    pdf_bytes = await file.read()
    items, delayed = parse_pdf_factura_bytes(pdf_bytes)
    xlsx_bytes = exportar_a_excel_bytes(items, delayed)

    base = (file.filename or "factura").rsplit(".", 1)[0]
    out_name = re.sub(r"[^A-Za-z0-9_-]+", "_", base)[:60] + "_convertida.xlsx"

    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'}
    )

@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}
