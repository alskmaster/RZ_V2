# app/collectors/top_hosts_collector.py
import pandas as pd
import base64
import textwrap
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from .base_collector import BaseCollector

class TopHostsCollector(BaseCollector):
    
    def _generate_bar_chart(self, breakdown_data, chart_color):
        if not breakdown_data: return None
        
        df = pd.DataFrame(list(breakdown_data.items()), columns=['Problema', 'Ocorrências']).sort_values(by='Ocorrências', ascending=True)
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(8, 4), dpi=100)
        
        y_labels = ['\n'.join(textwrap.wrap(str(label), width=40)) for label in df['Problema']]
        bars = ax.barh(y_labels, df['Ocorrências'], color=chart_color)
        
        ax.set_xlabel('Nº de Ocorrências')
        ax.tick_params(axis='y', labelsize=8)
        ax.grid(True, which='major', axis='x', linestyle='--', linewidth=0.5)
        for spine in ['top', 'right', 'left', 'bottom']: ax.spines[spine].set_visible(False)
        
        plt.subplots_adjust(left=0.4, right=0.95, top=0.95, bottom=0.15)
        buffer = BytesIO()
        plt.savefig(buffer, format='png', transparent=True)
        plt.close(fig)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def _generate_pie_chart(self, breakdown_data):
        if not breakdown_data: return None

        top_5 = sorted(breakdown_data.items(), key=lambda item: item[1], reverse=True)[:5]
        labels = [item[0] for item in top_5]
        sizes = [item[1] for item in top_5]
        
        if len(breakdown_data) > 5:
            others_sum = sum(item[1] for item in sorted(breakdown_data.items(), key=lambda item: item[1], reverse=True)[5:])
            labels.append('Outros')
            sizes.append(others_sum)

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(8, 4), dpi=100)
        
        wedges, _, autotexts = ax.pie(sizes, autopct='%1.1f%%', startangle=90)
        plt.setp(autotexts, size=8, weight="bold", color="white")
        ax.axis('equal')
        
        ax.legend(wedges, labels, title="Problemas", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), fontsize='small')

        plt.subplots_adjust(left=0.1, right=0.7, top=0.95, bottom=0.05)
        buffer = BytesIO()
        plt.savefig(buffer, format='png', transparent=True)
        plt.close(fig)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def collect(self, all_hosts, period, availability_data):
        self._update_status("Analisando os principais ofensores de indisponibilidade...")

        df_sla = availability_data.get('df_sla_problems', pd.DataFrame())
        df_incidents = availability_data.get('df_top_incidents', pd.DataFrame())
        
        custom_options = self.module_config.get('custom_options', {})
        top_n = int(custom_options.get('top_n', 5))
        chart_type = custom_options.get('chart_type', 'table')

        if df_sla.empty:
            return self.render('top_hosts', {
                'ofensores': [],
                'summary_chart': None,
                'custom_options': custom_options
            })

        top_hosts_atual = df_sla[df_sla['SLA (%)'] < 100].head(top_n)

        summary_df_chart = top_hosts_atual.copy()
        summary_df_chart['downtime_hours'] = summary_df_chart['Tempo Indisponível'].apply(lambda x: pd.to_timedelta(x).total_seconds() / 3600)
        summary_chart_b64 = self._generate_bar_chart_summary(summary_df_chart, top_n)
        
        ofensores_data = []
        for _, host_row in top_hosts_atual.iterrows():
            host_name = host_row['Host']
            
            host_incidents = df_incidents[df_incidents['Host'] == host_name] if not df_incidents.empty else pd.DataFrame()
            # Garante que o valor seja um inteiro padrão do Python
            total_incidentes = int(host_incidents['Ocorrências'].sum()) if not host_incidents.empty else 0
            problem_breakdown = host_incidents.groupby('Problema')['Ocorrências'].sum().sort_values(ascending=False).to_dict() if not host_incidents.empty else {}

            breakdown_chart_b64 = None
            if chart_type != 'table':
                if chart_type == 'pie':
                    breakdown_chart_b64 = self._generate_pie_chart(problem_breakdown)
                else:
                    breakdown_chart_b64 = self._generate_bar_chart(problem_breakdown, '#3498db')

            ofensores_data.append({
                'name': host_name,
                'downtime_str': host_row['Tempo Indisponível'],
                'total_incidents': total_incidentes,
                'breakdown': problem_breakdown,
                'breakdown_chart': breakdown_chart_b64
            })
        
        module_data = {
            'ofensores': ofensores_data,
            'summary_chart': summary_chart_b64,
            'custom_options': custom_options
        }
        
        return self.render('top_hosts', module_data)

    def _generate_bar_chart_summary(self, df, top_n):
        if df.empty: return None
        
        df_sorted = df.sort_values(by='downtime_hours', ascending=True)
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(12, max(4, len(df_sorted) * 0.6)), dpi=100)
        
        bars = ax.barh(df_sorted['Host'], df_sorted['downtime_hours'], color='#c0392b')
        ax.set_xlabel('Horas Indisponível')
        ax.set_title(f'Top {top_n} Hosts por Tempo de Indisponibilidade (Mês Atual)')

        for bar in bars:
            width = bar.get_width()
            if width > 0:
                ax.text(width * 1.01, bar.get_y() + bar.get_height()/2, f'{width:.2f}h', ha='left', va='center', fontsize=8)
        
        plt.tight_layout(pad=3)
        buffer = BytesIO()
        plt.savefig(buffer, format='png', transparent=True)
        plt.close(fig)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')