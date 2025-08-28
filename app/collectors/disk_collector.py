# app/collectors/disk_collector.py
import pandas as pd
from .base_collector import BaseCollector
# Importa a função de gerar gráfico do novo módulo
from app.charting import generate_multi_bar_chart

class DiskCollector(BaseCollector):
    """
    Plugin (Collector) específico para coletar e renderizar dados de Disco.
    """
    def collect(self, all_hosts, period):
        # 1. Informa o status
        self._update_status("Coletando dados de Disco...")
        
        # 2. Coleta os dados brutos, chamando a lógica movida para este arquivo
        data, error_msg = self._collect_disk_data(all_hosts, period)
        if error_msg:
            return f"<p>Erro no módulo de Disco: {error_msg}</p>"

        df_disk = data['df_disk']
        
        # Renomeia as colunas para a tabela ficar mais clara no relatório
        df_disk_table = df_disk.rename(columns={
            'Host': 'Host', 
            'Filesystem': 'Filesystem', 
            'Min': 'Mínimo (%)', 
            'Max': 'Máximo (%)', 
            'Avg': 'Média (%)'
        })
        
        # 3. Prepara os dados para o template
        module_data = {
            'tabela': df_disk_table.to_html(classes='table', index=False, float_format='%.2f'),
            'grafico': generate_multi_bar_chart(
                df_disk, 
                'Uso de Disco (%) - Pior FS por Host', 
                'Uso de Disco (%)', 
                ['#d1b3ff', '#a366ff', '#7a1aff']
            )
        }

        # 4. Renderiza o HTML final
        return self.render('disk', module_data)

    def _collect_disk_data(self, all_hosts, period):
        """
        Coleta dados de disco do Zabbix.
        Este método foi movido do services.py para cá.
        """
        host_ids = [h['hostid'] for h in all_hosts]
        host_map = {h['hostid']: h['nome_visivel'] for h in all_hosts}
        disk_items = self.generator.get_items(host_ids, "vfs.fs.size", search_by_key=True)
        pused_items = [item for item in disk_items if ',pused' in item['key_']]
        if not pused_items: return None, "Nenhum item de Disco ('vfs.fs.size[,pused]') encontrado."
        disk_trends = self.generator.get_trends([item['itemid'] for item in pused_items], period['start'], period['end'])
        if not disk_trends: return {'df_disk': pd.DataFrame()}, None
        df_trends = pd.DataFrame(disk_trends)
        df_trends[['value_min', 'value_avg', 'value_max']] = df_trends[['value_min', 'value_avg', 'value_max']].astype(float)
        item_map = {item['itemid']: {'hostid': item['hostid'], 'name': item['name']} for item in pused_items}
        df_trends['hostid'] = df_trends['itemid'].map(lambda x: item_map.get(x, {}).get('hostid'))
        df_trends['fs_name'] = df_trends['itemid'].map(lambda x: item_map.get(x, {}).get('name'))
        df_trends.dropna(subset=['hostid'], inplace=True)
        agg_fs = df_trends.groupby(['hostid', 'fs_name']).agg(Avg=('value_avg', 'mean')).reset_index()
        idx = agg_fs.groupby(['hostid'])['Avg'].transform(max) == agg_fs['Avg']
        df_worst_fs = agg_fs[idx].drop_duplicates(subset=['hostid'])
        final_data = []
        for _, row in df_worst_fs.iterrows():
            host_trends = df_trends[(df_trends['hostid'] == row['hostid']) & (df_trends['fs_name'] == row['fs_name'])]
            if not host_trends.empty:
                final_data.append({'Host': host_map.get(row['hostid']), 'Filesystem': row['fs_name'], 'Min': host_trends['value_min'].mean(), 'Max': host_trends['value_max'].mean(), 'Avg': host_trends['value_avg'].mean()})
        return {'df_disk': pd.DataFrame(final_data)}, None