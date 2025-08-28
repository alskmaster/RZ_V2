# app/collectors/traffic_collector.py
import pandas as pd
from .base_collector import BaseCollector
# Importa a função de gerar gráfico do novo módulo
from app.charting import generate_multi_bar_chart
import re
from collections import defaultdict
import datetime as dt

class TrafficCollector(BaseCollector):
    """
    Plugin (Collector) que lida com os módulos de Tráfego de Entrada e Saída.
    """
    def collect(self, all_hosts, period):
        # 1. Extrai as interfaces do módulo, se existirem
        interfaces = self.module_config.get('interfaces', [])
        interfaces_key = '_'.join(sorted(interfaces)) if interfaces else 'all'
        
        # Cria uma chave de cache para evitar buscar os mesmos dados duas vezes
        traffic_cache_key = f"traffic_data_{interfaces_key}"

        # 2. Verifica se os dados já foram buscados e cacheados pelo gerador
        if traffic_cache_key not in self.generator.cached_data:
            self._update_status(f"Coletando dados de Tráfego para interfaces: {interfaces_key}...")
            # Se não, busca os dados e armazena no cache
            data, error_msg = self._collect_traffic_data(all_hosts, period, interfaces)
            if error_msg:
                return f"<p>Erro no módulo de Tráfego: {error_msg}</p>"
            self.generator.cached_data[traffic_cache_key] = data
        
        # Pega os dados do cache
        cached_traffic_data = self.generator.cached_data[traffic_cache_key]
        
        # 3. Decide qual DataFrame (Entrada ou Saída) e quais cores usar
        module_type = self.module_config.get('type')
        
        title_sufix = f' - Agregado ({", ".join(interfaces)})' if len(interfaces) > 1 else (f' - {interfaces[0]}' if interfaces else '')

        if module_type == 'traffic_in':
            df = cached_traffic_data['df_net_in']
            title = self.module_config.get('title') or f"Tráfego de Entrada (Mbps){title_sufix}"
            chart_title = 'Tráfego de Entrada (Mbps)'
            colors = ['#ffc266', '#ffa31a', '#e68a00']
        else:  # 'traffic_out'
            df = cached_traffic_data['df_net_out']
            title = self.module_config.get('title') or f"Tráfego de Saída (Mbps){title_sufix}"
            chart_title = 'Tráfego de Saída (Mbps)'
            colors = ['#85e085', '#33cc33', '#248f24']
        
        # 4. Prepara os dados e renderiza o template
        module_data = {
            'tabela': df.to_html(classes='table', index=False, float_format='%.4f'),
            'grafico': generate_multi_bar_chart(df, chart_title, 'Mbps', colors)
        }
        
        # Sobrescreve o título no config para passar o título dinâmico para o renderizador
        self.module_config['title'] = title
        return self.render('traffic', module_data)

    def _collect_traffic_data(self, all_hosts, period, interfaces):
        """
        Coleta dados de tráfego (Entrada e Saída) do Zabbix.
        Este método foi movido do services.py para cá.
        """
        host_ids = [h['hostid'] for h in all_hosts]
        host_map = {h['hostid']: h['nome_visivel'] for h in all_hosts}

        def get_traffic_data(key_filter):
            self._update_status(f"Buscando itens de tráfego: {key_filter}")
            traffic_items = self.generator.get_items(host_ids, key_filter, search_by_key=True)
            
            if interfaces:
                # Filtra os itens apenas para as interfaces selecionadas
                regex = f'.*({"|".join(re.escape(i) for i in interfaces)})'
                traffic_items = [item for item in traffic_items if re.search(regex, item['key_'])]

            if not traffic_items: return pd.DataFrame(), f"Nenhum item de tráfego '{key_filter}' encontrado para as interfaces selecionadas."
            
            self._update_status(f"Buscando tendências para {len(traffic_items)} itens de tráfego...")
            traffic_trends = self.generator.get_trends([item['itemid'] for item in traffic_items], period['start'], period['end'])
            
            if not traffic_trends: return pd.DataFrame(), None
            
            df = pd.DataFrame(traffic_trends)
            df[['value_min', 'value_avg', 'value_max']] = df[['value_min', 'value_avg', 'value_max']].astype(float)
            
            item_map = {item['itemid']: item['hostid'] for item in traffic_items}
            df['hostid'] = df['itemid'].map(item_map)
            df.dropna(subset=['hostid'], inplace=True)
            
            agg_functions = {'Min': ('value_min', 'sum'), 'Max': ('value_max', 'sum'), 'Avg': ('value_avg', 'sum')}
            df_agg = df.groupby('hostid').agg(**agg_functions).reset_index()
            
            for col in ['Min', 'Max', 'Avg']: df_agg[col] = df_agg[col] * 8 / (1024 * 1024)
            df_agg['Host'] = df_agg['hostid'].map(host_map)
            return df_agg, None
        
        df_net_in, error_in = get_traffic_data("net.if.in")
        df_net_out, error_out = get_traffic_data("net.if.out")
        
        if error_in and error_out: return None, f"{error_in} e {error_out}"
        if error_in and not df_net_out.empty: return None, error_in
        if error_out and not df_net_in.empty: return None, error_out
        
        return {'df_net_in': df_net_in, 'df_net_out': df_net_out}, None