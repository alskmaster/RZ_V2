# app/collectors/latency_collector.py
import pandas as pd
from .base_collector import BaseCollector
from app.zabbix_api import fazer_request_zabbix
from app.charting import generate_multi_bar_chart

class LatencyCollector(BaseCollector):
    def collect(self, all_hosts, period):
        cache_key = 'latency_loss_data'
        if cache_key not in self.generator.cached_data:
            self._update_status("Coletando dados de Latência e Perda...")
            data, error_msg = self.generator.shared_collect_latency_and_loss(all_hosts, period)
            if error_msg:
                return f"<p>Erro no módulo de Latência: {error_msg}</p>"
            self.generator.cached_data[cache_key] = data
        
        cached_data = self.generator.cached_data[cache_key]
        df_lat = cached_data['df_lat']
        
        module_data = {
            'tabela': df_lat.to_html(classes='table', index=False, float_format='%.2f'),
            'grafico': generate_multi_bar_chart(
                df_lat, 
                'Latência Média (ms)', 
                'Latência (ms)', 
                ['#ffb3b3', '#ff6666', '#cc0000']
            )
        }
        return self.render('latency', module_data)