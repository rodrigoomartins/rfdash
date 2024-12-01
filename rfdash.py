import streamlit as st
import pandas as pd
from openpyxl import load_workbook
from pyxlsb import open_workbook as open_xlsb
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from datetime import datetime
import unidecode
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
import plotly.express as px
import tempfile
import json
import os
import numpy as np

# Configurações padrão do Streamlit
st.set_page_config(layout="wide", page_title="Análise de Divergência", page_icon="📊", initial_sidebar_state="auto",menu_items={'Report a bug': 'https://wa.me/5588993201518','About':'''
# Sobre a aplicação
Aplicação para análise de divergência de inventários.
\nFeita por [Votu RFID](https://www.voturfid.com.br)
                                                                                                                                
### Acesse nossas redes sociais 📲
[LinkedIn](https://www.linkedin.com/company/voturfid)
                                                                                                                                
[Instagram](https://www.instagram.com/voturfid)

[Facebook](https://www.facebook.com/voturfid)'''})

logo_claro_path = "logo_claro_votu.png"
logo_icon_claro_path = "logo_icon_claro.png"
logo_escuro_path = "logo_escuro_votu.png"
site_url = "https://www.voturfid.com.br"
#st.image (logo_claro_path, width=150)

# Adiciona a imagem sem a opção de expandir
st.logo(image=logo_claro_path,icon_image=logo_icon_claro_path,link=site_url)

with st.sidebar:
    st.header("Esta é uma ferramenta para análise de divergência de inventários feitos utilizando a tecnologia de RFID da Votu.")
    st.divider()
    st.write("""
    São necessários dois arquivos para gerar a análise:
    - CSV do estoque esperado;
    - CSV da contagem do inventário com RFID.

    O arquivo CSV do estoque esperado deve conter as seguintes informações:
    - EAN (obrigatório)
    - ESTOQUE (obrigatório)
    - Outras colunas opcionais (PRODUTO, REFERENCIA, DESCRICAO, COR, TAMANHO)

    O arquivo CSV da contagem com RFID é gerado pelo RFLOG e contém EAN e Quantidade dos produtos lidos.

    Os arquivos CSV devem conter cabeçalhos, ter `,` (vírgula) como separador padrão e estarem na codificação `UTF-8` (padrão para Google Planilhas; disponível no menu `Tipo` na janela de salvamento do Excel; disponível no menu `Codificação` na janela de salvamento do Bloco de Notas.)
    """)
    st.write("É possível carregar mais de um arquivo CSV de inventário e escolher qual será comparado com o estoque esperado.\nA tabela de divergência permite vários tipos de filtragens, ordenações e outras configurações disponíveis.\nAo fim, é possível gerar um arquivo PDF da tabela de divergência.\n\nCaso não seja possível gerar o arquivo PDF, é possível exportar a tabela clicando com o botão direito dentro de qualquer célula e seguindo o menu `Export`.")

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

# Função para processar o upload de arquivos
def process_upload(file, expected_type):
    """
    Processa o arquivo carregado e aplica o tratamento específico baseado no tipo esperado.
    """
    if file is None:
        return None, None

    # Detectar a extensão do arquivo
    file_extension = file.name.split('.')[-1].lower()

    try:
        if file_extension == 'csv':
            # Ler arquivos CSV diretamente com o pandas
            file.seek(0)  # Certifique-se de que o ponteiro do arquivo está no início
            dataframe = pd.read_csv(file, dtype=str)  # Forçar tudo como string para evitar problemas de tipos
        elif file_extension in ['xlsx', 'xls', 'xlsb']:
            # Processar arquivos Excel
            dataframe = process_excel_file(file, file_extension)
            st.success("Arquivo Excel carregado com sucesso!")
        elif file_extension == 'txt':
            # Ler arquivos TXT como arquivos delimitados (tabulação por padrão)
            file.seek(0)  # Certifique-se de que o ponteiro do arquivo está no início
            dataframe = pd.read_csv(file, delimiter=',', header=None, dtype=str)
        else:
            st.error("Formato de arquivo não suportado. Use .csv, .xls, .xlsx, .xlsb ou .txt.")
            return None, None

        # Normalizar os nomes das colunas para arquivos com cabeçalho
        if file_extension in ['csv', 'xlsx', 'xls', 'xlsb']:
            dataframe.columns = normalize_column_names(dataframe.columns)

        # Verificar as colunas obrigatórias para estoque_esperado
        if expected_type == 'estoque_esperado':
            required_columns = {'EAN', 'ESTOQUE'}
            if not required_columns.issubset(set(dataframe.columns)):
                st.error(f"O arquivo {expected_type} precisa conter as colunas obrigatórias: {', '.join(required_columns)}.")
                return None, None

        # Tratamento para arquivo de contagem
        elif expected_type == 'contagem':
            num_columns = dataframe.shape[1]
            if num_columns == 2:  # Duas colunas
                dataframe.columns = ['EAN', 'CONTAGEM']
                dataframe['EAN'] = dataframe['EAN'].astype(str)
                dataframe['CONTAGEM'] = pd.to_numeric(dataframe['CONTAGEM'].str.replace(',', '.'), errors='coerce').fillna(0).astype(int)
            elif num_columns == 1:  # Uma coluna
                dataframe.columns = ['EAN']
                dataframe['CONTAGEM'] = 1
                dataframe = dataframe.groupby('EAN', as_index=False).agg({'CONTAGEM': 'sum'})
            else:  # Qualquer outro número de colunas é inválido
                st.error("O arquivo de contagem deve ter uma ou duas colunas.")
                return None, None

    except pd.errors.EmptyDataError:
        st.error(f"O arquivo {expected_type} está vazio ou possui um formato inválido.")
        return None, None
    except Exception as e:
        st.error(f"Erro ao ler o arquivo {expected_type}: {e}")
        return None, None

    return dataframe, expected_type


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

def generate_pdf(filtered_df, font_size, orientation):
    from reportlab.lib.pagesizes import A4, landscape, portrait
    # Colunas obrigatórias
    required_columns = ['EAN', 'ESTOQUE', 'CONTAGEM', 'DIVERGÊNCIA']
    missing_columns = [col for col in required_columns if col not in filtered_df.columns]
    if missing_columns:
        st.error(f"Colunas ausentes no DataFrame: {', '.join(missing_columns)}. Não é possível gerar o PDF.")
        return None

    # Substituir valores NaN por '-'
    filtered_df = filtered_df.fillna('-')

    # Renomear a coluna 'TAMANHO' para 'TAM' se existir
    if 'TAMANHO' in filtered_df.columns:
        filtered_df = filtered_df.rename(columns={'TAMANHO': 'TAM'})

    # Remover a coluna 'PEÇAS A SEREM RELIDAS' se existir
    if 'PEÇAS A SEREM RELIDAS' in filtered_df.columns:
        filtered_df = filtered_df.drop(columns=['PEÇAS A SEREM RELIDAS'])

    # Criar um arquivo temporário para o PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        pdf_output_path = tmp_pdf.name

    # Definir a orientação e tamanho da página
    if orientation == "P":
        pagesize = portrait(A4)
    else:
        pagesize = landscape(A4)

    pdf = SimpleDocTemplate(
        pdf_output_path,
        pagesize=pagesize,
        rightMargin=20,
        leftMargin=20,
        topMargin=50,
        bottomMargin=50
    )

    # Estilo de texto
    styles = getSampleStyleSheet()
    styles["Title"].alignment = TA_CENTER

    # Estilo para as células da tabela
    cell_style = ParagraphStyle(
        name='CellStyle',
        parent=styles['Normal'],
        fontSize=font_size,
        wordWrap='CJK',
        leading=font_size + 2,  # Espaçamento entre linhas
    )

    # Cabeçalho da tabela e colunas a incluir
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

    # Filtrar apenas as colunas presentes no DataFrame
    columns_to_include = [col for col in ['PRODUTO', 'EAN', 'REFERENCIA', 'DESCRICAO', 'COR', 'TAM', 'ESTOQUE', 'CONTAGEM', 'DIVERGÊNCIA'] if col in filtered_df.columns]
    headers = columns_to_include

    # Ajustar col_widths de acordo com as colunas presentes
    col_widths_in_use = {col: col_widths[col] for col in columns_to_include}

    # Normalizar col_widths_in_use para que a soma seja 1
    total_width = sum(col_widths_in_use.values())
    col_widths_in_use = {col: width / total_width for col, width in col_widths_in_use.items()}

    # Calcular as larguras reais das colunas
    page_width = pdf.width
    col_width_values = [page_width * col_widths_in_use[col] for col in columns_to_include]

    # Lista de elementos a serem adicionados no PDF
    elements = []
    elements.append(Paragraph("Relatório de Divergência de Inventário", styles['Title']))
    elements.append(Spacer(1, 12))

    # **Adicionar o Resumo ao PDF**
    # Calcular os valores do resumo
    if not filtered_df.empty:
        total_estoque = int(filtered_df['ESTOQUE'].astype(float).sum())
        total_contagem = int(filtered_df['CONTAGEM'].astype(float).sum())
        total_divergencia_positiva = int(filtered_df[filtered_df['DIVERGÊNCIA'].astype(float) > 0]['DIVERGÊNCIA'].astype(float).sum())
        total_divergencia_negativa = int(filtered_df[filtered_df['DIVERGÊNCIA'].astype(float) < 0]['DIVERGÊNCIA'].astype(float).sum())
        total_divergencia_absoluta = int(filtered_df['DIVERGÊNCIA'].astype(float).abs().sum())
    else:
        total_estoque = total_contagem = total_divergencia_positiva = total_divergencia_negativa = total_divergencia_absoluta = 0

    # Adicionando o resumo ao PDF
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

    # Definir os dados da tabela
    data = [headers]

    # Iterar pelas linhas do DataFrame e adicionar ao 'data'
    for i, row in filtered_df.iterrows():
        try:
            row_data = []
            for col in columns_to_include:
                value = str(row[col]) if col in row else '-'
                para = Paragraph(value, cell_style)
                row_data.append(para)
            data.append(row_data)
        except Exception as e:
            st.error(f"Erro ao processar a linha {i}. Detalhes: {e}")
            continue

    # Criar a tabela com os dados e larguras de coluna ajustadas
    table = Table(data, colWidths=col_width_values, repeatRows=1)

    # Estilo da tabela
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),  # Cabeçalho
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), font_size),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('WORDWRAP', (0, 0), (-1, -1), True),
    ])

    # Aplicando cores alternadas às linhas de dados
    for row_index, _ in enumerate(data[1:], start=1):
        bg_color = colors.whitesmoke if row_index % 2 == 0 else colors.lightgrey
        style.add('BACKGROUND', (0, row_index), (-1, row_index), bg_color)

    table.setStyle(style)
    elements.append(table)

    # Adicionar rodapé com número de páginas
    pdf.build(elements, onFirstPage=lambda canv, doc: add_page_number(canv, doc, orientation),
              onLaterPages=lambda canv, doc: add_page_number(canv, doc, orientation))
    return pdf_output_path


# Função para gerar gráfico de pizza
def generate_pie_chart(accuracy_percentage):
    labels = ['Acurácia', 'Inacurácia']
    values = [accuracy_percentage, 100 - accuracy_percentage]
    fig = px.pie(values=values, names=labels, title='Acurácia do Inventário')
    return fig

# Função para exibir tabela de dados
def display_data_table(df):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_pagination(enabled=False)  # Desativar paginação
    gb.configure_side_bar(True)
    gb.configure_selection('multiple', use_checkbox=True)
    gb.configure_default_column(value=True, enableRowGroup=True, aggFunc='sum', editable=True, groupable=True, filter=True, sortable=True)
    gb.configure_grid_options(domLayout='normal', enableEnterpriseModules=True, enableRangeSelection=True, suppressExcelExport=False, suppressMultiSort=False)  # Configurar altura automática para rolagem infinita
    grid_options = gb.build()

    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.MODEL_CHANGED,
        fit_columns_on_grid_load=True,
        theme='alpine',
        enable_enterprise_modules=True,
        height=750,
        width='100%',
        reload_data=True,
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
    st.divider()
    st.subheader("Resumo Total")
    col1, col2 = st.columns(2)
    with col1:
        st.metric('Total Esperado em Estoque', total_estoque)
    with col2:
        st.metric('Total da Contagem com RFID', total_contagem_rfid)

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
    discrepancies['ESTOQUE'].fillna(0, inplace=True)
    discrepancies['CONTAGEM'].fillna(0, inplace=True)

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


# Dicionário para armazenar divergências de múltiplos arquivos
all_discrepancies = {}

# Título da aplicação
st.title("Análise de Divergência")

# Configurar as caixas de upload fixas
st.header("Upload de Arquivos")

st.subheader("Arquivo de Estoque Esperado")
st.info("O arquivo de estoque esperado deve conter obrigatoriamente as colunas 'EAN' e 'ESTOQUE'. As demais colunas são opcionais e, se presentes, serão exibidas na tabela.")
uploaded_estoque_esperado = st.file_uploader(
    "Upload do arquivo de estoque esperado (.csv, .xls, .xlsx)",
    type=['csv', 'xls', 'xlsx'],
    key="estoque_esperado"
)

st.subheader("Arquivo de Contagem")
uploaded_contagem = st.file_uploader(
    "Upload do arquivo de contagem (.csv ou .txt)",
    type=['csv', 'txt'],
    key="contagem"
)

# Processar os uploads
estoque_df, estoque_tipo = process_upload(uploaded_estoque_esperado, "estoque_esperado")
contagem_df, contagem_tipo = process_upload(uploaded_contagem, "contagem")

# Exibir mensagens de sucesso ou erro
if uploaded_estoque_esperado:
    if estoque_df is not None:
        st.success("Arquivo de estoque esperado carregado com sucesso!")
    else:
        st.error("Falha ao carregar o arquivo de estoque esperado.")

if uploaded_contagem:
    if contagem_df is not None:
        st.success("Arquivo de contagem carregado com sucesso!")
    else:
        st.error("Falha ao carregar o arquivo de contagem.")

# Processar os arquivos carregados e realizar a análise de divergência
if estoque_df is not None and contagem_df is not None:
    expected_df = estoque_df
    counted_df = contagem_df
    file_name = uploaded_contagem.name  # Nome do arquivo de contagem

    # Converter a coluna 'CONTAGEM' para numérica (caso não esteja)
    counted_df['CONTAGEM'] = pd.to_numeric(counted_df['CONTAGEM'], errors='coerce').fillna(0).astype(int)

    discrepancies = calculate_discrepancies(expected_df, counted_df, file_name)
    all_discrepancies[file_name] = discrepancies

    # Exibir tabela de dados filtrados
    filtered_df = display_data_table(discrepancies)

    # Mostrar resumo
    show_summary(discrepancies)

    # Exibir métricas do resumo dinâmico
    if not filtered_df.empty:
        total_estoque = int(filtered_df['ESTOQUE'].sum())
        total_contagem = int(filtered_df['CONTAGEM'].sum())
        total_divergencia_positiva = int(filtered_df[filtered_df['DIVERGÊNCIA'] > 0]['DIVERGÊNCIA'].sum())
        total_divergencia_negativa = int(filtered_df[filtered_df['DIVERGÊNCIA'] < 0]['DIVERGÊNCIA'].sum())
        total_divergencia_absoluta = int(filtered_df['DIVERGÊNCIA'].abs().sum())
        total_pecas_a_serem_relidas = filtered_df[filtered_df['DIVERGÊNCIA'] != 0]['PEÇAS A SEREM RELIDAS'].sum()

        st.subheader("Resumo Dinâmico")
        st.caption("Valores filtrados")
        col5, col6, col7 = st.columns(3)
        with col5:
            st.metric("Estoque Esperado", total_estoque)
        with col6:
            st.metric('Total da Contagem', total_contagem)
        accuracy_percentage = ((total_estoque - total_divergencia_absoluta) / total_estoque * 100) if total_estoque != 0 else 0
        with col7:
            st.metric("Acurácia do Inventário", f"{accuracy_percentage:.2f}%")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            sobra_percentage = (total_divergencia_positiva / total_estoque) * 100 if total_estoque != 0 else 0
            st.metric("Sobra", total_divergencia_positiva, delta=f"{sobra_percentage:.2f}%", delta_color='inverse')
        with col2:
            falta_percentage = (abs(total_divergencia_negativa) / total_estoque) * 100 if total_estoque != 0 else 0
            st.metric("Falta", total_divergencia_negativa, delta=f"{falta_percentage:.2f}%", delta_color='inverse')
        with col3:
            divergencia_absoluta_percentage = (total_divergencia_absoluta / total_estoque) * 100 if total_estoque != 0 else 0
            st.metric("Divergência Absoluta", total_divergencia_absoluta, delta=f"{divergencia_absoluta_percentage:.2f}%", delta_color='inverse')
        with col4:
            pecas_relidas_percentage = (total_pecas_a_serem_relidas / total_estoque) * 100 if total_estoque != 0 else 0
            st.metric("Peças a Serem Relidas", f"{int(total_pecas_a_serem_relidas)}", delta=f"{pecas_relidas_percentage:.2f}%", delta_color='inverse')
        
        # Salvar métricas no arquivo JSON
        metrics = {
            'total_estoque': total_estoque,
            'total_contagem': total_contagem,
            'total_divergencia_positiva': total_divergencia_positiva,
            'total_divergencia_negativa': total_divergencia_negativa,
            'total_divergencia_absoluta': total_divergencia_absoluta,
            'timestamp': generate_timestamp(),
            'nome_arquivo_contagem': file_name
        }
        save_metrics(metrics)

    # Gerar gráfico de pizza para acurácia
    st.divider()
    fig_pie_chart = generate_pie_chart(accuracy_percentage)
    st.plotly_chart(fig_pie_chart)

    # Botão para gerar PDF
    if st.button("Gerar PDF"):
        with st.spinner('Gerando o PDF, por favor aguarde...'):
            pdf_path = generate_pdf(filtered_df, font_size=8, orientation="L")
            if pdf_path:
                with open(pdf_path, "rb") as pdf_file:
                    st.download_button(
                        label="Baixar PDF",
                        data=pdf_file,
                        file_name="relatorio_divergencia_inventario.pdf",
                        mime="application/pdf"
                    )