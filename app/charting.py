# app/charting.py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import textwrap
import logging
import pandas as pd

# -----------------------
# Utilitários internos
# -----------------------

def _coerce_percent_series(s):
    """
    Converte uma Series com possíveis valores '12.3%' ou strings em floats.
    Valores inválidos viram NaN (coerce).
    """
    if s is None:
        return None
    if s.dtype == object:
        s = s.astype(str).str.replace('%', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce')


def _normalize_mem_dataframe(df):
    """
    Normaliza um DataFrame de memória para o formato canônico exigido pelos gráficos:
        colunas: ['Host', 'Min', 'Avg', 'Max']
    Aceita sinônimos típicos vindos dos coletores:
        - Host: 'Host', 'Hostname', 'Nome', 'name'
        - Min: 'Min', 'Mínimo', 'Min %', 'value_min'
        - Avg: 'Avg', 'Médio', 'Med', 'Med %', 'Média', 'value_avg'
        - Max: 'Max', 'Máximo', 'Max %', 'value_max'
    Também:
        - Remove '%' e converte para float
        - Se 'Avg' não existir mas houver 'Min' e 'Max', calcula Avg como média
        - Descarta linhas sem números válidos
    """
    original_cols = list(df.columns)
    logging.debug(f"[charting] Colunas originais do DF: {original_cols}")

    # Mapas de possíveis nomes
    host_candidates = ['Host', 'Hostname', 'Nome', 'Name', 'host', 'hostname', 'nome', 'name']
    min_candidates  = ['Min', 'Mínimo', 'Min %', 'value_min', 'min', 'minimo', 'mínimo']
    avg_candidates  = ['Avg', 'Médio', 'Med', 'Med %', 'Média', 'value_avg', 'avg', 'media', 'média']
    max_candidates  = ['Max', 'Máximo', 'Max %', 'value_max', 'max', 'maximo', 'máximo']

    def _find_col(candidates):
        for c in candidates:
            if c in df.columns:
                return c
        # tentativa case-insensitive
        lower_map = {str(c).lower(): c for c in df.columns}
        for c in candidates:
            if c.lower() in lower_map:
                return lower_map[c.lower()]
        return None

    host_col = _find_col(host_candidates)
    min_col  = _find_col(min_candidates)
    avg_col  = _find_col(avg_candidates)
    max_col  = _find_col(max_candidates)

    # Host é obrigatório para a visualização
    if not host_col:
        raise ValueError("DataFrame não possui coluna de Host identificável.")

    # Coerção numérica
    min_series = _coerce_percent_series(df[min_col]) if min_col else None
    avg_series = _coerce_percent_series(df[avg_col]) if avg_col else None
    max_series = _coerce_percent_series(df[max_col]) if max_col else None

    # Se não houver Avg mas houver Min e Max, calcula média
    if avg_series is None and (min_series is not None and max_series is not None):
        avg_series = (min_series + max_series) / 2.0

    # Se ainda não houver pelo menos uma das séries numéricas, não dá para plotar
    if avg_series is None and min_series is None and max_series is None:
        raise ValueError("DataFrame não possui colunas numéricas reconhecíveis para Min/Avg/Max.")

    # Monta DF canônico
    out = pd.DataFrame({'Host': df[host_col]})
    if min_series is not None:
        out['Min'] = min_series
    if avg_series is not None:
        out['Avg'] = avg_series
    if max_series is not None:
        out['Max'] = max_series

    # Remove linhas completamente vazias nas métricas
    metric_cols = [c for c in ['Min', 'Avg', 'Max'] if c in out.columns]
    out = out.dropna(subset=metric_cols, how='all').copy()

    # Garantias finais: se 'Avg' ainda estiver ausente mas houver alguma métrica, cria uma aproximação
    if 'Avg' not in out.columns:
        if 'Min' in out.columns and 'Max' in out.columns:
            out['Avg'] = (out['Min'] + out['Max']) / 2.0
        elif 'Min' in out.columns:
            out['Avg'] = out['Min']
        elif 'Max' in out.columns:
            out['Avg'] = out['Max']
        else:
            # Sem Avg e sem Min/Max — não há o que fazer
            raise ValueError("Não foi possível derivar a coluna 'Avg'.")

    # Converte para float com segurança
    for c in ['Min', 'Avg', 'Max']:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors='coerce')

    logging.debug(f"[charting] Colunas após normalização: {list(out.columns)}")
    logging.debug(f"[charting] Amostra de dados normalizados:\n{out.head(3).to_string(index=False)}")
    return out


# -----------------------
# API pública
# -----------------------

def generate_chart(df, x_col, y_col, title, x_label, chart_color):
    logging.info(f"Gerando gráfico: {title}...")
    if df is None or df.empty:
        logging.warning("[charting.generate_chart] DataFrame vazio - gráfico não será gerado.")
        return None

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))

    try:
        df_sorted = df.sort_values(by=x_col, ascending=True)
    except Exception as e:
        logging.error(f"[charting.generate_chart] Falha ao ordenar por '{x_col}': {e}")
        df_sorted = df

    y_labels = ['\n'.join(textwrap.wrap(str(label), width=50)) for label in df_sorted[y_col]]
    bars = ax.barh(y_labels, df_sorted[x_col], color=chart_color)
    font_size = 8 if len(y_labels) > 10 else 9

    ax.tick_params(axis='y', labelsize=font_size)
    ax.set_xlabel(x_label)
    ax.set_title(title, fontsize=16)
    ax.grid(True, which='major', axis='x', linestyle='--', linewidth=0.5)
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)

    for bar in bars:
        label_val = bar.get_width()
        try:
            label = f'{float(label_val):.2f}'
        except Exception:
            label = str(label_val)
        ax.text(label_val, bar.get_y() + bar.get_height()/2, f' {label}', va='center', ha='left', fontsize=font_size - 1)

    plt.subplots_adjust(left=0.45, right=0.95, top=0.9, bottom=0.1)
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, transparent=True)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


def generate_multi_bar_chart(df, title, x_label, colors):
    """
    Gera gráfico horizontal de barras múltiplas (Min/Avg/Max) para hosts.

    - Aceita DataFrame em vários formatos e normaliza para ['Host','Min','Avg','Max'].
    - Limita a quantidade de barras para evitar explosão visual e de memória.
    - Retorna base64 do PNG, ou None se DF inválido.
    """
    logging.info(f"Gerando gráfico: {title}...")

    if df is None or df.empty:
        logging.warning("[charting.generate_multi_bar_chart] DataFrame vazio - gráfico não será gerado.")
        return None

    try:
        df_norm = _normalize_mem_dataframe(df.copy())
    except Exception as e:
        logging.error(f"[charting.generate_multi_bar_chart] Falha na normalização do DataFrame: {e}", exc_info=True)
        return None

    # Ordena por Avg (substitui NaN por -inf para irem ao início)
    try:
        df_sorted = df_norm.copy()
        df_sorted['Avg_sort'] = df_sorted['Avg'].fillna(float('-inf'))
        df_sorted = df_sorted.sort_values(by='Avg_sort', ascending=True).drop(columns=['Avg_sort'])
    except Exception as e:
        logging.error(f"[charting.generate_multi_bar_chart] Falha ao ordenar por 'Avg': {e}")
        df_sorted = df_norm

    # Proteção para grandes volumes
    MAX_BARS = 60
    if len(df_sorted) > MAX_BARS:
        logging.info(f"[charting.generate_multi_bar_chart] {len(df_sorted)} linhas -> limitando a {MAX_BARS} com maiores 'Avg'.")
        # Pega as maiores 'Avg' (mais relevantes) mantendo ordem
        df_sorted = df_sorted.nlargest(MAX_BARS, 'Avg').sort_values(by='Avg', ascending=True)

    y_labels = ['\n'.join(textwrap.wrap(str(label), width=45)) for label in df_sorted['Host']]

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, max(8, len(df_sorted) * 0.4)))

    y = range(len(df_sorted))
    bar_height = 0.25

    # As colunas Min/Avg/Max podem eventualmente faltar — tratamos ausências
    min_vals = df_sorted['Min'] if 'Min' in df_sorted.columns else pd.Series([None]*len(df_sorted))
    avg_vals = df_sorted['Avg'] if 'Avg' in df_sorted.columns else pd.Series([None]*len(df_sorted))
    max_vals = df_sorted['Max'] if 'Max' in df_sorted.columns else pd.Series([None]*len(df_sorted))

    # Coerção final a numérico
    min_vals = pd.to_numeric(min_vals, errors='coerce')
    avg_vals = pd.to_numeric(avg_vals, errors='coerce')
    max_vals = pd.to_numeric(max_vals, errors='coerce')

    # Barras
    c0 = colors[0] if len(colors) > 0 else None
    c1 = colors[1] if len(colors) > 1 else None
    c2 = colors[2] if len(colors) > 2 else None

    ax.barh([i - bar_height for i in y], max_vals, height=bar_height, label='Máximo', color=c0)
    ax.barh(y,                          avg_vals, height=bar_height, label='Médio',  color=c1)
    ax.barh([i + bar_height for i in y], min_vals, height=bar_height, label='Mínimo', color=c2)

    font_size = 8 if len(y_labels) > 10 else 9
    ax.set_yticks(list(y))
    ax.set_yticklabels(y_labels, fontsize=font_size)
    ax.set_xlabel(x_label)
    ax.set_title(title, fontsize=16)
    ax.grid(True, which='major', axis='x', linestyle='--', linewidth=0.5)
    ax.legend()
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)

    plt.subplots_adjust(left=0.4, right=0.95, top=0.9, bottom=0.1)
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, transparent=True)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')
