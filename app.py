import streamlit as st
import pandas as pd
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime, time as datetime_time
import json
import io
import os
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Sistema Integrado Produção", layout="wide")

# --- CSS ---
st.markdown("""
<style>
    header[data-testid="stHeader"] {display: none;}
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
    .block-container {padding-top: 1rem !important;}
</style>
""", unsafe_allow_html=True)

# --- CONEXÃO FIREBASE ---
@st.cache_resource
def get_db():
    key_dict = dict(st.secrets["firebase"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

# --- FUNÇÕES ---
def get_proximo_lote(db, cod_sap):
    doc_ref = db.collection('controles').document('lotes_perfis')
    doc = doc_ref.get()
    
    if not doc.exists:
        doc_ref.set({})
        dados = {}
    else:
        dados = doc.to_dict()
        
    sap_str = str(cod_sap)
    ultimo = int(dados.get(sap_str, 0))
    novo = ultimo + 1
    
    doc_ref.set({sap_str: novo}, merge=True)
    return f"BRASA{novo:05d}"

def salvar_no_firebase(dados):
    db = get_db()
    lote = get_proximo_lote(db, dados['cod_sap'])
    
    payload = {
        "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "timestamp": datetime.now(),
        "lote": lote,
        "reserva": str(dados['reserva']),
        "status_reserva": "Pendente",
        "cod_sap": int(dados['cod_sap']),
        "descricao": dados['descricao'],
        "qtd": int(dados['qtd']),
        "peso_real": float(dados['peso_real']),
        "tamanho_real_mm": int(dados['tamanho_real_mm']),
        "tamanho_corte_mm": int(dados['tamanho_corte_mm']),
        "peso_teorico": float(dados['peso_teorico']),
        "sucata": float(dados['sucata'])
    }
    
    db.collection('perfis_producao').add(payload)
    return lote

def formatar_br(v):
    try: return f"{float(v):,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,000"

def regra_corte(mm):
    try: return (int(float(mm)) // 500) * 500
    except: return 0

@st.cache_data
def carregar_base_sap():
    path = "base_sap.xlsx"
    if not os.path.exists(path): return None
    try:
        df = pd.read_excel(path, dtype=str)
        df.columns = df.columns.str.strip().str.upper()
        col_prod = next((c for c in df.columns if 'PRODUTO' in c), None)
        col_peso = next((c for c in df.columns if 'PESO' in c and 'METRO' in c), None)
        
        if col_prod and col_peso:
            df['PRODUTO'] = pd.to_numeric(df[col_prod], errors='coerce').fillna(0).astype(int)
            def conv(x):
                if pd.isna(x): return 0.0
                s = str(x).strip()
                if '.' in s and ',' in s: s = s.replace('.', '')
                s = s.replace(',', '.')
                try: return float(s)
                except: return 0.0
            df['PESO_FATOR'] = df[col_peso].apply(conv)
            return df
        return None
    except: return None

# --- APP ---
st.sidebar.title("Acesso ao Sistema")
perfil = st.sidebar.radio("Perfil de Acesso:", ["Operador", "Administrador", "Super Admin"])
df_sap = carregar_base_sap()

# === OPERADOR ===
if perfil == "Operador":
    st.title("Operador: Perfis")
    if df_sap is not None:
        if 'wizard_data' not in st.session_state: st.session_state.wizard_data = {}
        if 'wizard_step' not in st.session_state: st.session_state.wizard_step = 0
        
        @st.dialog("Entrada de Dados")
        def wizard():
            st.write(f"**Item:** {st.session_state.wizard_data.get('Cód. SAP')}")
            fator_oculto = float(st.session_state.wizard_data.get('PESO_FATOR', 0.0))
            
            st.markdown("---")
            if st.session_state.wizard_step == 1:
                with st.form("f1"):
                    res = st.text_input("1. Reserva:", key="w_res")
                    if st.form_submit_button("PRÓXIMO"):
                        if res.strip():
                            st.session_state.wizard_data.update({'reserva': res, 'PESO_FATOR': fator_oculto})
                            st.session_state.wizard_step = 2
                            st.rerun()
                        else: st.error("Campo obrigatório.")
            
            elif st.session_state.wizard_step == 2:
                with st.form("f2"):
                    qtd = st.number_input("2. Quantidade:", min_value=1, step=1)
                    if st.form_submit_button("PRÓXIMO"):
                        st.session_state.wizard_data['qtd'] = qtd
                        st.session_state.wizard_step = 3
                        st.rerun()
            
            elif st.session_state.wizard_step == 3:
                with st.form("f3"):
                    peso = st.number_input("3. Peso Real (kg):", min_value=0.001, format="%.3f")
                    if st.form_submit_button("PRÓXIMO"):
                        st.session_state.wizard_data['peso_real'] = peso
                        st.session_state.wizard_step = 4
                        st.rerun()
            
            elif st.session_state.wizard_step == 4:
                comp = st.number_input("4. Comprimento Real (mm):", min_value=0)
                fator = st.session_state.wizard_data['PESO_FATOR']
                q = st.session_state.wizard_data['qtd']
                tc = regra_corte(comp)
                pt = (tc/1000.0) * fator * q
                
                if comp > 0: st.info(f"Cálculo: **{formatar_br(pt)} kg**")
                
                if st.button("SALVAR DADOS", type="primary"):
                    if comp > 0:
                        with st.spinner("Registrando no sistema..."):
                            sucata = st.session_state.wizard_data['peso_real'] - pt
                            dados = {
                                'reserva': st.session_state.wizard_data['reserva'],
                                'cod_sap': st.session_state.wizard_data['Cód. SAP'],
                                'descricao': st.session_state.wizard_data['Descrição'],
                                'qtd': q,
                                'peso_real': st.session_state.wizard_data['peso_real'],
                                'tamanho_real_mm': comp,
                                'tamanho_corte_mm': tc,
                                'peso_teorico': pt,
                                'sucata': sucata
                            }
                            try:
                                lote = salvar_no_firebase(dados)
                                st.toast(f"Lote {lote} registrado.")
                                st.session_state.wizard_step = 0
                                st.session_state.input_scanner = ""
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro de conexão: {e}")
                    else: st.error("Valor inválido.")

        def check():
            c = st.session_state.input_scanner
            if c:
                try:
                    cod = int(str(c).strip().split(":")[-1])
                    row = df_sap[df_sap['PRODUTO'] == cod]
                    if not row.empty:
                        st.session_state.wizard_data = {
                            "Cód. SAP": cod,
                            "Descrição": row.iloc[0]['DESCRIÇÃO DO PRODUTO'],
                            "PESO_FATOR": float(row.iloc[0]['PESO_FATOR'])
                        }
                        st.session_state.wizard_step = 1
                    else: st.toast("Código não encontrado.")
                except: pass
                st.session_state.input_scanner = ""

        if st.session_state.wizard_step > 0: wizard()
        st.text_input("Leitura SAP (Código):", key="input_scanner", on_change=check)

# === ADMIN ===
elif perfil == "Administrador":
    st.title("Painel Administrativo")
    if st.sidebar.text_input("Senha", type="password") == "Br@met4l":
        if st.button("Atualizar Página"): st.rerun()
        
        db = get_db()
        docs = db.collection('perfis_producao').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1000).stream()
        lista = [d.to_dict() | {'id_doc': d.id} for d in docs]
        df = pd.DataFrame(lista)
        
        if not df.empty:
            df_pendentes = df[df['status_reserva'] == 'Pendente'].copy()
            
            tab1, tab2 = st.tabs(["Fila de Lançamentos", "Relatórios e Exportação"])
            
            with tab1:
                st.subheader("Lotes Pendentes de Lançamento no SAP")
                
                if not df_pendentes.empty:
                    df_view = df_pendentes[['lote', 'reserva', 'cod_sap', 'descricao', 'qtd', 'peso_teorico', 'data_hora']]
                    df_view.columns = ['Lote', 'Reserva', 'Cód. SAP', 'Descrição', 'Qtd', 'Peso (kg)', 'Data/Hora']
                    st.dataframe(df_view, use_container_width=True, hide_index=True)
                    
                    # Preparação do Excel apenas com os dados visíveis na tela
                    lst_export_pendentes = []
                    for _, r in df_pendentes.iterrows():
                        lst_export_pendentes.append({
                            'Lote': r['lote'],
                            'Reserva': r['reserva'],
                            'SAP': r['cod_sap'],
                            'Descrição': r['descricao'],
                            'Status': r['status_reserva'],
                            'Qtd': int(r['qtd']),
                            'Peso Lançamento (kg)': float(r['peso_teorico']),
                            'Comp. Real': int(r['tamanho_real_mm']),
                            'Comp. Corte': int(r['tamanho_corte_mm']),
                            'Data/Hora': r['data_hora']
                        })
                        if float(r['sucata']) > 0.001:
                            lst_export_pendentes.append({
                                'Lote': 'VIRTUAL',
                                'Reserva': r['reserva'],
                                'SAP': r['cod_sap'],
                                'Descrição': f"SUCATA - {r['descricao']}",
                                'Status': r['status_reserva'],
                                'Qtd': 1,
                                'Peso Lançamento (kg)': float(r['sucata']),
                                'Comp. Real': 0,
                                'Comp. Corte': 0,
                                'Data/Hora': r['data_hora']
                            })
                    
                    df_export_pendentes = pd.DataFrame(lst_export_pendentes)
                    b_pendentes = io.BytesIO()
                    with pd.ExcelWriter(b_pendentes, engine='openpyxl') as w:
                        df_export_pendentes.to_excel(w, index=False, sheet_name='Pendentes')
                        ws = w.sheets['Pendentes']
                        col_indices = [i+1 for i, c in enumerate(df_export_pendentes.columns) if 'peso' in c.lower() or 'sucata' in c.lower()]
                        for r in range(2, ws.max_row + 1):
                            for c in col_indices:
                                ws.cell(row=r, column=c).number_format = '#,##0.000'
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    col_btn1, col_btn2 = st.columns(2)
                    
                    with col_btn1:
                        st.download_button("Baixar Excel (Apenas Lotes da Tela)", b_pendentes.getvalue(), "Lotes_Pendentes.xlsx", "secondary", use_container_width=True)
                    
                    with col_btn2:
                        if st.button("Arquivar Todos os Lotes Pendentes", type="primary", use_container_width=True):
                            with st.spinner("Processando..."):
                                for _, row in df_pendentes.iterrows():
                                    db.collection('perfis_producao').document(row['id_doc']).update({'status_reserva': 'Ok - Lançada'})
                            st.success("Lotes arquivados com sucesso.")
                            time.sleep(1)
                            st.rerun()
                else:
                    st.info("Não há lotes pendentes no momento.")
                    
                st.markdown("---")
                with st.expander("Excluir Registro Específico"):
                    id_del_admin = st.text_input("Insira o ID do Sistema para exclusão:")
                    if st.button("Confirmar Exclusão"):
                        if id_del_admin:
                            try:
                                db.collection('perfis_producao').document(id_del_admin).delete()
                                st.success("Registro excluído.")
                                time.sleep(1)
                                st.rerun()
                            except: st.error("Erro na operação.")

            with tab2:
                st.subheader("Indicadores de Produção (Últimos 1000 registros)")
                c1,c2,c3 = st.columns(3)
                c1.metric("Volume de Itens", len(df))
                c2.metric("Peso Total (kg)", formatar_br(df['peso_real'].sum()))
                c3.metric("Sucata Total (kg)", formatar_br(df['sucata'].sum()))
                
                st.markdown("---")
                st.subheader("Exportação de Dados (Histórico Completo)")
                st.info("Selecione o período para gerar o relatório consolidado de todos os lotes (pendentes e arquivados).")
                
                col_d1, col_d2 = st.columns(2)
                data_inicio = col_d1.date_input("Data Inicial", datetime.today())
                data_fim = col_d2.date_input("Data Final", datetime.today())
                
                if st.button("Gerar Relatório Excel (Histórico)"):
                    with st.spinner("Extraindo dados..."):
                        inicio_dt = datetime.combine(data_inicio, datetime_time.min)
                        fim_dt = datetime.combine(data_fim, datetime_time.max)
                        
                        docs_export = db.collection('perfis_producao')\
                                        .where('timestamp', '>=', inicio_dt)\
                                        .where('timestamp', '<=', fim_dt)\
                                        .order_by('timestamp', direction=firestore.Query.DESCENDING)\
                                        .stream()
                        
                        lista_export = [d.to_dict() for d in docs_export]
                        
                        if not lista_export:
                            st.warning("Nenhum registro encontrado no período selecionado.")
                        else:
                            df_export = pd.DataFrame(lista_export)
                            lst_final_excel = []
                            
                            for _, r in df_export.iterrows():
                                lst_final_excel.append({
                                    'Lote': r.get('lote', ''),
                                    'Reserva': r.get('reserva', ''),
                                    'SAP': r.get('cod_sap', ''),
                                    'Descrição': r.get('descricao', ''),
                                    'Status': r.get('status_reserva', ''),
                                    'Qtd': int(r.get('qtd', 0)),
                                    'Peso Lançamento (kg)': float(r.get('peso_teorico', 0)),
                                    'Comp. Real': int(r.get('tamanho_real_mm', 0)),
                                    'Comp. Corte': int(r.get('tamanho_corte_mm', 0)),
                                    'Data/Hora': r.get('data_hora', '')
                                })
                                if float(r.get('sucata', 0)) > 0.001:
                                    lst_final_excel.append({
                                        'Lote': 'VIRTUAL',
                                        'Reserva': r.get('reserva', ''),
                                        'SAP': r.get('cod_sap', ''),
                                        'Descrição': f"SUCATA - {r.get('descricao', '')}",
                                        'Status': r.get('status_reserva', ''),
                                        'Qtd': 1,
                                        'Peso Lançamento (kg)': float(r.get('sucata', 0)),
                                        'Comp. Real': 0,
                                        'Comp. Corte': 0,
                                        'Data/Hora': r.get('data_hora', '')
                                    })
                            
                            df_final = pd.DataFrame(lst_final_excel)
                            b = io.BytesIO()
                            with pd.ExcelWriter(b, engine='openpyxl') as w:
                                df_final.to_excel(w, index=False, sheet_name='Relatorio')
                                ws = w.sheets['Relatorio']
                                col_indices = [i+1 for i, c in enumerate(df_final.columns) if 'peso' in c.lower() or 'sucata' in c.lower()]
                                for r in range(2, ws.max_row + 1):
                                    for c in col_indices:
                                        ws.cell(row=r, column=c).number_format = '#,##0.000'
                            
                            st.success("Relatório histórico gerado.")
                            nome_arquivo = f"Relatorio_Producao_{data_inicio.strftime('%d%m%Y')}.xlsx"
                            st.download_button("Download Arquivo Excel", b.getvalue(), nome_arquivo, "primary")

        else: st.info("Banco de dados vazio.")
    else: st.error("Credenciais inválidas.")

# === SUPER ADMIN ===
elif perfil == "Super Admin":
    st.title("Super Administrador")
    if st.sidebar.text_input("Senha", type="password") == "Workaround&97146605":
        db = get_db()
        
        tab_a, tab_b, tab_c = st.tabs(["Reset Geral", "Ajuste de Lotes", "Exclusão Manual"])
        
        with tab_a:
            st.warning("ATENÇÃO: Operação destrutiva. Apaga todos os dados de produção.")
            if st.button("APAGAR BANCO DE DADOS", type="primary"):
                docs = db.collection('perfis_producao').stream()
                for d in docs: d.reference.delete()
                db.collection('controles').document('lotes_perfis').delete()
                st.success("Banco de dados limpo com sucesso.")
                time.sleep(1)
                st.rerun()
        
        with tab_b:
            st.subheader("Gerenciamento de Contadores de Lote")
            doc = db.collection('controles').document('lotes_perfis').get()
            if doc.exists:
                data = doc.to_dict()
                df_lotes = pd.DataFrame(list(data.items()), columns=['Código SAP', 'Último Lote Gerado'])
                st.dataframe(df_lotes, use_container_width=True)
                
                c1, c2 = st.columns(2)
                sap = c1.number_input("SAP para alteração:", step=1, format="%d")
                val = c2.number_input("Novo Valor Inicial:", step=1)
                if c2.button("Atualizar Contador"):
                    db.collection('controles').document('lotes_perfis').set({str(sap): val}, merge=True)
                    st.success("Contador atualizado.")
                    time.sleep(1)
                    st.rerun()
            else: st.info("Sem registros de lote no sistema.")
            
        with tab_c:
            st.subheader("Exclusão de Registros via ID")
            st.info("Insira o ID exato do documento do Firestore para exclusão permanente.")
            id_manual = st.text_input("ID do Documento:")
            if st.button("Executar Exclusão"):
                if id_manual:
                    try:
                        db.collection('perfis_producao').document(id_manual).delete()
                        st.success("Documento deletado com sucesso.")
                    except: st.error("Falha na execução.")
