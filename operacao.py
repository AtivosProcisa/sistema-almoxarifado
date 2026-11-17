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

def _montar_df_pdf_equipamentos(df_ativos_selecionados, coord_padrao="", nf_padrao=""):
    """Prepara o DataFrame padronizado para o gerador de PDF elástico (idêntico ao Ferramental)."""
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
# MÓDULO 2: SOLICITAÇÃO DE MOVIMENTAÇÃO (MÚLTIPLOS ATIVOS ESTILO PROCV)
# ==========================================
def render_modulo_solicitacao(df_ativos, df_empregados):
    st.subheader("📝 Solicitação de Movimentação de Equipamentos (Individual ou Múltiplos Itens)")
    st.caption("Selecione a modalidade e busque um ou vários equipamentos (estilo PROCV). Os dados de destino são preenchidos automaticamente.")
    
    opcoes_mov = [
        "MOV-01 | Almoxarifado -> Colaborador", 
        "MOV-02 | Colaborador -> Almoxarifado", 
        "MOV-03 | Unidade -> Unidade", 
        "MOV-04 | Almoxarifado -> Laboratório",
        "MOV-05 | Laboratório -> Almoxarifado"
    ]
    tipo_mov = st.selectbox("1️⃣ Selecione o Tipo de Movimentação:", opcoes_mov)
    cod_tipo = tipo_mov[:6]
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if not df_ativos.empty:
            opcoes_ativos = df_ativos.apply(
                lambda r: f"Pat: {r['patrimonio']} | {r.get('equipamento','')} {r.get('marca','')} {r.get('modelo','')} | Série: {r.get('numero_serie','')} | Status: {r.get('status_sistema','')} [PAT: {r['patrimonio']}]",
                axis=1
            ).tolist()
        else:
            opcoes_ativos = []

        ativos_selecionados_str = st.multiselect(
            "2️⃣ Busque e Selecione o(s) Equipamento(s) (Patrimônio, Série ou Descrição):",
            options=opcoes_ativos
        )
    
    matricula_busca = ""
    unidade_escolhida = ""
    emp_dict = {}
    
    with col_b2:
        if cod_tipo == "MOV-01":
            matricula_busca = st.text_input("3️⃣ Digite a Matrícula do Colaborador (Destino) e pressione Enter:")
            mat_limpa = limpar_texto_matricula(matricula_busca)
            if mat_limpa and not df_empregados.empty:
                match_emp = df_empregados[df_empregados['matricula'].astype(str) == mat_limpa]
                if not match_emp.empty:
                    emp_dict = match_emp.iloc[0].fillna("").to_dict()
                    st.success(f"👤 **Colaborador:** {emp_dict.get('nome', '')} | Proj: {emp_dict.get('projeto', '')} | Coord: {emp_dict.get('unidade', '')}")
                else:
                    st.warning("⚠️ Matrícula não localizada na base. Preencha abaixo.")
        elif cod_tipo == "MOV-03":
            unidades_existentes = []
            if not df_empregados.empty and 'unidade' in df_empregados.columns:
                unidades_existentes += df_empregados['unidade'].dropna().astype(str).tolist()
            if not df_ativos.empty and 'coordenacao' in df_ativos.columns:
                unidades_existentes += df_ativos['coordenacao'].dropna().astype(str).tolist()
            unidades_limpas = sorted(list({u.strip() for u in unidades_existentes if u.strip() and u.strip().lower() != 'none'}))
            opcoes_unid = ["Digitar Manualmente..."] + unidades_limpas
            sel_unid = st.selectbox("3️⃣ Selecione a Unidade / Coordenação de Destino:", opcoes_unid)
            if sel_unid == "Digitar Manualmente...":
                unidade_escolhida = st.text_input("Nome da Unidade de Destino:")
            else:
                unidade_escolhida = sel_unid
        else:
            st.info(f"⚡ **Auto-Preenchimento Ativo:** Destino configurado automaticamente para **{tipo_mov.split('->')[1].strip()}**.")

    if ativos_selecionados_str:
        pats_escolhidos = [s.split("[PAT: ")[1].replace("]", "") for s in ativos_selecionados_str]
        df_sel_ativos = df_ativos[df_ativos['patrimonio'].isin(pats_escolhidos)].copy()
        primeiro_reg = df_sel_ativos.iloc[0].to_dict()

        st.markdown(f"###### 📦 {len(df_sel_ativos)} Equipamento(s) Selecionado(s) para o Lote:")
        st.dataframe(
            df_sel_ativos[['patrimonio', 'equipamento', 'marca', 'modelo', 'numero_serie', 'status_sistema', 'cautela']],
            use_container_width=True, hide_index=True
        )

        cautela_atual = str(primeiro_reg.get('cautela', ''))
        origem_auto = cautela_atual if cautela_atual else "ALMOXARIFADO CENTRAL"
        
        if cod_tipo == "MOV-01":
            origem_auto = "ALMOXARIFADO CENTRAL"
            destino_auto = emp_dict.get('nome', '')
            projeto_auto = emp_dict.get('projeto', primeiro_reg.get('projeto', ''))
            coord_auto = emp_dict.get('unidade', primeiro_reg.get('coordenacao', ''))
            mat_auto = limpar_texto_matricula(matricula_busca)
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

        with st.form("form_solicitacao_multipla"):
            st.markdown("###### Confirme os detalhes da destinação do lote:")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.text_input("Modalidade Selecionada", value=tipo_mov, disabled=True)
                origem = st.text_input("Origem Padrão", value=origem_auto)
            with c2:
                destino = st.text_input("Destino / Novo Responsável *", value=destino_auto)
                projeto = st.text_input("Projeto (Destino)", value=projeto_auto)
            with c3:
                coordenacao = st.text_input("Coordenação / Unidade (Destino)", value=coord_auto)
                matricula_col = st.text_input("Matrícula (Apenas para Colaborador)", value=mat_auto)
                
            c4, c5 = st.columns(2)
            with c4:
                nf_edit = st.text_input("Nota Fiscal / NF Procisa (Opcional)", value=str(primeiro_reg.get('nf_procisa', '')))
            with c5:
                data_mov = st.date_input("Data da Movimentação (Efetiva)", datetime.today())
            
            if st.form_submit_button(f"🚀 Registrar Solicitação para {len(df_sel_ativos)} Equipamento(s)", type="primary"):
                if destino.strip():
                    stamp_lote = datetime.now().strftime('%Y%m%d-%H%M%S')
                    agora_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    mat_salvar = limpar_texto_matricula(matricula_col)
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
                            'destino': destino.strip(), 
                            'solicitante': st.session_state.get('nome_real', destino.strip()),
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
                        st.cache_data.clear()
                        registrar_log_auditoria(
                            "SOLICITAÇÃO EM LOTE", 
                            f"{len(novas_movs)} ativos", 
                            f"Lote MOV-{stamp_lote} ({cod_tipo}) registrado para Destino: {destino.strip()}."
                        )
                        st.success(f"✅ {len(novas_movs)} equipamento(s) enviado(s) para a fila da Central de Validações!")
                    except Exception as e:
                        st.error(f"Erro ao salvar solicitação em lote: {e}")
                else:
                    st.error("O campo de Destino / Novo Responsável deve estar preenchido.")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 3: CENTRAL DE VALIDAÇÕES (SUPORTE A LOTE E INDIVIDUAL)
# ==========================================
def render_modulo_validacoes(df_ativos, df_mov, df_termos, df_empregados):
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

        # Extrai o prefixo do lote (ex: MOV-20261117-120000) ou agrupa por Destino + Tipo
        def _extrair_chave_lote(row):
            idm = str(row.get('id_mov', ''))
            partes = idm.split('-')
            if len(partes) >= 3:
                return f"{partes[0]}-{partes[1]}-{partes[2]} | {row.get('tipo_mov')} -> {row.get('destino')} ({row.get('matricula_solicitante')})"
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
            st.info(f"**Itens neste processo ({len(pats_lote)}):** `{', '.join(pats_lote)}` | **Destino:** {mov_ref.get('destino', '')}")

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
                    nova_cautela = st.text_input("Atualizar Cautela (Destino Real)", value=str(mov_ref.get('destino', '')))

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

                                supabase.table('ativos_master').update({
                                    'status_sistema': novo_status,
                                    'cautela': nova_cautela.strip(),
                                    'projeto': str(m_row.get('projeto', '')).strip(),
                                    'coordenacao': str(m_row.get('coordenacao', '')).strip(),
                                    'nf_procisa': str(m_row.get('nf_procisa', '')).strip(),
                                    'atualizado_em': str(m_row.get('data_efetiva', datetime.now().strftime('%Y-%m-%d'))).strip()
                                }).eq('patrimonio', pat_i).execute()

                                supabase.table('movimentacoes').update({
                                    'status_mov': 'Concluído',
                                    'autorizador': st.session_state.nome_real
                                }).eq('id_mov', id_m_i).execute()

                                if tipo_m.startswith("MOV-01"):
                                    mat_solic = limpar_texto_matricula(m_row.get('matricula_solicitante', ''))
                                    match_emp = df_empregados[df_empregados['matricula'].astype(str) == mat_solic] if (not df_empregados.empty and mat_solic) else pd.DataFrame()
                                    emp = match_emp.iloc[0].fillna("").to_dict() if not match_emp.empty else {}
                                    resp_nome = emp.get('nome', nova_cautela.strip())
                                    resp_unid = emp.get('unidade', m_row.get('coordenacao', ''))

                                    termos_inserir.append({
                                        'id_termo': f"TRM-{stamp_trm}-{idx_v:02d}",
                                        'patrimonio': pat_i,
                                        'responsavel': resp_nome,
                                        'matricula': mat_solic,
                                        'unidade': resp_unid,
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
    with st.expander("🛠️ Movimentação Avulsa (Excepcional / Sem solicitação prévia)"):
        pat_avulso = st.text_input("Bipar/Digitar Patrimônio ou Série:")
        if pat_avulso:
            ativo_avulso = buscar_ativo(pat_avulso, df_ativos)
            if not ativo_avulso.empty:
                reg_avulso = ativo_avulso.iloc[0].to_dict()
                st.write(f"Ativo: {reg_avulso.get('marca')} {reg_avulso.get('modelo')} | Cautela Atual: {reg_avulso.get('cautela')}")
                
                with st.form("form_avulso"):
                    cA, cB = st.columns(2)
                    with cA:
                        status_av = st.selectbox("Status", ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"])
                    with cB:
                        cautela_av = st.text_input("Nova Cautela", value=reg_avulso.get('cautela', ''))
                    
                    if st.form_submit_button("✅ Forçar Atualização"):
                        dados_update_av = {
                            'status_sistema': status_av,
                            'cautela': cautela_av.strip(),
                            'atualizado_em': datetime.now().strftime('%Y-%m-%d')
                        }
                        try:
                            supabase.table('ativos_master').update(dados_update_av).eq('patrimonio', reg_avulso['patrimonio']).execute()
                            st.cache_data.clear()
                            registrar_log_auditoria("MOVIMENTAÇÃO AVULSA", reg_avulso['patrimonio'], f"Atualizado para {status_av} / {cautela_av}")
                            st.success("✅ Atualizado com sucesso.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro: {e}")
            else:
                st.warning("Não encontrado.")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 4: GESTÃO DE TERMOS E DIVERGÊNCIAS (COM PDF MULTI-ITENS E 2ª VIA DINÂMICA)
# ==========================================
def render_modulo_termos_divergencias(df_ativos, df_termos, df_diverg, df_empregados):
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
    
    # --- SUB-ABA 0: FILA DE IMPRESSÃO CONSOLIDADA POR LOTE / COLABORADOR ---
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
                    mat = limpar_texto_matricula(t_info['matricula'])
                    
                    ativos_match = df_ativos[df_ativos['patrimonio'].isin(pats_fila)] if not df_ativos.empty else pd.DataFrame()
                    emp_match = df_empregados[df_empregados['matricula'].astype(str) == mat] if (not df_empregados.empty and mat) else pd.DataFrame()
                    
                    if not ativos_match.empty:
                        emp = emp_match.iloc[0].fillna("").to_dict() if not emp_match.empty else {}
                        resp_nome = t_info['responsavel']
                        resp_cpf = emp.get('cpf', '')
                        resp_rg = emp.get('rg', '')
                        resp_proj = emp.get('projeto', ativos_match.iloc[0].get('projeto', ''))
                        resp_unid = t_info['unidade']
                        
                        df_pdf_pronto = _montar_df_pdf_equipamentos(ativos_match, resp_unid, str(t_info['id_termo']))
                        caminho_pdf = gerar_termo_pdf(pats_fila[0], resp_nome, mat, resp_cpf, resp_rg, resp_proj, resp_unid, df_pdf_pronto)
                        with open(caminho_pdf, "rb") as pdf_file: 
                            PDFbyte = pdf_file.read()
                        
                        try:
                            for id_t_up in df_sub_fila['id_termo'].tolist():
                                supabase.table('termos').update({'status_termo': 'Ativo'}).eq('id_termo', id_t_up).execute()
                            st.cache_data.clear()
                            registrar_log_auditoria("IMPRESSÃO TERMO FILA", f"{len(pats_fila)} ativos", f"Termo impresso e ativado para {resp_nome}.")
                            
                            st.session_state.pdf_termo_pronto = {
                                'bytes': PDFbyte,
                                'nome_arquivo': f"Termo_PROCISA_{resp_nome.replace(' ', '_')}_{pats_fila[0]}.pdf",
                                'msg': f"✅ Termo com {len(pats_fila)} equipamento(s) gerado e ativado no sistema! Clique abaixo para baixar."
                            }
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar status: {e}")
                    else:
                        st.error("Erro: Equipamento(s) vinculado(s) não encontrado(s) na base.")
        else:
            st.success("🎉 Nenhum termo pendente na fila de impressão.")

    # --- SUB-ABA 1: REIMPRESSÃO DINÂMICA DE TERMOS EMITIDOS (SEM ARMAZENAR ARQUIVO) ---
    with aba_reimp:
        st.markdown("###### 🔄 Central de Reimpressão de Termos Emitidos (2ª Via Sob Demanda)")
        st.caption("Reconstrói o PDF oficial na hora (individual ou consolidado por lote/colaborador) sem ocupar espaço no banco.")
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
                mat = limpar_texto_matricula(t_info['matricula'])
                
                ativos_match = df_ativos[df_ativos['patrimonio'].isin(pats_2via)] if not df_ativos.empty else pd.DataFrame()
                emp_match = df_empregados[df_empregados['matricula'].astype(str) == mat] if (not df_empregados.empty and mat) else pd.DataFrame()
                
                if not ativos_match.empty:
                    emp = emp_match.iloc[0].fillna("").to_dict() if not emp_match.empty else {}
                    df_pdf_2via = _montar_df_pdf_equipamentos(ativos_match, t_info['unidade'], str(t_info['id_termo']))
                    caminho_pdf = gerar_termo_pdf(
                        pats_2via[0], t_info['responsavel'], mat, 
                        emp.get('cpf', ''), emp.get('rg', ''), 
                        emp.get('projeto', ativos_match.iloc[0].get('projeto', '')), 
                        t_info['unidade'], df_pdf_2via
                    )
                    with open(caminho_pdf, "rb") as pdf_file:
                        PDFbyte = pdf_file.read()
                    st.session_state.pdf_termo_pronto = {
                        'bytes': PDFbyte,
                        'nome_arquivo': f"2Via_Termo_PROCISA_{t_info['responsavel'].replace(' ', '_')}.pdf",
                        'msg': f"✅ 2ª Via do Termo ({len(pats_2via)} equipamento(s)) gerada dinamicamente!"
                    }
                    st.rerun()
                else:
                    st.error("Ativo(s) vinculado(s) não encontrado(s) na base mestra.")
        else:
            st.info("Nenhum termo registado no histórico.")

    # --- SUB-ABA 2: EMISSÃO EXCEPCIONAL MULTI-ITENS E BAIXA DE TERMO ---
    with aba_avulso:
        acao_trm = st.radio("Selecione a Operação:", ["📤 Emitir Novo Termo Excepcional (Multi-Equipamentos)", "📥 Encerrar / Baixar Termo Ativo (Devolução)"], horizontal=True)
        if acao_trm.startswith("📤"):
            c_t1, c_t2 = st.columns(2)
            with c_t1:
                op_at_trm = df_ativos.apply(
                    lambda r: f"Pat: {r['patrimonio']} | {r.get('equipamento','')} {r.get('marca','')} {r.get('modelo','')} [PAT: {r['patrimonio']}]",
                    axis=1
                ).tolist() if not df_ativos.empty else []
                sel_ats_trm = st.multiselect("1️⃣ Selecione o(s) Equipamento(s) para o Termo:", op_at_trm)
            with c_t2:
                matricula_busca = st.text_input("2️⃣ Digite a Matrícula do Colaborador e pressione Enter:")
                mat_limpa = limpar_texto_matricula(matricula_busca)
                emp_dict = {'nome': '', 'cpf': '', 'rg': '', 'projeto': '', 'unidade': ''}
                if mat_limpa and not df_empregados.empty:
                    match_emp = df_empregados[df_empregados['matricula'].astype(str) == mat_limpa]
                    if not match_emp.empty:
                        emp_dict = match_emp.iloc[0].fillna("").to_dict()
                        st.success(f"👤 Colaborador: {emp_dict.get('nome', '')}")

            with st.form("form_termo_avulso_multi"):
                colA, colB = st.columns(2)
                with colA:
                    responsavel_termo = st.text_input("Nome do Responsável *", value=emp_dict.get('nome', ''))
                    cpf_termo = st.text_input("CPF", value=emp_dict.get('cpf', ''))
                    rg_termo = st.text_input("RG", value=emp_dict.get('rg', ''))
                with colB:
                    matricula_termo = st.text_input("Matrícula", value=mat_limpa)
                    unidade_termo = st.text_input("Unidade / Área / Coordenação", value=emp_dict.get('unidade', ''))
                    projeto_termo = st.text_input("Projeto", value=emp_dict.get('projeto', ''))
                submit_termo = st.form_submit_button("🖨️ Gerar PDF Único do Termo", type="primary")
                
            if submit_termo and sel_ats_trm and responsavel_termo.strip():
                pats_t = [s.split("[PAT: ")[1].replace("]", "") for s in sel_ats_trm]
                ativos_info_t = df_ativos[df_ativos['patrimonio'].isin(pats_t)]
                mat_salvar = limpar_texto_matricula(matricula_termo)
                stamp_av = datetime.now().strftime('%Y%m%d%H%M%S')

                df_pdf_av = _montar_df_pdf_equipamentos(ativos_info_t, unidade_termo.strip(), f"TRM-{stamp_av}")
                caminho_pdf = gerar_termo_pdf(
                    pats_t[0], responsavel_termo.strip(), mat_salvar, 
                    cpf_termo.strip(), rg_termo.strip(), projeto_termo.strip(), unidade_termo.strip(), 
                    df_pdf_av
                )
                with open(caminho_pdf, "rb") as pdf_file: 
                    PDFbyte = pdf_file.read()
                
                novos_termos_av = []
                for idx_a, p_a in enumerate(pats_t, start=1):
                    novos_termos_av.append({
                        'id_termo': f"TRM-{stamp_av}-{idx_a:02d}", 
                        'patrimonio': p_a, 
                        'responsavel': responsavel_termo.strip(), 
                        'matricula': mat_salvar, 
                        'unidade': unidade_termo.strip(), 
                        'data_emissao': datetime.now().strftime('%Y-%m-%d'), 
                        'data_baixa': '', 
                        'status_termo': 'Ativo'
                    })
                supabase.table('termos').insert(novos_termos_av).execute()
                st.cache_data.clear()
                registrar_log_auditoria("EMISSÃO DE TERMO (AVULSO)", f"{len(pats_t)} ativos", f"Termo emitido para {responsavel_termo.strip()}.")
                st.session_state.pdf_termo_pronto = {
                    'bytes': PDFbyte,
                    'nome_arquivo': f"Termo_PROCISA_{responsavel_termo.strip().replace(' ', '_')}.pdf",
                    'msg': f"✅ Termo com {len(pats_t)} equipamento(s) registrado e ativado na nuvem!"
                }
                st.rerun()
        else:
            pat_baixa = st.text_input("Patrimônio ou Série devolvido:")
            if st.button("Baixar Termo Ativo", type="primary"):
                ativo_info_baixa = buscar_ativo(pat_baixa, df_ativos)
                if not ativo_info_baixa.empty:
                    pat_real = ativo_info_baixa.iloc[0]['patrimonio']
                    termos_ativos = df_termos[(df_termos['patrimonio'].astype(str) == str(pat_real)) & (df_termos['status_termo'].isin(['Ativo', 'Pendente Impressão']))] if not df_termos.empty else pd.DataFrame()
                    if not termos_ativos.empty:
                        for _, t_r in termos_ativos.iterrows():
                            supabase.table('termos').update({
                                'data_baixa': datetime.now().strftime('%Y-%m-%d'),
                                'status_termo': 'Encerrado'
                            }).eq('id_termo', t_r['id_termo']).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria("BAIXA DE TERMO", pat_real, "Termo encerrado por devolução.")
                        st.success("✅ Termo encerrado com sucesso!")
                        st.rerun()
                    else:
                        st.warning("Nenhum termo ativo encontrado para este equipamento.")
                else:
                    st.error("Patrimônio ou série não localizado.")

    # --- SUB-ABA 3: DIVERGÊNCIAS ---
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
# MÓDULO 5: DIAGNÓSTICO (LABORATÓRIO)
# ==========================================
def render_modulo_laboratorio(df_ativos):
    st.subheader("🔬 Laboratório Técnico")
    patrimonio_lab = st.text_input("Patrimônio ou Série em Análise:")
    
    if patrimonio_lab.strip():
        ativo_match = buscar_ativo(patrimonio_lab, df_ativos)
        if not ativo_match.empty:
            reg_lab = ativo_match.iloc[0]
            st.info(f"**Equipamento:** {reg_lab.get('equipamento')} - {reg_lab.get('marca')} {reg_lab.get('modelo')} | **Condição Atual:** {reg_lab.get('condicoes_para_uso')}")
        else:
            st.warning("⚠️ Patrimônio ou série não localizado.")
            
    resultado = st.radio("Parecer Técnico:", ["APTO", "APTO COM RESSALVA", "REPARADO", "CALIBRADO", "REPROVADO", "INSERVÍVEL"], horizontal=True)
    acessorios_lab = st.text_input("Atualizar Observação / Acessórios (Opcional):")
    
    if st.button("Atualizar Base com Parecer Técnico", type="primary"):
        ativo_match = buscar_ativo(patrimonio_lab, df_ativos)
        
        if not ativo_match.empty:
            pat_real = ativo_match.iloc[0]['patrimonio']
            cond_antiga = ativo_match.iloc[0].get('condicoes_para_uso', '')
            novo_status = 'Baixado' if ("INSERVÍVEL" in resultado or "REPROVADO" in resultado) else 'Disponível'
            
            dados_update_lab = {
                'condicoes_para_uso': resultado,
                'status_sistema': novo_status,
                'atualizado_em': datetime.now().strftime('%Y-%m-%d')
            }
            if acessorios_lab.strip():
                dados_update_lab['acessorios'] = acessorios_lab.strip()
            
            try:
                supabase.table('ativos_master').update(dados_update_lab).eq('patrimonio', pat_real).execute()
                st.cache_data.clear()
                registrar_log_auditoria("LAUDO LABORATÓRIO", pat_real, f"Parecer: '{cond_antiga}' -> '{resultado}'. Novo Status: '{novo_status}'.")
                st.success(f"✅ Laudo registrado! Ativo atualizado para: {novo_status}")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar laudo: {e}")
        else:
            st.warning("⚠️ Patrimônio ou série não localizado.")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 8 (EQUIPAMENTOS): MODO OPERADOR QR CODE AUTOMÁTICO + FOLHA A4
# ==========================================
def render_operador_qrcode_eqp(df_ativos, df_empregados):
    gerar_etiquetas_qrcode_pdf = getattr(pdf_termo, 'gerar_etiquetas_qrcode_pdf', None)
    render_leitor_fn = getattr(nuvem, 'render_leitor_qrcode_mobile', None)

    st.subheader("📷 Modo Operador — Leitura Automática de QR Code (Equipamentos)")
    st.caption("Ative o '📱 Scanner Ao Vivo (Auto)' no smartphone para leitura automática contínua ou utilize o coletor.")

    if st.session_state.get('pdf_etiquetas_eqp_pronto'):
        st.success(st.session_state.pdf_etiquetas_eqp_pronto['msg'])
        st.download_button(
            "📥 Baixar Folha de Etiquetas QR Code em PDF (A4 - Equipamentos)",
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
        "🏷️ Gerador de Folha de Etiquetas QR Code em Lote (PDF A4)"
    ])

    with aba_sc_eqp:
        if render_leitor_fn:
            cod_eqp_qr = render_leitor_fn("eqp_qr", "Ex: US-AC1N1P9 ou Patrimônio...")
        else:
            cod_eqp_qr = st.text_input("🔫 Bipe ou Digite o Código:", placeholder="Ex: US-AC1N1P9 ou Patrimônio...").strip().upper()

        if cod_eqp_qr and not df_ativos.empty:
            resultados = buscar_ativo(cod_eqp_qr, df_ativos)
            if not resultados.empty:
                st.success(f"✅ **{len(resultados)} equipamento(s)** localizado(s) para o código `{cod_eqp_qr}`!")
                cols_v = [c for c in ['patrimonio', 'equipamento', 'marca', 'modelo', 'numero_serie', 'status_sistema', 'cautela', 'enderecamento_01', 'enderecamento_02'] if c in resultados.columns]
                st.dataframe(resultados[cols_v], use_container_width=True, hide_index=True)

                op_eq = resultados.apply(lambda r: f"{r['patrimonio']} | {r.get('equipamento','')} {r.get('marca','')} {r.get('modelo','')} | End: {r.get('enderecamento_01','')} / {r.get('enderecamento_02','')}", axis=1).tolist()
                sel_eq = st.selectbox("Selecione o Equipamento para Ação Rápida:", op_eq)
                pat_sel = sel_eq.split(" | ")[0]
                reg_eq = resultados[resultados['patrimonio'] == pat_sel].iloc[0].to_dict()

                with st.form("form_qr_eqp_mov"):
                    ce1, ce2, ce3 = st.columns(3)
                    with ce1:
                        n_end1 = st.text_input("Bipar Novo Endereçamento 01:", value=reg_eq.get('enderecamento_01', ''))
                        n_end2 = st.text_input("Bipar Novo Endereçamento 02:", value=reg_eq.get('enderecamento_02', ''))
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
                st.warning(f"⚠️ Nenhum equipamento ou endereço localizado para `{cod_eqp_qr}`.")

    with aba_etq_eqp:
        st.markdown("###### 🖨️ Impressão em Lote de Etiquetas QR Code (Equipamentos e Endereços)")
        if not df_ativos.empty and gerar_etiquetas_qrcode_pdf:
            op_at = df_ativos.apply(lambda r: f"{r['patrimonio']} | {r.get('equipamento','')} {r.get('marca','')} {r.get('modelo','')}", axis=1).tolist()
            sel_at = st.multiselect("Selecione os Equipamentos para gerar etiquetas (21 por folha A4):", options=op_at, default=op_at[:21])
            etq_eqp_list = []
            for item_a in sel_at:
                pat_a = item_a.split(" | ")[0]
                r_a = df_ativos[df_ativos['patrimonio'] == pat_a].iloc[0]
                etq_eqp_list.append({
                    'codigo': pat_a,
                    'tipo': f"SÉRIE: {r_a.get('numero_serie', '')}",
                    'subtitulo': f"{r_a.get('equipamento', '')} {r_a.get('marca', '')} {r_a.get('modelo', '')}".strip()
                })
            if etq_eqp_list and st.button(f"🖨️ Gerar PDF com {len(etq_eqp_list)} Etiqueta(s)", type="primary"):
                with st.spinner("Gerando folha A4 de etiquetas QR Code..."):
                    cam_eq = gerar_etiquetas_qrcode_pdf(etq_eqp_list)
                    with open(cam_eq, "rb") as f_e:
                        st.session_state.pdf_etiquetas_eqp_pronto = {
                            'bytes': f_e.read(),
                            'nome': f"Etiquetas_QR_Equipamentos_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            'msg': f"✅ Folha com {len(etq_eqp_list)} etiquetas gerada!"
                        }
                    st.rerun()
        else:
            st.info("Base de equipamentos vazia.")

    exibir_marca_desenvolvedor()
