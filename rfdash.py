import streamlit as st
import pandas as pd
from utils.config import process_upload, show_temporary_success, show_summary, calculate_discrepancies, display_data_table, generate_timestamp, dynamic_dashboard, generate_pdf
import streamlit.components.v1 as components

# Configurações padrão do Streamlit
st.set_page_config(layout="wide", page_title="Análise de Divergência", page_icon="📊", initial_sidebar_state="collapsed",menu_items={'Report a bug': 'https://wa.me/5588993201518','About':'''
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

# Inicializar session_state para mensagens de sucesso, se não estiver presente
if "success_messages" not in st.session_state:
    st.session_state.success_messages = {}

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

# Dicionário para armazenar divergências de múltiplos arquivos
all_discrepancies = {}

st.title("Análise de Divergências de Estoque")
# Exibir o texto estilizado dentro do expander
with st.expander("Upload de Arquivos",expanded=True, icon='📂'):
    
    col8, col9 = st.columns(2)
    with col8:
        st.subheader("Arquivo de Estoque Esperado")
        uploaded_estoque_esperado = st.file_uploader(
            "Upload do arquivo de estoque esperado (.csv, .xls, .xlsx)",
            type=['csv', 'xls', 'xlsx'],
            key="estoque_esperado",
            help="Arquivo `.csv`, `.txt`, `.xls` ou `xlsx` com dados de estoque (recomendado utilizar `.csv` separado por `,`)"
        )

    with col9:
        st.subheader("Arquivo de Contagem")
        uploaded_contagem = st.file_uploader(
            "Upload do arquivo de contagem (.csv ou .txt)",
            type=['csv', 'txt'],
            key="contagem",
            help="Arquivo `.txt` extraído do RFLog"
        )
    st.info("O arquivo de estoque esperado deve conter obrigatoriamente as colunas 'EAN' e 'ESTOQUE'. As demais colunas são opcionais e, se presentes, serão exibidas na tabela.")
# Processar os uploads
estoque_df, estoque_tipo = process_upload(uploaded_estoque_esperado, "estoque_esperado")
contagem_df, contagem_tipo = process_upload(uploaded_contagem, "contagem")

# Exibir mensagens de sucesso ou erro
if uploaded_estoque_esperado:
    if estoque_df is not None:
        show_temporary_success("estoque_df","Arquivo de estoque esperado carregado com sucesso!",duration=2)
    else:
        st.error("Falha ao carregar o arquivo de estoque esperado.")

if uploaded_contagem:
    if contagem_df is not None:
        show_temporary_success("contagem_df","Arquivo de contagem carregado com sucesso!",duration=2)
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
    show_summary(discrepancies)
    st.divider()
    # Exibir tabela de dados filtrados
    filtered_df = display_data_table(discrepancies)
    # Mostrar resumo
    
    # Exibir métricas do resumo dinâmico
    if not filtered_df.empty:
        total_estoque = int(filtered_df['ESTOQUE'].sum())
        print("---")
        print("total_estoque: ",total_estoque)
        total_contagem = int(filtered_df['CONTAGEM'].sum())
        print("total_contagem: ",total_contagem)
        total_divergencia_positiva = int(filtered_df[filtered_df['DIVERGÊNCIA'] > 0]['DIVERGÊNCIA'].sum())
        print("total_divergencia_positiva: ",total_divergencia_positiva)
        total_divergencia_negativa = int(filtered_df[filtered_df['DIVERGÊNCIA'] < 0]['DIVERGÊNCIA'].sum())
        print("total_divergencia_negativa: ",total_divergencia_negativa)
        total_divergencia_absoluta = int(filtered_df['DIVERGÊNCIA'].abs().sum())
        print("total_divergencia_absoluta: ",total_divergencia_absoluta)
        total_pecas_a_serem_relidas = filtered_df[filtered_df['DIVERGÊNCIA'] != 0]['PEÇAS A SEREM RELIDAS'].sum()
        print("total_pecas_a_serem_relidas: ",total_pecas_a_serem_relidas)

        st.subheader("Resumo Dinâmico")
        st.caption("(valores filtrados na tabela)")
        col5, col6, col7 = st.columns(3)
        with col5:
            st.metric("Estoque Esperado", total_estoque,border=True)
        with col6:
            st.metric('Total da Contagem com RFID', total_contagem,border=True)
        # accuracy_percentage = ((total_estoque - total_divergencia_absoluta) / total_estoque * 100) if total_estoque != 0 else 0
        # contagem_correta = total_estoque-total_divergencia_absoluta
        # print("contagem_correta: ",contagem_correta)
        # if total_estoque > 0:
        #     accuracy_percentage = max(0, (1 - (total_divergencia_absoluta / total_estoque)) * 100)
        # else:
        #     accuracy_percentage = 0  # ou 'N/A' 
        # accuracy_percentage = max(0, (contagem_correta / total_estoque) * 100)
        # if total_contagem == total_estoque:
        #     accuracy_percentage = 100
        # if total_contagem < total_estoque:
        #     accuracy_percentage = (total_contagem / total_estoque) * 100
        # if total_contagem > total_estoque:
        #     accuracy_percentage = (total_estoque / total_contagem) * 100
        accuracy_percentage = (1 - (total_divergencia_absoluta / total_estoque))*100
        print("accurracy_percentage: ",accuracy_percentage)
        with col7:
            st.metric("Acurácia do Inventário", f"{accuracy_percentage:.2f}%",border=True)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            sobra_percentage = (total_divergencia_positiva / total_estoque) * 100 if total_estoque != 0 else 0
            st.metric("Sobra", total_divergencia_positiva, delta=f"{sobra_percentage:.2f}%", delta_color='inverse',border=True)

        with col2:
            falta_percentage = (abs(total_divergencia_negativa) / total_estoque) * 100 if total_estoque != 0 else 0
            st.metric("Falta", total_divergencia_negativa, delta=f"{falta_percentage:.2f}%", delta_color='inverse',border=True)
        with col3:
            divergencia_absoluta_percentage = (total_divergencia_absoluta / total_estoque) * 100 if total_estoque != 0 else 0
            st.metric("Divergência Absoluta", total_divergencia_absoluta, delta=f"{divergencia_absoluta_percentage:.2f}%", delta_color='inverse',border=True)
        with col4:
            pecas_relidas_percentage = (total_pecas_a_serem_relidas / total_estoque) * 100 if total_estoque != 0 else 0
            st.metric("Peças a Serem Relidas", f"{int(total_pecas_a_serem_relidas)}", delta=f"{pecas_relidas_percentage:.2f}%", delta_color='inverse',border=True)
        
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
        #save_metrics(metrics)

    # Gerar gráfico de pizza para acurácia
    st.divider()
    # col_graph1,col_graph2 = st.columns(2)
    # with col_graph1:
    #     fig_pie_chart = generate_pie_chart(accuracy_percentage)
    #     st.plotly_chart(fig_pie_chart)
    # with col_graph2:
    # liquid_html = generate_liquid_chart(accuracy_percentage)
    # nested_html= grafico_resumo_inventario()
    # components.html(liquid_html, height=400)
    # components.html(nested_html,height=1000)
    dashboard_html = dynamic_dashboard(
        total_estoque,
        total_contagem,
        total_divergencia_absoluta,
        total_pecas_a_serem_relidas,
        accuracy_percentage,
        total_divergencia_positiva,
        total_divergencia_negativa
    )
    
    components.html(dashboard_html,height=1600)
    st.divider()
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