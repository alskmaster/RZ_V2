# app/collectors/stress_collector.py
import pandas as pd
import base64
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime as dt

from .base_collector import BaseCollector

class StressCollector(BaseCollector):
    """
    Collector para o módulo "Eletrocardiograma do Ambiente".
    Analisa a distribuição de incidentes ao longo do tempo.
    """
    def _generate_timeline_chart(self, df):
        if df.empty:
            return None

        # Garante que o índice é do tipo Datetime para manipulação correta
        df.index = pd.to_datetime(df.index)

        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(12, 6), dpi=100)

        ax.bar(df.index, df['Ocorrências'], color='#2980b9', width=0.8)

        # Formatando o eixo X para exibir as datas de forma inteligente
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=10, maxticks=31))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')

        ax.set_ylabel('Nº de Novos Incidentes')
        ax.set_title('Linha do Tempo de Incidentes (Estresse do Ambiente)')
        ax.grid(True, which='major', axis='y', linestyle='--', linewidth=0.5)
        for spine in ['top', 'right']:
            ax.spines[spine].set_visible(False)

        plt.tight_layout(pad=2)
        buffer = BytesIO()
        plt.savefig(buffer, format='png', transparent=True)
        plt.close(fig)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def collect(self, all_hosts, period, availability_data):
        self._update_status("Gerando Eletrocardiograma do Ambiente...")

        df_incidents = availability_data.get('df_top_incidents', pd.DataFrame())
        if df_incidents.empty or 'clock' not in df_incidents.columns:
            return self.render('stress', {'grafico': None})

        df_copy = df_incidents.copy()
        
        # Converte a coluna 'clock' para um formato de data legível
        df_copy['event_date'] = pd.to_datetime(df_copy['clock'], unit='s').dt.date

        # Agrupa os incidentes por dia e conta as ocorrências
        incidents_per_day = df_copy.groupby('event_date')['Ocorrências'].sum()
        
        # --- INÍCIO DA NOVA LÓGICA DE CALENDÁRIO COMPLETO ---

        # 1. Descobrir o primeiro e último dia do mês do relatório
        start_date = dt.datetime.fromtimestamp(period['start']).date()
        end_date = dt.datetime.fromtimestamp(period['end']).date()

        # 2. Criar um "calendário" com todos os dias do mês
        all_days_in_month = pd.to_datetime(pd.date_range(start=start_date, end=end_date, freq='D')).date
        
        # 3. Criar o DataFrame final com todos os dias, começando com zero incidentes
        df_full_month = pd.DataFrame(index=all_days_in_month)
        df_full_month['Ocorrências'] = 0

        # 4. Atualizar o calendário com os dados reais dos dias que tiveram incidentes
        df_full_month.update(incidents_per_day)

        # --- FIM DA NOVA LÓGICA ---
        
        # Gera o gráfico a partir do DataFrame completo do mês
        grafico_timeline = self._generate_timeline_chart(df_full_month)

        module_data = {
            'grafico': grafico_timeline
        }
        
        return self.render('stress', module_data)