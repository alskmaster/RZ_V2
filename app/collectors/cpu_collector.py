# app/collectors/cpu_collector.py
import pandas as pd
from .base_collector import BaseCollector
# Novos imports:
from app.zabbix_api import fazer_request_zabbix
from app.charting import generate_multi_bar_chart

class CpuCollector(BaseCollector):
    def collect(self, all_hosts, period):
        self._update_status("Coletando dados de CPU...")
        
        host_ids = [h['hostid'] for h in all_hosts]
        host_map = {h['hostid']: h['nome_visivel'] for h in all_hosts}
        
        cpu_items = self.generator.get_items(host_ids, 'system.cpu.util', search_by_key=True)
        if not cpu_items: 
            return f"<p>Erro no módulo de CPU: Nenhum item de CPU ('system.cpu.util') encontrado.</p>"

        cpu_trends = self.generator.get_trends([item['itemid'] for item in cpu_items], period['start'], period['end'])
        
        df_cpu = self.generator._process_trends(cpu_trends, cpu_items, host_map)

        module_data = {
            'tabela': df_cpu.to_html(classes='table', index=False, float_format='%.2f'),
            'grafico': generate_multi_bar_chart(
                df_cpu, 
                'Ocupação de CPU (%)', 
                'Uso de CPU (%)', 
                ['#ff9999', '#ff4d4d', '#b30000']
            )
        }
        return self.render('cpu', module_data)