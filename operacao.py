import streamlit as st
import pandas as pd
from datetime import datetime
import urllib.parse
import nuvem
import pdf_termo

supabase = nuvem.supabase
buscar_ativo = nuvem.buscar_ativo
registrar_log_auditoria = nuvem.registrar_log_auditoria
limpar_texto_matricula = nuvem.limpar_texto_matricula
exibir_marca_desenvolvedor = nuvem.exibir_marca_desenvolvedor
gerar_termo_pdf = pdf_termo.gerar_termo_pdf

# ==========================================
# BUSCA INTELIGENTE DE COLABORADOR (POR MATRÍCULA OU NOME)
# ==========================================
def localizar_colaborador(termo, df_empregados):
    if df_empregados is None or df_empregados.empty or not termo:
        return {}
    t_limpo = limpar_texto_matricula(termo)
    if not t_limpo:
        return {}

    s_mat = df_empregados['matricula'].fillna("").apply(limpar_texto_matricula)
    m1 = df_empregados[s_mat == t_limpo]
    if not m1.empty:
        return m1.iloc[0].fillna("").to_dict()

    t_sem_zero = t_limpo.lstrip("0")
    if t_sem_zero:
        m2 = df_empregados[s_mat.apply(lambda x: x.lstrip("0") == t_sem_zero)]
        if not m2.empty:
            return m2.iloc[0].fillna("").to_dict()

    if 'nome' in df_empregados.columns:
        m3 = df_empregados[df_empregados['nome'].fillna("").astype(str).str.upper().str.contains(t_limpo.upper(), regex=False, na=False)]
        if not m3.empty:
            return m3.iloc[0].fillna("").to_dict()

    return {}

def _resolver_dados_termo_colaborador(resp_raw, mat_raw, unid_raw, proj_raw, df_empregados):
    r_txt = str(resp_raw or "").strip()
    m_txt = limpar_texto_matricula(mat_raw)

    if r_txt.isdigit() and not m_txt:
        m_txt = r_txt

    emp = localizar_colaborador(m_txt or r_txt, df_empregados)
    nome_final = emp.get('nome', '').strip() or ("" if r_txt.isdigit() else r_txt)
    mat_final = emp.get('matricula', '').strip() or m_txt
    cpf_final = emp.get('cpf', '').strip()
    rg_final = emp.get('rg', '').strip()
    unid_final = emp.get('unidade', '').strip() or str(unid_raw or "").strip()
    proj_final = emp.get('projeto', '').strip() or str(proj_raw or "").strip()

    if not nome_final:
        nome_final = r_txt

    return nome_final, mat_final, cpf_final, rg_final, proj_final, unid_final

# ==========================================
# SELETOR ESTILO FILTRO DO EXCEL PARA EQUIPAMENTOS (BUSCA EXATA + TABELA COM CHECKBOX)
# ==========================================
def render_seletor_excel_equipamentos(df_fonte, chave_unica, multiplo=True, altura=230):
    state_sel = f"sel_excel_pats_{chave_unica}"
    if state_sel not in st.session_state:
        st.session_state[state_sel] = set()

    if df_fonte.empty:
        st.warning("Nenhum equipamento disponível na base para seleção.")
        return pd.DataFrame()

    c_f1, c_f2, c_f3, c_f4 = st.columns([1.5, 2.1, 0.9, 0.7])
    with c_f1:
        col_alvo = st.selectbox(
            "Filtrar Coluna:",
            [
                "Patrimônio",
                "Número de Série",
                "Item / Código D365",
                "Equipamento / Marca / Modelo",
                "Endereçamento 01/02",
                "Cautela / Responsável",
                "Todos os Campos"
            ],
            key=f"col_ex_eqp_{chave_unica}",
            label_visibility="collapsed"
        )
    with c_f3:
        padrao_exato = True if col_alvo in ["Patrimônio", "Número de Série", "Item / Código D365"] else False
        modo_exato = st.checkbox(
            "🎯 Busca Exata",
            value=padrao_exato,
            key=f"exato_eqp_{chave_unica}",
            help="Quando marcado, digitar um número busca exatamente aquele código."
        )
    with c_f2:
        termo_b = st.text_input(
            "Digite para filtrar:",
            placeholder="🔍 Digite código(s) separados por vírgula ou descrição...",
            key=f"txt_ex_eqp_{chave_unica}",
            label_visibility="collapsed"
        )
    with c_f4:
        if st.button(f"🧹 Limpar ({len(st.session_state[state_sel])})", key=f"clr_ex_eqp_{chave_unica}", use_container_width=True):
            st.session_state[state_sel] = set()
            st.rerun()

    df_view = df_fonte.copy()
    for c_garantir in ['patrimonio', 'item', 'equipamento', 'marca', 'modelo', 'numero_serie', 'status_sistema', 'cautela', 'enderecamento_01', 'enderecamento_02']:
        if c_garantir not in df_view.columns:
            df_view[c_garantir] = ""

    if termo_b.strip():
        termos_lista = [t.strip().upper() for t in termo_b.replace(";", ",").split(",") if t.strip()]
        mask_total = pd.Series(False, index=df_view.index)

        for t_item in termos_lista:
            if col_alvo == "Patrimônio":
                s_col = df_view['patrimonio'].fillna("").astype(str).str.strip().str.upper()
            elif col_alvo == "Número de Série":
                s_col = df_view['numero_serie'].fillna("").astype(str).str.strip().str.upper()
            elif col_alvo == "Item / Código D365":
                s_col = df_view['item'].fillna("").astype(str).str.strip().str.upper()
            elif col_alvo == "Equipamento / Marca / Modelo":
                s_col = (
                    df_view['equipamento'].fillna("").astype(str) + " " +
                    df_view['marca'].fillna("").astype(str) + " " +
                    df_view['modelo'].fillna("").astype(str)
                ).str.upper()
            elif col_alvo == "Endereçamento 01/02":
                s_col = (
                    df_view['enderecamento_01'].fillna("").astype(str) + " " +
                    df_view['enderecamento_02'].fillna("").astype(str)
                ).str.upper()
            elif col_alvo == "Cautela / Responsável":
                s_col = df_view['cautela'].fillna("").astype(str).str.upper()
            else:
                s_col = (
                    df_view['patrimonio'].fillna("").astype(str) + " " +
                    df_view['numero_serie'].fillna("").astype(str) + " " +
                    df_view['item'].fillna("").astype(str) + " " +
                    df_view['equipamento'].fillna("").astype(str) + " " +
                    df_view['marca'].fillna("").astype(str) + " " +
                    df_view['modelo'].fillna("").astype(str) + " " +
                    df_view['enderecamento_01'].fillna("").astype(str) + " " +
                    df_view['cautela'].fillna("").astype(str)
                ).str.upper()

            if modo_exato and col_alvo in ["Patrimônio", "Número de Série", "Item / Código D365"]:
                mask_total = mask_total | (s_col == t_item)
            elif modo_exato:
                mask_total = mask_total | s_col.str.split().apply(lambda palavras: t_item in palavras)
            else:
                mask_total = mask_total | s_col.str.contains(t_item, regex=False, na=False)

        mask_ja_marcados = df_view['patrimonio'].astype(str).isin(st.session_state[state_sel])
        df_view = df_view[mask_total | mask_ja_marcados].copy()

    df_grid = pd.DataFrame({
        'Selecionar': df_view['patrimonio'].astype(str).isin(st.session_state[state_sel]),
        'Patrimônio': df_view['patrimonio'].astype(str),
        'Item D365': df_view['item'].astype(str),
        'Equipamento': df_view['equipamento'].astype(str),
        'Marca / Modelo': (df_view['marca'].astype(str) + " " + df_view['modelo'].astype(str)).str.strip(),
        'Nº de Série': df_view['numero_serie'].astype(str),
        'Status': df_view['status_sistema'].astype(str),
        'Cautela / Local': df_view['cautela'].astype(str),
        'Endereço 01': df_view['enderecamento_01'].astype(str),
        'Endereço 02': df_view['enderecamento_02'].astype(str)
    })

    df_grid = df_grid.sort_values(by=['Selecionar', 'Patrimônio'], ascending=[False, True]).reset_index(drop=True)

    cols_travadas = ['Patrimônio', 'Item D365', 'Equipamento', 'Marca / Modelo', 'Nº de Série', 'Status', 'Cautela / Local', 'Endereço 01', 'Endereço 02']
    editado = st.data_editor(
        df_grid,
        hide_index=True,
        use_container_width=True,
        height=altura,
        disabled=cols_travadas,
        column_config={
            'Selecionar': st.column_config.CheckboxColumn("☑️ Selecionar", default=False, width="small"),
            'Patrimônio': st.column_config.TextColumn("Patrimônio", width="small"),
            'Item D365': st.column_config.TextColumn("Item D365", width="small"),
            'Status': st.column_config.TextColumn("Status", width="small")
        },
        key=f"grid_ex_eqp_{chave_unica}"
    )

    pats_visiveis = set(df_grid['Patrimônio'].tolist())
    pats_marcados_agora = set(editado[editado['Selecionar'] == True]['Patrimônio'].tolist())

    if not multiplo and len(pats_marcados_agora) > 1:
        novos_clicados = list(pats_marcados_agora - st.session_state[state_sel])
        pat_manter = novos_clicados[0] if novos_clicados else list(pats_marcados_agora)[0]
        st.session_state[state_sel] = {pat_manter}
        st.rerun()
    else:
        st.session_state[state_sel] = (st.session_state[state_sel] - pats_visiveis) | pats_marcados_agora

    df_selecionados_final = df_fonte[df_fonte['patrimonio'].astype(str).isin(st.session_state[state_sel])].copy()
    if not df_selecionados_final.empty:
        resumo_sel = ", ".join([f"Pat {r['patrimonio']} ({r.get('equipamento','')})" for _, r in df_selecionados_final.iterrows()])
        st.caption(f"✅ **{len(df_selecionados_final)} equipamento(s) marcado(s):** {resumo_sel}")
    return df_selecionados_final

def _montar_df_pdf_equipamentos(df_ativos_selecionados, coord_padrao="", nf_padrao=""):
    linhas_pdf = []
    for _, r in df_ativos_selecionados.iterrows():
        marca = str(r.get('marca', '')).strip()
        modelo = str(r.get('modelo', '')).strip()
        serie = str(r.get('numero_serie', '')).strip()
        pat = str(r.get('patrimonio', '')).strip()
        cond = str(r.get('condicoes_para_uso', 'APTO')).strip() or "APTO"
        acess = str(r.get('acessorios', '')).strip()
        cod_item = str(r.get('item', '')).strip()
        eqp_desc = str(r.get('equipamento', '')).strip()

        linhas_pdf.append({
            'marca': marca,
            'modelo': modelo,
            'numero_serie': serie,
            'patrimonio': pat,
            'condicoes_para_uso': cond,
            'acessorios': acess,
            'codigo_d365': cod_item if cod_item else pat,
            'descricao_d365': eqp_desc,
            'coordenacao': str(r.get('coordenacao', coord_padrao)).strip() or coord_padrao,
            'nf_procisa': str(r.get('nf_procisa', nf_padrao)).strip() or nf_padrao
        })
    return pd.DataFrame(linhas_pdf)

# ==========================================
# MÓDULO 2: SOLICITAÇÃO DE MOVIMENTAÇÃO (COM BLOQUEIO DE SEGREGADOS/ROUBADOS)
# ==========================================
def render_modulo_solicitacao(df_ativos, df_empregados):
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("📝 Solicitação de Movimentação de Equipamentos")
    st.caption("Selecione a modalidade, digite a matrícula para puxar automaticamente o Nome do Responsável e marque um ou mais equipamentos na tabela estilo Excel.")
    
    opcoes_mov = [
        "MOV-01 | Almoxarifado -> Colaborador", 
        "MOV-02 | Colaborador -> Almoxarifado", 
        "MOV-03 | Unidade -> Unidade", 
        "MOV-04 | Almoxarifado -> Laboratório",
        "MOV-05 | Laboratório -> Almoxarifado"
    ]
    c_top1, c_top2 = st.columns(2)
    with c_top1:
        tipo_mov = st.selectbox("1️⃣ Selecione o Tipo de Movimentação:", opcoes_mov)
        cod_tipo = tipo_mov[:6]
    
    matricula_busca = ""
    unidade_escolhida = ""
    emp_dict = {}
    
    with c_top2:
        if cod_tipo == "MOV-01":
            matricula_busca = st.text_input("2️⃣ Digite a Matrícula (ou Nome) do Colaborador e pressione Enter:")
            if matricula_busca.strip():
                emp_dict = localizar_colaborador(matricula_busca, df_empregados)
                if emp_dict:
                    st.success(f"👤 **Responsável Localizado:** {emp_dict.get('nome', '')} | Matrícula: {emp_dict.get('matricula', '')} | Proj: {emp_dict.get('projeto', '')} | Área: {emp_dict.get('unidade', '')}")
                else:
                    st.warning("⚠️ Matrícula não localizada na base de colaboradores. Digite o nome do responsável abaixo.")
        elif cod_tipo == "MOV-03":
            unidades_existentes = []
            if not df_empregados.empty and 'unidade' in df_empregados.columns:
                unidades_existentes += df_empregados['unidade'].dropna().astype(str).tolist()
            if not df_ativos.empty and 'coordenacao' in df_ativos.columns:
                unidades_existentes += df_ativos['coordenacao'].dropna().astype(str).tolist()
            unidades_limpas = sorted(list({u.strip() for u in unidades_existentes if u.strip() and u.strip().lower() != 'none'}))
            opcoes_unid = ["Digitar Manualmente..."] + unidades_limpas
            sel_unid = st.selectbox("2️⃣ Selecione a Unidade / Coordenação de Destino:", opcoes_unid)
            if sel_unid == "Digitar Manualmente...":
                unidade_escolhida = st.text_input("Nome da Unidade de Destino:")
            else:
                unidade_escolhida = sel_unid
        else:
            st.info(f"⚡ **Auto-Preenchimento Ativo:** Destino configurado automaticamente para **{tipo_mov.split('->')[1].strip()}**.")

    st.markdown("###### 3️⃣ Busque (Estilo Filtro Excel) e marque na tabela o(s) Equipamento(s) para movimentar:")
    # Bloqueio de Movimentação: impede empréstimo/transferência de itens Segregados para Descarte, Roubados/Furtados ou Baixados
    df_ativos_mov = df_ativos[
        ~df_ativos['status_sistema'].astype(str).str.upper().str.strip().isin(['SEGREGADO PARA DESCARTE', 'ROUBADO/FURTADO', 'BAIXADO'])
    ].copy() if not df_ativos.empty else pd.DataFrame()
    df_sel_ativos = render_seletor_excel_equipamentos(df_ativos_mov, "solic_mov_eqp", multiplo=True, altura=230)

    if not df_sel_ativos.empty:
        primeiro_reg = df_sel_ativos.iloc[0].to_dict()
        cautela_atual = str(primeiro_reg.get('cautela', ''))
        origem_auto = cautela_atual if cautela_atual else "ALMOXARIFADO CENTRAL"
        
        if cod_tipo == "MOV-01":
            origem_auto = "ALMOXARIFADO CENTRAL"
            destino_auto = emp_dict.get('nome', '')
            projeto_auto = emp_dict.get('projeto', primeiro_reg.get('projeto', ''))
            coord_auto = emp_dict.get('unidade', primeiro_reg.get('coordenacao', ''))
            mat_auto = emp_dict.get('matricula', limpar_texto_matricula(matricula_busca))
        elif cod_tipo in ["MOV-02", "MOV-05"]:
            if cod_tipo == "MOV-05":
                origem_auto = "LABORATÓRIO TÉCNICO - PROCISA"
            destino_auto = "ALMOXARIFADO CENTRAL"
            projeto_auto = "ESTOQUE ALMOXARIFADO"
            coord_auto = "LOGÍSTICA / ALMOXARIFADO"
            mat_auto = ""
        elif cod_tipo == "MOV-04":
            destino_auto = "LABORATÓRIO TÉCNICO - PROCISA"
            projeto_auto = "MANUTENÇÃO / LAB"
            coord_auto = "LABORATÓRIO"
            mat_auto = ""
        elif cod_tipo == "MOV-03":
            destino_auto = unidade_escolhida
            proj_unid = primeiro_reg.get('projeto', '')
            if unidade_escolhida and not df_empregados.empty:
                m_u = df_empregados[df_empregados['unidade'].astype(str).str.upper() == unidade_escolhida.upper()]
                if not m_u.empty:
                    proj_unid = m_u.iloc[0].get('projeto', proj_unid)
            projeto_auto = proj_unid
            coord_auto = unidade_escolhida
            mat_auto = ""

        sufixo_key = f"{cod_tipo}_{mat_auto}_{unidade_escolhida}"

        with st.form("form_solicitacao_multipla"):
            st.markdown("###### 4️⃣ Confirme os detalhes da destinação do lote:")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.text_input("Modalidade Selecionada", value=tipo_mov, disabled=True)
                origem = st.text_input("Origem Padrão", value=origem_auto, key=f"orig_{sufixo_key}")
            with c2:
                destino = st.text_input("Nome do Responsável / Destino *", value=destino_auto, key=f"dest_{sufixo_key}")
                projeto = st.text_input("Projeto (Destino)", value=projeto_auto, key=f"proj_{sufixo_key}")
            with c3:
                coordenacao = st.text_input("Coordenação / Área (Destino)", value=coord_auto, key=f"coord_{sufixo_key}")
                matricula_col = st.text_input("Matrícula do Colaborador", value=mat_auto, key=f"mat_{sufixo_key}")
                
            c4, c5 = st.columns(2)
            with c4:
                nf_edit = st.text_input("Nota Fiscal / NF Procisa (Opcional)", value=str(primeiro_reg.get('nf_procisa', '')))
            with c5:
                data_mov = st.date_input("Data da Movimentação (Efetiva)", datetime.today())
            
            if st.form_submit_button(f"🚀 Registrar Solicitação para {len(df_sel_ativos)} Equipamento(s)", type="primary"):
                mat_salvar = limpar_texto_matricula(matricula_col) or limpar_texto_matricula(matricula_busca)
                dest_salvar = destino.strip()

                if cod_tipo == "MOV-01" and (not dest_salvar or dest_salvar.isdigit()):
                    emp_tardio = localizar_colaborador(mat_salvar or dest_salvar, df_empregados)
                    if emp_tardio:
                        dest_salvar = emp_tardio.get('nome', dest_salvar)
                        mat_salvar = emp_tardio.get('matricula', mat_salvar)
                        if not projeto.strip():
                            projeto = emp_tardio.get('projeto', '')
                        if not coordenacao.strip():
                            coordenacao = emp_tardio.get('unidade', '')

                if dest_salvar:
                    stamp_lote = datetime.now().strftime('%Y%m%d-%H%M%S')
                    agora_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    novas_movs = []

                    for idx_m, (_, row_at) in enumerate(df_sel_ativos.iterrows(), start=1):
                        pat_item = str(row_at['patrimonio']).strip()
                        id_mov_item = f"MOV-{stamp_lote}-{idx_m:02d}"
                        orig_item = origem.strip() if len(df_sel_ativos) == 1 else (str(row_at.get('cautela', '')).strip() or origem.strip())
                        novas_movs.append({
                            'id_mov': id_mov_item, 
                            'data_hora': agora_str, 
                            'tipo_mov': cod_tipo, 
                            'patrimonio': pat_item, 
                            'origem': orig_item, 
                            'destino': dest_salvar, 
                            'solicitante': st.session_state.get('nome_real', dest_salvar),
                            'matricula_solicitante': mat_salvar,
                            'autorizador': 'Pendente', 
                            'status_mov': 'Aguardando Conferência',
                            'nf_procisa': nf_edit.strip(),
                            'projeto': projeto.strip(),
                            'coordenacao': coordenacao.strip(),
                            'data_efetiva': data_mov.strftime('%Y-%m-%d')
                        })
                    
                    try:
                        supabase.table('movimentacoes').insert(novas_movs).execute()
                        st.session_state["sel_excel_pats_solic_mov_eqp"] = set()
                        st.cache_data.clear()
                        registrar_log_auditoria(
                            "SOLICITAÇÃO EM LOTE", 
                            f"{len(novas_movs)} ativos", 
                            f"Lote MOV-{stamp_lote} ({cod_tipo}) registrado para Destino: {dest_salvar} (Mat: {mat_salvar})."
                        )
                        st.success(f"✅ {len(novas_movs)} equipamento(s) enviado(s) para a fila da Central de Validações em nome de **{dest_salvar}**!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar solicitação em lote: {e}")
                else:
                    st.error("O campo 'Nome do Responsável / Destino' deve estar preenchido.")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 3: CENTRAL DE VALIDAÇÕES (SUPORTE A LOTE E INDIVIDUAL)
# ==========================================
def render_modulo_validacoes(df_ativos, df_mov, df_termos, df_empregados):
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("✅ Central de Validações (Almoxarifado)")
    
    if st.session_state.get('msg_sucesso'):
        st.success(st.session_state.msg_sucesso)
        if st.button("✖️ Fechar Aviso"):
            st.session_state.msg_sucesso = None
            st.rerun()
        st.divider()
    
    movs_pendentes = df_mov[df_mov['status_mov'] == 'Aguardando Conferência'].copy() if not df_mov.empty else pd.DataFrame()
    
    if movs_pendentes.empty:
        st.success("🎉 Excelente! Nenhuma solicitação pendente no momento.")
    else:
        st.caption("Marque a caixinha **'🗑️ Cancelar?'** caso precise excluir solicitações indevidas, ou valide abaixo por Lote / Individual.")
        
        df_mov_view = movs_pendentes[['id_mov', 'data_hora', 'tipo_mov', 'patrimonio', 'origem', 'destino', 'solicitante', 'matricula_solicitante']].copy()
        df_mov_view.insert(0, "Excluir", False)
        
        df_mov_editado = st.data_editor(
            df_mov_view,
            hide_index=True,
            use_container_width=True,
            disabled=[c for c in df_mov_view.columns if c != "Excluir"],
            column_config={"Excluir": st.column_config.CheckboxColumn("🗑️ Cancelar?", default=False)},
            key="editor_mov_pendentes"
        )
        
        movs_selecionadas = df_mov_editado[df_mov_editado["Excluir"] == True]
        if not movs_selecionadas.empty:
            st.error(f"⚠️ Selecionou **{len(movs_selecionadas)} solicitação(ões)** para cancelamento direto da fila.")
            if st.button("🗑️ Confirmar Cancelamento", type="primary"):
                try:
                    for m_del in movs_selecionadas['id_mov'].tolist():
                        supabase.table('movimentacoes').delete().eq('id_mov', m_del).execute()
                    registrar_log_auditoria("CANCELAMENTO MOV.", f"{len(movs_selecionadas)} itens", "Solicitações canceladas da fila do almoxarifado.")
                    st.cache_data.clear()
                    st.success("✅ Solicitações canceladas com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cancelar: {e}")
        
        st.divider()
        st.markdown("###### 🔄 Proceder com a Validação (Agrupada por Lote/Destinatário ou Individual)")

        def _extrair_chave_lote(row):
            idm = str(row.get('id_mov', ''))
            partes = idm.split('-')
            if len(partes) >= 3:
                return f"{partes[0]}-{partes[1]}-{partes[2]} | {row.get('tipo_mov')} -> {row.get('destino')} (Mat: {row.get('matricula_solicitante')})"
            return f"{idm} | {row.get('tipo_mov')} -> {row.get('destino')}"

        movs_pendentes['chave_lote'] = movs_pendentes.apply(_extrair_chave_lote, axis=1)
        lotes_disp = movs_pendentes['chave_lote'].unique().tolist()

        modo_val = st.radio("Modo de Validação:", ["📦 Validar Lote Completo (Múltiplos Itens do Mesmo Pedido)", "🔍 Validar Item Individual"], horizontal=True)

        if modo_val.startswith("📦"):
            lote_escolhido = st.selectbox("Selecione o Lote Pendente:", lotes_disp)
            df_lote_atual = movs_pendentes[movs_pendentes['chave_lote'] == lote_escolhido].copy()
        else:
            id_ind = st.selectbox("Selecione o ID da Movimentação:", movs_pendentes['id_mov'].tolist())
            df_lote_atual = movs_pendentes[movs_pendentes['id_mov'] == id_ind].copy()

        if not df_lote_atual.empty:
            mov_ref = df_lote_atual.iloc[0].to_dict()
            tipo_m = str(mov_ref.get('tipo_mov', ''))
            pats_lote = df_lote_atual['patrimonio'].astype(str).tolist()

            nome_res, mat_res, _, _, proj_res, unid_res = _resolver_dados_termo_colaborador(
                mov_ref.get('destino', ''), mov_ref.get('matricula_solicitante', ''),
                mov_ref.get('coordenacao', ''), mov_ref.get('projeto', ''), df_empregados
            )
            cautela_sugerida = nome_res if tipo_m.startswith("MOV-01") else str(mov_ref.get('destino', ''))

            st.info(f"**Itens neste processo ({len(pats_lote)}):** `{', '.join(pats_lote)}` | **Destinatário:** {cautela_sugerida} (Mat: {mat_res})")

            opcoes_st = ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"]
            if tipo_m in ["MOV-02", "MOV-05"] or 'ALMOX' in str(mov_ref.get('destino', '')).upper():
                idx_sugerido = 0
            elif tipo_m == "MOV-04" or 'LAB' in str(mov_ref.get('destino', '')).upper():
                idx_sugerido = 2
            else:
                idx_sugerido = 1

            with st.form("form_validacao_lote"):
                colA, colB = st.columns(2)
                with colA:
                    novo_status = st.selectbox("Novo Status no Sistema:", opcoes_st, index=idx_sugerido)
                with colB:
                    nova_cautela = st.text_input("Atualizar Cautela (Nome do Responsável / Destino Real)", value=cautela_sugerida)

                st.write("Verificações de Segurança:")
                d365_ok = st.checkbox("Status e Localização conferem no sistema central?")
                eponto_ok = st.checkbox("Movimentação validada no e-Ponto?")
                fisico_ok = st.checkbox("Estado físico, Série e Acessórios conferem?")

                if st.form_submit_button(f"✅ Validar e Concluir Transferência ({len(df_lote_atual)} item/itens)", type="primary"):
                    if d365_ok and eponto_ok and fisico_ok:
                        try:
                            stamp_trm = datetime.now().strftime('%Y%m%d%H%M%S')
                            termos_inserir = []

                            for idx_v, (_, m_row) in enumerate(df_lote_atual.iterrows(), start=1):
                                pat_i = str(m_row['patrimonio']).strip()
                                id_m_i = str(m_row['id_mov']).strip()

                                nome_emp_v, mat_emp_v, _, _, proj_emp_v, unid_emp_v = _resolver_dados_termo_colaborador(
                                    nova_cautela.strip(), m_row.get('matricula_solicitante', ''),
                                    m_row.get('coordenacao', ''), m_row.get('projeto', ''), df_empregados
                                )

                                supabase.table('ativos_master').update({
                                    'status_sistema': novo_status,
                                    'cautela': nome_emp_v if tipo_m.startswith("MOV-01") else nova_cautela.strip(),
                                    'projeto': proj_emp_v,
                                    'coordenacao': unid_emp_v,
                                    'nf_procisa': str(m_row.get('nf_procisa', '')).strip(),
                                    'atualizado_em': str(m_row.get('data_efetiva', datetime.now().strftime('%Y-%m-%d'))).strip()
                                }).eq('patrimonio', pat_i).execute()

                                supabase.table('movimentacoes').update({
                                    'status_mov': 'Concluído',
                                    'destino': nome_emp_v if tipo_m.startswith("MOV-01") else nova_cautela.strip(),
                                    'matricula_solicitante': mat_emp_v,
                                    'autorizador': st.session_state.nome_real
                                }).eq('id_mov', id_m_i).execute()

                                if tipo_m.startswith("MOV-01"):
                                    termos_inserir.append({
                                        'id_termo': f"TRM-{stamp_trm}-{idx_v:02d}",
                                        'patrimonio': pat_i,
                                        'responsavel': nome_emp_v,
                                        'matricula': mat_emp_v,
                                        'unidade': unid_emp_v,
                                        'data_emissao': datetime.now().strftime('%Y-%m-%d'),
                                        'data_baixa': '',
                                        'status_termo': 'Pendente Impressão'
                                    })
                                elif tipo_m.startswith("MOV-02") and not df_termos.empty:
                                    termos_abertos = df_termos[(df_termos['patrimonio'].astype(str) == pat_i) & (df_termos['status_termo'].isin(['Ativo', 'Pendente Impressão']))]
                                    for _, t_row in termos_abertos.iterrows():
                                        supabase.table('termos').update({
                                            'data_baixa': datetime.now().strftime('%Y-%m-%d'),
                                            'status_termo': 'Encerrado'
                                        }).eq('id_termo', t_row['id_termo']).execute()

                            if termos_inserir:
                                supabase.table('termos').insert(termos_inserir).execute()
                                st.session_state.msg_sucesso = f"✅ {len(termos_inserir)} equipamento(s) validado(s)! O Lote de Termos (`TRM-{stamp_trm}`) foi enviado para a Fila de Impressão (Módulo 4)."
                            elif tipo_m.startswith("MOV-02"):
                                st.session_state.msg_sucesso = f"✅ Devolução de {len(df_lote_atual)} equipamento(s) validada e termos baixados automaticamente!"
                            else:
                                st.session_state.msg_sucesso = f"✅ Transferência de {len(df_lote_atual)} equipamento(s) concluída!"

                            registrar_log_auditoria("VALIDAÇÃO LOTE", f"{len(df_lote_atual)} itens", f"Validado para Cautela: {nova_cautela.strip()}")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao concluir validação: {e}")
                    else:
                        st.error("Complete as 3 caixas de verificação antes de validar.")

    st.divider()
    with st.expander("🛠️ Movimentação Avulsa (Excepcional / Sem solicitação prévia — Busca Estilo Excel)"):
        df_av_sel = render_seletor_excel_equipamentos(df_ativos, "avulso_val_eqp", multiplo=True, altura=190)
        if not df_av_sel.empty:
            reg_av0 = df_av_sel.iloc[0].to_dict()
            with st.form("form_avulso"):
                cA, cB, cC = st.columns(3)
                with cA:
                    status_av = st.selectbox("Status", ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"])
                with cB:
                    cautela_av = st.text_input("Nova Cautela", value=reg_av0.get('cautela', ''))
                with cC:
                    end1_av = st.text_input("Endereçamento 01", value=reg_av0.get('enderecamento_01', ''))
                
                if st.form_submit_button(f"✅ Forçar Atualização em {len(df_av_sel)} Equipamento(s)"):
                    try:
                        for _, r_av in df_av_sel.iterrows():
                            pat_av_i = str(r_av['patrimonio']).strip()
                            supabase.table('ativos_master').update({
                                'status_sistema': status_av,
                                'cautela': cautela_av.strip(),
                                'enderecamento_01': end1_av.strip().upper(),
                                'atualizado_em': datetime.now().strftime('%Y-%m-%d')
                            }).eq('patrimonio', pat_av_i).execute()
                        st.session_state["sel_excel_pats_avulso_val_eqp"] = set()
                        st.cache_data.clear()
                        registrar_log_auditoria("MOVIMENTAÇÃO AVULSA", f"{len(df_av_sel)} itens", f"Atualizado para {status_av} / {cautela_av}")
                        st.success("✅ Atualizado com sucesso.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 4: GESTÃO DE TERMOS E DIVERGÊNCIAS (COM AUTO-PREENCHIMENTO E PDF CORRIGIDO)
# ==========================================
def render_modulo_termos_divergencias(df_ativos, df_termos, df_diverg, df_empregados):
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("📄 Gestão de Termos (PDF Multi-Equipamentos) e Divergências")
    
    if st.session_state.get('pdf_termo_pronto'):
        st.success(st.session_state.pdf_termo_pronto.get('msg', "✅ Termo gerado com sucesso!"))
        st.download_button(
            label="📥 Baixar Termo PDF (Modelo Oficial PROCISA FR-RH-P-026)", 
            data=st.session_state.pdf_termo_pronto['bytes'], 
            file_name=st.session_state.pdf_termo_pronto['nome_arquivo'], 
            mime='application/pdf',
            type="primary"
        )
        if st.button("✖️ Fechar Aviso"):
            st.session_state.pdf_termo_pronto = None
            st.rerun()
        st.divider()

    aba_fila, aba_reimp, aba_avulso, aba_diverg = st.tabs([
        "🖨️ Fila de Impressão (Termos Pendentes)",
        "🔄 Termos Emitidos (Reimpressão 2ª Via)",
        "➕ Emitir Termo Multi-Itens / Baixar Termo",
        "🚨 Tratar Divergências"
    ])
    
    with aba_fila:
        st.caption("Termos gerados pelas validações (MOV-01). Lotes do mesmo colaborador são agrupados automaticamente num único PDF.")
        termos_pendentes = df_termos[df_termos['status_termo'] == 'Pendente Impressão'].copy() if not df_termos.empty else pd.DataFrame()
        
        if not termos_pendentes.empty:
            def _grupo_fila(row):
                idt = str(row.get('id_termo', ''))
                partes = idt.split('-')
                prefixo = f"{partes[0]}-{partes[1]}" if len(partes) >= 2 else idt
                return f"{prefixo} | {row.get('responsavel', '')} (Mat: {row.get('matricula', '')}) | Data: {row.get('data_emissao', '')}"

            termos_pendentes['grupo_imp'] = termos_pendentes.apply(_grupo_fila, axis=1)
            grupos_pendentes = termos_pendentes['grupo_imp'].unique().tolist()

            st.dataframe(termos_pendentes[['id_termo', 'patrimonio', 'responsavel', 'matricula', 'unidade', 'data_emissao']], use_container_width=True, hide_index=True)
            
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                grupo_sel = st.selectbox("Selecione o Lote / Colaborador da Fila para Imprimir:", grupos_pendentes)
            with col_f2:
                st.write("")
                st.write("")
                if st.button("🖨️ Gerar PDF Único e Ativar", type="primary", use_container_width=True):
                    df_sub_fila = termos_pendentes[termos_pendentes['grupo_imp'] == grupo_sel]
                    t_info = df_sub_fila.iloc[0]
                    pats_fila = df_sub_fila['patrimonio'].astype(str).tolist()
                    
                    ativos_match = df_ativos[df_ativos['patrimonio'].astype(str).isin(pats_fila)] if not df_ativos.empty else pd.DataFrame()
                    
                    if not ativos_match.empty:
                        resp_nome, mat_ok, resp_cpf, resp_rg, resp_proj, resp_unid = _resolver_dados_termo_colaborador(
                            t_info.get('responsavel', ''), t_info.get('matricula', ''),
                            t_info.get('unidade', ''), ativos_match.iloc[0].get('projeto', ''), df_empregados
                        )
                        
                        df_pdf_pronto = _montar_df_pdf_equipamentos(ativos_match, resp_unid, str(t_info['id_termo']))
                        caminho_pdf = gerar_termo_pdf(pats_fila[0], resp_nome, mat_ok, resp_cpf, resp_rg, resp_proj, resp_unid, df_pdf_pronto)
                        with open(caminho_pdf, "rb") as pdf_file: 
                            PDFbyte = pdf_file.read()
                        
                        try:
                            for id_t_up in df_sub_fila['id_termo'].tolist():
                                supabase.table('termos').update({
                                    'status_termo': 'Ativo',
                                    'responsavel': resp_nome,
                                    'matricula': mat_ok,
                                    'unidade': resp_unid
                                }).eq('id_termo', id_t_up).execute()
                            st.cache_data.clear()
                            registrar_log_auditoria("IMPRESSÃO TERMO FILA", f"{len(pats_fila)} ativos", f"Termo impresso e ativado para {resp_nome} (Mat: {mat_ok}).")
                            
                            st.session_state.pdf_termo_pronto = {
                                'bytes': PDFbyte,
                                'nome_arquivo': f"Termo_PROCISA_{resp_nome.replace(' ', '_')}_{pats_fila[0]}.pdf",
                                'msg': f"✅ Termo com {len(pats_fila)} equipamento(s) gerado e ativado em nome de **{resp_nome}**!"
                            }
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar status: {e}")
                    else:
                        st.error("Erro: Equipamento(s) vinculado(s) não encontrado(s) na base.")
        else:
            st.success("🎉 Nenhum termo pendente na fila de impressão.")

    with aba_reimp:
        st.markdown("###### 🔄 Central de Reimpressão de Termos Emitidos (2ª Via Sob Demanda)")
        st.caption("Reconstrói o PDF oficial na hora (resgatando Nome, RG, CPF e Matrícula da base de colaboradores) sem ocupar espaço no banco.")
        if not df_termos.empty:
            df_t_reimp = df_termos.copy()
            def _chave_reimp(row):
                idt = str(row.get('id_termo', ''))
                partes = idt.split('-')
                prefixo = f"{partes[0]}-{partes[1]}" if len(partes) >= 2 else idt
                return f"{prefixo} | {row.get('responsavel', '')} (Mat: {row.get('matricula', '')}) | Emissão: {row.get('data_emissao', '')} [{row.get('status_termo', '')}]"

            df_t_reimp['grupo_reimp'] = df_t_reimp.apply(_chave_reimp, axis=1)
            opcoes_2via = list(reversed(df_t_reimp['grupo_reimp'].unique().tolist()))
            sel_2via = st.selectbox("Selecione o Termo / Lote para Reimpressão (2ª Via):", opcoes_2via)
            df_itens_2via = df_t_reimp[df_t_reimp['grupo_reimp'] == sel_2via]
            st.dataframe(df_itens_2via[['id_termo', 'patrimonio', 'responsavel', 'matricula', 'unidade', 'data_emissao', 'status_termo']], use_container_width=True, hide_index=True)

            if st.button("🖨️ Reconstruir e Baixar 2ª Via em PDF", type="primary"):
                t_info = df_itens_2via.iloc[0]
                pats_2via = df_itens_2via['patrimonio'].astype(str).tolist()
                ativos_match = df_ativos[df_ativos['patrimonio'].astype(str).isin(pats_2via)] if not df_ativos.empty else pd.DataFrame()
                
                if not ativos_match.empty:
                    resp_nome, mat_ok, resp_cpf, resp_rg, resp_proj, resp_unid = _resolver_dados_termo_colaborador(
                        t_info.get('responsavel', ''), t_info.get('matricula', ''),
                        t_info.get('unidade', ''), ativos_match.iloc[0].get('projeto', ''), df_empregados
                    )
                    df_pdf_2via = _montar_df_pdf_equipamentos(ativos_match, resp_unid, str(t_info['id_termo']))
                    caminho_pdf = gerar_termo_pdf(
                        pats_2via[0], resp_nome, mat_ok,
                        resp_cpf, resp_rg, resp_proj, resp_unid, df_pdf_2via
                    )
                    with open(caminho_pdf, "rb") as pdf_file:
                        PDFbyte = pdf_file.read()
                    st.session_state.pdf_termo_pronto = {
                        'bytes': PDFbyte,
                        'nome_arquivo': f"2Via_Termo_PROCISA_{resp_nome.replace(' ', '_')}.pdf",
                        'msg': f"✅ 2ª Via do Termo de **{resp_nome}** ({len(pats_2via)} equipamento(s)) gerada dinamicamente!"
                    }
                    st.rerun()
                else:
                    st.error("Ativo(s) vinculado(s) não encontrado(s) na base mestra.")
        else:
            st.info("Nenhum termo registado no histórico.")

    with aba_avulso:
        acao_trm = st.radio("Selecione a Operação:", ["📤 Emitir Novo Termo Excepcional (Multi-Equipamentos)", "📥 Encerrar / Baixar Termo Ativo (Devolução)"], horizontal=True)
        if acao_trm.startswith("📤"):
            st.markdown("###### 1️⃣ Busque (Estilo Excel) e marque o(s) Equipamento(s) para o Termo:")
            ativos_info_t = render_seletor_excel_equipamentos(df_ativos, "termo_avulso_eqp", multiplo=True, altura=210)

            matricula_busca = st.text_input("2️⃣ Digite a Matrícula (ou Nome) do Colaborador e pressione Enter:")
            emp_dict = localizar_colaborador(matricula_busca, df_empregados)
            if matricula_busca.strip():
                if emp_dict:
                    st.success(f"👤 Colaborador Localizado: **{emp_dict.get('nome', '')}** | Matrícula: {emp_dict.get('matricula', '')} | CPF: {emp_dict.get('cpf', '')}")
                else:
                    st.warning("⚠️ Colaborador não localizado pela matrícula digitada. Preencha abaixo.")

            suf_trm = emp_dict.get('matricula', limpar_texto_matricula(matricula_busca))

            with st.form("form_termo_avulso_multi"):
                colA, colB = st.columns(2)
                with colA:
                    responsavel_termo = st.text_input("Nome do Responsável *", value=emp_dict.get('nome', ''), key=f"trm_nom_{suf_trm}")
                    cpf_termo = st.text_input("CPF", value=emp_dict.get('cpf', ''), key=f"trm_cpf_{suf_trm}")
                    rg_termo = st.text_input("RG", value=emp_dict.get('rg', ''), key=f"trm_rg_{suf_trm}")
                with colB:
                    matricula_termo = st.text_input("Matrícula *", value=suf_trm, key=f"trm_mat_{suf_trm}")
                    unidade_termo = st.text_input("Unidade / Área / Coordenação", value=emp_dict.get('unidade', ''), key=f"trm_uni_{suf_trm}")
                    projeto_termo = st.text_input("Projeto", value=emp_dict.get('projeto', ''), key=f"trm_prj_{suf_trm}")
                submit_termo = st.form_submit_button("🖨️ Gerar PDF Único do Termo", type="primary")
                
            if submit_termo and (not ativos_info_t.empty):
                resp_nome, mat_salvar, cpf_f, rg_f, proj_f, unid_f = _resolver_dados_termo_colaborador(
                    responsavel_termo, matricula_termo or matricula_busca,
                    unidade_termo, projeto_termo, df_empregados
                )
                cpf_f = cpf_termo.strip() or cpf_f
                rg_f = rg_termo.strip() or rg_f

                if resp_nome:
                    pats_t = ativos_info_t['patrimonio'].astype(str).tolist()
                    stamp_av = datetime.now().strftime('%Y%m%d%H%M%S')

                    df_pdf_av = _montar_df_pdf_equipamentos(ativos_info_t, unid_f, f"TRM-{stamp_av}")
                    caminho_pdf = gerar_termo_pdf(
                        pats_t[0], resp_nome, mat_salvar, 
                        cpf_f, rg_f, proj_f, unid_f, 
                        df_pdf_av
                    )
                    with open(caminho_pdf, "rb") as pdf_file: 
                        PDFbyte = pdf_file.read()
                    
                    novos_termos_av = []
                    for idx_a, p_a in enumerate(pats_t, start=1):
                        novos_termos_av.append({
                            'id_termo': f"TRM-{stamp_av}-{idx_a:02d}", 
                            'patrimonio': p_a, 
                            'responsavel': resp_nome, 
                            'matricula': mat_salvar, 
                            'unidade': unid_f, 
                            'data_emissao': datetime.now().strftime('%Y-%m-%d'), 
                            'data_baixa': '', 
                            'status_termo': 'Ativo'
                        })
                    supabase.table('termos').insert(novos_termos_av).execute()
                    st.session_state["sel_excel_pats_termo_avulso_eqp"] = set()
                    st.cache_data.clear()
                    registrar_log_auditoria("EMISSÃO DE TERMO (AVULSO)", f"{len(pats_t)} ativos", f"Termo emitido para {resp_nome} (Mat: {mat_salvar}).")
                    st.session_state.pdf_termo_pronto = {
                        'bytes': PDFbyte,
                        'nome_arquivo': f"Termo_PROCISA_{resp_nome.replace(' ', '_')}.pdf",
                        'msg': f"✅ Termo com {len(pats_t)} equipamento(s) emitido em nome de **{resp_nome}**!"
                    }
                    st.rerun()
                else:
                    st.error("Informe o Nome do Responsável ou uma Matrícula válida.")
        else:
            st.markdown("###### Busque e marque o(s) equipamento(s) devolvido(s) para encerrar o Termo:")
            df_bx_sel = render_seletor_excel_equipamentos(df_ativos, "baixa_trm_eqp", multiplo=True, altura=190)
            if not df_bx_sel.empty and st.button(f"📥 Baixar Termo(s) Ativo(s) ({len(df_bx_sel)} selecionado(s))", type="primary"):
                pats_bx = df_bx_sel['patrimonio'].astype(str).tolist()
                termos_ativos = df_termos[(df_termos['patrimonio'].astype(str).isin(pats_bx)) & (df_termos['status_termo'].isin(['Ativo', 'Pendente Impressão']))] if not df_termos.empty else pd.DataFrame()
                if not termos_ativos.empty:
                    for _, t_r in termos_ativos.iterrows():
                        supabase.table('termos').update({
                            'data_baixa': datetime.now().strftime('%Y-%m-%d'),
                            'status_termo': 'Encerrado'
                        }).eq('id_termo', t_r['id_termo']).execute()
                    st.session_state["sel_excel_pats_baixa_trm_eqp"] = set()
                    st.cache_data.clear()
                    registrar_log_auditoria("BAIXA DE TERMO", f"{len(pats_bx)} itens", "Termo(s) encerrado(s) por devolução.")
                    st.success("✅ Termo(s) encerrado(s) com sucesso!")
                    st.rerun()
                else:
                    st.warning("Nenhum termo ativo encontrado para o(s) equipamento(s) selecionado(s).")

    with aba_diverg:
        pendentes = df_diverg[df_diverg['status_resolucao'] != 'Resolvido'] if not df_diverg.empty else pd.DataFrame()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("###### Reportar Nova Divergência")
            pat_div = st.text_input("Patrimônio com Divergência:")
            obs_abertura = st.text_input("Descrição do Problema (Ex: Falta fonte, Série divergente):")
            if st.button("🚨 Abrir Alerta e Segregar Ativo", type="secondary"):
                if pat_div.strip():
                    id_div = f"DIV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    nova_div = {
                        'id_divergencia': id_div, 
                        'data_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                        'patrimonio': pat_div.strip(), 
                        'tipo_divergencia': 'Inconsistência Relatada pelo Almoxarifado', 
                        'status_resolucao': 'Pendente', 
                        'analista_responsavel': st.session_state.nome_real, 
                        'observacoes': obs_abertura.strip() if obs_abertura.strip() else 'Ativo segregado manualmente.'
                    }
                    supabase.table('divergencias').insert(nova_div).execute()
                    st.cache_data.clear()
                    registrar_log_auditoria("DIVERGÊNCIA ABERTA", pat_div.strip(), f"Abertura manual: {obs_abertura}")
                    st.success("Alerta criado com sucesso!")
                    st.rerun()
                        
        with c2:
            st.markdown("###### Resolver Pendência")
            if not pendentes.empty:
                st.dataframe(pendentes[['id_divergencia', 'patrimonio', 'observacoes']], use_container_width=True, hide_index=True)
                id_div_selecionada = st.selectbox("Selecione a Divergência:", pendentes['id_divergencia'].tolist())
                obs = st.text_area("Justificativa / Ação Tomada:")
                analista = st.text_input("Analista Responsável:", value=st.session_state.nome_real)
                if st.button("Aplicar Resolução", type="primary"):
                    if obs.strip() and analista.strip():
                        supabase.table('divergencias').update({
                            'status_resolucao': 'Resolvido',
                            'observacoes': obs.strip(),
                            'analista_responsavel': analista.strip()
                        }).eq('id_divergencia', id_div_selecionada).execute()
                        st.cache_data.clear()
                        div_pat = pendentes[pendentes['id_divergencia'] == id_div_selecionada].iloc[0]['patrimonio']
                        registrar_log_auditoria("RESOLUÇÃO DIVERGÊNCIA", div_pat, f"Divergência {id_div_selecionada} resolvida. Ação: {obs.strip()}")
                        st.success("✅ Divergência resolvida com sucesso!")
                        st.rerun()
                    else:
                        st.error("Preencha a justificativa.")
            else:
                st.success("Nenhuma divergência pendente!")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 5: DIAGNÓSTICO (LABORATÓRIO - COM SELETOR ESTILO EXCEL)
# ==========================================
def render_modulo_laboratorio(df_ativos):
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("🔬 Laboratório Técnico (Busca Estilo Excel)")
    st.markdown("###### 1️⃣ Filtre e marque o(s) equipamento(s) em análise:")
    df_lab_sel = render_seletor_excel_equipamentos(df_ativos, "lab_eqp_sel", multiplo=True, altura=210)
            
    resultado = st.radio("2️⃣ Parecer Técnico:", ["APTO", "APTO COM RESSALVA", "REPARADO", "CALIBRADO", "REPROVADO", "INSERVÍVEL"], horizontal=True)
    acessorios_lab = st.text_input("Atualizar Observação / Acessórios (Opcional):")
    
    if st.button("💾 Atualizar Base com Parecer Técnico", type="primary"):
        if not df_lab_sel.empty:
            novo_status = 'Baixado' if ("INSERVÍVEL" in resultado or "REPROVADO" in resultado) else 'Disponível'
            try:
                for _, r_l in df_lab_sel.iterrows():
                    pat_real = str(r_l['patrimonio']).strip()
                    cond_antiga = str(r_l.get('condicoes_para_uso', ''))
                    dados_update_lab = {
                        'condicoes_para_uso': resultado,
                        'status_sistema': novo_status,
                        'atualizado_em': datetime.now().strftime('%Y-%m-%d')
                    }
                    if acessorios_lab.strip():
                        dados_update_lab['acessorios'] = acessorios_lab.strip()
                    supabase.table('ativos_master').update(dados_update_lab).eq('patrimonio', pat_real).execute()
                    registrar_log_auditoria("LAUDO LABORATÓRIO", pat_real, f"Parecer: '{cond_antiga}' -> '{resultado}'. Novo Status: '{novo_status}'.")
                st.session_state["sel_excel_pats_lab_eqp_sel"] = set()
                st.cache_data.clear()
                st.success(f"✅ Laudo registrado para {len(df_lab_sel)} equipamento(s)! Status atualizado para: {novo_status}")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar laudo: {e}")
        else:
            st.warning("⚠️ Marque pelo menos um equipamento na tabela acima.")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 8 (EQUIPAMENTOS): MODO OPERADOR QR CODE AUTOMÁTICO + FOLHA A4 PADRÃO PROCISA
# ==========================================
def render_operador_qrcode_eqp(df_ativos, df_empregados):
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    gerar_etiquetas_qrcode_pdf = getattr(pdf_termo, 'gerar_etiquetas_qrcode_pdf', None)
    render_leitor_fn = getattr(nuvem, 'render_leitor_qrcode_mobile', None)

    st.subheader("📷 Modo Operador — Leitura Automática de QR Code (Equipamentos)")
    st.caption("Ative o '📱 Scanner Ao Vivo (Auto)' no smartphone para leitura automática contínua ou utilize o coletor.")

    if st.session_state.get('pdf_etiquetas_eqp_pronto'):
        st.success(st.session_state.pdf_etiquetas_eqp_pronto['msg'])
        st.download_button(
            "📥 Baixar Folha de Etiquetas Padrão PROCISA em PDF (A4 - Equipamentos)",
            data=st.session_state.pdf_etiquetas_eqp_pronto['bytes'],
            file_name=st.session_state.pdf_etiquetas_eqp_pronto['nome'],
            mime="application/pdf",
            type="primary"
        )
        if st.button("✖️ Fechar Folha de Etiquetas (Equipamentos)"):
            st.session_state.pdf_etiquetas_eqp_pronto = None
            st.rerun()
        st.divider()

    aba_sc_eqp, aba_etq_eqp = st.tabs([
        "📡 Coletor / Scanner Automático (Equipamentos)",
        "🏷️ Gerador de Folha de Etiquetas Padrão PROCISA (PDF A4)"
    ])

    with aba_sc_eqp:
        if render_leitor_fn:
            cod_eqp_bruto = render_leitor_fn("eqp_qr", "Ex: US-AC1N1P9 ou Patrimônio...")
        else:
            cod_eqp_bruto = st.text_input("🔫 Bipe ou Digite o Código:", placeholder="Ex: US-AC1N1P9 ou Patrimônio...").strip().upper()

        if cod_eqp_bruto and not df_ativos.empty:
            cod_eqp_qr = cod_eqp_bruto
            if "|" in cod_eqp_bruto and "FER:" in cod_eqp_bruto:
                for p in cod_eqp_bruto.split("|"):
                    if p.startswith("FER:"):
                        cod_eqp_qr = p.replace("FER:", "").strip()

            resultados = buscar_ativo(cod_eqp_qr, df_ativos)
            if not resultados.empty:
                st.success(f"✅ **{len(resultados)} equipamento(s)** localizado(s) para o código `{cod_eqp_bruto}`!")
                df_qr_sel = render_seletor_excel_equipamentos(resultados, "qr_sc_eqp_sel", multiplo=False, altura=180)

                if not df_qr_sel.empty:
                    reg_eq = df_qr_sel.iloc[0].to_dict()
                    pat_sel = str(reg_eq['patrimonio']).strip()

                    with st.form("form_qr_eqp_mov"):
                        ce1, ce2, ce3 = st.columns(3)
                        with ce1:
                            n_end1 = st.text_input("Bipar Novo LOCAL (Endereçamento 01):", value=reg_eq.get('enderecamento_01', ''))
                            n_end2 = st.text_input("Bipar Novo Descri. Local (Endereçamento 02):", value=reg_eq.get('enderecamento_02', ''))
                        with ce2:
                            n_caut = st.text_input("Cautela / Localização:", value=reg_eq.get('cautela', 'ALMOXARIFADO CENTRAL'))
                        with ce3:
                            n_st = st.selectbox("Status:", ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"])

                        if st.form_submit_button("🚀 Atualizar Endereçamento / Localização do Equipamento", type="primary"):
                            supabase.table('ativos_master').update({
                                'enderecamento_01': n_end1.strip().upper(),
                                'enderecamento_02': n_end2.strip().upper(),
                                'cautela': n_caut.strip(),
                                'status_sistema': n_st,
                                'atualizado_em': datetime.now().strftime('%Y-%m-%d')
                            }).eq('patrimonio', pat_sel).execute()
                            registrar_log_auditoria("QR CODE EQUIPAMENTO", pat_sel, f"Endereçado para {n_end1.strip().upper()} / {n_end2.strip().upper()} ({n_caut.strip()})")
                            st.cache_data.clear()
                            st.success(f"✅ Equipamento `{pat_sel}` atualizado com sucesso!")
                            st.rerun()
            else:
                st.warning(f"⚠️ Nenhum equipamento ou endereço localizado para `{cod_eqp_bruto}`.")

    with aba_etq_eqp:
        st.markdown("###### 🖨️ Impressão em Lote de Etiquetas Padronizadas PROCISA (Equipamentos - 8 por Folha A4)")
        if not df_ativos.empty and gerar_etiquetas_qrcode_pdf:
            st.markdown("Filtre (Estilo Excel) e marque na tabela os equipamentos para gerar etiquetas:")
            df_sel_etq_eqp = render_seletor_excel_equipamentos(df_ativos, "etq_lote_eqp_excel", multiplo=True, altura=220)
            etq_eqp_list = []
            for _, r_a in df_sel_etq_eqp.iterrows():
                pat_a = str(r_a['patrimonio']).strip()
                cod_item_d365 = str(r_a.get('item', '')).strip()
                e1_a = str(r_a.get('enderecamento_01', '')).strip()
                e2_a = str(r_a.get('enderecamento_02', '')).strip()
                qr_eqp = f"D365:{cod_item_d365}|FER:{pat_a}|LOC:{e1_a}/{e2_a}"

                etq_eqp_list.append({
                    'codigo_qr': qr_eqp,
                    'item_d365': cod_item_d365,
                    'ref_interna': pat_a,
                    'descricao': f"{r_a.get('equipamento', '')} {r_a.get('marca', '')} {r_a.get('modelo', '')}".strip(),
                    'placa_licenca': '',
                    'local': e1_a,
                    'descri_local': e2_a,
                    'quantidade': '1',
                    'data_criacao': r_a.get('atualizado_em', datetime.now().strftime('%Y-%m-%d')),
                    'obs': '0',
                    'lote': str(r_a.get('numero_serie', '')).strip()
                })
            if etq_eqp_list and st.button(f"🖨️ Gerar PDF com {len(etq_eqp_list)} Etiqueta(s) Padrão PROCISA", type="primary"):
                with st.spinner("Gerando folha A4 de etiquetas padrão PROCISA..."):
                    cam_eq = gerar_etiquetas_qrcode_pdf(etq_eqp_list)
                    with open(cam_eq, "rb") as f_e:
                        st.session_state.pdf_etiquetas_eqp_pronto = {
                            'bytes': f_e.read(),
                            'nome': f"Etiquetas_PROCISA_Equipamentos_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            'msg': f"✅ Folha com {len(etq_eqp_list)} etiqueta(s) no padrão PROCISA gerada!"
                        }
                    st.rerun()
        else:
            st.info("Base de equipamentos vazia.")

    exibir_marca_desenvolvedor()
