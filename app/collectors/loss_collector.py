# app/collectors/loss_collector.py
import pandas as pd
from .base_collector import BaseCollector
from app.zabbix_api import fazer_request_zabbix
from app.charting import generate_multi_bar_chart

class LossCollector(BaseCollector):
    def collect(self, all_hosts, period):
        cache_key = 'latency_loss_data'
        if cache_key not in self.generator.cached_data:
            self._update_status("Coletando dados de Latência e Perda...")
            data, error_msg = self.generator.shared_collect_latency_and_loss(all_hosts, period)
            if error_msg:
                return f"<p>Erro no módulo de Perda de Pacotes: {error_msg}</p>"
            self.generator.cached_data[cache_key] = data
        
        cached_data = self.generator.cached_data[cache_key]
        df_loss = cached_data['df_loss']
        
        module_data = {
            'tabela': df_loss.to_html(classes='table', index=False, float_format='%.2f'),
            'grafico': generate_multi_bar_chart(
                df_loss, 
                'Perda de Pacotes Média (%)', 
                'Perda (%)', 
                ['#ffdf80', '#ffc61a', '#cc9900']
            )
        }
        return self.render('loss', module_data)