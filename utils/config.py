import streamlit as st
import pandas as pd
from pyxlsb import open_workbook as open_xlsb
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from datetime import datetime
import unidecode
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
import time
from io import BytesIO
import plotly.express as px
import tempfile
import json
import os
import numpy as np
import hashlib
from pyecharts.charts import Pie, Liquid, Bar, Gauge, Page
from pyecharts import options as opts
from st_aggrid.shared import JsCode
import streamlit.components.v1 as components

def gerar_hash(file):
    """
    Gera um hash MD5 do conteúdo do arquivo para uso no cache.
    """
    file.seek(0)
    file_content = file.read()
    file.seek(0)
    return hashlib.md5(file_content).hexdigest()


def show_temporary_success(message_key, message_text, duration=3):
    """
    Exibe uma mensagem de sucesso temporária apenas uma vez, utilizando `st.session_state`.
    - message_key: Identificador único da mensagem.
    - message_text: Texto a ser exibido.
    - duration: Duração da mensagem (em segundos).
    """
    # Inicializar a chave no session_state se não estiver presente
    if message_key not in st.session_state.success_messages:
        st.session_state.success_messages[message_key] = False  # Inicialmente, mensagem não exibida

    # Exibir a mensagem apenas se ainda não foi exibida
    if not st.session_state.success_messages[message_key]:
        with st.container():  # Usar container para garantir atualização
            placeholder = st.empty()
            placeholder.success(message_text)  # Exibe a mensagem
            time.sleep(duration)  # Aguarda a duração definida
            placeholder.empty()  # Remove a mensagem
        st.session_state.success_messages[message_key] = True  # Marcar como exibida

# Função para normalizar nomes de colunas
def normalize_column_names(columns):
    return [unidecode.unidecode(col).strip().upper().replace(' ', '_') for col in columns]

def process_excel_file(file, file_extension):
    try:
        # Para arquivos .xlsx
        if file_extension == 'xlsx':
            dataframe = pd.read_excel(file, engine='openpyxl')
        # Para arquivos .xls
        elif file_extension == 'xls':
            dataframe = pd.read_excel(file, engine='xlrd')
        # Para arquivos .xlsb (Binários do Excel)
        elif file_extension == 'xlsb':
            with open_xlsb(file) as wb:
                sheets = wb.sheets
                df_list = []
                for sheet in sheets:
                    with wb.get_sheet(sheet) as ws:
                        df = pd.DataFrame([row for row in ws.rows()])
                        df_list.append(df)
                dataframe = pd.concat(df_list, ignore_index=True)
        else:
            raise ValueError(f"Formato de arquivo não suportado: {file_extension}")
    except Exception as e:
        raise ValueError(f"Erro ao processar o arquivo: {e}")

    return dataframe

@st.cache_data(show_spinner="Processando arquivo...")
def processar_arquivo_com_hash(hash_value, content, file_extension, expected_type):
    from io import BytesIO, StringIO

    if file_extension == 'csv':
        df = pd.read_csv(StringIO(content.decode('utf-8')), dtype=str)
    elif file_extension in ['xls', 'xlsx']:
        df = pd.read_excel(BytesIO(content), engine='openpyxl')
    elif file_extension == 'txt':
        df = pd.read_csv(StringIO(content.decode('utf-8')), delimiter=',', header=None, dtype=str)
    else:
        return None, None

    # Normalizar e validar
    df.columns = normalize_column_names(df.columns) if df.shape[1] > 1 else df.columns

    if expected_type == "estoque_esperado":
        if not {'EAN', 'ESTOQUE'}.issubset(set(df.columns)):
            return None, None
    elif expected_type == "contagem":
        if df.shape[1] == 2:
            df.columns = ['EAN', 'CONTAGEM']
            df['EAN'] = df['EAN'].astype(str)
            df['CONTAGEM'] = pd.to_numeric(df['CONTAGEM'].str.replace(',', '.'), errors='coerce').fillna(0).astype(int)
        elif df.shape[1] == 1:
            df.columns = ['EAN']
            df['CONTAGEM'] = 1
            df = df.groupby('EAN', as_index=False).agg({'CONTAGEM': 'sum'})
        else:
            return None, None

    return df, expected_type

# @st.cache_data(show_spinner=True)
# def process_file_cached(content, extension, expected_type):
#     """
#     Função cacheada que processa o conteúdo do arquivo com base no tipo e extensão.
#     """
#     from io import BytesIO, StringIO

#     try:
#         if extension == 'csv':
#             dataframe = pd.read_csv(StringIO(content.decode('utf-8')), dtype=str)
#         elif extension in ['xlsx', 'xls', 'xlsb']:
#             dataframe = process_excel_file(BytesIO(content), extension)
#         elif extension == 'txt':
#             dataframe = pd.read_csv(StringIO(content.decode('utf-8')), delimiter=',', header=None, dtype=str)
#         else:
#             return None, f"Formato de arquivo não suportado: {extension}"

#         # Normalização para arquivos com cabeçalho
#         if extension in ['csv', 'xlsx', 'xls', 'xlsb']:
#             dataframe.columns = normalize_column_names(dataframe.columns)

#         # Validação para estoque_esperado
#         if expected_type == 'estoque_esperado':
#             required_columns = {'EAN', 'ESTOQUE'}
#             if not required_columns.issubset(set(dataframe.columns)):
#                 return None, f"O arquivo '{expected_type}' precisa conter: {', '.join(required_columns)}."

#         # Tratamento para contagem
#         elif expected_type == 'contagem':
#             num_columns = dataframe.shape[1]
#             if num_columns == 2:
#                 dataframe.columns = ['EAN', 'CONTAGEM']
#                 dataframe['EAN'] = dataframe['EAN'].astype(str)
#                 dataframe['CONTAGEM'] = pd.to_numeric(dataframe['CONTAGEM'].str.replace(',', '.'), errors='coerce').fillna(0).astype(int)
#             elif num_columns == 1:
#                 dataframe.columns = ['EAN']
#                 dataframe['CONTAGEM'] = 1
#                 dataframe = dataframe.groupby('EAN', as_index=False).agg({'CONTAGEM': 'sum'})
#             else:
#                 return None, "O arquivo de contagem deve ter uma ou duas colunas."

#         return dataframe, None

#     except pd.errors.EmptyDataError:
#         return None, f"O arquivo '{expected_type}' está vazio ou inválido."
#     except Exception as e:
#         return None, f"Erro ao ler o arquivo '{expected_type}': {e}"

# Função para processar o upload de arquivos
# def process_upload(file, expected_type):
#     """
#     Processa o arquivo carregado e aplica o tratamento específico baseado no tipo esperado.
#     """
#     if file is None:
#         return None, None

#     # Detectar a extensão do arquivo
#     file_extension = file.name.split('.')[-1].lower()

#     try:
#         if file_extension == 'csv':
#             # Ler arquivos CSV diretamente com o pandas
#             file.seek(0)  # Certifique-se de que o ponteiro do arquivo está no início
#             dataframe = pd.read_csv(file, dtype=str)  # Forçar tudo como string para evitar problemas de tipos
#         elif file_extension in ['xlsx', 'xls', 'xlsb']:
#             # Processar arquivos Excel
#             dataframe = process_excel_file(file, file_extension)
#         elif file_extension == 'txt':
#             # Ler arquivos TXT como arquivos delimitados (tabulação por padrão)
#             file.seek(0)  # Certifique-se de que o ponteiro do arquivo está no início
#             dataframe = pd.read_csv(file, delimiter=',', header=None, dtype=str)
#         else:
#             st.error("Formato de arquivo não suportado. Use .csv, .xls, .xlsx, .xlsb ou .txt.")
#             return None, None

#         # Normalizar os nomes das colunas para arquivos com cabeçalho
#         if file_extension in ['csv', 'xlsx', 'xls', 'xlsb']:
#             dataframe.columns = normalize_column_names(dataframe.columns)

#         # Verificar as colunas obrigatórias para estoque_esperado
#         if expected_type == 'estoque_esperado':
#             required_columns = {'EAN', 'ESTOQUE'}
#             if not required_columns.issubset(set(dataframe.columns)):
#                 st.error(f"O arquivo {expected_type} precisa conter as colunas obrigatórias: {', '.join(required_columns)}.")
#                 return None, None

#         # Tratamento para arquivo de contagem
#         elif expected_type == 'contagem':
#             num_columns = dataframe.shape[1]
#             if num_columns == 2:  # Duas colunas
#                 dataframe.columns = ['EAN', 'CONTAGEM']
#                 dataframe['EAN'] = dataframe['EAN'].astype(str)
#                 dataframe['CONTAGEM'] = pd.to_numeric(dataframe['CONTAGEM'].str.replace(',', '.'), errors='coerce').fillna(0).astype(int)
#             elif num_columns == 1:  # Uma coluna
#                 dataframe.columns = ['EAN']
#                 dataframe['CONTAGEM'] = 1
#                 dataframe = dataframe.groupby('EAN', as_index=False).agg({'CONTAGEM': 'sum'})
#             else:  # Qualquer outro número de colunas é inválido
#                 st.error("O arquivo de contagem deve ter uma ou duas colunas.")
#                 return None, None

#     except pd.errors.EmptyDataError:
#         st.error(f"O arquivo {expected_type} está vazio ou possui um formato inválido.")
#         return None, None
#     except Exception as e:
#         st.error(f"Erro ao ler o arquivo {expected_type}: {e}")
#         return None, None

#     return dataframe, expected_type

def process_upload(file, expected_type):
    """
    Processa o arquivo carregado e aplica o tratamento específico baseado no tipo esperado.
    - Para arquivos de contagem: assume SEM cabeçalho. Se tiver 1 coluna = EANs empilhados; 2 colunas = EAN, QUANTIDADE
    - Para estoque_esperado: assume COM cabeçalho padrão.
    """
    if file is None:
        return None, None

    file_extension = file.name.split('.')[-1].lower()

    try:
        # Arquivo de CONTAGEM (sem cabeçalho!)
        if expected_type == 'contagem':
            file.seek(0)
            dataframe = pd.read_csv(file, delimiter=',', header=None, dtype=str)

            num_columns = dataframe.shape[1]

            if num_columns == 2:
                dataframe.columns = ['EAN', 'CONTAGEM']
                dataframe['EAN'] = dataframe['EAN'].astype(str).str.strip()
                dataframe['CONTAGEM'] = pd.to_numeric(
                    dataframe['CONTAGEM'].str.replace(',', '.'), errors='coerce'
                ).fillna(0).astype(int)

            elif num_columns == 1:
                dataframe.columns = ['EAN']
                dataframe['EAN'] = dataframe['EAN'].astype(str).str.strip()
                dataframe['CONTAGEM'] = 1
                dataframe = dataframe.groupby('EAN', as_index=False).agg({'CONTAGEM': 'sum'})

            else:
                st.error("O arquivo de contagem deve conter uma ou duas colunas.")
                return None, None

        # Arquivo de ESTOQUE ESPERADO (com cabeçalho!)
        elif expected_type == 'estoque_esperado':
            if file_extension == 'csv':
                file.seek(0)
                dataframe = pd.read_csv(file, dtype=str)
            elif file_extension in ['xlsx', 'xls', 'xlsb']:
                dataframe = process_excel_file(file, file_extension)
            else:
                st.error("Formato de arquivo não suportado para estoque esperado.")
                return None, None

            # Normaliza nomes das colunas
            dataframe.columns = normalize_column_names(dataframe.columns)

            required_columns = {'EAN', 'ESTOQUE'}
            if not required_columns.issubset(set(dataframe.columns)):
                st.error(f"O arquivo {expected_type} precisa conter as colunas obrigatórias: {', '.join(required_columns)}.")
                return None, None

    except pd.errors.EmptyDataError:
        st.error(f"O arquivo {expected_type} está vazio ou possui um formato inválido.")
        return None, None
    except Exception as e:
        st.error(f"Erro ao ler o arquivo {expected_type}: {e}")
        return None, None

    return dataframe, expected_type


# def process_upload(file, expected_type):
#     if file is None:
#         return None, None

#     # Detectar extensão
#     file_extension = file.name.split('.')[-1].lower()

#     # Gerar hash do conteúdo do arquivo para usar no cache
#     file_hash = gerar_hash(file)

#     # Recarregar conteúdo e chamar a função cacheada
#     file.seek(0)
#     content = file.read()
#     file.seek(0)

#     dataframe, error = process_file_cached(content, file_extension, expected_type)

#     if error:
#         st.error(error)
#         return None, None

#     return dataframe, expected_type


# Função para salvar métricas
def save_metrics(metrics, filename="metrics.json"):
    data = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            st.error("Erro ao carregar o arquivo de métricas. Inicializando um novo arquivo.")
            data = []

    # Convertendo os valores do dicionário metrics para tipos de dados do Python
    converted_metrics = {k: (int(v) if isinstance(v, (np.integer, int)) else float(v) if isinstance(v, (np.floating, float)) else v) for k, v in metrics.items()}
    
    data.append(converted_metrics)

    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# Função para gerar um timestamp
def generate_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M")

# Função para adicionar número de página no PDF
def add_page_number(canvas, doc, orientation):
    """
    Função para adicionar o número da página no rodapé direito.
    """
    width, height = A4 if orientation == "P" else A4[::-1]
    page_number_text = f"{doc.page}"
    canvas.drawRightString(width - 30, 35, page_number_text)  # Ajustado para alinhar no canto direito
def grafico_resumo_inventario():
    # Exemplo de dados (ajuste conforme a sua lógica)
    contagem_total = 41459
    divergencia_total = 218  # Sobra + Falta
    contagem_correta = contagem_total - divergencia_total  # Exemplo
    sobra = 207
    falta = 11
    pecas_sem_relidas = 2609

    # Dados para o anel interno (visão geral)
    inner_data = [
        ("Contagem Correta", contagem_correta),
        ("Não Contado", pecas_sem_relidas),
        ("Divergência", divergencia_total),
    ]

    # Dados para o anel externo (detalhamento)
    # Neste exemplo, detalhamos apenas a divergência
    outer_data = [
        ("Contagem Correta", contagem_correta),
        ("Não Contado", pecas_sem_relidas),
        ("Sobra", sobra),
        ("Falta", falta),
    ]

    # Configuração do rich text para os labels externos
    rich_formatter = {
        "a": {"color": "#999", "lineHeight": 22, "align": "center"},
        "abg": {
            "backgroundColor": "#e3e3e3",
            "width": "100%",
            "align": "right",
            "height": 22,
            "borderRadius": [4, 4, 0, 0],
        },
        "hr": {
            "borderColor": "#aaa",
            "width": "100%",
            "borderWidth": 0.5,
            "height": 0,
        },
        "b": {"fontSize": 16, "lineHeight": 33},
        "per": {
            "color": "#eee",
            "backgroundColor": "#334455",
            "padding": [2, 4],
            "borderRadius": 2,
        },
    }

    pie = (
        Pie(init_opts=opts.InitOpts(width="800px", height="800px", theme="dark"))
        # Anel Interno: visão geral
        .add(
            series_name="Visão Geral",
            data_pair=inner_data,
            radius=[0, "35%"],
            label_opts=opts.LabelOpts(
                position="inner",
                formatter="{b}: {c}",
                color="#fff"
            ),
        )
        # Anel Externo: detalhamento com labels formatados (caixinhas flutuantes)
        .add(
            series_name="Detalhamento",
            data_pair=outer_data,
            radius=["45%", "60%"],
            label_opts=opts.LabelOpts(
                position="outside",
                formatter=(
                    "{a|{a}}{abg|}\n{hr|}\n {b|{b}: }{c}  {per|{d}%}  "
                ),
                background_color="#101010",
                border_color="#aaa",
                border_width=1,
                border_radius=4,
                rich=rich_formatter,
            ),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="Resumo do Inventário",
                subtitle="Acurácia: 99.47%",
                pos_left="center",
                title_textstyle_opts=opts.TextStyleOpts(color="#fff"),
                subtitle_textstyle_opts=opts.TextStyleOpts(color="#fff"),
            ),
            legend_opts=opts.LegendOpts(
                pos_left="center",
                pos_top="90%",
                textstyle_opts=opts.TextStyleOpts(color="#fff"),
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="item",
                formatter="{a} <br/>{b}: {c} ({d}%)"
            ),
        )
    )
    return pie.render_embed()

# def generate_pdf(filtered_df, font_size, orientation):
#     from reportlab.lib.pagesizes import A4, landscape, portrait
#     # Colunas obrigatórias
#     required_columns = ['EAN', 'ESTOQUE', 'CONTAGEM', 'DIVERGÊNCIA']
#     missing_columns = [col for col in required_columns if col not in filtered_df.columns]
#     if missing_columns:
#         st.error(f"Colunas ausentes no DataFrame: {', '.join(missing_columns)}. Não é possível gerar o PDF.")
#         return None

#     # Substituir valores NaN por '-'
#     filtered_df = filtered_df.fillna('-')

#     # Renomear a coluna 'TAMANHO' para 'TAM' se existir
#     if 'TAMANHO' in filtered_df.columns:
#         filtered_df = filtered_df.rename(columns={'TAMANHO': 'TAM'})

#     # Remover a coluna 'PEÇAS A SEREM RELIDAS' se existir
#     if 'PEÇAS A SEREM RELIDAS' in filtered_df.columns:
#         filtered_df = filtered_df.drop(columns=['PEÇAS A SEREM RELIDAS'])

#     # Criar um arquivo temporário para o PDF
#     with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
#         pdf_output_path = tmp_pdf.name

#     # Definir a orientação e tamanho da página
#     if orientation == "P":
#         pagesize = portrait(A4)
#     else:
#         pagesize = landscape(A4)

#     pdf = SimpleDocTemplate(
#         pdf_output_path,
#         pagesize=pagesize,
#         rightMargin=20,
#         leftMargin=20,
#         topMargin=50,
#         bottomMargin=50
#     )

#     # Estilo de texto
#     styles = getSampleStyleSheet()
#     styles["Title"].alignment = TA_CENTER

#     # Estilo para as células da tabela
#     cell_style = ParagraphStyle(
#         name='CellStyle',
#         parent=styles['Normal'],
#         fontSize=font_size,
#         wordWrap='CJK',
#         leading=font_size + 2,  # Espaçamento entre linhas
#     )

#     # Cabeçalho da tabela e colunas a incluir
#     col_widths = {
#         'PRODUTO': 0.08,
#         'EAN': 0.10,
#         'REFERENCIA': 0.10,
#         'DESCRICAO': 0.32,
#         'COR': 0.10,
#         'TAM': 0.06,
#         'ESTOQUE': 0.06,
#         'CONTAGEM': 0.07,
#         'DIVERGÊNCIA': 0.08
#     }

#     # Filtrar apenas as colunas presentes no DataFrame
#     columns_to_include = [col for col in ['PRODUTO', 'EAN', 'REFERENCIA', 'DESCRICAO', 'COR', 'TAM', 'ESTOQUE', 'CONTAGEM', 'DIVERGÊNCIA'] if col in filtered_df.columns]
#     headers = columns_to_include

#     # Ajustar col_widths de acordo com as colunas presentes
#     col_widths_in_use = {col: col_widths[col] for col in columns_to_include}

#     # Normalizar col_widths_in_use para que a soma seja 1
#     total_width = sum(col_widths_in_use.values())
#     col_widths_in_use = {col: width / total_width for col, width in col_widths_in_use.items()}

#     # Calcular as larguras reais das colunas
#     page_width = pdf.width
#     col_width_values = [page_width * col_widths_in_use[col] for col in columns_to_include]

#     # Lista de elementos a serem adicionados no PDF
#     elements = []
#     elements.append(Paragraph("Relatório de Divergência de Inventário", styles['Title']))
#     elements.append(Spacer(1, 12))

#     # **Adicionar o Resumo ao PDF**
#     # Calcular os valores do resumo
#     if not filtered_df.empty:
#         total_estoque = int(filtered_df['ESTOQUE'].astype(float).sum())
#         total_contagem = int(filtered_df['CONTAGEM'].astype(float).sum())
#         total_divergencia_positiva = int(filtered_df[filtered_df['DIVERGÊNCIA'].astype(float) > 0]['DIVERGÊNCIA'].astype(float).sum())
#         total_divergencia_negativa = int(filtered_df[filtered_df['DIVERGÊNCIA'].astype(float) < 0]['DIVERGÊNCIA'].astype(float).sum())
#         total_divergencia_absoluta = int(filtered_df['DIVERGÊNCIA'].astype(float).abs().sum())
#     else:
#         total_estoque = total_contagem = total_divergencia_positiva = total_divergencia_negativa = total_divergencia_absoluta = 0

#     # Adicionando o resumo ao PDF
#     resumo = [
#         f"Total Esperado em Estoque: {total_estoque}",
#         f"Total da Contagem: {total_contagem}",
#         f"Divergência Positiva (Sobrando): {total_divergencia_positiva}",
#         f"Divergência Negativa (Faltando): {total_divergencia_negativa}",
#         f"Divergência Absoluta: {total_divergencia_absoluta}"
#     ]

#     for linha in resumo:
#         elements.append(Paragraph(linha, styles['Normal']))
#         elements.append(Spacer(1, 6))

#     elements.append(Spacer(1, 12))

#     # Definir os dados da tabela
#     data = [headers]

#     # Iterar pelas linhas do DataFrame e adicionar ao 'data'
#     for i, row in filtered_df.iterrows():
#         try:
#             row_data = []
#             for col in columns_to_include:
#                 value = str(row[col]) if col in row else '-'
#                 para = Paragraph(value, cell_style)
#                 row_data.append(para)
#             data.append(row_data)
#         except Exception as e:
#             st.error(f"Erro ao processar a linha {i}. Detalhes: {e}")
#             continue

#     # Criar a tabela com os dados e larguras de coluna ajustadas
#     table = Table(data, colWidths=col_width_values, repeatRows=1)

#     # Estilo da tabela
#     style = TableStyle([
#         ('BACKGROUND', (0, 0), (-1, 0), colors.grey),  # Cabeçalho
#         ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
#         ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
#         ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
#         ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#         ('FONTSIZE', (0, 0), (-1, -1), font_size),
#         ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
#         ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#         ('WORDWRAP', (0, 0), (-1, -1), True),
#     ])

#     # Aplicando cores alternadas às linhas de dados
#     for row_index, _ in enumerate(data[1:], start=1):
#         bg_color = colors.whitesmoke if row_index % 2 == 0 else colors.lightgrey
#         style.add('BACKGROUND', (0, row_index), (-1, row_index), bg_color)

#     table.setStyle(style)
#     elements.append(table)

#     # Adicionar rodapé com número de páginas
#     pdf.build(elements, onFirstPage=lambda canv, doc: add_page_number(canv, doc, orientation),
#               onLaterPages=lambda canv, doc: add_page_number(canv, doc, orientation))
#     return pdf_output_path

def add_page_number(canvas, doc, orientation):
    canvas.saveState()
    if orientation == "P":
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 20, 20, f"Página {doc.page}")
    else:
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[1] - 20, 20, f"Página {doc.page}")
    canvas.restoreState()

def generate_pdf_in_memory(filtered_df, font_size, orientation):
    """Versão modificada da generate_pdf que trabalha em memória"""
    # Verificação de colunas obrigatórias
    required_columns = ['EAN', 'ESTOQUE', 'CONTAGEM', 'DIVERGÊNCIA']
    missing_columns = [col for col in required_columns if col not in filtered_df.columns]
    if missing_columns:
        raise ValueError(f"Colunas ausentes no DataFrame: {', '.join(missing_columns)}")

    # Substituir valores NaN por '-'
    filtered_df = filtered_df.fillna('-')

    # Renomear/remover colunas conforme necessário
    if 'TAMANHO' in filtered_df.columns:
        filtered_df = filtered_df.rename(columns={'TAMANHO': 'TAM'})
    if 'PEÇAS A SEREM RELIDAS' in filtered_df.columns:
        filtered_df = filtered_df.drop(columns=['PEÇAS A SEREM RELIDAS'])

    # Criar buffer em memória
    buffer = BytesIO()

    # Definir orientação
    if orientation == "P":
        pagesize = portrait(A4)
    else:
        pagesize = landscape(A4)

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=20,
        leftMargin=20,
        topMargin=50,
        bottomMargin=50
    )

    # Estilos
    styles = getSampleStyleSheet()
    styles["Title"].alignment = TA_CENTER

    cell_style = ParagraphStyle(
        name='CellStyle',
        parent=styles['Normal'],
        fontSize=font_size,
        wordWrap='CJK',
        leading=font_size + 2,
    )

    # Configurações de colunas
    col_widths = {
        'PRODUTO': 0.08,
        'EAN': 0.10,
        'REFERENCIA': 0.10,
        'DESCRICAO': 0.32,
        'COR': 0.10,
        'TAM': 0.06,
        'ESTOQUE': 0.06,
        'CONTAGEM': 0.07,
        'DIVERGÊNCIA': 0.08
    }

    columns_to_include = [col for col in ['PRODUTO', 'EAN', 'REFERENCIA', 'DESCRICAO', 'COR', 'TAM', 'ESTOQUE', 'CONTAGEM', 'DIVERGÊNCIA'] if col in filtered_df.columns]
    headers = columns_to_include

    # Ajustar larguras das colunas
    col_widths_in_use = {col: col_widths[col] for col in columns_to_include}
    total_width = sum(col_widths_in_use.values())
    col_widths_in_use = {col: width / total_width for col, width in col_widths_in_use.items()}
    col_width_values = [pdf.width * col_widths_in_use[col] for col in columns_to_include]

    # Elementos do PDF
    elements = []
    elements.append(Paragraph("Relatório de Divergência de Inventário", styles['Title']))
    elements.append(Spacer(1, 12))

    # Adicionar resumo
    if not filtered_df.empty:
        total_estoque = int(filtered_df['ESTOQUE'].astype(float).sum())
        total_contagem = int(filtered_df['CONTAGEM'].astype(float).sum())
        total_divergencia_positiva = int(filtered_df[filtered_df['DIVERGÊNCIA'].astype(float) > 0]['DIVERGÊNCIA'].astype(float).sum())
        total_divergencia_negativa = int(filtered_df[filtered_df['DIVERGÊNCIA'].astype(float) < 0]['DIVERGÊNCIA'].astype(float).sum())
        total_divergencia_absoluta = int(filtered_df['DIVERGÊNCIA'].astype(float).abs().sum())
    else:
        total_estoque = total_contagem = total_divergencia_positiva = total_divergencia_negativa = total_divergencia_absoluta = 0

    resumo = [
        f"Total Esperado em Estoque: {total_estoque}",
        f"Total da Contagem: {total_contagem}",
        f"Divergência Positiva (Sobrando): {total_divergencia_positiva}",
        f"Divergência Negativa (Faltando): {total_divergencia_negativa}",
        f"Divergência Absoluta: {total_divergencia_absoluta}"
    ]

    for linha in resumo:
        elements.append(Paragraph(linha, styles['Normal']))
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 12))

    # Dados da tabela
    data = [headers]
    for i, row in filtered_df.iterrows():
        try:
            row_data = []
            for col in columns_to_include:
                value = str(row[col]) if col in row else '-'
                para = Paragraph(value, cell_style)
                row_data.append(para)
            data.append(row_data)
        except Exception as e:
            raise ValueError(f"Erro ao processar a linha {i}. Detalhes: {e}")

    table = Table(data, colWidths=col_width_values, repeatRows=1)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), font_size),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('WORDWRAP', (0, 0), (-1, -1), True),
    ])

    for row_index, _ in enumerate(data[1:], start=1):
        bg_color = colors.whitesmoke if row_index % 2 == 0 else colors.lightgrey
        style.add('BACKGROUND', (0, row_index), (-1, row_index), bg_color)

    table.setStyle(style)
    elements.append(table)

    # Construir PDF
    pdf.build(elements, 
              onFirstPage=lambda canv, doc: add_page_number(canv, doc, orientation),
              onLaterPages=lambda canv, doc: add_page_number(canv, doc, orientation))
    
    buffer.seek(0)
    return buffer.getvalue()

def generate_liquid_chart(accuracy_percentage: float) -> str:
    """
    Gera um gráfico Liquid usando pyecharts para representar a acurácia do inventário.
    
    Parâmetros:
        accuracy_percentage (float): Acurácia em porcentagem (0 a 100).
    
    Retorna:
        str: HTML embed do gráfico.
    """
    # Converter a porcentagem em uma razão (0 a 1)
    ratio = accuracy_percentage /100
    
    # Criar o gráfico Liquid
    liquid_chart = (
        Liquid(init_opts=opts.InitOpts(width="550px", height="550px",is_horizontal_center=True))
        .add(shape="circle",  # Formato do gráfico
            is_animation=True,

            outline_border_distance=16,  # Desativar animação
            series_name="Acurácia",
            data=[ratio],
            is_outline_show=True,  # Remove o contorno, se desejar
            center=["50%", "40%"],
            # label_opts=opts.LabelOpts(formatter="{c*100:.0f}%"),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="Acurácia do Inventário",
                                      pos_left='center',
                                      pos_top='top',
                                      title_textstyle_opts=opts.TextStyleOpts(color="white")),
            tooltip_opts=opts.TooltipOpts(trigger="item"),
        )
    )
    # Retorna o HTML embed do gráfico
    return liquid_chart.render_embed()

# Função para gerar gráfico de pizza
def generate_pie_chart(accuracy_percentage):
    labels = ['Acurácia', 'Inacurácia']
    values = [accuracy_percentage, 100 - accuracy_percentage]
    fig = px.pie(values=values, names=labels, title='Acurácia do Inventário')
    return fig

def configurar_colunas_com_filtros_dinamicos(gb, df):
    # Palavras que sugerem texto
    texto_keywords = ['EAN', 'PRODUTO', 'MODELO', 'COR', 'TAM', 'DESCRIÇÃO', 'REFERÊNCIA', 'NOME']

    # Palavras que sugerem número
    numero_keywords = ['ESTOQUE', 'CONTAGEM', 'DIVERGÊNCIA', 'RELIDAS', 'QUANTIDADE']

    for col in df.columns:
        col_normalized = col.upper()

        if any(keyword in col_normalized for keyword in texto_keywords):
            gb.configure_column(col, filter="agTextColumnFilter")
        elif any(keyword in col_normalized for keyword in numero_keywords):
            gb.configure_column(col, filter="agNumberColumnFilter")
        else:
            # Filtro padrão de texto caso não detecte
            gb.configure_column(col, filter="agTextColumnFilter")


def adicionar_status_visual(df):
    if "DIVERGÊNCIA" in df.columns:
        df["STATUS"] = df["DIVERGÊNCIA"].apply(lambda x:
            "🟡 SOBRA" if x > 0 else "🔴 FALTA" if x < 0 else "✅ OK"
        )
    else:
        df["STATUS"] = "N/A"
    return df

# Função para exibir tabela de dados
def display_data_table(df):
    df = adicionar_status_visual(df)
    gb = GridOptionsBuilder.from_dataframe(df)
    # Estilo direto em JavaScript como string, válido para cellStyle
    # Aplicar cellStyle diretamente como string JS (sem JsCode)
    gb.configure_pagination(enabled=False)  # Desativar paginação
    gb.configure_side_bar(True)
    gb.configure_selection('multiple')
    # gb.configure_column("REFERENCIA", type=["numericColumn"],editable=False,enableRowGroup=True,enablePivot=True,enableValue=True,rowGroup=True)
    # gb.configure_column("COR",type=["textColumn"],editable=False,enableRowGroup=True,enablePivot=True,enableValue=True,rowGroup=True)
    for col in df.columns:
        gb.configure_column(
            col,
            cellStyle={"borderRight": "1px solid #4e4e4e", "padding": "6px"},
        )
        gb.configure_column(
            col,
            filter="agSetColumnFilter",
            filter_params={"excelMode": "windows"}
        )
    gb.configure_column(
        "STATUS",
        header_name="STATUS",
        cellStyle={
            "fontWeight": "bold",
            "textAlign": "center"
        }
    )
    gb.configure_default_column(
        floatingFilter=True,
        value=True,
        enableRowGroup=True,
        editable=False,
        groupable=True,
        filter=True,
        sortable=True
    )# Estilo condicional com JsCode — definido ANTES do build
    gb.configure_grid_options(
        domLayout='normal',
        rowHeight=30,
        headerHeight=42,
        enableEnterpriseModules=True,
        enableRangeSelection=True,
        suppressExcelExport=False,
        suppressMultiSort=False,
        enableCharts=True
    )  # Configurar altura automática para rolagem infinita
    # Aplica filtros inteligentes por coluna
    configurar_colunas_com_filtros_dinamicos(gb, df)
    grid_options = gb.build()
    grid_options["enableRangeSelection"] = True
    grid_options["enableCharts"] = True
    grid_options["enableStatusBar"] = True
    grid_options["enableFilter"] = True
    grid_options["enableSorting"] = True
    grid_options["groupDefaultExpanded"] = -1
    grid_options["groupMultiAutoColumn"] = True
    # Define o estilo visual da grade
    grid_options["gridStyle"] = {
        "border": "1px solid #4e4e4e",         # contorno
        "borderColor": "#f2ede3",
        "borderWidth": "1px",
        "borderStyle": "solid",
        "borderCollapse": "collapse"
    }
    
    grid_options["rowStyle"] = {
        "borderBottom": "1px solid #4e4e4e"
    }
    grid_options["rowHeight"] = 30
    grid_options["headerHeight"] = 45
    grid_options["autoGroupColumnDef"] = {
        "headerName": "Produtos Agrupados",  # Nome desejado no lugar de "Group"
        "minWidth": 300,
        "cellRendererParams": {
            "suppressCount": False,  # Se quiser ocultar a contagem de itens entre parênteses, use True
            "checkbox": True  # <-- Isso coloca o checkbox na coluna agrupada!
        }
    }

    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.FILTERING_CHANGED,
        fit_columns_on_grid_load=True,
        theme="meterial",
        enable_enterprise_modules=True,
        height=750,
        width='100%',
        reload_data=True,
        allow_unsafe_jscode=True
    )

    filtered_df = pd.DataFrame(grid_response['data'])
    return filtered_df

# Função para mostrar o resumo de inventário de forma estilizada
def show_summary(discrepancies):
    """
    Exibe o resumo de estoque e contagem com RFID.
    """
    total_estoque = discrepancies['ESTOQUE'].sum()
    total_contagem_rfid = discrepancies['CONTAGEM'].sum()  # Soma total da contagem RFID
    total_divergencia_positiva = int(discrepancies[discrepancies['DIVERGÊNCIA'] > 0]['DIVERGÊNCIA'].sum())
    total_divergencia_negativa = int(discrepancies[discrepancies['DIVERGÊNCIA'] < 0]['DIVERGÊNCIA'].sum())
    total_divergencia_absoluta = int(discrepancies['DIVERGÊNCIA'].abs().sum())

    st.subheader("Resumo Total")
    col1, col2, col3, col4, col5 = st.columns([2,2,1,1,1])
    with col1:
        st.metric('Total Esperado em Estoque', total_estoque, border=True)
    with col2:    
        st.metric('Total da Contagem com RFID', total_contagem_rfid, border=True)
    with col3:
        st.metric('Sobra',total_divergencia_positiva, border=True)
    with col4:    
        st.metric('Falta',total_divergencia_negativa, border=True)
    with col5:    
        st.metric('Divergência absoluta',total_divergencia_absoluta, border=True)

def calculate_discrepancies(expected, counted, file_name):
    """
    Calcula as discrepâncias entre os DataFrames de estoque esperado e contagem.
    """
    # Verificar se a coluna 'EAN' existe em ambos os DataFrames
    if 'EAN' not in expected.columns or 'EAN' not in counted.columns:
        st.error("A coluna 'EAN' não foi encontrada em um dos arquivos CSV.")
        return pd.DataFrame()  # Retorna um DataFrame vazio em caso de erro

    # Converte a coluna 'EAN' para string em ambos os DataFrames
    expected['EAN'] = expected['EAN'].astype(str)
    counted['EAN'] = counted['EAN'].astype(str)

    # Agregar o DataFrame de contagem para consolidar as quantidades
    counted_aggregated = counted.groupby('EAN', as_index=False).agg({'CONTAGEM': 'sum'})

    # Adiciona a coluna 'ESTOQUE' com valor 0 no expected se não existir
    if 'ESTOQUE' not in expected.columns:
        expected['ESTOQUE'] = 0

    # Merge completo dos dados esperados e contados usando EAN como chave
    discrepancies = pd.merge(expected, counted_aggregated, on='EAN', how='outer', suffixes=('_EXPECTED', '_COUNTED'))

    # Substitui NaN em 'ESTOQUE' e 'CONTAGEM' por 0
    discrepancies['ESTOQUE'] = discrepancies['ESTOQUE'].fillna(0).astype(int)
    discrepancies['CONTAGEM'] = discrepancies['CONTAGEM'].fillna(0).astype(int)

    # Converter as colunas 'ESTOQUE' e 'CONTAGEM' para numérico
    discrepancies['ESTOQUE'] = pd.to_numeric(discrepancies['ESTOQUE'], errors='coerce').fillna(0).astype(int)
    discrepancies['CONTAGEM'] = pd.to_numeric(discrepancies['CONTAGEM'], errors='coerce').fillna(0).astype(int)

    # Cálculo da divergência
    discrepancies['DIVERGÊNCIA'] = discrepancies['CONTAGEM'] - discrepancies['ESTOQUE']

    # Adicionar coluna para reler peças apenas para os SKUs divergentes
    discrepancies['PEÇAS A SEREM RELIDAS'] = discrepancies.apply(
        lambda row: max(row['ESTOQUE'], row['CONTAGEM']) if row['DIVERGÊNCIA'] != 0 else 0, axis=1
    )

    return discrepancies

# 1. KPI - Exibindo a acurácia via Gauge
def kpi_gauge():
    gauge = (
        Gauge()
        .add(
            series_name="Acurácia",
            data_pair=[("Acurácia", 99.47)],
            min_=0,
            max_=100,
            detail_label_opts=opts.LabelOpts(formatter="{value}%")
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="Acurácia do Inventário", pos_left="center"),
            tooltip_opts=opts.TooltipOpts(formatter="{a} <br/>{b}: {c}%")
        )
    )
    return gauge

# 2. KPI - Outros indicadores em gráfico de barras
def kpi_bar():
    # Exemplo de dados (ajuste conforme necessário)
    kpis = ["Estoque Esperado", "Contagem Realizada", "Divergência Absoluta", "Peças a Recontar"]
    values = [41263, 41459, 218, 2609]
    bar = (
        Bar()
        .add_xaxis(kpis)
        .add_yaxis("Valores", values)
        .set_global_opts(
            title_opts=opts.TitleOpts(title="KPIs do Inventário", pos_left="center"),
            tooltip_opts=opts.TooltipOpts(trigger="axis")
        )
    )
    return bar

# 3. Comparativo Estoque x Contagem (gráfico de colunas simples)
def comparativo_estoque_contagem():
    categorias = ["Estoque Esperado", "Contagem Realizada"]
    valores = [41263, 41459]
    bar = (
        Bar()
        .add_xaxis(categorias)
        .add_yaxis("Valores", valores)
        .set_global_opts(
            title_opts=opts.TitleOpts(title="Comparativo: Estoque x Contagem", pos_left="center"),
            tooltip_opts=opts.TooltipOpts(trigger="axis")
        )
    )
    return bar

# 4. Gráfico de Pizza Aninhada – Distribuição dos Itens
def nested_pie_chart():
    # Dados de exemplo (ajuste conforme a lógica do seu inventário)
    contagem_total = 41459
    divergencia_total = 218  # soma de sobra e falta
    contagem_correta = contagem_total - divergencia_total
    sobra = 207
    falta = 11
    pecas_sem_relidas = 2609

    # Anel interno – visão geral
    inner_data = [
        ("Contagem Correta", contagem_correta),
        ("Não Contado", pecas_sem_relidas),
        ("Divergência", divergencia_total),
    ]
    # Anel externo – detalhamento (dentro da divergência, mostra sobra e falta)
    outer_data = [
        ("Contagem Correta", contagem_correta),
        ("Não Contado", pecas_sem_relidas),
        ("Sobra", sobra),
        ("Falta", falta),
    ]

    # Configuração do rich text para labels com caixinhas flutuantes
    rich_formatter = {
        "a": {"color": "#999", "lineHeight": 22, "align": "center"},
        "abg": {
            "backgroundColor": "#e3e3e3",
            "width": "100%",
            "align": "right",
            "height": 22,
            "borderRadius": [4, 4, 0, 0],
        },
        "hr": {"borderColor": "#aaa", "width": "100%", "borderWidth": 0.5, "height": 0},
        "b": {"fontSize": 16, "lineHeight": 33},
        "per": {"color": "#eee", "backgroundColor": "#334455", "padding": [2, 4], "borderRadius": 2},
    }

    pie = (
        Pie(init_opts=opts.InitOpts(width="800px", height="600px", theme="dark"))
        # Anel interno: visão geral
        .add(
            series_name="Visão Geral",
            data_pair=inner_data,
            radius=[0, "35%"],
            label_opts=opts.LabelOpts(
                position="inner",
                formatter="{b}: {c}",
                color="#fff"
            ),
        )
        # Anel externo: detalhamento com labels formatados
        .add(
            series_name="Detalhamento",
            data_pair=outer_data,
            radius=["45%", "60%"],
            label_opts=opts.LabelOpts(
                position="outside",
                formatter="{a|{a}}{abg|}\n{hr|}\n {b|{b}: }{c}  {per|{d}%}  ",
                background_color="#eee",
                border_color="#aaa",
                border_width=1,
                border_radius=4,
                rich=rich_formatter,
            ),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="Resumo do Inventário",
                subtitle="Acurácia: 99.47%",
                pos_left="center",
                title_textstyle_opts=opts.TextStyleOpts(color="#fff"),
                subtitle_textstyle_opts=opts.TextStyleOpts(color="#fff")
            ),
            legend_opts=opts.LegendOpts(pos_left="left", textstyle_opts=opts.TextStyleOpts(color="#fff")),
            tooltip_opts=opts.TooltipOpts(trigger="item", formatter="{a} <br/>{b}: {c} ({d}%)"),
        )
    )
    return pie

# 5. Gráfico de Barras – Peças a Recontar por SKU
def sku_recount_bar():
    # Dados de exemplo – ajuste conforme os SKUs e a quantidade de peças a recontar
    skus = ["SKU1", "SKU2", "SKU3", "SKU4", "SKU5"]
    recounts = [50, 120, 30, 80, 60]
    bar = (
        Bar()
        .add_xaxis(skus)
        .add_yaxis("Peças a Recontar", recounts)
        .reversal_axis()  # transforma em gráfico de barras horizontal
        .set_global_opts(
            title_opts=opts.TitleOpts(title="Peças a Recontar por SKU", pos_left="center"),
            tooltip_opts=opts.TooltipOpts(trigger="axis")
        )
    )
    return bar

# 7. Dashboard – Combinando todos os gráficos em uma única página
def dashboard():
    page = Page(layout=Page.SimplePageLayout)
    # Adiciona os gráficos conforme a ordem desejada
    page.add(kpi_gauge())
    page.add(kpi_bar())
    page.add(comparativo_estoque_contagem())
    page.add(nested_pie_chart())
    page.add(sku_recount_bar())
    # Renderiza o dashboard como HTML embed (pode usar page.render("dashboard.html") para gerar um arquivo)
    return page.render_embed()

def dynamic_dashboard(total_estoque: int,
                      total_contagem: int,
                      total_divergencia_absoluta: int,
                      total_pecas_a_serem_relidas: int,
                      accuracy_percentage: float,
                      total_divergencia_positiva: int,
                      total_divergencia_negativa: int) -> str:
    # 1. KPI – Gauge da Acurácia
    #reduzir as casas decimais da variavel accuracy_percentage para 2
    accuracy_percentage = round(accuracy_percentage,2)
    gauge = (
        Gauge()
        .add(
            series_name="Acurácia",
            data_pair=[("Acurácia", accuracy_percentage)],
            min_=0,
            max_=100,
            # detail_label_opts=opts.LabelOpts(formatter="{value}%"),
            detail_label_opts=opts.GaugeDetailOpts(
                formatter="{value}%",  # Exibe o símbolo de porcentagem
                color="#fff",          # Cor do valor central
                font_size=26           # Ajuste se quiser maior ou menor
            ),
        )
        .set_series_opts(
            # Cor e estilo do arco do gauge
            axisline_opts=opts.AxisLineOpts(
                linestyle_opts=opts.LineStyleOpts(
                    color=[(1, "#fff")],  # cor branca para todo o arco
                    width=10
                )
            ),
            # Risquinhos (ticks)
            axistick_opts=opts.AxisTickOpts(
                is_show=True,
                length=8,
                linestyle_opts=opts.LineStyleOpts(is_show=True,color="#fff")  # cor dos ticks
            ),
            # Labels do eixo (0, 10, 20 ... 100)
            axislabel_opts=opts.LabelOpts(
                is_show=True,
                color="#fff"
                ),        # cor dos valores no eixo
            # Linhas de divisão entre faixas
            splitline_opts=opts.SplitLineOpts(
                is_show=True,
                linestyle_opts=opts.LineStyleOpts(
                    is_show=True,
                    width=25,
                    opacity=0.2,
                    color="#fff")  # cor das linhas de divisão
            ),
            # IMPORTANTE: É aqui que alteramos a cor dos valores numéricos (0, 10, 20, ... 100)
            label_opts=opts.LabelOpts(
                is_show=True,
                color="blue",
                font_size=50,
                background_color="white"
                )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="Acurácia do Inventário",
                pos_left="center",
                title_textstyle_opts=opts.TextStyleOpts(color="#fff")  # Título em branco
            ),
            legend_opts=opts.LegendOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(formatter="{a} <br/>{b}: {c}%")
        )
    )
    
    # 2. KPI – Gráfico de Barras com indicadores principais
    # kpi_bar_chart = (
    #     Bar()
    #     .add_xaxis(["Estoque Esperado", "Contagem Realizada", "Divergência Absoluta", "Peças a Recontar"])
    #     .add_yaxis("Valores", [total_estoque, total_contagem, total_divergencia_absoluta, total_pecas_a_serem_relidas])
    #     .set_global_opts(
    #         title_opts=opts.TitleOpts(
    #             title="KPIs do Inventário",
    #             pos_left="center",
    #             title_textstyle_opts=opts.TextStyleOpts(color="white")
    #             ),
    #         tooltip_opts=opts.TooltipOpts(trigger="axis"),
    #         legend_opts=opts.LegendOpts(is_show=False)
    #     )
    # )
    
    # 3. Comparativo Estoque x Contagem
    comparativo_chart = (
        Bar()
        .add_xaxis(["Estoque Esperado", "Contagem Realizada"])
        .add_yaxis("Valores", [total_estoque, total_contagem])
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="Comparativo: Estoque x Contagem",
                pos_left="center",
                title_textstyle_opts=opts.TextStyleOpts(color="white")
                ),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )
    
    # 4. Gráfico de Pizza Aninhada – Distribuição dos Itens
    # Definindo a "contagem correta" como a contagem realizada sem a divergência
    contagem_correta = total_contagem - total_divergencia_absoluta
    inner_data = [
        # ("Contagem Correta", contagem_correta),
        # ("Não Contado", total_pecas_relidas),
        ("Divergência", total_divergencia_absoluta),
    ]
    outer_data = [
        # ("Contagem Correta", contagem_correta),
        #("Não Contado", total_pecas_relidas),
        ("Sobra", total_divergencia_positiva),
        ("Falta", abs(total_divergencia_negativa)),
    ]
    
    # Configuração do rich text para as "caixinhas flutuantes" dos labels
    rich_formatter = {
        "a": {"color": "#999", "lineHeight": 22, "align": "center"},
        "abg": {
            "backgroundColor": "#e3e3e3",
            "width": "100%",
            "align": "right",
            "height": 22,
            "borderRadius": [4, 4, 0, 0],
        },
        "hr": {"borderColor": "#aaa", "width": "100%", "borderWidth": 0.5, "height": 0},
        "b": {"fontSize": 16, "lineHeight": 33},
        "per": {"color": "#eee", "backgroundColor": "#334455", "padding": [2, 4], "borderRadius": 2},
    }
    
    nested_pie = (
        Pie(init_opts=opts.InitOpts(width="800px", height="600px"))
        .add(
            series_name="Visão Geral",
            data_pair=inner_data,
            radius=[0, "35%"],
            label_opts=opts.LabelOpts(
                position="inner",
                formatter="{b}: {c}",
                color="#fff"
            )
        )
        .add(
            series_name="Detalhamento",
            data_pair=outer_data,
            radius=["45%", "60%"],
            label_opts=opts.LabelOpts(
                position="outside",
                formatter="{a|{a}}{abg|}\n{hr|}\n {b|{b}: }{c}  {per|{d}%}  ",
                background_color="#eee",
                border_color="#aaa",
                border_width=1,
                border_radius=4,
                rich=rich_formatter,
            )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="Resumo do Inventário",
                subtitle=f"Acurácia: {accuracy_percentage:.2f}%",
                pos_left="center",
                title_textstyle_opts=opts.TextStyleOpts(color="#fff"),
                subtitle_textstyle_opts=opts.TextStyleOpts(color="#fff")
            ),
            legend_opts=opts.LegendOpts(
                pos_left="center",
                pos_top="90%",
                textstyle_opts=opts.TextStyleOpts(color="#fff")
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="item",
                formatter="{a} <br/>{b}: {c} ({d}%)"
            )
        )
    )
    
    # 5. (Opcional) Se houver gráfico por SKU, você pode criar aqui um gráfico de barras agrupado.
    # Por exemplo, agrupar 'PEÇAS A SEREM RELIDAS' por 'REFERENCIA' ou outro identificador.
    
    # Combina os gráficos em uma única página (dashboard)
    page = Page(layout=Page.SimplePageLayout)
    page.add(gauge)
    # page.add(kpi_bar_chart)
    page.add(comparativo_chart)
    page.add(nested_pie)
    return page.render_embed()