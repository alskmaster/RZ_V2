# app/collectors/mem_collector.py
import pandas as pd
from .base_collector import BaseCollector
# Importa a função de gerar gráfico do novo módulo
from app.charting import generate_multi_bar_chart

class MemCollector(BaseCollector):
    """
    Plugin (Collector) específico para coletar e renderizar dados de Memória.
    """
    def collect(self, all_hosts, period):
        # 1. Informa o status da operação
        self._update_status("Coletando dados de Memória...")

        # 2. Chama a lógica de coleta de dados que agora está neste próprio arquivo
        data, error_msg = self._collect_mem_data(all_hosts, period)
        if error_msg:
            return f"<p>Erro no módulo de Memória: {error_msg}</p>"

        df_mem = data['df_mem']
        
        # 3. Prepara os dados para o template: gera gráfico e tabela
        module_data = {
            'tabela': df_mem.to_html(classes='table', index=False, float_format='%.2f'),
            'grafico': generate_multi_bar_chart(
                df_mem, 
                'Ocupação de Memória (%)', 
                'Uso de Memória (%)', 
                ['#99ccff', '#4da6ff', '#0059b3']
            )
        }

        # 4. Usa o método 'render' da classe base para gerar o HTML final
        return self.render('mem', module_data)

    def _collect_mem_data(self, all_hosts, period):
        """
        Coleta dados de memória do Zabbix.
        Este método foi movido do services.py para cá.
        """
        host_ids = [h['hostid'] for h in all_hosts]
        host_map = {h['hostid']: h['nome_visivel'] for h in all_hosts}
        mem_items = self.generator.get_items(host_ids, 'vm.memory.size[pused]', search_by_key=True)
        mem_pavailable = False
        if not mem_items:
            mem_items = self.generator.get_items(host_ids, 'vm.memory.size[pavailable]', search_by_key=True)
            mem_pavailable = True
        if not mem_items: return None, "Nenhum item de Memória ('vm.memory.size[pused]' ou '[pavailable]') encontrado."
        mem_trends = self.generator.get_trends([item['itemid'] for item in mem_items], period['start'], period['end'])
        df_mem = self.generator._process_trends(mem_trends, mem_items, host_map, is_pavailable=mem_pavailable)
        return {'df_mem': df_mem}, None