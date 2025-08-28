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

    // --- ESTADO DA APLICAÇÃO ---
    let reportLayout = [];
    let availableModules = [];
    let currentModuleToCustomize = null;

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
        }
    };
    // ===================================================================================

    // --- FUNÇÕES ---

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
        console.debug('[gerar_form] GET módulos', { url });

        try {
            const response = await fetch(url, { headers: { 'Accept': 'application/json' }});
            const status = response.status;
            let rawText = '';
            let data = null;

            if (!response.ok) {
                try { rawText = await response.text(); } catch (_) {}
                console.error('[gerar_form] Resposta não-OK ao buscar módulos', { status, rawText });
                window.__reportModulesDebug = { url, status, rawText };
                moduleTypeSelect.innerHTML = '<option>Erro ao carregar módulos</option>';
                return;
            }

            // Tenta parsear JSON com tolerância
            try {
                data = await response.json();
            } catch (jsonErr) {
                rawText = rawText || (await response.text().catch(() => ''));
                console.error('[gerar_form] Falha ao parsear JSON de módulos', { status, jsonErr, rawText });
                window.__reportModulesDebug = { url, status, jsonErr: String(jsonErr), rawText };
                moduleTypeSelect.innerHTML = '<option>Erro ao carregar módulos</option>';
                return;
            }

            if (data && data.error) {
                console.error('[gerar_form] Backend retornou erro de módulos', { status, error: data.error });
                window.__reportModulesDebug = { url, status, error: data.error };
                moduleTypeSelect.innerHTML = '<option>Erro ao carregar módulos</option>';
                return;
            }

            availableModules = (data && data.available_modules) || [];
            console.debug('[gerar_form] Módulos disponíveis', { count: availableModules.length, items: availableModules });

            moduleTypeSelect.innerHTML = '';
            if (availableModules.length > 0) {
                availableModules.forEach(mod => moduleTypeSelect.add(new Option(mod.name, mod.type)));
                moduleTypeSelect.disabled = false;
                addModuleBtn.disabled = false;
            } else {
                moduleTypeSelect.innerHTML = '<option>Nenhum módulo disponível</option>';
            }
        } catch (error) {
            console.error('[gerar_form] Erro ao carregar módulos (network/JS):', error);
            window.__reportModulesDebug = { url, exception: String(error) };
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

    // --- LÓGICA DE EVENTOS ---

    function handleCustomizeClick(module) {
        currentModuleToCustomize = module;
        const customizer = moduleCustomizers[module.type];
        if (customizer) {
            customizer.load(module.custom_options || {});
            customizer.modal.show();
        }
    }

    function handleSaveCustomization(moduleType) {
        if (!currentModuleToCustomize) return;
        const customizer = moduleCustomizers[moduleType];
        if (customizer) {
            currentModuleToCustomize.custom_options = customizer.save();
            renderLayoutList();
            customizer.modal.hide();
        }
    }

    clientSelect.addEventListener('change', () => {
        fetchClientData(clientSelect.value);
        reportLayout = [];
        renderLayoutList();
    });

    addModuleBtn.addEventListener('click', () => {
        const moduleType = moduleTypeSelect.value;
        if (!moduleType) return;
        reportLayout.push({
            id: crypto.randomUUID(),
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
            handleCustomizeClick(module);
        }
    });

    Object.keys(moduleCustomizers).forEach(moduleType => {
        const customizer = moduleCustomizers[moduleType];
        if (customizer.elements.saveBtn) {
            customizer.elements.saveBtn.addEventListener('click', () => handleSaveCustomization(moduleType));
        }
    });

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

    loadTemplateBtn.addEventListener('click', () => {
        if (templateSelector.value) {
            reportLayout = JSON.parse(templateSelector.value);
            renderLayoutList();
        }
    });

    reportForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (reportLayout.length === 0) {
            alert('Por favor, adicione ao menos um módulo ao layout do relatório.');
            return;
        }

        generateBtn.disabled = true;
        generateBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Gerando...';
        resetStatusArea();
        statusArea.style.display = 'block';

        const formData = new FormData(reportForm);

        try {
            const response = await fetch(URLS.gerar_relatorio, {
                method: 'POST',
                body: formData
            });
            if (!response.ok) throw new Error(`Erro no servidor: ${response.status} ${response.statusText}`);
            const data = await response.json();
            const taskId = data.task_id;

            if (taskId) {
                const pollInterval = setInterval(async () => {
                    try {
                        const statusResponse = await fetch(URLS.report_status.replace('0', taskId));
                        if (!statusResponse.ok) throw new Error('Falha ao verificar status');
                        const statusData = await statusResponse.json();

                        statusMessage.textContent = statusData.status || 'Aguardando...';

                        if (statusData.status === 'Concluído') {
                            clearInterval(pollInterval);
                            statusMessage.textContent = 'Relatório gerado com sucesso!';
                            downloadLink.href = URLS.download_report.replace('0', taskId);
                            downloadLink.classList.remove('disabled');
                            generateBtn.disabled = false;
                            generateBtn.innerHTML = '<i class="bi bi-file-earmark-pdf"></i> Gerar Novo Relatório';
                        } else if (statusData.status && statusData.status.startsWith('Erro:')) {
                            clearInterval(pollInterval);
                            statusArea.className = 'alert alert-danger mt-4';
                            generateBtn.disabled = false;
                            generateBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Tentar Novamente';
                        }
                    } catch (pollError) {
                        clearInterval(pollInterval);
                        statusMessage.textContent = `Erro ao consultar status: ${pollError.message}`;
                        statusArea.className = 'alert alert-danger mt-4';
                        generateBtn.disabled = false;
                        generateBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Tentar Novamente';
                    }
                }, 2000);
            } else { throw new Error("Não foi possível iniciar a tarefa."); }

        } catch (error) {
            console.error("Erro na submissão:", error);
            statusMessage.textContent = `Erro: ${error.message}`;
            statusArea.className = 'alert alert-danger mt-4';
            generateBtn.disabled = false;
            generateBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Tentar Novamente';
        }
    });

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
