import streamlit as st
import pandas as pd
import io
import os

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner Produção", layout="wide")

# CSS para focar no fluxo
st.markdown("""
<style>
    /* Destaque para o Scanner */
    div[data-testid="stTextInput"] label {
        font-size: 1.4rem;
        font-weight: bold;
        color: #2563eb; 
    }
    /* Modal mais limpo */
    div[data-testid="stDialog"] {
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES AUXILIARES ---
def formatar_br(valor):
    try:
        if pd.isna(valor) or valor == "": return "0,000"
        val = float(valor)
        return f"{val:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

@st.cache_data
def carregar_sap(caminho_ou_arquivo):
    try:
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

# --- ESTADO E CARREGAMENTO ---
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

# Variáveis do Wizard (Passo a Passo)
if 'wizard_data' not in st.session_state:
    st.session_state.wizard_data = {} # Guarda dados temporários do item sendo criado
if 'wizard_step' not in st.session_state:
    st.session_state.wizard_step = 0 # 0=Fechado, 1=Reserva, 2=Qtd, 3=Peso, 4=Comp

# Carrega Base
pasta_script = os.path.dirname(os.path.abspath(__file__))
caminho_fixo = os.path.join(pasta_script, "base_sap.xlsx")
df_sap = None

if os.path.exists(caminho_fixo):
    df_sap = carregar_sap(caminho_fixo)

st.title("🏭 Scanner de Produção")

if df_sap is None:
    st.warning("⚠️ Base SAP não encontrada. Faça upload:")
    arquivo_upload = st.file_uploader("Upload Base SAP", type=['xlsx', 'csv'])
    if arquivo_upload:
        df_sap = carregar_sap(arquivo_upload)
    else:
        st.stop()

# --- JANELA MODAL (O WIZARD) ---
@st.dialog("Entrada de Dados do Item")
def wizard_item():
    st.write(f"**Item:** {st.session_state.wizard_data.get('Cód. SAP')} - {st.session_state.wizard_data.get('Descrição')}")
    st.markdown("---")
    
    # PASSO 1: RESERVA
    if st.session_state.wizard_step == 1:
        reserva = st.text_input("1. Nº da Reserva (Caneta):", key="wiz_reserva", value="")
        if st.button("Próximo >>") or reserva: # O 'or reserva' pega o Enter se configurado no form
            st.session_state.wizard_data['Reserva'] = reserva
            st.session_state.wizard_step = 2
            st.rerun()

    # PASSO 2: QUANTIDADE
    elif st.session_state.wizard_step == 2:
        qtd = st.number_input("2. Quantidade de Peças:", min_value=1, step=1, value=1, key="wiz_qtd")
        if st.button("Próximo >>"):
            st.session_state.wizard_data['Qtd'] = qtd
            st.session_state.wizard_step = 3
            st.rerun()

    # PASSO 3: PESO
    elif st.session_state.wizard_step == 3:
        peso = st.number_input("3. Peso Real (kg):", min_value=0.000, step=0.001, format="%.3f", key="wiz_peso")
        if st.button("Próximo >>"):
            st.session_state.wizard_data['Peso Balança (kg)'] = peso
            st.session_state.wizard_step = 4
            st.rerun()

    # PASSO 4: COMPRIMENTO
    elif st.session_state.wizard_step == 4:
        comp = st.number_input("4. Comprimento (mm):", min_value=0, step=1, key="wiz_comp")
        if st.button("🏁 FINALIZAR ITEM"):
            st.session_state.wizard_data['Tamanho (mm)'] = comp
            
            # Salva na lista principal
            st.session_state.lista_itens.insert(0, st.session_state.wizard_data)
            
            # Reseta tudo
            st.session_state.wizard_data = {}
            st.session_state.wizard_step = 0
            st.session_state.input_scanner = "" # Limpa scanner
            st.rerun()

# --- LÓGICA DO SCANNER ---
def iniciar_bipagem():
    codigo = st.session_state.input_scanner
    if codigo:
        try:
            cod_limpo = str(codigo).strip()
            if ":" in cod_limpo: cod_limpo = cod_limpo.split(":")[-1]
            cod_int = int(cod_limpo)
            
            produto = df_sap[df_sap['Produto'] == cod_int]
            
            if not produto.empty:
                # Inicia o Wizard com os dados básicos
                st.session_state.wizard_data = {
                    "Cód. SAP": cod_int,
                    "Descrição": produto.iloc[0]['Descrição do produto'],
                    "Peso/m": produto.iloc[0]['Peso por Metro']
                }
                st.session_state.wizard_step = 1 # Vai para o passo 1 (Reserva)
                # Não limpamos o input_scanner ainda para não perder o foco, limpamos no final do wizard
            else:
                st.toast(f"Código {cod_int} não encontrado!", icon="🚫")
                st.session_state.input_scanner = ""
        except:
            st.toast("Erro no código.", icon="❌")
            st.session_state.input_scanner = ""

# Se o Wizard estiver ativo (step > 0), chama a função para abrir o modal
if st.session_state.wizard_step > 0:
    wizard_item()

# CAMPO DE SCANNER (Sempre visível no fundo)
st.text_input("BIPAR CÓDIGO DO MATERIAL:", key="input_scanner", on_change=iniciar_bipagem)

if st.button("🗑️ Limpar Lista"):
    st.session_state.lista_itens = []
    st.rerun()

st.markdown("---")

# --- TABELA FINAL (Acumulativa) ---
if st.session_state.lista_itens:
    st.markdown("### Itens Registrados")
    
    df_atual = pd.DataFrame(st.session_state.lista_itens)
    
    # Ainda permite edição se errou algo no Wizard
    df_editado = st.data_editor(
        df_atual,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Reserva": st.column_config.TextColumn("Reserva"),
            "Cód. SAP": st.column_config.NumberColumn(format="%d", disabled=True),
            "Descrição": st.column_config.TextColumn(disabled=True),
            "Qtd": st.column_config.NumberColumn(format="%d"),
            "Peso Balança (kg)": st.column_config.NumberColumn(format="%.3f"),
            "Tamanho (mm)": st.column_config.NumberColumn(format="%d"),
            "Peso/m": st.column_config.NumberColumn(disabled=True)
        },
        key="tabela_final"
    )

    # Persistência
    if not df_editado.equals(df_atual):
        st.session_state.lista_itens = df_editado.to_dict('records')

    # Cálculos e Totais
    if not df_editado.empty:
        df_final = df_editado.copy()
        for c in ['Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 'Peso/m']:
            df_final[c] = pd.to_numeric(df_final[c], errors='coerce').fillna(0)

        df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(regra_corte)
        df_final['Peso Teórico'] = (df_final['Nova Dimensão (mm)']/1000) * df_final['Peso/m'] * df_final['Qtd']
        df_final['Sucata'] = df_final['Peso Balança (kg)'] - df_final['Peso Teórico']

        c1, c2, c3 = st.columns(3)
        c1.metric("Itens", len(df_final))
        c2.metric("Peso Total", formatar_br(df_final['Peso Balança (kg)'].sum()) + " kg")
        c3.metric("Sucata Total", formatar_br(df_final['Sucata'].sum()) + " kg")

        # Exportação
        colunas_finais = ['Reserva', 'Cód. SAP', 'Descrição', 'Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 'Nova Dimensão (mm)', 'Peso Teórico', 'Sucata']
        # (Garante colunas faltantes se for o primeiro item)
        for c in colunas_finais: 
            if c not in df_final.columns: df_final[c] = ""
            
        df_export = df_final[colunas_finais].copy()
        for c in ['Peso Balança (kg)', 'Peso Teórico', 'Sucata']:
            if c in df_export.columns: df_export[c] = df_export[c].apply(formatar_br)
            
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False)
        st.download_button("📥 BAIXAR EXCEL", buffer.getvalue(), "Relatorio.xlsx", type="primary")
