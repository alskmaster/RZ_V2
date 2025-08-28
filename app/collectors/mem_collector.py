# app/collectors/mem_collector.py
import pandas as pd
from flask import current_app
from .base_collector import BaseCollector
from app.charting import generate_multi_bar_chart
from app.models import MetricKeyProfile, CalculationType


class MemCollector(BaseCollector):
    """
    Plugin (Collector) para coletar e renderizar dados de Memória.
    - Usa Perfis de Métrica (tabela MetricKeyProfile) para decidir dinamicamente quais chaves buscar.
    - Padroniza o DataFrame final para colunas: ['Host', 'Min', 'Avg', 'Max'] (floats).
    - Acrescenta logs detalhados (debug) em todas as etapas.
    - Otimiza volume: busca itens por perfil em lote (menos chamadas à API).
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
            current_app.logger.warning(
                "Módulo Memória [Dinâmico]: Nenhum dado de memória foi retornado para os hosts selecionados."
            )
            return "<p>Não foram encontrados dados de memória para os hosts no período selecionado.</p>"

        df_mem = data['df_mem']
        current_app.logger.debug(
            f"Módulo Memória [Dinâmico]: DataFrame criado com sucesso: "
            f"{len(df_mem)} linhas | colunas={list(df_mem.columns)} | dtypes={dict(df_mem.dtypes)}"
        )
        current_app.logger.debug(f"Módulo Memória [Dinâmico]: Amostra de dados:\n{df_mem.head(5).to_string(index=False)}")

        # Opção para limitar a quantidade no gráfico (pensando em grandes volumes)
        top_n = None
        try:
            # se existir opção no módulo (ex.: {"top_n": 60}), aplica antes do gráfico
            top_n = int(self.module_config.get('custom_options', {}).get('top_n', 0) or 0)
        except Exception:
            top_n = 0

        df_for_chart = df_mem
        if top_n and top_n > 0:
            # Mantém os maiores 'Avg' (mais relevantes), depois ordena ascendente para exibição agradável
            df_for_chart = (
                df_mem.nlargest(top_n, 'Avg')
                .sort_values(by='Avg', ascending=True)
                .reset_index(drop=True)
            )
            current_app.logger.info(
                f"Módulo Memória [Dinâmico]: top_n={top_n} aplicado ao gráfico (linhas originais={len(df_mem)} -> exibidas={len(df_for_chart)})."
            )

        try:
            module_data = {
                'tabela': df_mem.to_html(classes='table', index=False, float_format='%.2f'),
                'grafico': generate_multi_bar_chart(
                    df_for_chart,
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

        Retorna:
            ({'df_mem': DataFrame[Host, Min, Avg, Max]}, None) em caso de sucesso
            (None, 'mensagem de erro') em caso de falha
        """
        try:
            # 1) Perfis de chave ativos para 'memory'
            mem_key_profiles = (
                MetricKeyProfile.query
                .filter_by(metric_type='memory', is_active=True)
                .order_by(MetricKeyProfile.priority)
                .all()
            )
            if not mem_key_profiles:
                return None, (
                    "Nenhum perfil de coleta para 'memória' está ativo no sistema. "
                    "Configure na área de administração."
                )

            current_app.logger.debug(
                f"Módulo Memória [Dinâmico]: {len(mem_key_profiles)} perfis de chave encontrados."
            )
            for profile in mem_key_profiles:
                current_app.logger.debug(
                    f" - Perfil Prioridade {profile.priority}: "
                    f"Key='{profile.key_string}', Cálculo='{profile.calculation_type.name}'"
                )

            host_map = {h['hostid']: h['nome_visivel'] for h in all_hosts}
            host_ids = [h['hostid'] for h in all_hosts]

            # 2) Encontrar 1 item por host seguindo a ordem de prioridade dos perfis (lote por perfil)
            #    - Reduz drasticamente chamadas à API: em vez de 1 chamada por host+perfil, viram ~1 por perfil.
            items_to_fetch = []
            item_profile_map = {}   # itemid -> profile
            hosts_already_covered = set()

            for profile in mem_key_profiles:
                remaining_hosts = [hid for hid in host_ids if hid not in hosts_already_covered]
                if not remaining_hosts:
                    break

                current_app.logger.debug(
                    f"Módulo Memória [Dinâmico]: Buscando itens para {len(remaining_hosts)} hosts "
                    f"usando a chave '{profile.key_string}' (prioridade {profile.priority})."
                )
                # Busca todos os itens dessa key para os hosts restantes
                items = self.generator.get_items(remaining_hosts, profile.key_string, search_by_key=True)
                if not items:
                    continue

                # Para cada host, escolhe o primeiro item retornado
                chosen_by_host = {}
                for it in items:
                    hid = it.get('hostid')
                    if hid and hid not in chosen_by_host:
                        chosen_by_host[hid] = it

                for hid, item in chosen_by_host.items():
                    items_to_fetch.append(item)
                    item_profile_map[item['itemid']] = profile
                    hosts_already_covered.add(hid)
                    current_app.logger.debug(
                        f"SUCESSO: Item {item['itemid']} (host '{host_map.get(hid, hid)}') "
                        f"com perfil prioridade {profile.priority}."
                    )

            if not items_to_fetch:
                return None, (
                    "Não foi possível encontrar itens de monitoramento de memória em nenhum dos hosts "
                    "selecionados usando os perfis de coleta ativos."
                )

            current_app.logger.debug(
                f"Módulo Memória [Dinâmico]: {len(items_to_fetch)} itens selecionados "
                f"({len(hosts_already_covered)} hosts cobertos de {len(host_ids)})."
            )

            # 3) Histórico (trends) em lote para todos os itens
            item_ids = [item['itemid'] for item in items_to_fetch]
            current_app.logger.debug(
                f"Módulo Memória [Dinâmico]: Buscando histórico (trends) para {len(item_ids)} itens."
            )
            history = self.generator.get_trends(item_ids, period)  # aceita dict period (retrocompat)

            if not history:
                return None, "Não foi possível obter o histórico de dados de memória para os itens encontrados."

            # Agrupa trends por itemid para facilitar cálculo
            hist_by_item = {}
            for h in history:
                iid = h.get('itemid')
                if not iid:
                    continue
                hist_by_item.setdefault(iid, []).append(h)

            # 4) Processa dados aplicando o cálculo do perfil (DIRECT/INVERSE)
            mem_rows = []
            for item in items_to_fetch:
                hid = item.get('hostid')
                itemid = item.get('itemid')
                item_history = hist_by_item.get(itemid, [])

                if not item_history:
                    current_app.logger.warning(
                        f"Módulo Memória [Dinâmico]: Nenhum histórico para o item {itemid} "
                        f"do host {host_map.get(hid, hid)}."
                    )
                    continue

                # Converte e agrega
                try:
                    avg_values = [float(h['value_avg']) for h in item_history]
                    min_values = [float(h['value_min']) for h in item_history]
                    max_values = [float(h['value_max']) for h in item_history]
                except Exception as e:
                    current_app.logger.warning(
                        f"Módulo Memória [Dinâmico]: Histórico com valores inválidos para item {itemid} "
                        f"(host {host_map.get(hid, hid)}): {e}"
                    )
                    continue

                # Agregações
                avg_val = sum(avg_values) / len(avg_values) if avg_values else None
                min_val = min(min_values) if min_values else None
                max_val = max(max_values) if max_values else None

                profile = item_profile_map.get(itemid)
                if profile and profile.calculation_type == CalculationType.INVERSE:
                    # Inversão apropriada (com atenção aos extremos)
                    current_app.logger.debug(
                        f"Aplicando cálculo INVERSO para o item {itemid} "
                        f"(Host: {host_map.get(hid, hid)})"
                    )
                    if avg_val is not None:
                        avg_val = 100 - avg_val
                    if min_val is not None and max_val is not None:
                        tmp_min = 100 - max_val
                        max_val = 100 - min_val
                        min_val = tmp_min
                    else:
                        # fallback simplificado quando faltarem extremos
                        if min_val is not None:
                            min_val = 100 - min_val
                        if max_val is not None:
                            max_val = 100 - max_val

                mem_rows.append({
                    'Host': host_map.get(hid, f"Host ID {hid}"),
                    'Min': float(min_val) if min_val is not None else None,
                    'Avg': float(avg_val) if avg_val is not None else None,
                    'Max': float(max_val) if max_val is not None else None
                })

            if not mem_rows:
                return None, (
                    "Dados de histórico de memória foram encontrados, mas não puderam ser processados "
                    "(todas as linhas inválidas ou vazias)."
                )

            df_mem = pd.DataFrame(mem_rows, columns=['Host', 'Min', 'Avg', 'Max'])

            # Tipagem final + limpeza de linhas totalmente vazias em métricas
            for c in ['Min', 'Avg', 'Max']:
                df_mem[c] = pd.to_numeric(df_mem[c], errors='coerce')
            df_mem = df_mem.dropna(subset=['Min', 'Avg', 'Max'], how='all').reset_index(drop=True)

            current_app.logger.debug(
                f"Módulo Memória [Dinâmico]: DF final padronizado -> "
                f"linhas={len(df_mem)} | colunas={list(df_mem.columns)} | dtypes={dict(df_mem.dtypes)}"
            )

            return {'df_mem': df_mem}, None

        except Exception as e:
            current_app.logger.error(
                f"Módulo Memória [Dinâmico]: Exceção inesperada: {e}", exc_info=True
            )
            return None, "Ocorreu um erro interno inesperado ao processar os dados de memória."
