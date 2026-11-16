import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import nuvem
from pdf_termo import converter_df_excel_simples, gerar_backup_completo_excel, gerar_termo_pdf

# Extração resiliente de constantes e funções do módulo nuvem (imune a cache de reload)
supabase = nuvem.supabase
registrar_log_auditoria = nuvem.registrar_log_auditoria
exibir_marca_desenvolvedor = nuvem.exibir_marca_desenvolvedor
normalizar_nome_coluna = nuvem.normalizar_nome_coluna
salvar_dados_massa = nuvem.salvar_dados_massa
matricula_valida = nuvem.matricula_valida
limpar_texto_matricula = nuvem.limpar_texto_matricula
carregar_preferencias_colunas = getattr(nuvem, 'carregar_preferencias_colunas', lambda: {})
salvar_preferencias_colunas = getattr(nuvem, 'salvar_preferencias_colunas', lambda *a, **kw: None)

COLUNAS_FERRAMENTAS = getattr(nuvem, 'COLUNAS_FERRAMENTAS', [
    'id_controle', 'codigo_d365', 'descricao_d365', 'descricao_ferramenta',
    'categoria', 'marca', 'modelo', 'numero_serie', 'patrimonio',
    'quantidade', 'unidade', 'condicao_fisica', 'status_operacional',
    'localizacao', 'responsavel_atual', 'matricula', 'projeto', 'coordenacao',
    'data_entrada', 'data_entrega', 'data_devolucao', 'ultima_movimentacao',
    'dias_sem_movimentacao', 'data_ultima_inspecao', 'proxima_inspecao',
    'valor_referencia', 'custo_acumulado_manutencao', 'quantidade_manutencoes',
    'motivo_segregacao', 'destinacao_final', 'documento_referencia', 'observacoes'
])

LISTA_CONDICAO_FISICA = getattr(nuvem, 'LISTA_CONDICAO_FISICA', [
    "NOVO", "USADO - BOM", "USADO - REGULAR", "EM INSPEÇÃO",
    "EM MANUTENÇÃO", "COM DEFEITO", "SEGREGADO", "OBSOLETO", "DESCARTE"
])

LISTA_STATUS_OPERACIONAL = getattr(nuvem, 'LISTA_STATUS_OPERACIONAL', [
    "DISPONÍVEL", "EM CAUTELA", "EM INSPEÇÃO", "EM MANUTENÇÃO",
    "BLOQUEADO", "AGUARDANDO DECISÃO", "AGUARDANDO DESCARTE", "TRANSFERIDO", "BAIXADO"
])

LISTA_LOCALIZACOES_FER = getattr(nuvem, 'LISTA_LOCALIZACOES_FER', [
    "USADO-DISP", "USADO-INSPECAO", "USADO-MANUT", "USADO-DEFEITO",
    "USADO-SEGREGADO", "USADO-OBSOLETO", "USADO-DESCARTE", "CAMPO / COLABORADOR", "BAIXADO / DESCARTADO"
])

LISTA_TIPOS_MOV_FER = getattr(nuvem, 'LISTA_TIPOS_MOV_FER', [
    "ENTRADA", "DEVOLUÇÃO", "ENTREGA", "CAUTELA", "TRANSFERÊNCIA",
    "ENVIO PARA MANUTENÇÃO", "RETORNO DE MANUTENÇÃO", "LIBERAÇÃO",
    "SEGREGAÇÃO", "BAIXA", "DESCARTE"
])

def gerar_proximo_id_fer(df_fer):
    if hasattr(nuvem, 'gerar_proximo_id_fer'):
        return nuvem.gerar_proximo_id_fer(df_fer)
    if df_fer.empty or 'id_controle' not in df_fer.columns:
        return "FER-000001"
    maior = 0
    for val in df_fer['id_controle'].astype(str):
        val_limpo = val.strip().upper()
        if val_limpo.startswith("FER-"):
            num_str = val_limpo.replace("FER-", "").strip()
            if num_str.isdigit():
                maior = max(maior, int(num_str))
    return f"FER-{maior + 1:06d}"

def buscar_ferramenta(termo_busca, df_fer):
    if hasattr(nuvem, 'buscar_ferramenta'):
        return nuvem.buscar_ferramenta(termo_busca, df_fer)
    if df_fer.empty or not termo_busca:
        return pd.DataFrame()
    t = str(termo_busca).strip().upper()
    id_c = df_fer['id_controle'].fillna("").astype(str).str.strip().str.upper()
    c_d365 = df_fer['codigo_d365'].fillna("").astype(str).str.strip().str.upper()
    pat = df_fer['patrimonio'].fillna("").astype(str).str.strip().str.upper()
    ser = df_fer['numero_serie'].fillna("").astype(str).str.strip().str.upper()
    return df_fer[(id_c == t) | (c_d365 == t) | (pat == t) | (ser == t)]

# ==========================================
# ESTILIZAÇÃO VISUAL DE ALERTAS
# ==========================================
def formatar_badge_alerta(status_op, cond_fis):
    st_up = str(status_op).strip().upper()
    cd_up = str(cond_fis).strip().upper()
    if st_up == "DISPONÍVEL":
        return "🟢 DISPONÍVEL"
    elif st_up == "EM CAUTELA":
        return "🔵 EM CAUTELA"
    elif st_up == "EM INSPEÇÃO" or cd_up == "EM INSPEÇÃO":
        return "🟡 EM INSPEÇÃO"
    elif st_up == "EM MANUTENÇÃO" or cd_up == "EM MANUTENÇÃO":
        return "🟠 EM MANUTENÇÃO"
    elif st_up == "BLOQUEADO" or cd_up == "COM DEFEITO":
        return "🔴 DEFEITO / BLOQUEADO"
    elif st_up in ["AGUARDANDO DESCARTE", "BAIXADO"] or cd_up in ["OBSOLETO", "DESCARTE", "SEGREGADO"]:
        return "⚪ OBSOLETO / DESCARTE"
    return f"⚪ {st_up}"

def _parse_float(val):
    if not val:
        return 0.0
    txt = str(val).replace("R$", "").replace(" ", "").strip()
    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif "," in txt:
        txt = txt.replace(",", ".")
    try:
        return float(txt)
    except Exception:
        return 0.0

def _parse_int(val, default=1):
    try:
        return int(float(str(val).strip()))
    except Exception:
        return default

def update_cols_fer():
    st.session_state.saved_cols_fer = st.session_state.ms_fer_key
    salvar_preferencias_colunas(
        st.session_state.get('saved_cols_inv'),
        st.session_state.get('saved_cols_mov'),
        st.session_state.get('saved_cols_trm'),
        st.session_state.saved_cols_fer
    )

# ==========================================
# F1: PAINEL GERENCIAL E SALDO OPERACIONAL
# ==========================================
def render_painel_ferramental(df_fer, df_mov_fer, df_caut_fer, df_manut_fer, df_baixa_fer, df_conc_d365):
    if 'saved_cols_fer' not in st.session_state:
        prefs = carregar_preferencias_colunas()
        st.session_state.saved_cols_fer = prefs.get('fer', list(COLUNAS_FERRAMENTAS))

    st.header("🛠️ Controle Gerencial de Ferramentas Usadas / Reutilizáveis")
    st.caption("Controle operacional complementar ao D365 — Rastreabilidade física e individual sem alterar artificialmente o saldo do ERP.")

    st.markdown("##### 📊 SALDO OPERACIONAL DE FERRAMENTAS USADAS")
    
    if not df_fer.empty:
        qtd_series = df_fer['quantidade'].apply(lambda x: _parse_int(x, 1))
        st_op = df_fer['status_operacional'].astype(str).str.upper().str.strip()
        cd_fi = df_fer['condicao_fisica'].astype(str).str.upper().str.strip()

        mask_ativo_fisico = ~st_op.isin(['BAIXADO', 'TRANSFERIDO'])
        total_fisico = int(qtd_series[mask_ativo_fisico].sum())
        
        mask_disp = (st_op == 'DISPONÍVEL') & (cd_fi.isin(['NOVO', 'USADO - BOM', 'USADO - REGULAR']))
        s_disp = int(qtd_series[mask_disp].sum())
        s_cautela = int(qtd_series[st_op == 'EM CAUTELA'].sum())
        s_manut = int(qtd_series[(st_op == 'EM MANUTENÇÃO') | (cd_fi == 'EM MANUTENÇÃO')].sum())
        s_insp = int(qtd_series[(st_op == 'EM INSPEÇÃO') | (cd_fi == 'EM INSPEÇÃO')].sum())
        s_defeito = int(qtd_series[(cd_fi == 'COM DEFEITO') | (st_op == 'BLOQUEADO')].sum())
        s_segreg = int(qtd_series[cd_fi == 'SEGREGADO'].sum())
        s_obsoleto = int(qtd_series[cd_fi == 'OBSOLETO'].sum())
        s_descarte = int(qtd_series[(st_op == 'AGUARDANDO DESCARTE') | (cd_fi == 'DESCARTE')].sum())
    else:
        total_fisico = s_disp = s_cautela = s_manut = s_insp = s_defeito = s_segreg = s_obsoleto = s_descarte = 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📦 TOTAL FÍSICO", total_fisico)
    c2.metric("🟢 DISPONÍVEL (Aprovadas)", s_disp, help="Apenas ferramentas aprovadas e prontas para nova entrega")
    c3.metric("🔵 EM CAUTELA", s_cautela)
    c4.metric("🟡 EM INSPEÇÃO", s_insp)
    c5.metric("🟠 EM MANUTENÇÃO", s_manut)

    c6, c7, c8, c9 = st.columns(4)
    c6.metric("🔴 COM DEFEITO / BLOQ.", s_defeito)
    c7.metric("🟣 SEGREGADO", s_segreg)
    c8.metric("⚪ OBSOLETO", s_obsoleto)
    c9.metric("🗑️ AGUARDANDO DESCARTE", s_descarte)

    st.markdown(
        "<div style='background-color:#f8f9fa; padding:6px 12px; border-radius:6px; font-size:0.80rem; margin-bottom:12px; border:1px solid #e9ecef;'>"
        "<b>Legenda de Alertas Operacionais:</b> &nbsp; "
        "🟢 <b>Verde:</b> Disponível &nbsp;|&nbsp; "
        "🔵 <b>Azul:</b> Em Cautela &nbsp;|&nbsp; "
        "🟡 <b>Amarelo:</b> Em Inspeção &nbsp;|&nbsp; "
        "🟠 <b>Laranja:</b> Em Manutenção &nbsp;|&nbsp; "
        "🔴 <b>Vermelho:</b> Defeito / Bloqueado &nbsp;|&nbsp; "
        "⚪ <b>Cinza:</b> Obsoleto / Descarte"
        "</div>",
        unsafe_allow_html=True
    )

    abas_fer = [
        "📋 Base: Controle de Ferramentas Usadas",
        "➕ Cadastrar / Receber Ferramenta (ID FER)",
        "📜 Histórico de Movimentos",
        "📥 Importar / Exportar & Backup"
    ]
    if st.session_state.perfil == 'Master':
        abas_fer.append("❌ Excluir Registos (Master)")

    tabs = st.tabs(abas_fer)

    with tabs[0]:
        with st.expander("👁️ Filtros e Colunas Visíveis", expanded=False):
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                fil_st = st.selectbox("Status Operacional:", ["Todos"] + LISTA_STATUS_OPERACIONAL)
            with f2:
                fil_cd = st.selectbox("Condição Física:", ["Todas"] + LISTA_CONDICAO_FISICA)
            with f3:
                fil_loc = st.selectbox("Localização:", ["Todas"] + LISTA_LOCALIZACOES_FER)
            with f4:
                fil_txt = st.text_input("Buscar (ID FER, Cód D365, Descrição, Responsável):")

            st.multiselect(
                "Ocultar ou Mostrar Colunas (Salvo automaticamente na nuvem):",
                options=COLUNAS_FERRAMENTAS,
                default=st.session_state.saved_cols_fer,
                key="ms_fer_key",
                on_change=update_cols_fer
            )

        cols_exibir = st.session_state.saved_cols_fer if st.session_state.saved_cols_fer else COLUNAS_FERRAMENTAS

        if not df_fer.empty:
            df_view = df_fer.copy()
            if fil_st != "Todos":
                df_view = df_view[df_view['status_operacional'] == fil_st]
            if fil_cd != "Todas":
                df_view = df_view[df_view['condicao_fisica'] == fil_cd]
            if fil_loc != "Todas":
                df_view = df_view[df_view['localizacao'] == fil_loc]
            if fil_txt.strip():
                termo = fil_txt.strip().lower()
                mask = df_view.astype(str).apply(lambda x: x.str.lower().str.contains(termo, na=False)).any(axis=1)
                df_view = df_view[mask]

            df_view_display = df_view[cols_exibir].copy()
            df_view_display.insert(0, "Alerta", df_view.apply(lambda r: formatar_badge_alerta(r['status_operacional'], r['condicao_fisica']), axis=1))
            st.dataframe(df_view_display, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma ferramenta usada cadastrada ainda. Utilize a aba '➕ Cadastrar / Receber Ferramenta' ao lado.")

    with tabs[1]:
        st.subheader("➕ Recebimento / Cadastro de Ferramenta Usada")
        prox_id = gerar_proximo_id_fer(df_fer)
        st.info(f"💡 **Identificação Individual Automática:** O próximo código físico disponível é **`{prox_id}`**. Um mesmo Código D365 pode possuir diversos IDs FER individuais.")

        with st.form("form_cad_ferramenta"):
            c_a, c_b, c_c, c_d = st.columns(4)
            with c_a:
                id_fer_input = st.text_input("ID Controle (ID FER) *", value=prox_id)
                qtd_clones = st.number_input("Gerar quantos IDs FER iguais? (Lote Individual)", min_value=1, max_value=50, value=1, help="Se colocar 3, o sistema criará 3 registros individuais sequenciais para o mesmo Código D365.")
                cod_d365 = st.text_input("Código D365 (Referência ERP)")
                desc_d365 = st.text_input("Descrição Oficial D365")
                desc_fer = st.text_input("Descrição Operacional da Ferramenta *")
            with c_b:
                categoria = st.text_input("Categoria (Ex: Elétrica, Manual, Medição)")
                marca = st.text_input("Marca")
                modelo = st.text_input("Modelo")
                num_serie = st.text_input("Número de Série")
                patrimonio = st.text_input("Patrimônio (Se aplicável)")
            with c_c:
                quantidade = st.number_input("Quantidade por registro", min_value=1, value=1)
                unidade = st.selectbox("Unidade", ["UN", "PC", "KIT", "CJ", "PAR", "M"])
                cond_fisica = st.selectbox("Condição Física *", LISTA_CONDICAO_FISICA, index=1)
                status_op = st.selectbox("Status Operacional *", LISTA_STATUS_OPERACIONAL, index=0)
                localizacao = st.selectbox("Localização *", LISTA_LOCALIZACOES_FER, index=0)
            with c_d:
                resp_atual = st.text_input("Responsável Atual", value="ALMOXARIFADO")
                projeto = st.text_input("Projeto", value="ESTOQUE USADOS")
                coordenacao = st.text_input("Coordenação", value="LOGÍSTICA")
                val_ref = st.text_input("Valor de Referência (R$)", value="0,00")
                doc_ref = st.text_input("Documento de Referência / NF / Romaneio")

            obs_cad = st.text_area("Observações Técnicas / Estado na Entrada:")

            if st.form_submit_button("💾 Registrar Ferramenta(s) na Base", type="primary"):
                if desc_fer.strip():
                    hoje = datetime.now().strftime('%Y-%m-%d')
                    prox_insp = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
                    novos_registros = []
                    movs_iniciais = []

                    base_num = int(prox_id.replace("FER-", "")) if prox_id.startswith("FER-") and prox_id.replace("FER-", "").isdigit() else 1

                    for i in range(int(qtd_clones)):
                        id_gerado = id_fer_input.strip().upper() if int(qtd_clones) == 1 else f"FER-{base_num + i:06d}"
                        novos_registros.append({
                            'id_controle': id_gerado,
                            'codigo_d365': cod_d365.strip(),
                            'descricao_d365': desc_d365.strip(),
                            'descricao_ferramenta': desc_fer.strip(),
                            'categoria': categoria.strip(),
                            'marca': marca.strip(),
                            'modelo': modelo.strip(),
                            'numero_serie': num_serie.strip() if int(qtd_clones) == 1 else "",
                            'patrimonio': patrimonio.strip() if int(qtd_clones) == 1 else "",
                            'quantidade': str(quantidade),
                            'unidade': unidade,
                            'condicao_fisica': cond_fisica,
                            'status_operacional': status_op,
                            'localizacao': localizacao,
                            'responsavel_atual': resp_atual.strip(),
                            'matricula': '',
                            'projeto': projeto.strip(),
                            'coordenacao': coordenacao.strip(),
                            'data_entrada': hoje,
                            'data_entrega': '',
                            'data_devolucao': '',
                            'ultima_movimentacao': hoje,
                            'dias_sem_movimentacao': '0',
                            'data_ultima_inspecao': hoje,
                            'proxima_inspecao': prox_insp,
                            'valor_referencia': val_ref.strip(),
                            'custo_acumulado_manutencao': '0.00',
                            'quantidade_manutencoes': '0',
                            'motivo_segregacao': '',
                            'destinacao_final': '',
                            'documento_referencia': doc_ref.strip(),
                            'observacoes': obs_cad.strip()
                        })
                        movs_iniciais.append({
                            'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i+1}",
                            'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'id_fer': id_gerado,
                            'codigo_d365': cod_d365.strip(),
                            'tipo_movimento': 'ENTRADA',
                            'localizacao_origem': 'EXTERNO / CAMPO',
                            'localizacao_destino': localizacao,
                            'responsavel_origem': 'DEVOLUÇÃO / RECUPERAÇÃO',
                            'responsavel_destino': resp_atual.strip(),
                            'projeto': projeto.strip(),
                            'quantidade': str(quantidade),
                            'documento': doc_ref.strip(),
                            'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                            'observacao': f"Cadastro inicial ({cond_fisica} / {status_op})"
                        })

                    try:
                        supabase.table('ferramentas_usadas').upsert(novos_registros).execute()
                        supabase.table('mov_ferramentas').insert(movs_iniciais).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria("CADASTRO FERRAMENTA", novos_registros[0]['id_controle'], f"{len(novos_registros)} ferramenta(s) registrada(s): {desc_fer.strip()}")
                        st.success(f"✅ {len(novos_registros)} ferramenta(s) registrada(s) com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar no Supabase: {e}")
                else:
                    st.error("Preencha a 'Descrição Operacional da Ferramenta'.")

    with tabs[2]:
        st.subheader("📜 Histórico Completo de Movimentações do Ferramental")
        st.dataframe(df_mov_fer, use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader("📤 Exportar Relatórios do Ferramental (.xlsx)")
        stamp = datetime.now().strftime('%Y%m%d_%H%M')
        ce1, ce2, ce3 = st.columns(3)
        with ce1:
            st.download_button("📥 Base Ferramentas Usadas (.xlsx)", data=converter_df_excel_simples(df_fer, "Ferramentas_Usadas"), file_name=f"Controle_Ferramentas_Usadas_{stamp}.xlsx", use_container_width=True)
            st.download_button("📥 Histórico Movimentos (.xlsx)", data=converter_df_excel_simples(df_mov_fer, "Mov_Ferramentas"), file_name=f"Movimentos_Ferramentas_{stamp}.xlsx", use_container_width=True)
        with ce2:
            st.download_button("📥 Controle de Cautelas (.xlsx)", data=converter_df_excel_simples(df_caut_fer, "Cautelas"), file_name=f"Cautelas_Ferramentas_{stamp}.xlsx", use_container_width=True)
            st.download_button("📥 Histórico Manutenções (.xlsx)", data=converter_df_excel_simples(df_manut_fer, "Manutencoes"), file_name=f"Manutencoes_Ferramentas_{stamp}.xlsx", use_container_width=True)
        with ce3:
            st.download_button("📥 Obsolescência e Baixas (.xlsx)", data=converter_df_excel_simples(df_baixa_fer, "Baixas_Descarte"), file_name=f"Baixas_Ferramentas_{stamp}.xlsx", use_container_width=True)
            bkp_fer = gerar_backup_completo_excel({
                "Ferramentas_Usadas": df_fer,
                "Movimentacoes": df_mov_fer,
                "Cautelas": df_caut_fer,
                "Manutencoes": df_manut_fer,
                "Baixas_Descarte": df_baixa_fer,
                "Conciliacao_D365": df_conc_d365
            })
            st.download_button("📦 Backup Completo Ferramental", data=bkp_fer, file_name=f"Backup_Ferramental_Procisa_{stamp}.xlsx", type="primary", use_container_width=True)

        st.divider()
        st.subheader("📥 Importar Planilha de Ferramentas Usadas (.xlsx)")
        st.info("💡 A ferramenta reconhece automaticamente o padrão **MASSIVO FERRAMENTAL** (Número do item, Nome do produto, Pesquisar nome, Total, etc) ou o padrão da própria ferramenta (exportado acima). O que faltar pode ser deixado em branco para edição manual depois.")
        
        arq_fer = st.file_uploader("Arraste a planilha Excel com a relação de ferramentas (.xlsx)", type=["xlsx"], key="up_fer_mass")
        if arq_fer:
            try:
                df_up_f = pd.read_excel(arq_fer)
                df_up_f.columns = [normalizar_nome_coluna(c) for c in df_up_f.columns]
                
                # MAPEAMENTO DO PADRÃO "MASSIVO FERRAMENTAL"
                de_para_massivo = {
                    'numero_do_item': 'codigo_d365',
                    'nome_do_produto': 'descricao_d365',
                    'pesquisar_nome': 'descricao_ferramenta',
                    'total': 'quantidade',
                    'serial': 'numero_serie',
                    'status': 'condicao_fisica'
                }
                df_up_f = df_up_f.rename(columns=de_para_massivo)
                
                # Endereçamentos físicos da planilha massiva vão para observações para controle logístico
                if 'enderecamento_01' in df_up_f.columns or 'enderecamento_02' in df_up_f.columns:
                    e1 = df_up_f.get('enderecamento_01', pd.Series(['']*len(df_up_f))).fillna('').astype(str)
                    e2 = df_up_f.get('enderecamento_02', pd.Series(['']*len(df_up_f))).fillna('').astype(str)
                    df_up_f['observacoes'] = "Endereço: " + e1 + " / " + e2
                
                # Preenche valores que vieram em branco com o padrão operacional
                if 'condicao_fisica' not in df_up_f.columns:
                    df_up_f['condicao_fisica'] = 'USADO - BOM'
                else:
                    df_up_f['condicao_fisica'] = df_up_f['condicao_fisica'].fillna('USADO - BOM')
                    
                if 'status_operacional' not in df_up_f.columns:
                    df_up_f['status_operacional'] = 'DISPONÍVEL'
                    
                if 'localizacao' not in df_up_f.columns:
                    df_up_f['localizacao'] = 'USADO-DISP'
                    
                if 'quantidade' not in df_up_f.columns:
                    df_up_f['quantidade'] = '1'
                
                # Limpa N/A ou Vazio de Marca, Modelo, Serie para evitar bugs na exibição
                for c_limpar in ['marca', 'modelo', 'numero_serie', 'categoria', 'projeto', 'coordenacao']:
                    if c_limpar in df_up_f.columns:
                        df_up_f[c_limpar] = df_up_f[c_limpar].fillna('')
                
                # Gera o ID Controle (FER-000000) sequencial para as linhas importadas
                base_n = 0
                if not df_fer.empty and 'id_controle' in df_fer.columns:
                    for val in df_fer['id_controle'].astype(str):
                        val_limpo = val.strip().upper()
                        if val_limpo.startswith("FER-"):
                            num_str = val_limpo.replace("FER-", "").strip()
                            if num_str.isdigit():
                                base_n = max(base_n, int(num_str))
                
                if 'id_controle' not in df_up_f.columns:
                    df_up_f['id_controle'] = [f"FER-{base_n + idx + 1:06d}" for idx in range(len(df_up_f))]
                else:
                    # Se tiver a coluna mas ela estiver vazia em algum ponto
                    faltantes_mask = df_up_f['id_controle'].isnull() | (df_up_f['id_controle'] == '')
                    novos_ids = [f"FER-{base_n + idx + 1:06d}" for idx in range(faltantes_mask.sum())]
                    df_up_f.loc[faltantes_mask, 'id_controle'] = novos_ids
                
                # Parametrização inicial de cadastro
                df_up_f['responsavel_atual'] = 'ALMOXARIFADO'
                df_up_f['data_entrada'] = datetime.now().strftime('%Y-%m-%d')
                df_up_f['ultima_movimentacao'] = datetime.now().strftime('%Y-%m-%d')
                df_up_f['dias_sem_movimentacao'] = '0'

                st.caption(f"Leitura concluída. Identificação do Padrão Massivo efetuada. Pré-visualização ({len(df_up_f)} itens):")
                st.dataframe(df_up_f[['id_controle', 'codigo_d365', 'descricao_ferramenta', 'quantidade', 'condicao_fisica']].head(5), use_container_width=True)
                
                if st.button("🚀 Confirmar Importação de Ferramentas", type="primary"):
                    with st.spinner("Enviando ferramentas para o Supabase..."):
                        if salvar_dados_massa('ferramentas_usadas', df_up_f, COLUNAS_FERRAMENTAS):
                            registrar_log_auditoria("UPLOAD FERRAMENTAL", arq_fer.name, f"{len(df_up_f)} ferramentas importadas (Padrão Massivo).")
                            st.success("✅ Ferramentas importadas com sucesso!")
                            st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar planilha: {e}")

    if st.session_state.perfil == 'Master':
        with tabs[4]:
            st.subheader("❌ Exclusão de Ferramentas por Seleção (Master)")
            if not df_fer.empty:
                df_del_f = df_fer[['id_controle', 'codigo_d365', 'descricao_ferramenta', 'condicao_fisica', 'status_operacional', 'localizacao', 'responsavel_atual']].copy()
                df_del_f.insert(0, "Excluir", False)
                df_ed_f = st.data_editor(
                    df_del_f,
                    hide_index=True,
                    use_container_width=True,
                    disabled=[c for c in df_del_f.columns if c != "Excluir"],
                    column_config={"Excluir": st.column_config.CheckboxColumn("🗑️ Excluir?", default=False)},
                    key="ed_del_fer"
                )
                sel_f = df_ed_f[df_ed_f["Excluir"] == True]
                if not sel_f.empty:
                    if st.button(f"🗑️ Confirmar Exclusão de {len(sel_f)} Ferramenta(s)", type="primary"):
                        for id_f in sel_f['id_controle'].tolist():
                            supabase.table('ferramentas_usadas').delete().eq('id_controle', id_f).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria("EXCLUSÃO FERRAMENTAL", f"{len(sel_f)} itens", "Ferramentas excluídas pelo Master.")
                        st.success("✅ Registos removidos!")
                        st.rerun()
            else:
                st.info("Base vazia.")

    exibir_marca_desenvolvedor()

# ==========================================
# F2: FLUXO DE INSPEÇÃO, TRIAGEM E MOVIMENTAÇÃO
# ==========================================
def render_inspecao_movimentacao_fer(df_fer):
    st.header("🔍 Fluxo de Inspeção, Classificação e Endereçamento")
    st.markdown(
        "**Fluxo Operacional Padronizado:** `DEVOLUÇÃO` → `RECEBIMENTO` → `INSPEÇÃO` → `CLASSIFICAÇÃO` → `IDENTIFICAÇÃO` → `ENDEREÇAMENTO` → `DECISÃO`"
    )

    aba_triagem, aba_mov_geral = st.tabs([
        "🟡 Fila de Inspeção e Decisão Técnica",
        "🔄 Movimentação / Transferência Rápida"
    ])

    with aba_triagem:
        if not df_fer.empty:
            mask_triagem = (
                df_fer['status_operacional'].isin(['EM INSPEÇÃO', 'AGUARDANDO DECISÃO', 'BLOQUEADO']) |
                df_fer['condicao_fisica'].isin(['EM INSPEÇÃO', 'COM DEFEITO'])
            )
            df_fila_insp = df_fer[mask_triagem].copy()
        else:
            df_fila_insp = pd.DataFrame()

        st.markdown("###### 📋 Ferramentas Aguardando Inspeção ou Decisão")
        if not df_fila_insp.empty:
            st.dataframe(df_fila_insp[['id_controle', 'codigo_d365', 'descricao_ferramenta', 'condicao_fisica', 'status_operacional', 'localizacao', 'ultima_movimentacao']], use_container_width=True, hide_index=True)
        else:
            st.success("🎉 Nenhuma ferramenta travada na fila de inspeção no momento. Você ainda pode inspecionar qualquer ID FER buscando abaixo.")

        busca_insp = st.text_input("🔍 Digite o ID FER (ex: FER-000001), Código D365 ou Série para Inspecionar / Decidir:")
        fer_match = buscar_ferramenta(busca_insp, df_fer) if busca_insp else pd.DataFrame()

        if not fer_match.empty:
            reg = fer_match.iloc[0].to_dict()
            id_fer_real = reg['id_controle']
            st.info(
                f"**Selecionado:** `{id_fer_real}` — {reg.get('descricao_ferramenta')} | "
                f"**Condição Atual:** {reg.get('condicao_fisica')} | **Status Atual:** {reg.get('status_operacional')} | **Local:** {reg.get('localizacao')}"
            )

            decisao = st.radio(
                "Selecione a Decisão da Inspeção (Regra de Fluxo Item 6):",
                [
                    "🟢 1. APROVAR (USADO - BOM/REGULAR → DISPONÍVEL em USADO-DISP)",
                    "🟠 2. ENVIAR PARA MANUTENÇÃO (EM MANUTENÇÃO → Bloqueada para entrega em USADO-MANUT)",
                    "🔴 3. REPROVAR / COM DEFEITO (COM DEFEITO → BLOQUEADO em USADO-DEFEITO)",
                    "⚪ 4. SEGREGAR / OBSOLETO (Inviável recuperação → SEGREGADO/OBSOLETO para Baixa/Descarte)"
                ]
            )

            with st.form("form_decisao_inspecao"):
                c1, c2 = st.columns(2)
                with c1:
                    if decisao.startswith("🟢"):
                        cond_sug = st.selectbox("Classificação Física:", ["USADO - BOM", "USADO - REGULAR", "NOVO"])
                        st_sug = "DISPONÍVEL"
                        loc_sug = "USADO-DISP"
                        tipo_mv = "LIBERAÇÃO"
                    elif decisao.startswith("🟠"):
                        cond_sug = "EM MANUTENÇÃO"
                        st_sug = "EM MANUTENÇÃO"
                        loc_sug = "USADO-MANUT"
                        tipo_mv = "ENVIO PARA MANUTENÇÃO"
                    elif decisao.startswith("🔴"):
                        cond_sug = "COM DEFEITO"
                        st_sug = "BLOQUEADO"
                        loc_sug = "USADO-DEFEITO"
                        tipo_mv = "SEGREGAÇÃO"
                    else:
                        cond_sug = st.selectbox("Classificação Física:", ["SEGREGADO", "OBSOLETO", "DESCARTE"])
                        st_sug = "AGUARDANDO DESCARTE" if cond_sug != "SEGREGADO" else "AGUARDANDO DECISÃO"
                        loc_sug = "USADO-SEGREGADO" if cond_sug == "SEGREGADO" else "USADO-OBSOLETO"
                        tipo_mv = "SEGREGAÇÃO"

                    st.text_input("Novo Status Operacional (Automático):", value=st_sug, disabled=True)
                with c2:
                    loc_final = st.selectbox("Endereço / Localização Destino:", LISTA_LOCALIZACOES_FER, index=LISTA_LOCALIZACOES_FER.index(loc_sug))
                    prox_insp_dt = st.date_input("Próxima Inspeção Programada:", datetime.today() + timedelta(days=90))

                obs_insp = st.text_area("Laudo Rápido / Observação da Inspeção:")

                if st.form_submit_button("✅ Aplicar Classificação e Endereçamento", type="primary"):
                    hoje_str = datetime.now().strftime('%Y-%m-%d')
                    upd = {
                        'condicao_fisica': cond_sug,
                        'status_operacional': st_sug,
                        'localizacao': loc_final,
                        'data_ultima_inspecao': hoje_str,
                        'proxima_inspecao': prox_insp_dt.strftime('%Y-%m-%d'),
                        'ultima_movimentacao': hoje_str,
                        'dias_sem_movimentacao': '0'
                    }
                    if obs_insp.strip():
                        upd['observacoes'] = obs_insp.strip()
                    if decisao.startswith("⚪"):
                        upd['motivo_segregacao'] = obs_insp.strip()

                    mov_log = {
                        'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'id_fer': id_fer_real,
                        'codigo_d365': reg.get('codigo_d365', ''),
                        'tipo_movimento': tipo_mv,
                        'localizacao_origem': reg.get('localizacao', ''),
                        'localizacao_destino': loc_final,
                        'responsavel_origem': reg.get('responsavel_atual', ''),
                        'responsavel_destino': 'ALMOXARIFADO / TRIAGEM',
                        'projeto': reg.get('projeto', ''),
                        'quantidade': reg.get('quantidade', '1'),
                        'documento': reg.get('documento_referencia', ''),
                        'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                        'observacao': f"Inspeção: {cond_sug} -> {st_sug}. {obs_insp.strip()}"
                    }
                    try:
                        supabase.table('ferramentas_usadas').update(upd).eq('id_controle', id_fer_real).execute()
                        supabase.table('mov_ferramentas').insert(mov_log).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria("INSPEÇÃO FERRAMENTA", id_fer_real, f"Classificada como {cond_sug} / {st_sug} em {loc_final}")
                        st.success(f"✅ Ferramenta {id_fer_real} atualizada para {st_sug} ({loc_final})!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao gravar inspeção: {e}")

    with aba_mov_geral:
        st.subheader("🔄 Registrar Movimento Operacional")
        busca_mv = st.text_input("🔍 Buscar Ferramenta (ID FER, Código D365 ou Série):", key="b_mv_fer")
        f_mv = buscar_ferramenta(busca_mv, df_fer) if busca_mv else pd.DataFrame()

        if not f_mv.empty:
            r_mv = f_mv.iloc[0].to_dict()
            id_f = r_mv['id_controle']
            st.success(f"**Ferramenta:** `{id_f}` - {r_mv.get('descricao_ferramenta')} | Local Atual: `{r_mv.get('localizacao')}` | Status: `{r_mv.get('status_operacional')}`")

            with st.form("form_mov_fer_avulso"):
                cm1, cm2, cm3 = st.columns(3)
                with cm1:
                    t_mov = st.selectbox("Tipo de Movimento:", LISTA_TIPOS_MOV_FER)
                    loc_dest = st.selectbox("Localização Destino:", LISTA_LOCALIZACOES_FER)
                with cm2:
                    idx_st = LISTA_STATUS_OPERACIONAL.index(r_mv['status_operacional']) if r_mv['status_operacional'] in LISTA_STATUS_OPERACIONAL else 0
                    idx_cd = LISTA_CONDICAO_FISICA.index(r_mv['condicao_fisica']) if r_mv['condicao_fisica'] in LISTA_CONDICAO_FISICA else 1
                    st_novo = st.selectbox("Novo Status Operacional:", LISTA_STATUS_OPERACIONAL, index=idx_st)
                    cd_nova = st.selectbox("Condição Física:", LISTA_CONDICAO_FISICA, index=idx_cd)
                with cm3:
                    resp_dest = st.text_input("Responsável Destino:", value=r_mv.get('responsavel_atual', 'ALMOXARIFADO'))
                    proj_dest = st.text_input("Projeto:", value=r_mv.get('projeto', ''))
                    doc_mv = st.text_input("Documento / Romaneio:")

                obs_mv = st.text_input("Observação do Movimento:")

                if st.form_submit_button("🚀 Confirmar Movimento", type="primary"):
                    hoje_s = datetime.now().strftime('%Y-%m-%d')
                    upd_f = {
                        'localizacao': loc_dest,
                        'status_operacional': st_novo,
                        'condicao_fisica': cd_nova,
                        'responsavel_atual': resp_dest.strip(),
                        'projeto': proj_dest.strip(),
                        'ultima_movimentacao': hoje_s,
                        'dias_sem_movimentacao': '0'
                    }
                    novo_m = {
                        'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'id_fer': id_f,
                        'codigo_d365': r_mv.get('codigo_d365', ''),
                        'tipo_movimento': t_mov,
                        'localizacao_origem': r_mv.get('localizacao', ''),
                        'localizacao_destino': loc_dest,
                        'responsavel_origem': r_mv.get('responsavel_atual', ''),
                        'responsavel_destino': resp_dest.strip(),
                        'projeto': proj_dest.strip(),
                        'quantidade': r_mv.get('quantidade', '1'),
                        'documento': doc_mv.strip(),
                        'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                        'observacao': obs_mv.strip()
                    }
                    supabase.table('ferramentas_usadas').update(upd_f).eq('id_controle', id_f).execute()
                    supabase.table('mov_ferramentas').insert(novo_m).execute()
                    st.cache_data.clear()
                    registrar_log_auditoria(f"MOV. FERRAMENTA ({t_mov})", id_f, f"De {r_mv.get('localizacao')} para {loc_dest}")
                    st.success("✅ Movimentação registrada!")
                    st.rerun()

    exibir_marca_desenvolvedor()

# ==========================================
# F3: CONTROLE DE CAUTELA DE FERRAMENTAS
# ==========================================
def render_cautela_ferramentas(df_fer, df_caut_fer, df_empregados):
    st.header("👷 Controle de Cautela (Entrega e Devolução de Ferramentas)")
    st.caption("Regra Operacional (Item 4): Somente ferramentas aprovadas e classificadas como DISPONÍVEL podem ser entregues em nova cautela.")

    if st.session_state.get('pdf_cautela_fer'):
        st.success("✅ Cautela registrada! Baixe o Termo de Responsabilidade abaixo:")
        st.download_button(
            "📥 Baixar Termo de Cautela PDF (PROCISA)",
            data=st.session_state.pdf_cautela_fer['bytes'],
            file_name=st.session_state.pdf_cautela_fer['nome'],
            mime="application/pdf",
            type="primary"
        )
        if st.button("✖️ Fechar PDF"):
            st.session_state.pdf_cautela_fer = None
            st.rerun()
        st.divider()

    aba_entrega, aba_devolucao, aba_hist_caut = st.tabs([
        "📤 Nova Entrega / Cautela (Apenas Disponíveis)",
        "📥 Registrar Devolução de Cautela",
        "📋 Histórico Geral de Cautelas"
    ])

    with aba_entrega:
        fer_disponiveis = df_fer[
            (df_fer['status_operacional'] == 'DISPONÍVEL') &
            (df_fer['condicao_fisica'].isin(['NOVO', 'USADO - BOM', 'USADO - REGULAR']))
        ].copy() if not df_fer.empty else pd.DataFrame()

        if fer_disponiveis.empty:
            st.warning("⚠️ Não há ferramentas com status 'DISPONÍVEL' e aprovadas na inspeção no momento.")
        else:
            c_b1, c_b2 = st.columns(2)
            with c_b1:
                opcoes_f = fer_disponiveis.apply(
                    lambda r: f"{r['id_controle']} | D365: {r['codigo_d365']} | {r['descricao_ferramenta']} ({r['condicao_fisica']})", axis=1
                ).tolist()
                sel_fer_str = st.selectbox("1️⃣ Selecione a Ferramenta Disponível:", opcoes_f)
                id_fer_sel = sel_fer_str.split(" | ")[0]
                reg_f = fer_disponiveis[fer_disponiveis['id_controle'] == id_fer_sel].iloc[0].to_dict()
            with c_b2:
                mat_busca = st.text_input("2️⃣ Digite a Matrícula do Colaborador e pressione Enter:")
                mat_limpa = limpar_texto_matricula(mat_busca)
                emp_info = {}
                if mat_limpa and not df_empregados.empty:
                    m_e = df_empregados[df_empregados['matricula'].astype(str) == mat_limpa]
                    if not m_e.empty:
                        emp_info = m_e.iloc[0].fillna("").to_dict()
                        st.success(f"👤 Colaborador: **{emp_info.get('nome')}** | Projeto: {emp_info.get('projeto')} | Unidade: {emp_info.get('unidade')}")
                    else:
                        st.warning("⚠️ Matrícula não localizada na base de colaboradores. Preencha abaixo.")

            with st.form("form_nova_cautela_fer"):
                cc1, cc2, cc3 = st.columns(3)
                with cc1:
                    col_nome = st.text_input("Colaborador *", value=emp_info.get('nome', ''))
                    col_mat = st.text_input("Matrícula *", value=mat_limpa)
                with cc2:
                    col_proj = st.text_input("Projeto *", value=emp_info.get('projeto', ''))
                    col_coord = st.text_input("Coordenação / Unidade *", value=emp_info.get('unidade', ''))
                with cc3:
                    dt_ent = st.date_input("Data da Entrega", datetime.today())
                    dt_prev = st.date_input("Data Prevista de Devolução", datetime.today() + timedelta(days=30))

                obs_caut = st.text_input("Observações da Entrega:")
                gerar_pdf_chk = st.checkbox("Gerar Termo de Responsabilidade em PDF (FR-RH-P-026)", value=True)

                if st.form_submit_button("🚀 Confirmar Cautela e Entregar Ferramenta", type="primary"):
                    if col_nome.strip():
                        id_caut = f"CAU-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        hoje_s = dt_ent.strftime('%Y-%m-%d')
                        nova_caut = {
                            'id_cautela': id_caut,
                            'id_fer': id_fer_sel,
                            'codigo_d365': reg_f.get('codigo_d365', ''),
                            'colaborador': col_nome.strip(),
                            'matricula': col_mat.strip(),
                            'projeto': col_proj.strip(),
                            'coordenacao': col_coord.strip(),
                            'data_entrega': hoje_s,
                            'condicao_entrega': reg_f.get('condicao_fisica', 'USADO - BOM'),
                            'data_prevista_devolucao': dt_prev.strftime('%Y-%m-%d'),
                            'data_efetiva_devolucao': '',
                            'condicao_devolucao': '',
                            'status': 'EM CAUTELA',
                            'observacao': obs_caut.strip()
                        }
                        upd_fer = {
                            'status_operacional': 'EM CAUTELA',
                            'localizacao': 'CAMPO / COLABORADOR',
                            'responsavel_atual': col_nome.strip(),
                            'matricula': col_mat.strip(),
                            'projeto': col_proj.strip(),
                            'coordenacao': col_coord.strip(),
                            'data_entrega': hoje_s,
                            'ultima_movimentacao': hoje_s,
                            'dias_sem_movimentacao': '0'
                        }
                        mov_caut = {
                            'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'id_fer': id_fer_sel,
                            'codigo_d365': reg_f.get('codigo_d365', ''),
                            'tipo_movimento': 'CAUTELA',
                            'localizacao_origem': reg_f.get('localizacao', 'USADO-DISP'),
                            'localizacao_destino': 'CAMPO / COLABORADOR',
                            'responsavel_origem': 'ALMOXARIFADO',
                            'responsavel_destino': col_nome.strip(),
                            'projeto': col_proj.strip(),
                            'quantidade': reg_f.get('quantidade', '1'),
                            'documento': id_caut,
                            'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                            'observacao': f"Entrega em cautela para {col_nome.strip()} ({col_mat.strip()})"
                        }
                        supabase.table('cautelas_ferramentas').insert(nova_caut).execute()
                        supabase.table('ferramentas_usadas').update(upd_fer).eq('id_controle', id_fer_sel).execute()
                        supabase.table('mov_ferramentas').insert(mov_caut).execute()

                        if gerar_pdf_chk:
                            df_fake_ativo = pd.DataFrame([{
                                'equipamento': reg_f.get('descricao_ferramenta', ''),
                                'marca': reg_f.get('marca', ''),
                                'modelo': reg_f.get('modelo', ''),
                                'numero_serie': reg_f.get('numero_serie', id_fer_sel),
                                'condicoes_para_uso': reg_f.get('condicao_fisica', ''),
                                'acessorios': f"Cód D365: {reg_f.get('codigo_d365', '')} | {obs_caut.strip()}",
                                'coordenacao': col_coord.strip(),
                                'nf_procisa': reg_f.get('documento_referencia', '')
                            }])
                            caminho = gerar_termo_pdf(
                                id_fer_sel, col_nome.strip(), col_mat.strip(),
                                emp_info.get('cpf', ''), emp_info.get('rg', ''),
                                col_proj.strip(), col_coord.strip(), df_fake_ativo
                            )
                            with open(caminho, "rb") as f_pdf:
                                st.session_state.pdf_cautela_fer = {
                                    'bytes': f_pdf.read(),
                                    'nome': f"Termo_Ferramenta_{id_fer_sel}.pdf"
                                }

                        st.cache_data.clear()
                        registrar_log_auditoria("CAUTELA FERRAMENTA", id_fer_sel, f"Entregue para {col_nome.strip()}")
                        st.rerun()
                    else:
                        st.error("Informe o nome do colaborador.")

    with aba_devolucao:
        cautelas_ativas = df_caut_fer[df_caut_fer['status'] == 'EM CAUTELA'].copy() if not df_caut_fer.empty else pd.DataFrame()
        if cautelas_ativas.empty:
            st.success("🎉 Nenhuma ferramenta pendente de devolução no momento.")
        else:
            st.dataframe(cautelas_ativas[['id_cautela', 'id_fer', 'codigo_d365', 'colaborador', 'matricula', 'projeto', 'data_entrega', 'data_prevista_devolucao']], use_container_width=True, hide_index=True)
            op_dev = cautelas_ativas.apply(lambda r: f"{r['id_cautela']} | {r['id_fer']} - {r['colaborador']}", axis=1).tolist()
            sel_dev = st.selectbox("Selecione a Cautela para Devolução:", op_dev)
            id_caut_dev = sel_dev.split(" | ")[0]
            reg_c = cautelas_ativas[cautelas_ativas['id_cautela'] == id_caut_dev].iloc[0].to_dict()

            with st.form("form_dev_cautela"):
                cd1, cd2, cd3 = st.columns(3)
                with cd1:
                    cond_dev = st.selectbox("Condição na Devolução:", LISTA_CONDICAO_FISICA, index=3)
                with cd2:
                    st_pos_dev = st.selectbox("Status Após Devolução (Fluxo: Recebimento -> Inspeção):", ["EM INSPEÇÃO", "DISPONÍVEL", "EM MANUTENÇÃO", "BLOQUEADO"], index=0)
                with cd3:
                    loc_pos_dev = st.selectbox("Localização de Recebimento:", LISTA_LOCALIZACOES_FER, index=1)

                obs_dev = st.text_input("Observação no Recebimento / Avarias:")

                if st.form_submit_button("📥 Confirmar Devolução e Enviar para Triagem", type="primary"):
                    hoje_d = datetime.now().strftime('%Y-%m-%d')
                    id_f_dev = reg_c['id_fer']
                    supabase.table('cautelas_ferramentas').update({
                        'data_efetiva_devolucao': hoje_d,
                        'condicao_devolucao': cond_dev,
                        'status': 'DEVOLVIDO',
                        'observacao': obs_dev.strip()
                    }).eq('id_cautela', id_caut_dev).execute()

                    supabase.table('ferramentas_usadas').update({
                        'condicao_fisica': cond_dev,
                        'status_operacional': st_pos_dev,
                        'localizacao': loc_pos_dev,
                        'responsavel_atual': 'ALMOXARIFADO',
                        'matricula': '',
                        'data_devolucao': hoje_d,
                        'ultima_movimentacao': hoje_d,
                        'dias_sem_movimentacao': '0'
                    }).eq('id_controle', id_f_dev).execute()

                    supabase.table('mov_ferramentas').insert({
                        'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'id_fer': id_f_dev,
                        'codigo_d365': reg_c.get('codigo_d365', ''),
                        'tipo_movimento': 'DEVOLUÇÃO',
                        'localizacao_origem': 'CAMPO / COLABORADOR',
                        'localizacao_destino': loc_pos_dev,
                        'responsavel_origem': reg_c.get('colaborador', ''),
                        'responsavel_destino': 'ALMOXARIFADO',
                        'projeto': reg_c.get('projeto', ''),
                        'quantidade': '1',
                        'documento': id_caut_dev,
                        'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                        'observacao': f"Devolução de cautela ({cond_dev}). {obs_dev.strip()}"
                    }).execute()

                    st.cache_data.clear()
                    registrar_log_auditoria("DEVOLUÇÃO FERRAMENTA", id_f_dev, f"Devolvida por {reg_c.get('colaborador')} -> {loc_pos_dev}")
                    st.success(f"✅ Ferramenta {id_f_dev} devolvida e encaminhada para {loc_pos_dev}!")
                    st.rerun()

    with aba_hist_caut:
        st.dataframe(df_caut_fer, use_container_width=True, hide_index=True)

    exibir_marca_desenvolvedor()

# ==========================================
# F4: MANUTENÇÃO, OBSOLESCÊNCIA E DESCARTE
# ==========================================
def render_manutencao_baixa_fer(df_fer, df_manut_fer, df_baixa_fer):
    st.header("🔧 Oficina / Manutenção & Controle de Obsolescência e Descarte")

    aba_manut, aba_baixa = st.tabs([
        "🟠 Histórico e Retorno de Manutenção (Item 11)",
        "⚪ Obsolescência, Laudo e Descarte (Item 12)"
    ])

    with aba_manut:
        st.subheader("🔧 Registro de Manutenção e Cálculo Automático de Custo Acumulado")
        busca_m = st.text_input("🔍 Digite o ID FER ou Código D365 da ferramenta:", key="b_manut_f")
        f_m = buscar_ferramenta(busca_m, df_fer) if busca_m else pd.DataFrame()

        if not f_m.empty:
            rm = f_m.iloc[0].to_dict()
            id_f_m = rm['id_controle']
            qtd_m_atual = _parse_int(rm.get('quantidade_manutencoes', '0'), 0)
            custo_m_atual = _parse_float(rm.get('custo_acumulado_manutencao', '0'))

            k1, k2, k3 = st.columns(3)
            k1.metric("Ferramenta Selecionada", f"{id_f_m} ({rm.get('descricao_ferramenta')})")
            k2.metric("Quantidade de Manutenções", qtd_m_atual)
            k3.metric("Custo Acumulado de Manutenção", f"R$ {custo_m_atual:,.2f}")

            with st.form("form_reg_manut"):
                m1, m2, m3 = st.columns(3)
                with m1:
                    dt_envio = st.date_input("Data de Envio", datetime.today())
                    defeito_inf = st.text_input("Defeito Informado *")
                    fornecedor = st.text_input("Fornecedor / Oficina / Laboratório *")
                with m2:
                    num_os = st.text_input("Número da OS")
                    val_manut = st.number_input("Valor da Manutenção (R$)", min_value=0.0, step=10.0, value=0.0)
                    dt_ret = st.date_input("Data de Retorno", datetime.today())
                with m3:
                    resultado_m = st.selectbox("Resultado da Manutenção", ["REPARADO COM SUCESSO", "CALIBRADO / REVISADO", "AGUARDANDO PEÇA", "SEM CONSERTO / INVIÁVEL"])
                    cond_apos = st.selectbox("Condição Após Manutenção", LISTA_CONDICAO_FISICA, index=1)
                    liberado = st.radio("Liberado para Utilização?", ["Sim", "Não"], horizontal=True)

                obs_m = st.text_area("Observações Técnicas da Manutenção:")

                if st.form_submit_button("💾 Registrar Manutenção e Recalcular Custos", type="primary"):
                    if defeito_inf.strip():
                        id_mn = f"MNT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        nova_qtd = qtd_m_atual + 1
                        novo_custo = custo_m_atual + float(val_manut)

                        if liberado == "Sim" and cond_apos in ["NOVO", "USADO - BOM", "USADO - REGULAR"]:
                            novo_st_op = "DISPONÍVEL"
                            nova_loc = "USADO-DISP"
                        elif resultado_m == "SEM CONSERTO / INVIÁVEL":
                            novo_st_op = "AGUARDANDO DECISÃO"
                            nova_loc = "USADO-SEGREGADO"
                        else:
                            novo_st_op = "EM INSPEÇÃO"
                            nova_loc = "USADO-INSPECAO"

                        reg_mnt = {
                            'id_manut': id_mn,
                            'id_fer': id_f_m,
                            'data_envio': dt_envio.strftime('%Y-%m-%d'),
                            'defeito_informado': defeito_inf.strip(),
                            'fornecedor_oficina': fornecedor.strip(),
                            'numero_os': num_os.strip(),
                            'valor_manutencao': f"{val_manut:.2f}",
                            'data_retorno': dt_ret.strftime('%Y-%m-%d'),
                            'resultado': resultado_m,
                            'condicao_apos_manutencao': cond_apos,
                            'liberado_utilizacao': liberado,
                            'observacoes': obs_m.strip()
                        }

                        upd_f_m = {
                            'condicao_fisica': cond_apos,
                            'status_operacional': novo_st_op,
                            'localizacao': nova_loc,
                            'quantidade_manutencoes': str(nova_qtd),
                            'custo_acumulado_manutencao': f"{novo_custo:.2f}",
                            'ultima_movimentacao': dt_ret.strftime('%Y-%m-%d'),
                            'dias_sem_movimentacao': '0'
                        }

                        supabase.table('manutencao_ferramentas').insert(reg_mnt).execute()
                        supabase.table('ferramentas_usadas').update(upd_f_m).eq('id_controle', id_f_m).execute()
                        supabase.table('mov_ferramentas').insert({
                            'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'id_fer': id_f_m,
                            'codigo_d365': rm.get('codigo_d365', ''),
                            'tipo_movimento': 'RETORNO DE MANUTENÇÃO',
                            'localizacao_origem': 'USADO-MANUT',
                            'localizacao_destino': nova_loc,
                            'responsavel_origem': fornecedor.strip(),
                            'responsavel_destino': 'ALMOXARIFADO',
                            'projeto': rm.get('projeto', ''),
                            'quantidade': rm.get('quantidade', '1'),
                            'documento': num_os.strip(),
                            'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                            'observacao': f"OS {num_os}: {resultado_m} | Custo: R$ {val_manut:.2f} | Liberado: {liberado}"
                        }).execute()

                        st.cache_data.clear()
                        registrar_log_auditoria("MANUTENÇÃO FERRAMENTA", id_f_m, f"OS {num_os} registrada. Custo acumulado: R$ {novo_custo:.2f}")
                        st.success(f"✅ Manutenção registrada! Quantidade: {nova_qtd} | Custo Acumulado: R$ {novo_custo:,.2f}")
                        st.rerun()
                    else:
                        st.error("Informe o defeito.")

        st.divider()
        st.markdown("###### 📋 Histórico Geral de Manutenções")
        st.dataframe(df_manut_fer, use_container_width=True, hide_index=True)

    with aba_baixa:
        st.subheader("⚪ Controle de Obsolescência, Viabilidade e Processo de Baixa/Descarte")
        busca_bx = st.text_input("🔍 Digite o ID FER para registrar Segregação / Laudo de Baixa:", key="b_baixa_f")
        f_bx = buscar_ferramenta(busca_bx, df_fer) if busca_bx else pd.DataFrame()

        if not f_bx.empty:
            rbx = f_bx.iloc[0].to_dict()
            id_f_bx = rbx['id_controle']
            st.warning(f"**Ferramenta:** `{id_f_bx}` - {rbx.get('descricao_ferramenta')} | Valor Ref: R$ {rbx.get('valor_referencia', '0')} | Custo Manut. Acumulado: R$ {rbx.get('custo_acumulado_manutencao', '0')}")

            with st.form("form_baixa_descarte"):
                b1, b2, b3 = st.columns(3)
                with b1:
                    cond_bx = st.selectbox("Condição:", ["OBSOLETO", "DESCARTE", "SEGREGADO", "COM DEFEITO"])
                    motivo_bx = st.text_input("Motivo da Segregação / Baixa *")
                    dt_seg = st.date_input("Data da Segregação", datetime.today())
                    laudo_tec = st.text_input("Número / Resumo do Laudo Técnico *")
                with b2:
                    val_ref_bx = st.text_input("Valor de Referência (R$)", value=str(rbx.get('valor_referencia', '0,00')))
                    custo_rec_bx = st.text_input("Custo Estimado de Recuperação (R$)", value="0,00")
                    viabilidade = st.selectbox("Viabilidade de Recuperação:", ["INVIÁVEL ECONOMICAMENTE", "INVIÁVEL TECNICAMENTE", "OBSOLETO TECNOLOGICAMENTE", "EM ANÁLISE"])
                with b3:
                    aprov_bx = st.selectbox("Aprovação para Baixa:", ["AGUARDANDO APROVAÇÃO", "APROVADO PARA BAIXA/DESCARTE", "REJEITADO (RETORNAR)"])
                    dest_final = st.selectbox("Destinação Final:", ["AGUARDANDO", "SUCATA / RECICLAGEM", "DESCARTE AMBIENTAL", "DOAÇÃO", "CANIBALIZAÇÃO DE PEÇAS"])
                    doc_evid = st.text_input("Evidência / Documento de Baixa:")

                obs_bx = st.text_area("Observações Finais:")

                if st.form_submit_button("🗑️ Registrar Processo de Obsolescência / Baixa", type="primary"):
                    if motivo_bx.strip():
                        id_bx = f"BXA-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        aprovado = aprov_bx.startswith("APROVADO")
                        dt_baixa_efetiva = datetime.now().strftime('%Y-%m-%d') if aprovado else ""
                        novo_st_bx = "BAIXADO" if aprovado else "AGUARDANDO DESCARTE"
                        nova_loc_bx = "USADO-DESCARTE" if aprovado else "USADO-OBSOLETO"

                        reg_baixa = {
                            'id_baixa': id_bx,
                            'id_fer': id_f_bx,
                            'codigo_d365': rbx.get('codigo_d365', ''),
                            'condicao': cond_bx,
                            'motivo': motivo_bx.strip(),
                            'data_segregacao': dt_seg.strftime('%Y-%m-%d'),
                            'laudo_tecnico': laudo_tec.strip(),
                            'valor_referencia': val_ref_bx.strip(),
                            'custo_recuperacao': custo_rec_bx.strip(),
                            'viabilidade_recuperacao': viabilidade,
                            'aprovacao_baixa': aprov_bx,
                            'data_baixa': dt_baixa_efetiva,
                            'destinacao': dest_final,
                            'evidencia_documento': doc_evid.strip(),
                            'observacoes': obs_bx.strip()
                        }

                        supabase.table('baixa_ferramentas').insert(reg_baixa).execute()
                        supabase.table('ferramentas_usadas').update({
                            'condicao_fisica': cond_bx,
                            'status_operacional': novo_st_bx,
                            'localizacao': nova_loc_bx,
                            'motivo_segregacao': motivo_bx.strip(),
                            'destinacao_final': dest_final,
                            'ultima_movimentacao': datetime.now().strftime('%Y-%m-%d'),
                            'dias_sem_movimentacao': '0'
                        }).eq('id_controle', id_f_bx).execute()

                        supabase.table('mov_ferramentas').insert({
                            'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'id_fer': id_f_bx,
                            'codigo_d365': rbx.get('codigo_d365', ''),
                            'tipo_movimento': 'BAIXA' if aprovado else 'SEGREGAÇÃO',
                            'localizacao_origem': rbx.get('localizacao', ''),
                            'localizacao_destino': nova_loc_bx,
                            'responsavel_origem': rbx.get('responsavel_atual', ''),
                            'responsavel_destino': dest_final,
                            'projeto': rbx.get('projeto', ''),
                            'quantidade': rbx.get('quantidade', '1'),
                            'documento': doc_evid.strip(),
                            'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                            'observacao': f"Motivo: {motivo_bx.strip()} | Viabilidade: {viabilidade}"
                        }).execute()

                        st.cache_data.clear()
                        registrar_log_auditoria("BAIXA / OBSOLESCÊNCIA", id_f_bx, f"{cond_bx} - {aprov_bx} ({dest_final})")
                        st.success("✅ Processo de obsolescência/baixa registrado!")
                        st.rerun()
                    else:
                        st.error("Informe o motivo da segregação/baixa.")

        st.divider()
        st.markdown("###### 📋 Ferramentas em Obsolescência, Baixa ou Descarte")
        st.dataframe(df_baixa_fer, use_container_width=True, hide_index=True)

    exibir_marca_desenvolvedor()

# ==========================================
# F5: DIVERGÊNCIA D365 X CONTROLE OPERACIONAL (ITEM 9)
# ==========================================
def render_conciliacao_d365_fer(df_fer, df_conc_d365):
    st.header("⚖️ Divergência: Saldo D365 x Saldo Operacional de Usados")
    st.info(
        "💡 **Regra de Governança (Item 9):** Esta conciliação compara o saldo informado no ERP D365 (quando existente) com o **Saldo Operacional de Ferramentas Usadas** físico, sem alterar artificialmente o ERP."
    )

    saldos_op_map = {}
    desc_map = {}
    if not df_fer.empty:
        df_validos = df_fer[~df_fer['status_operacional'].isin(['BAIXADO'])].copy()
        for _, r in df_validos.iterrows():
            cod = str(r.get('codigo_d365', '')).strip()
            if cod:
                q = _parse_int(r.get('quantidade', '1'), 1)
                saldos_op_map[cod] = saldos_op_map.get(cod, 0) + q
                if cod not in desc_map:
                    desc_map[cod] = r.get('descricao_d365') or r.get('descricao_ferramenta', '')

    with st.expander("➕ Informar / Atualizar Saldo Oficial do D365 para Comparação", expanded=True):
        with st.form("form_conc_d365"):
            c1, c2, c3 = st.columns(3)
            with c1:
                codigos_sug = sorted(list(saldos_op_map.keys()))
                cod_sel = st.selectbox("Selecionar Código D365 cadastrado (ou digite ao lado):", [""] + codigos_sug)
                cod_manual = st.text_input("Ou Digite o Código D365:")
                cod_final = cod_manual.strip() if cod_manual.strip() else cod_sel
            with c2:
                desc_d365_in = st.text_input("Descrição D365:", value=desc_map.get(cod_final, ''))
                saldo_erp = st.number_input("Saldo Oficial no D365:", min_value=0, value=0, step=1)
            with c3:
                motivo_dif = st.text_input("Motivo da Diferença (Ex: Material recuperado de obra sem saldo ERP)")
                situacao_c = st.selectbox("Situação:", ["Conferido - Uso Operacional Interno", "Em Análise Contábil/Fiscal", "Aguardando Regularização", "Conciliado"])
                acao_nec = st.text_input("Ação Necessária:", value="Manter controle operacional complementar")

            if st.form_submit_button("⚖️ Calcular Diferença e Salvar Análise", type="primary"):
                if cod_final:
                    s_op = saldos_op_map.get(cod_final, 0)
                    dif = s_op - int(saldo_erp)
                    reg_c = {
                        'codigo_d365': cod_final,
                        'descricao_d365': desc_d365_in.strip() or desc_map.get(cod_final, ''),
                        'saldo_d365': str(saldo_erp),
                        'saldo_operacional_usados': str(s_op),
                        'diferenca': f"{dif:+d}",
                        'motivo_diferenca': motivo_dif.strip(),
                        'situacao': situacao_c,
                        'acao_necessaria': acao_nec.strip(),
                        'atualizado_em': datetime.now().strftime('%Y-%m-%d %H:%M')
                    }
                    supabase.table('conciliacao_d365_fer').upsert([reg_c]).execute()
                    st.cache_data.clear()
                    registrar_log_auditoria("CONCILIAÇÃO D365 FERRAMENTAL", cod_final, f"D365: {saldo_erp} | Op. Usados: {s_op} | Dif: {dif:+d}")
                    st.success("✅ Comparativo atualizado!")
                    st.rerun()
                else:
                    st.error("Informe o Código D365.")

    if not df_conc_d365.empty:
        df_view_c = df_conc_d365.copy()
        for idx, row in df_view_c.iterrows():
            c_cod = str(row['codigo_d365']).strip()
            if c_cod in saldos_op_map:
                s_op_atual = saldos_op_map[c_cod]
                s_d365_atual = _parse_int(row['saldo_d365'], 0)
                df_view_c.at[idx, 'saldo_operacional_usados'] = str(s_op_atual)
                df_view_c.at[idx, 'diferenca'] = f"{s_op_atual - s_d365_atual:+d}"
        st.subheader("📊 Painel Comparativo: Saldo D365 x Saldo Operacional de Usados")
        st.dataframe(df_view_c, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum código D365 parametrizado para comparação ainda.")

    exibir_marca_desenvolvedor()
