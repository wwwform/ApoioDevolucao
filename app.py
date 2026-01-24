import streamlit as st
import pandas as pd
import io

# --- 1. Configuração (Layout Profissional) ---
st.set_page_config(
    page_title="Sistema de Devolução Manual",
    page_icon="✍️",
    layout="wide"
)

# --- 2. CSS para Tabela de Entrada ---
st.markdown("""
<style>
    .stApp {background-color: #f8fafc;}
    h1 {color: #1e293b; font-family: 'Segoe UI', sans-serif;}
    .stButton>button {
        background-color: #166534; /* Verde Sóbrio */
        color: white; 
        height: 3rem; 
        font-weight: 600;
        border-radius: 6px;
    }
    .stButton>button:hover {background-color: #14532d; color: white;}
</style>
""", unsafe_allow_html=True)

# --- 3. Barra Lateral (Apenas SAP) ---
with st.sidebar:
    st.header("1. Base de Dados")
    st.info("Carregue a planilha do SAP para que o sistema possa calcular o Peso Teórico automaticamente.")
    
    file_sap = st.file_uploader("Upload Tabela SAP (.xlsx/.csv)", type=['xlsx', 'xls', 'csv'])
    
    st.markdown("---")
    st.caption("Modo de Entrada Manual")

# --- 4. Funções ---
def carregar_sap(file):
    try:
        if file.name.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        # Garante que o Produto é número para cruzar
        df['Produto'] = pd.to_numeric(df['Produto'], errors='coerce').fillna(0).astype(int)
        return df[['Produto', 'Peso por Metro']]
    except Exception as e:
        st.error(f"Erro no arquivo SAP: {e}")
        return None

def regra_corte(mm):
    """Arredonda para baixo (múltiplo de 500)"""
    try:
        val = int(float(mm))
        return (val // 500) * 500
    except: return 0

# --- 5. Interface Principal ---
st.title("✍️ Sistema de Controle de Sucata")
st.markdown("Digite os dados das etiquetas abaixo. O sistema fará os cálculos de corte e peso teórico automaticamente.")

if not file_sap:
    st.warning("⚠️ Por favor, carregue a planilha SAP na barra lateral para habilitar os cálculos.")
else:
    df_sap = carregar_sap(file_sap)
    
    if df_sap is not None:
        st.markdown("### 2. Entrada de Dados")
        
        # Cria um DataFrame vazio com as colunas certas para o usuário preencher
        template_data = pd.DataFrame(
            [{"Reserva": "", "Descrição": "", "Código Material": 0, "Qtd": 1, "Peso Etiqueta": 0.0, "Tamanho (mm)": 0}],
        )

        # Tabela Editável (Excel na tela)
        # num_rows="dynamic" permite adicionar linhas clicando no "+"
        df_input = st.data_editor(
            template_data,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Reserva": st.column_config.TextColumn("Reserva (Caneta)", help="Número escrito à mão"),
                "Descrição": st.column_config.TextColumn("Descrição Material", width="medium"),
                "Código Material": st.column_config.NumberColumn("Cód. Material (SAP)", format="%d"),
                "Qtd": st.column_config.NumberColumn("Quantidade", min_value=1, step=1),
                "Peso Etiqueta": st.column_config.NumberColumn("Peso (kg)", min_value=0.0, format="%.3f"),
                "Tamanho (mm)": st.column_config.NumberColumn("Tamanho (mm)", min_value=0, step=1),
            },
            key="editor"
        )

        # Botão de Calcular
        st.markdown("###")
        if st.button("🔄 CALCULAR SUCATA E GERAR RELATÓRIO"):
            
            if df_input.empty or (df_input['Código Material'].sum() == 0):
                st.error("Preencha a tabela acima com pelo menos um item.")
            else:
                # --- Lógica de Negócio ---
                
                # 1. Tratamento de Tipos
                df_calc = df_input.copy()
                df_calc['Código Material'] = pd.to_numeric(df_calc['Código Material'], errors='coerce').fillna(0).astype(int)
                df_calc['Qtd'] = pd.to_numeric(df_calc['Qtd'], errors='coerce').fillna(1)
                df_calc['Peso Etiqueta'] = pd.to_numeric(df_calc['Peso Etiqueta'], errors='coerce').fillna(0.0)
                df_calc['Tamanho (mm)'] = pd.to_numeric(df_calc['Tamanho (mm)'], errors='coerce').fillna(0)

                # 2. Cruzamento com SAP (VLOOKUP)
                df_final = df_calc.merge(
                    df_sap, 
                    left_on='Código Material', 
                    right_on='Produto', 
                    how='left'
                )
                
                # Renomeia coluna SAP
                df_final.rename(columns={'Peso por Metro': 'Peso Padrão (kg/m)'}, inplace=True)
                
                # Se não achou no SAP, avisa visualmente (Peso Padrão = 0)
                df_final['Peso Padrão (kg/m)'] = df_final['Peso Padrão (kg/m)'].fillna(0.0)

                # 3. Cálculos de Engenharia
                df_final['Nova Dimensão (mm)'] = df_final['Tamanho (mm)'].apply(regra_corte)
                
                # Fórmula: (Nova Dimensão / 1000) * Peso SAP * Qtd
                df_final['Peso Calculado'] = (
                    (df_final['Nova Dimensão (mm)'] / 1000.0) * df_final['Peso Padrão (kg/m)'] * df_final['Qtd']
                )
                
                df_final['Diferença (Sucata)'] = df_final['Peso Etiqueta'] - df_final['Peso Calculado']

                # 4. Organização Final
                cols_order = [
                    'Reserva', 'Descrição', 'Código Material', 'Qtd', 
                    'Peso Etiqueta', 'Tamanho (mm)', 
                    'Nova Dimensão (mm)', 'Peso Padrão (kg/m)', 
                    'Peso Calculado', 'Diferença (Sucata)'
                ]
                
                # Remove colunas extras do merge
                df_final = df_final[cols_order]

                # --- Exibição ---
                st.success("Cálculos realizados com sucesso!")
                
                # Resumo
                c1, c2, c3 = st.columns(3)
                c1.metric("Itens", len(df_final))
                c2.metric("Peso Total", f"{df_final['Peso Etiqueta'].sum():.2f} kg")
                c3.metric("Sucata Total", f"{df_final['Diferença (Sucata)'].sum():.2f} kg", delta_color="inverse")

                # Tabela de Resultados
                st.dataframe(
                    df_final.style.format({
                        'Peso Etiqueta': '{:.2f}', 
                        'Peso Padrão (kg/m)': '{:.2f}',
                        'Peso Calculado': '{:.2f}',
                        'Diferença (Sucata)': '{:.2f}'
                    }),
                    use_container_width=True
                )

                # Download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 BAIXAR EXCEL PRONTO",
                    data=buffer.getvalue(),
                    file_name="Relatorio_Sucata_Manual.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
