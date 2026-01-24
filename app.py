import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import io
import json
import time

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Sistema de Devolução | Brametal",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. ESTILIZAÇÃO (CSS) ---
st.markdown("""
<style>
    /* Fundo e Fontes */
    .stApp {
        background-color: #f8fafc;
    }
    h1, h2, h3 {
        color: #0f172a;
        font-family: 'Segoe UI', sans-serif;
    }
    
    /* Uploaders */
    .stFileUploader {
        background-color: white;
        border: 1px dashed #cbd5e1;
        border-radius: 8px;
        padding: 15px;
    }
    
    /* Botão Principal */
    .stButton>button {
        background-color: #2563eb;
        color: white;
        font-weight: 600;
        border-radius: 6px;
        height: 3.5rem;
        width: 100%;
        border: none;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        background-color: #1d4ed8;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        color: white;
    }
    
    /* Métricas */
    div[data-testid="stMetric"] {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    }
</style>
""", unsafe_allow_html=True)

# --- 3. AUTENTICAÇÃO E SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Verifica se a chave está nos segredos do servidor
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ Licença Ativa (Server)")
    else:
        # Fallback para teste local
        api_key = st.text_input("Chave API (Gemini)", type="password")
        if not api_key:
            st.warning("Insira a chave para continuar.")

    st.markdown("---")
    st.markdown("### 📝 Instruções")
    st.info(
        "1. Carregue a **Planilha SAP**.\n"
        "2. Carregue as **Fotos**.\n"
        "3. Clique em **Iniciar Processamento**."
    )
    st.caption("Versão 4.0 (Pro Vision)")

# --- 4. INTERFACE PRINCIPAL ---

st.title("🏗️ Sistema de Devolução e Sucata")
st.markdown("Extração inteligente de dados de etiquetas e cruzamento automático com base SAP.")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Base de Dados (SAP)")
    file_sap = st.file_uploader(
        "Arraste a planilha de pesos aqui", 
        type=['xlsx', 'xls', 'csv'],
        key="sap"
    )

with col2:
    st.subheader("2. Fotos das Etiquetas")
    uploaded_images = st.file_uploader(
        "Selecione as fotos (múltiplos arquivos)", 
        type=['png', 'jpg', 'jpeg'], 
        accept_multiple_files=True,
        key="imgs"
    )

# --- 5. FUNÇÕES DE NEGÓCIO ---

def carregar_sap_e_limpar(file):
    """Carrega o Excel SAP e retorna apenas colunas úteis"""
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Remove espaços em branco dos nomes das colunas
        df.columns = df.columns.str.strip()
        
        # Validação de colunas
        cols_necessarias = ['Produto', 'Peso por Metro']
        if not all(col in df.columns for col in cols_necessarias):
            st.error(f"A planilha deve conter as colunas: {cols_necessarias}")
            return None
            
        # Garante tipo inteiro para cruzamento
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        
        return df[['Produto', 'Peso por Metro']]
    except Exception as e:
        st.error(f"Erro ao ler arquivo SAP: {str(e)}")
        return None

def calcular_arredondamento_500mm(tamanho_mm):
    """Regra: Arredonda para baixo no múltiplo de 500mm mais próximo"""
    try:
        val = int(float(tamanho_mm))
        return (val // 500) * 500
    except:
        return 0

# --- 6. PROCESSAMENTO ---

st.markdown("###")
btn_processar = st.button("🚀 INICIAR PROCESSAMENTO INTELIGENTE")

if btn_processar:
    # Validações Iniciais
    if not api_key:
        st.error("❌ Chave de API não encontrada.")
        st.stop()
    
    if not file_sap or not uploaded_images:
        st.warning("⚠️ Por favor, carregue a planilha SAP e as Imagens antes de processar.")
        st.stop()

    # Início do Fluxo
    status_container = st.container()
    
    with status_container:
        with st.status("🤖 Iniciando motor de IA...", expanded=True) as status:
            
            # 1. Carregar SAP
            st.write("📂 Lendo e validando planilha SAP...")
            df_sap = carregar_sap_e_limpar(file_sap)
            if df_sap is None:
                status.update(label="Falha na leitura do SAP", state="error")
                st.stop()
            
            # 2. Configurar Gemini (Modelo PRO para melhor leitura)
            st.write("🧠 Configurando visão computacional (Modelo PRO)...")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-pro')
            
            dados_extraidos = []
            progress_bar = st.progress(0)
            
            # 3. Loop pelas Imagens
            total_imgs = len(uploaded_images)
            for index, img_file in enumerate(uploaded_images):
                st.write(f"👁️ Analisando imagem {index+1}/{total_imgs}: {img_file.name}...")
                try:
                    image = PIL.Image.open(img_file)
                    
                    # Prompt "Agressivo" para manuscritos e sujeira
                    prompt = """
                    Atue como um especialista em OCR industrial. Analise esta etiqueta de aço.
                    Atenção: A etiqueta pode estar suja, rasgada ou com anotações manuais fora da área impressa.
                    
                    Extraia um JSON estrito com os campos:
                    1. "Reserva": O número escrito à MÃO (caneta/marcador). Pode estar rabiscado. Se não houver, deixe vazio.
                    2. "Descrição Material": O texto descritivo (Ex: L 90 X 6...).
                    3. "Código Material": O código numérico (Ex: 11000...).
                    4. "Quantidade": Inteiro. Se não explícito, assuma 1.
                    5. "Peso": Decimal (ponto).
                    6. "Tamanho": Inteiro em milímetros (mm).
                    
                    Se a imagem estiver ruim, use inferência lógica. Retorne APENAS o JSON.
                    """
                    
                    response = model.generate_content([prompt, image])
                    text_response = response.text.replace("```json", "").replace("```", "").strip()
                    
                    # Limpeza de JSON (busca o primeiro { e o último })
                    if "{" in text_response:
                        json_str = text_response[text_response.find("{"):text_response.rfind("}")+1]
                        data = json.loads(json_str)
                        
                        # Normaliza para lista se vier um único objeto
                        if isinstance(data, dict):
                            data = [data]
                            
                        for item in data:
                            # Adiciona metadados
                            item['Arquivo Origem'] = img_file.name
                            dados_extraidos.append(item)
                    
                except Exception as e:
                    print(f"Erro silencioso na imagem {img_file.name}: {e}")
                
                # Atualiza barra
                progress_bar.progress((index + 1) / total_imgs)

            # 4. Cálculos e Cruzamento
            if dados_extraidos:
                st.write("📐 Realizando cálculos de engenharia...")
                df_etiquetas = pd.DataFrame(dados_extraidos)
                
                # Tratamento de Tipos
                cols_numericas = ['Código Material', 'Quantidade', 'Peso', 'Tamanho']
                for col in cols_numericas:
                    if col in df_etiquetas.columns:
                        df_etiquetas[col] = pd.to_numeric(df_etiquetas[col], errors='coerce').fillna(0)
                
                # Conversão para Int onde cabe
                if 'Código Material' in df_etiquetas.columns:
                    df_etiquetas['Código Material'] = df_etiquetas['Código Material'].astype(int)
                if 'Quantidade' in df_etiquetas.columns:
                    df_etiquetas['Quantidade'] = df_etiquetas['Quantidade'].astype(int)

                # Merge (Cruzamento)
                df_final = df_etiquetas.merge(
                    df_sap, 
                    left_on='Código Material', 
                    right_on='Produto', 
                    how='left'
                )
                
                # Renomeia e Preenche Nulos
                df_final.rename(columns={'Peso por Metro': 'Peso Padrão (SAP)'}, inplace=True)
                df_final['Peso Padrão (SAP)'] = df_final['Peso Padrão (SAP)'].fillna(0.0)
                
                # Cálculos Finais (Regras de Negócio)
                df_final['Nova Dimensão (mm)'] = df_final['Tamanho'].apply(calcular_arredondamento_500mm)
                
                # Peso Calc = (Nova Dim / 1000) * Peso SAP * Qtd
                df_final['Peso Calculado'] = (
                    (df_final['Nova Dimensão (mm)'] / 1000.0) * df_final['Peso Padrão (SAP)'] * df_final['Quantidade']
                )
                
                # Diferença (Sucata)
                if 'Peso' in df_final.columns:
                    df_final['Diferença (Sucata)'] = df_final['Peso'] - df_final['Peso Calculado']
                else:
                    df_final['Diferença (Sucata)'] = 0.0

                # Organização das Colunas
                colunas_finais = [
                    'Reserva', 'Descrição Material', 'Código Material', 
                    'Quantidade', 'Peso', 'Tamanho', 
                    'Nova Dimensão (mm)', 'Peso Padrão (SAP)', 
                    'Peso Calculado', 'Diferença (Sucata)'
                ]
                
                # Garante que colunas existem
                for col in colunas_finais:
                    if col not in df_final.columns:
                        df_final[col] = "-"
                
                df_display = df_final[colunas_finais]

                status.update(label="Processamento Concluído com Sucesso!", state="complete", expanded=False)
                
                # --- RESULTADOS VISUAIS ---
                st.markdown("### 📊 Relatório Final")
                
                # Cards de Resumo
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Etiquetas Lidas", len(df_display))
                m2.metric("Peso Original", f"{df_display['Peso'].sum():.2f} kg")
                m3.metric("Peso Calculado", f"{df_display['Peso Calculado'].sum():.2f} kg")
                
                total_sucata = df_display['Diferença (Sucata)'].sum()
                m4.metric("Diferença (Sucata)", f"{total_sucata:.2f} kg", delta_color="inverse")
                
                # Tabela Interativa
                st.data_editor(
                    df_display,
                    column_config={
                        "Peso": st.column_config.NumberColumn(format="%.2f kg"),
                        "Peso Calculado": st.column_config.NumberColumn(format="%.2f kg"),
                        "Diferença (Sucata)": st.column_config.NumberColumn(format="%.2f kg"),
                    },
                    use_container_width=True,
                    height=400
                )
                
                # Botão Download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_display.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 BAIXAR RELATÓRIO (EXCEL)",
                    data=buffer.getvalue(),
                    file_name="Relatorio_Brametal_Final.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )

            else:
                st.error("Não foi possível extrair dados das imagens. Tente novamente com fotos mais nítidas.")

    st.balloons()
