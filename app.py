#!/usr/bin/env python3
"""
Antimicrobial / Antifungal Activity Analyzer - FINAL
- Comparison logic switched to PGI% as primary metric (so larger measured colony => more resistant fungus;
  PGI% measures inhibition: higher PGI% => more effective bacteria).
- Data Entry: Control (KR) field moved after Zone input and before Concentration input.
- Plots & Analysis reactivated to use PGI% where possible.
- Statistics tab displays the PGI equation.
- Keeps existing features: tabs, CSV import/load/save, edit/delete/undo, images, PDF exports.
"""

import os
import io
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from datetime import datetime

# CSV columns include Control_mm
DATA_CSV = "measurements.csv"
DATA_COLUMNS = ["Isolate", "Fungus", "Measurement_mm", "Concentration_CFU_per_ml", "Control_mm", "ImagePath", "Notes"]

# --------------- Data Model ---------------
class DataModel:
    def __init__(self):
        if os.path.exists(DATA_CSV):
            try:
                self.df = pd.read_csv(DATA_CSV)
                for c in DATA_COLUMNS:
                    if c not in self.df.columns:
                        self.df[c] = np.nan if c in ("Measurement_mm","Concentration_CFU_per_ml","Control_mm") else ""
                self.df = self.df.reindex(columns=DATA_COLUMNS)
            except Exception:
                self.df = pd.DataFrame(columns=DATA_COLUMNS)
        else:
            self.df = pd.DataFrame(columns=DATA_COLUMNS)

    def add(self, isolate, fungus, mm, conc=None, control=None, imgpath="", notes=""):
        row = {
            "Isolate": isolate,
            "Fungus": fungus,
            "Measurement_mm": float(mm),
            "Concentration_CFU_per_ml": float(conc) if (conc is not None and conc != "") else np.nan,
            "Control_mm": float(control) if (control is not None and control != "") else np.nan,
            "ImagePath": imgpath,
            "Notes": notes
        }
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)

    def update(self, index, isolate, fungus, mm, conc, control, imgpath, notes):
        if index < 0 or index >= len(self.df):
            return
        self.df.at[index, "Isolate"] = isolate
        self.df.at[index, "Fungus"] = fungus
        self.df.at[index, "Measurement_mm"] = float(mm)
        self.df.at[index, "Concentration_CFU_per_ml"] = float(conc) if (conc is not None and conc != "") else np.nan
        self.df.at[index, "Control_mm"] = float(control) if (control is not None and control != "") else np.nan
        self.df.at[index, "ImagePath"] = imgpath
        self.df.at[index, "Notes"] = notes

    def delete(self, index):
        if index < 0 or index >= len(self.df):
            return
        self.df = self.df.drop(index).reset_index(drop=True)

    def save(self, path=DATA_CSV):
        self.df.to_csv(path, index=False)

    def load(self, path):
        self.df = pd.read_csv(path)
        for c in DATA_COLUMNS:
            if c not in self.df.columns:
                self.df[c] = np.nan if c in ("Measurement_mm","Concentration_CFU_per_ml","Control_mm") else ""
        self.df = self.df.reindex(columns=DATA_COLUMNS)

    def isolates(self):
        return sorted(self.df["Isolate"].dropna().unique())

    def fungi(self):
        return sorted(self.df["Fungus"].dropna().unique())

# --------------- PGI Utilities ---------------
def compute_pgi_for_row(row):
    try:
        R1 = float(row["Measurement_mm"])
        KR = float(row.get("Control_mm", np.nan))
        if np.isnan(KR) or KR <= 0:
            return np.nan
        return (KR - R1) / KR * 100.0
    except Exception:
        return np.nan

def compute_pgi_df(df):
    df2 = df.copy()
    df2["PGI_pct"] = df2.apply(compute_pgi_for_row, axis=1)
    return df2

# --------------- Main App ---------------
class AnalyzerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Antimicrobial / Antifungal Activity Analyzer - FINAL")
        self.geometry("1280x780")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.model = DataModel()
        self.current_image = ""
        self.selected_index = None
        self._last_deleted = None

        # last PGI results / figures for PDF export
        self._last_pgi_df = None
        self._last_pgi_fig = None
        self._last_pgi_summary = ""

        self.create_tabs()
        self.refresh_table()
        self.refresh_dropdowns()

    # -------- Tabs & UI build --------
    def create_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # Data Entry
        self.tab_entry = ttk.Frame(nb); nb.add(self.tab_entry, text="Data Entry"); self.build_entry_tab(self.tab_entry)

        # Data Table
        self.tab_table = ttk.Frame(nb); nb.add(self.tab_table, text="Data Table"); self.build_table_tab(self.tab_table)

        # Plots & Analysis
        self.tab_plots = ttk.Frame(nb); nb.add(self.tab_plots, text="Plots & Analysis"); self.build_plots_tab(self.tab_plots)

        # Statistics (PGI)
        self.tab_stats = ttk.Frame(nb); nb.add(self.tab_stats, text="Statistics (PGI)"); self.build_stats_tab(self.tab_stats)

        # Reports
        self.tab_reports = ttk.Frame(nb); nb.add(self.tab_reports, text="Reports"); self.build_reports_tab(self.tab_reports)

    # -------- Data Entry tab (Control field moved) --------
    def build_entry_tab(self, parent):
        panel = ttk.Frame(parent, padding=8); panel.pack(fill="x", padx=8, pady=6)

        ttk.Label(panel, text="Isolate:").grid(row=0, column=0, sticky="w")
        self.entry_isolate = ttk.Entry(panel, width=22); self.entry_isolate.grid(row=0, column=1, padx=6)

        ttk.Label(panel, text="Fungus:").grid(row=0, column=2, sticky="w")
        self.entry_fungus = ttk.Entry(panel, width=22); self.entry_fungus.grid(row=0, column=3, padx=6)

        ttk.Label(panel, text="Zone (mm):").grid(row=1, column=0, sticky="w")
        self.entry_zone = ttk.Entry(panel, width=12); self.entry_zone.grid(row=1, column=1, padx=6)

        # Control moved here (after Zone and before Concentration)
        ttk.Label(panel, text="Control (KR) (mm):").grid(row=1, column=2, sticky="w")
        self.entry_control = ttk.Entry(panel, width=12); self.entry_control.grid(row=1, column=3, padx=6)

        ttk.Label(panel, text="Concentration (CFU/ml):").grid(row=2, column=0, sticky="w")
        self.entry_conc = ttk.Entry(panel, width=16); self.entry_conc.grid(row=2, column=1, padx=6)

        ttk.Button(panel, text="Upload image", command=self.upload_image).grid(row=0, column=4, rowspan=3, padx=8)
        self.lbl_image = ttk.Label(panel, text="No image"); self.lbl_image.grid(row=0, column=5, rowspan=3, padx=6)

        # actions
        actions = ttk.Frame(panel); actions.grid(row=3, column=0, columnspan=6, pady=(8,0))
        ttk.Button(actions, text="Add / Save entry", command=self.save_entry).pack(side="left", padx=4)
        ttk.Button(actions, text="Clear fields", command=self.clear_fields).pack(side="left", padx=4)
        ttk.Button(actions, text="Import CSV (append)", command=self.import_csv_append).pack(side="left", padx=4)
        ttk.Button(actions, text="Load CSV (replace)", command=self.load_csv).pack(side="left", padx=4)
        ttk.Button(actions, text="Save CSV", command=self.save_csv).pack(side="left", padx=4)

    # -------- Data Table tab --------
    def build_table_tab(self, parent):
        frame = ttk.Frame(parent); frame.pack(fill="both", expand=True, padx=8, pady=8)
        cols = ("Isolate","Fungus","Measurement_mm","Control_mm","Concentration","Image","Notes")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse", height=18)
        for c in cols:
            self.tree.heading(c, text=c); self.tree.column(c, width=140, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        ops = ttk.Frame(frame); ops.pack(fill="x", pady=(6,0))
        ttk.Button(ops, text="Edit selected", command=self.edit_selected).pack(side="left")
        ttk.Button(ops, text="Delete selected", command=self.delete_selected).pack(side="left", padx=6)
        ttk.Button(ops, text="Undo last delete", command=self.undo_delete).pack(side="left", padx=6)
        ttk.Button(ops, text="Show image preview", command=self.show_image_preview).pack(side="right")
        ttk.Button(ops, text="Export CSV", command=self.save_csv).pack(side="right", padx=(0,6))

    # -------- Plots & Analysis tab (uses PGI when available) --------
    def build_plots_tab(self, parent):
        top = ttk.Frame(parent); top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="Plot settings:").pack(anchor="w")
        controls = ttk.Frame(top); controls.pack(fill="x", padx=4)

        ttk.Label(controls, text="Plot type:").pack(side="left")
        self.plot_type_var = tk.StringVar(value="bar")
        ttk.Combobox(controls, textvariable=self.plot_type_var, values=["bar","box","scatter_annot","hist"], width=12).pack(side="left", padx=6)

        ttk.Label(controls, text="Comparison metric:").pack(side="left", padx=(8,0))
        # By default use PGI (preferred). If user wants raw measurement, they can choose 'Measurement_mm'
        self.metric_var = tk.StringVar(value="PGI_pct")
        ttk.Combobox(controls, textvariable=self.metric_var, values=["PGI_pct","Measurement_mm"], width=16).pack(side="left", padx=6)

        ttk.Label(controls, text="Compare mode:").pack(side="left", padx=(8,0))
        self.compare_mode_var = tk.StringVar(value="ByFungus")
        cm = ttk.Combobox(controls, textvariable=self.compare_mode_var, values=["ByFungus","ByIsolate"], width=12); cm.pack(side="left", padx=6)
        cm.bind("<<ComboboxSelected>>", lambda e: self.refresh_dropdowns())

        ttk.Label(controls, text="Select target:").pack(side="left", padx=(8,0))
        self.target_var = tk.StringVar()
        self.target_combo = ttk.Combobox(controls, textvariable=self.target_var, values=[], width=18); self.target_combo.pack(side="left", padx=6)
        self.target_combo.bind("<<ComboboxSelected>>", lambda e: self.generate_plot())

        ttk.Button(controls, text="Generate plot", command=self.generate_plot).pack(side="left", padx=8)
        ttk.Button(controls, text="Export plot PNG", command=self.export_plot_png).pack(side="left")

        body = ttk.Frame(parent); body.pack(fill="both", expand=True, padx=6, pady=(6,8))
        left = ttk.Frame(body); left.pack(side="left", fill="both", expand=True)
        self.fig = Figure(figsize=(6,4), dpi=100); self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=left); self.canvas.get_tk_widget().pack(fill="both", expand=True)

        right = ttk.Frame(body, width=360); right.pack(side="right", fill="y")
        ttk.Label(right, text="Selected record / comparison details:").pack(anchor="nw")
        self.txt_details = tk.Text(right, width=44, height=20); self.txt_details.pack(fill="both", expand=True)

    # -------- Statistics (PGI) tab (equation displayed) --------
    def build_stats_tab(self, parent):
        top = ttk.Frame(parent); top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="PGI (Percentage Growth Inhibition) statistics", font=("Segoe UI",11,"bold")).pack(anchor="w", pady=(0,6))

        # Display the PGI formula (cooler)
        eq_frame = ttk.Frame(top); eq_frame.pack(fill="x", padx=2, pady=(0,6))
        eq_text = "PGI% = (KR - R1) / KR × 100\nwhere KR = Control_mm (control colony diameter, mm)\n      R1 = Measurement_mm (treated colony diameter, mm)"
        ttk.Label(eq_frame, text=eq_text, justify="left", font=("Segoe UI",10,"italic")).pack(anchor="w")

        ctrl = ttk.Frame(top); ctrl.pack(fill="x")
        ttk.Label(ctrl, text="Group by:").pack(side="left")
        self.pgi_group_var = tk.StringVar(value="ByFungus")
        grp = ttk.Combobox(ctrl, textvariable=self.pgi_group_var, values=["ByFungus","ByIsolate"], width=12); grp.pack(side="left", padx=6)
        ttk.Label(ctrl, text="Aggregation:").pack(side="left", padx=(8,0))
        self.pgi_agg_var = tk.StringVar(value="Mean±Std")
        ttk.Combobox(ctrl, textvariable=self.pgi_agg_var, values=["Mean±Std","Boxplot / All replicates"], width=20).pack(side="left", padx=6)

        ttk.Label(ctrl, text="Plot type:").pack(side="left", padx=(8,0))
        self.pgi_plot_var = tk.StringVar(value="grouped_bar")
        ttk.Combobox(ctrl, textvariable=self.pgi_plot_var, values=["grouped_bar","boxplot","scatter_annot"], width=14).pack(side="left", padx=6)

        ttk.Button(ctrl, text="Generate PGI plot", command=self.generate_pgi_plot).pack(side="left", padx=8)
        ttk.Button(ctrl, text="Export PGI CSV", command=self.export_pgi_csv).pack(side="left", padx=4)
        ttk.Button(ctrl, text="Generate PGI PDF", command=self.export_pgi_pdf).pack(side="left", padx=4)

        area = ttk.Frame(parent); area.pack(fill="both", expand=True, padx=6, pady=(6,8))
        left = ttk.Frame(area); left.pack(side="left", fill="both", expand=True)
        self.pgi_fig = Figure(figsize=(6,4), dpi=100); self.pgi_ax = self.pgi_fig.add_subplot(111)
        self.pgi_canvas = FigureCanvasTkAgg(self.pgi_fig, master=left); self.pgi_canvas.get_tk_widget().pack(fill="both", expand=True)

        right = ttk.Frame(area, width=380); right.pack(side="right", fill="y")
        ttk.Label(right, text="PGI table & notes:").pack(anchor="w")
        cols = ("Index","Isolate","Fungus","Measurement_mm","Control_mm","PGI_pct")
        self.pgi_tree = ttk.Treeview(right, columns=cols, show="headings", height=12)
        for c in cols:
            self.pgi_tree.heading(c, text=c); self.pgi_tree.column(c, width=110, anchor="center")
        self.pgi_tree.pack(fill="y", expand=False, pady=(4,6))

        self.pgi_notes = tk.Text(right, width=42, height=12)
        self.pgi_notes.pack(fill="both", expand=True)

    # -------- Reports tab --------
    def build_reports_tab(self, parent):
        panel = ttk.Frame(parent, padding=8); panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Reports", font=("Segoe UI",11,"bold")).pack(anchor="w")
        ttk.Button(panel, text="Generate full PDF report (dataset + pivot + plot)", command=self.export_pdf).pack(anchor="w", pady=(8,0))
        ttk.Button(panel, text="Export dataset CSV", command=self.save_csv).pack(anchor="w", pady=(8,0))

    # -------- Data helpers --------
    def refresh_table(self):
        try:
            self.tree.delete(*self.tree.get_children())
        except Exception:
            pass
        for i, row in self.model.df.iterrows():
            meas = "" if pd.isna(row.get("Measurement_mm", np.nan)) else f"{row['Measurement_mm']:.2f}"
            ctrl = "" if pd.isna(row.get("Control_mm", np.nan)) else f"{row['Control_mm']:.2f}"
            conc = "" if pd.isna(row.get("Concentration_CFU_per_ml", np.nan)) else f"{int(row['Concentration_CFU_per_ml']):,}"
            vals = (row["Isolate"], row["Fungus"], meas, ctrl, conc, os.path.basename(str(row.get("ImagePath",""))), row.get("Notes",""))
            self.tree.insert("", "end", iid=str(i), values=vals)

    def refresh_dropdowns(self):
        try:
            if self.compare_mode_var.get() == "ByFungus":
                self.target_combo['values'] = self.model.fungi()
            else:
                self.target_combo['values'] = self.model.isolates()
        except Exception:
            pass

    def clear_fields(self):
        self.entry_isolate.delete(0, tk.END); self.entry_fungus.delete(0, tk.END)
        self.entry_zone.delete(0, tk.END); self.entry_control.delete(0, tk.END)
        self.entry_conc.delete(0, tk.END); self.lbl_image.config(text="No image")
        self.current_image = ""; self.selected_index = None; self.txt_details.delete('1.0', tk.END)

    def upload_image(self):
        files = filedialog.askopenfilenames(title="Select plate image(s)", filetypes=[("Images","*.png;*.jpg;*.jpeg;*.tif;*.bmp")])
        if not files:
            return
        self.current_image = files[0]; self.lbl_image.config(text=os.path.basename(self.current_image))

    def save_entry(self):
        iso = self.entry_isolate.get().strip(); fungus = self.entry_fungus.get().strip(); zone = self.entry_zone.get().strip()
        control = self.entry_control.get().strip(); conc = self.entry_conc.get().strip()
        if not iso or not fungus or not zone:
            messagebox.showwarning("Missing", "Please provide isolate, fungus and measurement (mm)."); return
        try:
            mm = float(zone)
        except ValueError:
            messagebox.showerror("Invalid", "Measurement must be numeric."); return
        if control != "":
            try:
                ctrl_val = float(control)
            except ValueError:
                messagebox.showerror("Invalid", "Control must be numeric."); return
        else:
            ctrl_val = np.nan
        if conc != "":
            try:
                conc_val = float(conc)
            except ValueError:
                messagebox.showerror("Invalid", "Concentration must be numeric."); return
        else:
            conc_val = np.nan

        if self.selected_index is None:
            self.model.add(iso, fungus, mm, conc_val, ctrl_val, self.current_image, "")
        else:
            idx = int(self.selected_index); self.model.update(idx, iso, fungus, mm, conc_val, ctrl_val, self.current_image, "")
        self.current_image = ""; self.lbl_image.config(text="No image")
        self.refresh_table(); self.refresh_dropdowns(); self.clear_fields()

    def import_csv_append(self):
        path = filedialog.askopenfilename(title="Import CSV (append)", filetypes=[("CSV","*.csv")])
        if not path:
            return
        try:
            df = pd.read_csv(path)
            for c in DATA_COLUMNS:
                if c not in df.columns:
                    df[c] = np.nan if c in ("Measurement_mm","Concentration_CFU_per_ml","Control_mm") else ""
            df = df.reindex(columns=DATA_COLUMNS)
            self.model.df = pd.concat([self.model.df, df], ignore_index=True)
            self.refresh_table(); self.refresh_dropdowns()
            messagebox.showinfo("Imported", f"Appended {len(df)} records from {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Import error", str(e))

    def save_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if not path:
            return
        try:
            self.model.save(path); messagebox.showinfo("Saved", f"Saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def load_csv(self):
        path = filedialog.askopenfilename(title="Open CSV (replace)", filetypes=[("CSV","*.csv")])
        if not path:
            return
        try:
            self.model.load(path); self.refresh_table(); self.refresh_dropdowns(); messagebox.showinfo("Loaded", f"Loaded {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # -------- Table interactions --------
    def on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0]); self.selected_index = idx
        row = self.model.df.loc[idx]
        conc_display = "N/A" if pd.isna(row.get("Concentration_CFU_per_ml", np.nan)) else f"{int(row['Concentration_CFU_per_ml']):,}"
        ctrl_display = "N/A" if pd.isna(row.get("Control_mm", np.nan)) else f"{row['Control_mm']:.2f}"
        txt = (f"Index: {idx}\nIsolate: {row['Isolate']}\nFungus: {row['Fungus']}\n"
               f"Zone (mm): {row['Measurement_mm']:.2f}\nControl (KR): {ctrl_display}\nConcentration: {conc_display}\nImage: {row.get('ImagePath','')}\nNotes: {row.get('Notes','')}")
        self.txt_details.delete('1.0', tk.END); self.txt_details.insert(tk.END, txt)

    def edit_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a record first."); return
        idx = int(sel[0]); row = self.model.df.loc[idx]; self.selected_index = idx
        self.entry_isolate.delete(0,tk.END); self.entry_isolate.insert(0,row["Isolate"])
        self.entry_fungus.delete(0,tk.END); self.entry_fungus.insert(0,row["Fungus"])
        self.entry_zone.delete(0,tk.END); self.entry_zone.insert(0,f"{row['Measurement_mm']:.2f}")
        self.entry_control.delete(0,tk.END)
        if not pd.isna(row.get("Control_mm", np.nan)): self.entry_control.insert(0, f"{row['Control_mm']:.2f}")
        self.entry_conc.delete(0,tk.END)
        if not pd.isna(row.get("Concentration_CFU_per_ml", np.nan)): self.entry_conc.insert(0, f"{int(row['Concentration_CFU_per_ml']):d}")
        self.current_image = row.get("ImagePath","") if isinstance(row.get("ImagePath",""), str) else ""
        self.lbl_image.config(text=os.path.basename(self.current_image) if self.current_image else "No image")

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a record first."); return
        idx = int(sel[0]); row = self.model.df.loc[idx].to_dict()
        if messagebox.askyesno("Confirm", f"Delete record {idx}: {row['Isolate']} vs {row['Fungus']}?"):
            self._last_deleted = (idx, row); self.model.delete(idx); self.refresh_table(); self.refresh_dropdowns(); self.txt_details.delete('1.0', tk.END)

    def undo_delete(self):
        if not self._last_deleted:
            messagebox.showinfo("Undo", "No deletion to undo."); return
        idx, row = self._last_deleted; df_top = self.model.df.iloc[:idx]; df_bot = self.model.df.iloc[idx:]; restored = pd.DataFrame([row])
        self.model.df = pd.concat([df_top, restored, df_bot]).reset_index(drop=True); self._last_deleted = None; self.refresh_table(); self.refresh_dropdowns(); messagebox.showinfo("Undo", "Last deletion undone.")

    def show_image_preview(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a record."); return
        idx = int(sel[0]); imgpath = self.model.df.at[idx, "ImagePath"]
        if not isinstance(imgpath, str) or not imgpath or not os.path.exists(imgpath):
            messagebox.showinfo("No image", "No valid image for selected record."); return
        top = tk.Toplevel(self); top.title(os.path.basename(imgpath)); img = Image.open(imgpath)
        img.thumbnail((1000,800)); tkimg = ImageTk.PhotoImage(img); lbl = ttk.Label(top, image=tkimg); lbl.image = tkimg; lbl.pack()

    # -------- Plots & Analysis (PGI-based) --------
    def generate_plot(self):
        # Use PGI_pct when metric_var == "PGI_pct" and Control_mm available for those records
        df = self.model.df.copy()
        if df.empty:
            messagebox.showinfo("No data", "No records to plot."); return

        metric = self.metric_var.get()  # "PGI_pct" or "Measurement_mm"
        plot_type = self.plot_type_var.get()
        mode = self.compare_mode_var.get()
        target = self.target_var.get().strip()

        # compute PGI column if needed
        if metric == "PGI_pct":
            df = compute_pgi_df(df)
            # check if any valid PGI exists for target
        # select subset by mode
        if mode == "ByFungus":
            if not target:
                messagebox.showinfo("Select", "Choose a fungus in Select target."); return
            sub = df[df["Fungus"] == target]
            if sub.empty:
                messagebox.showinfo("No data", f"No records for fungus {target}"); return
            # group by isolate
            group_col = "Isolate"
        else:
            if not target:
                messagebox.showinfo("Select", "Choose an isolate in Select target."); return
            sub = df[df["Isolate"] == target]
            if sub.empty:
                messagebox.showinfo("No data", f"No records for isolate {target}"); return
            group_col = "Fungus"

        # if metric==PGI_pct but none of the sub rows have PGI computed, let user know and fallback to Measurement_mm
        if metric == "PGI_pct" and sub["PGI_pct"].dropna().empty:
            if messagebox.askyesno("No PGI data", "No valid Control_mm for these records so PGI% can't be computed. Plot raw Measurement_mm instead?"):
                metric = "Measurement_mm"
            else:
                return

        # prepare stats per group
        labels = sorted(sub[group_col].unique()) if group_col in sub.columns else []
        # compute means and stds for chosen metric across each label
        means = []
        stds = []
        for lab in labels:
            sel = sub[sub[group_col] == lab]
            vals = sel[metric].dropna().astype(float)
            means.append(vals.mean() if not vals.empty else np.nan)
            stds.append(vals.std(ddof=0) if not vals.empty else np.nan)

        # plotting
        self.ax.clear()
        fig_for_pdf = Figure(figsize=(8,4), dpi=150); ax_pdf = fig_for_pdf.add_subplot(111)
        if plot_type == "bar":
            x = np.arange(len(labels))
            self.ax.bar(x, means, yerr=stds, capsize=5)
            self.ax.set_xticks(x); self.ax.set_xticklabels(labels, rotation=45, ha='right')
            ax_pdf.bar(x, means, yerr=stds, capsize=5)
            ax_pdf.set_xticks(x); ax_pdf.set_xticklabels(labels, rotation=45, ha='right')
            ylabel = "PGI % (higher = better inhibition)" if metric == "PGI_pct" else metric
            self.ax.set_ylabel(ylabel); ax_pdf.set_ylabel(ylabel)
            title_left = f"{'Isolates' if group_col=='Isolate' else 'Fungi'} vs {target}"
            self.ax.set_title(title_left)
            ax_pdf.set_title(title_left)
        elif plot_type == "box":
            data = [sub[sub[group_col] == lab][metric].dropna().astype(float).values for lab in labels]
            self.ax.boxplot(data, labels=labels, patch_artist=True)
            ax_pdf.boxplot(data, labels=labels)
            self.ax.set_ylabel("PGI %" if metric=="PGI_pct" else metric)
            self.ax.set_title(f"Distribution - {target}")
            ax_pdf.set_title(f"Distribution - {target}")
        elif plot_type == "scatter_annot":
            x = np.arange(len(labels))
            self.ax.scatter(x, means, s=80)
            for xi, yi, lab in zip(x, means, labels):
                self.ax.annotate(lab, (xi, yi), textcoords="offset points", xytext=(5,3), ha='left', fontsize=9)
            self.ax.set_xticks(x); self.ax.set_xticklabels(labels, rotation=45, ha='right')
            self.ax.set_ylabel("PGI %" if metric=="PGI_pct" else metric)
            self.ax.set_title(f"Scatter - {target}")
            ax_pdf.scatter(x, means, s=80)
            for xi, yi, lab in zip(x, means, labels):
                ax_pdf.annotate(lab, (xi, yi), textcoords="offset points", xytext=(5,3), ha='left', fontsize=9)
            ax_pdf.set_xticks(x); ax_pdf.set_xticklabels(labels, rotation=45, ha='right')
        elif plot_type == "hist":
            vals = sub[metric].dropna().astype(float).values
            self.ax.hist(vals, bins=12)
            self.ax.set_title(f"Histogram - {target}")
            ax_pdf.hist(vals, bins=12)
            ax_pdf.set_title(f"Histogram - {target}")
        else:
            messagebox.showinfo("Unknown", "Choose a valid plot type"); return

        self.fig.tight_layout(); self.canvas.draw()
        self._last_pgi_fig = fig_for_pdf  # we store last figure (for PDF export consistency)
        # create details text: if metric is PGI, explain best bacteria = highest PGI
        details = ""
        if metric == "PGI_pct":
            if np.all(np.isnan(means)):
                details = "No valid PGI values (missing Control_mm or invalid values)." 
            else:
                best_idx = np.nanargmax(means)
                best_label = labels[best_idx]
                best_val = means[best_idx]
                details = f"For target '{target}': best performer = {best_label} (mean PGI% = {best_val:.2f}).\n\n"
                for lab, m, s in zip(labels, means, stds):
                    details += f"{lab}: mean PGI% = {'' if pd.isna(m) else f'{m:.2f}'} ± {'' if pd.isna(s) else f'{s:.2f}'}\n"
        else:
            if np.all(np.isnan(means)):
                details = "No valid measurement values."
            else:
                # With raw measurement, larger values indicate more resistant fungus (less effective bacteria).
                # So best bacteria is the one with lowest mean measurement.
                best_idx = np.nanargmin(means)
                best_label = labels[best_idx]
                best_val = means[best_idx]
                details = f"(Raw metric) For target '{target}': most effective = {best_label} (mean measurement = {best_val:.2f} mm - smaller is better).\n\n"
                for lab, m, s in zip(labels, means, stds):
                    details += f"{lab}: mean = {'' if pd.isna(m) else f'{m:.2f}'} ± {'' if pd.isna(s) else f'{s:.2f}'}\n"

        self.txt_details.delete('1.0', tk.END); self.txt_details.insert(tk.END, details)
        # also update last PGI summary text for Reports
        self._last_pgi_summary = details

    def export_plot_png(self):
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG","*.png")])
        if not path: return
        try:
            self.fig.savefig(path, dpi=200); messagebox.showinfo("Saved", f"Plot saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # -------- PGI statistics tab (grouped) --------
    def generate_pgi_plot(self):
        # compute PGI table and populate tree
        pgi_df = compute_pgi_df(self.model.df)
        self._last_pgi_df = pgi_df
        # populate pgi tree
        for r in self.pgi_tree.get_children(): self.pgi_tree.delete(r)
        for idx, row in pgi_df.iterrows():
            pgi_val = "" if pd.isna(row.get("PGI_pct", np.nan)) else f"{row['PGI_pct']:.2f}"
            meas = "" if pd.isna(row.get("Measurement_mm", np.nan)) else f"{row['Measurement_mm']:.2f}"
            ctrl = "" if pd.isna(row.get("Control_mm", np.nan)) else f"{row['Control_mm']:.2f}"
            self.pgi_tree.insert("", "end", values=(idx, row["Isolate"], row["Fungus"], meas, ctrl, pgi_val))

        group_mode = self.pgi_group_var.get()
        agg_mode = self.pgi_agg_var.get()
        plot_type = self.pgi_plot_var.get()

        # choose x_groups and series key
        if group_mode == "ByFungus":
            x_groups = sorted(self.model.df["Fungus"].dropna().unique())
            series_key = "Isolate"
        else:
            x_groups = sorted(self.model.df["Isolate"].dropna().unique())
            series_key = "Fungus"

        valid = pgi_df.dropna(subset=["PGI_pct"])
        series_labels = sorted(valid[series_key].dropna().unique())
        mean_mat = pd.DataFrame(index=series_labels, columns=x_groups, dtype=float)
        std_mat = pd.DataFrame(index=series_labels, columns=x_groups, dtype=float)
        raw_vals = { (ser,xg): [] for ser in series_labels for xg in x_groups }
        for _, row in valid.iterrows():
            ser = row[series_key]; xg = row["Fungus"] if group_mode=="ByFungus" else row["Isolate"]
            if ser in series_labels and xg in x_groups:
                raw_vals[(ser,xg)].append(row["PGI_pct"])
        for ser in series_labels:
            for xg in x_groups:
                v = raw_vals[(ser,xg)]
                if v:
                    mean_mat.at[ser,xg] = float(np.nanmean(v)); std_mat.at[ser,xg] = float(np.nanstd(v, ddof=0))
                else:
                    mean_mat.at[ser,xg] = np.nan; std_mat.at[ser,xg] = np.nan

        # plotting
        self.pgi_ax.clear()
        fig_for_pdf = Figure(figsize=(8,4), dpi=150); ax_pdf = fig_for_pdf.add_subplot(111)
        if plot_type == "grouped_bar":
            n = len(x_groups); m = len(series_labels)
            if m==0 or n==0:
                messagebox.showinfo("No data", "No valid PGI values to plot."); return
            x = np.arange(n); width = 0.8/m
            for i, ser in enumerate(series_labels):
                vals = mean_mat.loc[ser].values.astype(float)
                errs = std_mat.loc[ser].values.astype(float)
                pos = x - 0.4 + i*width + width/2
                self.pgi_ax.bar(pos, vals, width=width, yerr=errs, capsize=4, label=ser)
                ax_pdf.bar(pos, vals, width=width, yerr=errs, capsize=4, label=ser)
            self.pgi_ax.set_xticks(x); self.pgi_ax.set_xticklabels(x_groups, rotation=45, ha='right')
            ax_pdf.set_xticks(x); ax_pdf.set_xticklabels(x_groups, rotation=45, ha='right')
            self.pgi_ax.set_ylabel("PGI % (higher = better)"); ax_pdf.set_ylabel("PGI % (higher = better)")
            self.pgi_ax.set_title("PGI% by group (mean ± std)"); ax_pdf.set_title("PGI% by group (mean ± std)")
            self.pgi_ax.legend(fontsize=8); ax_pdf.legend(fontsize=8)
        elif plot_type == "boxplot":
            # build data list grouped
            data = []
            labels_for_plot = []
            for xg in x_groups:
                for ser in series_labels:
                    vals = raw_vals[(ser,xg)]
                    data.append(vals if vals else [np.nan])
                    labels_for_plot.append(f"{xg}\n{ser}")
            # positions will be sequential
            if all(np.isnan(np.array([np.nanmean(d) if len(d)>0 else np.nan for d in data]))):
                messagebox.showinfo("No data", "No valid PGI values to plot."); return
            self.pgi_ax.boxplot(data, labels=labels_for_plot, patch_artist=True)
            ax_pdf.boxplot(data, labels=labels_for_plot)
            self.pgi_ax.set_title("PGI% distribution (grouped boxplots)")
            ax_pdf.set_title("PGI% distribution (grouped boxplots)")
        elif plot_type == "scatter_annot":
            if len(series_labels)==0:
                messagebox.showinfo("No data", "No valid PGI values to plot."); return
            series_mean = mean_mat.mean(axis=1, skipna=True).values
            x = np.arange(len(series_labels))
            self.pgi_ax.scatter(x, series_mean, s=80)
            ax_pdf.scatter(x, series_mean, s=80)
            for xi, yi, lab in zip(x, series_mean, series_labels):
                self.pgi_ax.annotate(lab, (xi, yi), textcoords="offset points", xytext=(5,3), ha='left')
                ax_pdf.annotate(lab, (xi, yi), textcoords="offset points", xytext=(5,3), ha='left')
            self.pgi_ax.set_xticks(x); self.pgi_ax.set_xticklabels(series_labels, rotation=45, ha='right')
            self.pgi_ax.set_title("PGI% scatter (series mean)")
            ax_pdf.set_title("PGI% scatter (series mean)")
        else:
            messagebox.showinfo("Unknown", "Choose a valid PGI plot type."); return

        self.pgi_fig.tight_layout(); self.pgi_canvas.draw()
        self._last_pgi_fig = fig_for_pdf
        # prepare summary text
        summary = ""
        for xg in x_groups:
            try:
                col = mean_mat[xg].dropna()
                if col.empty:
                    summary += f"{xg}: no PGI data\n"
                else:
                    best = col.idxmax(); best_val = col.max()
                    summary += f"{xg}: best = {best} (mean PGI% = {best_val:.2f})\n"
            except Exception:
                summary += f"{xg}: error computing\n"
        summary += "\nNotes:\n- PGI% computed only when Control_mm > 0 is present per record.\n- Higher PGI% indicates better inhibition by the bacteria.\n"
        # highlight excluded records
        nan_rows = pgi_df[pgi_df["PGI_pct"].isna()]
        if not nan_rows.empty:
            summary += f"\nExcluded (missing/invalid Control_mm): {len(nan_rows)} - indexes {list(nan_rows.index)}\n"
        bad = pgi_df[(pgi_df["PGI_pct"].notna()) & ((pgi_df["PGI_pct"]<0) | (pgi_df["PGI_pct"]>100))]
        if not bad.empty:
            summary += "\nSuspicious PGI values (negative or >100):\n"
            for idx, row in bad.iterrows():
                summary += f" - index {idx}: PGI={row['PGI_pct']:.2f} ({row['Isolate']} vs {row['Fungus']})\n"

        self.pgi_notes.delete('1.0', tk.END); self.pgi_notes.insert(tk.END, summary)
        self._last_pgi_summary = summary

    def export_pgi_csv(self):
        if self._last_pgi_df is None:
            messagebox.showinfo("No data", "Generate PGI first."); return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if not path: return
        try:
            self._last_pgi_df.to_csv(path, index=False); messagebox.showinfo("Saved", f"PGI CSV saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_pgi_pdf(self):
        if self._last_pgi_fig is None or not self._last_pgi_summary:
            messagebox.showinfo("No data", "Generate PGI plot first."); return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF","*.pdf")])
        if not path: return
        try:
            self._create_pgi_pdf(path, self._last_pgi_fig, self._last_pgi_summary); messagebox.showinfo("Saved", f"PGI PDF saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _create_pgi_pdf(self, outpath, fig_obj, details_text):
        c = canvas.Canvas(outpath, pagesize=A4); width, height = A4; margin = 36; y = height - margin
        c.setFont("Helvetica-Bold", 16); c.drawString(margin, y, "PGI% Report"); y -= 22
        c.setFont("Helvetica", 10); c.drawString(margin, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"); y -= 16
        buf = io.BytesIO(); fig_obj.tight_layout(); fig_obj.savefig(buf, format="png"); buf.seek(0)
        img_h = 260; c.drawImage(ImageReader(buf), margin, y-img_h, width=width-2*margin, height=img_h); y -= img_h + 8
        c.setFont("Helvetica", 10)
        for line in details_text.splitlines():
            if y < margin+40: c.showPage(); y = height - margin
            c.drawString(margin, y, line); y -= 12
        c.save()

    # -------- Full dataset PDF (keeps previous functionality) --------
    def export_pdf(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF","*.pdf")])
        if not path: return
        try:
            self._create_full_pdf(path); messagebox.showinfo("Saved", f"PDF saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _create_full_pdf(self, outpath):
        c = canvas.Canvas(outpath, pagesize=A4); width, height = A4; margin = 36; y = height - margin
        c.setFont("Helvetica-Bold", 16); c.drawString(margin, y, "Full dataset report"); y -= 22
        c.setFont("Helvetica", 10); c.drawString(margin, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"); y -= 16
        c.drawString(margin, y, f"Total records: {len(self.model.df)}"); y -= 18
        try:
            pivot = self.model.df.pivot_table(index="Isolate", columns="Fungus", values="Measurement_mm", aggfunc=np.mean)
        except Exception:
            pivot = None
        if pivot is not None:
            c.setFont("Helvetica-Bold", 12); c.drawString(margin, y, "Pivot (mean measurement mm)"); y -= 14
            c.setFont("Helvetica", 9)
            rows = pivot.reset_index().fillna("").values.tolist()
            cols = ["Isolate"] + list(pivot.columns)
            colw = (width-2*margin)/len(cols); x = margin
            for col in cols: c.drawString(x, y, str(col)[:12]); x += colw
            y -= 12
            for r in rows[:20]:
                x = margin
                for cell in r:
                    txt = "" if cell == "" else (f"{cell:.2f}" if isinstance(cell, (float, np.floating)) else str(cell))
                    c.drawString(x, y, txt[:12]); x += colw
                y -= 12
                if y < margin + 80: c.showPage(); y = height - margin
        if self._last_pgi_fig is not None:
            buf = io.BytesIO(); self._last_pgi_fig.tight_layout(); self._last_pgi_fig.savefig(buf, format="png"); buf.seek(0)
            h = 240; c.drawImage(ImageReader(buf), margin, y-h, width=width-2*margin, height=h); y -= h + 8
        c.save()

    # -------- Close --------
    def on_close(self):
        try:
            self.model.save(DATA_CSV)
        except Exception:
            pass
        self.destroy()

# -------- Run --------
if __name__ == "__main__":
    app = AnalyzerApp(); app.mainloop()
