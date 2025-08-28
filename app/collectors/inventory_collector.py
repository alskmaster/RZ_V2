# app/collectors/inventory_collector.py
import pandas as pd
from .base_collector import BaseCollector

class InventoryCollector(BaseCollector):
    """
    Plugin (Collector) simples para gerar uma tabela de inventário de hosts.
    """
    def collect(self, all_hosts, period):
        self._update_status("Gerando inventário de hosts...")
        
        # Converte a lista de hosts (dicionários) em um DataFrame do Pandas
        df_hosts = pd.DataFrame(all_hosts)
        
        # Seleciona, renomeia e formata as colunas para a tabela
        df_inventory = df_hosts[['nome_visivel', 'ip0']].rename(
            columns={'nome_visivel': 'Host', 'ip0': 'IP'}
        )
        
        # Prepara os dados para o template
        module_data = {
            'tabela': df_inventory.to_html(classes='table', index=False, border=0)
        }

        # Renderiza o HTML final
        return self.render('inventory', module_data)