"""
Motozuni — Generador de Dashboard
Lee el Consolidado de Google Sheets y genera index.html
"""

import json
import os
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID   = "11h-2thjqf_Mfg1T0hQHLXpiSqIWVIhkb32K_8EuZr94"
SHEET_NAME = "Consolidado"
SCOPES     = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

ITEMS_FULL = [
    "Control de billetes contra caja",
    "Cobros registrados en Presea",
    "Gastos menores pasados en Presea y planilla Drive",
    "Control sistema vs inventario físico (Marca/Modelo)",
    "Control sistema vs inventario físico",
    "Carpetas físicas (remitos, recepciones ordenadas)",
    "Conteo de chapas",
    "Calculadores y recalculadores",
    "Documentación respaldatoria (créditos, transferencias)",
    "Asientos del legajo en sistema",
    "Señas de motos",
    "Estado de prendas (no transcripta, no liquidada)",
]

SECTORES = {
    "Caja":             ["Control de billetes contra caja","Cobros registrados en Presea","Gastos menores pasados en Presea y planilla Drive"],
    "Motos":            ["Control sistema vs inventario físico (Marca/Modelo)"],
    "Accesorios":       ["Control sistema vs inventario físico"],
    "Orden del Sector": ["Carpetas físicas (remitos, recepciones ordenadas)","Conteo de chapas"],
    "Legajo Clientes":  ["Calculadores y recalculadores","Documentación respaldatoria (créditos, transferencias)","Asientos del legajo en sistema","Señas de motos"],
    "Prendas":          ["Estado de prendas (no transcripta, no liquidada)"],
}

PUNTAJES = {
    "Control de billetes contra caja": 3,
    "Cobros registrados en Presea": 2,
    "Gastos menores pasados en Presea y planilla Drive": 2,
    "Control sistema vs inventario físico (Marca/Modelo)": 5,
    "Control sistema vs inventario físico": 2,
    "Carpetas físicas (remitos, recepciones ordenadas)": 1,
    "Conteo de chapas": 1,
    "Calculadores y recalculadores": 2,
    "Documentación respaldatoria (créditos, transferencias)": 2,
    "Asientos del legajo en sistema": 2,
    "Señas de motos": 2,
    "Estado de prendas (no transcripta, no liquidada)": 2,
}


def get_sheet_data():
    """Lee el Consolidado desde Google Sheets."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS no está configurado")

    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    sheet   = service.spreadsheets()
    result  = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!A1:ZZ"
    ).execute()
    return result.get("values", [])


def parse_data(rows):
    """Convierte las filas del Consolidado en objetos de auditoría."""
    if not rows or len(rows) < 2:
        return []

    headers = [h.upper().strip() for h in rows[0]]

    def col(row, name):
        try:
            idx = headers.index(name)
            return row[idx] if idx < len(row) else ""
        except ValueError:
            return ""

    # Detectar columnas de ítems y observaciones
    item_cols = {}
    obs_cols  = {}
    for item in ITEMS_FULL:
        item_upper = item.upper()
        if item_upper in headers:
            item_cols[item] = headers.index(item_upper)
        obs_key = f"OBS: {item[:30].upper()}"
        for i, h in enumerate(headers):
            if h.startswith("OBS:") and item[:20].upper() in h:
                obs_cols[item] = i
                break

    auditorias = []
    for row in rows[1:]:
        if not row or not row[0]:
            continue

        sucursal   = col(row, "SUCURSAL")
        supervisor = col(row, "SUPERVISOR")
        encargado  = col(row, "ENCARGADO")
        general    = col(row, "GENERAL")
        asistentes = col(row, "ASISTENTES")
        fecha_raw  = col(row, "FECHA")
        score_raw  = col(row, "SCORE")
        pts_raw    = col(row, "PUNTOS OBTENIDOS")
        total_raw  = col(row, "TOTAL POSIBLE")
        stock      = col(row, "STOCK PRESEA")
        fuera      = col(row, "MOTOS FUERA STOCK")
        sin_fisico = col(row, "MOTOS SIN FISICO")

        # Normalizar fecha
        fecha = str(fecha_raw).split(" ")[0] if fecha_raw else ""
        if "/" in fecha:
            parts = fecha.split("/")
            if len(parts) == 3:
                fecha = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"

        # Ítems y observaciones
        items = []
        obs   = []
        for item in ITEMS_FULL:
            v = ""
            if item in item_cols:
                idx = item_cols[item]
                v = row[idx].strip().upper() if idx < len(row) else ""
            items.append(v)
            o = ""
            if item in obs_cols:
                idx = obs_cols[item]
                o = row[idx].strip() if idx < len(row) else ""
            obs.append(o)

        def safe_num(v):
            try:
                return float(v)
            except:
                return None

        auditorias.append({
            "sucursal":   sucursal,
            "supervisor": supervisor,
            "encargado":  encargado,
            "general":    general,
            "asistentes": asistentes,
            "fecha":      fecha,
            "score":      safe_num(score_raw) or 0,
            "pts":        int(safe_num(pts_raw) or 0),
            "total":      int(safe_num(total_raw) or 0),
            "items":      items,
            "obs":        obs,
            "stockPresea":     safe_num(stock),
            "motosFuera":      safe_num(fuera),
            "motosSinFisico":  safe_num(sin_fisico),
        })

    return auditorias


def to_js(obj):
    """Convierte un objeto Python a JSON seguro para JS."""
    return json.dumps(obj, ensure_ascii=False)


def generate_html(auditorias):
    """Genera el HTML completo con los datos embedidos."""
    data_js = to_js(auditorias)

    # Leer el template HTML v6 y reemplazar el bloque DATA
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    if os.path.exists(template_path):
        html = open(template_path, encoding="utf-8").read()
        # Reemplazar el bloque DATA entre los marcadores.
        # IMPORTANTE: el reemplazo se pasa como función (lambda), no como string.
        # Si se pasa como string, re.sub reinterpreta las secuencias \n, \\, etc.
        # que json.dumps ya había escapado correctamente dentro de data_js,
        # rompiendo el JSON cuando una observación tiene saltos de línea reales
        # (ej: textos largos escritos en varios renglones en el Sheet).
        html = re.sub(
            r'// ===DATA_START===.*?// ===DATA_END===',
            lambda m: f'// ===DATA_START===\nconst DATA = {data_js};\n// ===DATA_END===',
            html,
            flags=re.DOTALL
        )
    else:
        raise FileNotFoundError("template.html no encontrado")

    return html


def main():
    print("Leyendo datos de Google Sheets...")
    rows = get_sheet_data()
    print(f"  {len(rows)-1} filas encontradas")

    auditorias = parse_data(rows)
    print(f"  {len(auditorias)} auditorías procesadas")

    html = generate_html(auditorias)

    out_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  index.html generado ({len(html)} chars)")


if __name__ == "__main__":
    main()
