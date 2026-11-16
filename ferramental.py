import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import nuvem
from pdf_termo import converter_df_excel_simples, gerar_backup_completo_excel, gerar_termo_pdf

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

def formatar_badge_alerta(status_op, cond_fis, dias_ociosos=0):
    st_up = str(status_op).strip().upper()
    cd_up = str(cond_fis).strip().upper()
    
    if int(dias_ociosos) > 90 and st_up not in ["BAIXADO", "TRANSFERIDO"]:
        return "⏳ PARADO > 90 DIAS"
        
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
    if not val: return 0.0
    txt = str(val).replace("R$", "").replace(" ", "").strip()
    if "," in txt and "." in txt: txt = txt.replace(".", "").replace(",", ".")
    elif "," in txt: txt = txt.replace(",", ".")
    try: return float(txt)
    except: return 0.0

def _parse_int(val, default=1):
    try: return int(float(str(val).strip()))
    except: return default

def update_cols_fer():
    st.session_state.saved_cols_fer = st.session_state.ms_fer_key
    salvar_preferencias_colunas(
        st.session_state.get('saved_cols_inv'),
        st.session_state.get('saved_cols_mov'),
        st.session_state.get('saved_cols_trm'),
        st.session_state.saved_cols_fer
    )

# ==========================================
# F1: PAINEL GERENCIAL
# ==========================================
def render_painel_ferramental(df_fer, df_mov_fer, df_caut_fer, df_manut_fer, df_baixa_fer, df_conc_d365):
    if 'saved_cols_fer' not in st.session_state:
        prefs = carregar_preferencias_colunas()
        st.session_state.saved_cols_fer = prefs.get('fer', list(COLUNAS_FERRAMENTAS))

    st.header("🛠️ Controle Gerencial de Ferramentas Usadas / Reutilizáveis")
    st.caption("Controle operacional complementar ao D365 — Rastreabilidade física e individual sem alterar artificialmente o saldo do ERP.")

    st.markdown("##### 📊 SALDO OPERACIONAL DE FERRAMENTAS USADAS (Contagem por Quantidade Informada)")
    
    if not df_fer.empty:
        qtd_series = df_fer['quantidade'].apply(lambda x: _parse_int(x, 1))
        st_op = df_fer['status_operacional'].astype(str).str.upper().str.strip()
        cd_fi = df_fer['condicao_fisica'].astype(str).str.upper().str.strip()
        dias_ociosos = df_fer['dias_sem_movimentacao'].apply(lambda x: _parse_int(x, 0))

        mask_ativo_fisico = ~st_op.isin(['BAIXADO', 'TRANSFERIDO'])
        
        total_fisico = int(qtd_series[mask_ativo_fisico].sum())
        
        mask_disp = (st_op == 'DISPONÍVEL') & (cd_fi.isin(['NOVO', 'USADO - BOM', 'USADO - REGULAR']))
        s_disp = int(qtd_series[mask_disp].sum())
        s_cautela = int(qtd_series[st_op == 'EM CAUTELA'].sum())
        
        s_ocioso = int(qtd_series[(dias_ociosos > 90) & mask_ativo_fisico].sum())
    else:
        total_fisico = s_disp = s_cautela = s_ocioso = 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📦 TOTAL FÍSICO", total_fisico, help="Soma do campo 'Quantidade' de todos os lotes.")
    c2.metric("🟢 DISPONÍVEL (Aprovadas)", s_disp, help="Soma da Quantidade pronta para entrega.")
    c3.metric("🔵 EM CAUTELA", s_cautela, help="Soma da Quantidade em posse dos colaboradores.")
    c4.metric("⏳ PARADOS > 3 MESES", s_ocioso, help="Quantidade de ferramentas sem movimento há > 90 dias.")

    st.markdown(
        "<div style='background-color:#f8f9fa; padding:6px 12px; border-radius:6px; font-size:0.80rem; margin-bottom:12px; border:1px solid #e9ecef;'>"
        "<b>Legenda de Alertas Operacionais:</b> &nbsp; "
        "🟢 <b>Verde:</b> Disponível &nbsp;|&nbsp; "
        "🔵 <b>Azul:</b> Em Cautela &nbsp;|&nbsp; "
        "🟡 <b>Amarelo:</b> Em Inspeção &nbsp;|&nbsp; "
        "🟠 <b>Laranja:</b> Em Manutenção &nbsp;|&nbsp; "
        "🔴 <b>Vermelho:</b> Defeito / Bloqueado &nbsp;|&nbsp; "
        "⚪ <b>Cinza:</b> Obsoleto / Descarte &nbsp;|&nbsp; "
        "⏳ <b>Ampulheta:</b> Parado > 90 dias"
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
                
            f_ocioso = st.checkbox("⏳ Mostrar apenas itens parados há mais de 3 meses (> 90 dias)", value=False)

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
            if f_ocioso:
                df_view = df_view[df_view['dias_sem_movimentacao'].apply(lambda x: _parse_int(x, 0)) > 90]
            if fil_txt.strip():
                termo = fil_txt.strip().lower()
                mask = df_view.astype(str).apply(lambda x: x.str.lower().str.contains(termo, na=False)).any(axis=1)
                df_view = df_view[mask]

            df_view_display = df_view[cols_exibir].copy()
            df_view_display.insert(0, "Alerta", df_view.apply(lambda r: formatar_badge_alerta(r.get('status_operacional',''), r.get('condicao_fisica',''), r.get('dias_sem_movimentacao', 0)), axis=1))
            st.dataframe(df_view_display, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma ferramenta usada cadastrada ainda. Utilize a aba '➕ Cadastrar / Receber Ferramenta' ao lado.")

    with tabs[1]:
        st.subheader("➕ Recebimento / Cadastro de Ferramenta Usada")
        prox_id = gerar_proximo_id_fer(df_fer)
        st.info(f"💡 **Identificação Individual Automática:** O próximo código físico disponível é **`{prox_id}`**. A data de entrada é registada automaticamente e contabilizada no histórico (Saldo Inicial).")

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
                            'observacao': f"Cadastro Inicial (Saldo): {cond_fisica} / {status_op}"
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
        st.info("💡 A ferramenta reconhece automaticamente o padrão **MASSIVO FERRAMENTAL** ou o padrão exportado. A Data de Entrada e Histórico Base são criados automaticamente para as ferramentas importadas.")
        
        arq_fer = st.file_uploader("Arraste a planilha Excel com a relação de ferramentas (.xlsx)", type=["xlsx"], key="up_fer_mass")
        if arq_fer:
            try:
                df_up_f = pd.read_excel(arq_fer)
                df_up_f.columns = [normalizar_nome_coluna(c) for c in df_up_f.columns]
                
                de_para_massivo = {
                    'numero_do_item': 'codigo_d365',
                    'nome_do_produto': 'descricao_d365',
                    'pesquisar_nome': 'descricao_ferramenta',
                    'total': 'quantidade',
                    'serial': 'numero_serie',
                    'status': 'condicao_fisica'
                }
                df_up_f = df_up_f.rename(columns=de_para_massivo)
                
                if 'enderecamento_01' in df_up_f.columns or 'enderecamento_02' in df_up_f.columns:
                    e1 = df_up_f.get('enderecamento_01', pd.Series(['']*len(df_up_f))).fillna('').astype(str)
                    e2 = df_up_f.get('enderecamento_02', pd.Series(['']*len(df_up_f))).fillna('').astype(str)
                    df_up_f['observacoes'] = "Endereço: " + e1 + " / " + e2
                
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
                
                for c_limpar in ['marca', 'modelo', 'numero_serie', 'categoria', 'projeto', 'coordenacao']:
                    if c_limpar in df_up_f.columns:
                        df_up_f[c_limpar] = df_up_f[c_limpar].fillna('')
                
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
                    faltantes_mask = df_up_f['id_controle'].isnull() | (df_up_f['id_controle'] == '')
                    novos_ids = [f"FER-{base_n + idx + 1:06d}" for idx in range(faltantes_mask.sum())]
                    df_up_f.loc[faltantes_mask, 'id_controle'] = novos_ids
                
                df_up_f['responsavel_atual'] = 'ALMOXARIFADO'
                df_up_f['data_entrada'] = datetime.now().strftime('%Y-%m-%d')
                df_up_f['ultima_movimentacao'] = datetime.now().strftime('%Y-%m-%d')
                df_up_f['dias_sem_movimentacao'] = '0'

                st.caption(f"Leitura concluída. Pré-visualização ({len(df_up_f)} itens):")
                st.dataframe(df_up_f[['id_controle', 'codigo_d365', 'descricao_ferramenta', 'quantidade', 'condicao_fisica', 'data_entrada']].head(5), use_container_width=True)
                
                if st.button("🚀 Confirmar Importação de Ferramentas", type="primary"):
                    with st.spinner("Enviando ferramentas para o Supabase..."):
                        if salvar_dados_massa('ferramentas_usadas', df_up_f, COLUNAS_FERRAMENTAS):
                            movs_massa = []
                            stamp_t = datetime.now().strftime('%Y%m%d%H%M%S')
                            hoje_dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            for indx, m_r in df_up_f.iterrows():
                                movs_massa.append({
                                    'id_movimento': f"MVF-{stamp_t}-{indx}",
                                    'data': hoje_dt,
                                    'id_fer': m_r['id_controle'],
                                    'codigo_d365': m_r.get('codigo_d365', ''),
                                    'tipo_movimento': 'ENTRADA',
                                    'localizacao_origem': 'EXTERNO',
                                    'localizacao_destino': m_r.get('localizacao', 'USADO-DISP'),
                                    'responsavel_origem': 'IMPORTAÇÃO EM MASSA',
                                    'responsavel_destino': 'ALMOXARIFADO',
                                    'projeto': m_r.get('projeto', ''),
                                    'quantidade': str(m_r.get('quantidade', '1')),
                                    'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                                    'observacao': "Carga Inicial (Saldo)"
                                })
                            supabase.table('mov_ferramentas').insert(movs_massa).execute()
                            
                            registrar_log_auditoria("UPLOAD FERRAMENTAL", arq_fer.name, f"{len(df_up_f)} ferramentas importadas (Padrão Massivo).")
                            st.success("✅ Ferramentas importadas com sucesso!")
                            st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar planilha: {e}")

    if st.session_state.perfil == 'Master':
        with tabs[4]:
            st.subheader("❌ Exclusão de Ferramentas por Seleção (Master)")
            if not df_fer.empty:
                df_del_f = df_fer[['id_controle', 'codigo_d365', 'descricao_ferramenta', 'condicao_fisica', 'status_operacional', 'quantidade', 'localizacao', 'responsavel_atual']].copy()
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
            st.dataframe(df_fila_insp[['id_controle', 'codigo_d365', 'descricao_ferramenta', 'condicao_fisica', 'status_operacional', 'localizacao', 'quantidade']], use_container_width=True, hide_index=True)
        else:
            st.success("🎉 Nenhuma ferramenta travada na fila de inspeção no momento.")

        busca_insp = st.text_input("🔍 Digite o ID FER (ex: FER-000001), Código D365 ou Série para Inspecionar / Decidir:")
        fer_match = buscar_ferramenta(busca_insp, df_fer) if busca_insp else pd.DataFrame()

        if not fer_match.empty:
            reg = fer_match.iloc[0].to_dict()
            id_fer_real = reg['id_controle']
            st.info(
                f"**Selecionado:** `{id_fer_real}` — {reg.get('descricao_ferramenta')} | "
                f"**Condição Atual:** {reg.get('condicao_fisica')} | **Status Atual:** {reg.get('status_operacional')} | **Qtd:** {reg.get('quantidade')}"
            )

            decisao = st.radio(
                "Selecione a Decisão da Inspeção:",
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
                        'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                        'observacao': f"Inspeção: {cond_sug} -> {st_sug}. {obs_insp.strip()}"
                    }
                    supabase.table('ferramentas_usadas').update(upd).eq('id_controle', id_fer_real).execute()
                    supabase.table('mov_ferramentas').insert(mov_log).execute()
                    st.cache_data.clear()
                    st.success(f"✅ Ferramenta {id_fer_real} atualizada para {st_sug} ({loc_final})!")
                    st.rerun()

    with aba_mov_geral:
        st.subheader("🔄 Registrar Movimento Operacional")
        busca_mv = st.text_input("🔍 Buscar Ferramenta (ID FER, Código D365 ou Série):", key="b_mv_fer")
        f_mv = buscar_ferramenta(busca_mv, df_fer) if busca_mv else pd.DataFrame()

        if not f_mv.empty:
            r_mv = f_mv.iloc[0].to_dict()
            id_f = r_mv['id_controle']
            qtd_lote = _parse_int(r_mv.get('quantidade', '1'), 1)
            
            st.success(f"**Ferramenta:** `{id_f}` - {r_mv.get('descricao_ferramenta')} | Saldo do Lote: `{qtd_lote}`")

            with st.form("form_mov_fer_avulso"):
                cm1, cm2, cm3 = st.columns(3)
                with cm1:
                    qtd_mover = st.number_input("Quantidade a Movimentar *", min_value=1, max_value=qtd_lote, value=1, help="Se movimentar menos que o total, o lote será separado mantendo o saldo correto no Almoxarifado.")
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
                    
                    if qtd_mover < qtd_lote:
                        # SEPARAÇÃO DE LOTE (PARCIAL)
                        saldo_restante = qtd_lote - qtd_mover
                        supabase.table('ferramentas_usadas').update({'quantidade': str(saldo_restante)}).eq('id_controle', id_f).execute()
                        
                        id_novo_lote = gerar_proximo_id_fer(df_fer)
                        novo_reg = r_mv.copy()
                        novo_reg['id_controle'] = id_novo_lote
                        novo_reg['quantidade'] = str(qtd_mover)
                        novo_reg['localizacao'] = loc_dest
                        novo_reg['status_operacional'] = st_novo
                        novo_reg['condicao_fisica'] = cd_nova
                        novo_reg['responsavel_atual'] = resp_dest.strip()
                        novo_reg['projeto'] = proj_dest.strip()
                        novo_reg['ultima_movimentacao'] = hoje_s
                        novo_reg['dias_sem_movimentacao'] = '0'
                        
                        supabase.table('ferramentas_usadas').insert([novo_reg]).execute()
                        id_movimentado = id_novo_lote
                    else:
                        # MOVIMENTAÇÃO TOTAL
                        upd_f = {
                            'localizacao': loc_dest,
                            'status_operacional': st_novo,
                            'condicao_fisica': cd_nova,
                            'responsavel_atual': resp_dest.strip(),
                            'projeto': proj_dest.strip(),
                            'ultima_movimentacao': hoje_s,
                            'dias_sem_movimentacao': '0'
                        }
                        supabase.table('ferramentas_usadas').update(upd_f).eq('id_controle', id_f).execute()
                        id_movimentado = id_f

                    novo_m = {
                        'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'id_fer': id_movimentado,
                        'codigo_d365': r_mv.get('codigo_d365', ''),
                        'tipo_movimento': t_mov,
                        'localizacao_origem': r_mv.get('localizacao', ''),
                        'localizacao_destino': loc_dest,
                        'responsavel_origem': r_mv.get('responsavel_atual', ''),
                        'responsavel_destino': resp_dest.strip(),
                        'projeto': proj_dest.strip(),
                        'quantidade': str(qtd_mover),
                        'documento': doc_mv.strip(),
                        'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                        'observacao': obs_mv.strip()
                    }
                    supabase.table('mov_ferramentas').insert(novo_m).execute()
                    st.cache_data.clear()
                    st.success("✅ Movimentação de quantidade exata registrada com sucesso!")
                    st.rerun()

    exibir_marca_desenvolvedor()

# ==========================================
# F3: CONTROLE DE CAUTELA (ENTREGA PARCIAL MÚLTIPLA)
# ==========================================
def render_cautela_ferramentas(df_fer, df_caut_fer, df_empregados):
    st.header("👷 Controle de Cautela (Entrega e Devolução de Ferramentas)")

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
                    lambda r: f"Cód D365: {r['codigo_d365']} | {r['descricao_d365'] or r['descricao_ferramenta']} | Saldo: {r['quantidade']} [ID: {r['id_controle']}]", axis=1
                ).tolist()
                
                itens_selecionados = st.multiselect("1️⃣ Busque e Selecione as Ferramentas (Pode escolher várias):", opcoes_f)
            
            with c_b2:
                mat_busca = st.text_input("2️⃣ Digite a Matrícula do Colaborador e pressione Enter:")
                mat_limpa = limpar_texto_matricula(mat_busca)
                emp_info = {}
                if mat_limpa and not df_empregados.empty:
                    m_e = df_empregados[df_empregados['matricula'].astype(str) == mat_limpa]
                    if not m_e.empty:
                        emp_info = m_e.iloc[0].fillna("").to_dict()
                        st.success(f"👤 Colaborador: **{emp_info.get('nome')}**")
                    else:
                        st.warning("⚠️ Matrícula não localizada na base.")

            qtds_entregar = {}
            if itens_selecionados:
                st.markdown("###### 📦 Defina a quantidade a entregar para cada ferramenta selecionada:")
                c_q1, c_q2 = st.columns(2)
                for idx, item_str in enumerate(itens_selecionados):
                    id_fer = item_str.split("[ID: ")[1].replace("]", "")
                    saldo_str = item_str.split(" | Saldo: ")[1].split(" ")[0]
                    saldo_val = int(saldo_str) if saldo_str.isdigit() else 1
                    desc = item_str.split(" | ")[1][:30] + "..."
                    
                    with (c_q1 if idx % 2 == 0 else c_q2):
                        qtds_entregar[id_fer] = st.number_input(f"Qtd: {desc} (Máx {saldo_val})", min_value=1, max_value=saldo_val, value=1, key=f"qtd_{id_fer}")

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

                if st.form_submit_button("🚀 Confirmar Cautela e Entregar", type="primary"):
                    if col_nome.strip() and itens_selecionados:
                        hoje_s = dt_ent.strftime('%Y-%m-%d')
                        id_caut_geral = f"CAU-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        
                        lista_fakes_pdf = []
                        
                        # Pegar o próximo ID base para evitar duplicação em caso de múltiplas quebras de lote no mesmo clique
                        prox_id_str = gerar_proximo_id_fer(df_fer)
                        base_num = int(prox_id_str.replace("FER-", "")) if prox_id_str.startswith("FER-") and prox_id_str.replace("FER-", "").isdigit() else 1
                        lotes_quebrados = 0
                        
                        # Processa a baixa de cada ferramenta agrupada no lote da Cautela
                        for id_fer_sel, qtd_entregar in qtds_entregar.items():
                            reg_f = fer_disponiveis[fer_disponiveis['id_controle'] == id_fer_sel].iloc[0].to_dict()
                            qtd_estoque_max = _parse_int(reg_f.get('quantidade', '1'), 1)
                            
                            if qtd_entregar < qtd_estoque_max:
                                # Quebra o lote (Mantém restante no Almoxarifado, cria novo para o Colaborador)
                                saldo_restante = qtd_estoque_max - qtd_entregar
                                supabase.table('ferramentas_usadas').update({'quantidade': str(saldo_restante)}).eq('id_controle', id_fer_sel).execute()
                                
                                id_entregue = f"FER-{base_num + lotes_quebrados:06d}"
                                lotes_quebrados += 1
                                
                                novo_reg = reg_f.copy()
                                novo_reg['id_controle'] = id_entregue
                                novo_reg['quantidade'] = str(qtd_entregar)
                                novo_reg['status_operacional'] = 'EM CAUTELA'
                                novo_reg['localizacao'] = 'CAMPO / COLABORADOR'
                                novo_reg['responsavel_atual'] = col_nome.strip()
                                novo_reg['matricula'] = col_mat.strip()
                                novo_reg['projeto'] = col_proj.strip()
                                novo_reg['coordenacao'] = col_coord.strip()
                                novo_reg['data_entrega'] = hoje_s
                                novo_reg['ultima_movimentacao'] = hoje_s
                                novo_reg['dias_sem_movimentacao'] = '0'
                                
                                supabase.table('ferramentas_usadas').insert([novo_reg]).execute()
                            else:
                                # Entrega lote inteiro
                                id_entregue = id_fer_sel
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
                                supabase.table('ferramentas_usadas').update(upd_fer).eq('id_controle', id_fer_sel).execute()

                            nova_caut = {
                                'id_cautela': id_caut_geral,
                                'id_fer': id_entregue,
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
                                'observacao': f"Qtd: {qtd_entregar}. " + obs_caut.strip()
                            }
                            mov_caut = {
                                'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}-{id_entregue[-4:]}",
                                'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'id_fer': id_entregue,
                                'codigo_d365': reg_f.get('codigo_d365', ''),
                                'tipo_movimento': 'CAUTELA',
                                'localizacao_origem': reg_f.get('localizacao', 'USADO-DISP'),
                                'localizacao_destino': 'CAMPO / COLABORADOR',
                                'responsavel_origem': 'ALMOXARIFADO',
                                'responsavel_destino': col_nome.strip(),
                                'projeto': col_proj.strip(),
                                'quantidade': str(qtd_entregar),
                                'documento': id_caut_geral,
                                'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                                'observacao': f"Entrega parcial/total ({qtd_entregar} un) para {col_nome.strip()}"
                            }
                            supabase.table('cautelas_ferramentas').insert(nova_caut).execute()
                            supabase.table('mov_ferramentas').insert(mov_caut).execute()

                            # Acumula info para PDF agrupado
                            lista_fakes_pdf.append({
                                'marca': reg_f.get('marca', ''),
                                'modelo': reg_f.get('modelo', ''),
                                'numero_serie': reg_f.get('numero_serie', ''),
                                'patrimonio': id_entregue,
                                'condicoes_para_uso': reg_f.get('condicao_fisica', 'USADO - BOM'),
                                'acessorios': f"Qtd: {qtd_entregar} | {obs_caut.strip()}",
                                'codigo_d365': reg_f.get('codigo_d365', ''),
                                'descricao_d365': reg_f.get('descricao_d365', reg_f.get('descricao_ferramenta', '')),
                                'coordenacao': col_coord.strip(),
                                'nf_procisa': reg_f.get('documento_referencia', '')
                            })

                        if gerar_pdf_chk and len(lista_fakes_pdf) > 0:
                            df_fake_ativo = pd.DataFrame(lista_fakes_pdf)
                            caminho = gerar_termo_pdf(
                                id_caut_geral, col_nome.strip(), col_mat.strip(),
                                emp_info.get('cpf', ''), emp_info.get('rg', ''),
                                col_proj.strip(), col_coord.strip(), df_fake_ativo
                            )
                            with open(caminho, "rb") as f_pdf:
                                st.session_state.pdf_cautela_fer = {
                                    'bytes': f_pdf.read(),
                                    'nome': f"Termo_Cautela_Multipla_{id_caut_geral}.pdf"
                                }

                        st.cache_data.clear()
                        st.rerun()
                    elif not itens_selecionados:
                        st.error("Selecione pelo menos uma ferramenta.")
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
                    
                    f_dev_match = df_fer[df_fer['id_controle'] == id_f_dev]
                    qtd_devolvida = f_dev_match.iloc[0]['quantidade'] if not f_dev_match.empty else '1'
                    
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
                        'quantidade': qtd_devolvida,
                        'documento': id_caut_dev,
                        'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                        'observacao': f"Devolução de cautela ({cond_dev}). {obs_dev.strip()}"
                    }).execute()

                    st.cache_data.clear()
                    st.success(f"✅ Ferramenta devolvida e encaminhada para {loc_pos_dev}!")
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
        "🟠 Histórico e Retorno de Manutenção",
        "⚪ Obsolescência, Laudo e Descarte"
    ])

    with aba_manut:
        busca_m = st.text_input("🔍 Digite o ID FER ou Código D365 da ferramenta:", key="b_manut_f")
        f_m = buscar_ferramenta(busca_m, df_fer) if busca_m else pd.DataFrame()
        if not f_m.empty:
            rm = f_m.iloc[0].to_dict()
            id_f_m = rm['id_controle']
            qtd_m_atual = _parse_int(rm.get('quantidade_manutencoes', '0'), 0)
            with st.form("form_reg_manut"):
                m1, m2, m3 = st.columns(3)
                with m1:
                    dt_envio = st.date_input("Data de Envio", datetime.today())
                    defeito_inf = st.text_input("Defeito Informado *")
                    fornecedor = st.text_input("Fornecedor / Oficina *")
                with m2:
                    num_os = st.text_input("Número da OS")
                    val_manut = st.number_input("Valor (R$)", min_value=0.0, step=10.0, value=0.0)
                    dt_ret = st.date_input("Data de Retorno", datetime.today())
                with m3:
                    resultado_m = st.selectbox("Resultado", ["REPARADO COM SUCESSO", "CALIBRADO / REVISADO", "AGUARDANDO PEÇA", "SEM CONSERTO / INVIÁVEL"])
                    cond_apos = st.selectbox("Condição Após", LISTA_CONDICAO_FISICA, index=1)
                    liberado = st.radio("Liberado?", ["Sim", "Não"], horizontal=True)

                if st.form_submit_button("💾 Registrar Manutenção", type="primary"):
                    if defeito_inf.strip():
                        id_mn = f"MNT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        if liberado == "Sim" and cond_apos in ["NOVO", "USADO - BOM", "USADO - REGULAR"]:
                            novo_st_op, nova_loc = "DISPONÍVEL", "USADO-DISP"
                        elif resultado_m == "SEM CONSERTO / INVIÁVEL":
                            novo_st_op, nova_loc = "AGUARDANDO DECISÃO", "USADO-SEGREGADO"
                        else:
                            novo_st_op, nova_loc = "EM INSPEÇÃO", "USADO-INSPECAO"

                        reg_mnt = {
                            'id_manut': id_mn, 'id_fer': id_f_m, 'data_envio': dt_envio.strftime('%Y-%m-%d'),
                            'defeito_informado': defeito_inf.strip(), 'fornecedor_oficina': fornecedor.strip(),
                            'numero_os': num_os.strip(), 'valor_manutencao': f"{val_manut:.2f}",
                            'data_retorno': dt_ret.strftime('%Y-%m-%d'), 'resultado': resultado_m,
                            'condicao_apos_manutencao': cond_apos, 'liberado_utilizacao': liberado, 'observacoes': ""
                        }
                        supabase.table('manutencao_ferramentas').insert(reg_mnt).execute()
                        supabase.table('ferramentas_usadas').update({
                            'condicao_fisica': cond_apos, 'status_operacional': novo_st_op, 'localizacao': nova_loc,
                            'quantidade_manutencoes': str(qtd_m_atual + 1), 'ultima_movimentacao': dt_ret.strftime('%Y-%m-%d'), 'dias_sem_movimentacao': '0'
                        }).eq('id_controle', id_f_m).execute()
                        st.cache_data.clear()
                        st.success("✅ Manutenção registrada!")
                        st.rerun()

    with aba_baixa:
        st.dataframe(df_baixa_fer, use_container_width=True, hide_index=True)

    exibir_marca_desenvolvedor()

# ==========================================
# F5: DIVERGÊNCIA D365 X CONTROLE OPERACIONAL
# ==========================================
def render_conciliacao_d365_fer(df_fer, df_conc_d365):
    st.header("⚖️ Divergência: Saldo D365 x Saldo Operacional de Usados")
    saldos_op_map, desc_map = {}, {}
    if not df_fer.empty:
        df_validos = df_fer[~df_fer['status_operacional'].isin(['BAIXADO'])].copy()
        for _, r in df_validos.iterrows():
            cod = str(r.get('codigo_d365', '')).strip()
            if cod:
                q = _parse_int(r.get('quantidade', '1'), 1)
                saldos_op_map[cod] = saldos_op_map.get(cod, 0) + q
                if cod not in desc_map: desc_map[cod] = r.get('descricao_d365') or r.get('descricao_ferramenta', '')

    with st.expander("➕ Informar / Atualizar Saldo Oficial do D365 para Comparação", expanded=True):
        with st.form("form_conc_d365"):
            c1, c2, c3 = st.columns(3)
            with c1:
                cod_sel = st.selectbox("Selecionar Código D365:", [""] + sorted(list(saldos_op_map.keys())))
                cod_final = st.text_input("Ou Digite o Código D365:").strip() or cod_sel
            with c2:
                desc_d365_in = st.text_input("Descrição D365:", value=desc_map.get(cod_final, ''))
                saldo_erp = st.number_input("Saldo Oficial D365:", min_value=0, value=0, step=1)
            with c3:
                situacao_c = st.selectbox("Situação:", ["Conferido", "Aguardando Regularização"])

            if st.form_submit_button("⚖️ Calcular Diferença", type="primary"):
                if cod_final:
                    s_op = saldos_op_map.get(cod_final, 0)
                    dif = s_op - int(saldo_erp)
                    reg_c = {
                        'codigo_d365': cod_final, 'descricao_d365': desc_d365_in.strip(), 'saldo_d365': str(saldo_erp),
                        'saldo_operacional_usados': str(s_op), 'diferenca': f"{dif:+d}", 'situacao': situacao_c,
                        'atualizado_em': datetime.now().strftime('%Y-%m-%d %H:%M')
                    }
                    supabase.table('conciliacao_d365_fer').upsert([reg_c]).execute()
                    st.cache_data.clear()
                    st.success("✅ Comparativo atualizado!")
                    st.rerun()

    if not df_conc_d365.empty:
        df_view_c = df_conc_d365.copy()
        for idx, row in df_view_c.iterrows():
            c_cod = str(row['codigo_d365']).strip()
            if c_cod in saldos_op_map:
                s_op_atual = saldos_op_map[c_cod]
                s_d365_atual = _parse_int(row['saldo_d365'], 0)
                df_view_c.at[idx, 'saldo_operacional_usados'] = str(s_op_atual)
                df_view_c.at[idx, 'diferenca'] = f"{s_op_atual - s_d365_atual:+d}"
        st.dataframe(df_view_c, use_container_width=True, hide_index=True)

    exibir_marca_desenvolvedor()
