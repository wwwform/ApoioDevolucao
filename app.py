import streamlit as st
import pandas as pd
import io
import os
import sqlite3
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema Integrado Produção", layout="wide")

# CSS (Respeitando o tema escuro, apenas destacando o necessário)
st.markdown("""
<style>
    /* Destaque para o Scanner */
    div[data-testid="stTextInput"] label {
        font-size: 1.4rem;
        font-weight: bold;
        color: #3b82f6; 
    }
    /* Botões grandes */
    .stButton>button {
        height: 3rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. BANCO DE DADOS (SQLite) ---
def init_db():
    """Cria a tabela se não existir"""
    conn = sqlite3.connect('dados_fabrica.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS producao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            reserva TEXT,
            cod_sap INTEGER,
            descricao TEXT,
            qtd INTEGER,
            peso_real REAL,
            tamanho_mm INTEGER,
            peso_teorico REAL,
            sucata REAL
        )
    ''')
    conn.commit()
    conn.close()

def salvar_no_banco(dados):
    """Insere um item no banco"""
    conn = sqlite3.connect('dados_fabrica.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        INSERT INTO producao (data_hora, reserva, cod_sap, descricao, qtd, peso_real, tamanho_mm, peso_teorico, sucata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        dados['Reserva'],
        dados['Cód. SAP'],
        dados['Descrição'],
        dados['Qtd'],
        dados['Peso Balança (kg)'],
        dados['Tamanho (mm)'],
        dados['Peso Teórico'],
        dados['Sucata']
    ))
    conn.commit()
    conn.close()

def ler_banco():
    """Lê todos os dados para o Admin"""
    conn = sqlite3.connect('dados_fabrica.db', check_same_thread=False)
    df = pd.read_sql_query("SELECT * FROM producao ORDER BY id DESC", conn)
    conn.close()
    return df

def limpar_banco():
    """Admin zera a produção"""
    conn = sqlite3.connect('dados_fabrica.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("DELETE FROM producao")
    conn.commit()
    conn.close()

# Inicializa o banco ao abrir
init_db()

# --- 2. FUNÇÕES AUXILIARES ---
def formatar_br(valor):
    try:
        if pd.isna(valor) or valor == "": return "0,000"
        val = float(valor)
        return f"{val:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

def regra_corte(mm):
    try: return (int(float(mm)) // 500) * 500
    except: return 0

@st.cache_data
def carregar_base_sap():
    # Tenta carregar do GitHub/Pasta Local
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

# --- 3. CONTROLE DE ACESSO (SIDEBAR) ---
st.sidebar.title("🔐 Acesso")
modo_acesso = st.sidebar.radio("Selecione o Perfil:", ["Operador (Chão de Fábrica)", "Administrador (Escritório)"])

# --- CARREGA BASE SAP ---
df_sap = carregar_base_sap()
if df_sap is None:
    st.error("ERRO: `base_sap.xlsx` não encontrado. Faça upload no GitHub.")
    st.stop()

# ==============================================================================
# TELA 1: OPERADOR (BIPA E ENVIA)
# ==============================================================================
if modo_acesso == "Operador (Chão de Fábrica)":
    st.title("🏭 Operador: Bipagem")

    # Estados do Wizard
    if 'wizard_data' not in st.session_state: st.session_state.wizard_data = {}
    if 'wizard_step' not in st.session_state: st.session_state.wizard_step = 0

    # --- WIZARD MODAL ---
    @st.dialog("📦 Entrada de Material")
    def wizard_item():
        st.write(f"**Item:** {st.session_state.wizard_data.get('Cód. SAP')} - {st.session_state.wizard_data.get('Descrição')}")
        
        # PASSO 1: RESERVA
        if st.session_state.wizard_step == 1:
            reserva = st.text_input("1. Nº da Reserva:", key="wiz_reserva")
            if st.button("Próximo") or reserva:
                st.session_state.wizard_data['Reserva'] = reserva
                st.session_state.wizard_step = 2
                st.rerun()

        # PASSO 2: QUANTIDADE
        elif st.session_state.wizard_step == 2:
            qtd = st.number_input("2. Quantidade:", min_value=1, step=1, value=1, key="wiz_qtd")
            if st.button("Próximo"):
                st.session_state.wizard_data['Qtd'] = qtd
                st.session_state.wizard_step = 3
                st.rerun()

        # PASSO 3: PESO
        elif st.session_state.wizard_step == 3:
            peso = st.number_input("3. Peso (kg):", min_value=0.000, step=0.001, format="%.3f", key="wiz_peso")
            if st.button("Próximo"):
                st.session_state.wizard_data['Peso Balança (kg)'] = peso
                st.session_state.wizard_step = 4
                st.rerun()

        # PASSO 4: COMPRIMENTO & SALVAR
        elif st.session_state.wizard_step == 4:
            comp = st.number_input("4. Comprimento (mm):", min_value=0, step=1, key="wiz_comp")
            
            if st.button("✅ SALVAR E ENVIAR"):
                # Cálculos Finais Antes de Salvar
                peso_metro = st.session_state.wizard_data['Peso/m']
                qtd_f = st.session_state.wizard_data['Qtd']
                tamanho_f = comp
                peso_balanca_f = st.session_state.wizard_data['Peso Balança (kg)']
                
                nova_dimensao = regra_corte(tamanho_f)
                peso_teorico = (nova_dimensao / 1000.0) * peso_metro * qtd_f
                sucata = peso_balanca_f - peso_teorico
                
                # Monta objeto final
                item_final = {
                    "Reserva": st.session_state.wizard_data['Reserva'],
                    "Cód. SAP": st.session_state.wizard_data['Cód. SAP'],
                    "Descrição": st.session_state.wizard_data['Descrição'],
                    "Qtd": qtd_f,
                    "Peso Balança (kg)": peso_balanca_f,
                    "Tamanho (mm)": tamanho_f,
                    "Peso Teórico": peso_teorico,
                    "Sucata": sucata
                }
                
                # SALVA NO BANCO DE DADOS
                salvar_no_banco(item_final)
                
                st.toast("Dados enviados para o escritório!", icon="🚀")
                
                # Reseta
                st.session_state.wizard_data = {}
                st.session_state.wizard_step = 0
                st.session_state.input_scanner = ""
                st.rerun()

    # --- INPUT SCANNER ---
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
    
    # Feedback visual
    st.info("ℹ️ Ao finalizar o preenchimento, os dados são enviados automaticamente para a tela do Admin.")

# ==============================================================================
# TELA 2: ADMINISTRADOR (VISUALIZA E BAIXA)
# ==============================================================================
elif modo_acesso == "Administrador (Escritório)":
    st.title("💻 Admin: Controle de Produção")
    
    # Login Simples
    senha = st.sidebar.text_input("Senha Admin", type="password")
    if senha == "admin123": # Senha fixa simples
        
        if st.button("🔄 Atualizar Tabela"):
            st.rerun()
            
        df_banco = ler_banco()
        
        if not df_banco.empty:
            # Métricas
            c1, c2, c3 = st.columns(3)
            c1.metric("Itens Registrados", len(df_banco))
            c2.metric("Peso Total", formatar_br(df_banco['peso_real'].sum()) + " kg")
            c3.metric("Sucata Total", formatar_br(df_banco['sucata'].sum()) + " kg")
            
            # Mostra Tabela
            st.dataframe(df_banco, use_container_width=True)
            
            # Exportação
            df_export = df_banco.copy()
            # Formata colunas para Excel BR
            for col in ['peso_real', 'peso_teorico', 'sucata']:
                df_export[col] = df_export[col].apply(formatar_br)
                
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False)
                
            col_d, col_l = st.columns([2,1])
            col_d.download_button("📥 Baixar Excel Geral", buffer.getvalue(), "Relatorio_Geral.xlsx", type="primary")
            
            if col_l.button("🗑️ Limpar Banco de Dados", type="secondary"):
                limpar_banco()
                st.success("Banco limpo!")
                st.rerun()
        else:
            st.info("Nenhum dado recebido do operador ainda.")
            
    else:
        st.warning("Digite a senha para acessar os dados (Senha: admin123)")
