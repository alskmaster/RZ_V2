# app/charting.py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import textwrap
import logging

def generate_chart(df, x_col, y_col, title, x_label, chart_color):
    logging.info(f"Gerando gráfico: {title}...")
    if df.empty: return None
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))
    df_sorted = df.sort_values(by=x_col, ascending=True)
    y_labels = ['\n'.join(textwrap.wrap(str(label), width=50)) for label in df_sorted[y_col]]
    bars = ax.barh(y_labels, df_sorted[x_col], color=chart_color)
    font_size = 8 if len(y_labels) > 10 else 9
    ax.tick_params(axis='y', labelsize=font_size)
    ax.set_xlabel(x_label)
    ax.set_title(title, fontsize=16)
    ax.grid(True, which='major', axis='x', linestyle='--', linewidth=0.5)
    for spine in ['top', 'right', 'left', 'bottom']: ax.spines[spine].set_visible(False)
    for bar in bars:
        label_val = bar.get_width()
        label = f'{label_val:.2f}h' if isinstance(label_val, float) else f'{int(label_val)}'
        ax.text(label_val, bar.get_y() + bar.get_height()/2, f' {label}', va='center', ha='left', fontsize=font_size - 1)
    plt.subplots_adjust(left=0.45, right=0.95, top=0.9, bottom=0.1)
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, transparent=True)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def generate_multi_bar_chart(df, title, x_label, colors):
    logging.info(f"Gerando gráfico: {title}...")
    if df.empty or len(df.columns) < 4: return None
    df_sorted = df.sort_values(by='Avg', ascending=True)
    y_labels = ['\n'.join(textwrap.wrap(str(label), width=45)) for label in df_sorted['Host']]
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, max(8, len(df_sorted) * 0.4)))
    y = range(len(df_sorted))
    bar_height = 0.25
    ax.barh([i - bar_height for i in y], df_sorted['Max'], height=bar_height, label='Máximo', color=colors[0])
    ax.barh(y, df_sorted['Avg'], height=bar_height, label='Médio', color=colors[1])
    ax.barh([i + bar_height for i in y], df_sorted['Min'], height=bar_height, label='Mínimo', color=colors[2])
    font_size = 8 if len(y_labels) > 10 else 9
    ax.set_yticks(y)
    ax.set_yticklabels(y_labels, fontsize=font_size)
    ax.set_xlabel(x_label)
    ax.set_title(title, fontsize=16)
    ax.grid(True, which='major', axis='x', linestyle='--', linewidth=0.5)
    ax.legend()
    for spine in ['top', 'right', 'left', 'bottom']: ax.spines[spine].set_visible(False)
    plt.subplots_adjust(left=0.4, right=0.95, top=0.9, bottom=0.1)
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, transparent=True)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')