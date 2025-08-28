# app/collectors/kpi_collector.py
import base64
from io import BytesIO
import matplotlib
matplotlib.use('Agg')  # Configura o Matplotlib para não usar interface gráfica
import matplotlib.pyplot as plt

from .base_collector import BaseCollector

class KpiCollector(BaseCollector):
    """
    Collector dedicado a renderizar o painel de KPIs de disponibilidade.
    Recebe os dados já processados do ReportGenerator e os passa para o template.
    Agora também gera um gráfico de pizza da severidade dos incidentes.
    """
    
    def _generate_severity_pie_chart(self, severity_data):
        """
        Gera uma imagem de gráfico de pizza a partir dos dados de severidade.
        """
        if not severity_data:
            return None

        labels = list(severity_data.keys())
        sizes = list(severity_data.values())

        # Mapeamento de cores padrão do Zabbix para consistência visual
        color_map = {
            'Não Classificado': '#97AAB3',
            'Informação': '#7499FF',
            'Atenção': '#FFC859',
            'Média': '#FFA059',
            'Alta': '#E97659',
            'Desastre': '#E45959',
            'Desconhecido': '#D4D4D4'
        }
        
        # Garante que temos cores para todas as labels, usando cinza como padrão
        colors = [color_map.get(label, '#BDBDBD') for label in labels]

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
        
        wedges, texts, autotexts = ax.pie(
            sizes, 
            labels=labels, 
            autopct='%1.1f%%', 
            startangle=140, 
            colors=colors,
            wedgeprops={'edgecolor': 'white', 'linewidth': 1}
        )
        
        # Melhora a legibilidade dos textos
        plt.setp(autotexts, size=8, weight="bold", color="white")
        plt.setp(texts, size=9)
        
        ax.axis('equal')  # Garante que a pizza seja um círculo.
        
        # Salva o gráfico em um buffer de memória
        buffer = BytesIO()
        plt.savefig(buffer, format='png', transparent=True, bbox_inches='tight')
        plt.close(fig)
        
        # Converte a imagem para base64
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def collect(self, all_hosts, period, availability_data):
        """
        Renderiza o módulo de KPIs, incluindo o novo gráfico de pizza.
        """
        self._update_status("Renderizando painel de KPIs de Disponibilidade...")

        kpis_data = availability_data.get('kpis')
        if not kpis_data:
            return "<p><i>Não foi possível renderizar os KPIs de disponibilidade.</i></p>"
        
        # --- INÍCIO DA NOVA MODIFICAÇÃO: Gerar e passar o gráfico para o template ---
        severity_counts = availability_data.get('severity_counts', {})
        pie_chart_base64 = self._generate_severity_pie_chart(severity_counts)
        
        module_data = {
            'kpis_data': kpis_data,
            'pie_chart_base64': pie_chart_base64
        }
        # --- FIM DA NOVA MODIFICAÇÃO ---
        
        return self.render('kpi', module_data)