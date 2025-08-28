ESTRUTURA DO SISTEMA

zabbix-reporter/
├── app/
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── availability_collector.py
│   │   ├── base_collector.py
│   │   ├── cpu_collector.py
│   │   ├── disk_collector.py
│   │   ├── html_collector.py
│   │   ├── inventory_collector.py
│   │   ├── kpi_collector.py
│   │   ├── latency_collector.py
│   │   ├── loss_collector.py
│   │   ├── mem_collector.py
│   │   ├── sla_collector.py
│   │   ├── top_hosts_collector.py
│   │   ├── top_problems_collector.py
│   │   └── traffic_collector.py
│   ├── admin/
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── auth/
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── main/
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── static/
│   │   └── gerar_form.js
│   ├── templates/
│   │   ├── admin/
│   │   │   ├── audit_log.html
│   │   │   ├── base.html
│   │   │   ├── client_form.html
│   │   │   ├── clients.html
│   │   │   ├── customize.html
│   │   │   ├── dashboard.html
│   │   │   ├── user_form.html
│   │   │   ├── users.html
│   │   │   └── vincular.html
│   │   ├── modules/
│   │   │   ├── cpu.html
│   │   │   ├── custom_html.html
│   │   │   ├── disk.html
│   │   │   ├── inventory.html
│   │   │   ├── kpi.html
│   │   │   ├── latency.html
│   │   │   ├── loss.html
│   │   │   ├── mem.html
│   │   │   ├── sla.html
│   │   │   ├── top_hosts.html
│   │   │   ├── top_problems.html
│   │   │   ├── traffic.html
│   │   ├── _MIOLO_BASE.html
│   │   ├── base.html
│   │   ├── form.html
│   │   ├── gerar_form.html
│   │   ├── history.html
│   │   └── login.html
│   ├── __init__.py        # A fábrica da aplicação
│   ├── charting.py
│   ├── models.py          # Modelos do banco de dados
│   ├── pdf_builder.py
│   ├── services.py        # O ReportGenerator "orquestrador"
│   ├── utils.py           # Funções auxiliares (ex: @admin_required)
│   └── zabbix_api.py
│
├── relatorios_gerados/
│   └── (Relatórios em .pdf são salvos aqui)
├── uploads/
│   └── (Logos e mídias são salvos aqui)
│
├── .env                 # Suas variáveis de ambiente (chaves, senhas)
├── config.py            # As classes de configuração
└── run.py               # O novo ponto de partida para rodar a app

PLANO DE MELHORIAS

CAT1: Performance e Eficiência (Otimizações Críticas)
-------------------------------------------------------------------
(PENDENTE) Otimizar a Geração de Tabelas HTML
-------------------------------------------------------------------
Problema: A geração da tabela HTML no sla_collector.py é feita manualmente, concatenando strings. Isso torna o código menos legível e mais propenso a erros, além de ser difícil de modificar.

Melhoria Proposta: Em vez de construir a tabela como uma string, a classe SlaCollector poderia passar os dados processados para um template Jinja2 específico para a tabela (templates/modules/_sla_table.html, por exemplo). Isso separaria a lógica de processamento dos dados da lógica de apresentação, tornando o código mais limpo e a manutenção mais fácil.

(PENDENTE) Refatorar a Lógica de Geração de Gráficos
    -------------------------------------------------------------------
        Problema: A função generate_chart está duplicada nos arquivos top_hosts_collector.py e top_problems_collector.py. Essa repetição de código dificulta a manutenção, pois qualquer mudança na lógica do gráfico precisa ser feita em dois lugares.

        Melhoria Proposta: Mover essa função para um novo módulo de utilitários, por exemplo, app/charting.py. Isso seguiria o princípio DRY (Don't Repeat Yourself) e tornaria o código mais organizado. Os coletores simplesmente importariam e utilizariam a função centralizada. A lógica de geração de gráficos no kpi_collector.py também poderia ser integrada a esse novo módulo para manter a consistência.

(REALIZADA) Agrupamento de Chamadas à API (Batch Requests):
    -------------------------------------------------------------------
        Ponto de Dor: No método obter_eventos_wrapper, você itera e faz uma chamada à API para cada triggerid. Se um cliente tiver 200 triggers, isso se torna 200 chamadas de API sequenciais, o que é extremamente lento.

        Melhoria: Modifique a função obter_eventos para aceitar uma lista completa de triggerids (ou hostids) em uma única chamada. A API do Zabbix é projetada para isso. Isso transformaria 200 chamadas em apenas 1, resultando em uma melhoria de performance drástica, especialmente no AvailabilityCollector.

(PENDENTE) Reforçar a Estratégia de Cache:
-------------------------------------------------------------------
Ponto de Dor: O cache atual é bom, mas funciona em um nível alto (ex: latency_loss_data). Se módulos diferentes precisarem de dados de base parecidos, mas não idênticos, a chamada pode ser refeita.

Melhoria: Implementar um cache de nível mais baixo, diretamente na função fazer_request_zabbix. Podemos criar um cache em memória (com um tempo de expiração curto, ex: 60 segundos) que armazena a resposta de uma chamada com base na sua url e body. Isso garante que qualquer chamada à API Zabbix exatamente igual dentro de um curto período de tempo não seja refeita, independentemente de qual módulo a solicitou.

(PENDENTE) Sistema de Fila para Tarefas em Background:  
-------------------------------------------------------------------
Ponto de Dor: O uso de threading é funcional, mas limitado. Se a aplicação for reiniciada, todas as gerações em andamento são perdidas. Ela também não escala bem se muitos usuários gerarem relatórios ao mesmo tempo.
Melhoria: Migrar o processo de geração para um sistema de fila dedicado, como Celery com Redis ou RabbitMQ.

Benefícios:
Persistência: As tarefas sobrevivem a reinicializações da aplicação.
Escalabilidade: Você pode ter "workers" separados rodando em outras máquinas apenas para processar relatórios.
Retentativas: Tarefas que falham (ex: Zabbix temporariamente offline) podem ser reexecutadas automaticamente.

-------------------------------------------------------------------

CAT2: Manutenibilidade e Qualidade do Código
-------------------------------------------------------------------
(REALIZADA) Refatorar o services.py:
-------------------------------------------------------------------
Ponto de Dor: O arquivo services.py é gigante. Ele tem responsabilidades demais: comunicação com Zabbix, lógica de negócio de todos os coletores, geração de gráficos, montagem de PDF, etc.

Melhoria: Divisão em arquivos menores e mais focados:

app/zabbix_api.py: Mova para cá as funções fazer_request_zabbix e obter_config_e_token_zabbix.

app/charting.py: Mova as funções _generate_chart e _generate_multi_bar_chart.

app/pdf_builder.py: Mova a lógica de montagem do PDF com PyPDF2.

Mova a Lógica de Coleta para os Coletores: Esta é a mudança mais importante. A lógica de coleta (ex: _collect_cpu_data) que hoje está no ReportGenerator deveria estar dentro do respectivo coletor (ex: CpuCollector). O ReportGenerator apenas orquestra, chamando cpu_collector.collect(), e o coletor é quem sabe como buscar e processar seus próprios dados. Isso segue o princípio de "Alta Coesão".

(REALIZADA) Configurar Dependências Externas:
-------------------------------------------------------------------
Ponto de Dor: O caminho para o wkhtmltoimage.exe está fixo no código (availability_collector.py). Isso quebra a aplicação em qualquer outro ambiente.

Melhoria: Mova este caminho para o arquivo config.py ou para o .env, permitindo que cada ambiente configure seu próprio caminho.

(PENDENTE) Adotar Tipagem Estática (Type Hinting):
-------------------------------------------------------------------
Ponto de Dor: O código não possui anotações de tipo.

Melhoria: Adicione type hints (ex: def get_hosts(self, groupids: list[str]) -> list[dict]:). Isso torna o código auto-documentado, mais fácil de entender e permite que ferramentas como mypy encontrem bugs antes mesmo de você rodar o código.

Categoria 3: Novas Funcionalidades (Evolução do Produto)

(PENDENTE) Acesso do Cliente - Gerar Relatório
-------------------------------------------------------------------
Oportunidade: Criar a Area do Clientes para ele ter acesso aos TEMPLATES e GRUPOS (HOSTS), que
ele poderá criar os relatórios já montados.

Melhoria: Fornecer ao cliente a possibilidade de ter o controle sobre seus relatórios.

(EM ANDAMENTO) Módulos Softdesk: [Patrick]
-------------------------------------------------------------------
Oportunidade: Conseguir Linkar os Problemas dos hosts do Zabbix com os Chamados do Softdesk.

Melhoria: Ter a visão completa dos chamados linkados com os problemas de forma clara e objetiva.

(REALIZADA) Templates de Relatório:
-------------------------------------------------------------------
Oportunidade: Hoje, o usuário precisa montar o layout do relatório toda vez.

Melhoria: Crie uma nova tabela ReportTemplate no banco de dados. Na página gerar_form.html, adicione botões de "Salvar layout como template" e "Carregar template". O usuário poderia montar um relatório complexo uma vez e apenas carregá-lo no futuro, mudando apenas o mês de referência.

(EM ANDAMENTO) Agendamento de Relatórios:
-------------------------------------------------------------------
Oportunidade: O processo ainda é manual.

Melhoria: Com os templates salvos, o próximo passo é permitir o agendamento. Um administrador poderia configurar um template para ser gerado automaticamente todo dia 1º do mês e enviado por e-mail para os usuários vinculados ao cliente. Isso transformaria a ferramenta de reativa para proativa.

(PENDENTE) Exportação para CSV/Excel:
-------------------------------------------------------------------
Oportunidade: PDF é ótimo para visualização, mas não para análise de dados.

Melhoria: Em cada módulo que gera uma tabela, adicione um pequeno ícone de "Exportar para CSV". A lógica seria simples: pegar o DataFrame Pandas que você já tem e usar o método df.to_csv() para entregar os dados brutos ao usuário.

(PENDENTE) Customização dos Módulos:
-------------------------------------------------------------------
Oportunidade: Ter a possibilidade de custamização das informação por módulos.

Melhoria: Em cada módulo que gera uma tabela, poderá ter as colunas selecionadas para ter visões diferenciadas. Assim poderiamos ter com o mesmo Módulo um mix de visões com dados obtidos desse módulos.

Ex: Módulo de Disponibilidade: 
+ Comparação com Mês Anterior.
+ Coluna de Melhoria ou Piora de SLA
+ Metas de SLA de forma individual por host em comparação com a SLA contratada como "Atingido" ou "Não Atingido"
+ Tempo de Indisponibilidade
+ % Total de Disponibilidade

(PENDENTE) Melhorar a Organização do CSS
-------------------------------------------------------------------
Problema: Há CSS embutido (<style>) em alguns templates de módulo, como o kpi.html. Essa prática é útil para a geração de PDFs, mas pode levar à duplicação de estilos se o mesmo CSS for necessário em outros módulos.

Melhoria Proposta: Criar um arquivo CSS dedicado para os estilos dos relatórios (static/css/report.css). Esse arquivo seria injetado ou referenciado apenas uma vez no template base do PDF (_MIOLO_BASE.html). Isso garantiria consistência visual e facilitaria a manutenção de estilos para todos os módulos do relatório.

(PENDENTE) Simplificar a Lógica dos Templates
-------------------------------------------------------------------
Problema: O template traffic.html contém lógica redundante, verificando a existência de data.grafico e data.tabela várias vezes. Essa duplicação de código não é necessária e pode ser confusa.

Melhoria Proposta: Simplificar o código do template, removendo as verificações e duplicações desnecessárias. O div principal que renderiza o conteúdo já é suficiente e a verificação de dados pode ser feita apenas uma vez, ou a renderização de cada componente pode ser feita em uma única linha.

(PENDENTE) Centralizar as Coletas da API do Zabbix
-------------------------------------------------------------------
Problema: Embora a lógica de coleta de tráfego (_collect_traffic_data) tenha sido movida para o traffic_collector.py, e a de disco/memória para seus respectivos coletores, as funções de chamada à API (get_items, get_trends, etc.) ainda residem na classe ReportGenerator (services.py). Isso sobrecarrega essa classe e mistura responsabilidades de orquestração com responsabilidades de comunicação de dados.

Melhoria Proposta: Criar uma classe dedicada à comunicação com o Zabbix, como ZabbixService. Todas as funções de chamada à API (get_hosts, get_items, get_trends, etc.) seriam movidas para essa classe, e o ReportGenerator apenas a utilizaria para buscar os dados. Essa separação de responsabilidades tornaria o sistema mais limpo, fácil de testar e escalar.
