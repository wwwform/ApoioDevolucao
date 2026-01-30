import streamlit as st
import pandas as pd
import io
import os
import sqlite3
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema Integrado Produção", layout="wide")

st.markdown("""
<style>
    div[data-testid="stTextInput"] label {
        font-size: 1.4rem;
        font-weight: bold;
        color: #3b82f6; 
    }
    .stButton>button {
        height: 3rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. BANCO DE DADOS (Atualizado com colunas extras) ---
def init_db():
    conn = sqlite3.connect('dados_fabrica_v2.db', check_same_thread=False)
    c = conn.cursor()
    # Adicionei 'nova_dimensao_mm' explicitamente
    c.execute('''
        CREATE TABLE IF NOT EXISTS producao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            reserva TEXT,
            cod_sap INTEGER,
            descricao TEXT,
            qtd INTEGER,
            peso_real REAL,
            tamanho_real_mm INTEGER,
            tamanho_corte_mm INTEGER,
            peso_teorico REAL,
            sucata REAL
        )
    ''')
    conn.commit()
    conn.close()

def salvar_no_banco(dados):
    conn = sqlite3.connect('dados_fabrica_v2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        INSERT INTO producao (data_hora, reserva, cod_sap, descricao, qtd, peso_real, tamanho_real_mm, tamanho_corte_mm, peso_teorico, sucata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        dados['Reserva'],
        dados['Cód. SAP'],
        dados['Descrição'],
        dados['Qtd'],
        dados['Peso Balança (kg)'],
        dados['Tamanho Real (mm)'],
        dados['Tamanho Corte (mm)'], # Salva o valor já arredondado
        dados['Peso Teórico'],
        dados['Sucata']
    ))
    conn.commit()
    conn.close()

def ler_banco():
    conn = sqlite3.connect('dados_fabrica_v2.db', check_same_thread=False)
    df = pd.read_sql_query("SELECT * FROM producao ORDER BY id DESC", conn)
    conn.close()
    return df

def limpar_banco():
    conn = sqlite3.connect('dados_fabrica_v2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("DELETE FROM producao")
    conn.commit()
    conn.close()

init_db()

# --- 2. FUNÇÕES AUXILIARES ---
def formatar_br(valor):
    try:
        if pd.isna(valor) or valor == "": return "0,000"
        val = float(valor)
        return f"{val:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

def regra_corte(mm):
    """Aplica regra de múltiplos de 500mm para baixo"""
    try:
        valor = int(float(mm))
        # Ex: 1255 // 500 = 2 -> 2 * 500 = 1000
        return (valor // 500) * 500
    except: return 0

@st.cache_data
def carregar_base_sap():
    pasta_script = os.path.dirname(os.path.abspath(__file__))
    caminho_fixo = os.path.join(pasta_script, "base_sap.xlsx")
    
    if os.path.exists(caminho_fixo):
        try:
            df = pd.read_excel(caminho_fixo)
            df.columns = df.columns.str.strip()
            df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
            if df['Peso por Metro'].dtype == 'object':
                 df['Peso por Metro'] = df['Peso por Metro'].str.replace(',', '.').astype(float)
            return df
        except: return None
    return None

# --- 3. CONTROLE DE ACESSO ---
st.sidebar.title("🔐 Acesso")
modo_acesso = st.sidebar.radio("Selecione o Perfil:", ["Operador (Chão de Fábrica)", "Administrador (Escritório)"])

df_sap = carregar_base_sap()
if df_sap is None:
    st.error("ERRO: `base_sap.xlsx` não encontrado.")
    st.stop()

# ==============================================================================
# TELA 1: OPERADOR
# ==============================================================================
if modo_acesso == "Operador (Chão de Fábrica)":
    st.title("🏭 Operador: Bipagem")

    if 'wizard_data' not in st.session_state: st.session_state.wizard_data = {}
    if 'wizard_step' not in st.session_state: st.session_state.wizard_step = 0

    @st.dialog("📦 Entrada de Material")
    def wizard_item():
        st.write(f"**Item:** {st.session_state.wizard_data.get('Cód. SAP')} - {st.session_state.wizard_data.get('Descrição')}")
        
        if st.session_state.wizard_step == 1:
            reserva = st.text_input("1. Nº da Reserva:", key="wiz_reserva")
            if st.button("Próximo") or reserva:
                st.session_state.wizard_data['Reserva'] = reserva
                st.session_state.wizard_step = 2
                st.rerun()

        elif st.session_state.wizard_step == 2:
            qtd = st.number_input("2. Quantidade:", min_value=1, step=1, value=1, key="wiz_qtd")
            if st.button("Próximo"):
                st.session_state.wizard_data['Qtd'] = qtd
                st.session_state.wizard_step = 3
                st.rerun()

        elif st.session_state.wizard_step == 3:
            peso = st.number_input("3. Peso (kg):", min_value=0.000, step=0.001, format="%.3f", key="wiz_peso")
            if st.button("Próximo"):
                st.session_state.wizard_data['Peso Balança (kg)'] = peso
                st.session_state.wizard_step = 4
                st.rerun()

        elif st.session_state.wizard_step == 4:
            comp = st.number_input("4. Comprimento Real (mm):", min_value=0, step=1, key="wiz_comp")
            
            # Mostra prévia do cálculo para o operador conferir
            if comp > 0:
                novo_corte = regra_corte(comp)
                st.caption(f"ℹ️ O sistema considerará: **{novo_corte} mm** (Múltiplo de 500)")
            
            if st.button("✅ SALVAR E ENVIAR"):
                peso_metro = st.session_state.wizard_data['Peso/m']
                qtd_f = st.session_state.wizard_data['Qtd']
                tamanho_real = comp
                peso_balanca_f = st.session_state.wizard_data['Peso Balança (kg)']
                
                # CÁLCULOS CORRIGIDOS
                tamanho_corte = regra_corte(tamanho_real) # Aplica a regra
                
                # Peso Teórico = (Tamanho Corte / 1000) * Peso Metro * Qtd
                peso_teorico = (tamanho_corte / 1000.0) * peso_metro * qtd_f
                
                # Sucata = Peso Real - Peso Teórico do Aproveitamento
                sucata = peso_balanca_f - peso_teorico
                
                item_final = {
                    "Reserva": st.session_state.wizard_data['Reserva'],
                    "Cód. SAP": st.session_state.wizard_data['Cód. SAP'],
                    "Descrição": st.session_state.wizard_data['Descrição'],
                    "Qtd": qtd_f,
                    "Peso Balança (kg)": peso_balanca_f,
                    "Tamanho Real (mm)": tamanho_real,   # O que ele digitou
                    "Tamanho Corte (mm)": tamanho_corte, # O calculado (500mm)
                    "Peso Teórico": peso_teorico,
                    "Sucata": sucata
                }
                salvar_no_banco(item_final)
                st.toast(f"Salvo! Corte considerado: {tamanho_corte}mm", icon="✂️")
                st.session_state.wizard_data = {}
                st.session_state.wizard_step = 0
                st.session_state.input_scanner = ""
                st.rerun()

    def iniciar_bipagem():
        codigo = st.session_state.input_scanner
        if codigo:
            try:
                cod_limpo = str(codigo).strip().split(":")[-1]
                cod_int = int(cod_limpo)
                produto = df_sap[df_sap['Produto'] == cod_int]
                if not produto.empty:
                    st.session_state.wizard_data = {
                        "Cód. SAP": cod_int,
                        "Descrição": produto.iloc[0]['Descrição do produto'],
                        "Peso/m": produto.iloc[0]['Peso por Metro']
                    }
                    st.session_state.wizard_step = 1
                else:
                    st.toast("Material não encontrado!", icon="🚫")
                    st.session_state.input_scanner = ""
            except:
                st.session_state.input_scanner = ""

    if st.session_state.wizard_step > 0:
        wizard_item()

    st.text_input("BIPAR CÓDIGO:", key="input_scanner", on_change=iniciar_bipagem)

# ==============================================================================
# TELA 2: ADMINISTRADOR
# ==============================================================================
elif modo_acesso == "Administrador (Escritório)":
    st.title("💻 Admin: Controle de Produção")
    SENHA_CORRETA = "Br@met4l"

    senha_digitada = st.sidebar.text_input("Senha Admin", type="password")
    
    if senha_digitada == SENHA_CORRETA:
        st.sidebar.success("Acesso Liberado")
        
        if st.button("🔄 Atualizar Tabela"):
            st.rerun()
            
        df_banco = ler_banco()
        
        if not df_banco.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Itens", len(df_banco))
            c2.metric("Peso Total", formatar_br(df_banco['peso_real'].sum()) + " kg")
            c3.metric("Sucata Total", formatar_br(df_banco['sucata'].sum()) + " kg")
            
            # Mostra Tabela com as NOVAS colunas
            # Renomeando para ficar bonito na tela
            df_view = df_banco.rename(columns={
                'tamanho_real_mm': 'Comp. Real (mm)',
                'tamanho_corte_mm': 'Comp. Corte (500mm)',
                'peso_real': 'Peso Balança',
                'peso_teorico': 'Peso Teórico',
                'sucata': 'Sucata'
            })
            
            st.dataframe(df_view, use_container_width=True)
            
            # Exportação Excel Completa
            df_export = df_banco.copy()
            df_export.rename(columns={
                'tamanho_real_mm': 'Comprimento Real (mm)',
                'tamanho_corte_mm': 'Comprimento Considerado (mm)'
            }, inplace=True)
            
            for col in ['peso_real', 'peso_teorico', 'sucata']:
                df_export[col] = df_export[col].apply(formatar_br)
                
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False)
                
            col_d, col_l = st.columns([2,1])
            col_d.download_button("📥 Baixar Relatório Detalhado", buffer.getvalue(), "Relatorio_Producao.xlsx", type="primary")
            
            if col_l.button("🗑️ Limpar Banco", type="secondary"):
                limpar_banco()
                st.success("Limpo!")
                st.rerun()
        else:
            st.info("Nenhum dado recebido.")
    elif senha_digitada:
        st.sidebar.error("Senha Incorreta")
