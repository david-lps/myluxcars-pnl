import streamlit as st
import pandas as pd
import numpy as np
from typing import Dict, List
import os
import sys

st.set_page_config(page_title="MyLuxCars – P&L & Caixa", layout="wide")


# =============================
# Helpers & Defaults
# =============================
YEARS = [1,2,3,4,5,6]
DEFAULT_UPSELL = 0.05
DEFAULT_TAX_RATE = 0.25
DEFAULT_INTEREST_RATE = 0.045  # 4.5% do valor do carro/ano no P&L (juros)
# Percentuais de parcela TOTAL ao ano (Caixa) por prazo (juros + principal) – relação % do preço do carro
FINANCING_TERM_TO_ANNUAL_INSTALLMENT = {3: 0.376, 4: 0.294, 5: 0.244}

# Depreciação acumulada default (premium EUA) – pode ser sobrescrita por carro/ano na grade
DEFAULT_DEPR_ACC = {1:0.18, 2:0.30, 3:0.40, 4:0.50, 5:0.58, 6:0.65}

@st.cache_data
def empty_cars_df():
    return pd.DataFrame({
        "CarID": pd.Series([], dtype=str),
        "Ano": pd.Series([], dtype=int),
        "Marca": pd.Series([], dtype=str),
        "Modelo": pd.Series([], dtype=str),
        "Categoria": pd.Series([], dtype=str),
        "PrecoCompra": pd.Series([], dtype=float)
    })

@st.cache_data
def template_yearly_inputs(car_ids: List[str]):
    rows = []
    for car_id in car_ids:
        for y in YEARS:
            rows.append({
                "CarID": car_id,
                "AnoOffset": y,
                # Defaults editáveis pelo usuário
                "TaxaDepreciacao_%": round((DEFAULT_DEPR_ACC[y] - DEFAULT_DEPR_ACC.get(y-1, 0.0))*100, 2) if y in DEFAULT_DEPR_ACC else 10.0,
                "Juros_%_sobre_preco": DEFAULT_INTEREST_RATE*100,
                "AnoCompra": 1,   # default: compra no ano 1 do horizonte
                "AnoVenda": np.nan,  # sem venda por padrão
                "PrecoDiaria": 120.0,
                "TaxaOcupacao_%": 60.0,
                "Seguro_USD": 1200.0,
                "Manutencao_USD": 1000.0,
                "Sinistro_USD": 900.0,
                "Combustivel_USD": 275.0,
                "Estacionamento_USD": 0.0
            })
    return pd.DataFrame(rows)

# Inicialização de estado
def load_default_data():
    """Carrega dados do arquivo JSON padrão se existir"""
    try:
        import json
        with open('frota_myluxcars.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Carregar dados da frota
        cars_data = pd.DataFrame(data['cars']) if 'cars' in data else empty_cars_df()

        # Carregar dados anuais
        yearly_data = pd.DataFrame(data['yearly']) if 'yearly' in data else template_yearly_inputs([])

        # Carregar parâmetros globais
        global_params = data.get('global_params', {})

        return cars_data, yearly_data, global_params
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(f"Arquivo frota_myluxcars.json não encontrado ou inválido: {e}")
        return empty_cars_df(), template_yearly_inputs([]), {}

if "cars" not in st.session_state:
    default_cars, default_yearly, global_params = load_default_data()
    st.session_state.cars = default_cars
    st.session_state.yearly = default_yearly
    # Salvar parâmetros globais no session state
    if global_params:
        st.session_state.global_params = global_params
else:
    # Verificar se os dados estão vazios e carregar o padrão
    if st.session_state.cars.empty:
        default_cars, default_yearly, global_params = load_default_data()
        st.session_state.cars = default_cars
        st.session_state.yearly = default_yearly
        if global_params:
            st.session_state.global_params = global_params

# =============================
# Sidebar – Parâmetros globais
# =============================
st.sidebar.header("Parâmetros Globais")

# Usar valores do JSON se disponíveis, senão usar defaults
saved_params = st.session_state.get('global_params', {})

horizon_years = st.sidebar.slider("Horizonte (anos)", 3, 6, 
                                  saved_params.get('horizon_years', 6))
financing_term = st.sidebar.selectbox("Prazo do financiamento (anos)", [3,4,5], 
                                      index=[3,4,5].index(saved_params.get('financing_term', 5)),
                                      help="Usado para o Caixa: parcela anual total como % do preço do carro.")
upsell_rate = st.sidebar.number_input("Upsell sobre Receita Bruta (%)", 0.0, 100.0, 
                                     saved_params.get('upsell_rate', DEFAULT_UPSELL)*100.0, step=0.5)/100.0

# Inicializar dicionários com valores salvos ou defaults
deductions_rate_by_year = {}
marketing_rate_by_year = {}
team_cost_by_year = {}
platform_cost_by_year = {}
other_fixed_by_year = {}

tax_rate = st.sidebar.number_input("Impostos sobre EBT (%)", 0.0, 100.0, 
                                  saved_params.get('tax_rate', DEFAULT_TAX_RATE)*100.0, step=1.0)/100.0

st.sidebar.markdown("---")
st.sidebar.caption("Deduções/Equipe/Marketing/Plataforma/Outros são definidos na seção 'Custos Gerais por Ano'.")

# =============================
# Layout
# =============================
st.title("MyLuxCars – P&L e Fluxo de Caixa (6 anos)")

# Mostrar status do carregamento de dados
if not st.session_state.cars.empty:
    st.success(f"✅ Sistema carregado com {len(st.session_state.cars)} carros da frota padrão!")

with st.expander("1) Frota – Cadastre/edite os carros"):
    cars = st.data_editor(
        st.session_state.cars,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "CarID": st.column_config.TextColumn(help="Identificador único do carro"),
            "PrecoCompra": st.column_config.NumberColumn(format="$%.0f"),
        },
        key="cars_editor"
    )
    st.session_state.cars = cars

    # Garantir linhas de Yearly para cada CarID
    car_ids = [str(c) for c in st.session_state.cars["CarID"].dropna().unique() if str(c) != '']

    # Verificar se yearly tem dados, se não, inicializar
    if st.session_state.yearly.empty:
        st.session_state.yearly = template_yearly_inputs([])

    existing_ids = set(st.session_state.yearly["CarID"].unique()) if not st.session_state.yearly.empty else set()
    missing = [cid for cid in car_ids if cid not in existing_ids]
    if missing:
        new_rows = template_yearly_inputs(missing)
        if st.session_state.yearly.empty:
            st.session_state.yearly = new_rows
        else:
            st.session_state.yearly = pd.concat([st.session_state.yearly, new_rows], ignore_index=True)

with st.expander("2) Inputs por Carro/Ano – Operação, Juros e Depreciação"):
    # Filtro por CarID opcional
    all_ids = ["(todos)"] + [cid for cid in car_ids if cid != '']
    sel = st.selectbox("Filtrar por CarID", all_ids)

    if not st.session_state.yearly.empty:
        yearly_view = st.session_state.yearly.copy()
        if sel != "(todos)":
            yearly_view = yearly_view[yearly_view["CarID"]==sel]

        yearly_view = yearly_view[yearly_view["AnoOffset"]<=horizon_years]

        yearly_view = st.data_editor(
            yearly_view,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "TaxaDepreciacao_%": st.column_config.NumberColumn(help="% do preço reconhecido em depreciação no ano"),
                "Juros_%_sobre_preco": st.column_config.NumberColumn(help="Somente JUROS que vão para o P&L (% do preço)"),
                "PrecoDiaria": st.column_config.NumberColumn(format="$%.0f"),
                "TaxaOcupacao_%": st.column_config.NumberColumn(format="%.1f%%"),
                "Seguro_USD": st.column_config.NumberColumn(format="$%.0f"),
                "Manutencao_USD": st.column_config.NumberColumn(format="$%.0f"),
                "Sinistro_USD": st.column_config.NumberColumn(format="$%.0f"),
                "Combustivel_USD": st.column_config.NumberColumn(format="$%.0f"),
                "Estacionamento_USD": st.column_config.NumberColumn(format="$%.0f"),
            },
            key="yearly_editor"
        )
        # Persist edits back into session state (merge on index)
        st.session_state.yearly = pd.concat([yearly_view, st.session_state.yearly[~st.session_state.yearly.index.isin(yearly_view.index)]])
    else:
        st.info("Adicione carros na seção 1 para configurar os parâmetros por carro/ano.")

with st.expander("3) Custos Gerais por Ano"):
    cols = st.columns(6)
    cols[0].markdown("**Ano**")
    cols[1].markdown("**Deduções (% Receita)**")
    cols[2].markdown("**Equipe (US$)**")
    cols[3].markdown("**Marketing (% Receita)**")
    cols[4].markdown("**Plataforma/SaaS (US$)**")
    cols[5].markdown("**Outros Fixos (US$)**")

    # Usar valores salvos se disponíveis
    saved_deductions = saved_params.get('deductions_rate_by_year', {})
    saved_team = saved_params.get('team_cost_by_year', {})
    saved_marketing = saved_params.get('marketing_rate_by_year', {})
    saved_platform = saved_params.get('platform_cost_by_year', {})
    saved_other = saved_params.get('other_fixed_by_year', {})

    for y in YEARS:
        if y>horizon_years: break
        c = st.columns(6)
        c[0].markdown(f"{y}")

        # Usar valores salvos ou defaults
        deductions_rate_by_year[y] = c[1].number_input(" ", key=f"ded_{y}", min_value=0.0, max_value=100.0, 
                                                     value=saved_deductions.get(str(y), 10.0)*100 if str(y) in saved_deductions else 10.0)/100.0
        team_cost_by_year[y] = c[2].number_input("  ", key=f"team_{y}", min_value=0.0, 
                                               value=float(saved_team.get(str(y), 0.0)), step=1000.0)
        marketing_rate_by_year[y] = c[3].number_input("   ", key=f"mkt_{y}", min_value=0.0, max_value=100.0, 
                                                     value=saved_marketing.get(str(y), 8.0)*100 if str(y) in saved_marketing else 8.0)/100.0
        platform_cost_by_year[y] = c[4].number_input("    ", key=f"plat_{y}", min_value=0.0, 
                                                    value=float(saved_platform.get(str(y), 0.0)), step=500.0)
        other_fixed_by_year[y] = c[5].number_input("     ", key=f"other_{y}", min_value=0.0, 
                                                 value=float(saved_other.get(str(y), 0.0)), step=500.0)

# =============================
# Cálculos
# =============================

def compute_per_year_tables(cars: pd.DataFrame, yearly: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    if cars.empty or yearly.empty:
        idx = pd.Index([y for y in YEARS if y<=horizon_years], name="Ano")
        zeros = pd.DataFrame(0.0, index=idx, columns=["ReceitaBruta","Upsell","Deducoes","ReceitaLiquida",
                                                      "Seguro","Manutencao","Sinistro","Combustivel","Estacionamento",
                                                      "Depreciacao","CustoFrotaTotal","LucroBruto",
                                                      "Equipe","Marketing","Plataforma","OutrosFixos","EBITDA",
                                                      "Juros","EBT","Impostos","LucroLiquido",
                                                      "Depreciacao_add","Principal","VendaFrota","CaixaFinal"])        
        return {"PnL": zeros.copy(), "Cash": zeros.copy()}

    # Join Yearly with cars
    y = yearly.copy()

    # Verificar se yearly tem as colunas necessárias
    if 'AnoOffset' not in y.columns:
        # Se não tem dados, retorna zeros
        idx = pd.Index([y for y in YEARS if y<=horizon_years], name="Ano")
        zeros = pd.DataFrame(0.0, index=idx, columns=["ReceitaBruta","Upsell","Deducoes","ReceitaLiquida",
                                                      "Seguro","Manutencao","Sinistro","Combustivel","Estacionamento",
                                                      "Depreciacao","CustoFrotaTotal","LucroBruto",
                                                      "Equipe","Marketing","Plataforma","OutrosFixos","EBITDA",
                                                      "Juros","EBT","Impostos","LucroLiquido",
                                                      "Depreciacao_add","Principal","VendaFrota","CaixaFinal"])        
        return {"PnL": zeros.copy(), "Cash": zeros.copy()}

    y = y[y["AnoOffset"]<=horizon_years]
    cars_use = cars.dropna(subset=["CarID"]).copy()
    y = y.merge(cars_use, on="CarID", how="inner", suffixes=("_Y","_C"))

    def active_in_year(row):
        # carro conta se ano está entre ano compra e (ano venda inclusive para venda, exclusivo para operação)
        ano = row["AnoOffset"]
        ano_compra = row.get("AnoCompra", 1)
        ano_venda = row.get("AnoVenda", np.nan)
        if pd.isna(ano_venda):
            return ano >= ano_compra
        return (ano >= ano_compra) and (ano < ano_venda)

    # Receitas e custos por linha
    y["IsActive"] = y.apply(active_in_year, axis=1)

    # Receita
    y["ReceitaBruta"] = np.where(
        y["IsActive"],
        y["PrecoDiaria"] * (y["TaxaOcupacao_%"] / 100.0) * 365.0,
        0.0
    )
    y["Upsell"] = y["ReceitaBruta"] * upsell_rate
    # Deduções % por ano
    y["Deducoes"] = (y["ReceitaBruta"] + y["Upsell"]) * y["AnoOffset"].map(deductions_rate_by_year)
    y["ReceitaLiquida"] = (y["ReceitaBruta"] + y["Upsell"]) - y["Deducoes"]

    # Custos operacionais por carro/ano
    for col in ["Seguro_USD","Manutencao_USD","Sinistro_USD","Combustivel_USD","Estacionamento_USD"]:
        y[col.replace("_USD", "")] = np.where(y["IsActive"], y[col], 0.0)

    # Depreciação (percentual * preço)
    y["Depreciacao"] = np.where(
        y["IsActive"],
        (y["TaxaDepreciacao_%"]/100.0) * y["PrecoCompra"],
        0.0
    )

    # P&L – soma por ano
    grouped = y.groupby("AnoOffset").agg({
        "ReceitaBruta":"sum","Upsell":"sum","Deducoes":"sum","ReceitaLiquida":"sum",
        "Seguro":"sum","Manutencao":"sum","Sinistro":"sum","Combustivel":"sum","Estacionamento":"sum",
        "Depreciacao":"sum"
    }).rename_axis("Ano")

    grouped["CustoFrotaTotal"] = grouped[["Seguro","Manutencao","Sinistro","Combustivel","Estacionamento","Depreciacao"]].sum(axis=1)
    grouped["LucroBruto"] = grouped["ReceitaLiquida"] - grouped["CustoFrotaTotal"]

    # Opex por ano (globais)
    grouped["Equipe"] = grouped.index.map(team_cost_by_year).astype(float)
    grouped["Marketing"] = grouped["ReceitaLiquida"] * grouped.index.map(marketing_rate_by_year).astype(float)
    grouped["Plataforma"] = grouped.index.map(platform_cost_by_year).astype(float)
    grouped["OutrosFixos"] = grouped.index.map(other_fixed_by_year).astype(float)

    grouped["EBITDA"] = grouped["LucroBruto"] - (grouped["Equipe"] + grouped["Marketing"] + grouped["Plataforma"] + grouped["OutrosFixos"])

    # Juros P&L – por carro/ano (% do preço original)
    y["JurosPL"] = np.where(y["IsActive"], (y["Juros_%_sobre_preco"]/100.0) * y["PrecoCompra"], 0.0)
    juros_by_year = y.groupby("AnoOffset")["JurosPL"].sum()
    grouped["Juros"] = juros_by_year

    grouped["EBT"] = grouped["EBITDA"] - grouped["Juros"]
    grouped["Impostos"] = np.where(grouped["EBT"]>0, grouped["EBT"]*tax_rate, 0.0)
    grouped["LucroLiquido"] = grouped["EBT"] - grouped["Impostos"]

    pnl_table = grouped.copy()

    # ================= CASHFLOW =================
    cash = pnl_table[["LucroLiquido"]].copy()
    cash["Depreciacao_add"] = pnl_table["Depreciacao"]  # volta depreciação

    # Principal (Caixa): parcela total – juros P&L
    # Parcela total anual depende do prazo global
    annual_install_pct = FINANCING_TERM_TO_ANNUAL_INSTALLMENT[financing_term]
    y["ParcelaTotal"] = np.where(y["IsActive"], annual_install_pct * y["PrecoCompra"], 0.0)
    y["Principal"] = np.maximum(y["ParcelaTotal"] - y["JurosPL"], 0.0)
    principal_by_year = y.groupby("AnoOffset")["Principal"].sum()
    cash["Principal"] = principal_by_year

    # Venda Frota no ano de venda – pelo valor contábil (Preço – depreciação acumulada até o ano-1 e reconhece depreciação do ano de venda antes?)
    # Convenção: a depreciação do ano da venda é reconhecida e a venda ocorre no fim do ano pelo valor contábil após a depreciação do próprio ano.
    # Cálculo do valor contábil por linha
    def compute_book_value(df: pd.DataFrame) -> pd.Series:
        book_vals = []
        for (car), sub in df.sort_values(["AnoOffset"]).groupby("CarID"):
            preco = sub["PrecoCompra"].iloc[0]
            deprec_acc = 0.0
            for _, r in sub.iterrows():
                deprec_acc += (r["TaxaDepreciacao_%"]/100.0) * preco if r["IsActive"] else 0.0
                if not pd.isna(r.get("AnoVenda")) and r["AnoOffset"]==r["AnoVenda"]:
                    # valor contábil após reconhecer a depreciação deste ano
                    book_vals.append((r.name, max(preco - deprec_acc, 0.0)))
        # Map back
        s = pd.Series({idx: val for idx,val in book_vals})
        return s

    book_map = compute_book_value(y)
    y["VendaValorContabil"] = y.index.map(book_map)
    venda_by_year = y.groupby("AnoOffset")["VendaValorContabil"].sum(min_count=1).fillna(0.0)
    cash["VendaFrota"] = venda_by_year

    cash["CaixaFinal"] = cash["LucroLiquido"] + cash["Depreciacao_add"] - cash["Principal"] + cash["VendaFrota"]

    # Limitar ao horizonte
    pnl_table = pnl_table.loc[pnl_table.index<=horizon_years]
    cash = cash.loc[cash.index<=horizon_years]

    return {"PnL": pnl_table, "Cash": cash}

# =============================
# Run calculations & Show
# =============================
results = compute_per_year_tables(st.session_state.cars, st.session_state.yearly)

pnl, cash = results["PnL"], results["Cash"]

st.subheader("P&L (Por Ano)")
st.dataframe(pnl.style.format({
    "ReceitaBruta":"$ {:,.0f}", "Upsell":"$ {:,.0f}", "Deducoes":"$ {:,.0f}", "ReceitaLiquida":"$ {:,.0f}",
    "Seguro":"$ {:,.0f}", "Manutencao":"$ {:,.0f}", "Sinistro":"$ {:,.0f}", "Combustivel":"$ {:,.0f}", "Estacionamento":"$ {:,.0f}",
    "Depreciacao":"$ {:,.0f}", "CustoFrotaTotal":"$ {:,.0f}", "LucroBruto":"$ {:,.0f}",
    "Equipe":"$ {:,.0f}", "Marketing":"$ {:,.0f}", "Plataforma":"$ {:,.0f}", "OutrosFixos":"$ {:,.0f}", "EBITDA":"$ {:,.0f}",
    "Juros":"$ {:,.0f}", "EBT":"$ {:,.0f}", "Impostos":"$ {:,.0f}", "LucroLiquido":"$ {:,.0f}"
}))

st.subheader("Fluxo de Caixa (Por Ano)")
st.dataframe(cash.style.format({
    "LucroLiquido":"$ {:,.0f}", "Depreciacao_add":"$ {:,.0f}", "Principal":"$ {:,.0f}", "VendaFrota":"$ {:,.0f}", "CaixaFinal":"$ {:,.0f}"
}))

# =============================
# Charts
# =============================
colA, colB = st.columns(2)
with colA:
    st.markdown("**Gráfico – Receita Líquida, EBITDA, Lucro Líquido**")
    chart_df = pnl[["ReceitaLiquida","EBITDA","LucroLiquido"]].copy()
    st.line_chart(chart_df)
with colB:
    st.markdown("**Gráfico – Caixa Líquido por Ano**")
    st.bar_chart(cash[["CaixaFinal"]])

# =============================
# Export
# =============================
with st.expander("Exportar (CSV)"):
    pnl_csv = pnl.to_csv().encode("utf-8")
    cash_csv = cash.to_csv().encode("utf-8")
    st.download_button("Baixar P&L (CSV)", pnl_csv, file_name="pnl_myluxcars.csv", mime="text/csv")
    st.download_button("Baixar Caixa (CSV)", cash_csv, file_name="caixa_myluxcars.csv", mime="text/csv")

# =============================
# Salvar/Carregar Dados Completos
# =============================
with st.expander("Salvar/Carregar Projeto Completo"):
    st.markdown("**Salve todos os seus dados (frota + configurações) em um arquivo JSON:**")

    # Preparar dados para salvar
    def prepare_data_for_export():
        return {
            "cars": st.session_state.cars.to_dict('records'),
            "yearly": st.session_state.yearly.to_dict('records'),
            "global_params": {
                "horizon_years": horizon_years,
                "financing_term": financing_term,
                "upsell_rate": upsell_rate,
                "tax_rate": tax_rate,
                "deductions_rate_by_year": deductions_rate_by_year,
                "marketing_rate_by_year": marketing_rate_by_year,
                "team_cost_by_year": team_cost_by_year,
                "platform_cost_by_year": platform_cost_by_year,
                "other_fixed_by_year": other_fixed_by_year
            },
            "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    # Botão para download do JSON
    if st.button("Gerar Arquivo de Dados"):
        data_to_export = prepare_data_for_export()
        json_str = pd.io.json.dumps(data_to_export, indent=2)

        st.download_button(
            label="Baixar Dados Completos (JSON)",
            data=json_str,
            file_name=f"myluxcars_dados_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
        st.success("Arquivo gerado! Clique no botão acima para baixar.")

    # Botão para salvar como arquivo padrão
    if st.button("💾 Salvar como Padrão do Sistema"):
        try:
            data_to_export = prepare_data_for_export()
            import json
            with open('frota_myluxcars.json', 'w', encoding='utf-8') as f:
                json.dump(data_to_export, f, indent=2, ensure_ascii=False)
            st.success("✅ Dados salvos como padrão! Próxima vez que abrir o sistema, estes dados aparecerão automaticamente.")
        except Exception as e:
            st.error(f"❌ Erro ao salvar arquivo padrão: {str(e)}")

    st.markdown("---")
    st.markdown("**Carregue um arquivo de dados salvo anteriormente:**")

    uploaded_file = st.file_uploader(
        "Selecione um arquivo JSON de dados", 
        type=['json'],
        help="Carregue um arquivo JSON salvo anteriormente para restaurar todos os dados."
    )

    if uploaded_file is not None:
        try:
            # Ler o arquivo JSON
            data_loaded = pd.read_json(uploaded_file)

            if st.button("Carregar Dados do Arquivo"):
                # Restaurar dados da frota
                if 'cars' in data_loaded:
                    st.session_state.cars = pd.DataFrame(data_loaded['cars'])

                # Restaurar dados anuais
                if 'yearly' in data_loaded:
                    st.session_state.yearly = pd.DataFrame(data_loaded['yearly'])

                # Restaurar parâmetros globais
                if 'global_params' in data_loaded:
                    st.session_state.global_params = data_loaded['global_params']

                # Mostrar informações do arquivo
                if 'timestamp' in data_loaded:
                    st.info(f"Dados carregados de: {data_loaded['timestamp']}")

                st.success("Dados carregados com sucesso! A página será atualizada.")
                st.rerun()

        except Exception as e:
            st.error(f"Erro ao carregar arquivo: {str(e)}")
            st.info("Certifique-se de que o arquivo é um JSON válido gerado por este sistema.")

    st.markdown("---")
    st.markdown("**Instruções:**")
    st.markdown("""
    **Para salvar seus dados:**
    1. Clique em "Gerar Arquivo de Dados" para download temporário
    2. OU clique "💾 Salvar como Padrão" para que apareça sempre no sistema
    3. O arquivo será salvo no seu computador/projeto

    **Para carregar dados salvos:**
    1. Clique em "Browse files" ou arraste o arquivo JSON
    2. Clique em "Carregar Dados do Arquivo"
    3. Todos os seus carros e configurações serão restaurados

    **O que é salvo:**
    - Todos os carros da frota
    - Todas as configurações por carro/ano
    - Parâmetros globais (horizonte, financiamento, impostos, etc.)
    - Data e hora do salvamento

    **💡 Dica:** Use "Salvar como Padrão" para que seus dados apareçam automaticamente toda vez que abrir o sistema!
    """)

st.caption("Obs.: Juros no P&L usam a coluna 'Juros_%_sobre_preco'. Parcela total (caixa) usa o prazo global selecionado e a tabela padrão de % sobre o preço do carro.")

# Configurações específicas para deployment
if 'REPLIT_DEPLOYMENT' in os.environ:
    sys.path.append('/home/runner/workspace')