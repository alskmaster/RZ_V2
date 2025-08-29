# app/services.py
import os
import json
import re
import datetime as dt
import threading
import traceback
import pandas as pd
from collections import defaultdict
from flask import render_template, current_app

from . import db
from .models import AuditLog, Report
from .zabbix_api import fazer_request_zabbix
from .pdf_builder import PDFBuilder

# Importação dos nossos Plugins (Collectors)
from .collectors.cpu_collector import CpuCollector
from .collectors.mem_collector import MemCollector
from .collectors.disk_collector import DiskCollector
from .collectors.traffic_collector import TrafficCollector
from .collectors.latency_collector import LatencyCollector
from .collectors.loss_collector import LossCollector
from .collectors.inventory_collector import InventoryCollector
from .collectors.html_collector import HtmlCollector
from .collectors.sla_collector import SlaCollector
from .collectors.kpi_collector import KpiCollector
from .collectors.top_hosts_collector import TopHostsCollector
from .collectors.top_problems_collector import TopProblemsCollector
from .collectors.stress_collector import StressCollector
from .collectors.wifi_collector import WiFiCollector   # <-- NOVO

# --- Registro de Plugins ---
COLLECTOR_MAP = {
    'cpu': CpuCollector,
    'mem': MemCollector,
    'disk': DiskCollector,
    'traffic_in': TrafficCollector,
    'traffic_out': TrafficCollector,
    'latency': LatencyCollector,
    'loss': LossCollector,
    'inventory': InventoryCollector,
    'html': HtmlCollector,
    'kpi': KpiCollector,
    'sla': SlaCollector,
    'top_hosts': TopHostsCollector,
    'top_problems': TopProblemsCollector,
    'stress': StressCollector,
    'wifi': WiFiCollector,    # <-- NOVO
}

# --- Gerenciador de Tarefas e Auditoria ---
REPORT_GENERATION_TASKS = {}
TASK_LOCK = threading.Lock()

def update_status(task_id, message):
    with TASK_LOCK:
        if task_id in REPORT_GENERATION_TASKS:
            REPORT_GENERATION_TASKS[task_id]['status'] = message
    try:
        current_app.logger.info(f"TASK {task_id}: {message}")
    except Exception:
        pass


class AuditService:
    @staticmethod
    def log(action, user=None):
        from flask_login import current_user
        log_user = user or (current_user if current_user.is_authenticated else None)
        username = log_user.username if log_user else "Anonymous"
        user_id = log_user.id if log_user else None
        try:
            new_log = AuditLog(user_id=user_id, username=username, action=action)
            db.session.add(new_log)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Falha ao salvar log de auditoria: {e}")


class ReportGenerator:
    def __init__(self, config, task_id):
        self.config = config
        self.token = config.get('ZABBIX_TOKEN')
        self.url = config.get('ZABBIX_URL')
        self.task_id = task_id
        self.client = None
        self.system_config = None
        self.cached_data = {}
        if not self.token or not self.url:
            raise ValueError("Configuração do Zabbix não encontrada ou token inválido.")

    def _update_status(self, message):
        update_status(self.task_id, message)

    # -------------------- SLA Helper (resiliente) --------------------
    def _get_client_sla_contract(self):
        """
        Tenta obter a meta de SLA do cliente de forma resiliente.
        - Procura por atributos comuns no objeto Client (futuro-compatível).
        - Caso não exista, tenta fallback em system_config (chave DEFAULT_SLA_CONTRACT se disponível).
        - Se nada for encontrado, retorna None e loga aviso.
        """
        try:
            current_app.logger.debug(f"[ReportGenerator] Buscando SLA do cliente id={getattr(self.client, 'id', 'N/A')}")
            for attr in ("sla_contract", "sla", "sla_policy", "sla_plan", "sla_goal"):
                val = getattr(self.client, attr, None)
                if val is not None:
                    try:
                        fval = float(val)
                        current_app.logger.debug(f"[ReportGenerator] SLA encontrado em Client.{attr} = {fval}")
                        return fval
                    except Exception:
                        current_app.logger.debug(f"[ReportGenerator] SLA encontrado em Client.{attr} (não numérico): {val}")
                        return val
        except Exception as e:
            current_app.logger.warning(f"[ReportGenerator] Falha ao inspecionar SLA no Client: {e}", exc_info=True)

        # Fallback: system_config pode ser objeto ORM ou dict
        fallback = None
        try:
            if isinstance(self.system_config, dict):
                fallback = self.system_config.get("DEFAULT_SLA_CONTRACT")
            else:
                fallback = getattr(self.system_config, "DEFAULT_SLA_CONTRACT", None)
        except Exception as e:
            current_app.logger.debug(f"[ReportGenerator] Erro ao consultar fallback de SLA em system_config: {e}")

        if fallback is not None:
            current_app.logger.debug(f"[ReportGenerator] Usando fallback DEFAULT_SLA_CONTRACT = {fallback}")
            try:
                return float(fallback)
            except Exception:
                return fallback

        current_app.logger.warning("[ReportGenerator] Nenhuma meta de SLA definida para o cliente; prosseguindo sem meta.")
        return None
    # ----------------------------------------------------------------

    def generate(self, client, ref_month_str, system_config, author, report_layout_json):
        """Gera o relatório com base no layout configurado (JSON)."""
        self.client = client
        self.system_config = system_config
        self.cached_data = {}

        self._update_status("Iniciando geração do relatório…")

        # --- Período de referência ---
        try:
            ref_date = dt.datetime.strptime(f'{ref_month_str}-01', '%Y-%m-%d')
        except ValueError:
            return None, "Formato de mês de referência inválido. Use YYYY-MM."
        start_date = ref_date.replace(day=1, hour=0, minute=0, second=0)
        end_date = (start_date.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(seconds=1)
        period = {'start': int(start_date.timestamp()), 'end': int(end_date.timestamp())}
        current_app.logger.debug(f"[ReportGenerator.generate] período={period} ref={ref_month_str}")

        # --- Grupos do cliente (RELACIONAMENTO DINÂMICO) ---
        try:
            groups_rel = client.zabbix_groups.all() if hasattr(client.zabbix_groups, "all") else client.zabbix_groups
            group_ids = [g.group_id for g in groups_rel if getattr(g, "group_id", None)]
        except Exception as e:
            current_app.logger.error(f"[ReportGenerator.generate] Falha ao obter grupos do cliente {client.id}: {e}", exc_info=True)
            group_ids = []

        current_app.logger.debug(f"[ReportGenerator.generate] client_id={client.id} group_ids={group_ids}")

        if not group_ids:
            return None, f"O cliente '{client.name}' não possui Grupos Zabbix associados."

        # --- Hosts do cliente ---
        self._update_status("Coletando hosts do cliente...")
        all_hosts = self.get_hosts(group_ids)
        if not all_hosts:
            return None, f"Nenhum host encontrado para os grupos Zabbix do cliente {client.name}."
        self.cached_data['all_hosts'] = all_hosts
        current_app.logger.debug(f"[ReportGenerator.generate] hosts_carregados={len(all_hosts)}")

        # --- Layout solicitado ---
        try:
            report_layout = json.loads(report_layout_json) if isinstance(report_layout_json, str) else report_layout_json
        except Exception as e:
            current_app.logger.error(f"[ReportGenerator.generate] Layout JSON inválido: {e}", exc_info=True)
            return None, "Layout inválido (JSON)."

        availability_data_cache = None
        sla_prev_month_df = None

        availability_module_types = {'sla', 'kpi', 'top_hosts', 'top_problems', 'stress'}

        final_html_parts = []

        # Pré-coleta de disponibilidade (SLA/KPI/Top)
        if any(mod.get('type') in availability_module_types for mod in (report_layout or [])):
            self._update_status("Coletando dados de Disponibilidade (SLA)…")
            sla_contract = self._get_client_sla_contract()
            availability_data_cache, error_msg = self._collect_availability_data(all_hosts, period, sla_contract)
            if error_msg:
                current_app.logger.warning(f"[ReportGenerator.generate] Erro SLA primário: {error_msg}")
                final_html_parts.append(f"<p>Erro crítico ao coletar dados de disponibilidade: {error_msg}</p>")
                availability_data_cache = {}

        # Mês anterior para SLA comparativo
        sla_module_config = next((mod for mod in (report_layout or []) if mod.get('type') == 'sla'), None)
        if sla_module_config and availability_data_cache:
            custom_options = sla_module_config.get('custom_options', {})
            if custom_options.get('compare_to_previous_month'):
                self._update_status("Coletando dados do mês anterior para comparação de SLA…")
                prev_ref_date = ref_date - dt.timedelta(days=1)
                prev_month_start = prev_ref_date.replace(day=1)
                prev_month_end = (prev_month_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(seconds=1)
                prev_period = {'start': int(prev_month_start.timestamp()), 'end': int(prev_month_end.timestamp())}

                sla_contract = self._get_client_sla_contract()
                prev_data, prev_error = self._collect_availability_data(all_hosts, prev_period, sla_contract, trends_only=True)
                if prev_error:
                    self._update_status(f"Aviso: Falha ao coletar dados do mês anterior: {prev_error}")
                elif prev_data and 'df_sla_problems' in prev_data:
                    sla_prev_month_df = prev_data['df_sla_problems'].rename(columns={'SLA (%)': 'SLA_anterior'})
                    self.cached_data['prev_month_sla_df'] = prev_data['df_sla_problems']

        # Montagem dos módulos
        for module_config in (report_layout or []):
            module_type = module_config.get('type')
            collector_class = COLLECTOR_MAP.get(module_type)
            if not collector_class:
                self._update_status(f"Aviso: Nenhum plugin encontrado para o tipo '{module_type}'.")
                continue

            try:
                collector_instance = collector_class(self, module_config)
                html_part = ""
                if module_type in availability_module_types:
                    if availability_data_cache:
                        if module_type == 'sla':
                            html_part = collector_instance.collect(all_hosts, period, availability_data_cache, df_prev_month=sla_prev_month_df)
                        else:
                            html_part = collector_instance.collect(all_hosts, period, availability_data_cache)
                    else:
                        html_part = "<p>Dados de disponibilidade indisponíveis para este módulo.</p>"
                else:
                    html_part = collector_instance.collect(all_hosts, period)

                final_html_parts.append(html_part)
            except Exception as e:
                current_app.logger.error(f"Erro ao executar o plugin '{module_type}': {e}", exc_info=True)
                final_html_parts.append(f"<p>Erro crítico ao processar módulo '{module_type}'.</p>")

        # Miolo + PDF
        dados_gerais = {
            'group_name': client.name,
            'periodo_referencia': start_date.strftime('%B de %Y').capitalize(),
            'data_emissao': dt.datetime.now().strftime('%d/%m/%Y'),
            'report_content': "".join(final_html_parts)
        }
        miolo_html = render_template('_MIOLO_BASE.html', **dados_gerais, modules={'pandas': pd})

        self._update_status("Montando o relatório final…")

        pdf_builder = PDFBuilder(self.task_id)
        error = pdf_builder.add_cover_page(system_config.report_cover_path)
        if error:
            return None, error
        error = pdf_builder.add_miolo_from_html(miolo_html)
        if error:
            return None, error
        error = pdf_builder.add_final_page(system_config.report_final_page_path)
        if error:
            return None, error

        pdf_filename = f'Relatorio_Custom_{client.name.replace(" ", "_")}_{ref_month_str}_{os.urandom(4).hex()}.pdf'
        pdf_path = os.path.join(current_app.config['GENERATED_REPORTS_FOLDER'], pdf_filename)

        final_file_path = pdf_builder.save_and_cleanup(pdf_path)

        report_record = Report(
            filename=pdf_filename,
            file_path=pdf_path,
            reference_month=ref_month_str,
            user_id=author.id,
            client_id=client.id,
            report_type='custom'
        )
        db.session.add(report_record)
        db.session.commit()
        AuditService.log(f"Gerou relatório customizado para '{client.name}' referente a {ref_month_str}", user=author)
        return pdf_path, None

    # -------------------- Bloco de coleta / utilidades --------------------

    def _collect_availability_data(self, all_hosts, period, sla_goal, trends_only=False):
        if sla_goal is None:
            current_app.logger.debug("[Availability] Nenhuma meta de SLA definida; calculando disponibilidade sem metas.")

        all_host_ids = [h['hostid'] for h in all_hosts]

        ping_items = self.get_items(all_host_ids, 'icmpping', search_by_key=True)
        if not ping_items:
            return None, "Nenhum item de monitoramento de PING ('icmpping') encontrado."

        hosts_with_ping_ids = {item['hostid'] for item in ping_items}
        hosts_for_sla = [host for host in all_hosts if host['hostid'] in hosts_with_ping_ids]
        if not hosts_for_sla:
            return None, "Nenhum dos hosts neste grupo tem um item de PING para calcular o SLA."

        ping_trigger_ids = list({t['triggerid'] for item in ping_items for t in item.get('triggers', [])})
        if not ping_trigger_ids:
            return None, "Nenhum gatilho (trigger) de PING encontrado para os itens deste grupo."

        ping_events = self.obter_eventos_wrapper(ping_trigger_ids, period, 'objectids')
        if ping_events is None:
            return None, "Falha na coleta de eventos de PING."

        ping_problems = [
            p for p in ping_events
            if p.get('source') == '0' and p.get('object') == '0' and p.get('value') == '1'
        ]
        correlated_ping_problems = self._correlate_problems(ping_problems, ping_events)
        df_sla = pd.DataFrame(self._calculate_sla(correlated_ping_problems, hosts_for_sla, period))

        if trends_only:
            return {'df_sla_problems': df_sla}, None

        all_group_events = self.obter_eventos_wrapper(all_host_ids, period, 'hostids')
        if all_group_events is None:
            return None, "Falha na coleta de eventos gerais do grupo."

        all_problems = [
            p for p in all_group_events
            if p.get('source') == '0' and p.get('object') == '0' and p.get('value') == '1'
        ]
        df_top_incidents = self._count_problems_by_host(all_problems, all_hosts)

        avg_sla = df_sla['SLA (%)'].mean() if not df_sla.empty else 100.0
        principal_ofensor = df_top_incidents.iloc[0]['Host'] if not df_top_incidents.empty else "Nenhum"

        self._update_status("Calculando tendências de KPIs…")
        ref_date = dt.datetime.fromtimestamp(period['start'])
        prev_ref_date = ref_date - dt.timedelta(days=1)
        prev_month_start = prev_ref_date.replace(day=1)
        prev_month_end = (prev_month_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(seconds=1)
        prev_period = {'start': int(prev_month_start.timestamp()), 'end': int(prev_month_end.timestamp())}

        prev_ping_events = self.obter_eventos_wrapper(ping_trigger_ids, prev_period, 'objectids')
        prev_avg_sla = 100.0
        if prev_ping_events:
            prev_ping_problems = [
                p for p in prev_ping_events
                if p.get('source') == '0' and p.get('object') == '0' and p.get('value') == '1'
            ]
            prev_correlated = self._correlate_problems(prev_ping_problems, prev_ping_events)
            prev_df_sla = pd.DataFrame(self._calculate_sla(prev_correlated, hosts_for_sla, prev_period))
            if not prev_df_sla.empty:
                prev_avg_sla = prev_df_sla['SLA (%)'].mean()

        prev_all_group_events = self.obter_eventos_wrapper(all_host_ids, prev_period, 'hostids')
        prev_all_problems_count = 0
        if prev_all_group_events:
            prev_all_problems_count = len([
                p for p in prev_all_group_events
                if p.get('source') == '0' and p.get('object') == '0' and p.get('value') == '1'
            ])

        sla_trend = 'stable'
        if avg_sla > prev_avg_sla:
            sla_trend = 'up'
        elif avg_sla < prev_avg_sla:
            sla_trend = 'down'

        incidents_trend = 'stable'
        if len(all_problems) < prev_all_problems_count:
            incidents_trend = 'up'
        elif len(all_problems) > prev_all_problems_count:
            incidents_trend = 'down'

        # KPI principal com/sem meta de SLA
        if sla_goal is not None:
            sublabel = f"Meta: {f'{float(sla_goal):.2f}'.replace('.', ',')}%"
            status = "atingido" if avg_sla >= float(sla_goal) else "nao-atingido"
        else:
            sublabel = "Meta: não definida"
            status = "indefinido"

        kpis_data = [
            {
                'label': f"Média de SLA ({len(hosts_for_sla)} Hosts)",
                'value': f"{avg_sla:.2f}".replace('.', ',') + '%',
                'sublabel': sublabel,
                'status': status,
                'trend': sla_trend
            },
            {
                'label': "Hosts com SLA < 99.9%",
                'value': df_sla[df_sla['SLA (%)'] < 99.9].shape[0],
                'sublabel': f"De um total de {len(hosts_for_sla)} hosts",
                'status': "critico" if df_sla[df_sla['SLA (%)'] < 99.9].shape[0] > 0 else "ok",
                'trend': None
            },
            {
                'label': "Total de Incidentes",
                'value': len(all_problems),
                'sublabel': "Eventos de problema registrados",
                'status': "info",
                'trend': incidents_trend
            },
            {
                'label': "Principal Ofensor",
                'value': principal_ofensor,
                'sublabel': "Host com mais incidentes",
                'status': "info",
                'trend': None
            }
        ]

        self._update_status("Classificando incidentes por severidade…")
        severity_map = {
            '0': 'Não Classificado', '1': 'Informação', '2': 'Atenção',
            '3': 'Média', '4': 'Alta', '5': 'Desastre'
        }
        severity_counts = defaultdict(int)
        for problem in all_problems:
            severity_level = problem.get('severity', '0')
            severity_name = severity_map.get(severity_level, 'Desconhecido')
            severity_counts[severity_name] += 1

        return {
            'kpis': kpis_data,
            'df_sla_problems': df_sla,
            'df_top_incidents': df_top_incidents,
            'severity_counts': dict(severity_counts)
        }, None

    def _normalize_string(self, s):
        return re.sub(r'\s+', ' ', str(s).replace('\n', ' ').replace('\r', ' ')).strip()

    def get_hosts(self, groupids):
        self._update_status("Coletando dados de hosts…")
        body = {
            'jsonrpc': '2.0',
            'method': 'host.get',
            'params': {
                'groupids': groupids,
                'selectInterfaces': ['ip'],
                'output': ['hostid', 'host', 'name']
            },
            'auth': self.token,
            'id': 1
        }
        resposta = fazer_request_zabbix(body, self.url)
        if not isinstance(resposta, list):
            return []
        return sorted(
            [
                {
                    'hostid': item['hostid'],
                    'hostname': item['host'],
                    'nome_visivel': self._normalize_string(item['name']),
                    'ip0': item['interfaces'][0].get('ip', 'N/A') if item.get('interfaces') else 'N/A'
                }
                for item in resposta
            ],
            key=lambda x: x['nome_visivel']
        )

    def get_items(self, hostids, filter_key, search_by_key=False, exact_key_search=False):
        self._update_status(f"Buscando itens com filtro '{filter_key}'…")
        params = {
            'output': ['itemid', 'hostid', 'name', 'key_'],
            'hostids': hostids,
            'sortfield': 'name'
        }
        if search_by_key:
            search_dict = {'key_': filter_key if isinstance(filter_key, list) else [filter_key]}
            if exact_key_search:
                params['filter'] = search_dict
            else:
                params['search'] = search_dict
            params['selectTriggers'] = 'extend'
        else:
            params['search'] = {'name': filter_key}
        body = {
            'jsonrpc': '2.0',
            'method': 'item.get',
            'params': params,
            'auth': self.token,
            'id': 1
        }
        return fazer_request_zabbix(body, self.url) or []

    # === AQUI: retrocompat para period dict ===
    def get_trends(self, itemids, time_from=None, time_till=None):
        """
        Aceita:
          - get_trends(itemids, time_from:int, time_till:int)
          - get_trends(itemids, period:dict com 'start'/'end')  [retrocompat]
        """
        # Se o 2º argumento for um dict, tratamos como período
        if isinstance(time_from, dict) and time_till is None:
            period = time_from
            time_from = int(period.get('start'))
            time_till = int(period.get('end'))
            current_app.logger.debug("[ReportGenerator.get_trends] Back-compat: recebido dict 'period'.")

        if time_from is None or time_till is None:
            raise TypeError("get_trends() requer time_from e time_till, ou um dict 'period' como 2º argumento.")

        self._update_status(f"Buscando tendências para {len(itemids)} itens…")
        body = {
            'jsonrpc': '2.0',
            'method': 'trend.get',
            'params': {
                'output': ['itemid', 'clock', 'num', 'value_min', 'value_avg', 'value_max'],
                'itemids': itemids,
                'time_from': int(time_from),
                'time_till': int(time_till)
            },
            'auth': self.token,
            'id': 1
        }
        trends = fazer_request_zabbix(body, self.url)
        if not isinstance(trends, list):
            current_app.logger.error(f"Falha ao buscar trends para {len(itemids)} itens. Resposta inválida do Zabbix.")
            return []
        return trends

    def obter_eventos(self, object_ids, periodo, id_type='hostids', max_depth=3):
        time_from, time_till = periodo['start'], periodo['end']
        if max_depth <= 0:
            current_app.logger.error("ERRO: Limite de profundidade de recursão atingido para obter eventos.")
            return None
        params = {
            'output': 'extend',
            'selectHosts': ['hostid'],
            'time_from': time_from,
            'time_till': time_till,
            id_type: object_ids,
            'sortfield': ["eventid"],
            'sortorder': "ASC",
            'select_acknowledges': 'extend'
        }
        body = {'jsonrpc': '2.0', 'method': 'event.get', 'params': params, 'auth': self.token, 'id': 1}
        resposta = fazer_request_zabbix(body, self.url, allow_retry=False)
        if isinstance(resposta, dict) and 'error' in resposta:
            self._update_status("Consulta pesada detectada, quebrando o período…")
            mid_point = time_from + (time_till - time_from) // 2
            periodo1 = {'start': time_from, 'end': mid_point}
            periodo2 = {'start': mid_point + 1, 'end': time_till}
            eventos1 = self.obter_eventos(object_ids, periodo1, id_type, max_depth - 1)
            if eventos1 is None:
                return None
            eventos2 = self.obter_eventos(object_ids, periodo2, id_type, max_depth - 1)
            if eventos2 is None:
                return None
            return eventos1 + eventos2
        return resposta

    def obter_eventos_wrapper(self, object_ids, periodo, id_type='objectids'):
        if not object_ids:
            return []
        self._update_status(f"Processando eventos para {len(object_ids)} objetos em uma única chamada…")
        all_events = self.obter_eventos(object_ids, periodo, id_type)
        if all_events is None:
            current_app.logger.critical("Falha crítica ao coletar eventos para os IDs. Abortando.")
            return None
        return sorted(all_events, key=lambda x: int(x['clock']))

    def _process_trends(self, trends, items, host_map, unit_conversion_factor=1, is_pavailable=False, agg_method='mean'):
        if not isinstance(trends, list) or not trends:
            return pd.DataFrame(columns=['Host', 'Min', 'Max', 'Avg'])
        df = pd.DataFrame(trends)
        df[['value_min', 'value_avg', 'value_max']] = df[['value_min', 'value_avg', 'value_max']].astype(float)
        item_to_host_map = {item['itemid']: item['hostid'] for item in items}
        df['hostid'] = df['itemid'].map(item_to_host_map)
        agg_functions = {
            'Min': ('value_min', agg_method),
            'Max': ('value_max', agg_method),
            'Avg': ('value_avg', agg_method)
        }
        agg_results = df.groupby('hostid').agg(**agg_functions).reset_index()
        if is_pavailable:
            agg_results['Min_old'], agg_results['Max_old'] = agg_results['Min'], agg_results['Max']
            agg_results['Min'], agg_results['Max'] = 100 - agg_results['Max_old'], 100 - agg_results['Min_old']
            agg_results['Avg'] = 100 - agg_results['Avg']
            agg_results.drop(columns=['Min_old', 'Max_old'], inplace=True)
        for col in ['Min', 'Max', 'Avg']:
            agg_results[col] *= unit_conversion_factor
        agg_results['Host'] = agg_results['hostid'].map(host_map)
        return agg_results[['Host', 'Min', 'Max', 'Avg']]

    def _correlate_problems(self, problems, all_events):
        correlated = []
        resolution_events = {
            p['eventid']: p for p in all_events
            if p.get('source') == '0' and p.get('value') == '0'
        }
        for problem in problems:
            r_eventid = problem.get('r_eventid', '0')
            duration = dt.timedelta(seconds=0)
            if r_eventid != '0' and r_eventid in resolution_events:
                res_event = resolution_events[r_eventid]
                if int(res_event['clock']) >= int(problem['clock']):
                    duration = dt.timedelta(seconds=(int(res_event['clock']) - int(problem['clock'])))
            correlated.append({
                'hostid': problem.get('hosts')[0].get('hostid') if problem.get('hosts') else None,
                'duration_seconds': duration.total_seconds()
            })
        return correlated

    def _calculate_sla(self, correlated_problems, all_hosts, period):
        period_seconds = period['end'] - period['start']
        if period_seconds <= 0:
            return []
        sla_by_host = {h['hostid']: {'downtime': 0} for h in all_hosts}
        for problem in correlated_problems:
            if problem['hostid'] in sla_by_host:
                sla_by_host[problem['hostid']]['downtime'] += problem['duration_seconds']
        final_results = []
        for host in all_hosts:
            downtime = sla_by_host.get(host['hostid'], {}).get('downtime', 0)
            sla_percent = max(0, 100.0 - (downtime / period_seconds * 100.0))
            final_results.append({
                'Host': host['nome_visivel'],
                'IP': host['ip0'],
                'Tempo Indisponível': str(dt.timedelta(seconds=int(downtime))),
                'SLA (%)': sla_percent
            })
        return final_results

    def _count_problems_by_host(self, problems, all_hosts):
        host_map = {h['hostid']: h['nome_visivel'] for h in all_hosts}
        problem_data = []
        for p in problems:
            if p.get('object') == '0' and p.get('hosts'):
                host_name = host_map.get(p['hosts'][0]['hostid'])
                if host_name:
                    problem_data.append({
                        'Host': host_name,
                        'Problema': self._normalize_string(p['name']),
                        'Ocorrências': 1,
                        'clock': p['clock']
                    })

        if not problem_data:
            return pd.DataFrame(columns=['Host', 'Problema', 'Ocorrências', 'clock'])

        df = pd.DataFrame(problem_data)
        df_grouped = df.groupby(['Host', 'Problema', 'clock']).size().reset_index(name='Ocorrências')
        return df_grouped.sort_values(by=['clock', 'Host'], ascending=True)

    def shared_collect_latency_and_loss(self, all_hosts, period):
        host_ids = [h['hostid'] for h in all_hosts]
        host_map = {h['hostid']: h['nome_visivel'] for h in all_hosts}

        lat_items = self.get_items(host_ids, 'icmppingsec', search_by_key=True)
        df_lat = pd.DataFrame()
        if lat_items:
            lat_trends = self.get_trends([item['itemid'] for item in lat_items], period['start'], period['end'])
            df_lat = self._process_trends(lat_trends, lat_items, host_map, unit_conversion_factor=1000)

        loss_items = self.get_items(host_ids, 'icmppingloss', search_by_key=True)
        df_loss = pd.DataFrame()
        if loss_items:
            loss_trends = self.get_trends([item['itemid'] for item in loss_items], period['start'], period['end'])
            df_loss = self._process_trends(loss_trends, loss_items, host_map)

        if df_lat.empty and df_loss.empty:
            return None, "Nenhum item de Latência ('icmppingsec') ou Perda ('icmppingloss') encontrado."

        return {'df_lat': df_lat, 'df_loss': df_loss}, None
