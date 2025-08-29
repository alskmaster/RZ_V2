document.addEventListener('DOMContentLoaded', function () {
    // --- ELEMENTOS DO DOM ---
    const clientSelect = document.getElementById('client_id');
    const monthInput = document.getElementById('mes_ref');
    const moduleTypeSelect = document.getElementById('module-type-select');
    const moduleTitleInput = document.getElementById('module-title-input');
    const newPageCheck = document.getElementById('module-newpage-check');
    const addModuleBtn = document.getElementById('add-module-btn');
    const layoutList = document.getElementById('report-layout-list');
    const jsonTextarea = document.getElementById('report_layout_json');
    const reportForm = document.getElementById('report-form');
    const generateBtn = document.getElementById('generate-btn');
    const statusArea = document.getElementById('status-area');
    const statusMessage = document.getElementById('status-message');
    const downloadLink = document.getElementById('download-link');
    const templateSelector = document.getElementById('templateSelector');
    const loadTemplateBtn = document.getElementById('loadTemplateBtn');
    const saveTemplateBtn = document.getElementById('saveTemplateBtn');
    const templateNameInput = document.getElementById('templateNameInput');

    // --- ELEMENTOS DO MODAL WIFI ---
    const wifiModalEl = document.getElementById('customizeWifiModal');
    const wifiModal = wifiModalEl ? new bootstrap.Modal(wifiModalEl) : null;
    const wifiChartType = document.getElementById('wifiChartType');
    const wifiTableType = document.getElementById('wifiTableType');
    const wifiHeatmapMode = document.getElementById('wifiHeatmapMode');
    const wifiCapacity = document.getElementById('wifiCapacity');
    const wifiMaxCharts = document.getElementById('wifiMaxCharts');
    const saveWifiCustomizationBtn = document.getElementById('saveWifiCustomizationBtn');

    // --- ESTADO DA APLICAÇÃO ---
    let reportLayout = [];
    let availableModules = [];
    let currentModuleToCustomize = null;
    let activePoll = null; // controle para polling de status

    // ===================================================================================
    // --- CENTRO DE COMANDO DE CUSTOMIZAÇÃO DE MÓDULOS ---
    // ===================================================================================
    const moduleCustomizers = {
        'sla': {
            modal: new bootstrap.Modal(document.getElementById('customizeSlaModal')),
            elements: {
                hideSummary: document.getElementById('slaHideSummaryCheck'),
                comparePrevMonth: document.getElementById('slaComparePrevMonthCheck'),
                showIp: document.getElementById('slaShowIpCheck'),
                showDowntime: document.getElementById('slaShowDowntimeCheck'),
                showPrevSla: document.getElementById('slaShowPreviousSlaCheck'),
                showImprovement: document.getElementById('slaShowImprovementCheck'),
                showGoal: document.getElementById('slaShowGoalCheck'),
                saveBtn: document.getElementById('saveSlaCustomizationBtn')
            },
            load: function(options) {
                this.elements.hideSummary.checked = options.hide_summary || false;
                this.elements.comparePrevMonth.checked = options.compare_to_previous_month || false;
                this.elements.showIp.checked = options.show_ip || false;
                this.elements.showDowntime.checked = options.show_downtime || false;
                this.elements.showGoal.checked = options.show_goal || false;

                const isCompareChecked = this.elements.comparePrevMonth.checked;
                this.elements.showPrevSla.disabled = !isCompareChecked;
                this.elements.showImprovement.disabled = !isCompareChecked;
                this.elements.showPrevSla.checked = isCompareChecked && (options.show_previous_sla || false);
                this.elements.showImprovement.checked = isCompareChecked && (options.show_improvement || false);
            },
            save: function() {
                return {
                    hide_summary: this.elements.hideSummary.checked,
                    compare_to_previous_month: this.elements.comparePrevMonth.checked,
                    show_ip: this.elements.showIp.checked,
                    show_downtime: this.elements.showDowntime.checked,
                    show_previous_sla: this.elements.showPrevSla.checked,
                    show_improvement: this.elements.showImprovement.checked,
                    show_goal: this.elements.showGoal.checked
                };
            }
        },
        'top_hosts': {
            modal: new bootstrap.Modal(document.getElementById('customizeTopHostsModal')),
            elements: {
                topN: document.getElementById('topHostsCount'),
                showSummary: document.getElementById('topHostsShowSummaryChartCheck'),
                showDiagnosis: document.getElementById('topHostsShowDetailedDiagnosisCheck'),
                chartType: document.getElementById('topHostsBreakdownChartType'),
                saveBtn: document.getElementById('saveTopHostsCustomizationBtn')
            },
            load: function(options) {
                this.elements.topN.value = options.top_n || 5;
                this.elements.showSummary.checked = options.show_summary_chart !== false;
                this.elements.showDiagnosis.checked = options.show_detailed_diagnosis !== false;
                this.elements.chartType.value = options.chart_type || 'table';
            },
            save: function() {
                return {
                    top_n: parseInt(this.elements.topN.value, 10),
                    show_summary_chart: this.elements.showSummary.checked,
                    show_detailed_diagnosis: this.elements.showDiagnosis.checked,
                    chart_type: this.elements.chartType.value
                };
            }
        },
        // ----------------- NOVO: CUSTOMIZER DO WI-FI -----------------
        'wifi': {
            modal: wifiModal,
            elements: {
                chartType: wifiChartType,
                tableType: wifiTableType,
                heatmap: wifiHeatmapMode,
                capacity: wifiCapacity,
                maxCharts: wifiMaxCharts,
                saveBtn: saveWifiCustomizationBtn
            },
            load: function(options) {
                this.elements.chartType.value = (options.chart || 'bar');
                this.elements.tableType.value = (options.table || 'both');
                this.elements.heatmap.value = (options.heatmap || 'global');
                this.elements.capacity.value = (options.capacity_per_ap != null ? options.capacity_per_ap : 50);
                this.elements.maxCharts.value = (options.max_charts != null ? options.max_charts : 6);
            },
            save: function() {
                return {
                    chart: this.elements.chartType.value,
                    table: this.elements.tableType.value,
                    heatmap: this.elements.heatmap.value,
                    capacity_per_ap: parseFloat(this.elements.capacity.value),
                    max_charts: parseInt(this.elements.maxCharts.value, 10)
                };
            }
        }
        // -------------------------------------------------------------
    };
    // ===================================================================================

    // --- FUNÇÕES AUXILIARES ---

    function logDebug(event, details = {}) {
        console.debug(`[gerar_form] ${event}`, details);
        window.__gerarFormDebug = window.__gerarFormDebug || [];
        window.__gerarFormDebug.push({ ts: new Date().toISOString(), event, details });
    }

    function safeUUID() {
        if (window.crypto && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        return 'id-' + Math.random().toString(36).substring(2, 11);
    }

    function renderLayoutList() {
        layoutList.innerHTML = '';
        if (reportLayout.length === 0) {
            layoutList.innerHTML = '<li class="list-group-item text-muted">Nenhum módulo adicionado.</li>';
            return;
        }
        reportLayout.forEach(module => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center';
            li.dataset.moduleId = module.id;

            const moduleName = availableModules.find(m => m.type === module.type)?.name || module.type;
            const titleDisplay = module.title ? `"${module.title}"` : '';
            const isCustomizable = module.type in moduleCustomizers;

            li.innerHTML = `
                <div class="d-flex align-items-center">
                    <i class="bi bi-grip-vertical me-3" style="cursor: grab;"></i>
                    <div>
                        <span class="fw-bold">${moduleName}</span>
                        <small class="d-block text-muted">${titleDisplay}</small>
                    </div>
                </div>
                <div class="btn-group">
                    ${isCustomizable ? `<button type="button" class="btn btn-sm btn-outline-secondary customize-module-btn me-2" data-module-id="${module.id}" title="Personalizar"><i class="bi bi-gear"></i></button>` : ''}
                    <button type="button" class="btn btn-sm btn-outline-danger remove-module-btn" data-module-id="${module.id}" title="Remover">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            `;
            layoutList.appendChild(li);
        });
        jsonTextarea.value = JSON.stringify(reportLayout);
    }

    async function fetchClientData(clientId) {
        if (!clientId) {
            moduleTypeSelect.innerHTML = '<option>Selecione um cliente primeiro</option>';
            moduleTypeSelect.disabled = true;
            addModuleBtn.disabled = true;
            return;
        }
        moduleTypeSelect.innerHTML = '<option>Carregando módulos…</option>';
        moduleTypeSelect.disabled = true;
        addModuleBtn.disabled = true;

        const url = URLS.get_modules.replace('0', String(clientId));
        logDebug('fetchClientData.start', { url });

        try {
            const response = await fetch(url, { headers: { 'Accept': 'application/json' }});
            if (!response.ok) {
                const rawText = await response.text().catch(() => '');
                logDebug('fetchClientData.error', { status: response.status, rawText });
                moduleTypeSelect.innerHTML = '<option>Erro ao carregar módulos</option>';
                return;
            }

            const data = await response.json().catch(err => {
                logDebug('fetchClientData.jsonError', { err: String(err) });
                return null;
            });

            if (!data || data.error) {
                logDebug('fetchClientData.backendError', { error: data?.error });
                moduleTypeSelect.innerHTML = '<option>Erro ao carregar módulos</option>';
                return;
            }

            availableModules = Array.isArray(data.available_modules) ? data.available_modules : [];
            logDebug('fetchClientData.success', { count: availableModules.length });

            moduleTypeSelect.innerHTML = '';
            if (availableModules.length > 0) {
                availableModules.forEach(mod => moduleTypeSelect.add(new Option(mod.name, mod.type)));
                moduleTypeSelect.disabled = false;
                addModuleBtn.disabled = false;
            } else {
                moduleTypeSelect.innerHTML = '<option>Nenhum módulo disponível</option>';
            }
        } catch (error) {
            logDebug('fetchClientData.exception', { error: String(error) });
            moduleTypeSelect.innerHTML = '<option>Erro ao carregar módulos</option>';
        }
    }

    function resetStatusArea() {
        statusArea.style.display = 'none';
        statusMessage.textContent = 'Iniciando...';
        statusArea.className = 'alert alert-info mt-4';
        downloadLink.classList.add('disabled');
        downloadLink.href = '#';
        generateBtn.disabled = false;
        generateBtn.innerHTML = '<i class="bi bi-file-earmark-pdf"></i> Gerar Relatório';
    }

    // --- EVENTOS ---

    clientSelect.addEventListener('change', () => {
        fetchClientData(clientSelect.value);
        reportLayout = [];
        renderLayoutList();
    });

    addModuleBtn.addEventListener('click', () => {
        const moduleType = moduleTypeSelect.value;
        if (!moduleType) return;
        reportLayout.push({
            id: safeUUID(),
            type: moduleType,
            title: moduleTitleInput.value.trim(),
            newPage: newPageCheck.checked,
            custom_options: {}
        });
        renderLayoutList();
        moduleTitleInput.value = '';
        newPageCheck.checked = false;
    });

    layoutList.addEventListener('click', (e) => {
        const targetBtn = e.target.closest('button');
        if (!targetBtn) return;

        const moduleId = targetBtn.dataset.moduleId;
        const module = reportLayout.find(m => m.id === moduleId);
        if (!module) return;

        if (targetBtn.classList.contains('remove-module-btn')) {
            reportLayout = reportLayout.filter(m => m.id !== moduleId);
            renderLayoutList();
        } else if (targetBtn.classList.contains('customize-module-btn')) {
            currentModuleToCustomize = module;
            const customizer = moduleCustomizers[module.type];
            if (customizer && customizer.modal) {
                customizer.load(module.custom_options || {});
                customizer.modal.show();
            }
        }
    });

    // Salvar de cada customizer
    Object.keys(moduleCustomizers).forEach(moduleType => {
        const customizer = moduleCustomizers[moduleType];
        if (customizer.elements && customizer.elements.saveBtn) {
            customizer.elements.saveBtn.addEventListener('click', () => {
                if (!currentModuleToCustomize) return;
                currentModuleToCustomize.custom_options = customizer.save();
                renderLayoutList();
                customizer.modal.hide();
            });
        }
    });

    // Regras específicas de SLA (já existentes)
    if (moduleCustomizers.sla) {
        const slaElements = moduleCustomizers.sla.elements;
        slaElements.comparePrevMonth.addEventListener('change', () => {
            const isChecked = slaElements.comparePrevMonth.checked;
            slaElements.showPrevSla.disabled = !isChecked;
            slaElements.showImprovement.disabled = !isChecked;
            if (!isChecked) {
                slaElements.showPrevSla.checked = false;
                slaElements.showImprovement.checked = false;
            }
        });
    }

    // Carregar template salvo
    loadTemplateBtn.addEventListener('click', () => {
        if (templateSelector.value) {
            try {
                reportLayout = JSON.parse(templateSelector.value);
                renderLayoutList();
            } catch (e) {
                logDebug('loadTemplateBtn.jsonError', { error: String(e) });
            }
        }
    });

    // Submissão do form → gerar relatório
    reportForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (reportLayout.length === 0) {
            statusArea.style.display = 'block';
            statusArea.className = 'alert alert-warning mt-4';
            statusMessage.textContent = '⚠️ Adicione ao menos um módulo antes de gerar o relatório.';
            return;
        }

        generateBtn.disabled = true;
        generateBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Gerando...';
        resetStatusArea();
        statusArea.style.display = 'block';

        const formData = new FormData(reportForm);

        try {
            const response = await fetch(URLS.gerar_relatorio, { method: 'POST', body: formData });
            if (!response.ok) throw new Error(`Erro no servidor: ${response.status} ${response.statusText}`);
            const data = await response.json();
            const taskId = data.task_id;

            if (taskId) {
                activePoll = setInterval(async () => {
                    try {
                        const statusResponse = await fetch(URLS.report_status.replace('0', taskId));
                        if (!statusResponse.ok) throw new Error('Falha ao verificar status');
                        const statusData = await statusResponse.json();

                        statusMessage.textContent = statusData.status || 'Aguardando...';

                        if (statusData.status === 'Concluído') {
                            clearInterval(activePoll);
                            statusMessage.textContent = '✅ Relatório gerado com sucesso!';
                            downloadLink.href = URLS.download_report.replace('0', taskId);
                            downloadLink.classList.remove('disabled');
                            generateBtn.disabled = false;
                            generateBtn.innerHTML = '<i class="bi bi-file-earmark-pdf"></i> Gerar Novo Relatório';
                        } else if (statusData.status && statusData.status.startsWith('Erro:')) {
                            clearInterval(activePoll);
                            statusArea.className = 'alert alert-danger mt-4';
                            generateBtn.disabled = false;
                            generateBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Tentar Novamente';
                        }
                    } catch (pollError) {
                        clearInterval(activePoll);
                        logDebug('poll.error', { error: String(pollError) });
                        statusMessage.textContent = `Erro ao consultar status: ${pollError.message}`;
                        statusArea.className = 'alert alert-danger mt-4';
                        generateBtn.disabled = false;
                        generateBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Tentar Novamente';
                    }
                }, 2000);
            } else { throw new Error("Não foi possível iniciar a tarefa."); }

        } catch (error) {
            logDebug('submit.error', { error: String(error) });
            statusMessage.textContent = `Erro: ${error.message}`;
            statusArea.className = 'alert alert-danger mt-4';
            generateBtn.disabled = false;
            generateBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Tentar Novamente';
        }
    });

    // Drag & drop na lista
    new Sortable(layoutList, {
        animation: 150,
        handle: '.bi-grip-vertical',
        onEnd: function (evt) {
            const [movedItem] = reportLayout.splice(evt.oldIndex, 1);
            reportLayout.splice(evt.newIndex, 0, movedItem);
            renderLayoutList();
        }
    });

    // --- INICIALIZAÇÃO ---
    const today = new Date();
    monthInput.value = `${today.getFullYear()}-${(today.getMonth() + 1).toString().padStart(2, '0')}`;
    renderLayoutList();
});
