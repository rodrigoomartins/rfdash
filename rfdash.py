import streamlit as st
import pandas as pd
from utils.config import process_upload, show_temporary_success, show_summary, calculate_discrepancies, display_data_table, generate_timestamp, dynamic_dashboard, generate_pdf_in_memory, pick_expected_columns_ui, standardize_expected_df, pick_pdf_columns_ui
import streamlit.components.v1 as components
import base64

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

    Os arquivos CSV podem ter vírgula ou ponto e vírgula como separador, com ou sem aspas, e codificações variadas (UTF-8, Latin-1/CP1252 etc.). A aplicação detecta isso automaticamente.
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
    st.info("Após carregar o **estoque esperado**, selecione abaixo quais colunas correspondem a **EAN** e **ESTOQUE**. Suportamos CSV com separador vírgula `,` ou ponto e vírgula `;`, com ou sem aspas, e diferentes codificações (UTF-8, Latin-1/CP1252 etc.). As demais colunas são opcionais e, se presentes, serão exibidas na tabela.")
# Processar os uploads
estoque_df, estoque_tipo = process_upload(uploaded_estoque_esperado, "estoque_esperado")
contagem_df, contagem_tipo = process_upload(uploaded_contagem, "contagem")
# === Mapeamento de colunas do ESTOQUE ESPERADO ===
if estoque_df is not None:
    with st.expander("Mapeamento de Colunas do Estoque Esperado", expanded=True):
        mapping = pick_expected_columns_ui(estoque_df)
        try:
            estoque_df = standardize_expected_df(estoque_df, mapping)
            st.success("Mapeamento aplicado. Colunas padronizadas para 'EAN' e 'ESTOQUE'.")
        except Exception as e:
            st.error(f"Não foi possível aplicar o mapeamento: {e}")
            estoque_df = None

# Exibir mensagens de sucesso ou erro
if uploaded_estoque_esperado:
    if estoque_df is not None:
        show_temporary_success("estoque_df","Arquivo de estoque esperado carregado com sucesso!",duration=2)
    else:
        st.error("Falha ao carregar/normalizar o arquivo de estoque esperado. Verifique o mapeamento de colunas.")

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
    # opcao = st.radio("Filtro rápido",[
    #     "Tudo",
    #     "Divergências",
    #     "Sobra",
    #     "Falta"
    # ],
    # horizontal=True
    # )
    # # Aplicar filtro de acordo com a seleção
    # if opcao == "Divergências":
    #     df_filtrado = discrepancies[discrepancies["DIVERGÊNCIA"] != 0]
    # elif opcao == "Sobra":
    #     df_filtrado = discrepancies[discrepancies["DIVERGÊNCIA"] > 0]
    # elif opcao == "Falta":
    #     df_filtrado = discrepancies[discrepancies["DIVERGÊNCIA"] < 0]
    # else:
    #     df_filtrado = discrepancies
    # Exibir tabela de dados filtrados
    
    #     filtro=option_menu(
    #         menu_title=None,
    #         options=[
    #             "Tudo",
    #             "Divergências",
    #             "Sobra",
    #             "Falta"
    #         ],
    #         icons=[
    #             "list",
    #             "exclamation-triangle",
    #             "arrow-up",
    #             "arrow-down"
    #         ],
    #         orientation="horizontal",
    #         default_index=0,
    #         styles={
    #             "container": {
    #                 "display": "flex",
    #                 "justify-content": "flex-start",  # Alinhamento à esquerda
    #                 "padding": "0px",
    #                 "margin-bottom": "12px",
    #                 "background-color": "#111",  # Mais discreto
    #                 "border-radius": "6px",
    #                 "flex-wrap": "wrap",  # Garante que quebra em telas menores
    #             },
    #             "icon": {"color": "white", "font-size": "12px"},
    #             "nav-link": {
    #                 "font-size": "12px",
    #                 "padding": "2px 10px",  # Reduz a altura/largura
    #                 "margin": "0 2px",
    #                 "color": "#ccc",
    #                 "--hover-color": "#222",
    #                 "border-radius": "4px"
    #             },
    #             "nav-link-selected": {
    #                 "background-color": "#2d4030",
    #                 "color": "#fff",
    #                 "font-weight": "600"
    #             },
    #         }
    #     )
        # Aplica estilo CSS personalizado
    col_filtro1, col_filtro2 = st.columns([1,5])
    with col_filtro1:
        st.markdown("""
            <style>
            div[data-baseweb="select"] {
                font-size: 14px !important;
                width: 250px !important;
            }
            label {
                font-size: 12px !important;
                color: #fff;
            }
            </style>
        """, unsafe_allow_html=True)

        # Selectbox normal
        filtro = st.selectbox(
            "Filtro rápido:",
            ["Tudo", "Divergências", "Sobra", "Falta"],
        )
    if filtro == "Divergências":
        df_filtrado = discrepancies[discrepancies["DIVERGÊNCIA"] != 0]
    elif filtro == "Sobra":
        df_filtrado = discrepancies[discrepancies["DIVERGÊNCIA"] > 0]
    elif filtro == "Falta":
        df_filtrado = discrepancies[discrepancies["DIVERGÊNCIA"] < 0]
    else:
        df_filtrado = discrepancies
    
    filtered_df = display_data_table(df_filtrado)
    # Mostrar resumo
    
    # Atualize o session_state com o DataFrame filtrado
    st.session_state.filtered_df = filtered_df

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
    dashboard_html = dynamic_dashboard(
        total_estoque,
        total_contagem,
        total_divergencia_absoluta,
        total_pecas_a_serem_relidas,
        accuracy_percentage,
        total_divergencia_positiva,
        total_divergencia_negativa
    )
    
    from utils.config import pick_pdf_columns_ui, generate_pdf_in_memory, generate_timestamp

    with st.expander("Exportar PDF", expanded=False, icon="🖨️"):
        # É ESSENCIAL usar o mesmo DF que está na tabela:
        df_export = st.session_state.get("filtered_df", filtered_df)

        # Agora o multiselect já vem com todas as colunas do df_export, na ordem certa
        cols_pdf = pick_pdf_columns_ui(df_export, key="pdf_cols_export")

        with st.form("pdf_form", clear_on_submit=False):
            font_size = st.number_input("Tamanho da fonte", 6, 12, 8, 1)
            orient = st.selectbox("Orientação", ["L", "P"], index=0,help="L = paisagem, P = retrato")
            submit = st.form_submit_button("Gerar e Baixar PDF", use_container_width=True)

        if submit:
            with st.spinner("Gerando o PDF..."):
                pdf_bytes = generate_pdf_in_memory(
                    df_export,
                    font_size=font_size,
                    orientation=orient,
                    include_columns=cols_pdf,   # <- exatamente as colunas da tabela, mesma ordem
                )

            st.download_button(
                "Baixar PDF",
                data=pdf_bytes,
                file_name=f"relatorio_divergencia_{generate_timestamp()}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="dl_pdf_export",
            )