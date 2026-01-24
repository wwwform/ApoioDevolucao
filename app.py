import streamlit as st
import pandas as pd
import io

# --- 1. CONFIGURAÇÃO DE PÁGINA ---
st.set_page_config(
    page_title="Apoio devolução",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. DESIGN SYSTEM (CSS PROFISSIONAL) ---
st.markdown("""
<style>
    /* Fundo Geral - Cinza Azulado Leve para contraste */
    .stApp {
        background-color: #eef2f6;
    }
    
    /* Barra Lateral - Azul Escuro */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #d1d5db;
    }
    
    /* Títulos */
    h1 {
        color: #1e3a8a; /* Azul Marinho */
        font-weight: 800;
        font-family: 'Arial', sans-serif;
    }
    h2, h3 {
        color: #334155;
        font-weight: 600;
    }
    
    /* Containers (Cartões) */
    .css-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
    }
    
    /* Uploaders */
    .stFileUploader {
        border: 2px dashed #94a3b8;
        border-radius: 8px;
        padding: 10px;
        background-color: #f8fafc;
    }
    
    /* Botão Principal */
    .stButton>button {
        background-color: #15803d; /* Verde Sólido */
        color: white;
        border: none;
        border-radius: 6px;
        height: 3.5rem;
        font-size: 16px;
        font-weight: bold;
        width: 100%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.2s;
    }
    .stButton>button:hover {
        background-color: #166534;
        transform: translateY(-1px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.15);
        color: white;
    }
    
    /* Tabelas e Métricas */
    div[data-testid="stMetric"] {
        background-color: white;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #1e3a8a;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# --- 3. FUNÇÕES DE NEGÓCIO ---
def formatar_brasileiro(valor):
    """1234.56 -> 1.234,56"""
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
            # Tenta ler CSV com separador ; (comum excel br) ou ,
            try: df = pd.read_csv(file, sep=';', decimal=',')
            except: df = pd.read_csv(file)
        else: 
            df = pd.read_excel(file)
            
        df.columns = df.columns.str.strip()
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        
        # Garante float no peso
        if df['Peso por Metro'].dtype == 'object':
             df['Peso por Metro'] = df['Peso por Metro'].str.replace(',', '.').astype(float)
             
        return df[['Produto', 'Descrição do produto', 'Peso por Metro']]
    except: return None

def regra_corte(mm):
    try: return (int(float(mm)) // 500) * 500
    except: return 0

# --- 4. INTERFACE ---

# Cabeçalho com Container Visual
with st.container():
    st.title("🏭 Calculadora de Devolução")
    st.markdown("**Sistema de Controle de Sucata e Pesos Teóricos**")
    st.markdown("---")

# Barra Lateral
with st.sidebar:
    st.header("📂 Base de Dados")
    uploaded_file = st.file_uploader("Importar Planilha SAP", type=['xlsx', 'csv'])
    
    st.info("ℹ️ A planilha deve conter: 'Produto', 'Descrição do produto' e 'Peso por Metro'.")
    st.caption("Versão 7.0 (High Contrast)")

# Verificação Inicial
if not uploaded_file:
    st.warning("👈 Comece carregando a **Planilha SAP** no menu lateral esquerdo.")
    st.stop()

df_sap = carregar_sap(uploaded_file)
if df_sap is None:
    st.error("❌ Erro na leitura do arquivo. Verifique o formato.")
    st.stop()

# --- 5. ÁREA DE TRABALHO (CARTÃO BRANCO) ---
st.markdown("### 📝 Entrada de Dados")

# Inicialização do Estado
if 'data_input' not in st.session_state:
    st.session_state.data_input = pd.DataFrame(
        [{"Reserva": "", "Cód. SAP": None, "Qtd": 1, "Peso Balança (kg)": 0.0, "Tamanho (mm)": 0}],
    )

# Tabela de Entrada
with st.container():
    # Isso cria uma "caixa" visual ao redor da tabela
    st.info("Digite os dados das etiquetas abaixo:")
    
    df_digitado = st.data_editor(
        st.session_state.data_input,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Reserva": st.column_config.TextColumn("Reserva", help="Nº Caneta"),
            "Cód. SAP": st.column_config.NumberColumn("Cód. Material", format="%d", required=True),
            "Qtd": st.column_config.NumberColumn("Qtd", min_value=1, step=1, required=True),
            "Peso Balança (kg)": st.column_config.NumberColumn("Peso Real (kg)", min_value=0.0, format="%.2f", required=True),
            "Tamanho (mm)": st.column_config.NumberColumn("Tamanho (mm)", min_value=0, step=1, required=True),
        },
        key="editor_principal"
    )

st.markdown("###") # Espaçamento

# Botão de Ação
col_b1, col_b2, col_b3 = st.columns([1, 2, 1])
with col_b2:
    btn_calcular = st.button("🔄 PROCESSAR CÁLCULOS E FORMATAR")

# --- 6. PROCESSAMENTO E RESULTADOS ---
if btn_calcular:
    if df_digitado['Cód. SAP'].sum() == 0:
        st.error("⚠️ A tabela está vazia. Preencha os dados.")
    else:
        # Tratamento de Tipos
        df_work = df_digitado.copy()
        df_work['Cód. SAP'] = pd.to_numeric(df_work['Cód. SAP'], errors='coerce').fillna(0).astype(int)
        df_work['Qtd'] = pd.to_numeric(df_work['Qtd'], errors='coerce').fillna(0)
        df_work['Tamanho (mm)'] = pd.to_numeric(df_work['Tamanho (mm)'], errors='coerce').fillna(0)
        df_work['Peso Balança (kg)'] = pd.to_numeric(df_work['Peso Balança (kg)'], errors='coerce').fillna(0.0)

        # Cruzamento (VLOOKUP)
        df_final = df_work.merge(df_sap, left_on='Cód. SAP', right_on='Produto', how='left')
        
        # Tratamento de Nulos Pós-Merge
        df_final['Descrição do produto'] = df_final['Descrição do produto'].fillna("ITEM NÃO CADASTRADO")
        df_final['Peso por Metro'] = df_final['Peso por Metro'].fillna(0.0)

        # Cálculos Matemáticos
        df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(regra_corte)
        
        df_final['Peso Teórico (Calc)'] = (
            (df_final['Nova Dimensão (mm)'] / 1000.0) * df_final['Peso por Metro'] * df_final['Qtd']
        )
        
        df_final['Sucata (Dif)'] = df_final['Peso Balança (kg)'] - df_final['Peso Teórico (Calc)']

        # Seleção de Colunas
        cols_output = [
            'Reserva', 'Cód. SAP', 'Descrição do produto', 'Qtd', 
            'Peso Balança (kg)', 'Tamanho (mm)', 
            'Nova Dimensão (mm)', 'Peso Teórico (Calc)', 'Sucata (Dif)'
        ]
        df_view = df_final[cols_output]

        # --- ÁREA DE RESULTADOS ---
        st.markdown("---")
        st.markdown("### 📊 Resultado da Conferência")

        # Cards de Métricas
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Itens", len(df_view))
        c2.metric("Peso Real Total", f"{df_view['Peso Balança (kg)'].sum():,.2f} kg".replace(",", "X").replace(".", ",").replace("X", "."))
        c3.metric("Peso Teórico Total", f"{df_view['Peso Teórico (Calc)'].sum():,.2f} kg".replace(",", "X").replace(".", ",").replace("X", "."))
        
        total_sucata = df_view['Sucata (Dif)'].sum()
        c4.metric("Diferença (Sucata)", f"{total_sucata:,.2f} kg".replace(",", "X").replace(".", ",").replace("X", "."), delta_color="off")

        # Tabela Formatada (Visual)
        st.dataframe(
            df_view.style.format({
                "Peso Balança (kg)": "{:,.2f}",
                "Peso Teórico (Calc)": "{:,.2f}",
                "Sucata (Dif)": "{:,.2f}"
            }),
            use_container_width=True
        )

        # --- EXPORTAÇÃO EXCEL (FORMATO BRASIL) ---
        df_export = df_view.copy()
        cols_fmt = ['Peso Balança (kg)', 'Peso Teórico (Calc)', 'Sucata (Dif)']
        for col in cols_fmt:
            df_export[col] = df_export[col].apply(formatar_brasileiro)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False)
        
        st.download_button(
            label="📥 BAIXAR RELATÓRIO FORMATADO (SAP)",
            data=buffer.getvalue(),
            file_name="Relatorio_Devolucao_BR.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
