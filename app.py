import streamlit as st
import pandas as pd
import io

# --- 1. CONFIGURAÇÃO BÁSICA ---
st.set_page_config(
    page_title="Apoio Devolução",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CSS APENAS PARA O BOTÃO (Para não quebrar o resto) ---
st.markdown("""
<style>
    /* Aumenta o tamanho do botão para ficar clicável e visível */
    .stButton>button {
        height: 3.5rem;
        font-weight: bold;
        font-size: 16px;
        border: 2px solid #ccc;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. FUNÇÕES (Mesma lógica que funciona) ---
def formatar_brasileiro(valor):
    try:
        if pd.isna(valor): return ""
        val = float(valor)
        texto = f"{val:,.2f}"
        return texto.replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(valor)

def carregar_sap(file):
    try:
        if file.name.endswith('.csv'): 
            try: df = pd.read_csv(file, sep=';', decimal=',')
            except: df = pd.read_csv(file)
        else: 
            df = pd.read_excel(file)
            
        df.columns = df.columns.str.strip()
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        
        if df['Peso por Metro'].dtype == 'object':
             df['Peso por Metro'] = df['Peso por Metro'].str.replace(',', '.').astype(float)
             
        return df[['Produto', 'Descrição do produto', 'Peso por Metro']]
    except: return None

def regra_corte(mm):
    try: return (int(float(mm)) // 500) * 500
    except: return 0

# --- 4. BARRA LATERAL ---
with st.sidebar:
    st.header("📂 Arquivo SAP")
    file_sap = st.file_uploader("Carregue a tabela aqui", type=['xlsx', 'xls', 'csv'])
    st.caption("A tabela deve conter: Produto, Descrição e Peso por Metro.")

# --- 5. TELA PRINCIPAL ---
st.title("🏭 Calculadora de Devolução")
st.markdown("### 1. Digitação dos Dados")

# Validação do Arquivo SAP
if not file_sap:
    st.error("❌ PARADO: Carregue a planilha SAP na barra lateral esquerda para começar.")
    st.stop()

df_sap = carregar_sap(file_sap)
if df_sap is None:
    st.error("❌ ERRO: O arquivo SAP não pôde ser lido. Verifique o formato.")
    st.stop()
else:
    st.success("✅ Base SAP carregada com sucesso!")

# --- 6. TABELA DE ENTRADA ---
if 'data_input' not in st.session_state:
    st.session_state.data_input = pd.DataFrame(
        [{"Reserva": "", "Cód. SAP": None, "Qtd": 1, "Peso Balança (kg)": 0.0, "Tamanho (mm)": 0}],
    )

with st.container():
    df_digitado = st.data_editor(
        st.session_state.data_input,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Reserva": st.column_config.TextColumn("Reserva (Caneta)"),
            "Cód. SAP": st.column_config.NumberColumn("Cód. Material (SAP)", format="%d", required=True),
            "Qtd": st.column_config.NumberColumn("Qtd Peças", min_value=1, step=1, required=True),
            "Peso Balança (kg)": st.column_config.NumberColumn("Peso Real (kg)", min_value=0.0, format="%.2f", required=True),
            "Tamanho (mm)": st.column_config.NumberColumn("Tamanho (mm)", min_value=0, step=1, required=True),
        },
        key="editor_principal"
    )

st.write("") # Espaço em branco

# --- 7. BOTÃO DE CÁLCULO ---
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    if st.button("CALCULAR E GERAR RELATÓRIO", type="primary"):
        # Lógica de Cálculo
        if df_digitado['Cód. SAP'].sum() == 0:
            st.warning("⚠️ A tabela está vazia.")
        else:
            # Tratamento
            df_work = df_digitado.copy()
            df_work['Cód. SAP'] = pd.to_numeric(df_work['Cód. SAP'], errors='coerce').fillna(0).astype(int)
            df_work['Qtd'] = pd.to_numeric(df_work['Qtd'], errors='coerce').fillna(0)
            df_work['Tamanho (mm)'] = pd.to_numeric(df_work['Tamanho (mm)'], errors='coerce').fillna(0)
            df_work['Peso Balança (kg)'] = pd.to_numeric(df_work['Peso Balança (kg)'], errors='coerce').fillna(0.0)

            # Cruzamento
            df_final = df_work.merge(df_sap, left_on='Cód. SAP', right_on='Produto', how='left')
            df_final['Descrição do produto'] = df_final['Descrição do produto'].fillna("NÃO ENCONTRADO")
            df_final['Peso por Metro'] = df_final['Peso por Metro'].fillna(0.0)

            # Contas
            df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(regra_corte)
            df_final['Peso Teórico (Calc)'] = (
                (df_final['Nova Dimensão (mm)'] / 1000.0) * df_final['Peso por Metro'] * df_final['Qtd']
            )
            df_final['Sucata (Dif)'] = df_final['Peso Balança (kg)'] - df_final['Peso Teórico (Calc)']

            # Organização
            cols_output = [
                'Reserva', 'Cód. SAP', 'Descrição do produto', 'Qtd', 
                'Peso Balança (kg)', 'Tamanho (mm)', 
                'Nova Dimensão (mm)', 'Peso Teórico (Calc)', 'Sucata (Dif)'
            ]
            df_view = df_final[cols_output]

            st.divider()
            st.markdown("### 📊 Resultado Final")

            # Totais
            t1, t2, t3 = st.columns(3)
            t1.metric("Itens", len(df_view))
            
            # Formatação para exibição na tela (mantendo ponto do Python para métrica funcionar)
            t2.metric("Peso Total", f"{df_view['Peso Balança (kg)'].sum():.2f} kg")
            t3.metric("Sucata Total", f"{df_view['Sucata (Dif)'].sum():.2f} kg")

            # Tabela Visual
            st.dataframe(df_view, use_container_width=True)

            # Exportação Excel (Formatado BR)
            df_export = df_view.copy()
            cols_fmt = ['Peso Balança (kg)', 'Peso Teórico (Calc)', 'Sucata (Dif)']
            for col in cols_fmt:
                df_export[col] = df_export[col].apply(formatar_brasileiro)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False)
            
            st.download_button(
                label="📥 BAIXAR PLANILHA FORMATADA ",
                data=buffer.getvalue(),
                file_name="Relatorio_Final.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="secondary"
            )
