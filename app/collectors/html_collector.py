# app/collectors/html_collector.py
from .base_collector import BaseCollector

class HtmlCollector(BaseCollector):
    """
    Plugin (Collector) para renderizar um bloco de HTML customizado.
    """
    def collect(self, all_hosts, period):
        self._update_status("Processando HTML customizado...")
        
        # Pega o conteúdo HTML salvo na configuração do módulo
        html_content = self.module_config.get('content', '')
        
        # Prepara os dados para o template
        module_data = {
            'content': html_content
        }

        # Renderiza o HTML final
        return self.render('custom_html', module_data)