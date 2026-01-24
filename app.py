import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import io
import json

# --- Configuração da Página ---
st.set_page_config(
    page_title="Relatório de Devolução",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Barra Lateral de Controle ---
with st.sidebar:
    st.header("Parâmetros de Entrada")
    
    # 1. Autenticação
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    else:
        api_key = st.text_input("Chave de API", type="password")

    st.markdown("---")
    
    # 2. Uploads
    st.subheader("Arquivos")
    file_sap = st.file_uploader("1. Base SAP (.xlsx/.csv)", type=['xlsx', 'xls', 'csv'])
    uploaded_images = st.file_uploader("2. Fotos das Etiquetas", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    
    st.markdown("---")
    
    # 3. Botão de Execução
    btn_processar = st.button("Gerar Relatório", type="primary", use_container_width=True)

# --- Funções do Sistema ---

def limpar_json(texto):
    """Limpa a resposta da IA para garantir um JSON válido."""
    texto = texto.replace("```json", "").replace("```", "").strip()
    # Tenta encontrar o início e fim da lista ou objeto
    if "{" in texto:
        inicio = texto.find("{")
        fim = texto.rfind("}") + 1
        return texto[inicio:fim]
    return texto

def carregar_base_sap(arquivo):
    try:
        if arquivo.name.endswith('.csv'):
            df = pd.read_csv(arquivo)
        else:
            df = pd.read_excel(arquivo)
        
        # Padronização de colunas
        df.columns = df.columns.str.strip()
        
        # Validação mínima
        colunas_esperadas = ['Produto', 'Peso por Metro']
        if not all(col in df.columns for col in colunas_esperadas):
            return None, f"Colunas obrigatórias ausentes. Necessário: {colunas_esperadas}"
            
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        return df[['Produto', 'Peso por Metro']], None
    except Exception as e:
        return None, str(e)

def calcular_dimensao_corte(valor_mm):
    """Aplica regra de corte: múltiplos de 500mm arredondados para baixo."""
    try:
        valor = int(float(valor_mm))
        return (valor // 500) * 500
    except:
        return 0

# --- Processamento Principal ---

st.title("Sistema de Controle de Devolução")

if btn_processar:
    if not api_key:
        st.error("Erro: Chave de API não configurada.")
        st.stop()
        
    if not file_sap or not uploaded_images:
        st.warning("Atenção: É necessário carregar a Base SAP e as Fotos para prosseguir.")
        st.stop()

    # Container de Status
    status_msg = st.empty()
    bar_progresso = st.progress(0)

    # 1. Carregamento SAP
    status_msg.text("Carregando base de dados SAP...")
    df_sap, erro_sap = carregar_base_sap(file_sap)
    
    if erro_sap:
        st.error(f"Erro na leitura do SAP: {erro_sap}")
        st.stop()

    # 2. Configuração AI
    genai.configure(api_key=api_key)
    # Modelo PRO é obrigatório para ler manuscritos difíceis
    model = genai.GenerativeModel('gemini-1.5-pro')
    
    dados_processados = []
    
    # 3. Loop de Processamento de Imagens
    total_imgs = len(uploaded_images)
    
    for i, img_file in enumerate(uploaded_images):
        status_msg.text(f"Processando item {i+1} de {total_imgs}: {img_file.name}")
        
        try:
            image = PIL.Image.open(img_file)
            
            # Prompt Técnico Específico para Etiquetas Brametal
            prompt = """
            Extraia os dados técnicos desta etiqueta industrial de aço.
            Saída obrigatória: Objeto JSON único.
            
            Campos a extrair:
            1. "Reserva": Número manuscrito (feito a caneta/marcador) sobre a peça ou etiqueta. Geralmente tem 7 dígitos (ex: 3800994, 3603907). Se ilegível, retorne "".
            2. "descricao": Texto exato abaixo de "Desc. Material" (ex: L 90 X 6 A572-GR60).
            3. "codigo": Número abaixo de "Cod. Material" (ex: 1100001788). Apenas números.
            4. "qtd": Número em "Quantidade".
            5. "peso": Número em "Peso". Use ponto para decimal.
            6. "tamanho": Número em "Dimensões" (mm). Apenas números inteiros.

            Se houver múltiplas etiquetas, foque na mais legível ou central.
            """
            
            response = model.generate_content([prompt, image])
            texto_json = limpar_json(response.text)
            
            dados_item = json.loads(texto_json)
            
            # Normalização de chaves para lista
            if isinstance(dados_item, dict):
                dados_processados.append(dados_item)
            elif isinstance(dados_item, list):
                dados_processados.extend(dados_item)
                
        except Exception as e:
            # Log de erro silencioso para não interromper o lote
            print(f"Falha na imagem {img_file.name}: {e}")
            
        # Atualiza barra
        bar_progresso.progress((i + 1) / total_imgs)

    status_msg.empty()
    bar_progresso.empty()

    # 4. Consolidação e Cálculos
    if dados_processados:
        df_resultado = pd.DataFrame(dados_processados)
        
        # Tratamento de Tipos
        cols_num = ['codigo', 'qtd', 'peso', 'tamanho']
        for c in cols_num:
            if c in df_resultado.columns:
                df_resultado[c] = pd.to_numeric(df_resultado[c], errors='coerce').fillna(0)
        
        if 'codigo' in df_resultado.columns:
            df_resultado['codigo'] = df_resultado['codigo'].astype(int)
        
        # Cruzamento (Merge) com SAP
        df_final = df_resultado.merge(
            df_sap, 
            left_on='codigo', 
            right_on='Produto', 
            how='left'
        )
        
        # Renomear colunas para padrão de saída
        df_final.rename(columns={
            'Reserva': 'Reserva (Caneta)',
            'descricao': 'Descrição Material',
            'codigo': 'Código Material',
            'qtd': 'Quantidade',
            'peso': 'Peso Etiqueta',
            'tamanho': 'Tamanho (mm)',
            'Peso por Metro': 'Peso Padrão (SAP)'
        }, inplace=True)
        
        # Preencher nulos do SAP com 0
        df_final['Peso Padrão (SAP)'] = df_final['Peso Padrão (SAP)'].fillna(0.0)
        
        # Cálculos de Engenharia
        df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(calcular_dimensao_corte)
        
        df_final['Peso Recalculado'] = (
            (df_final['Nova Dimensão (mm)'] / 1000.0) * df_final['Peso Padrão (SAP)'] * df_final['Quantidade']
        )
        
        df_final['Diferença (Sucata)'] = df_final['Peso Etiqueta'] - df_final['Peso Recalculado']
        
        # Seleção e Ordenação de Colunas
        colunas_finais = [
            'Reserva (Caneta)', 'Descrição Material', 'Código Material', 'Quantidade',
            'Peso Etiqueta', 'Tamanho (mm)', 'Nova Dimensão (mm)', 
            'Peso Padrão (SAP)', 'Peso Recalculado', 'Diferença (Sucata)'
        ]
        
        # Garante integridade das colunas
        for col in colunas_finais:
            if col not in df_final.columns:
                df_final[col] = 0
                
        df_apresentacao = df_final[colunas_finais]

        # --- Exibição de Resultados ---
        
        # Métricas Consolidadas
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Itens Processados", len(df_apresentacao))
        col_m2.metric("Peso Total (Etiqueta)", f"{df_apresentacao['Peso Etiqueta'].sum():.2f} kg")
        col_m3.metric("Total Sucata", f"{df_apresentacao['Diferença (Sucata)'].sum():.2f} kg")
        
        st.markdown("### Detalhamento")
        st.dataframe(
            df_apresentacao, 
            use_container_width=True,
            hide_index=True
        )
        
        # Exportação Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_apresentacao.to_excel(writer, index=False)
            
        st.download_button(
            label="Baixar Relatório Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name="Relatorio_Devolucao.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    else:
        st.error("Não foi possível extrair dados válidos das imagens fornecidas. Verifique a qualidade das fotos.")

else:
    st.info("Aguardando início do processamento...")
