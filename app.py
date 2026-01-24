import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import io
import json

# --- Configurações da Página ---
st.set_page_config(
    page_title="Sistema Brametal - Devolução",
    page_icon="🏭",
    layout="wide"
)

# --- Estilização CSS ---
st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    h1 {color: #0d47a1;}
    .stButton>button {
        width: 100%;
        background-color: #1565c0;
        color: white;
        font-weight: bold;
        padding: 0.5rem;
    }
    .stButton>button:hover {
        background-color: #0d47a1;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏭 Sistema de Devolução e Controle de Sucata")
st.markdown("---")

# --- 1. Configuração da API Key (Segurança) ---
# Tenta pegar dos segredos (Servidor). Se não achar, pede manual (Local/Teste).
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    # Mostra um indicador visual discreto que a chave está carregada
    with st.sidebar:
        st.success("✅ Licença do Sistema Ativa")
else:
    with st.sidebar:
        st.warning("Modo de Desenvolvedor")
        api_key = st.text_input("Insira a Chave da API (Gemini)", type="password")

# --- 2. Interface de Upload ---
col1, col2 = st.columns(2)

with col1:
    st.info("📂 **Passo 1: Base de Dados**")
    file_sap = st.file_uploader(
        "Carregue a planilha 'PESO TEÓRICO - SAP'", 
        type=['xlsx', 'xls', 'csv'],
        help="A planilha deve conter as colunas 'Produto' e 'Peso por Metro'."
    )

with col2:
    st.info("📷 **Passo 2: Fotos das Etiquetas**")
    uploaded_images = st.file_uploader(
        "Carregue as fotos das etiquetas", 
        type=['png', 'jpg', 'jpeg'], 
        accept_multiple_files=True
    )

# --- 3. Funções Auxiliares ---

def carregar_dados_sap(file):
    """Lê o arquivo SAP e prepara para o cruzamento"""
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Limpeza básica nos nomes das colunas (remove espaços extras)
        df.columns = df.columns.str.strip()
        
        # Verifica se as colunas necessárias existem
        colunas_necessarias = ['Produto', 'Peso por Metro']
        if not all(col in df.columns for col in colunas_necessarias):
            st.error(f"A planilha SAP precisa ter as colunas: {colunas_necessarias}")
            return None
        
        # Garante que 'Produto' seja do mesmo tipo (inteiro) para cruzar depois
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        
        # Retorna apenas o que interessa para ficar leve
        return df[['Produto', 'Peso por Metro']]
    except Exception as e:
        st.error(f"Erro ao ler planilha SAP: {e}")
        return None

def calcular_nova_dimensao(tamanho_mm):
    """Regra de Negócio: Arredonda para baixo em múltiplos de 500mm"""
    try:
        val = int(float(tamanho_mm))
        # Ex: 1227 -> 1000 | 2622 -> 2500
        return (val // 500) * 500
    except:
        return 0

# --- 4. Processamento Principal ---

if st.button("🚀 PROCESSAR ETIQUETAS"):
    # Validações iniciais
    if not api_key:
        st.error("❌ Erro: Chave de API não configurada.")
        st.stop()
    
    if not file_sap:
        st.warning("⚠️ Por favor, carregue a planilha do SAP (Passo 1).")
        st.stop()
        
    if not uploaded_images:
        st.warning("⚠️ Por favor, carregue as fotos (Passo 2).")
        st.stop()

    # Carrega SAP
    df_sap = carregar_dados_sap(file_sap)
    if df_sap is None:
        st.stop()

    # Configura Gemini
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    # Barra de progresso
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    dados_extraidos = []

    # Loop pelas imagens
    for index, img_file in enumerate(uploaded_images):
        status_text.text(f"Analisando imagem {index + 1} de {len(uploaded_images)}...")
        
        try:
            image = PIL.Image.open(img_file)
            
            prompt = """
            Você é um assistente industrial. Analise esta etiqueta de aço.
            Extraia os dados no formato JSON estrito (sem markdown).
            Campos obrigatórios:
            - 'Reserva': Número escrito à mão com caneta (azul/preta). Se não houver, deixe vazio.
            - 'Descrição Material': Texto descritivo (ex: L 90 X 6...).
            - 'Código Material': O código numérico do produto (geralmente começa com 11...).
            - 'Quantidade': Número de peças (padrão é 1 se não estiver explícito).
            - 'Peso': Peso líquido (apenas números, use ponto para decimais).
            - 'Tamanho': Dimensão/Comprimento em mm (apenas números inteiros).
            
            Se a imagem tiver mais de uma etiqueta legível, retorne uma lista de objetos.
            """
            
            response = model.generate_content([prompt, image])
            
            # Limpeza do JSON
            txt_response = response.text.replace("```json", "").replace("```", "").strip()
            
            try:
                data = json.loads(txt_response)
                if isinstance(data, dict):
                    data = [data] # Transforma em lista se for um único objeto
                
                for item in data:
                    dados_extraidos.append(item)
                    
            except json.JSONDecodeError:
                st.warning(f"Não foi possível ler dados da imagem: {img_file.name}")
                
        except Exception as e:
            st.error(f"Erro ao processar imagem {img_file.name}: {e}")
        
        # Atualiza barra
        progress_bar.progress((index + 1) / len(uploaded_images))

    # --- 5. Cruzamento e Cálculos Finais ---
    if dados_extraidos:
        status_text.text("Realizando cálculos e cruzamento com SAP...")
        
        # Cria DataFrame com dados das imagens
        df_etiquetas = pd.DataFrame(dados_extraidos)
        
        # Tratamento de Tipos para evitar erros no Excel
        df_etiquetas['Código Material'] = pd.to_numeric(df_etiquetas['Código Material'], errors='coerce').fillna(0).astype(int)
        df_etiquetas['Quantidade'] = pd.to_numeric(df_etiquetas['Quantidade'], errors='coerce').fillna(1).astype(int)
        df_etiquetas['Peso'] = pd.to_numeric(df_etiquetas['Peso'], errors='coerce').fillna(0.0)
        df_etiquetas['Tamanho'] = pd.to_numeric(df_etiquetas['Tamanho'], errors='coerce').fillna(0).astype(int)

        # CRUZAMENTO (VLOOKUP) com a planilha SAP
        # Junta a tabela das imagens com a tabela SAP usando o código do material
        df_final = df_etiquetas.merge(
            df_sap, 
            left_on='Código Material', 
            right_on='Produto', 
            how='left'
        )
        
        # Renomeia coluna que veio do SAP
        df_final.rename(columns={'Peso por Metro': 'Peso Padrão (SAP)'}, inplace=True)
        
        # Se não achou o produto no SAP, preenche com 0 para não quebrar conta
        df_final['Peso Padrão (SAP)'] = df_final['Peso Padrão (SAP)'].fillna(0.0)

        # --- CÁLCULOS ---
        # 1. Metragem Original
        df_final['Metragem'] = df_final['Tamanho'] / 1000.0
        
        # 2. Nova Dimensão (Regra 500mm)
        df_final['Nova Dimensão (mm)'] = df_final['Tamanho'].apply(calcular_nova_dimensao)
        
        # 3. Nova Dimensão em Metros
        df_final['Nova dimensão (m)'] = df_final['Nova Dimensão (mm)'] / 1000.0
        
        # 4. Peso Real (Fórmula: Metros * Peso SAP * Qtd)
        df_final['Peso Real Nova Dimensão'] = (
            df_final['Nova dimensão (m)'] * df_final['Peso Padrão (SAP)'] * df_final['Quantidade']
        )
        
        # 5. Diferença (Sucata)
        df_final['Diferença (Peso Etiqueta - Peso Novo)'] = df_final['Peso'] - df_final['Peso Real Nova Dimensão']

        # Seleção e Ordem das Colunas Finais
        colunas_exibicao = [
            'Reserva', 'Descrição Material', 'Código Material', 'Quantidade',
            'Peso', 'Tamanho', 'Peso Padrão (SAP)', 'Metragem',
            'Nova Dimensão (mm)', 'Nova dimensão (m)', 
            'Peso Real Nova Dimensão', 'Diferença (Peso Etiqueta - Peso Novo)'
        ]
        
        # Garante que colunas existem (caso o Gemini não tenha retornado 'Reserva' por exemplo)
        for col in colunas_exibicao:
            if col not in df_final.columns:
                df_final[col] = ""
                
        df_final = df_final[colunas_exibicao]

        # --- Resultado na Tela ---
        st.success("✅ Processamento Concluído com Sucesso!")
        st.dataframe(df_final.style.format({
            "Peso": "{:.3f}",
            "Peso Padrão (SAP)": "{:.2f}",
            "Peso Real Nova Dimensão": "{:.3f}",
            "Diferença (Peso Etiqueta - Peso Novo)": "{:.3f}"
        }))

        # --- Botão de Download ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False)
            
        st.download_button(
            label="📥 BAIXAR RELATÓRIO FINAL (EXCEL)",
            data=buffer.getvalue(),
            file_name="Relatorio_Controle_Sucata.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    else:
        st.error("Não foi possível extrair dados das imagens fornecidas.")
