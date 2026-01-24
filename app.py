import streamlit as st
import pandas as pd
import io

# --- 1. CONFIGURAÇÃO VISUAL (Clean) ---
st.set_page_config(page_title="Calculadora de Devolução", layout="wide")

st.markdown("""
<style>
    .stApp {background-color: #f8fafc;}
    h1 {color: #1e293b; font-family: 'Segoe UI', sans-serif;}
    .stButton>button {
        background-color: #15803d; /* Verde Excel */
        color: white; height: 3rem; width: 100%; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. BARRA LATERAL (Base de Dados) ---
with st.sidebar:
    st.header("📂 Base de Dados")
    file_sap = st.file_uploader("Carregue a tabela SAP (.xlsx)", type=['xlsx', 'xls', 'csv'])
    st.info("O sistema buscará a Descrição e o Peso Teórico automaticamente nesta planilha.")

# --- 3. FUNÇÕES DE CÁLCULO ---
def carregar_sap(file):
    try:
        if file.name.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)
        df.columns = df.columns.str.strip() # Limpa espaços nos nomes das colunas
        # Garante que o código é número inteiro para bater com a digitação
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        return df[['Produto', 'Descrição do produto', 'Peso por Metro']]
    except: return None

def regra_corte_500mm(valor):
    """Arredonda para baixo em múltiplos de 500"""
    try:
        return (int(float(valor)) // 500) * 500
    except: return 0

# --- 4. TELA PRINCIPAL ---
st.title("✍️ Calculadora de Devolução & Sucata")

if not file_sap:
    st.warning("⚠️ Passo 1: Carregue a planilha SAP na barra lateral para liberar o sistema.")
    st.stop()

# Carrega o banco de dados em memória
df_sap = carregar_sap(file_sap)

if df_sap is None:
    st.error("Erro na planilha SAP. Verifique as colunas 'Produto', 'Descrição do produto' e 'Peso por Metro'.")
    st.stop()

# --- 5. ÁREA DE DIGITAÇÃO ---
st.markdown("### Entrada de Dados")
st.caption("Digite apenas os dados variáveis. A Descrição e o Peso Teórico serão preenchidos automaticamente.")

# Cria uma tabela vazia inicial com as colunas que o usuário DEVE preencher
if 'dados_input' not in st.session_state:
    st.session_state.dados_input = pd.DataFrame(
        [{"Reserva": "", "Cód. SAP": None, "Qtd": 1, "Peso Etiqueta (kg)": 0.0, "Tamanho (mm)": 0}],
    )

# Tabela Editável (O Usuário digita aqui)
df_digitado = st.data_editor(
    st.session_state.dados_input,
    num_rows="dynamic", # Permite adicionar linhas infinitas
    use_container_width=True,
    column_config={
        "Reserva": st.column_config.TextColumn("Reserva (Caneta)", help="Número manuscrito"),
        "Cód. SAP": st.column_config.NumberColumn("Cód. Material (SAP)", format="%d", required=True),
        "Qtd": st.column_config.NumberColumn("Qtd Peças", min_value=1, step=1, required=True),
        "Peso Etiqueta (kg)": st.column_config.NumberColumn("Peso Balança/Etiqueta", min_value=0.0, format="%.2f", required=True),
        "Tamanho (mm)": st.column_config.NumberColumn("Tamanho Real (mm)", min_value=0, step=1, required=True),
    },
    key="tabela_digitacao"
)

st.markdown("###") # Espaço

# --- 6. BOTÃO DE CÁLCULO E PROCESSAMENTO ---
if st.button("🔄 CALCULAR RESULTADOS"):
    
    # Validação básica: se tem dados e se tem código preenchido
    if df_digitado.empty or df_digitado['Cód. SAP'].sum() == 0:
        st.error("Preencha os dados na tabela acima.")
    else:
        # Copia os dados digitados para não alterar a entrada
        df_final = df_digitado.copy()
        
        # Converte tipos para garantir o cruzamento
        df_final['Cód. SAP'] = pd.to_numeric(df_final['Cód. SAP'], errors='coerce').fillna(0).astype(int)
        df_final['Qtd'] = pd.to_numeric(df_final['Qtd'], errors='coerce').fillna(0)
        df_final['Tamanho (mm)'] = pd.to_numeric(df_final['Tamanho (mm)'], errors='coerce').fillna(0)
        df_final['Peso Etiqueta (kg)'] = pd.to_numeric(df_final['Peso Etiqueta (kg)'], errors='coerce').fillna(0.0)

        # CRUZAMENTO INTELIGENTE (VLOOKUP)
        # Busca a descrição e o peso padrão na planilha que você subiu
        df_final = df_final.merge(
            df_sap, 
            left_on='Cód. SAP', 
            right_on='Produto', 
            how='left'
        )

        # --- CÁLCULOS MATEMÁTICOS ---
        
        # 1. Regra de Corte (500mm)
        df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(regra_corte_500mm)
        
        # 2. Peso Teórico = (Nova Dimensão / 1000) * Peso Padrão * Qtd
        # Trata caso não ache o produto no SAP (Peso por Metro vira 0)
        df_final['Peso por Metro'] = df_final['Peso por Metro'].fillna(0.0)
        
        df_final['Peso Teórico (Calc)'] = (
            (df_final['Nova Dimensão (mm)'] / 1000.0) * df_final['Peso por Metro'] * df_final['Qtd']
        )
        
        # 3. Sucata = Peso da Etiqueta - Peso Teórico Calculado
        df_final['Sucata (Diferença)'] = df_final['Peso Etiqueta (kg)'] - df_final['Peso Teórico (Calc)']

        # --- ORGANIZAÇÃO FINAL ---
        
        # Seleciona e renomeia as colunas para o relatório ficar bonito
        colunas_finais = [
            'Reserva', 'Cód. SAP', 'Descrição do produto', 
            'Qtd', 'Peso Etiqueta (kg)', 'Tamanho (mm)', 
            'Nova Dimensão (mm)', 'Peso Teórico (Calc)', 'Sucata (Diferença)'
        ]
        
        # Se algum código não foi achado, a descrição fica vazia
        df_final['Descrição do produto'] = df_final['Descrição do produto'].fillna("MATERIAL NÃO ENCONTRADO")
        
        df_relatorio = df_final[colunas_finais]

        # --- EXIBIÇÃO ---
        st.success("✅ Cálculos realizados!")
        
        # Totais
        c1, c2, c3 = st.columns(3)
        c1.metric("Total de Itens", len(df_relatorio))
        c2.metric("Peso Etiqueta Total", f"{df_relatorio['Peso Etiqueta (kg)'].sum():.2f} kg")
        total_sucata = df_relatorio['Sucata (Diferença)'].sum()
        c3.metric("Total Sucata", f"{total_sucata:.2f} kg", delta_color="inverse")

        # Tabela Final Colorida
        st.dataframe(
            df_relatorio.style.format({
                "Peso Etiqueta (kg)": "{:.2f}",
                "Peso Teórico (Calc)": "{:.2f}",
                "Sucata (Diferença)": "{:.2f}"
            }),
            use_container_width=True
        )

        # Download Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_relatorio.to_excel(writer, index=False)
        
        st.download_button(
            label="📥 Baixar Planilha Final",
            data=buffer.getvalue(),
            file_name="Relatorio_Devolucao_Calculado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
