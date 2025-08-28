# app/collectors/sla_collector.py
import pandas as pd
from .base_collector import BaseCollector

class SlaCollector(BaseCollector):
    """
    Collector dedicado a renderizar a tabela de análise de SLA.
    Recebe os dados já processados do ReportGenerator.
    """
    def collect(self, all_hosts, period, availability_data, df_prev_month=None):
        """
        Renderiza o módulo de tabela de SLA.
        :param all_hosts: Lista de todos os hosts (não utilizado diretamente, mas parte do contrato).
        :param period: Dicionário do período (não utilizado diretamente, mas parte do contrato).
        :param availability_data: Dicionário com os dataframes já processados.
        :param df_prev_month: DataFrame opcional com os dados de SLA do mês anterior.
        """
        self._update_status("Renderizando tabela de Análise de Disponibilidade (SLA)...")

        df_sla_problems = availability_data.get('df_sla_problems', pd.DataFrame()).copy()
        if df_sla_problems.empty:
            return self.render('sla', {'summary_html': '', 'tabela_sla_problemas': '<p><i>Nenhum dado de disponibilidade para exibir.</i></p>'})

        custom_options = self.module_config.get('custom_options', {})
        sla_goal = self.generator.client.sla_contract
        
        columns_to_show_display = ['Host']
        
        if custom_options.get('show_ip'):
            columns_to_show_display.append('IP')

        current_sla_col = 'SLA (%)'
        if custom_options.get('compare_to_previous_month') and df_prev_month is not None and not df_prev_month.empty:
            df_sla_problems = df_sla_problems.merge(df_prev_month[['Host', 'SLA_anterior']], on='Host', how='left').fillna({'SLA_anterior': 100.0})
            df_sla_problems.rename(columns={'SLA (%)': 'SLA Atual (%)'}, inplace=True)
            current_sla_col = 'SLA Atual (%)'
            
            if custom_options.get('show_previous_sla'):
                columns_to_show_display.append('SLA_anterior')
            if custom_options.get('show_improvement'):
                df_sla_problems['Melhoria/Piora'] = df_sla_problems[current_sla_col] - df_sla_problems['SLA_anterior']
                columns_to_show_display.append('Melhoria/Piora')
            
        columns_to_show_display.append(current_sla_col)
        
        if custom_options.get('show_downtime'):
            columns_to_show_display.append('Tempo Indisponível')

        if custom_options.get('show_goal'):
            df_sla_problems['Meta'] = df_sla_problems[current_sla_col].apply(lambda x: "Atingido" if x >= sla_goal else "Não Atingido")
            columns_to_show_display.append('Meta')
        
        df_sla_problems = df_sla_problems[columns_to_show_display]
        
        hosts_failed = df_sla_problems[df_sla_problems[current_sla_col] < 100].shape[0] if current_sla_col in df_sla_problems.columns else 0
        total_hosts_count = len(self.generator.cached_data.get('all_hosts', []))
        
        summary_html = ""
        if not custom_options.get('hide_summary'):
            alert_class = 'alert-success' if hosts_failed == 0 else 'alert-warning'
            summary_html = f'<div class="alert {alert_class} mt-3" role="alert">'
            summary_html += f'<p>Atenção: {hosts_failed} de {total_hosts_count} hosts analisados não atingiram 100% de disponibilidade.</p>'
            summary_html += '</div>'

        col_widths = {
            'Host': '32%', 'IP': '12%', 'SLA_anterior': 'auto', 'SLA (%)': 'auto',
            'SLA Atual (%)': 'auto', 'Melhoria/Piora': 'auto', 'Tempo Indisponível': 'auto', 'Meta': 'auto',
        }

        tabela_html = '<table class="table"><thead><tr>'
        for col in df_sla_problems.columns:
            col_name = 'SLA Mês Anterior (%)' if col == 'SLA_anterior' else col
            width = col_widths.get(col, 'auto')
            tabela_html += f'<th style="width: {width};">{col_name}</th>'
        tabela_html += '</tr></thead><tbody>'
        for _, row in df_sla_problems.iterrows():
            tabela_html += f"<tr>"
            for col in df_sla_problems.columns:
                value = row[col]
                original_value = value
                if isinstance(value, float):
                    if col == 'Melhoria/Piora':
                        value = f'{value:+.2f}%'.replace('.', ',') if value != 0 else f'{value:.2f}%'.replace('.', ',')
                    else:
                        value = f'{value:.2f}'.replace('.', ',')
                
                if col == 'Host' and len(str(value)) > 40:
                    value = str(value)[:30] + '...'
                
                tabela_html += f"<td title='{original_value}'>{value}</td>"
            tabela_html += "</tr>"
        tabela_html += '</tbody></table>'
        
        module_data = {
            'summary_html': summary_html,
            'tabela_sla_problemas': tabela_html,
        }
        return self.render('sla', module_data)