import streamlit as st
import pandas as pd
import io
import os

# --- 1. CONFIGURAÇÃO VISUAL FORÇADA ---
st.set_page_config(page_title="Scanner Devolução", layout="wide")

# Força cores manuais para garantir que não fique "tudo branco" em temas escuros
st.markdown("""
<style>
    /* Fundo Geral */
    .stApp {
        background-color: #f8fafc; /* Cinza muito claro */
        color: #0f172a; /* Texto quase preto */
    }
    
    /* Inputs de Texto */
    .stTextInput input {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #cbd5e1;
    }
    
    /* Tabelas */
    div[data-testid="stDataFrame"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
    }
    
    /* Botões */
    .stButton>button {
        background-color: #0f172a;
        color: #ffffff;
        border: none;
    }
    .stButton>button:hover {
        background-color: #334155;
        color: #ffffff;
    }
    
    /* Destaque Scanner */
    div[data-testid="stTextInput"] label {
        font-size: 1.2rem;
        font-weight: bold;
        color: #0ea5e9;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES ---

def formatar_br(valor):
    """3 casas decimais: 1.234,567"""
    try:
        if pd.isna(valor) or valor == "": return "0,000"
        val = float(valor)
        return f"{val:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

@st.cache_data
def carregar_base_sap():
    """Tenta carregar 'base_sap.xlsx' da pasta atual"""
    # Pega o diretório onde o script está rodando
    pasta_atual = os.getcwd()
    caminho_arquivo = os.path.join(pasta_atual, "base_sap.xlsx")
    
    if os.path.exists(caminho_arquivo):
        try:
            df = pd.read_excel(caminho_arquivo)
            df.columns = df.columns.str.strip()
            df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
            if df['Peso por Metro'].dtype == 'object':
                 df['Peso por Metro'] = df['Peso por Metro'].str.replace(',', '.').astype(float)
            return df[['Produto', 'Descrição do produto', 'Peso por Metro']], caminho_arquivo
        except Exception as e:
            return None, str(e)
    return None, "Arquivo não encontrado."

def regra_corte(mm):
    try: return (int(float(mm)) // 500) * 500
    except: return 0

# --- 3. INICIALIZAÇÃO ---
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

# Carrega Base
df_sap, msg_erro = carregar_base_sap()

# --- 4. INTERFACE ---
st.title("🏭 Scanner de Devolução (v10)")

# Diagnóstico de Arquivo (Para você saber se carregou)
if df_sap is not None:
    st.success(f"✅ Base SAP Carregada! ({len(df_sap)} produtos)")
else:
    st.error(f"❌ ERRO: Não foi possível carregar 'base_sap.xlsx'.")
    st.info(f"O sistema procurou na pasta: {os.getcwd()}")
    st.info("Certifique-se que o arquivo 'base_sap.xlsx' está nesta pasta.")
    st.stop() # Para tudo se não tiver base

# --- 5. LÓGICA SCANNER ---
def adicionar_item():
    codigo = st.session_state.input_scanner
    if codigo:
        try:
            cod_int = int(str(codigo).strip())
            produto = df_sap[df_sap['Produto'] == cod_int]
            
            if not produto.empty:
                novo = {
                    "Cód. SAP": cod_int,
                    "Descrição": produto.iloc[0]['Descrição do produto'],
                    "Qtd": 1,
                    "Peso Balança (kg)": 0.000,
                    "Tamanho (mm)": 0,
                    "Peso/m": produto.iloc[0]['Peso por Metro']
                }
                st.session_state.lista_itens.insert(0, novo)
            else:
                st.toast(f"Produto {cod_int} não cadastrado na base.", icon="⚠️")
        except:
            st.toast("Código inválido.", icon="❌")
        
        st.session_state.input_scanner = ""

# Input Scanner
st.text_input("Bipar Código Aqui:", key="input_scanner", on_change=adicionar_item)

# Botão Limpar
if st.button("Limpar Lista"):
    st.session_state.lista_itens = []
    st.rerun()

st.markdown("---")

# --- 6. TABELA E CÁLCULOS ---
if st.session_state.lista_itens:
    df_atual = pd.DataFrame(st.session_state.lista_itens)
    
    st.markdown("### Itens Lidos")
    df_editado = st.data_editor(
        df_atual,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Cód. SAP": st.column_config.NumberColumn(format="%d", disabled=True),
            "Descrição": st.column_config.TextColumn(disabled=True),
            "Qtd": st.column_config.NumberColumn(min_value=1, step=1),
            "Peso Balança (kg)": st.column_config.NumberColumn(format="%.3f", min_value=0.0),
            "Tamanho (mm)": st.column_config.NumberColumn(format="%d", min_value=0),
            "Peso/m": st.column_config.NumberColumn(format="%.3f", disabled=True)
        }
    )
    
    # Processamento Final
    if not df_editado.empty:
        df_final = df_editado.copy()
        
        # Garante tipos numéricos
        cols_num = ['Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 'Peso/m']
        for c in cols_num:
            df_final[c] = pd.to_numeric(df_final[c], errors='coerce').fillna(0)
            
        # Cálculos
        df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(regra_corte)
        df_final['Peso Teórico'] = (df_final['Nova Dimensão (mm)']/1000) * df_final['Peso/m'] * df_final['Qtd']
        df_final['Sucata'] = df_final['Peso Balança (kg)'] - df_final['Peso Teórico']
        
        # Totais
        c1, c2, c3 = st.columns(3)
        c1.metric("Itens", len(df_final))
        c2.metric("Peso Real Total", formatar_br(df_final['Peso Balança (kg)'].sum()) + " kg")
        c3.metric("Sucata Total", formatar_br(df_final['Sucata'].sum()) + " kg")
        
        # Exportação Excel
        df_export = df_final[['Cód. SAP', 'Descrição', 'Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 'Nova Dimensão (mm)', 'Peso Teórico', 'Sucata']].copy()
        for c in ['Peso Balança (kg)', 'Peso Teórico', 'Sucata']:
            df_export[c] = df_export[c].apply(formatar_br)
            
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False)
            
        st.download_button("📥 Baixar Relatório", buffer.getvalue(), "Relatorio.xlsx")
