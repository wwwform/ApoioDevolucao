import streamlit as st
import pandas as pd
import io
import os

# --- 1. CONFIGURAÇÃO VISUAL BLINDADA ---
st.set_page_config(page_title="Scanner Pro", layout="wide")

# CSS Forçado: Garante fundo claro e texto preto independente do PC do usuário
st.markdown("""
<style>
    /* Força Fundo Branco e Texto Preto */
    .stApp {
        background-color: #ffffff !important;
        color: #000000 !important;
    }
    
    /* Inputs */
    .stTextInput input, .stNumberInput input {
        background-color: #f1f5f9 !important;
        color: #000000 !important;
        border: 1px solid #cbd5e1 !important;
    }
    
    /* Tabelas */
    div[data-testid="stDataFrame"] {
        background-color: #ffffff !important;
        border: 1px solid #000000 !important;
    }
    
    /* Botões */
    .stButton>button {
        background-color: #000000 !important;
        color: #ffffff !important;
        border: none;
        height: 3rem;
        font-weight: bold;
    }
    
    /* Textos e Labels */
    h1, h2, h3, p, label {
        color: #000000 !important;
    }
    
    /* Destaque Campo Scanner */
    div[data-testid="stTextInput"] label {
        color: #2563eb !important; /* Azul forte */
        font-size: 1.3rem !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES ---

def formatar_br(valor):
    """3 casas decimais (1.000,000)"""
    try:
        if pd.isna(valor) or valor == "": return "0,000"
        val = float(valor)
        return f"{val:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

@st.cache_data
def carregar_sap(caminho_ou_arquivo):
    """Função genérica que lê tanto arquivo do GitHub quanto Upload manual"""
    try:
        if isinstance(caminho_ou_arquivo, str): # Se for caminho do GitHub
            if caminho_ou_arquivo.endswith('.csv'):
                try: df = pd.read_csv(caminho_ou_arquivo, sep=';', decimal=',')
                except: df = pd.read_csv(caminho_ou_arquivo)
            else:
                df = pd.read_excel(caminho_ou_arquivo)
        else: # Se for Upload manual
            if caminho_ou_arquivo.name.endswith('.csv'):
                try: df = pd.read_csv(caminho_ou_arquivo, sep=';', decimal=',')
                except: df = pd.read_csv(caminho_ou_arquivo)
            else:
                df = pd.read_excel(caminho_ou_arquivo)

        df.columns = df.columns.str.strip()
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        
        if df['Peso por Metro'].dtype == 'object':
             df['Peso por Metro'] = df['Peso por Metro'].str.replace(',', '.').astype(float)
        
        return df[['Produto', 'Descrição do produto', 'Peso por Metro']]
    except Exception as e:
        return None

def regra_corte(mm):
    try: return (int(float(mm)) // 500) * 500
    except: return 0

# --- 3. INICIALIZAÇÃO E CARREGAMENTO ---
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

# TENTA CARREGAR AUTOMÁTICO
pasta_script = os.path.dirname(os.path.abspath(__file__))
caminho_fixo = os.path.join(pasta_script, "base_sap.xlsx")
df_sap = None
modo_carregamento = "Indefinido"

if os.path.exists(caminho_fixo):
    df_sap = carregar_sap(caminho_fixo)
    modo_carregamento = "Automático (GitHub)"

# SE FALHAR O AUTOMÁTICO, PEDE MANUAL (FALLBACK)
st.title("🏭 Scanner de Devolução")

if df_sap is None:
    st.warning("⚠️ Arquivo padrão não encontrado. Carregue a base SAP abaixo para continuar:")
    arquivo_upload = st.file_uploader("Upload Base SAP", type=['xlsx', 'csv'])
    
    if arquivo_upload:
        df_sap = carregar_sap(arquivo_upload)
        modo_carregamento = "Manual (Upload)"
    else:
        st.stop() # Para aqui até o usuário subir o arquivo

# Feedback discreto
st.toast(f"Base carregada via: {modo_carregamento}", icon="✅")

# --- 4. LÓGICA DO SCANNER ---
def adicionar_item():
    codigo = st.session_state.input_scanner
    if codigo:
        try:
            cod_limpo = str(codigo).strip()
            # Remove prefixos comuns de QR Code se houver (ex: 'P:123')
            if ":" in cod_limpo: cod_limpo = cod_limpo.split(":")[-1]
            
            cod_int = int(cod_limpo)
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
                st.toast(f"Item {cod_int} OK!", icon="📦")
            else:
                st.toast(f"Produto {cod_int} não existe na base SAP carregada.", icon="🚫")
        except:
            st.toast("Erro ao ler código. Tente novamente.", icon="❌")
        
        st.session_state.input_scanner = ""

# Input Scanner (Foco Principal)
st.text_input("BIPAR CÓDIGO AQUI:", key="input_scanner", on_change=adicionar_item)

if st.button("Limpar Lista"):
    st.session_state.lista_itens = []
    st.rerun()

st.markdown("---")

# --- 5. TABELA DE EDIÇÃO ---
if st.session_state.lista_itens:
    df_atual = pd.DataFrame(st.session_state.lista_itens)
    
    st.info("👇 Digite o PESO REAL e o TAMANHO na tabela:")
    
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

    if not df_editado.empty:
        df_final = df_editado.copy()
        
        # Tipagem segura
        for c in ['Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 'Peso/m']:
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
        colunas_finais = ['Cód. SAP', 'Descrição', 'Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 'Nova Dimensão (mm)', 'Peso Teórico', 'Sucata']
        df_export = df_final[colunas_finais].copy()
        
        for c in ['Peso Balança (kg)', 'Peso Teórico', 'Sucata']:
            df_export[c] = df_export[c].apply(formatar_br)
            
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False)
            
        st.download_button("📥 BAIXAR EXCEL FINAL", buffer.getvalue(), "Relatorio_Scanner.xlsx")
