import streamlit as st
import pandas as pd
import io
import os

# --- CONFIGURAÇÃO BÁSICA (SEM CSS INVASIVO) ---
st.set_page_config(page_title="Scanner Devolução", layout="wide")

# CSS Mínimo apenas para destacar o campo de leitura
st.markdown("""
<style>
    /* Destaque apenas no label do scanner para facilitar o operador */
    div[data-testid="stTextInput"] label {
        font-size: 1.2rem;
        font-weight: bold;
        color: #2563eb; 
    }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES ---

def formatar_br(valor):
    """3 casas decimais (1.000,000)"""
    try:
        if pd.isna(valor) or valor == "": return "0,000"
        val = float(valor)
        return f"{val:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

@st.cache_data
def carregar_sap(caminho_ou_arquivo):
    """Lê arquivo do GitHub ou Upload Manual"""
    try:
        # Verifica se é string (caminho) ou objeto (upload)
        if isinstance(caminho_ou_arquivo, str):
            arquivo = caminho_ou_arquivo
            if arquivo.endswith('.csv'):
                try: df = pd.read_csv(arquivo, sep=';', decimal=',')
                except: df = pd.read_csv(arquivo)
            else:
                df = pd.read_excel(arquivo)
        else:
            arquivo = caminho_ou_arquivo
            if arquivo.name.endswith('.csv'):
                try: df = pd.read_csv(arquivo, sep=';', decimal=',')
                except: df = pd.read_csv(arquivo)
            else:
                df = pd.read_excel(arquivo)

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

# --- ESTADO (Mantém os dados na tela) ---
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

# --- CARREGAMENTO DO ARQUIVO (Híbrido) ---
# 1. Tenta achar automático no servidor/pasta
pasta_script = os.path.dirname(os.path.abspath(__file__))
caminho_fixo = os.path.join(pasta_script, "base_sap.xlsx")
df_sap = None

if os.path.exists(caminho_fixo):
    df_sap = carregar_sap(caminho_fixo)

# 2. Se falhar, mostra botão de upload (Plano B)
st.title("🏭 Scanner de Devolução")

if df_sap is None:
    st.warning("⚠️ Base SAP não encontrada automaticamente. Faça upload manual:")
    arquivo_upload = st.file_uploader("Upload Base SAP", type=['xlsx', 'csv'])
    if arquivo_upload:
        df_sap = carregar_sap(arquivo_upload)
    else:
        st.stop() # Para aqui até resolver

# --- LÓGICA DE BIPAGEM SIMPLES ---
def adicionar_item():
    codigo = st.session_state.input_scanner
    if codigo:
        try:
            # Limpeza do código lido
            cod_limpo = str(codigo).strip()
            if ":" in cod_limpo: cod_limpo = cod_limpo.split(":")[-1] # Remove prefixos
            
            cod_int = int(cod_limpo)
            
            # Busca no SAP
            produto = df_sap[df_sap['Produto'] == cod_int]
            
            if not produto.empty:
                # Adiciona APENAS o que o sistema sabe. O resto o operador preenche.
                novo = {
                    "Reserva": "", # Operador preenche
                    "Cód. SAP": cod_int,
                    "Descrição": produto.iloc[0]['Descrição do produto'],
                    "Qtd": 1,      # Padrão 1
                    "Peso Balança (kg)": 0.000, # Operador preenche
                    "Tamanho (mm)": 0,          # Operador preenche
                    "Peso/m": produto.iloc[0]['Peso por Metro'] # Oculto mas usado no cálculo
                }
                st.session_state.lista_itens.insert(0, novo)
                st.toast(f"Item {cod_int} bipado!", icon="✅")
            else:
                st.toast(f"Código {cod_int} não encontrado na base.", icon="⚠️")
        except:
            st.toast("Erro na leitura do código.", icon="❌")
        
        # Limpa o campo para o próximo bip
        st.session_state.input_scanner = ""

# CAMPO DE SCANNER (Foco)
st.text_input("BIPAR CÓDIGO DO MATERIAL:", key="input_scanner", on_change=adicionar_item)

if st.button("Limpar Tudo"):
    st.session_state.lista_itens = []
    st.rerun()

st.markdown("---")

# --- TABELA DE EDIÇÃO (O CORAÇÃO DO SISTEMA) ---
if st.session_state.lista_itens:
    df_atual = pd.DataFrame(st.session_state.lista_itens)
    
    st.markdown("### Conferência")
    
    # Tabela igual à que você gostou antes
    df_editado = st.data_editor(
        df_atual,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Reserva": st.column_config.TextColumn("Reserva (Caneta)"),
            "Cód. SAP": st.column_config.NumberColumn(format="%d", disabled=True),
            "Descrição": st.column_config.TextColumn(disabled=True),
            "Qtd": st.column_config.NumberColumn(min_value=1, step=1),
            "Peso Balança (kg)": st.column_config.NumberColumn(format="%.3f", min_value=0.0),
            "Tamanho (mm)": st.column_config.NumberColumn(format="%d", min_value=0),
            "Peso/m": st.column_config.NumberColumn(disabled=True) # Apenas visual
        }
    )

    if not df_editado.empty:
        df_final = df_editado.copy()
        
        # Tipagem
        for c in ['Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 'Peso/m']:
            df_final[c] = pd.to_numeric(df_final[c], errors='coerce').fillna(0)

        # Cálculos
        df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(regra_corte)
        df_final['Peso Teórico'] = (df_final['Nova Dimensão (mm)']/1000) * df_final['Peso/m'] * df_final['Qtd']
        df_final['Sucata'] = df_final['Peso Balança (kg)'] - df_final['Peso Teórico']

        # Totais
        c1, c2, c3 = st.columns(3)
        c1.metric("Itens", len(df_final))
        c2.metric("Peso Total", formatar_br(df_final['Peso Balança (kg)'].sum()) + " kg")
        c3.metric("Sucata Total", formatar_br(df_final['Sucata'].sum()) + " kg")

        # Exportação Excel
        colunas_finais = ['Reserva', 'Cód. SAP', 'Descrição', 'Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 'Nova Dimensão (mm)', 'Peso Teórico', 'Sucata']
        
        # Garante que colunas existem
        for c in colunas_finais:
            if c not in df_final.columns: df_final[c] = ""
            
        df_export = df_final[colunas_finais].copy()
        
        # Formata para BR
        for c in ['Peso Balança (kg)', 'Peso Teórico', 'Sucata']:
            if c in df_export.columns:
                df_export[c] = df_export[c].apply(formatar_br)
            
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False)
            
        st.download_button("📥 BAIXAR EXCEL", buffer.getvalue(), "Relatorio_Producao.xlsx", type="primary")
