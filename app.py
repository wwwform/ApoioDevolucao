import streamlit as st
import pandas as pd
import io
import os

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Scanner Devolução", layout="wide")

st.markdown("""
<style>
    /* Tema Claro Forçado para Legibilidade */
    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
    }
    .stTextInput input {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #cbd5e1;
    }
    div[data-testid="stDataFrame"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
    }
    .stButton>button {
        background-color: #0f172a;
        color: #ffffff;
        border: none;
        height: 3rem;
    }
    /* Destaque Scanner */
    div[data-testid="stTextInput"] label {
        font-size: 1.2rem;
        font-weight: bold;
        color: #0284c7;
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
    """Carrega 'base_sap.xlsx' direto do GitHub (pasta do script)"""
    
    # Esta linha garante que ele ache o arquivo onde quer que o script esteja (PC ou Nuvem)
    pasta_script = os.path.dirname(os.path.abspath(__file__))
    caminho_arquivo = os.path.join(pasta_script, "base_sap.xlsx")
    
    if os.path.exists(caminho_arquivo):
        try:
            df = pd.read_excel(caminho_arquivo)
            df.columns = df.columns.str.strip()
            df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
            
            # Tratamento se vier como texto
            if df['Peso por Metro'].dtype == 'object':
                 df['Peso por Metro'] = df['Peso por Metro'].str.replace(',', '.').astype(float)
            
            return df[['Produto', 'Descrição do produto', 'Peso por Metro']], None
        except Exception as e:
            return None, f"Erro ao ler Excel: {str(e)}"
    
    return None, "Arquivo 'base_sap.xlsx' não encontrado no repositório."

def regra_corte(mm):
    try: return (int(float(mm)) // 500) * 500
    except: return 0

# --- 3. ESTADO ---
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

# --- 4. CARREGAMENTO AUTOMÁTICO ---
df_sap, erro_msg = carregar_base_sap()

# --- 5. INTERFACE ---
st.title("🏭 Scanner de Devolução (Web)")

if df_sap is None:
    st.error("❌ ERRO CRÍTICO")
    st.warning(f"O sistema não encontrou o arquivo `base_sap.xlsx`.")
    st.info("Solução: Faça o upload do arquivo `base_sap.xlsx` para o seu GitHub, na mesma pasta do `app.py`.")
    st.stop()

# Diagnóstico discreto
st.success(f"✅ Sistema Online | Base SAP carregada ({len(df_sap)} produtos)")

# --- 6. LÓGICA SCANNER ---
def adicionar_item():
    codigo = st.session_state.input_scanner
    if codigo:
        try:
            # Limpa espaços e tenta converter
            cod_limpo = str(codigo).strip()
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
                # Insere no topo
                st.session_state.lista_itens.insert(0, novo)
                st.toast(f"Item {cod_int} adicionado!", icon="✅")
            else:
                st.toast(f"Produto {cod_int} não encontrado na planilha.", icon="⚠️")
        except:
            st.toast("Código inválido (apenas números).", icon="❌")
        
        # Limpa campo
        st.session_state.input_scanner = ""

# Input Scanner
st.text_input("Bipar Código Aqui:", key="input_scanner", on_change=adicionar_item)

if st.button("🗑️ Limpar Lista"):
    st.session_state.lista_itens = []
    st.rerun()

st.markdown("---")

# --- 7. TABELA E RESULTADOS ---
if st.session_state.lista_itens:
    st.markdown("### Itens Lidos")
    
    df_atual = pd.DataFrame(st.session_state.lista_itens)
    
    # Editor
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
        df_export = df_final[['Cód. SAP', 'Descrição', 'Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 'Nova Dimensão (mm)', 'Peso Teórico', 'Sucata']].copy()
        
        # Formata para texto BR (1.234,567)
        for c in ['Peso Balança (kg)', 'Peso Teórico', 'Sucata', 'Peso/m']:
            df_export[c] = df_export[c].apply(formatar_br)
            
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False)
            
        st.download_button("📥 Baixar Relatório Excel", buffer.getvalue(), "Relatorio_Scanner.xlsx")
        
