# app/collectors/wifi_collector.py
import io
import base64
import datetime as dt
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flask import current_app
from .base_collector import BaseCollector


class WiFiCollector(BaseCollector):
    """
    Módulo Wi-Fi (Contagem de Clientes por AP/SSID)
    - Segue o padrão dos módulos customizáveis (usa BaseCollector + template).
    - Configurações aceitas em custom_options:
        chart: 'bar' | 'line' | 'both' (default: 'bar')
        table: 'summary' | 'detailed' | 'both' (default: 'both')
        heatmap: 'global' | 'per_ap' | 'both' | 'none' (default: 'global')
        capacity_per_ap: int (default: 50)
        max_charts: int (default: 6)
    """

    def collect(self, all_hosts, period):
        self._update_status("Coletando dados Wi-Fi...")

        opts = (self.module_config or {}).get("custom_options", {}) or {}
        chart_mode = str(opts.get("chart", "bar")).lower()
        table_mode = str(opts.get("table", "both")).lower()
        heatmap_mode = str(opts.get("heatmap", "global")).lower()
        capacity = float(opts.get("capacity_per_ap", 50))
        max_charts = int(opts.get("max_charts", 6))

        wifi_keys = self._resolve_wifi_keys()
        host_ids = [h["hostid"] for h in all_hosts]
        host_map = {h["hostid"]: h["nome_visivel"] for h in all_hosts}

        # Busca itens
        items = []
        for key in wifi_keys:
            items.extend(self.generator.get_items(host_ids, key, search_by_key=True))
        if not items:
            return self.render("wifi", {"error": "Nenhum item Wi-Fi encontrado."})

        seen = set()
        items = [it for it in items if not (it["itemid"] in seen or seen.add(it["itemid"]))]

        # Trends do período atual
        trends = self.generator.get_trends([it["itemid"] for it in items], period)
        if not trends:
            return self.render("wifi", {"error": "Sem dados de Wi-Fi para o período."})

        df = pd.DataFrame(trends)
        for c in ["clock", "value_avg"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["clock", "value_avg"])
        if df.empty:
            return self.render("wifi", {"error": "Dados inválidos."})

        item_to_host = {it["itemid"]: it["hostid"] for it in items}
        df["hostid"] = df["itemid"].map(item_to_host)
        df["host"] = df["hostid"].map(host_map)
        df["datetime"] = df["clock"].apply(lambda x: dt.datetime.fromtimestamp(int(x)))
        df["date"] = df["datetime"].dt.date

        # KPIs
        pico_global = int(df["value_avg"].max())
        p95_global = int(df["value_avg"].quantile(0.95))
        total_aps = df["hostid"].nunique()

        # Agregações
        daily_ap = df.groupby(["host", "date"])["value_avg"].max().reset_index()

        summary_rows = []
        detailed_blocks = []

        if table_mode in ("summary", "both"):
            total_current = daily_ap.groupby("host")["value_avg"].sum().reset_index()
            for _, r in total_current.iterrows():
                summary_rows.append({
                    "host": r["host"],
                    "ap": "-",                # manter coluna AP no template
                    "total_current": int(r["value_avg"]),
                    "total_prev": 0           # TODO: comparar mês anterior (se necessário)
                })

        if table_mode in ("detailed", "both"):
            for host, part in daily_ap.groupby("host"):
                rows = [{"date": str(d), "max_daily": int(v)} for d, v in zip(part["date"], part["value_avg"])]
                detailed_blocks.append({"host": host, "ap": "AP", "rows": rows})

        # Gráficos
        charts_ap = []
        line_chart = None

        if chart_mode in ("bar", "both"):
            top_hosts = (daily_ap.groupby("host")["value_avg"].sum()
                                   .sort_values(ascending=False)
                                   .head(max_charts).index)
            for host in top_hosts:
                part = daily_ap[daily_ap["host"] == host]
                charts_ap.append(self._render_bar_chart(part, f"{host} – Máximo diário"))

        if chart_mode in ("line", "both"):
            global_daily = daily_ap.groupby("date")["value_avg"].sum().reset_index()
            line_chart = self._render_line_chart(global_daily, "Clientes Wi-Fi – soma dos máximos diários")

        # Heatmaps
        heatmap_global = None
        heatmap_per_ap = []

        if heatmap_mode in ("global", "both"):
            heatmap_global = self._render_heatmap_global(df)

        if heatmap_mode in ("per_ap", "both"):
            for host, part in df.groupby("host"):
                heatmap_per_ap.append(self._render_heatmap_single(part, f"{host}"))

        data = {
            "error": None,
            "kpis": {
                "pico_global": pico_global,
                "p95_global": p95_global,
                "total_aps": total_aps,
                "capacity": capacity
            },
            "charts_ap": charts_ap,
            "line_chart": line_chart,
            "summary_rows": summary_rows,
            "detailed_blocks": detailed_blocks,
            "heatmap_global": heatmap_global,
            "heatmap_per_ap": heatmap_per_ap,
            "show_table_summary": table_mode in ("summary", "both"),
            "show_table_detailed": table_mode in ("detailed", "both")
        }

        # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> CORREÇÃO AQUI <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        # BaseCollector.render já prefixa 'modules/', então passamos apenas 'wifi'
        return self.render("wifi", data)

    # ---------------- Helpers ----------------
    def _resolve_wifi_keys(self):
        try:
            from app.models import MetricKeyProfile
            profs = MetricKeyProfile.query.filter_by(metric_type="wifi_clients", is_active=True).all()
            return [p.key_string for p in profs] if profs else ["clientcountnumber"]
        except Exception as e:
            current_app.logger.warning(f"[WiFi] Falha ao buscar keys: {e}")
            return ["clientcountnumber"]

    def _fig_to_img(self, fig):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _render_bar_chart(self, df, title):
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.bar(df["date"].astype(str), df["value_avg"])
        ax.set_title(title)
        ax.set_ylabel("Máximo diário")
        ax.set_xlabel("Dia")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        return self._fig_to_img(fig)

    def _render_line_chart(self, df, title):
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.plot(df["date"].astype(str), df["value_avg"])
        ax.set_title(title)
        ax.set_ylabel("Clientes")
        ax.set_xlabel("Dia")
        ax.grid(True, linestyle="--", alpha=0.3)
        return self._fig_to_img(fig)

    def _render_heatmap_global(self, df):
        df = df.copy()
        df["hour"] = df["datetime"].dt.hour
        mat = df.groupby("hour")["value_avg"].mean().reindex(range(24), fill_value=0)
        fig, ax = plt.subplots(figsize=(10, 1.6))
        ax.imshow([mat.values], aspect="auto")
        ax.set_xticks(range(0, 24, 2))
        ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
        ax.set_yticks([])
        ax.set_title("Heatmap Global – média por hora")
        return self._fig_to_img(fig)

    def _render_heatmap_single(self, df_ap, title):
        df_ap = df_ap.copy()
        df_ap["hour"] = df_ap["datetime"].dt.hour
        mat = df_ap.groupby("hour")["value_avg"].mean().reindex(range(24), fill_value=0)
        fig, ax = plt.subplots(figsize=(10, 1.6))
        ax.imshow([mat.values], aspect="auto")
        ax.set_xticks(range(0, 24, 2))
        ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
        ax.set_yticks([])
        ax.set_title(f"Heatmap – {title}")
        return self._fig_to_img(fig)
