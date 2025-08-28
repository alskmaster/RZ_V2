# app/collectors/availability_collector.py
from .base_collector import BaseCollector

class AvailabilityCollector(BaseCollector):
    """
    Este Collector foi refatorado. Suas responsabilidades foram divididas em:
    - SlaCollector
    - KpiCollector
    - TopHostsCollector
    - TopProblemsCollector

    A lógica de coleta de dados foi centralizada no ReportGenerator (services.py)
    para otimizar as chamadas à API do Zabbix.

    Esta classe é mantida para evitar quebrar importações, mas não é mais
    utilizada diretamente pelos módulos de disponibilidade no COLLECTOR_MAP.
    """
    def collect(self, all_hosts, period, **kwargs):
        """
        Método de coleta que não deve mais ser chamado para os módulos refatorados.
        """
        # A lógica foi movida. Se este método for chamado, ele não faz nada.
        self._update_status("Aviso: O AvailabilityCollector foi chamado, mas está obsoleto.")
        return ""