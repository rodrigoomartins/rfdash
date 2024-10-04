import streamlit as st
import pandas as pd
import csv
import io
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from datetime import datetime
import unidecode
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER
import plotly.express as px
import tempfile
import json
import os
import numpy as np
from streamlit import session_state as state

# Configurações padrão do Streamlit
st.set_page_config(layout="wide", page_title="Análise de Divergência")

logo_claro_path = "logo_claro_votu.png"
logo_icon_claro_path = "logo_icon_claro.png"
logo_escuro_path = "logo_escuro_votu.png"
site_url = "https://www.voturfid.com.br"
estoque_esperado_exemplo_path = "POSICAO_ESTOQUE_DPA_20240630.csv"
contagem_rfid_exemplo_path = "Inventário-Ordem_271.csv"
#st.image (logo_claro_path, width=150)


# Adiciona a imagem sem a opção de expandir
st.logo(image=logo_claro_path,icon_image=logo_icon_claro_path,link=site_url)
with st.sidebar:
        st.header("""Esta é uma ferramenta para análise de divergência de inventários feitos utilizando a tecnologia de RFID da Votu.""")
        st.divider()
        st.write("""              
São necessários dois arquivos para gerar a análise:
- CSV do estoque esperado;
- CSV da contagem do inventário com RFID.

O arquivo CSV do estoque esperado, deve conter as seguintes informações:
- EAN
- PRODUTO
- REFERENCIA
- DESCRICAO
- COR
- TAMANHO
- ESTOQUE
- LOCALIZADOR
                 
O arquivo CSV da contagem com RFID é gerado pelo RFLOG e contém EAN e Quantidade dos produtos lidos.

Os arquivos CSV devem conter cabeçalhos, ter `,` (vírgula) como separador padrão e estarem na codificação `UTF-8` (padrão para Google Planilhas; disponível no menu `tipo` na janela de salvamento do Excel; disponível no menu `Codificação`na janela de salvamento do Bloco de Notas.)
""")
        st.write("É possível carregar mais de um arquivo CSV de inventário e escolher qual será comparado com o estoque esperado.\nA tabela de divergência permite vários tipos de filtragens, ordenações e outras configurações disponíveis.\nAo fim, é possível gerar um arquivo PDF da tabela de divergência.\n\nCaso não seja possível gerar o arquivo PDF, é possível exportar a tabela clicando com botão direito dentro de qualquer célula e seguindo o menu `export`.")
        
        
# Ajustar a função de leitura de arquivo para lidar com a detecção do delimitador
def detect_delimiter(file):
    try:
        file.seek(0)
        sample = file.read(1024).decode('utf-8')
        file.seek(0)  # Resetar o ponteiro do arquivo para o início
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample)
        return dialect.delimiter
    except Exception as e:
        st.warning(f"Não foi possível detectar o delimitador automaticamente. Usando ',' como padrão.")
        return ','  # Padrão para vírgula

# Função para normalizar nomes de colunas
def normalize_column_names(columns):
    return [unidecode.unidecode(col).upper().replace(' ', '_') for col in columns]

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


# Função para detectar codificação e ler o arquivo corretamente
def load_data(file):
    delimiter = detect_delimiter(file)
    
    # Detectar a codificação do arquivo (UTF-8 ou ANSI)
    try:
        # Tentativa de leitura com UTF-8
        file.seek(0)
        content = file.read().decode('utf-8')
    except UnicodeDecodeError:
        # Se falhar, tentar ler como ANSI
        file.seek(0)
        content = file.read().decode('latin-1')
    
    # Converter o conteúdo para um objeto StringIO para leitura pelo Pandas
    file.seek(0)
    file_buffer = io.StringIO(content)

    try:
        # Lendo o CSV com o quotechar configurado para lidar com vírgulas internas
        data = pd.read_csv(file_buffer, sep=delimiter, quotechar='"', engine='python', on_bad_lines='skip')
    except pd.errors.ParserError as e:
        st.error(f"Erro ao ler o arquivo CSV: {e}")
        return pd.DataFrame()  # Retorna um DataFrame vazio em caso de erro

    # Renomear colunas para formato normalizado
    data.columns = normalize_column_names(data.columns)
    
    # Renomear coluna QUANTIDADE para CONTAGEM
    if 'QUANTIDADE' in data.columns:
        data.rename(columns={'QUANTIDADE': 'CONTAGEM'}, inplace=True)
    
    return data

# Função para calcular divergências
def calculate_discrepancies(expected, counted, file_name):
    # Verificar se a coluna 'EAN' existe em ambos os DataFrames
    if 'EAN' not in expected.columns or 'EAN' not in counted.columns:
        st.error("A coluna 'EAN' não foi encontrada em um dos arquivos CSV.")
        return pd.DataFrame()  # Retorna um DataFrame vazio em caso de erro

    # Converte a coluna 'EAN' para string em ambos os DataFrames
    expected['EAN'] = expected['EAN'].astype(str)
    counted['EAN'] = counted['EAN'].astype(str)

    # Adiciona a coluna 'ESTOQUE' com valor 0 no expected se não existir
    if 'ESTOQUE' not in expected.columns:
        expected['ESTOQUE'] = 0

    # Adiciona a coluna 'CONTAGEM' com valor 0 no counted se não existir
    if 'CONTAGEM' not in counted.columns:
        counted['CONTAGEM'] = 0

    # Merge completo dos dados esperados e contados usando EAN como chave
    discrepancies = pd.merge(expected, counted, on='EAN', how='outer', suffixes=('_EXPECTED', '_COUNTED'))

    # Substitui NaN em 'ESTOQUE' e 'CONTAGEM' por 0
    discrepancies['ESTOQUE'].fillna(0, inplace=True)
    discrepancies['CONTAGEM'].fillna(0, inplace=True)

    # Cálculo da divergência
    discrepancies['DIVERGÊNCIA'] = discrepancies['CONTAGEM'] - discrepancies['ESTOQUE']

    # Adicionar coluna para reler peças apenas para os SKUs divergentes
    discrepancies['PEÇAS A SEREM RELIDAS'] = discrepancies.apply(lambda row: max(row['ESTOQUE'], row['CONTAGEM']) if row['DIVERGÊNCIA'] != 0 else 0, axis=1)

    # Arredondar números para inteiros
    discrepancies = discrepancies.astype({'ESTOQUE': int, 'CONTAGEM': int, 'DIVERGÊNCIA': int})

    # Adicionar coluna com o nome do arquivo de contagem
    #discrepancies['ARQUIVO_DE_CONTAGEM'] = file_name

    return discrepancies

def convert_df_to_csv(df):
    # Colunas a serem convertidas para string
    column_list = ['PRODUTO', 'REFERENCIA']

    # Itera sobre as colunas na lista
    for column in column_list:
        if column in df.columns:
            df[column] = df[column].astype(str)

    return df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')

# Função para gerar um timestamp
def generate_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M")

def generate_pdf(filtered_df, font_size, orientation):
    # Cria um arquivo temporário para o PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        pdf_output_path = tmp_pdf.name

    pdf = SimpleDocTemplate(pdf_output_path, pagesize=A4 if orientation == "P" else A4[::-1])

    # Lista de elementos a serem adicionados no PDF
    elements = []

    # Estilo de texto
    styles = getSampleStyleSheet()
    styles["Title"].alignment = TA_CENTER
    style_normal = styles["Normal"]

    # Adicionando estilo para evitar quebras no meio de palavras
    style_no_word_break = ParagraphStyle(
        name="NormalNoWordBreak",
        parent=styles["Normal"],
        wordWrap='CJK',  # Estilo que evita quebra de palavras no meio
        fontSize=font_size
    )

    # Cabeçalho
    elements.append(Paragraph("Relatório de Divergência de Inventário", styles['Title']))
    elements.append(Spacer(1, 12))

    # Resumo dinâmico
    if not filtered_df.empty:
        total_estoque = filtered_df['ESTOQUE'].sum()
        total_contagem = filtered_df['CONTAGEM'].sum()
        total_divergencia_positiva = filtered_df[filtered_df['DIVERGÊNCIA'] > 0]['DIVERGÊNCIA'].sum()
        total_divergencia_negativa = filtered_df[filtered_df['DIVERGÊNCIA'] < 0]['DIVERGÊNCIA'].sum()
        total_divergencia_absoluta = filtered_df['DIVERGÊNCIA'].abs().sum()
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
        elements.append(Paragraph(linha, style_normal))
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 12))

    # Cabeçalho da tabela
    headers = ['PRODUTO', 'EAN', 'REFERENCIA', 'DESCRICAO', 'COR', 'TAMANHO', 'ESTOQUE', 'CONTAGEM', 'DIVERGÊNCIA']
    if 'PEÇAS A SER RELIDAS' in filtered_df.columns:
        headers.append('PEÇAS A SER RELIDAS')

    # Definindo os dados da tabela
    data = [headers]

    # Iterando pelas linhas do DataFrame e adicionando ao 'data'
    for i, row in filtered_df.iterrows():
        row_data = [
            Paragraph(str(int(row['PRODUTO']) if not pd.isna(row['PRODUTO']) else '-'), style_normal),
            Paragraph(str(int(row['EAN'])), style_normal),
            # Verificar e tratar NaN antes da conversão para inteiro
            Paragraph(str(int(row['REFERENCIA']) if not pd.isna(row['REFERENCIA']) else '-'), style_normal),
            Paragraph(str(row['DESCRICAO']) if not pd.isna(row['DESCRICAO']) else '-', style_no_word_break),
            Paragraph(str(row['COR']) if not pd.isna(row['COR']) else '-', style_no_word_break),
            Paragraph(str(row['TAMANHO']) if not pd.isna(row['TAMANHO']) else '-', style_no_word_break),
            Paragraph(str(int(row['ESTOQUE'])), style_normal),
            Paragraph(str(int(row['CONTAGEM'])), style_normal),
            Paragraph(str(int(row['DIVERGÊNCIA'])), style_normal)
        ]

        if 'PEÇAS A SER RELIDAS' in filtered_df.columns:
            row_data.append(Paragraph(str(int(row['PEÇAS A SER RELIDAS'])), style_normal))

        data.append(row_data)

    # Definindo larguras fixas e proporcionais para cada coluna
    col_widths = [
        30*mm,  # PRODUTO
        35*mm,  # EAN
        40*mm,  # REFERENCIA
        60*mm,  # DESCRICAO (largura maior para suportar descrições longas)
        25*mm,  # COR
        20*mm,  # TAMANHO
        20*mm,  # ESTOQUE
        20*mm,  # CONTAGEM
        25*mm   # DIVERGÊNCIA
    ]

    # Configurando o estilo da tabela
    table = Table(data, colWidths=col_widths, repeatRows=1)  # 'repeatRows=1' para repetir cabeçalho em cada página
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), font_size),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),        
    ]))
    # Loop para aplicar cores alternadas nas linhas
    num_rows = len(data)
    for row_index in range(1, num_rows):
        if row_index % 2 == 0:
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, row_index), (-1, row_index), colors.lightgrey),
            ]))
        else:
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, row_index), (-1, row_index), colors.whitesmoke),
            ]))

    # Adicionando a tabela ao PDF
    elements.append(table)

    # Quebra de página, se necessário
    elements.append(PageBreak())

    # Build do PDF
    pdf.build(elements)

    return pdf_output_path


# Função para gerar gráfico de pizza
def generate_pie_chart(total_contagem, total_divergencia_absoluta, total_estoque):
    accuracy = (total_contagem - total_divergencia_absoluta) / total_estoque * 100
    labels = ['Acurácia', 'Inacurácia']
    values = [accuracy, 100 - accuracy]
    fig = px.pie(values=values, names=labels, title='Acurácia do Inventário')
    return fig

# Função para exibir tabela de dados
def display_data_table(df):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_pagination(enabled=False)  # Desativar paginação
    gb.configure_side_bar(True)
    gb.configure_default_column(value=True, enableRowGroup=True, aggFunc='sum', editable=True, groupable=True, filter=True, sortable=True)
    gb.configure_grid_options(domLayout='normal', enableEnterpriseModules = True)  # Configurar altura automática para rolagem infinita
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

# Título da aplicação
st.title("Análise de Divergência")

# Modifique a função de upload para aceitar .csv e .txt
expected_file = st.file_uploader("Carregar arquivo de estoque esperado (.csv ou .txt)", type=['csv', 'txt'], key="expected")
counted_files = st.file_uploader("Carregar arquivos de inventário RFID (.csv ou .txt)", type=['csv', 'txt'], accept_multiple_files=True, key="counted")

# Função para mostrar o resumo de inventário de forma estilizada
def show_summary(discrepancies):
    total_estoque = discrepancies['ESTOQUE'].sum()

    st.divider()
    st.metric('Total Esperado em Estoque', total_estoque)

# Dicionário para armazenar divergências de múltiplos arquivos
all_discrepancies = {}

# Processar os arquivos carregados
if expected_file is not None and counted_files is not None:
    expected_df = load_data(expected_file)
    for counted_file in counted_files:
        counted_df = load_data(counted_file)
        file_name = counted_file.name  # Nome do arquivo de contagem
        discrepancies = calculate_discrepancies(expected_df, counted_df, file_name)
        all_discrepancies[file_name] = discrepancies

    # Exibir filtro para selecionar arquivos
    selected_file = st.selectbox("Selecione o arquivo de contagem para visualizar", options=list(all_discrepancies.keys()))

    
    # Exibir tabela de dados filtrados para o arquivo selecionado
    if selected_file:
        filtered_df = display_data_table(all_discrepancies[selected_file])
        
        show_summary(discrepancies)

        # Exibir métricas do resumo dinâmico
        if not filtered_df.empty:
            total_estoque = int(filtered_df['ESTOQUE'].sum())
            total_contagem = int(filtered_df['CONTAGEM'].sum())
            total_divergencia_positiva = int(filtered_df[filtered_df['DIVERGÊNCIA'] > 0]['DIVERGÊNCIA'].sum())
            total_divergencia_negativa = int(filtered_df[filtered_df['DIVERGÊNCIA'] < 0]['DIVERGÊNCIA'].sum())
            total_divergencia_absoluta = int(filtered_df['DIVERGÊNCIA'].abs().sum())
            total_pecas_a_serem_relidas = discrepancies[discrepancies['DIVERGÊNCIA'] != 0]['PEÇAS A SEREM RELIDAS'].sum()
            total_estoque_global = discrepancies['ESTOQUE'].sum()
            total_contagem_global = discrepancies['CONTAGEM'].sum()
            st.subheader("Resumo Dinâmico")
            st.caption("Valores filtrados")
            st.metric("Estoque Esperado", total_estoque)
            st.metric("Contagem do Inventário", total_contagem, delta=f"{(total_contagem-total_divergencia_absoluta)/total_estoque*100:.2f}% (acurácia)")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:    
                st.metric("Sobra", total_divergencia_positiva, delta=f"{(total_divergencia_positiva/total_contagem)*100:.2f}%", delta_color='inverse')
            with col2:
                st.metric("Falta", total_divergencia_negativa, delta=f"{(total_divergencia_negativa/total_contagem)*-100:.2f}%",delta_color='inverse')
            with col3:
                st.metric("Divergência Absoluta", total_divergencia_absoluta, delta=f"{(total_divergencia_absoluta/total_contagem)*100:.2f}%", delta_color='inverse')
            with col4:
                st.metric("Total de peças a serem relidas", f"{total_pecas_a_serem_relidas:.0f}", delta=f"{(total_pecas_a_serem_relidas/total_contagem_global)*100:.2f}%", delta_color='inverse')
            # Salvar métricas no arquivo JSON
            metrics = {
                'total_estoque': total_estoque,
                'total_contagem': total_contagem,
                'total_divergencia_positiva': total_divergencia_positiva,
                'total_divergencia_negativa': total_divergencia_negativa,
                'total_divergencia_absoluta': total_divergencia_absoluta,
                'timestamp': generate_timestamp(),
                'nome_arquivo_contagem': selected_file
            }
            save_metrics(metrics)

        # Gerar gráfico de pizza para acurácia
        st.divider()
        fig_pie_chart = generate_pie_chart(total_contagem, total_divergencia_absoluta, total_estoque)
        st.plotly_chart(fig_pie_chart)

        # Botão para gerar PDF
        if st.button("Gerar PDF"):
            pdf_path = generate_pdf(filtered_df, 8, "L")
            with open(pdf_path, "rb") as pdf_file:
                st.download_button(
                    label="Baixar PDF",
                    data=pdf_file,
                    file_name="relatorio_divergencia_inventario.pdf",
                    mime="application/pdf"
                )
