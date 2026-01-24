import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import io
import json

# --- Configurações da Página ---
st.set_page_config(page_title="Sistema Brametal - Leitura de Etiquetas", layout="wide", page_icon="🏭")

# --- CSS para deixar bonito (Estilo App) ---
st.markdown("""
<style>
    .main {background-color: #f5f5f5;}
    h1 {color: #1E3A8A;}
    .stButton>button {width: 100%; border-radius: 5px; height: 3em; background-color: #1E3A8A; color: white;}
</style>
""", unsafe_allow_html=True)

st.title("🏭 Sistema de Devolução - Brametal")
st.markdown("Faça upload da **Tabela de Pesos** e das **Fotos das Etiquetas** para gerar o relatório final.")

# --- Barra Lateral (Configurações) ---
with st.sidebar:
    st.header("🔐 Acesso")
    api_key = st.text_input("Chave da API (Gemini)", type="password")
    st.info("Insira a chave da API para processar as imagens.")

# --- Lógica Principal ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Base de Dados")
    file_pesos = st.file_uploader("📂 Carregar Tabela de Pesos (Excel)", type=['xlsx', 'xls'])

with col2:
    st.subheader("2. Imagens")
    uploaded_files = st.file_uploader("📷 Carregar Fotos das Etiquetas", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

# Função para buscar peso no Excel do usuário
def buscar_peso_referencia(descricao_extraida, df_ref):
    if df_ref is None:
        return 0.0
    
    # Normalizar texto para facilitar a busca (maiúsculas e sem espaços extras)
    desc_busca = str(descricao_extraida).upper().strip()
    
    # Tenta encontrar uma correspondência parcial ou exata
    # Assume que a planilha tem colunas 'Descrição' e 'Peso/m' (ou similar)
    # Vamos tentar identificar as colunas automaticamente
    col_desc = None
    col_peso = None
    
    for col in df_ref.columns:
        if 'desc' in col.lower() or 'material' in col.lower():
            col_desc = col
        if 'peso' in col.lower() or 'kg' in col.lower():
            col_peso = col
            
    if col_desc and col_peso:
        for index, row in df_ref.iterrows():
            # Verifica se a descrição do excel está contida na etiqueta ou vice-versa
            val_ref = str(row[col_desc]).upper().strip()
            if val_ref in desc_busca or desc_busca in val_ref:
                return float(row[col_peso])
    
    return 0.0 # Se não achar

# Função de Arredondamento (Regra de Negócio)
def calcular_nova_dimensao(tamanho_mm):
    try:
        val = int(float(tamanho_mm))
        return (val // 500) * 500
    except:
        return 0

if st.button("🚀 PROCESSAR DADOS"):
    if not api_key:
        st.warning("⚠️ Por favor, insira a Chave da API na barra lateral.")
    elif not uploaded_files:
        st.warning("⚠️ Carregue pelo menos uma foto.")
    elif not file_pesos:
        st.warning("⚠️ Carregue a Tabela de Pesos para fazer os cálculos.")
    else:
        # Carregar Tabela de Referência
        try:
            df_pesos = pd.read_excel(file_pesos)
            st.toast("Tabela de pesos carregada com sucesso!", icon="✅")
        except Exception as e:
            st.error(f"Erro ao ler tabela de pesos: {e}")
            st.stop()

        # Configurar Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        dados_finais = []
        bar = st.progress(0)
        status = st.empty()

        for i, file in enumerate(uploaded_files):
            status.text(f"Analisando imagem {i+1}/{len(uploaded_files)}: {file.name}")
            try:
                img = PIL.Image.open(file)
                prompt = """
                Analise a etiqueta. Extraia EXATAMENTE:
                1. 'Reserva': Número manuscrito a caneta.
                2. 'Descrição Material': Texto descritivo (ex: L 90 X 6...).
                3. 'Código Material': Código numérico.
                4. 'Quantidade': Qtd de peças.
                5. 'Peso': Peso líquido (apenas números).
                6. 'Tamanho': Dimensão em mm.
                Retorne JSON.
                """
                res = model.generate_content([prompt, img])
                text_json = res.text.replace("```json", "").replace("```", "").strip()
                
                # Tratamento de erro do JSON
                if text_json.startswith("[") and text_json.endswith("]"):
                    data_list = json.loads(text_json)
                else:
                    data_list = [json.loads(text_json)]

                for item in data_list:
                    # Cálculos Cruzados
                    desc = item.get('Descrição Material', '')
                    tam = item.get('Tamanho', 0)
                    qtd = item.get('Quantidade', 1)
                    peso_etiqueta = float(str(item.get('Peso', 0)).replace(',', '.'))
                    
                    # 1. Busca Peso Padrão na Planilha do Usuário
                    peso_metro_padrao = buscar_peso_referencia(desc, df_pesos)
                    
                    # 2. Cálculos
                    nova_dim = calcular_nova_dimensao(tam)
                    peso_real_calc = (nova_dim / 1000) * peso_metro_padrao * int(qtd)
                    diferenca = peso_etiqueta - peso_real_calc

                    dados_finais.append({
                        "Reserva (Caneta)": item.get('Reserva', ''),
                        "Descrição": desc,
                        "Código": item.get('Código Material', ''),
                        "Qtd": qtd,
                        "Peso Etiqueta": peso_etiqueta,
                        "Tamanho Original (mm)": tam,
                        "Peso Padrão (kg/m)": peso_metro_padrao,
                        "Nova Dimensão (mm)": nova_dim,
                        "Peso Recalculado": round(peso_real_calc, 3),
                        "Diferença (Sucata)": round(diferenca, 3)
                    })

            except Exception as e:
                st.error(f"Falha na imagem {file.name}")
            
            bar.progress((i+1)/len(uploaded_files))

        if dados_finais:
            df_export = pd.DataFrame(dados_finais)
            st.success("Processamento Concluído!")
            
            st.dataframe(df_export)
            
            # Botão Download
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False)
                
            st.download_button(
                label="📥 BAIXAR PLANILHA PRONTA",
                data=buffer.getvalue(),
                file_name="Relatorio_Brametal_Final.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
