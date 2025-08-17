# =========================================
# config.py — utilidades para o dashboard
# =========================================

# ---- Imports
import csv
import io
import os
import re
import json
import time
import tempfile
import hashlib
from io import BytesIO, StringIO
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
import unidecode
from pyxlsb import open_workbook as open_xlsb
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from st_aggrid.shared import JsCode  # opcional (mantido)
from pyecharts.charts import Pie, Bar, Gauge, Page
from pyecharts import options as opts

# -----------------------------------------------------------------------------
# Mensagens temporárias
# -----------------------------------------------------------------------------
def show_temporary_success(message_key: str, message_text: str, duration: int = 3):
    """
    Exibe uma mensagem de sucesso temporária apenas uma vez por sessão.
    """
    if "success_messages" not in st.session_state:
        st.session_state.success_messages = {}
    if message_key not in st.session_state.success_messages:
        st.session_state.success_messages[message_key] = False
    if not st.session_state.success_messages[message_key]:
        with st.container():
            ph = st.empty()
            ph.success(message_text)
            time.sleep(duration)
            ph.empty()
        st.session_state.success_messages[message_key] = True

# -----------------------------------------------------------------------------
# Normalização de nomes de colunas
# -----------------------------------------------------------------------------
def normalize_column_names(columns):
    """
    Remove acentos, trim, upper e troca espaços/pontuação por underscore.
    Ex.: 'Descrição do Produto' -> 'DESCRICAO_DO_PRODUTO'
    """
    out = []
    for col in columns:
        if col is None:
            out.append(col)
            continue
        c = unidecode.unidecode(str(col)).strip().upper()
        c = re.sub(r"[^\w]+", "_", c)
        c = re.sub(r"_+", "_", c).strip("_")
        out.append(c)
    return out

# -----------------------------------------------------------------------------
# Hash de arquivo (opcional, útil p/ cache externo)
# -----------------------------------------------------------------------------
def gerar_hash(file) -> str:
    file.seek(0)
    content = file.read()
    file.seek(0)
    return hashlib.md5(content).hexdigest()

# -----------------------------------------------------------------------------
# Leitura de Excel (xlsx/xls/xlsb)
# -----------------------------------------------------------------------------
def _read_xlsb_to_df(tmp_path: str) -> pd.DataFrame:
    with open_xlsb(tmp_path) as wb:
        with wb.get_sheet(1) as sheet:
            data = [[cell.v for cell in row] for row in sheet.rows()]
    return pd.DataFrame(data[1:], columns=data[0])

def process_excel_file(file, extension: str) -> pd.DataFrame:
    """
    Lê Excel (xlsx/xls/xlsb) preservando strings.
    """
    if extension == "xlsb":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsb") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name
        try:
            df = _read_xlsb_to_df(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return df.astype(str)
    else:
        # pandas detecta engine automaticamente
        return pd.read_excel(file, dtype=str)

# -----------------------------------------------------------------------------
# CSV/TXT: detecção de encoding e dialeto (sep/aspas)
# -----------------------------------------------------------------------------
COMMON_ENCODINGS = ["utf-8", "utf-8-sig", "latin1", "cp1252", "iso-8859-1"]

def _read_text_with_fallback(uploaded_file) -> tuple[str, str]:
    """
    Lê bytes e tenta decodificar em vários encodings.
    Retorna (texto, encoding_utilizado). Último recurso: latin1(ignore).
    """
    raw = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    for enc in COMMON_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("latin1", errors="ignore"), "latin1(ignore)"

def _fallback_sep(sample: str) -> str:
    seps = [",", ";", "\t", "|"]
    return max(seps, key=lambda s: sample.count(s)) if sample else ","

def detect_csv_dialect(text: str):
    """
    Detecta separador e aspas com csv.Sniffer; fallback por contagem.
    """
    sample = text[:8192] if text else ""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return {
            "sep": dialect.delimiter,
            "quotechar": dialect.quotechar or '"',
            "doublequote": getattr(dialect, "doublequote", True),
            "escapechar": getattr(dialect, "escapechar", None),
        }
    except Exception:
        return {
            "sep": _fallback_sep(sample),
            "quotechar": '"',
            "doublequote": True,
            "escapechar": None,
        }

# -----------------------------------------------------------------------------
# Upload de arquivos
# -----------------------------------------------------------------------------
def process_upload(file, expected_type):
    """
    Lê e processa arquivos enviados pelo usuário.
    expected_type: 'contagem' | 'estoque_esperado'
    Retorna (dataframe, tipo_detectado) onde tipo_detectado descreve a origem.
    """
    if file is None:
        return None, None

    ext = file.name.split(".")[-1].lower()

    try:
        # --------- CONTAGEM: .txt/.csv sem cabeçalho; 1 ou 2 colunas ----------
        if expected_type == "contagem":
            if ext in ["txt", "csv"]:
                text, enc_used = _read_text_with_fallback(file)
                dial = detect_csv_dialect(text)
                df = pd.read_csv(
                    StringIO(text),
                    sep=dial["sep"],
                    header=None,        # contagem não tem cabeçalho
                    dtype=str,
                    quotechar=dial["quotechar"],
                    doublequote=dial["doublequote"],
                    escapechar=dial["escapechar"],
                    engine="python",
                )

                if df.shape[1] == 1:
                    # Só EAN → CONTAGEM=1
                    df.columns = ["EAN"]
                    df["CONTAGEM"] = 1
                elif df.shape[1] >= 2:
                    # EAN, CONTAGEM
                    df = df.iloc[:, :2]
                    df.columns = ["EAN", "CONTAGEM"]
                    df["CONTAGEM"] = (
                        pd.to_numeric(df["CONTAGEM"].str.replace(",", "."), errors="coerce")
                        .fillna(1)
                        .astype(int)
                    )
                else:
                    st.error("O arquivo de contagem deve conter uma ou duas colunas.")
                    return None, None

                df["EAN"] = df["EAN"].astype(str).str.strip()
                return df, f"contagem[{enc_used}; sep={dial['sep']}]"

            st.error("Formato de arquivo não suportado para contagem. Envie .txt ou .csv.")
            return None, None

        # --------- ESTOQUE ESPERADO: CSV (com cabeçalho) ou Excel ----------
        elif expected_type == "estoque_esperado":
            if ext == "csv":
                text, enc_used = _read_text_with_fallback(file)
                dial = detect_csv_dialect(text)
                df = pd.read_csv(
                    StringIO(text),
                    sep=dial["sep"],
                    dtype=str,
                    header=0,  # tem cabeçalho
                    quotechar=dial["quotechar"],
                    doublequote=dial["doublequote"],
                    escapechar=dial["escapechar"],
                    engine="python",
                )
                source_info = f"{enc_used}; sep={dial['sep']}"
            elif ext in ["xlsx", "xls", "xlsb"]:
                df = process_excel_file(file, ext)
                source_info = "excel"
            else:
                st.error("Formato de arquivo não suportado para estoque esperado.")
                return None, None

            # Importante: NÃO obrigamos 'EAN'/'ESTOQUE' aqui;
            # o mapeamento/renomeação acontece na UI do rfdash.py
            return df, f"estoque_esperado[{source_info}]"

        st.error("Tipo esperado desconhecido.")
        return None, None

    except pd.errors.EmptyDataError:
        st.error(f"O arquivo {expected_type} está vazio ou inválido.")
        return None, None
    except Exception as e:
        st.error(f"Falha ao processar o arquivo {expected_type}: {e}")
        return None, None

# -----------------------------------------------------------------------------
# AgGrid / Tabela
# -----------------------------------------------------------------------------
def configurar_colunas_com_filtros_dinamicos(gb, df):
    texto_keywords = ["EAN", "PRODUTO", "MODELO", "COR", "TAM", "DESCRICAO", "DESCRIÇÃO", "REFERENCIA", "REFERÊNCIA", "NOME"]
    numero_keywords = ["ESTOQUE", "CONTAGEM", "DIVERGÊNCIA", "DIVERGENCIA", "RELIDAS", "QUANTIDADE"]

    for col in df.columns:
        col_norm = unidecode.unidecode(col).upper()
        if any(k in col_norm for k in texto_keywords):
            gb.configure_column(col, filter="agTextColumnFilter")
        elif any(k in col_norm for k in numero_keywords):
            gb.configure_column(col, filter="agNumberColumnFilter")
        else:
            gb.configure_column(col, filter="agTextColumnFilter")

def adicionar_status_visual(df: pd.DataFrame) -> pd.DataFrame:
    if "DIVERGÊNCIA" in df.columns:
        df["STATUS"] = df["DIVERGÊNCIA"].apply(lambda x: "➕ SOBRA" if x > 0 else ("➖ FALTA" if x < 0 else "✅ OK"))
    elif "DIVERGENCIA" in df.columns:
        df["STATUS"] = df["DIVERGENCIA"].apply(lambda x: "➕ SOBRA" if x > 0 else ("➖ FALTA" if x < 0 else "✅ OK"))
    else:
        df["STATUS"] = "N/A"
    return df

def apply_quick_filter(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """
    Aplica o filtro rápido sobre o DF de divergências.
    Opções: 'Tudo' | 'Divergências' | 'Sobra' | 'Falta'
    """
    if df is None or df.empty or "DIVERGÊNCIA" not in df.columns:
        return df
    if mode == "Divergências":
        return df[df["DIVERGÊNCIA"] != 0]
    if mode == "Sobra":
        return df[df["DIVERGÊNCIA"] > 0]
    if mode == "Falta":
        return df[df["DIVERGÊNCIA"] < 0]
    return df  # Tudo


def display_data_table(df: pd.DataFrame, key: str | None = None) -> pd.DataFrame:
    """
    Mostra a tabela com AgGrid e retorna o DataFrame filtrado/ordenado pelo usuário.
    Aceita 'key' para forçar remontagem da grade (reset de filtros/sort internos).
    """
    df = adicionar_status_visual(df.copy())
    gb = GridOptionsBuilder.from_dataframe(df)

    gb.configure_pagination(enabled=False)
    gb.configure_side_bar(True)
    gb.configure_selection("multiple")

    for col in df.columns:
        gb.configure_column(col, cellStyle={"borderRight": "1px solid #4e4e4e", "padding": "6px"})
        gb.configure_column(col, filter="agSetColumnFilter", filter_params={"excelMode": "windows"})

    gb.configure_column("STATUS", header_name="STATUS", cellStyle={"fontWeight": "bold", "textAlign": "center"})
    gb.configure_default_column(
        floatingFilter=True, value=True, enableRowGroup=True, editable=False,
        groupable=True, filter=True, sortable=True
    )
    configurar_colunas_com_filtros_dinamicos(gb, df)
    gb.configure_grid_options(
        domLayout="normal", rowHeight=30, headerHeight=42,
        enableEnterpriseModules=True, enableRangeSelection=True,
        suppressExcelExport=False, suppressMultiSort=False, enableCharts=True
    )

    grid_options = gb.build()
    grid_options["enableRangeSelection"] = True
    grid_options["enableCharts"] = True
    grid_options["enableStatusBar"] = True
    grid_options["groupDefaultExpanded"] = -1
    grid_options["groupMultiAutoColumn"] = True
    grid_options["gridStyle"] = {
        "border": "1px solid #4e4e4e", "borderColor": "#f2ede3",
        "borderWidth": "1px", "borderStyle": "solid", "borderCollapse": "collapse",
    }
    grid_options["rowStyle"] = {"borderBottom": "1px solid #4e4e4e"}
    grid_options["rowHeight"] = 30
    grid_options["headerHeight"] = 45
    grid_options["autoGroupColumnDef"] = {
        "headerName": "Produtos Agrupados",
        "minWidth": 300,
        "cellRendererParams": {"suppressCount": False, "checkbox": True},
    }

    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.FILTERING_CHANGED,
        fit_columns_on_grid_load=True,
        theme="material",
        enable_enterprise_modules=True,
        height=750,
        width="100%",
        reload_data=True,
        allow_unsafe_jscode=True,
        key=key,  # <-- importante para “resetar” a grade quando o filtro rápido mudar
    )

    return pd.DataFrame(grid_response["data"])

# -----------------------------------------------------------------------------
# Resumo (cards Streamlit)
# -----------------------------------------------------------------------------
def show_summary(discrepancies: pd.DataFrame):
    total_estoque = int(discrepancies["ESTOQUE"].sum())
    total_contagem_rfid = int(discrepancies["CONTAGEM"].sum())
    total_div_pos = int(discrepancies[discrepancies["DIVERGÊNCIA"] > 0]["DIVERGÊNCIA"].sum())
    total_div_neg = int(discrepancies[discrepancies["DIVERGÊNCIA"] < 0]["DIVERGÊNCIA"].sum())
    total_div_abs = int(discrepancies["DIVERGÊNCIA"].abs().sum())

    st.subheader("Resumo Total")
    c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
    with c1:
        st.metric("Total Esperado em Estoque", total_estoque, border=True)
    with c2:
        st.metric("Total da Contagem com RFID", total_contagem_rfid, border=True)
    with c3:
        st.metric("Sobra", total_div_pos, border=True)
    with c4:
        st.metric("Falta", total_div_neg, border=True)
    with c5:
        st.metric("Divergência absoluta", total_div_abs, border=True)

# -----------------------------------------------------------------------------
# Cálculo de discrepâncias (mantém nomes e lógica originais do seu app)
# -----------------------------------------------------------------------------
def calculate_discrepancies(expected: pd.DataFrame, counted: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """
    Calcula discrepâncias entre estoque esperado e contagem.
    Espera colunas:
      - expected: 'EAN', 'ESTOQUE' (+ opcionais)
      - counted:  'EAN', 'CONTAGEM'
    Sai com: 'DIVERGÊNCIA' e 'PEÇAS A SEREM RELIDAS'
    """
    if "EAN" not in expected.columns or "EAN" not in counted.columns:
        st.error("A coluna 'EAN' não foi encontrada em um dos arquivos.")
        return pd.DataFrame()

    expected = expected.copy()
    counted = counted.copy()
    expected["EAN"] = expected["EAN"].astype(str)
    counted["EAN"] = counted["EAN"].astype(str)

    counted_agg = counted.groupby("EAN", as_index=False).agg({"CONTAGEM": "sum"})

    if "ESTOQUE" not in expected.columns:
        expected["ESTOQUE"] = 0

    discrepancies = pd.merge(expected, counted_agg, on="EAN", how="outer")
    discrepancies["ESTOQUE"] = pd.to_numeric(discrepancies["ESTOQUE"], errors="coerce").fillna(0).astype(int)
    discrepancies["CONTAGEM"] = pd.to_numeric(discrepancies["CONTAGEM"], errors="coerce").fillna(0).astype(int)

    discrepancies["DIVERGÊNCIA"] = discrepancies["CONTAGEM"] - discrepancies["ESTOQUE"]
    discrepancies["PEÇAS A SEREM RELIDAS"] = discrepancies.apply(
        lambda r: max(r["ESTOQUE"], r["CONTAGEM"]) if r["DIVERGÊNCIA"] != 0 else 0, axis=1
    )
    return discrepancies

# -----------------------------------------------------------------------------
# PDF em memória — AGORA COM SELEÇÃO DE COLUNAS
# -----------------------------------------------------------------------------
_DEFAULT_ORDER = [
    "PRODUTO", "EAN", "REFERENCIA", "DESCRICAO", "COR", "TAM",
    "ESTOQUE", "CONTAGEM", "DIVERGÊNCIA", "PEÇAS A SEREM RELIDAS"
]
_DEFAULT_WIDTHS = {
    "PRODUTO": 0.08, "EAN": 0.10, "REFERENCIA": 0.10, "DESCRICAO": 0.32,
    "COR": 0.10, "TAM": 0.06, "ESTOQUE": 0.06, "CONTAGEM": 0.07, "DIVERGÊNCIA": 0.08,
    "PEÇAS A SEREM RELIDAS": 0.08
}

def pick_pdf_columns_ui(
    df: pd.DataFrame,
    label: str = "Colunas para exportar no PDF:",
    include_status: bool = True,
    key: str = "pdf_cols_main",
) -> list:
    """
    Mostra um multiselect com as colunas do DF *na ordem exibida* e,
    por padrão, já seleciona TODAS elas (experiência de "imprimir a tabela").
    - include_status=False remove a coluna STATUS da lista, se existir.
    - key: permite ter essa UI em mais de um lugar sem conflito.
    """
    # colunas em EXACTAMENTE a mesma ordem do DataFrame que está na grade
    cols = list(df.columns)

    if not include_status:
        cols = [c for c in cols if unidecode.unidecode(c).upper() != "STATUS"]

    # default = todas as colunas visíveis (na mesma ordem)
    default = cols.copy()

    selected = st.multiselect(
        label,
        options=cols,
        default=default,
        key=key,
    )
    return selected

def _compute_col_widths(columns: list) -> list:
    """
    Gera larguras proporcionais para as colunas do PDF.
    Usa mapa padrão para conhecidas e um fallback para desconhecidas.
    """
    widths = []
    for c in columns:
        widths.append(_DEFAULT_WIDTHS.get(c, 0.08))  # fallback
    s = sum(widths) or 1.0
    return [w / s for w in widths]

def add_page_number(canvas, doc, orientation):
    canvas.saveState()
    if orientation.upper().startswith("P"):
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 20, 20, f"Página {doc.page}")
    else:
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[1] - 20, 20, f"Página {doc.page}")
    canvas.restoreState()

# --- helper novo: calcula largura das colunas pelo conteúdo ---
def _auto_col_widths(df: pd.DataFrame, cols: list[str], page_width: float) -> list[float]:
    """
    Estima larguras relativas das colunas com base no tamanho do conteúdo.
    - considera até 1.000 linhas (amostra) p/ velocidade
    - impõe limites min/max por coluna
    - normaliza para somar exatamente a largura disponível
    Retorna uma lista de larguras absolutas (em pontos) para a tabela do ReportLab.
    """
    # limites (fração da página); evita coluna "DESCRICAO" gigante e numéricas minúsculas
    MIN_FRACTION = 0.06
    MAX_FRACTION = 0.38

    # amostra para medir tamanho de texto
    sample = df[cols].astype(str).head(1000)

    weights = []
    for c in cols:
        # peso pelo maior comprimento (título também conta)
        max_len = max(sample[c].map(len).max(), len(str(c)))
        # bônus para campos “textuais”
        cname = unidecode.unidecode(c).upper()
        if any(tok in cname for tok in ["DESC", "PRODUTO", "NOME"]):
            max_len *= 1.3
        # penaliza campos tipicamente numéricos
        if any(tok in cname for tok in ["ESTOQUE", "CONTAGEM", "DIVERG", "QTD", "QTDE"]):
            max_len *= 0.9
        weights.append(max_len or 1)

    # normaliza para 1.0 e aplica limites
    total = float(sum(weights)) or 1.0
    fracs = [w / total for w in weights]
    fracs = [min(MAX_FRACTION, max(MIN_FRACTION, f)) for f in fracs]

    # re-normaliza após clamps
    total2 = sum(fracs)
    fracs = [f / total2 for f in fracs]

    # converte para largura absoluta em pontos
    return [page_width * f for f in fracs]

import re

def _clean_status_for_pdf(text: str) -> str:
    """
    Troca emojis e símbolos não suportados por ASCII.
    Mantém a semântica: + SOBRA, - FALTA, OK.
    """
    s = str(text or "")
    # mapeia símbolos comuns para ASCII
    repl = {
        "🟡": "", "🔴": "", "🟢": "", "✅": "OK",
        "➕": "+", "＋": "+", "\u2795": "+",
        "➖": "-", "－": "-", "\u2796": "-",
        "\u2212": "-",  # minus math
    }
    for k, v in repl.items():
        s = s.replace(k, v)

    # normaliza espaços e garante prefixo correto
    s = re.sub(r"\s+", " ", s).strip()
    up = s.upper()
    if "SOBRA" in up and not s.startswith("+"):
        s = "+ SOBRA"
    elif "FALTA" in up and not s.startswith("-"):
        s = "- FALTA"
    elif "OK" in up:
        s = "OK"
    return s


def generate_pdf_in_memory(
    filtered_df: pd.DataFrame,
    font_size: int,
    orientation: str,
    include_columns: list | None = None
) -> bytes:
    """
    Gera PDF (bytes) com a tabela de divergências.
    - `include_columns`: colunas (e ordem) escolhidas pelo usuário.
    - larguras de coluna calculadas automaticamente conforme o conteúdo.
    """
    from reportlab.lib.pagesizes import A4, landscape, portrait

    # checagens mínimas
    required = ["EAN", "ESTOQUE", "CONTAGEM", "DIVERGÊNCIA"]
    for c in required:
        if c not in filtered_df.columns:
            raise ValueError(f"Coluna obrigatória ausente: {c}")

    # prepara DF
    df = filtered_df.copy().fillna("-")
    if "TAMANHO" in df.columns:  # harmoniza com 'TAM' quando existir
        df = df.rename(columns={"TAMANHO": "TAM"})

    # decide colunas
    DEFAULT_ORDER = [
        "PRODUTO", "EAN", "REFERENCIA", "DESCRICAO", "COR", "TAM",
        "ESTOQUE", "CONTAGEM", "DIVERGÊNCIA", "PEÇAS A SEREM RELIDAS"
    ]
    if include_columns:
        cols = [c for c in include_columns if c in df.columns]
    else:
        cols = [c for c in DEFAULT_ORDER if c in df.columns] or list(df.columns)

    # página
    pagesize = portrait(A4) if orientation.upper().startswith("P") else landscape(A4)
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer, pagesize=pagesize,
        rightMargin=20, leftMargin=20, topMargin=50, bottomMargin=50
    )

    styles = getSampleStyleSheet()
    styles["Title"].alignment = TA_CENTER
    cell_style = ParagraphStyle(
        name="CellStyle", parent=styles["Normal"],
        fontSize=font_size, wordWrap="CJK", leading=font_size + 2
    )

    # título + resumo
    elements = []
    elements.append(Paragraph("Relatório de Divergência de Inventário", styles["Title"]))
    elements.append(Spacer(1, 12))

    total_estoque = int(pd.to_numeric(df["ESTOQUE"], errors="coerce").fillna(0).sum())
    total_contagem = int(pd.to_numeric(df["CONTAGEM"], errors="coerce").fillna(0).sum())
    div = pd.to_numeric(df["DIVERGÊNCIA"], errors="coerce").fillna(0)
    total_div_pos = int(div[div > 0].sum())
    total_div_neg = int(div[div < 0].sum())
    total_div_abs = int(div.abs().sum())

    for linha in [
        f"Total Esperado em Estoque: {total_estoque}",
        f"Total da Contagem: {total_contagem}",
        f"Divergência Positiva (Sobra): {total_div_pos}",
        f"Divergência Negativa (Falta): {total_div_neg}",
        f"Divergência Absoluta: {total_div_abs}",
    ]:
        elements.append(Paragraph(linha, styles["Normal"]))
        elements.append(Spacer(1, 6))
    elements.append(Spacer(1, 12))

    # dados da tabela
    data = [cols]
    for _, row in df.iterrows():
        row_data = []
        for c in cols:
            value = str(row.get(c, "-"))
            if unidecode.unidecode(c).upper() == "STATUS":
                value = _clean_status_for_pdf(value)
            para = Paragraph(value, cell_style)
            row_data.append(para)
        data.append(row_data)

    # larguras (AUTO)
    col_width_values = _auto_col_widths(df, cols, pdf.width)

    table = Table(data, colWidths=col_width_values, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("WORDWRAP", (0, 0), (-1, -1), True),
    ])
    # listras
    for i in range(1, len(data)):
        style.add("BACKGROUND", (0, i), (-1, i),
                  colors.whitesmoke if i % 2 == 0 else colors.lightgrey)
    table.setStyle(style)
    elements.append(table)

    # numeração de página
    pdf.build(
        elements,
        onFirstPage=lambda canv, doc: add_page_number(canv, doc, orientation),
        onLaterPages=lambda canv, doc: add_page_number(canv, doc, orientation),
    )
    buffer.seek(0)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# Dashboard analítico (pyecharts) — assinatura usada no rfdash.py
# -----------------------------------------------------------------------------
def dynamic_dashboard(
    total_estoque: int,
    total_contagem: int,
    total_divergencia_absoluta: int,
    total_pecas_a_serem_relidas: int,
    accuracy_percentage: float,
    total_divergencia_positiva: int,
    total_divergencia_negativa: int,
) -> str:
    accuracy_percentage = round(float(accuracy_percentage), 2)

    gauge = (
        Gauge()
        .add(
            series_name="Acurácia",
            data_pair=[("Acurácia", accuracy_percentage)],
            min_=0,
            max_=100,
            detail_label_opts=opts.GaugeDetailOpts(formatter="{value}%", color="#fff", font_size=26),
        )
        .set_series_opts(
            axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color=[(1, "#fff")], width=10)),
            axistick_opts=opts.AxisTickOpts(is_show=True, length=8, linestyle_opts=opts.LineStyleOpts(is_show=True, color="#fff")),
            axislabel_opts=opts.LabelOpts(is_show=True, color="#fff"),
            splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(is_show=True, width=25, opacity=0.2, color="#fff")),
            label_opts=opts.LabelOpts(is_show=True, color="blue", font_size=50, background_color="white"),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="Acurácia do Inventário", pos_left="center", title_textstyle_opts=opts.TextStyleOpts(color="#fff")),
            legend_opts=opts.LegendOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(formatter="{a} <br/>{b}: {c}%"),
        )
    )

    comparativo_chart = (
        Bar()
        .add_xaxis(["Estoque Esperado", "Contagem Realizada"])
        .add_yaxis("Valores", [total_estoque, total_contagem])
        .set_global_opts(
            title_opts=opts.TitleOpts(title="Comparativo: Estoque x Contagem", pos_left="center", title_textstyle_opts=opts.TextStyleOpts(color="white")),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )

    inner_data = [("Divergência", total_divergencia_absoluta)]
    outer_data = [("Sobra", total_divergencia_positiva), ("Falta", abs(total_divergencia_negativa))]

    nested_pie = (
        Pie(init_opts=opts.InitOpts(width="800px", height="600px"))
        .add("Visão Geral", inner_data, radius=[0, "35%"], label_opts=opts.LabelOpts(position="inner", formatter="{b}: {c}", color="#fff"))
        .add(
            "Detalhamento",
            outer_data,
            radius=["45%", "60%"],
            label_opts=opts.LabelOpts(
                position="outside",
                formatter="{b}: {c} ({d}%)",
                background_color="#eee",
                border_color="#aaa",
                border_width=1,
                border_radius=4,
            ),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="Resumo do Inventário",
                subtitle=f"Acurácia: {accuracy_percentage:.2f}%",
                pos_left="center",
                title_textstyle_opts=opts.TextStyleOpts(color="#fff"),
                subtitle_textstyle_opts=opts.TextStyleOpts(color="#fff"),
            ),
            legend_opts=opts.LegendOpts(pos_left="center", pos_top="90%", textstyle_opts=opts.TextStyleOpts(color="#fff")),
            tooltip_opts=opts.TooltipOpts(trigger="item", formatter="{a} <br/>{b}: {c} ({d}%)"),
        )
    )

    page = Page(layout=Page.SimplePageLayout)
    page.add(gauge)
    page.add(comparativo_chart)
    page.add(nested_pie)
    return page.render_embed()

# -----------------------------------------------------------------------------
# Utilidades diversas
# -----------------------------------------------------------------------------
def generate_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")

def generate_pie_chart(accuracy_percentage: float):
    labels = ["Acurácia", "Inacurácia"]
    values = [accuracy_percentage, 100 - accuracy_percentage]
    return px.pie(values=values, names=labels, title="Acurácia do Inventário")

def save_metrics(metrics: dict, filename: str = "metrics.json"):
    data = []
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            data = []
    converted = {
        k: (int(v) if isinstance(v, (np.integer, int)) else float(v) if isinstance(v, (np.floating, float)) else v)
        for k, v in metrics.items()
    }
    data.append(converted)
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

# -----------------------------------------------------------------------------
# Mapeamento de colunas (estoque esperado)
# -----------------------------------------------------------------------------
def _original_to_normalized_map(columns):
    norm = normalize_column_names(columns)
    to_norm = dict(zip(columns, norm))
    to_orig = dict(zip(norm, columns))
    return to_norm, to_orig

# candidatos (versionados para nomes NORMALIZADOS)
EAN_CANDIDATES = {
    "EAN", "CODBARRAS", "COD_BARRAS", "CODIGO_DE_BARRAS", "CÓDIGO_DE_BARRAS",
    "GTIN", "SKU", "BARCODE", "CODBARRA", "COD_DE_BARRAS",
}
ESTOQUE_CANDIDATES = {
    "ESTOQUE", "QTD", "QTDE", "QUANTIDADE", "QTD_ESTOQUE", "QTD_ATUAL",
    "SALDO", "DISPONIVEL", "DISPONÍVEL", "QTY", "ON_HAND",
}

def suggest_expected_mapping(df: pd.DataFrame):
    """
    Sugere, quando possível, as colunas de EAN e ESTOQUE a partir de sinônimos.
    """
    to_norm, to_orig = _original_to_normalized_map(df.columns)
    ean = est = None
    for c_norm in to_norm.values():
        if ean is None and c_norm in EAN_CANDIDATES:
            ean = to_orig[c_norm]
        if est is None and c_norm in ESTOQUE_CANDIDATES:
            est = to_orig[c_norm]
    return ean, est

def pick_expected_columns_ui(df: pd.DataFrame):
    """
    UI (Streamlit) para o usuário escolher quais colunas são EAN e ESTOQUE.
    """
    st.caption("Mapeie as colunas do arquivo de **Estoque Esperado**:")
    sug_ean, sug_est = suggest_expected_mapping(df)
    c1, c2 = st.columns(2)
    with c1:
        ean_col = st.selectbox(
            "Coluna que contém o **EAN**",
            list(df.columns),
            index=(list(df.columns).index(sug_ean) if sug_ean in df.columns else 0),
            key="map_col_ean",
        )
    with c2:
        est_col = st.selectbox(
            "Coluna que contém o **ESTOQUE**",
            list(df.columns),
            index=(list(df.columns).index(sug_est) if sug_est in df.columns else 0),
            key="map_col_estoque",
        )
    return {"EAN": ean_col, "ESTOQUE": est_col}

def standardize_expected_df(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """
    Renomeia as colunas selecionadas para 'EAN' e 'ESTOQUE' e normaliza tipos.
    """
    if not mapping or "EAN" not in mapping or "ESTOQUE" not in mapping:
        raise ValueError("Mapeamento inválido. Selecione as colunas de EAN e ESTOQUE.")

    src_ean = mapping["EAN"]
    src_est = mapping["ESTOQUE"]
    if src_ean not in df.columns or src_est not in df.columns:
        raise ValueError("As colunas selecionadas não existem no arquivo.")

    out = df.rename(columns={src_ean: "EAN", src_est: "ESTOQUE"}).copy()
    out["EAN"] = out["EAN"].astype(str).str.strip()
    out["ESTOQUE"] = pd.to_numeric(out["ESTOQUE"], errors="coerce").fillna(0).astype(int)
    return out

# --- cache para bytes do PDF (1 clique) ---
@st.cache_data(show_spinner=False)
def build_pdf_bytes_cached(
    df: pd.DataFrame,
    include_columns_tuple: tuple,
    font_size: int,
    orientation: str,
) -> bytes:
    # reaproveita sua função já robusta (largura auto, colunas do usuário)
    return generate_pdf_in_memory(
        df, font_size=font_size, orientation=orientation,
        include_columns=list(include_columns_tuple) if include_columns_tuple else None
    )

def render_single_click_pdf_button(
    df: pd.DataFrame,
    include_columns: list | None,
    label: str = "Gerar e Baixar PDF",
    font_size: int = 8,
    orientation: str = "L",
    key: str = "btn_pdf_oneclick",
    file_name: str | None = None,
):
    """
    Mostra UM botão que já baixa o PDF.
    - Gera os bytes antes de renderizar o botão (com cache) e mostra spinner.
    - Respeita as colunas selecionadas e largura automática da página.
    """
    if file_name is None:
        file_name = f"relatorio_divergencia_{generate_timestamp()}.pdf"

    # prepara os bytes (usa cache; rápido em reruns com mesmo DF/colunas)
    with st.spinner("Preparando PDF..."):
        pdf_bytes = build_pdf_bytes_cached(
            df.copy(), tuple(include_columns or []), font_size, orientation
        )

    # único botão visível para o usuário
    st.download_button(
        label=label,
        data=pdf_bytes,
        file_name=file_name,
        mime="application/pdf",
        key=key,
        use_container_width=True,
    )


import base64
import streamlit.components.v1 as components

def one_click_generate_and_download_pdf(
    df: pd.DataFrame,
    include_columns: list | None,
    label: str = "Gerar e Baixar PDF",
    font_size: int = 8,
    orientation: str = "L",
    key: str = "oneclick_pdf",
    file_name: str | None = None,
):
    """
    Um único botão que gera o PDF no clique e inicia o download.
    - Usa Blob + URL.createObjectURL (mais estável que 'data:' em iframes)
    - Mantém um botão de download fallback se o auto-download for bloqueado
    """
    if file_name is None:
        file_name = f"relatorio_divergencia_{generate_timestamp()}.pdf"

    if st.button(label, key=key):
        with st.spinner("Gerando o PDF..."):
            pdf_bytes = generate_pdf_in_memory(
                df.copy(),
                font_size=font_size,
                orientation=orientation,
                include_columns=include_columns,
            )

        # Dispara download via Blob (JS)
        b64 = base64.b64encode(pdf_bytes).decode()
        components.html(
            f"""
<script>
(function() {{
  const b64 = "{b64}";
  const byteChars = atob(b64);
  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) {{
    byteNumbers[i] = byteChars.charCodeAt(i);
  }}
  const byteArray = new Uint8Array(byteNumbers);
  const blob = new Blob([byteArray], {{ type: "application/pdf" }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = "{file_name}";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}})();
</script>
            """,
            height=0,
        )

        # Fallback confiável (se o navegador bloquear o auto-click)
        st.download_button(
            "Baixar PDF (caso não tenha baixado automaticamente)",
            data=pdf_bytes,
            file_name=file_name,
            mime="application/pdf",
            key=f"{key}_fallback",
            use_container_width=True,
        )