# app/collectors/base_collector.py
from abc import ABC, abstractmethod
from flask import render_template

class BaseCollector(ABC):
    """
    Classe base abstrata (o 'Contrato') que todos os coletores de dados
    devem herdar. Garante que todos tenham a mesma estrutura.
    
    Qualquer classe que herdar de BaseCollector DEVE implementar o método collect().
    """
    def __init__(self, generator_instance, module_config):
        """
        O construtor armazena referências úteis para todos os plugins.
        """
        self.generator = generator_instance      # A instância principal do ReportGenerator
        self.module_config = module_config       # As configurações do módulo (título, newPage, etc.)
        self.config = generator_instance.config  # Configurações do Zabbix (URL, etc.)
        self.token = generator_instance.token    # Token da sessão Zabbix
        self.url = generator_instance.url        # URL da API Zabbix
        self.task_id = generator_instance.task_id # ID da tarefa para reportar status

    @abstractmethod
    def collect(self, all_hosts, period):
        """
        Este método DEVE ser implementado por cada classe filha.
        É aqui que a lógica de coleta de dados e renderização do HTML acontece.
        Ele deve retornar a string HTML final para o seu módulo.
        """
        pass

    def _update_status(self, message):
        """Método auxiliar para que cada plugin possa reportar seu progresso."""
        self.generator._update_status(message)
    
    def render(self, template_name, data):
        """
        Método auxiliar para renderizar o template HTML do módulo.
        Isso evita a repetição de código em cada plugin.
        """
        # --- MODIFICAÇÃO ABAIXO ---
        # Adicionamos 'system_config' ao contexto do template.
        # O self.generator (ReportGenerator) já possui essa informação.
        return render_template(
            f'modules/{template_name}.html',
            title=self.module_config.get('title'),
            data=data,
            new_page=self.module_config.get('newPage', False),
            system_config=self.generator.system_config
        )