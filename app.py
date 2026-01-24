import streamlit as st
import pandas as pd
import io

# --- 1. CONFIGURAÇÃO (Visual Limpo) ---
st.set_page_config(page_title="Calculadora SAP Brasil", layout="wide")

st.markdown("""
<style>
    .stApp {background-color: #f8fafc;}
    h1 {color: #1e293b; font-family: 'Segoe UI', sans-serif;}
    .stButton>button {
        background-color: #15803d; /* Verde Excel */
        color: white; height: 3.5rem; width: 100%; font-weight: bold; border-radius: 6px;
    }
    .stButton>button:hover {background-color: #166534;}
</style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES DE FORMATAÇÃO (O Segredo do Ponto e Vírgula) ---
def formatar_brasileiro(valor):
    """Converte número para string no padrão BR: 1.234,56"""
    try:
        # Verifica se é número
        if pd.isna(valor): return ""
        val = float(valor)
        # Formata com separador de milhar (,) e decimal (.) padrão US
        # Ex: 1234.56 -> "1,234.56"
        texto = f"{val:,.2f}"
        # Inverte os caracteres para o padrão BR
        # "1,234.56" -> "1.234,56"
        return texto.replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(valor)

def carregar_sap_robusto(file):
    """Lê CSV/Excel tentando identificar se o decimal é ponto ou vírgula"""
    try:
        if file.name.endswith('.csv'):
            # Tenta ler padrão BR (ponto e vírgula separador, vírgula decimal)
            try:
                df = pd.read_csv(file, sep=';', decimal=',')
                if 'Produto' not in df.columns: # Se falhar, tenta padrão US
                    df = pd.read_csv(file, sep=',', decimal='.')
            except:
                df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        df.columns = df.columns.str.strip()
        
        # Garante que o código é número
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        
        # Garante que Peso por Metro é float (mesmo se veio com vírgula)
        if df['Peso por Metro'].dtype == 'object':
            df['Peso por Metro'] = df['Peso por Metro'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float)
            
        return df[['Produto', 'Descrição do produto', 'Peso por Metro']]
    except Exception as e:
        return None

def regra_corte(mm):
    try:
        return (int(float(mm)) // 500) * 500
    except: return 0

# --- 3. BARRA LATERAL ---
with st.sidebar:
    st.header("📂 1. Base de Dados")
    file_sap = st.file_uploader("Carregue a tabela SAP", type=['xlsx', 'xls', 'csv'])
    st.info("Dica: O sistema aceita CSV exportado direto do SAP.")

# --- 4. TELA PRINCIPAL ---
st.title("✍️ Calculadora de Devolução (Padrão SAP)")

if not file_sap:
    st.warning("⚠️ Carregue a planilha SAP na barra lateral para começar.")
    st.stop()

df_sap = carregar_sap_robusto(file_sap)
if df_sap is None:
    st.error("Erro ao ler o arquivo SAP. Verifique as colunas.")
    st.stop()

# --- 5. ENTRADA DE DADOS ---
st.markdown("### 2. Entrada de Dados")
st.caption("Preencha os campos abaixo. O Peso Teórico e a Descrição são automáticos.")

# Estado da tabela
if 'input_data' not in st.session_state:
    st.session_state.input_data = pd.DataFrame(
        [{"Reserva": "", "Cód. SAP": None, "Qtd": 1, "Peso Balança (kg)": 0.0, "Tamanho (mm)": 0}],
    )

# Editor
df_digitado = st.data_editor(
    st.session_state.input_data,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Reserva": st.column_config.TextColumn("Reserva", help="Nº escrito à mão"),
        "Cód. SAP": st.column_config.NumberColumn("Cód. Material", format="%d", required=True),
        "Qtd": st.column_config.NumberColumn("Qtd", min_value=1, step=1, required=True),
        "Peso Balança (kg)": st.column_config.NumberColumn("Peso Real (kg)", min_value=0.0, format="%.2f", required=True),
        "Tamanho (mm)": st.column_config.NumberColumn("Tamanho (mm)", min_value=0, step=1, required=True),
    }
)

st.markdown("###")

# --- 6. PROCESSAMENTO ---
if st.button("🔄 CALCULAR E FORMATAR"):
    
    if df_digitado['Cód. SAP'].sum() == 0:
        st.error("Preencha os dados antes de calcular.")
    else:
        # Copia e Trata Tipos
        df_final = df_digitado.copy()
        df_final['Cód. SAP'] = pd.to_numeric(df_final['Cód. SAP'], errors='coerce').fillna(0).astype(int)
        df_final['Qtd'] = pd.to_numeric(df_final['Qtd'], errors='coerce').fillna(0)
        df_final['Tamanho (mm)'] = pd.to_numeric(df_final['Tamanho (mm)'], errors='coerce').fillna(0)
        df_final['Peso Balança (kg)'] = pd.to_numeric(df_final['Peso Balança (kg)'], errors='coerce').fillna(0.0)

        # Cruzamento SAP
        df_final = df_final.merge(
            df_sap, 
            left_on='Cód. SAP', 
            right_on='Produto', 
            how='left'
        )
        
        # Preenche vazios
        df_final['Descrição do produto'] = df_final['Descrição do produto'].fillna("NÃO ENCONTRADO")
        df_final['Peso por Metro'] = df_final['Peso por Metro'].fillna(0.0)

        # Cálculos
        df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(regra_corte)
        
        df_final['Peso Teórico (Calc)'] = (
            (df_final['Nova Dimensão (mm)'] / 1000.0) * df_final['Peso por Metro'] * df_final['Qtd']
        )
        
        df_final['Sucata (Dif)'] = df_final['Peso Balança (kg)'] - df_final['Peso Teórico (Calc)']

        # Seleção de Colunas
        cols = [
            'Reserva', 'Cód. SAP', 'Descrição do produto', 
            'Qtd', 'Peso Balança (kg)', 'Tamanho (mm)', 
            'Nova Dimensão (mm)', 'Peso Teórico (Calc)', 'Sucata (Dif)'
        ]
        df_relatorio = df_final[cols]

        # --- FORMATAÇÃO BRASILEIRA (O Pulo do Gato) ---
        # Cria uma cópia apenas para exibição e exportação, transformando números em Texto Formatado
        df_export = df_relatorio.copy()
        
        colunas_para_formatar = ['Peso Balança (kg)', 'Peso Teórico (Calc)', 'Sucata (Dif)']
        
        for col in colunas_para_formatar:
            # Aplica a função que troca ponto por vírgula e bota ponto no milhar
            df_export[col] = df_export[col].apply(formatar_brasileiro)

        # --- EXIBIÇÃO ---
        st.success("Cálculos realizados e formatados para padrão Brasil!")
        
        # Totais (calculados sobre o numérico original)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Peças", int(df_relatorio['Qtd'].sum()))
        c2.metric("Total Peso Real", f"{df_relatorio['Peso Balança (kg)'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " kg")
        c3.metric("Total Sucata", f"{df_relatorio['Sucata (Dif)'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " kg")

        # Tabela (Mostra a versão texto formatada)
        st.dataframe(df_export, use_container_width=True)

        # Download Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Salva a versão formatada (texto) para garantir que o Excel abra com vírgula
            df_export.to_excel(writer, index=False)
        
        st.download_button(
            label="📥 Baixar Excel (Formatado SAP)",
            data=buffer.getvalue(),
            file_name="Relatorio_Devolucao_SAP.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
