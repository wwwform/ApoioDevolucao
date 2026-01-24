import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import io
import json
import time

# --- 1. Configuração da Página ---
st.set_page_config(
    page_title="Sistema de Devolução PRO",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. CSS ---
st.markdown("""
<style>
    .block-container {padding-top: 1rem; padding-bottom: 5rem;}
    h1 {color: #1e3a8a; font-family: sans-serif;}
    .stButton>button {background-color: #1e3a8a; color: white; border-radius: 5px; height: 3rem; width: 100%;}
    .stButton>button:hover {background-color: #1565c0; color: white;}
    div[data-testid="stMetric"] {background-color: #f1f5f9; border-radius: 8px; padding: 10px; border: 1px solid #cbd5e1;}
</style>
""", unsafe_allow_html=True)

# --- 3. Autenticação ---
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    with st.sidebar:
        api_key = st.text_input("Chave API", type="password")

# --- 4. Interface ---
st.title("Sistema de Devolução (Versão PRO)")
st.markdown("Use esta versão para etiquetas difíceis, sujas ou com manuscritos complexos.")

if not api_key:
    st.error("⚠️ Configure a Chave de API para começar.")
    st.stop()

c1, c2 = st.columns(2)
with c1:
    st.markdown("### 1. Base SAP (Excel/CSV)")
    file_sap = st.file_uploader("Carregar Tabela", type=['xlsx', 'xls', 'csv'])
with c2:
    st.markdown("### 2. Fotos das Etiquetas")
    uploaded_images = st.file_uploader("Carregar Imagens", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

# --- 5. Lógica ---
def carregar_sap(file):
    try:
        if file.name.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        return df[['Produto', 'Peso por Metro']]
    except: return None

def regra_arredondamento(mm):
    try:
        val = int(float(mm))
        return (val // 500) * 500
    except: return 0

# --- 6. Processamento ---
if st.button("INICIAR LEITURA INTELIGENTE"):
    if not file_sap or not uploaded_images:
        st.warning("Carregue os arquivos primeiro.")
        st.stop()

    with st.status("Processando com Inteligência Avançada...", expanded=True) as status:
        st.write("📂 Lendo SAP...")
        df_sap = carregar_sap(file_sap)
        
        # MUDANÇA PRINCIPAL: Usando o modelo PRO (Mais inteligente)
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-pro') 
        
        dados = []
        bar = st.progress(0)

        for i, img_file in enumerate(uploaded_images):
            try:
                img = PIL.Image.open(img_file)
                
                # Prompt Reforçado para Manuscritos
                prompt = """
                Analise esta imagem industrial. Extraia os dados em JSON.
                Atenção: A etiqueta pode estar suja.
                
                1. "Reserva": Procure por números escritos à MÃO (CANETA/MARCADOR/GIZ). Eles podem estar grandes, rabiscados ou fora da etiqueta branca.
                2. "Descrição Material": Ex: L 90 X 6...
                3. "Código Material": Código numérico (Ex: 11000...).
                4. "Quantidade": Inteiro.
                5. "Peso": Decimal.
                6. "Tamanho": Inteiro (mm).
                
                Retorne apenas o JSON.
                """
                
                res = model.generate_content([prompt, img])
                text = res.text.replace("```json", "").replace("```", "").strip()
                
                # Tenta corrigir JSON quebrado
                if "{" in text:
                    text = text[text.find("{"):text.rfind("}")+1]
                
                # Se for lista ou dict
                d = json.loads(text)
                if isinstance(d, dict): d = [d]
                
                for item in d:
                    item['Arquivo'] = img_file.name # Rastreio
                    dados.append(item)
                    
            except Exception as e:
                print(f"Erro imagem {i}: {e}")
            
            bar.progress((i+1)/len(uploaded_images))

        if dados:
            st.write("📐 Calculando...")
            df = pd.DataFrame(dados)
            
            # Limpeza
            for col in ['Código Material', 'Quantidade', 'Peso', 'Tamanho']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            if 'Código Material' in df.columns: df['Código Material'] = df['Código Material'].astype(int)

            # Cruzamento
            df_final = df.merge(df_sap, left_on='Código Material', right_on='Produto', how='left')
            df_final.rename(columns={'Peso por Metro': 'Peso SAP'}, inplace=True)
            
            # Cálculos
            df_final['Nova Dimensão (mm)'] = df_final['Tamanho'].apply(regra_arredondamento)
            df_final['Peso Calculado'] = (df_final['Nova Dimensão (mm)']/1000) * df_final['Peso SAP'] * df_final['Quantidade']
            df_final['Diferença'] = df_final['Peso'] - df_final['Peso Calculado']
            
            # Colunas finais
            cols = ['Reserva', 'Descrição Material', 'Código Material', 'Quantidade', 'Peso', 'Tamanho', 'Nova Dimensão (mm)', 'Peso Calculado', 'Diferença']
            for c in cols: 
                if c not in df_final.columns: df_final[c] = "-"
            
            status.update(label="Concluído!", state="complete", expanded=False)
            
            # Exibição
            st.metric("Itens Processados", len(df_final))
            st.dataframe(df_final[cols], use_container_width=True)
            
            # Download
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False)
            
            st.download_button("📥 Baixar Excel", buffer.getvalue(), "Relatorio_Devolucao.xlsx")
            
        else:
            st.error("Não foi possível ler os dados. Tente novamente.")
