import streamlit as st
import pandas as pd
import io
import os

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner Devolução", layout="wide")

# CSS para focar no campo de bipagem e limpar o visual
st.markdown("""
<style>
    .stApp {background-color: #f1f5f9;}
    .stButton>button {height: 3rem; font-weight: bold; border: 1px solid #cbd5e1;}
    /* Destaque para o campo de Input do Scanner */
    div[data-testid="stTextInput"] input {
        font-size: 20px; 
        background-color: #e0f2fe; 
        border: 2px solid #0284c7;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES ---

def formatar_br(valor):
    """Formata com 3 casas decimais e padrão BR (1.234,567)"""
    try:
        if pd.isna(valor) or valor == "": return "0,000"
        val = float(valor)
        return f"{val:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

@st.cache_data
def carregar_sap_fixo_ou_upload(uploaded_file=None):
    """Tenta carregar arquivo local 'base_sap.xlsx' ou o upload do usuário"""
    df = None
    
    # 1. Prioridade: Upload do usuário
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                try: df = pd.read_csv(uploaded_file, sep=';', decimal=',')
                except: df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
        except: return None

    # 2. Se não tem upload, tenta arquivo local
    elif os.path.exists("base_sap.xlsx"):
        try: df = pd.read_excel("base_sap.xlsx")
        except: return None
    
    # Processamento padrão
    if df is not None:
        df.columns = df.columns.str.strip()
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        
        if df['Peso por Metro'].dtype == 'object':
             df['Peso por Metro'] = df['Peso por Metro'].str.replace('.', '').str.replace(',', '.').astype(float)
        
        return df[['Produto', 'Descrição do produto', 'Peso por Metro']]
    
    return None

def regra_corte(mm):
    try: return (int(float(mm)) // 500) * 500
    except: return 0

# --- 3. ESTADO DA SESSÃO (Memória do App) ---
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

if 'ultimo_codigo' not in st.session_state:
    st.session_state.ultimo_codigo = ""

# --- 4. BARRA LATERAL (Status da Base) ---
with st.sidebar:
    st.header("⚙️ Configuração")
    
    # Tenta carregar automático
    df_sap = carregar_sap_fixo_ou_upload()
    
    # Se não achou local, pede upload
    if df_sap is None:
        st.warning("Arquivo 'base_sap.xlsx' não encontrado na pasta.")
        arquivo_upload = st.file_uploader("Carregar Base SAP Manualmente", type=['xlsx', 'csv'])
        if arquivo_upload:
            df_sap = carregar_sap_fixo_ou_upload(arquivo_upload)
    else:
        st.success("✅ Base SAP Automática Carregada!")
        
    if st.button("🗑️ Limpar Lista de Itens"):
        st.session_state.lista_itens = []
        st.rerun()

# --- 5. LÓGICA DO SCANNER (Callback) ---
def adicionar_item():
    """Chamado automaticamente quando o leitor dá 'Enter'"""
    codigo_lido = st.session_state.input_scanner
    
    if codigo_lido and df_sap is not None:
        # Limpeza básica do código (remove espaços)
        try:
            cod_int = int(str(codigo_lido).strip())
        except:
            st.toast(f"❌ Código inválido: {codigo_lido}", icon="⚠️")
            st.session_state.input_scanner = ""
            return

        # Busca no SAP
        produto = df_sap[df_sap['Produto'] == cod_int]
        
        if not produto.empty:
            descricao = produto.iloc[0]['Descrição do produto']
            peso_metro = produto.iloc[0]['Peso por Metro']
            
            # Adiciona na lista (Topo da lista para ver o último lido)
            novo_item = {
                "Cód. SAP": cod_int,
                "Descrição": descricao,
                "Qtd": 1, # Padrão 1
                "Peso Balança (kg)": 0.000, # Usuário preenche depois ou agora
                "Tamanho (mm)": 0, # Usuário preenche
                "Peso por Metro": peso_metro
            }
            # Insere no começo da lista
            st.session_state.lista_itens.insert(0, novo_item)
            st.toast(f"✅ Item Adicionado: {descricao}", icon="📦")
        else:
            st.toast(f"⚠️ Material {cod_int} não encontrado no SAP", icon="🚫")
    
    # Limpa o campo para o próximo bip
    st.session_state.input_scanner = ""

# --- 6. TELA PRINCIPAL ---
st.title("🏭 Scanner de Devolução")

if df_sap is None:
    st.error("Por favor, coloque o arquivo 'base_sap.xlsx' na pasta ou faça upload.")
    st.stop()

# CAMPO DE BIPAGEM (Foco do Leitor)
st.text_input(
    "🔫 Bipar Código Aqui (QR Code/Barras):", 
    key="input_scanner", 
    on_change=adicionar_item,
    help="O leitor deve estar configurado para dar ENTER após a leitura."
)

st.markdown("---")

# --- 7. TABELA DE ITENS (Editável) ---
if st.session_state.lista_itens:
    df_atual = pd.DataFrame(st.session_state.lista_itens)
    
    st.info("👇 Ajuste a Quantidade, Peso e Tamanho na tabela abaixo:")
    
    # Editor de Dados
    df_editado = st.data_editor(
        df_atual,
        num_rows="dynamic", # Permite adicionar/remover manual também
        use_container_width=True,
        column_config={
            "Cód. SAP": st.column_config.NumberColumn("Cód. SAP", format="%d", disabled=True), # Bloqueia edição do código
            "Descrição": st.column_config.TextColumn("Descrição", disabled=True),
            "Qtd": st.column_config.NumberColumn("Qtd", min_value=1, step=1),
            # 3 Casas decimais aqui!
            "Peso Balança (kg)": st.column_config.NumberColumn("Peso Real (kg)", min_value=0.0, format="%.3f"),
            "Tamanho (mm)": st.column_config.NumberColumn("Tamanho (mm)", min_value=0, step=1),
            "Peso por Metro": st.column_config.NumberColumn("Peso/m", format="%.3f", disabled=True)
        },
        key="editor_lista"
    )

    # --- 8. CÁLCULOS E RELATÓRIO ---
    if not df_editado.empty:
        # Atualiza a memória com as edições do usuário
        # st.session_state.lista_itens = df_editado.to_dict('records') # Opcional: manter sincrono

        # Cálculos Finais
        df_final = df_editado.copy()
        
        # Garante tipos
        df_final['Tamanho (mm)'] = pd.to_numeric(df_final['Tamanho (mm)'], errors='coerce').fillna(0)
        df_final['Peso Balança (kg)'] = pd.to_numeric(df_final['Peso Balança (kg)'], errors='coerce').fillna(0.0)
        df_final['Qtd'] = pd.to_numeric(df_final['Qtd'], errors='coerce').fillna(0)

        df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(regra_corte)
        
        df_final['Peso Teórico (Calc)'] = (
            (df_final['Nova Dimensão (mm)'] / 1000.0) * df_final['Peso por Metro'] * df_final['Qtd']
        )
        
        df_final['Sucata (Dif)'] = df_final['Peso Balança (kg)'] - df_final['Peso Teórico (Calc)']

        # Totais
        st.markdown("### Resumo do Lote")
        c1, c2, c3 = st.columns(3)
        c1.metric("Itens", len(df_final))
        c2.metric("Peso Real Total", formatar_br(df_final['Peso Balança (kg)'].sum()) + " kg")
        c3.metric("Sucata Total", formatar_br(df_final['Sucata (Dif)'].sum()) + " kg")

        # Exportação
        colunas_export = [
            'Cód. SAP', 'Descrição', 'Qtd', 'Peso Balança (kg)', 
            'Tamanho (mm)', 'Nova Dimensão (mm)', 'Peso Teórico (Calc)', 'Sucata (Dif)'
        ]
        df_export = df_final[colunas_export].copy()
        
        # Formata para texto BR no Excel
        cols_fmt = ['Peso Balança (kg)', 'Peso Teórico (Calc)', 'Sucata (Dif)']
        for c in cols_fmt:
            df_export[c] = df_export[c].apply(formatar_br)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False)
            
        st.download_button(
            label="📥 BAIXAR RELATÓRIO FINAL",
            data=buffer.getvalue(),
            file_name="Relatorio_Scanner.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
else:
    st.info("Aguardando leitura de códigos...")
