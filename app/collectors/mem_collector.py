# app/collectors/mem_collector.py
import pandas as pd
from flask import current_app
from .base_collector import BaseCollector
from app.charting import generate_multi_bar_chart
# Importa os modelos para a busca dinâmica de chaves
from app.models import MetricKeyProfile, CalculationType

class MemCollector(BaseCollector):
    """
    Plugin (Collector) específico para coletar e renderizar dados de Memória.
    Esta versão utiliza o sistema de Perfis de Métrica para buscar dinamicamente
    as chaves de item no Zabbix, aplicando cálculos conforme configurado.
    """

    def collect(self, all_hosts, period):
        """
        Orquestra a coleta, processamento e renderização dos dados de memória.
        """
        current_app.logger.debug("Módulo Memória [Dinâmico]: Iniciando coleta.")
        self._update_status("Coletando dados de Memória...")

        data, error_msg = self._collect_mem_data(all_hosts, period)
        if error_msg:
            current_app.logger.error(f"Módulo Memória [Dinâmico]: Erro durante a coleta - {error_msg}")
            return f"<p>Erro no módulo de Memória: {error_msg}</p>"

        if not data or data['df_mem'].empty:
            current_app.logger.warning("Módulo Memória [Dinâmico]: Nenhum dado de memória foi retornado para os hosts selecionados.")
            return "<p>Não foram encontrados dados de memória para os hosts no período selecionado.</p>"

        df_mem = data['df_mem']
        current_app.logger.debug(f"Módulo Memória [Dinâmico]: DataFrame criado com sucesso para {len(df_mem)} hosts.")
        
        try:
            module_data = {
                'tabela': df_mem.to_html(classes='table', index=False, float_format='%.2f'),
                'grafico': generate_multi_bar_chart(
                    df_mem, 
                    'Ocupação de Memória (%)', 
                    'Uso de Memória (%)', 
                    ['#99ccff', '#4da6ff', '#0059b3']
                )
            }
            current_app.logger.debug("Módulo Memória [Dinâmico]: Gráfico e tabela gerados com sucesso.")
        except Exception as e:
            error_msg = f"Falha ao gerar gráfico ou tabela de memória: {e}"
            current_app.logger.error(error_msg, exc_info=True)
            return f"<p>Erro interno no módulo de Memória: {error_msg}</p>"

        return self.render('mem', module_data)

    def _collect_mem_data(self, all_hosts, period):
        """
        Coleta e processa dados de memória do Zabbix de forma dinâmica,
        utilizando os perfis de métricas cadastrados no banco de dados.
        """
        try:
            # 1. Buscar os perfis de chave para 'memory' do banco de dados
            mem_key_profiles = MetricKeyProfile.query.filter_by(
                metric_type='memory', 
                is_active=True
            ).order_by(MetricKeyProfile.priority).all()

            if not mem_key_profiles:
                return None, "Nenhum perfil de coleta para 'memória' está ativo no sistema. Configure na área de administração."
            
            current_app.logger.debug(f"Módulo Memória [Dinâmico]: {len(mem_key_profiles)} perfis de chave encontrados.")
            for profile in mem_key_profiles:
                current_app.logger.debug(f" - Perfil Prioridade {profile.priority}: Key='{profile.key_string}', Cálculo='{profile.calculation_type.name}'")

            host_map = {h['hostid']: h['nome_visivel'] for h in all_hosts}
            
            # 2. Encontrar o item correto para cada host, seguindo a prioridade dos perfis
            items_to_fetch = []
            item_profile_map = {} # Mapeia itemid -> profile para saber o cálculo a ser usado

            for host in all_hosts:
                host_id = host['hostid']
                item_found_for_host = False
                for profile in mem_key_profiles:
                    current_app.logger.debug(f"Procurando item com a chave '{profile.key_string}' para o host '{host_map[host_id]}'.")
                    items = self.generator.get_items([host_id], profile.key_string, search_by_key=True)
                    if items:
                        item = items[0] # Pega o primeiro item encontrado para essa chave/host
                        items_to_fetch.append(item)
                        item_profile_map[item['itemid']] = profile
                        current_app.logger.debug(f"SUCESSO: Item {item['itemid']} encontrado para o host '{host_map[host_id]}' usando o perfil de prioridade {profile.priority}.")
                        item_found_for_host = True
                        break # Para de procurar perfis para este host, pois já achamos o de maior prioridade
                
                if not item_found_for_host:
                    current_app.logger.warning(f"AVISO: Nenhum item de memória correspondente a qualquer perfil ativo foi encontrado para o host '{host_map[host_id]}'.")

            if not items_to_fetch:
                return None, "Não foi possível encontrar itens de monitoramento de memória em nenhum dos hosts selecionados usando os perfis de coleta ativos."

            # 3. Coletar o histórico de todos os itens encontrados de uma só vez
            item_ids = [item['itemid'] for item in items_to_fetch]
            current_app.logger.debug(f"Módulo Memória [Dinâmico]: Buscando histórico para {len(item_ids)} itens.")
            history = self.generator.get_trends(item_ids, period)

            if not history:
                return None, "Não foi possível obter o histórico de dados de memória para os itens encontrados."

            # 4. Processar os dados aplicando o cálculo correto para cada item
            mem_data = []
            for item in items_to_fetch:
                host_id = item['hostid']
                item_history = [h for h in history if h['itemid'] == item['itemid']]
                
                if item_history:
                    profile = item_profile_map[item['itemid']]
                    
                    avg_values = [float(h['value_avg']) for h in item_history]
                    min_values = [float(h['value_min']) for h in item_history]
                    max_values = [float(h['value_max']) for h in item_history]

                    avg = sum(avg_values) / len(avg_values)
                    min_val = min(min_values)
                    max_val = max(max_values)

                    # Aplica o cálculo dinâmico baseado no perfil
                    if profile.calculation_type == CalculationType.INVERSE:
                        current_app.logger.debug(f"Aplicando cálculo INVERSO para o item {item['itemid']} (Host: {host_map[host_id]})")
                        avg = 100 - avg
                        # A inversão de min/max é mais precisa desta forma
                        temp_min = 100 - max_val
                        max_val = 100 - min_val
                        min_val = temp_min

                    mem_data.append({
                        'Host': host_map.get(host_id, f"Host ID {host_id}"),
                        'Min %': min_val,
                        'Med %': avg,
                        'Max %': max_val
                    })
                else:
                    current_app.logger.warning(f"Módulo Memória [Dinâmico]: Nenhum dado de histórico retornado para o item {item['itemid']} do host {host_map.get(host_id)}.")
            
            if not mem_data:
                return None, "Dados de histórico de memória foram encontrados, mas não puderam ser processados."

            df_mem = pd.DataFrame(mem_data)
            return {'df_mem': df_mem}, None

        except Exception as e:
            current_app.logger.error(f"Módulo Memória [Dinâmico]: Exceção inesperada: {e}", exc_info=True)
            return None, "Ocorreu um erro interno inesperado ao processar os dados de memória."