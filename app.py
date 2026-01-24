import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import io
import json
import time

# --- 1. Configuração da Página (Deve ser a primeira linha) ---
st.set_page_config(
    page_title="Brametal | Controle de Devolução",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CSS Personalizado (O "Banho de Loja") ---
st.markdown("""
<style>
    /* Fundo geral e fontes */
    .stApp {
        background-color: #f0f2f6;
    }
    
    /* Cabeçalho */
    h1 {
        color: #0d47a1;
        font-family: 'Helvetica', sans-serif;
        font-weight: 700;
        padding-top: 0px;
    }
    h3 {
        color: #1565c0;
    }
    
    /* Cards de Upload */
    .stFileUploader {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Botão Principal */
    .stButton>button {
        width: 100%;
        background-color: #0d47a1; /* Azul Escuro */
        color: white;
        font-size: 18px;
        font-weight: bold;
        border-radius: 8px;
        padding: 0.8rem;
        border: none;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #1565c0; /* Azul mais claro no mouse over */
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        color: white;
    }

    /* Métricas */
    div[data-testid="stMetric"] {
        background-color: white;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #0d47a1;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# --- 3. Lógica de Autenticação (Chave API) ---
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    auth_status = True
else:
    auth_status = False

# --- 4. Barra Lateral (Sidebar) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2504/2504936.png", width=80) # Ícone genérico de indústria
    st.title("Menu de Controle")
    
    st.markdown("---")
    
    if auth_status:
        st.success("✅ Sistema Licenciado")
    else:
        st.warning("⚠️ Modo Desenvolvedor")
        api_key = st.text_input("Insira API Key", type="password")

    st.markdown("### 📝 Como usar:")
    st.markdown("""
    1. **Base de Dados:** Suba a planilha do SAP com os pesos teóricos.
    2. **Fotos:** Selecione todas as fotos das etiquetas de uma vez.
    3. **Processar:** Clique no botão azul e aguarde a mágica.
    """)
    
    st.markdown("---")
    st.caption("Versão 2.0 - Brametal System")

# --- 5. Corpo Principal ---

# Cabeçalho com colunas para organizar
col_header_1, col_header_2 = st.columns([3, 1])
with col_header_1:
    st.title("Controle de Devolução & Sucata")
    st.markdown("Sistema inteligente para leitura de etiquetas e recálculo de peso teórico.")

st.markdown("<br>", unsafe_allow_html=True) # Espaço

# Área de Uploads
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📂 1. Base de Dados (SAP)")
    file_sap = st.file_uploader(
        "Arraste a planilha aqui", 
        type=['xlsx', 'xls', 'csv'],
        key="sap_uploader"
    )

with col2:
    st.markdown("### 📷 2. Fotos das Etiquetas")
    uploaded_images = st.file_uploader(
        "Selecione as fotos (múltiplos arquivos)", 
        type=['png', 'jpg', 'jpeg'], 
        accept_multiple_files=True,
        key="img_uploader"
    )

# --- 6. Funções de Negócio ---

def carregar_dados_sap(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        return df[['Produto', 'Peso por Metro']]
    except Exception as e:
        return None

def calcular_nova_dimensao(tamanho_mm):
    try:
        val = int(float(tamanho_mm))
        return (val // 500) * 500
    except:
        return 0

# --- 7. Botão de Ação ---
st.markdown("---")
col_btn_1, col_btn_2, col_btn_3 = st.columns([1, 2, 1])

with col_btn_2:
    process_btn = st.button("🚀 INICIAR PROCESSAMENTO AUTOMÁTICO")

# --- 8. Execução ---

if process_btn:
    if not api_key:
        st.error("❌ Chave de API ausente.")
        st.stop()
    if not file_sap or not uploaded_images:
        st.warning("⚠️ Por favor, carregue a Planilha SAP e as Fotos antes de iniciar.")
        st.stop()

    # Layout de Carregamento
    with st.status("🤖 A IA está trabalhando...", expanded=True) as status:
        
        st.write("📥 Lendo planilha SAP...")
        df_sap = carregar_dados_sap(file_sap)
        if df_sap is None:
            status.update(label="Erro na planilha SAP", state="error")
            st.stop()
        
        st.write("👁️ Analisando etiquetas (Vision AI)...")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        dados_extraidos = []
        progress_bar = st.progress(0)

        for index, img_file in enumerate(uploaded_images):
            try:
                image = PIL.Image.open(img_file)
                prompt = """
                Extraia JSON estrito:
                [{'Reserva': 'txt', 'Descrição Material': 'txt', 'Código Material': int, 'Quantidade': int, 'Peso': float, 'Tamanho': int}]
                Se 'Código Material' não estiver claro, tente inferir ou deixe 0.
                """
                response = model.generate_content([prompt, image])
                text_json = response.text.replace("```json", "").replace("```", "").strip()
                
                # Tratamento robusto de JSON
                if text_json.startswith("{"): text_json = "[" + text_json + "]"
                items = json.loads(text_json)
                
                for item in items:
                    dados_extraidos.append(item)
            except:
                pass # Ignora erros pontuais para não parar o processo
            
            progress_bar.progress((index + 1) / len(uploaded_images))
        
        st.write("📐 Realizando cálculos de engenharia...")
        
        if dados_extraidos:
            df_etiquetas = pd.DataFrame(dados_extraidos)
            
            # Tratamento de dados
            df_etiquetas['Código Material'] = pd.to_numeric(df_etiquetas['Código Material'], errors='coerce').fillna(0).astype(int)
            df_etiquetas['Quantidade'] = pd.to_numeric(df_etiquetas['Quantidade'], errors='coerce').fillna(1).astype(int)
            df_etiquetas['Peso'] = pd.to_numeric(df_etiquetas['Peso'], errors='coerce').fillna(0.0)
            df_etiquetas['Tamanho'] = pd.to_numeric(df_etiquetas['Tamanho'], errors='coerce').fillna(0).astype(int)

            # Cruzamento
            df_final = df_etiquetas.merge(df_sap, left_on='Código Material', right_on='Produto', how='left')
            df_final.rename(columns={'Peso por Metro': 'Peso Padrão (SAP)'}, inplace=True)
            df_final['Peso Padrão (SAP)'] = df_final['Peso Padrão (SAP)'].fillna(0.0)

            # Cálculos
            df_final['Nova Dimensão (mm)'] = df_final['Tamanho'].apply(calcular_nova_dimensao)
            df_final['Peso Real Nova Dimensão'] = (df_final['Nova Dimensão (mm)']/1000) * df_final['Peso Padrão (SAP)'] * df_final['Quantidade']
            df_final['Diferença'] = df_final['Peso'] - df_final['Peso Real Nova Dimensão']

            # Colunas Finais
            cols = ['Reserva', 'Descrição Material', 'Código Material', 'Quantidade', 'Peso', 'Tamanho', 'Nova Dimensão (mm)', 'Peso Real Nova Dimensão', 'Diferença']
            for c in cols:
                if c not in df_final.columns: df_final[c] = 0
            df_final = df_final[cols]

            status.update(label="Processamento Concluído!", state="complete", expanded=False)
            
            # --- 9. Exibição dos Resultados (Bonito) ---
            st.markdown("### 📊 Resultado da Análise")
            
            # Cards de Métricas
            m1, m2, m3 = st.columns(3)
            m1.metric("Total de Peças", f"{df_final['Quantidade'].sum()} un")
            m2.metric("Peso Processado", f"{df_final['Peso'].sum():.2f} kg")
            total_sucata = df_final['Diferença'].sum()
            m3.metric("Diferença Total (Sucata)", f"{total_sucata:.2f} kg", delta_color="inverse")

            # Tabela Estilizada (Highlight)
            def highlight_diff(val):
                color = '#ffcdd2' if val > 0.5 else '#c8e6c9' # Vermelho claro se > 0.5kg, Verde se ok
                return f'background-color: {color}'

            st.dataframe(
                df_final.style.format({"Peso": "{:.2f}", "Peso Real Nova Dimensão": "{:.2f}", "Diferença": "{:.2f}"})
                .applymap(highlight_diff, subset=['Diferença']),
                use_container_width=True
            )

            # Download
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False)
            
            st.download_button(
                label="📥 BAIXAR RELATÓRIO EXCEL COMPLETO",
                data=buffer.getvalue(),
                file_name="Relatorio_Brametal_Final.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download-btn"
            )

        else:
            st.error("Nenhum dado legível encontrado nas imagens.")
