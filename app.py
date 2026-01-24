import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import io
import json

# --- 1. Configuração da Página (LAYOUT PROFISSIONAL) ---
st.set_page_config(
    page_title="Sistema de Devolução",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CSS Corporativo (O "Bonito") ---
st.markdown("""
<style>
    /* Remove padding excessivo */
    .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}
    
    /* Fontes e Cores */
    h1, h2, h3 {font-family: 'Segoe UI', sans-serif; color: #0f172a;}
    
    /* Área de Upload */
    .stFileUploader {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }
    
    /* Botão de Ação (Azul Sóbrio) */
    .stButton>button {
        background-color: #0284c7;
        color: white;
        border: none;
        border-radius: 6px;
        height: 3rem;
        font-weight: 600;
        width: 100%;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        background-color: #0369a1;
        color: white;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    /* Métricas (Cards) */
    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 15px;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. Gerenciamento de Estado (Para não perder dados) ---
if 'dados_tabela' not in st.session_state:
    st.session_state.dados_tabela = pd.DataFrame(columns=['Reserva', 'Descrição', 'Código', 'Qtd', 'Peso', 'Tamanho'])

# --- 4. Barra Lateral ---
with st.sidebar:
    st.header("⚙️ Configuração")
    
    # API Key
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("Licença Ativa")
    else:
        api_key = st.text_input("Chave API", type="password")

    st.markdown("---")
    st.info("Passo 1: Carregue a tabela SAP.\nPasso 2: Carregue as fotos.\nPasso 3: Clique em Processar.")

# --- 5. Funções ---
def limpar_json(texto):
    texto = texto.replace("```json", "").replace("```", "").strip()
    if "{" in texto:
        return texto[texto.find("{"):texto.rfind("}")+1]
    return texto

def carregar_sap(file):
    try:
        if file.name.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        return df[['Produto', 'Peso por Metro']]
    except: return None

def regra_corte(mm):
    try:
        return (int(float(mm)) // 500) * 500
    except: return 0

# --- 6. Interface Principal ---
st.title("🏗️ Sistema de Devolução")
st.markdown("Extração automática com conferência manual.")

col1, col2 = st.columns(2)
with col1:
    file_sap = st.file_uploader("1. Base SAP (.xlsx/.csv)", type=['xlsx', 'xls', 'csv'])
with col2:
    uploaded_images = st.file_uploader("2. Fotos das Etiquetas", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

# Botão de Processamento
if st.button("🚀 PROCESSAR FOTOS"):
    if not api_key or not uploaded_images:
        st.error("Verifique a Chave de API e as Fotos.")
        st.stop()
    
    with st.status("Analisando imagens...", expanded=True) as status:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-pro')
        
        novos_dados = []
        progresso = st.progress(0)
        
        for i, img_file in enumerate(uploaded_images):
            try:
                img = PIL.Image.open(img_file)
                prompt = """
                Extraia JSON estrito desta etiqueta de aço (Brametal).
                Campos:
                - "Reserva": Texto manuscrito (caneta). Se não houver, deixe vazio.
                - "Descrição": Texto do material (Ex: L 90 X 6...).
                - "Código": Código numérico (Ex: 11000...).
                - "Qtd": Inteiro.
                - "Peso": Decimal (ponto).
                - "Tamanho": Inteiro (mm).
                """
                res = model.generate_content([prompt, img])
                json_str = limpar_json(res.text)
                d = json.loads(json_str)
                
                if isinstance(d, dict): d = [d]
                for item in d: novos_dados.append(item)
            except:
                pass # Se falhar, segue o baile (usuário insere manual depois)
            
            progresso.progress((i+1)/len(uploaded_images))
        
        if novos_dados:
            st.session_state.dados_tabela = pd.DataFrame(novos_dados)
            status.update(label="Leitura concluída!", state="complete", expanded=False)
        else:
            status.update(label="Nenhum dado automático. Insira manualmente abaixo.", state="error")

# --- 7. Tabela Editável e Cálculos ---
st.markdown("### 📝 Conferência de Dados")

if file_sap:
    df_sap = carregar_sap(file_sap)
    if df_sap is not None:
        
        # TABELA EDITÁVEL (O Segredo do Sucesso)
        # O usuário vê o que a IA leu e CORRIGE se estiver errado ou preenche se estiver vazio
        df_editado = st.data_editor(
            st.session_state.dados_tabela,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Reserva": st.column_config.TextColumn("Reserva (Caneta)"),
                "Descrição": st.column_config.TextColumn("Descrição", width="medium"),
                "Código": st.column_config.NumberColumn("Cód. Material", format="%d"),
                "Qtd": st.column_config.NumberColumn("Qtd", step=1),
                "Peso": st.column_config.NumberColumn("Peso Etiqueta", format="%.3f"),
                "Tamanho": st.column_config.NumberColumn("Tamanho (mm)", format="%d"),
            }
        )

        # --- Lógica de Cálculo em Tempo Real ---
        if not df_editado.empty:
            # Tratamento
            df_calc = df_editado.copy()
            cols_num = ['Código', 'Qtd', 'Peso', 'Tamanho']
            for c in cols_num:
                if c in df_calc.columns:
                    df_calc[c] = pd.to_numeric(df_calc[c], errors='coerce').fillna(0)
            
            # Cruzamento SAP
            df_final = df_calc.merge(df_sap, left_on='Código', right_on='Produto', how='left')
            df_final['Peso por Metro'] = df_final['Peso por Metro'].fillna(0.0)
            
            # Cálculos
            df_final['Nova Dimensão (mm)'] = df_final['Tamanho'].apply(regra_corte)
            df_final['Peso Calculado'] = (df_final['Nova Dimensão (mm)']/1000) * df_final['Peso por Metro'] * df_final['Qtd']
            df_final['Sucata'] = df_final['Peso'] - df_final['Peso Calculado']
            
            # Seleção de Colunas
            cols_show = ['Reserva', 'Descrição', 'Código', 'Qtd', 'Peso', 'Tamanho', 'Peso por Metro', 'Nova Dimensão (mm)', 'Peso Calculado', 'Sucata']
            for c in cols_show:
                if c not in df_final.columns: df_final[c] = 0
            
            df_final = df_final[cols_show]

            # --- Resultados Finais ---
            st.markdown("---")
            st.markdown("### 📊 Relatório Final")
            
            # Cards Bonitos
            m1, m2, m3 = st.columns(3)
            m1.metric("Itens", len(df_final))
            m2.metric("Peso Etiqueta", f"{df_final['Peso'].sum():.2f} kg")
            m3.metric("Total Sucata", f"{df_final['Sucata'].sum():.2f} kg", delta_color="inverse")
            
            # Tabela Resultado
            st.dataframe(
                df_final.style.format({"Peso": "{:.2f}", "Peso Calculado": "{:.2f}", "Sucata": "{:.2f}", "Peso por Metro": "{:.2f}"}),
                use_container_width=True
            )
            
            # Download
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False)
            
            st.download_button(
                label="📥 Baixar Excel Final",
                data=buffer.getvalue(),
                file_name="Relatorio_Brametal.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

    else:
        st.error("Erro na leitura do SAP.")
else:
    st.warning("⚠️ Carregue a planilha SAP para ver a tabela de conferência.")
