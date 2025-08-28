# app/collectors/top_problems_collector.py
import base64
import textwrap
import pandas as pd
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from .base_collector import BaseCollector

class TopProblemsCollector(BaseCollector):
    """
    Collector evoluído para o "Painel de Vilões".
    Analisa os problemas de forma sistêmica, em todo o ambiente.
    """
    def generate_chart(self, df, x_col, y_col, title, x_label, chart_color):
        if df.empty: return None
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(12, 6), dpi=100) # Deixando o gráfico um pouco mais largo
        
        df_sorted = df.sort_values(by=x_col, ascending=True)
        
        # Ajusta a largura do texto para o novo layout
        y_labels = ['\n'.join(textwrap.wrap(str(label), width=60)) for label in df_sorted[y_col]]
        
        bars = ax.barh(y_labels, df_sorted[x_col], color=chart_color)
        
        font_size = 9
        ax.tick_params(axis='y', labelsize=font_size)
        ax.set_xlabel(x_label)
        ax.set_title(title, fontsize=16)
        ax.grid(True, which='major', axis='x', linestyle='--', linewidth=0.5)
        for spine in ['top', 'right', 'left', 'bottom']: ax.spines[spine].set_visible(False)
        
        for bar in bars:
            label_val = bar.get_width()
            label = f'{int(label_val)}'
            ax.text(label_val * 1.01, bar.get_y() + bar.get_height()/2, f' {label}', va='center', ha='left', fontsize=font_size - 1)
        
        plt.tight_layout(pad=2)
        buffer = BytesIO()
        plt.savefig(buffer, format='png', transparent=True)
        plt.close(fig)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def collect(self, all_hosts, period, availability_data):
        self._update_status("Gerando Painel de Vilões Sistêmicos...")

        df_top_incidents = availability_data.get('df_top_incidents', pd.DataFrame())
        if df_top_incidents.empty:
            return self.render('top_problems', {'grafico': None, 'drilldown_data': None})
            
        # 1. A Nova Lógica: Agrupar apenas por 'Problema'
        df_systemic_problems = df_top_incidents.groupby('Problema')['Ocorrências'].sum().reset_index()
        df_systemic_problems = df_systemic_problems.sort_values(by='Ocorrências', ascending=False).head(10)

        # 2. Gerar o novo gráfico principal
        grafico_sistemico = self.generate_chart(
            df_systemic_problems, 
            'Ocorrências', 
            'Problema', 
            'Top 10 Problemas Sistêmicos por Ocorrência', 
            'Número Total de Ocorrências no Ambiente', 
            self.generator.system_config.secondary_color
        )
        
        # 3. Preparar os dados para o "Drill-down" do principal vilão
        drilldown_data = None
        if not df_systemic_problems.empty:
            top_villain_name = df_systemic_problems.iloc[0]['Problema']
            
            # Filtra a lista original de incidentes para pegar só os do vilão principal
            df_villain_details = df_top_incidents[df_top_incidents['Problema'] == top_villain_name]
            
            # Agrupa por host para ver quem mais sofreu com esse problema
            df_villain_hosts = df_villain_details.groupby('Host')['Ocorrências'].sum().reset_index()
            df_villain_hosts = df_villain_hosts.sort_values(by='Ocorrências', ascending=False).head(5)
            
            drilldown_data = {
                'villain_name': top_villain_name,
                'hosts_table': df_villain_hosts.to_dict('records') # Converte para uma lista de dicionários
            }

        module_data = {
            'grafico': grafico_sistemico,
            'drilldown_data': drilldown_data
        }
        
        return self.render('top_problems', module_data)