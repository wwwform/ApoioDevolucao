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
    div[data-testid="stTextInput"] label, div[data-testid="stNumberInput"] label {
        font-size: 1.5rem !important;
        font-weight: bold;
        color: #2563eb; 
    }
    .stButton>button {
        height: 3.5rem;
        font-size: 1.2rem !important;
        font-weight: bold;
    }
    .stInfo {
        font-size: 1.2rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. BANCO DE DADOS (AGORA COM TABELA DE SEQUÊNCIA) ---
def init_db():
    conn = sqlite3.connect('dados_fabrica_v4.db', check_same_thread=False)
    c = conn.cursor()
    
    # Tabela de Produção (Pode ser limpa)
    c.execute('''
        CREATE TABLE IF NOT EXISTS producao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            lote TEXT,
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
    
    # Tabela de Sequência (NUNCA É LIMPA PELO ADMIN)
    # Guarda: cod_sap | ultimo_numero_usado
    c.execute('''
        CREATE TABLE IF NOT EXISTS sequencia_lotes (
            cod_sap INTEGER PRIMARY KEY,
            ultimo_numero INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()

def obter_e_incrementar_lote(cod_sap, apenas_visualizar=False):
    """
    Se apenas_visualizar=True: Mostra qual seria o próximo (sem gastar o número).
    Se apenas_visualizar=False: Gera o próximo, GRAVA no banco que foi usado e retorna.
    """
    conn = sqlite3.connect('dados_fabrica_v4.db', check_same_thread=False)
    c = conn.cursor()
    
    # Verifica qual o último número usado para este material
    c.execute("SELECT ultimo_numero FROM sequencia_lotes WHERE cod_sap = ?", (cod_sap,))
    resultado = c.fetchone()
    
    if resultado:
        ultimo = resultado[0]
        proximo = ultimo + 1
    else:
        # Primeira vez desse material na história
        ultimo = 0
        proximo = 1
    
    prefixo = "BRASA"
    lote_formatado = f"{prefixo}{proximo:05d}"
    
    if not apenas_visualizar:
        # Atualiza ou Insere o novo "Placar"
        c.execute('''
            INSERT INTO sequencia_lotes (cod_sap, ultimo_numero) 
            VALUES (?, ?) 
            ON CONFLICT(cod_sap) DO UPDATE SET ultimo_numero = ?
        ''', (cod_sap, proximo, proximo))
        conn.commit()
    
    conn.close()
    return lote_formatado

def salvar_no_banco(dados):
    # 1. Gera o Lote Oficial (Queima o número na sequência)
    lote_oficial = obter_e_incrementar_lote(dados['Cód. SAP'], apenas_visualizar=False)
    
    # 2. Salva na Produção
    conn = sqlite3.connect('dados_fabrica_v4.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        INSERT INTO producao (data_hora, lote, reserva, cod_sap, descricao, qtd, peso_real, tamanho_real_mm, tamanho_corte_mm, peso_teorico, sucata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        lote_oficial,
        dados['Reserva'],
        dados['Cód. SAP'],
        dados['Descrição'],
        dados['Qtd'],
        dados['Peso Balança (kg)'],
        dados['Tamanho Real (mm)'],
        dados['Tamanho Corte (mm)'],
        dados['Peso Teórico'],
        dados['Sucata']
    ))
    conn.commit()
    conn.close()
    return lote_oficial

def ler_banco():
    conn = sqlite3.connect('dados_fabrica_v4.db', check_same_thread=False)
    df = pd.read_sql_query("SELECT * FROM producao ORDER BY id DESC", conn)
    conn.close()
    return df

def limpar_banco():
    """
    Limpa APENAS a tabela de produção (relatório), 
    mas MANTÉM a tabela de sequência intacta.
    """
    conn = sqlite3.connect('dados_fabrica_v4.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("DELETE FROM producao") # Só apaga os registros de produção
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
    try:
        valor = int(float(mm))
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
# TELA 1: OPERADOR (Tablet)
# ==============================================================================
if modo_acesso == "Operador (Chão de Fábrica)":
    st.title("🏭 Operador: Bipagem")

    if 'wizard_data' not in st.session_state: st.session_state.wizard_data = {}
    if 'wizard_step' not in st.session_state: st.session_state.wizard_step = 0
    if 'item_id' not in st.session_state: st.session_state.item_id = 0 
    if 'proximo_lote_visual' not in st.session_state: st.session_state.proximo_lote_visual = ""

    @st.dialog("📦 Entrada de Material")
    def wizard_item():
        st.write(f"**Item:** {st.session_state.wizard_data.get('Cód. SAP')} - {st.session_state.wizard_data.get('Descrição')}")
        
        # Mostra qual SERÁ o lote (sem gastar o número ainda)
        st.info(f"🏷️ Próximo Lote Disponível: **{st.session_state.proximo_lote_visual}**")
        st.markdown("---")
        
        # --- PASSO 1: RESERVA ---
        if st.session_state.wizard_step == 1:
            with st.form("form_reserva"):
                reserva = st.text_input("1. Nº da Reserva:", key=f"res_{st.session_state.item_id}")
                st.write("")
                if st.form_submit_button("PRÓXIMO >>", use_container_width=True, type="primary"):
                    if reserva.strip():
                        st.session_state.wizard_data['Reserva'] = reserva
                        st.session_state.wizard_step = 2
                        st.rerun()
                    else:
                        st.error("⚠️ Digite a Reserva!")

        # --- PASSO 2: QUANTIDADE ---
        elif st.session_state.wizard_step == 2:
            with st.form("form_qtd"):
                qtd = st.number_input("2. Quantidade (Peças):", min_value=1, step=1, value=1, key=f"qtd_{st.session_state.item_id}")
                st.write("")
                if st.form_submit_button("PRÓXIMO >>", use_container_width=True, type="primary"):
                    st.session_state.wizard_data['Qtd'] = qtd
                    st.session_state.wizard_step = 3
                    st.rerun()

        # --- PASSO 3: PESO ---
        elif st.session_state.wizard_step == 3:
            with st.form("form_peso"):
                peso = st.number_input("3. Peso Real (kg):", min_value=0.000, step=0.001, format="%.3f", key=f"peso_{st.session_state.item_id}")
                st.write("")
                if st.form_submit_button("PRÓXIMO >>", use_container_width=True, type="primary"):
                    if peso > 0:
                        st.session_state.wizard_data['Peso Balança (kg)'] = peso
                        st.session_state.wizard_step = 4
                        st.rerun()
                    else:
                        st.error("⚠️ Peso não pode ser Zero!")

        # --- PASSO 4: COMPRIMENTO ---
        elif st.session_state.wizard_step == 4:
            with st.form("form_comp"):
                comp = st.number_input("4. Comprimento Real (mm):", min_value=0, step=1, key=f"comp_{st.session_state.item_id}")
                st.write("")
                
                if st.form_submit_button("✅ SALVAR E FINALIZAR", use_container_width=True, type="primary"):
                    if comp > 0:
                        # Processamento
                        peso_metro = st.session_state.wizard_data['Peso/m']
                        qtd_f = st.session_state.wizard_data['Qtd']
                        tamanho_real = comp
                        peso_balanca_f = st.session_state.wizard_data['Peso Balança (kg)']
                        
                        tamanho_corte = regra_corte(tamanho_real)
                        peso_teorico = (tamanho_corte / 1000.0) * peso_metro * qtd_f
                        sucata = peso_balanca_f - peso_teorico
                        
                        item_temp = {
                            "Reserva": st.session_state.wizard_data['Reserva'],
                            "Cód. SAP": st.session_state.wizard_data['Cód. SAP'],
                            "Descrição": st.session_state.wizard_data['Descrição'],
                            "Qtd": qtd_f,
                            "Peso Balança (kg)": peso_balanca_f,
                            "Tamanho Real (mm)": tamanho_real,
                            "Tamanho Corte (mm)": tamanho_corte,
                            "Peso Teórico": peso_teorico,
                            "Sucata": sucata
                        }
                        
                        # AQUI ACONTECE A MÁGICA: Gera o lote definitivo e salva
                        lote_gerado = salvar_no_banco(item_temp)
                        
                        st.toast(f"Salvo! Lote Confirmado: {lote_gerado}", icon="🏷️")
                        
                        st.session_state.wizard_data = {}
                        st.session_state.wizard_step = 0
                        st.session_state.input_scanner = ""
                        st.rerun()
                    else:
                        st.error("⚠️ Comprimento não pode ser Zero!")

    def iniciar_bipagem():
        codigo = st.session_state.input_scanner
        if codigo:
            try:
                cod_limpo = str(codigo).strip().split(":")[-1]
                cod_int = int(cod_limpo)
                produto = df_sap[df_sap['Produto'] == cod_int]
                if not produto.empty:
                    st.session_state.item_id += 1 
                    
                    # Previsão Visual (Sem consumir o número)
                    prev = obter_e_incrementar_lote(cod_int, apenas_visualizar=True)
                    st.session_state.proximo_lote_visual = prev
                    
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
    st.info("ℹ️ Sistema com contador de lote sequencial e indestrutível.")

# ==============================================================================
# TELA 2: ADMINISTRADOR
# ==============================================================================
elif modo_acesso == "Administrador (Escritório)":
    st.title("💻 Admin: Controle de Produção")
    SENHA_CORRETA = "Br@met4l"

    senha_digitada = st.sidebar.text_input("Senha Admin", type="password")
    
    if senha_digitada == SENHA_CORRETA:
        st.sidebar.success("Conectado")
        
        if st.button("🔄 Atualizar Tabela"):
            st.rerun()
            
        df_banco = ler_banco()
        
        if not df_banco.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Itens", len(df_banco))
            c2.metric("Peso Total", formatar_br(df_banco['peso_real'].sum()) + " kg")
            c3.metric("Sucata Total", formatar_br(df_banco['sucata'].sum()) + " kg")
            
            df_view = df_banco.rename(columns={
                'lote': 'Lote', 'reserva': 'Reserva', 'cod_sap': 'SAP', 'descricao': 'Descrição',
                'qtd': 'Qtd', 'tamanho_real_mm': 'Comp. Real', 
                'tamanho_corte_mm': 'Comp. Corte', 'peso_real': 'Peso',
                'sucata': 'Sucata'
            })
            st.dataframe(df_view[['Lote', 'Reserva', 'SAP', 'Descrição', 'Qtd', 'Peso', 'Comp. Real', 'Comp. Corte', 'Sucata']], use_container_width=True)
            
            df_export = df_banco.copy()
            df_export.rename(columns={
                'lote': 'Lote',
                'tamanho_real_mm': 'Comp. Real (mm)',
                'tamanho_corte_mm': 'Comp. Considerado (mm)'
            }, inplace=True)
            for col in ['peso_real', 'peso_teorico', 'sucata']:
                df_export[col] = df_export[col].apply(formatar_br)
                
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False)
            
            st.download_button("📥 Baixar Excel Completo", buffer.getvalue(), "Relatorio.xlsx", type="primary", use_container_width=True)
            
            st.markdown("---")
            st.caption("Atenção: Limpar o banco abaixo apaga os relatórios, mas NÃO reseta a contagem dos lotes (BRASAxxxxx).")
            if st.button("🗑️ Limpar Banco de Relatórios", type="secondary"):
                limpar_banco()
                st.success("Relatórios limpos! A sequência de lotes foi preservada.")
                st.rerun()
        else:
            st.info("Nenhum dado.")
    elif senha_digitada:
        st.sidebar.error("Senha Incorreta")
