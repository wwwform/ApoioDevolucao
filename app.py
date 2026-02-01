import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema Integrado Produção", layout="wide")

# --- CSS NUCLEAR ---
st.markdown("""
<style>
    header[data-testid="stHeader"] {visibility: hidden; display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden; display: none;}
    [data-testid="stDecoration"] {visibility: hidden; display: none;}
    .stDeployButton {display:none;}
    
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
    .block-container {
        padding-top: 1rem !important;
    }
</style>
""", unsafe_allow_html=True)

# --- CONEXÃO GOOGLE SHEETS ---
@st.cache_resource
def conectar_google():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    return client.open("BD_Fabrica_Geral")

def garantir_cabecalhos():
    try:
        sh = conectar_google()
        # Aba Produção
        ws_prod = sh.worksheet("Perfis_Producao")
        if not ws_prod.row_values(1):
            ws_prod.append_row([
                "id", "data_hora", "lote", "reserva", "status_reserva", 
                "cod_sap", "descricao", "qtd", "peso_real", 
                "tamanho_real_mm", "tamanho_corte_mm", "peso_teorico", "sucata"
            ])
        # Aba Lotes
        ws_lotes = sh.worksheet("Perfis_Lotes")
        if not ws_lotes.row_values(1):
            ws_lotes.append_row(["cod_sap", "ultimo_numero"])
    except Exception as e:
        st.error(f"Erro ao iniciar planilha: {e}")

# Garante cabeçalhos ao iniciar
garantir_cabecalhos()

# --- FUNÇÕES DE BANCO (ADAPTADAS PARA GOOGLE) ---
def ler_banco():
    sh = conectar_google()
    ws = sh.worksheet("Perfis_Producao")
    dados = ws.get_all_records()
    df = pd.DataFrame(dados)
    # Garante que colunas numéricas sejam números
    cols_num = ['id', 'cod_sap', 'qtd', 'peso_real', 'tamanho_real_mm', 'tamanho_corte_mm', 'peso_teorico', 'sucata']
    for c in cols_num:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return df.sort_values(by='id', ascending=False)

def obter_e_incrementar_lote(cod_sap):
    sh = conectar_google()
    ws = sh.worksheet("Perfis_Lotes")
    
    # Procura o SAP
    cell = ws.find(str(cod_sap))
    
    if cell:
        # Se achou, pega o valor da coluna ao lado (coluna B)
        ultimo = int(ws.cell(cell.row, 2).value)
        proximo = ultimo + 1
        ws.update_cell(cell.row, 2, proximo)
    else:
        # Se não achou, cria novo
        proximo = 1
        ws.append_row([cod_sap, proximo])
        
    prefixo = "BRASA"
    return f"{prefixo}{proximo:05d}"

def salvar_no_banco(dados):
    sh = conectar_google()
    ws = sh.worksheet("Perfis_Producao")
    
    lote_oficial = obter_e_incrementar_lote(dados['Cód. SAP'])
    
    # Gera ID único baseado no tempo (timestamp)
    novo_id = int(datetime.now().timestamp() * 1000)
    
    linha = [
        novo_id,
        datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        lote_oficial,
        dados['Reserva'],
        "Pendente",
        int(dados['Cód. SAP']),
        dados['Descrição'],
        int(dados['Qtd']),
        float(dados['Peso Balança (kg)']),
        int(dados['Tamanho Real (mm)']),
        int(dados['Tamanho Corte (mm)']),
        float(dados['Peso Teórico']),
        float(dados['Sucata'])
    ]
    
    ws.append_row(linha)
    return lote_oficial

def atualizar_status_lote(df_editado):
    sh = conectar_google()
    ws = sh.worksheet("Perfis_Producao")
    
    # GSheets é lento para atualizar um por um. 
    # Estratégia: O usuário editou o Status no Streamlit.
    # Vamos achar a linha pelo ID e atualizar o Status.
    
    # Pega todos os dados atuais da planilha para comparar (ou só atualiza o que mudou)
    # Para simplificar e não estourar cota: Atualiza apenas os que mudaram seria ideal, 
    # mas aqui vamos fazer loop simples.
    
    registros_sheet = ws.get_all_records()
    
    for i, row_sheet in enumerate(registros_sheet):
        id_sheet = row_sheet['id']
        # Acha esse ID no DF editado
        row_editada = df_editado[df_editado['id'] == id_sheet]
        
        if not row_editada.empty:
            novo_status = row_editada.iloc[0]['status_reserva']
            # Se mudou, atualiza na planilha
            if row_sheet['status_reserva'] != novo_status:
                # +2 porque row_sheet começa do 0 e tem cabeçalho (linha 1)
                ws.update_cell(i + 2, 5, novo_status) # 5 é a coluna status_reserva

def limpar_banco_completo():
    sh = conectar_google()
    # Limpa Produção
    ws_p = sh.worksheet("Perfis_Producao")
    ws_p.clear()
    ws_p.append_row(["id", "data_hora", "lote", "reserva", "status_reserva", "cod_sap", "descricao", "qtd", "peso_real", "tamanho_real_mm", "tamanho_corte_mm", "peso_teorico", "sucata"])
    
    # Limpa Lotes
    ws_l = sh.worksheet("Perfis_Lotes")
    ws_l.clear()
    ws_l.append_row(["cod_sap", "ultimo_numero"])

def excluir_linha_por_id(id_alvo):
    sh = conectar_google()
    ws = sh.worksheet("Perfis_Producao")
    cell = ws.find(str(id_alvo))
    if cell:
        ws.delete_rows(cell.row)
        return True
    return False

def ajustar_contador_lote(cod_sap, novo_valor):
    sh = conectar_google()
    ws = sh.worksheet("Perfis_Lotes")
    cell = ws.find(str(cod_sap))
    if cell:
        ws.update_cell(cell.row, 2, novo_valor)
    else:
        ws.append_row([cod_sap, novo_valor])

# --- FUNÇÕES AUXILIARES ---
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
    if os.path.exists("base_sap.xlsx"): caminho_final = "base_sap.xlsx"
    elif os.path.exists(caminho_fixo): caminho_final = caminho_fixo
    else: return None
    try:
        df = pd.read_excel(caminho_final)
        df.columns = df.columns.str.strip()
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        if df['Peso por Metro'].dtype == 'object':
                df['Peso por Metro'] = df['Peso por Metro'].str.replace(',', '.').astype(float)
        return df
    except: return None

# --- CONTROLE DE ACESSO ---
st.sidebar.title("🔐 Acesso Restrito")
modo_acesso = st.sidebar.radio("Selecione o Perfil:", ["Operador (Chão de Fábrica)", "Administrador (Escritório)", "Super Admin"])

df_sap = carregar_base_sap()
if df_sap is None: st.error("ERRO: `base_sap.xlsx` não encontrado.")

# ==============================================================================
# TELA 1: OPERADOR
# ==============================================================================
if modo_acesso == "Operador (Chão de Fábrica)":
    st.title("🏭 Operador: Bipagem")
    if df_sap is not None:
        if 'wizard_data' not in st.session_state: st.session_state.wizard_data = {}
        if 'wizard_step' not in st.session_state: st.session_state.wizard_step = 0
        if 'item_id' not in st.session_state: st.session_state.item_id = 0 
        
        # Como o lote é online, não mostramos o "próximo" antes de bipar para evitar delay
        # Mas podemos mostrar o último gerado se quisermos. Por hora, simplificado.

        @st.dialog("📦 Entrada de Material")
        def wizard_item():
            st.write(f"**Item:** {st.session_state.wizard_data.get('Cód. SAP')} - {st.session_state.wizard_data.get('Descrição')}")
            st.markdown("---")
            if st.session_state.wizard_step == 1:
                with st.form("form_reserva"):
                    reserva = st.text_input("1. Nº da Reserva:", key=f"res_{st.session_state.item_id}")
                    st.write("")
                    if st.form_submit_button("PRÓXIMO >>", use_container_width=True, type="primary"):
                        if reserva.strip():
                            st.session_state.wizard_data['Reserva'] = reserva
                            st.session_state.wizard_step = 2
                            st.rerun()
                        else: st.error("⚠️ Digite a Reserva!")
            elif st.session_state.wizard_step == 2:
                with st.form("form_qtd"):
                    qtd = st.number_input("2. Quantidade (Peças):", min_value=1, step=1, value=1, key=f"qtd_{st.session_state.item_id}")
                    st.write("")
                    if st.form_submit_button("PRÓXIMO >>", use_container_width=True, type="primary"):
                        st.session_state.wizard_data['Qtd'] = qtd
                        st.session_state.wizard_step = 3
                        st.rerun()
            elif st.session_state.wizard_step == 3:
                with st.form("form_peso"):
                    peso = st.number_input("3. Peso Real (kg):", min_value=0.000, step=0.001, format="%.3f", key=f"peso_{st.session_state.item_id}")
                    st.write("")
                    if st.form_submit_button("PRÓXIMO >>", use_container_width=True, type="primary"):
                        if peso > 0:
                            st.session_state.wizard_data['Peso Balança (kg)'] = peso
                            st.session_state.wizard_step = 4
                            st.rerun()
                        else: st.error("⚠️ Peso não pode ser Zero!")
            elif st.session_state.wizard_step == 4:
                with st.form("form_comp"):
                    comp = st.number_input("4. Comprimento Real (mm):", min_value=0, step=1, key=f"comp_{st.session_state.item_id}")
                    st.write("")
                    if st.form_submit_button("✅ SALVAR E FINALIZAR", use_container_width=True, type="primary"):
                        if comp > 0:
                            with st.spinner("Salvando na nuvem..."):
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
                                lote_gerado = salvar_no_banco(item_temp)
                                st.toast(f"Salvo! Lote: {lote_gerado}", icon="🏷️")
                                st.session_state.wizard_data = {}
                                st.session_state.wizard_step = 0
                                st.session_state.input_scanner = ""
                                time.sleep(1) # Tempo para ver o toast
                                st.rerun()
                        else: st.error("⚠️ Comprimento não pode ser Zero!")

        def iniciar_bipagem():
            codigo = st.session_state.input_scanner
            if codigo:
                try:
                    cod_limpo = str(codigo).strip().split(":")[-1]
                    cod_int = int(cod_limpo)
                    produto = df_sap[df_sap['Produto'] == cod_int]
                    if not produto.empty:
                        st.session_state.item_id += 1 
                        st.session_state.wizard_data = {
                            "Cód. SAP": cod_int,
                            "Descrição": produto.iloc[0]['Descrição do produto'],
                            "Peso/m": produto.iloc[0]['Peso por Metro']
                        }
                        st.session_state.wizard_step = 1
                    else:
                        st.toast("Material não encontrado!", icon="🚫")
                        st.session_state.input_scanner = ""
                except: st.session_state.input_scanner = ""

        if st.session_state.wizard_step > 0: wizard_item()
        st.text_input("BIPAR CÓDIGO:", key="input_scanner", on_change=iniciar_bipagem)

# ==============================================================================
# TELA 2: ADMINISTRADOR
# ==============================================================================
elif modo_acesso == "Administrador (Escritório)":
    st.title("💻 Admin: Controle de Produção (Google Cloud)")
    SENHA_CORRETA = "Br@met4l"
    senha_digitada = st.sidebar.text_input("Senha Admin", type="password")
    
    if senha_digitada == SENHA_CORRETA:
        st.sidebar.success("Conectado")
        
        # Carrega dados do GSheets
        try:
            df_banco = ler_banco()
        except:
            st.error("Erro ao conectar no Google Sheets. Verifique a internet ou credenciais.")
            df_banco = pd.DataFrame()
        
        if not df_banco.empty:
            tab1, tab2 = st.tabs(["📋 Tabela & Edição", "📊 Dashboard KPIs"])
            
            with tab1:
                if st.button("🔄 Atualizar Tabela (Nuvem)"): st.rerun()
                c1, c2, c3 = st.columns(3)
                c1.metric("Itens", len(df_banco))
                c2.metric("Peso Total", formatar_br(df_banco['peso_real'].sum()) + " kg")
                c3.metric("Sucata Total", formatar_br(df_banco['sucata'].sum()) + " kg")
                
                st.markdown("### Conferência")
                df_editado = st.data_editor(
                    df_banco,
                    use_container_width=True,
                    column_config={
                        "id": st.column_config.NumberColumn("ID", disabled=True),
                        "data_hora": st.column_config.TextColumn("Data", disabled=True),
                        "lote": st.column_config.TextColumn("Lote", disabled=True),
                        "reserva": st.column_config.TextColumn("Reserva", disabled=True),
                        "status_reserva": st.column_config.SelectboxColumn("Status", width="medium", options=["Pendente", "Ok - Lançada"], required=True),
                        "cod_sap": st.column_config.NumberColumn("SAP", format="%d", disabled=True),
                        "descricao": st.column_config.TextColumn("Descrição", disabled=True),
                        "qtd": st.column_config.NumberColumn("Qtd", disabled=True),
                        "peso_real": st.column_config.NumberColumn("Peso Real (kg)", format="%.3f", disabled=True),
                        "tamanho_real_mm": st.column_config.NumberColumn("Comp. Real", format="%d", disabled=True),
                        "tamanho_corte_mm": st.column_config.NumberColumn("Comp. Corte", format="%d", disabled=True),
                        "sucata": st.column_config.NumberColumn("Sucata (kg)", format="%.3f", disabled=True),
                        "peso_teorico": None
                    },
                    key="editor_admin"
                )
                if st.button("💾 Salvar Status na Nuvem"):
                    with st.spinner("Atualizando planilha..."):
                        atualizar_status_lote(df_editado)
                    st.success("Salvo com sucesso!")
                    st.rerun()
                
                # Exportação Excel
                lista_exportacao = []
                for index, row in df_banco.iterrows():
                    linha_original = {
                        'Lote': row['lote'],
                        'Reserva': row['reserva'],
                        'SAP': row['cod_sap'],
                        'Descrição': row['descricao'],
                        'Status': row['status_reserva'],
                        'Qtd': row['qtd'],
                        'Peso Lançamento (kg)': formatar_br(row['peso_teorico']), 
                        'Comp. Real (mm)': row['tamanho_real_mm'],
                        'Comp. Corte (mm)': row['tamanho_corte_mm'],
                    }
                    lista_exportacao.append(linha_original)
                    if row['sucata'] > 0.001:
                        linha_virtual = {
                            'Lote': "VIRTUAL",
                            'Reserva': row['reserva'],
                            'SAP': row['cod_sap'],
                            'Descrição': f"SUCATA - {row['descricao']}",
                            'Status': row['status_reserva'],
                            'Qtd': 1,
                            'Peso Lançamento (kg)': formatar_br(row['sucata']), 
                            'Comp. Real (mm)': 0,
                            'Comp. Corte (mm)': 0,
                        }
                        lista_exportacao.append(linha_virtual)

                df_export_final = pd.DataFrame(lista_exportacao)
                if not df_export_final.empty:
                    cols_order = ['Lote', 'Reserva', 'SAP', 'Descrição', 'Peso Lançamento (kg)', 'Status', 'Qtd', 'Comp. Real (mm)', 'Comp. Corte (mm)']
                    cols_final = [c for c in cols_order if c in df_export_final.columns]
                    df_export_final = df_export_final[cols_final]
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_export_final.to_excel(writer, index=False)
                    st.markdown("---")
                    st.download_button("📥 Baixar Excel", buffer.getvalue(), "Relatorio_Lancamento.xlsx", type="primary")
            
            with tab2:
                st.subheader("📊 Indicadores de Performance (KPIs)")
                peso_total = df_banco['peso_real'].sum()
                sucata_total = df_banco['sucata'].sum()
                if peso_total > 0: pct_sucata = (sucata_total / peso_total) * 100
                else: pct_sucata = 0
                kpi1, kpi2, kpi3 = st.columns(3)
                kpi1.metric("Produção Total", f"{peso_total:,.2f} kg".replace(",", "X").replace(".", ",").replace("X", "."))
                kpi2.metric("Total de Sucata", f"{sucata_total:,.2f} kg".replace(",", "X").replace(".", ",").replace("X", "."), delta_color="inverse")
                kpi3.metric("Índice de Sucata %", f"{pct_sucata:.2f}%", delta=f"{pct_sucata:.2f}%", delta_color="inverse")
                st.markdown("---")
                st.write("### 🏆 Top Materiais Produzidos")
                df_chart = df_banco.groupby("descricao")[["peso_real"]].sum().sort_values("peso_real", ascending=False).head(10)
                st.bar_chart(df_chart)
        else: st.info("Nenhum dado na nuvem.")
    elif senha_digitada: st.sidebar.error("Senha Incorreta")

# ==============================================================================
# TELA 3: SUPER ADMIN
# ==============================================================================
elif modo_acesso == "Super Admin":
    st.title("🛠️ Super Admin (Google Cloud)")
    SENHA_MESTRA = "Workaround&97146605"
    senha_digitada = st.sidebar.text_input("Senha Mestra", type="password")
    
    if senha_digitada == SENHA_MESTRA:
        st.sidebar.success("Acesso ROOT Liberado")
        
        st.subheader("1. Reset Geral (Perigo)")
        st.warning("⚠️ Isso apaga TODAS as linhas da planilha 'Perfis_Producao' e 'Perfis_Lotes'.")
        if st.button("💣 ZERAR PLANILHA COMPLETA", type="primary"):
            with st.spinner("Limpando Google Sheets..."):
                limpar_banco_completo()
            st.success("Planilhas limpas com sucesso!")
        
        st.markdown("---")
        st.subheader("2. Ajustar Contador de Lotes")
        
        sh = conectar_google()
        ws_lotes = sh.worksheet("Perfis_Lotes")
        dados_lotes = ws_lotes.get_all_records()
        df_lotes = pd.DataFrame(dados_lotes)
        st.dataframe(df_lotes)
        
        c1, c2, c3 = st.columns(3)
        cod_sap_alvo = c1.number_input("Cód. SAP:", step=1, format="%d")
        novo_valor = c2.number_input("Novo Valor:", min_value=0, step=1)
        if c3.button("Atualizar Lote"):
            ajustar_contador_lote(cod_sap_alvo, novo_valor)
            st.success("Atualizado!")
            st.rerun()
            
        st.markdown("---")
        st.subheader("3. Excluir Linha por ID")
        
        df_prod = ler_banco()
        st.dataframe(df_prod)
        
        c_del1, c_del2 = st.columns([1,2])
        id_del = c_del1.number_input("ID para excluir:", step=1, format="%d")
        if c_del2.button("🗑️ Excluir"):
            if id_del > 0:
                with st.spinner("Deletando da nuvem..."):
                    sucesso = excluir_linha_por_id(id_del)
                if sucesso: 
                    st.success("Excluído!")
                    st.rerun()
                else: st.error("ID não encontrado.")
    
    elif senha_digitada: st.error("Acesso Negado")
