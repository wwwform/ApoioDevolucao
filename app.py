import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import io
import json

# --- 1. Configuração da Página (Clean & Wide) ---
st.set_page_config(
    page_title="Sistema de Devolução",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed" # Barra lateral escondida para focar no conteúdo
)

# --- 2. CSS Minimalista (Estilo Profissional) ---
st.markdown("""
<style>
    /* Remover padding excessivo do topo */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Títulos */
    h1 {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        color: #1a1a1a;
        font-weight: 600;
        font-size: 2.2rem;
    }
    
    /* Uploaders mais bonitos */
    .stFileUploader {
        border: 1px dashed #d1d5db;
        border-radius: 8px;
        padding: 1rem;
        transition: border 0.3s;
    }
    .stFileUploader:hover {
        border-color: #2563eb;
    }
    
    /* Botão Principal - Azul Corporativo */
    .stButton>button {
        background-color: #2563eb;
        color: white;
        border-radius: 6px;
        font-weight: 500;
        height: 3rem;
        width: 100%;
        border: none;
    }
    .stButton>button:hover {
        background-color: #1d4ed8;
        color: white;
    }
    
    /* Métricas Limpas */
    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. Lógica da API Key ---
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    # Se não tiver configurado no servidor, pede na sidebar
    with st.sidebar:
        api_key = st.text_input("Chave de API", type="password")

# --- 4. Interface Principal ---

# Cabeçalho Limpo
c1, c2 = st.columns([3, 1])
with c1:
    st.title("Sistema de Devolução")
    st.markdown("Extração automática de etiquetas e conferência com SAP.")

if not api_key:
    st.warning("⚠️ Configure a Chave de API no menu lateral ou nos Secrets para começar.")
    st.stop()

st.markdown("---")

# Área de Upload (Lado a Lado)
col_sap, col_img = st.columns(2)

with col_sap:
    st.markdown("### 1. Planilha SAP")
    file_sap = st.file_uploader("Carregar Excel (.xlsx / .csv)", type=['xlsx', 'xls', 'csv'])

with col_img:
    st.markdown("### 2. Fotos das Etiquetas")
    uploaded_images = st.file_uploader("Carregar Fotos", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

# --- 5. Funções de Processamento ---

def carregar_sap(file):
    try:
        if file.name.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        # Garante tipos corretos
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        return df[['Produto', 'Peso por Metro']]
    except:
        return None

def regra_arredondamento(mm):
    try:
        val = int(float(mm))
        # Regra: Múltiplos de 500mm para baixo
        return (val // 500) * 500
    except:
        return 0

# --- 6. Botão de Ação ---
st.markdown("###")
btn_processar = st.button("INICIAR CONFERÊNCIA")

if btn_processar:
    if not file_sap or not uploaded_images:
        st.error("Por favor, carregue ambos os arquivos acima.")
        st.stop()

    # Layout de Carregamento
    status_container = st.container()
    
    with status_container:
        with st.status("Processando...", expanded=True) as status:
            
            # 1. Carregar SAP
            st.write("📂 Lendo base de dados...")
            df_sap = carregar_sap(file_sap)
            if df_sap is None:
                st.error("Erro na planilha SAP. Verifique se tem as colunas 'Produto' e 'Peso por Metro'.")
                st.stop()

            # 2. Configurar IA
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            dados_brutos = []
            progresso = st.progress(0)
            
            # 3. Loop Imagens
            for i, img_file in enumerate(uploaded_images):
                try:
                    img = PIL.Image.open(img_file)
                    
                    # PROMPT MELHORADO PARA SUJEIRA E MANUSCRITO
                    prompt = """
                    Atue como um especialista em OCR industrial. Analise esta imagem de etiqueta de aço (Brametal).
                    A etiqueta pode estar suja, rasgada ou com anotações manuais.
                    
                    Sua missão é extrair um JSON com estes campos exatos:
                    - "Reserva": O número escrito à MÃO (caneta/marcador). Geralmente fora da etiqueta ou rabiscado nela. Se não achar, deixe vazio.
                    - "Descrição Material": Texto descritivo (Ex: L 90 X 6...).
                    - "Código Material": Código numérico longo (Ex: 110000...).
                    - "Quantidade": Inteiro.
                    - "Peso": Decimal (ponto).
                    - "Tamanho": Inteiro em mm.
                    
                    Se a imagem estiver muito ruim, faça o seu melhor palpite baseado no contexto visual.
                    Retorne APENAS o JSON. Sem markdown.
                    """
                    
                    res = model.generate_content([prompt, img])
                    text = res.text.replace("```json", "").replace("```", "").strip()
                    
                    # Limpeza extra para garantir JSON válido
                    if "{" in text:
                        start = text.find("{")
                        end = text.rfind("}") + 1
                        json_str = text[start:end]
                        data = json.loads(json_str)
                        dados_brutos.append(data)
                        
                except Exception as e:
                    # Falha silenciosa para não travar tudo, mas registra erro no log se precisar
                    print(f"Erro na imagem {img_file.name}: {e}")
                
                progresso.progress((i + 1) / len(uploaded_images))
            
            st.write("⚙️ Cruzando dados e calculando...")
            
            if dados_brutos:
                df = pd.DataFrame(dados_brutos)
                
                # Tratamento de Nulos/Erros de Tipo
                cols_num = ['Código Material', 'Quantidade', 'Peso', 'Tamanho']
                for c in cols_num:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
                
                # Conversão para Inteiros onde necessário
                if 'Código Material' in df.columns: df['Código Material'] = df['Código Material'].astype(int)
                if 'Quantidade' in df.columns: df['Quantidade'] = df['Quantidade'].astype(int)
                if 'Tamanho' in df.columns: df['Tamanho'] = df['Tamanho'].astype(int)

                # Cruzamento com SAP
                df_final = df.merge(df_sap, left_on='Código Material', right_on='Produto', how='left')
                df_final.rename(columns={'Peso por Metro': 'Peso SAP (kg/m)'}, inplace=True)
                df_final['Peso SAP (kg/m)'] = df_final['Peso SAP (kg/m)'].fillna(0.0)

                # Cálculos Finais
                df_final['Nova Dimensão (mm)'] = df_final['Tamanho'].apply(regra_arredondamento)
                
                # Fórmula: (Nova Dimensão mm / 1000) * Peso SAP * Qtd
                df_final['Peso Calculado'] = (df_final['Nova Dimensão (mm)'] / 1000.0) * df_final['Peso SAP (kg/m)'] * df_final['Quantidade']
                
                if 'Peso' in df_final.columns:
                    df_final['Diferença (Sucata)'] = df_final['Peso'] - df_final['Peso Calculado']
                else:
                    df_final['Diferença (Sucata)'] = 0.0

                # Organizar Colunas
                cols_order = [
                    'Reserva', 'Descrição Material', 'Código Material', 'Quantidade', 
                    'Peso', 'Tamanho', 'Peso SAP (kg/m)', 
                    'Nova Dimensão (mm)', 'Peso Calculado', 'Diferença (Sucata)'
                ]
                
                # Garante que todas colunas existem
                for c in cols_order:
                    if c not in df_final.columns: df_final[c] = 0
                
                df_final = df_final[cols_order]

                status.update(label="Concluído!", state="complete", expanded=False)
                
                # --- RESULTADOS ---
                st.markdown("### Resultados")
                
                # Cards de Resumo
                m1, m2, m3 = st.columns(3)
                m1.metric("Itens Lidos", len(df_final))
                m2.metric("Peso Total (Etiqueta)", f"{df_final['Peso'].sum():.2f} kg")
                
                delta_val = df_final['Diferença (Sucata)'].sum()
                m3.metric("Total Sucata", f"{delta_val:.2f} kg", delta_color="off")

                # Tabela Interativa (Data Editor é mais bonito que Dataframe)
                st.data_editor(
                    df_final,
                    column_config={
                        "Peso": st.column_config.NumberColumn(format="%.2f kg"),
                        "Peso Calculado": st.column_config.NumberColumn(format="%.2f kg"),
                        "Diferença (Sucata)": st.column_config.NumberColumn(format="%.2f kg"),
                        "Peso SAP (kg/m)": st.column_config.NumberColumn(format="%.2f"),
                    },
                    use_container_width=True,
                    hide_index=True
                )

                # Download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 Baixar Excel Final",
                    data=buffer.getvalue(),
                    file_name="Relatorio_Devolucao.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            else:
                st.error("Não foi possível extrair dados. Tente fotos mais próximas ou verifique a API Key.")
