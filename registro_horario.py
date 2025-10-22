import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkcalendar import DateEntry
import datetime as dt
import platform, os, csv

# =========================
# CONFIG NEGOCIO
# =========================
BASE_START = dt.time(8, 30, 0)
BASE_END   = dt.time(18, 30, 0)
STANDARD_LUNCH = dt.timedelta(hours=1)

SHORT_DAY_SPAN  = dt.timedelta(hours=4, minutes=30)   # Media jornada manual (sin almuerzo)
SATURDAY_SPAN   = dt.timedelta(hours=4, minutes=30)   # Sábado base 4:30 (sin almuerzo)

# CSV
CSV_FILE = "historial.csv"
FIELDNAMES = [
    "Fecha","Entrada","Salida_Almuerzo","Regreso_Almuerzo","Salida",
    "Span_Total","Almuerzo","Efectivas","Extras","Notas"
]
# Encabezados viejos -> nuevos
LEGACY_MAP = {
    "Salida Almuerzo": "Salida_Almuerzo",
    "Regreso Almuerzo": "Regreso_Almuerzo",
    "Total (h)": "Span_Total",
    "Horas Extra (h)": "Extras",
    "Total": "Span_Total",
    "Horas Extra": "Extras",
}

# =========================
# CSV HELPERS (con migración)
# =========================
def ensure_csv_headers():
    if not os.path.isfile(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(FIELDNAMES)

def normalize_row_keys(row: dict) -> dict:
    # Mapea claves legacy y devuelve dict con todos los FIELDNAMES
    norm = {}
    # 1) clona con claves mapeadas
    for k, v in row.items():
        nk = LEGACY_MAP.get(k, k)
        norm[nk] = v
    # 2) completa faltantes
    for k in FIELDNAMES:
        if k not in norm:
            norm[k] = "-"
    return {k: norm[k] for k in FIELDNAMES}

def read_csv_rows():
    if not os.path.isfile(CSV_FILE):
        return []
    rows = []
    with open(CSV_FILE, "r", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(normalize_row_keys(row))
    return rows

def write_csv_rows(dict_rows):
    # Reescribe el CSV con fieldnames oficiales y mapeo a prueba de legacy
    with open(CSV_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for row in dict_rows:
            w.writerow(normalize_row_keys(row))

def append_csv(row_list):
    # row_list es en orden FIELDNAMES
    ensure_csv_headers()
    # Si el archivo tenía headers legacy, esta llamada forzará el formato correcto después
    with open(CSV_FILE, "a", newline="") as f:
        csv.writer(f).writerow(row_list)

# =========================
# UTIL TIEMPO
# =========================
def parse_hms(s: str) -> dt.time:
    return dt.datetime.strptime(s, "%H:%M:%S").time()

def hms_ok(s: str) -> bool:
    try: parse_hms(s); return True
    except: return False

def time_to_dt(fecha: dt.date, t: dt.time) -> dt.datetime:
    return dt.datetime.combine(fecha, t)

def td_to_hhmmss(td: dt.timedelta) -> str:
    total = int(td.total_seconds())
    sign = "-" if total < 0 else ""
    total = abs(total)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{sign}{h:02d}:{m:02d}:{s:02d}"

def week_range(d: dt.date):
    start = d - dt.timedelta(days=d.weekday())
    return start, start + dt.timedelta(days=6)

# =========================
# CÁLCULOS
# =========================
def calcular_jornada(fecha: dt.date,
                     entrada: dt.time,
                     out_lunch: dt.time|None,
                     in_lunch: dt.time|None,
                     salida: dt.time,
                     media_jornada_manual: bool):
    wd = fecha.weekday()  # 0..6 (Dom=6)
    if wd == 6:
        raise ValueError("Domingo es día no laborable.")

    ini = time_to_dt(fecha, entrada)
    fin = time_to_dt(fecha, salida)

    # Sábado: sin almuerzo, base 4:30
    if wd == 5:
        if not (ini < fin):
            raise ValueError("Orden inválido: Entrada debe ser menor que Salida.")
        span_total = fin - ini
        lunch = dt.timedelta(0)
        efectivas = span_total
        extras = max(dt.timedelta(0), efectivas - SATURDAY_SPAN)
        return dict(span_total=span_total, lunch=lunch, efectivas=efectivas,
                    extras=extras, base_desc="Sábado (base 04:30:00)")

    # Media jornada manual: sin almuerzo, base 4:30
    if media_jornada_manual:
        if not (ini < fin):
            raise ValueError("Orden inválido: Entrada debe ser menor que Salida.")
        span_total = fin - ini
        lunch = dt.timedelta(0)
        efectivas = span_total
        extras = max(dt.timedelta(0), efectivas - SHORT_DAY_SPAN)
        return dict(span_total=span_total, lunch=lunch, efectivas=efectivas,
                    extras=extras, base_desc="Jornada reducida (base 04:30:00)")

    # Día normal: con almuerzo real
    if out_lunch is None or in_lunch is None:
        raise ValueError("Debes ingresar salida y regreso de almuerzo (o marcar 'Media jornada').")

    lo  = time_to_dt(fecha, out_lunch)
    li  = time_to_dt(fecha, in_lunch)
    if not (ini < lo <= li <= fin):
        raise ValueError("Orden inválido: Entrada < Salida almuerzo <= Regreso almuerzo <= Salida.")

    span_total = fin - ini
    lunch = li - lo
    efectivas = span_total - lunch

    base_start_dt = time_to_dt(fecha, BASE_START)
    base_end_dt   = time_to_dt(fecha, BASE_END)

    early = base_start_dt - ini          # antes de 08:30 (positivo si llegaste antes)
    late  = fin - base_end_dt            # después de 18:30 (negativo si saliste antes)
    extras_raw = early + late + (STANDARD_LUNCH - lunch)
    extras = extras_raw if extras_raw > dt.timedelta(0) else dt.timedelta(0)

    return dict(span_total=span_total, lunch=lunch, efectivas=efectivas,
                extras=extras,
                base_desc=f"Base 08:30–18:30 + almuerzo estándar {td_to_hhmmss(STANDARD_LUNCH)}")

# =========================
# ESTILO (ttk, morado)
# =========================
def apply_style(root: tk.Tk):
    violet = {
        50:"#F5F3FF",100:"#EDE9FE",200:"#DDD6FE",300:"#C4B5FD",400:"#A78BFA",
        500:"#8B5CF6",600:"#7C3AED",700:"#6D28D9",800:"#5B21B6",900:"#4C1D95",
    }
    C = {
        "bg":"#0B1221","panel":"#101629","text":"#E5E7EB","muted":"#A7B0C0",
        "field":"#0F172A","border":"#1F2937","accent":violet[500],
        "accent_h":violet[400],"sel":violet[600],
    }
    system = platform.system()
    font_family = "Segoe UI" if system == "Windows" else "SF Pro Text"
    base_font = (font_family,11); small_font=(font_family,10); bold_font=(font_family,11,"bold")

    style = ttk.Style(); style.theme_use("clam"); root.configure(bg=C["bg"])
    style.configure("Root.TFrame", background=C["bg"])
    style.configure("Card.TFrame", background=C["panel"])
    style.configure("TLabel", background=C["panel"], foreground=C["text"], font=base_font)
    style.configure("Muted.TLabel", background=C["panel"], foreground=C["muted"], font=small_font)

    style.configure("TButton", background=C["border"], foreground=C["text"], font=base_font, borderwidth=0, padding=8)
    style.map("TButton", background=[("active", C["accent_h"])], relief=[("pressed","sunken")])
    style.configure("Accent.TButton", background=C["accent"], foreground="white", font=bold_font, borderwidth=0, padding=10)
    style.map("Accent.TButton", background=[("active", C["accent_h"])], relief=[("pressed","sunken")])

    style.configure("Custom.TEntry", fieldbackground=C["field"], foreground=C["text"], bordercolor=C["border"],
                    lightcolor=C["accent"], darkcolor=C["border"], insertcolor=C["text"], padding=6)
    style.configure("Custom.DateEntry", fieldbackground=C["field"], foreground=C["text"])
    style.configure("Custom.Treeview", background=C["field"], foreground=C["text"], fieldbackground=C["field"],
                    bordercolor=C["border"], rowheight=26, font=base_font)
    style.configure("Custom.Treeview.Heading", background=C["border"], foreground=C["text"], font=bold_font)
    style.map("Custom.Treeview", background=[("selected", C["sel"])], foreground=[("selected","white")])
    return C

# =========================
# GUI
# =========================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Registro de Horarios Laborales")
        self.resizable(False, False)
        apply_style(self)

        root = ttk.Frame(self, style="Root.TFrame", padding=14); root.grid(sticky="nsew")
        card = ttk.Frame(root, style="Card.TFrame", padding=18); card.grid(row=0, column=0, sticky="nsew")

        ttk.Label(card, text="Fecha (DD/MM/AAAA):").grid(row=0, column=0, padx=(2,8), pady=6, sticky="e")
        self.date_entry = DateEntry(card, date_pattern="dd/MM/yyyy", style="Custom.DateEntry", justify="center")
        self.date_entry.grid(row=0, column=1, padx=2, pady=6, sticky="w")
        self.date_entry.bind("<<DateEntrySelected>>", self.on_date_change)

        self.half_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(card, text="Media jornada (sin almuerzo)", variable=self.half_var,
                        command=self.update_lunch_state).grid(row=1, column=0, columnspan=2, padx=2, pady=(0,8), sticky="w")

        self.entry_var = tk.StringVar(); self.lout_var = tk.StringVar()
        self.lin_var   = tk.StringVar(); self.exit_var = tk.StringVar()

        def row(r, label, var):
            ttk.Label(card, text=label).grid(row=r, column=0, padx=(2,8), pady=6, sticky="e")
            e = ttk.Entry(card, textvariable=var, width=14, style="Custom.TEntry", justify="center")
            e.grid(row=r, column=1, padx=2, pady=6, sticky="w"); return e

        self.e_entry = row(2, "Hora de entrada (HH:MM:SS):", self.entry_var)
        self.e_lout  = row(3, "Salida a almuerzo (HH:MM:SS):", self.lout_var)
        self.e_lin   = row(4, "Regreso de almuerzo (HH:MM:SS):", self.lin_var)
        self.e_exit  = row(5, "Salida del trabajo (HH:MM:SS):", self.exit_var)

        actions = ttk.Frame(card, style="Card.TFrame"); actions.grid(row=6, column=0, columnspan=2, pady=(10,6))
        ttk.Button(actions, text="Calcular y Guardar", style="Accent.TButton", command=self.on_save).pack(side="top", fill="x")
        bar = ttk.Frame(card, style="Card.TFrame"); bar.grid(row=7, column=0, columnspan=2, pady=(6,0))
        ttk.Button(bar, text="Ver historial", command=self.open_history).pack(side="left", padx=5)
        ttk.Button(bar, text="Exportar CSV…", command=self.export_csv).pack(side="left", padx=5)

        card.columnconfigure(0, weight=0); card.columnconfigure(1, weight=1)
        self.on_date_change()

    def on_date_change(self, *_):
        d = self.date_entry.get_date()
        self.half_var.set(d.weekday() == 5)  # sábado -> media jornada
        self.update_lunch_state()

    def update_lunch_state(self):
        if self.half_var.get():
            self.e_lout.configure(state="disabled"); self.e_lin.configure(state="disabled")
            self.lout_var.set(""); self.lin_var.set("")
        else:
            self.e_lout.configure(state="normal"); self.e_lin.configure(state="normal")

    def on_save(self):
        fecha = self.date_entry.get_date()
        s_in, s_lo, s_li, s_out = self.entry_var.get().strip(), self.lout_var.get().strip(), self.lin_var.get().strip(), self.exit_var.get().strip()
        half = self.half_var.get()

        if fecha.weekday() == 6:
            messagebox.showerror("No laborable", "El domingo no se trabaja."); return
        for label, v in [("entrada", s_in), ("salida", s_out)]:
            if not v: messagebox.showerror("Falta dato", f"Ingresa la hora de {label}."); return
            if not hms_ok(v): messagebox.showerror("Formato inválido", f"La hora de {label} debe ser HH:MM:SS."); return
        if not half:
            for label, v in [("salida a almuerzo", s_lo), ("regreso de almuerzo", s_li)]:
                if not v: messagebox.showerror("Falta dato", f"Ingresa la hora de {label}."); return
                if not hms_ok(v): messagebox.showerror("Formato inválido", f"La hora de {label} debe ser HH:MM:SS."); return

        t_in  = parse_hms(s_in)
        t_out = parse_hms(s_out)
        t_lo  = parse_hms(s_lo) if (s_lo and not half) else None
        t_li  = parse_hms(s_li) if (s_li and not half) else None

        try:
            res = calcular_jornada(fecha, t_in, t_lo, t_li, t_out, half)
        except ValueError as e:
            messagebox.showerror("Error", str(e)); return

        txt = (
            f"Fecha: {fecha.strftime('%d/%m/%Y')}\n"
            f"Regla: {res['base_desc']}\n\n"
            f"Span total: {td_to_hhmmss(res['span_total'])}\n"
            f"Almuerzo: {td_to_hhmmss(res['lunch'])}\n"
            f"Efectivas: {td_to_hhmmss(res['efectivas'])}\n"
            f"Horas extra: {td_to_hhmmss(res['extras'])}\n\n"
            "¿Desea guardar este registro?"
        )
        if not messagebox.askyesno("Resumen de la jornada", txt):
            return

        # No duplicar fecha
        ensure_csv_headers()
        rows = read_csv_rows()
        fstr = fecha.strftime("%d/%m/%Y")
        existe = any(r["Fecha"] == fstr for r in rows)
        if existe:
            if not messagebox.askyesno("Fecha ya registrada", f"Ya existe un registro para {fstr}.\n¿Deseas reemplazarlo?"):
                return
            new_rows = [r for r in rows if r["Fecha"] != fstr]
            new_rows.append({
                "Fecha": fstr,
                "Entrada": s_in,
                "Salida_Almuerzo": (s_lo if s_lo else "-"),
                "Regreso_Almuerzo": (s_li if s_li else "-"),
                "Salida": s_out,
                "Span_Total": td_to_hhmmss(res["span_total"]),
                "Almuerzo": td_to_hhmmss(res["lunch"]),
                "Efectivas": td_to_hhmmss(res["efectivas"]),
                "Extras": td_to_hhmmss(res["extras"]),
                "Notas": res["base_desc"]
            })
            write_csv_rows(new_rows)  # <-- filtra y normaliza
        else:
            append_csv([
                fstr, s_in, (s_lo if s_lo else "-"), (s_li if s_li else "-"), s_out,
                td_to_hhmmss(res["span_total"]),
                td_to_hhmmss(res["lunch"]),
                td_to_hhmmss(res["efectivas"]),
                td_to_hhmmss(res["extras"]),
                res["base_desc"]
            ])
        messagebox.showinfo("OK", f"Guardado en {CSV_FILE}.")
        self.entry_var.set(""); self.lout_var.set(""); self.lin_var.set(""); self.exit_var.set("")

    def open_history(self):
        HistoryWindow(self)

    def export_csv(self):
        ensure_csv_headers()
        dest = filedialog.asksaveasfilename(
            title="Exportar CSV",
            defaultextension=".csv",
            initialfile="historial_export.csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not dest: return
        try:
            with open(CSV_FILE, "rb") as src, open(dest, "wb") as dst:
                dst.write(src.read())
            messagebox.showinfo("Exportado", f"Se guardó una copia en:\n{dest}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

# =========================
# HISTORIAL
# =========================
class HistoryWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Historial")
        self.geometry("940x480")
        apply_style(self)

        wrap = ttk.Frame(self, style="Root.TFrame", padding=14); wrap.pack(fill="both", expand=True)
        card = ttk.Frame(wrap, style="Card.TFrame", padding=14); card.pack(fill="both", expand=True)

        top = ttk.Frame(card, style="Card.TFrame"); top.pack(fill="x", pady=(0,8))
        ttk.Label(top, text="Filtrar por mes (MM/AAAA):", style="Muted.TLabel").pack(side="left", padx=(2,6))
        self.month_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.month_var, width=10, style="Custom.TEntry", justify="center").pack(side="left")
        ttk.Button(top, text="Aplicar", command=self.refresh).pack(side="left", padx=6)
        ttk.Button(top, text="Limpiar", command=self.clear_filter).pack(side="left")

        cols = FIELDNAMES
        self.tree = ttk.Treeview(card, columns=cols, show="headings", style="Custom.Treeview")
        for c in cols:
            self.tree.heading(c, text=c, anchor="center")
            self.tree.column(c, width=120 if c!="Notas" else 240, anchor="center")
        self.tree.pack(expand=True, fill="both")

        bot = ttk.Frame(card, style="Card.TFrame"); bot.pack(fill="x", pady=(8,0))
        self.lbl_week = ttk.Label(bot, text="Total extras (semana actual): --:--:--", style="Muted.TLabel")
        self.lbl_month = ttk.Label(bot, text="Total extras (mes actual): --:--:--", style="Muted.TLabel")
        self.lbl_week.pack(anchor="w"); self.lbl_month.pack(anchor="w")

        self.refresh()

    def clear_filter(self):
        self.month_var.set(""); self.refresh()

    def refresh(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        rows = read_csv_rows()
        mfilter = self.month_var.get().strip()
        filtered = []
        for r in rows:
            try:
                d = dt.datetime.strptime(r["Fecha"], "%d/%m/%Y").date()
            except:
                continue
            if mfilter:
                try:
                    mm, yyyy = mfilter.split("/")
                    if f"{d.month:02d}/{d.year}" != f"{int(mm):02d}/{int(yyyy)}":
                        continue
                except:
                    pass
            filtered.append((d, r))
        filtered.sort(key=lambda x: x[0])
        for _, r in filtered:
            # get() evita KeyError si alguna fila quedó con claves faltantes
            self.tree.insert("", "end", values=[r.get(c, "-") for c in self.tree["columns"]])
        self.update_totals(rows)

    def update_totals(self, rows):
        today = dt.date.today()
        w0, w1 = week_range(today)
        m0 = today.replace(day=1)
        if today.month == 12:
            m1 = today.replace(year=today.year+1, month=1, day=1) - dt.timedelta(days=1)
        else:
            m1 = today.replace(month=today.month+1, day=1) - dt.timedelta(days=1)

        def sum_extras(a, b):
            tot = dt.timedelta(0)
            for r in rows:
                try:
                    d = dt.datetime.strptime(r["Fecha"], "%d/%m/%Y").date()
                    if not (a <= d <= b): continue
                    h,m,s = map(int, r["Extras"].split(":"))
                    tot += dt.timedelta(hours=h, minutes=m, seconds=s)
                except: pass
            return tot

        self.lbl_week.config(text=f"Total extras (semana actual): {td_to_hhmmss(sum_extras(w0, w1))}")
        self.lbl_month.config(text=f"Total extras (mes actual): {td_to_hhmmss(sum_extras(m0, m1))}")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    ensure_csv_headers()
    # Si el CSV era legacy, una pasada de lectura+escritura normaliza archivos antiguos:
    legacy_rows = read_csv_rows()
    if legacy_rows:
        write_csv_rows(legacy_rows)
    App().mainloop()
