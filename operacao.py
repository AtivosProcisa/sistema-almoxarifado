import streamlit as st
import pandas as pd
from datetime import datetime
from nuvem import (
    supabase, buscar_ativo, registrar_log_auditoria, limpar_texto_matricula
)
from pdf_termo import gerar_termo_pdf

# ==========================================
# MÓDULO 2: SOLICITAÇÃO DE MOVIMENTAÇÃO
# ==========================================
def render_modulo_solicitacao(df_ativos, df_empregados):
    st.header("📝 Solicitação de Movimentação")
    st.write("Selecione a modalidade e identifique o ativo. Os dados de destino são preenchidos automaticamente conforme o tipo escolhido.")
    
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
        patrimonio_busca = st.text_input("2️⃣ Digite o Patrimônio ou Nº de Série (Ativo):")
    
    matricula_busca = ""
    unidade_escolhida = ""
    
    with col_b2:
        if cod_tipo == "MOV-01":
            matricula_busca = st.text_input("3️⃣ Digite a Matrícula do Colaborador (Destino):")
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
            st.info(f"⚡ **Auto-Preenchimento Ativo:** Os dados de destino para **{tipo_mov.split('->')[1].strip()}** serão preenchidos automaticamente.")

    ativo_info = pd.DataFrame()
    emp_dict = {}
    
    if patrimonio_busca:
        ativo_info = buscar_ativo(patrimonio_busca, df_ativos)
        if not ativo_info.empty:
            registro_atual = ativo_info.iloc[0].to_dict()
            pat_real = registro_atual.get('patrimonio', '')
            eqp = registro_atual.get('equipamento', '')
            marca = registro_atual.get('marca', '')
            modelo = registro_atual.get('modelo', '')
            serie = registro_atual.get('numero_serie', '')
            status_atual = registro_atual.get('status_sistema', 'Disponível')
            cautela_atual = registro_atual.get('cautela', '')
            nf_atual = registro_atual.get('nf_procisa', '')
            
            st.success(f"✅ **Ativo Localizado:** {eqp} - {marca} {modelo} (Série: {serie})")
            st.info(f"📍 **Status:** {status_atual} | **Cautela/Local Atual:** {cautela_atual}")
        else:
            st.warning("⚠️ Ativo não localizado na base mestra.")
            
    if matricula_busca and cod_tipo == "MOV-01":
        mat_limpa = limpar_texto_matricula(matricula_busca)
        if not df_empregados.empty and mat_limpa:
            match_emp = df_empregados[df_empregados['matricula'].astype(str) == mat_limpa]
            if not match_emp.empty:
                emp_dict = match_emp.iloc[0].fillna("").to_dict()
                st.success(f"👤 **Colaborador Localizado:** {emp_dict.get('nome', '')} | Projeto: {emp_dict.get('projeto', '')} | Coordenação: {emp_dict.get('unidade', '')}")
            else:
                st.warning("⚠️ Matrícula não encontrada na base. Preencha manualmente abaixo.")
    
    if not ativo_info.empty:
        origem_auto = str(cautela_atual) if cautela_atual else "ALMOXARIFADO CENTRAL"
        
        if cod_tipo == "MOV-01":
            origem_auto = "ALMOXARIFADO CENTRAL"
            destino_auto = emp_dict.get('nome', '')
            projeto_auto = emp_dict.get('projeto', registro_atual.get('projeto', ''))
            coord_auto = emp_dict.get('unidade', registro_atual.get('coordenacao', ''))
            mat_auto = limpar_texto_matricula(matricula_busca)
        elif cod_tipo in ["MOV-02", "MOV-05"]:
            if cod_tipo == "MOV-05":
                origem_auto = "LABORATÓRIO TÉCNICO - PROCISA"
            destino_auto = "ALMOXARIFADO CENTRAL"
            projeto_auto = "ESTOQUE ALMOXARIFADO"
            coord_auto = "LOGÍSTICA / ALMOXARIFADO"
            mat_auto = ""
        elif cod_tipo == "MOV-04":
            origem_auto = str(cautela_atual) if cautela_atual else "ALMOXARIFADO CENTRAL"
            destino_auto = "LABORATÓRIO TÉCNICO - PROCISA"
            projeto_auto = "MANUTENÇÃO / LAB"
            coord_auto = "LABORATÓRIO"
            mat_auto = ""
        elif cod_tipo == "MOV-03":
            destino_auto = unidade_escolhida
            proj_unid = registro_atual.get('projeto', '')
            if unidade_escolhida and not df_empregados.empty:
                m_u = df_empregados[df_empregados['unidade'].astype(str).str.upper() == unidade_escolhida.upper()]
                if not m_u.empty:
                    proj_unid = m_u.iloc[0].get('projeto', proj_unid)
            projeto_auto = proj_unid
            coord_auto = unidade_escolhida
            mat_auto = ""

        with st.form("form_solicitacao"):
            st.markdown("###### Confirme os detalhes da destinação (Preenchidos Automaticamente):")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.text_input("Modalidade Selecionada", value=tipo_mov, disabled=True)
                origem = st.text_input("Origem (Local Atual)", value=origem_auto)
            with c2:
                destino = st.text_input("Destino / Novo Responsável", value=destino_auto)
                projeto = st.text_input("Projeto (Destino)", value=projeto_auto)
            with c3:
                coordenacao = st.text_input("Coordenação / Unidade (Destino)", value=coord_auto)
                matricula_col = st.text_input("Matrícula (Apenas para Colaborador)", value=mat_auto)
                
            c4, c5 = st.columns(2)
            with c4:
                nf_edit = st.text_input("Nota Fiscal / NF Procisa", value=nf_atual)
            with c5:
                data_mov = st.date_input("Data da Movimentação (Efetiva)", datetime.today())
            
            if st.form_submit_button("🚀 Registrar Solicitação", type="primary"):
                if destino.strip():
                    id_mov = f"MOV-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                    mat_salvar = limpar_texto_matricula(matricula_col)
                    nova_mov = {
                        'id_mov': id_mov, 
                        'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                        'tipo_mov': cod_tipo, 
                        'patrimonio': pat_real, 
                        'origem': origem.strip(), 
                        'destino': destino.strip(), 
                        'solicitante': st.session_state.get('nome_real', destino.strip()),
                        'matricula_solicitante': mat_salvar,
                        'autorizador': 'Pendente', 
                        'status_mov': 'Aguardando Conferência',
                        'nf_procisa': nf_edit.strip(),
                        'projeto': projeto.strip(),
                        'coordenacao': coordenacao.strip(),
                        'data_efetiva': data_mov.strftime('%Y-%m-%d')
                    }
                    
                    try:
                        supabase.table('movimentacoes').insert(nova_mov).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria(
                            "SOLICITAÇÃO MOV.", 
                            pat_real, 
                            f"ID {id_mov} ({cod_tipo}) registrada. Origem: {origem} -> Destino: {destino}."
                        )
                        st.success("✅ Solicitação integrada à base e enviada para a fila da Central de Validações!")
                    except Exception as e:
                        st.error(f"Erro ao salvar solicitação: {e}")
                else:
                    st.error("O campo de Destino / Novo Responsável deve estar preenchido.")

# ==========================================
# MÓDULO 3: CENTRAL DE VALIDAÇÕES
# ==========================================
def render_modulo_validacoes(df_ativos, df_mov, df_termos, df_empregados):
    st.header("✅ Central de Validações (Almoxarifado)")
    
    if st.session_state.get('msg_sucesso'):
        st.success(st.session_state.msg_sucesso)
        if st.button("✖️ Fechar Aviso"):
            st.session_state.msg_sucesso = None
            st.rerun()
        st.divider()
    
    movs_pendentes = df_mov[df_mov['status_mov'] == 'Aguardando Conferência'] if not df_mov.empty else pd.DataFrame()
    
    if movs_pendentes.empty:
        st.success("🎉 Excelente! Nenhuma solicitação pendente no momento.")
    else:
        st.write("Abaixo estão as solicitações pendentes. Se necessitar cancelar algum pedido errado, marque a caixinha **'🗑️ Cancelar?'**. Caso contrário, selecione o ID abaixo da tabela para **Validá-lo**.")
        
        df_mov_view = movs_pendentes[['id_mov', 'tipo_mov', 'patrimonio', 'origem', 'destino', 'solicitante']].copy()
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
            if st.button(f"🗑️ Confirmar Cancelamento", type="primary"):
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
        st.markdown("###### 🔄 Proceder com a Validação")
        id_selecionado = st.selectbox("Selecione o ID da Movimentação para Validar:", movs_pendentes['id_mov'].tolist())
        
        if id_selecionado:
            mov_atual = movs_pendentes[movs_pendentes['id_mov'] == id_selecionado].iloc[0].to_dict()
            pat_real = mov_atual.get('patrimonio', '')
            tipo_m = str(mov_atual.get('tipo_mov', ''))
            ativo_info = buscar_ativo(pat_real, df_ativos)
            
            if not ativo_info.empty:
                registro_atual = ativo_info.iloc[0].to_dict()
                status_antigo = registro_atual.get('status_sistema', 'Disponível')
                
                st.info(f"**Ativo Vinculado:** {registro_atual.get('marca', '')} {registro_atual.get('modelo', '')} (Série: {registro_atual.get('numero_serie', '')}) | **Status Atual:** {status_antigo}")
                
                opcoes_st = ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"]
                if tipo_m in ["MOV-02", "MOV-05"] or 'ALMOX' in str(mov_atual.get('destino', '')).upper():
                    idx_sugerido = 0
                elif tipo_m == "MOV-04" or 'LAB' in str(mov_atual.get('destino', '')).upper():
                    idx_sugerido = 2
                else:
                    idx_sugerido = 1
                
                with st.form("form_validacao_pendente"):
                    colA, colB = st.columns(2)
                    with colA: 
                        novo_status = st.selectbox("Novo Status no Sistema:", opcoes_st, index=idx_sugerido)
                    with colB: 
                        nova_cautela = st.text_input("Atualizar Cautela (Destino Real)", value=str(mov_atual.get('destino', '')))
                    
                    st.write("Verificações de Segurança:")
                    d365_ok = st.checkbox("Status e Localização conferem no sistema central?")
                    eponto_ok = st.checkbox("Movimentação validada no e-Ponto?")
                    fisico_ok = st.checkbox("Estado físico, Série e Acessórios conferem?")
                    
                    btn_validar = st.form_submit_button("✅ Validar e Concluir Transferência", type="primary")
                    
                    if btn_validar:
                        if d365_ok and eponto_ok and fisico_ok:
                            try:
                                dados_update_ativo = {
                                    'status_sistema': novo_status,
                                    'cautela': nova_cautela.strip(),
                                    'projeto': str(mov_atual.get('projeto', '')).strip(),
                                    'coordenacao': str(mov_atual.get('coordenacao', '')).strip(),
                                    'nf_procisa': str(mov_atual.get('nf_procisa', '')).strip(),
                                    'atualizado_em': str(mov_atual.get('data_efetiva', datetime.now().strftime('%Y-%m-%d'))).strip()
                                }
                                supabase.table('ativos_master').update(dados_update_ativo).eq('patrimonio', pat_real).execute()
                                
                                dados_update_mov = {'status_mov': 'Concluído', 'autorizador': st.session_state.nome_real}
                                supabase.table('movimentacoes').update(dados_update_mov).eq('id_mov', id_selecionado).execute()
                                
                                if tipo_m.startswith("MOV-01"):
                                    mat_solic = limpar_texto_matricula(mov_atual.get('matricula_solicitante', ''))
                                    match_emp = df_empregados[df_empregados['matricula'].astype(str) == mat_solic] if (not df_empregados.empty and mat_solic) else pd.DataFrame()
                                    emp = match_emp.iloc[0].fillna("").to_dict() if not match_emp.empty else {}
                                    
                                    resp_nome = emp.get('nome', mov_atual.get('destino', ''))
                                    resp_unid = emp.get('unidade', mov_atual.get('coordenacao', ''))
                                    
                                    id_termo = f"TRM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                                    novo_termo = {
                                        'id_termo': id_termo, 
                                        'patrimonio': pat_real, 
                                        'responsavel': resp_nome, 
                                        'matricula': mat_solic, 
                                        'unidade': resp_unid, 
                                        'data_emissao': datetime.now().strftime('%Y-%m-%d'), 
                                        'data_baixa': '', 
                                        'status_termo': 'Pendente Impressão'
                                    }
                                    supabase.table('termos').insert(novo_termo).execute()
                                    registrar_log_auditoria("TERMO NA FILA", pat_real, f"Termo {id_termo} gerado e enviado para Fila de Impressão.")
                                    st.session_state.msg_sucesso = "✅ Validação concluída! O Termo de Responsabilidade foi enviado para a Fila de Impressão (Módulo 4)."
                                
                                elif tipo_m.startswith("MOV-02"):
                                    termos_abertos = df_termos[(df_termos['patrimonio'].astype(str) == str(pat_real)) & (df_termos['status_termo'].isin(['Ativo', 'Pendente Impressão']))] if not df_termos.empty else pd.DataFrame()
                                    if not termos_abertos.empty:
                                        for _, t_row in termos_abertos.iterrows():
                                            supabase.table('termos').update({
                                                'data_baixa': datetime.now().strftime('%Y-%m-%d'),
                                                'status_termo': 'Encerrado'
                                            }).eq('id_termo', t_row['id_termo']).execute()
                                        registrar_log_auditoria("BAIXA AUTOMÁTICA TERMO", pat_real, "Termo encerrado automaticamente na validação de devolução (MOV-02).")
                                    st.session_state.msg_sucesso = "✅ Devolução validada! Ativo disponível no Almoxarifado e Termo anterior baixado automaticamente."
                                else:
                                    st.session_state.msg_sucesso = "✅ Ciclo de movimentação fechado! Dashboard atualizado em tempo real."
                                
                                st.cache_data.clear()
                                registrar_log_auditoria("VALIDAÇÃO CONCLUÍDA", pat_real, f"Mov. {id_selecionado} concluída. Cautela atual: {nova_cautela}.")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Erro ao concluir movimentação: {e}")
                        else:
                            st.error("Complete as 3 caixas de verificação antes de validar.")
            else:
                st.warning("⚠️ Patrimônio vinculado não foi localizado na base mestra.")

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

# ==========================================
# MÓDULO 4: GESTÃO DE TERMOS E DIVERGÊNCIAS
# ==========================================
def render_modulo_termos_divergencias(df_ativos, df_termos, df_diverg, df_empregados):
    st.header("📄 Gestão de Termos e Divergências")
    
    if st.session_state.get('pdf_termo_pronto'):
        st.success(st.session_state.pdf_termo_pronto.get('msg', "✅ Termo gerado com sucesso!"))
        st.download_button(
            label="📥 Baixar Termo PDF (Modelo Oficial PROCISA)", 
            data=st.session_state.pdf_termo_pronto['bytes'], 
            file_name=st.session_state.pdf_termo_pronto['nome_arquivo'], 
            mime='application/pdf',
            type="primary"
        )
        if st.button("✖️ Fechar Aviso"):
            st.session_state.pdf_termo_pronto = None
            st.rerun()
        st.divider()

    aba_termos, aba_diverg = st.tabs(["Emissão, Fila e 2ª Via de Termos", "Tratar Divergências"])
    
    with aba_termos:
        st.markdown("###### 🖨️ Fila de Impressão (Termos Pendentes)")
        st.caption("Termos gerados automaticamente pelas Movimentações (MOV-01) que aguardam impressão e assinatura.")
        termos_pendentes = df_termos[df_termos['status_termo'] == 'Pendente Impressão'] if not df_termos.empty else pd.DataFrame()
        
        if not termos_pendentes.empty:
            st.dataframe(termos_pendentes[['id_termo', 'patrimonio', 'responsavel', 'matricula', 'unidade', 'data_emissao']], use_container_width=True)
            
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                id_imp = st.selectbox("Selecione o Termo da Fila para Imprimir:", termos_pendentes['id_termo'].tolist())
            with col_f2:
                st.write("")
                st.write("")
                if st.button("🖨️ Gerar PDF e Ativar", type="primary", use_container_width=True):
                    t_info = termos_pendentes[termos_pendentes['id_termo'] == id_imp].iloc[0]
                    pat_real = t_info['patrimonio']
                    mat = limpar_texto_matricula(t_info['matricula'])
                    
                    ativo_match = buscar_ativo(pat_real, df_ativos)
                    emp_match = df_empregados[df_empregados['matricula'].astype(str) == mat] if (not df_empregados.empty and mat) else pd.DataFrame()
                    
                    if not ativo_match.empty:
                        emp = emp_match.iloc[0].fillna("").to_dict() if not emp_match.empty else {}
                        resp_nome = t_info['responsavel']
                        resp_cpf = emp.get('cpf', '')
                        resp_rg = emp.get('rg', '')
                        resp_proj = emp.get('projeto', ativo_match.iloc[0].get('projeto', ''))
                        resp_unid = t_info['unidade']
                        
                        caminho_pdf = gerar_termo_pdf(pat_real, resp_nome, mat, resp_cpf, resp_rg, resp_proj, resp_unid, ativo_match)
                        with open(caminho_pdf, "rb") as pdf_file: 
                            PDFbyte = pdf_file.read()
                        
                        try:
                            supabase.table('termos').update({'status_termo': 'Ativo'}).eq('id_termo', id_imp).execute()
                            st.cache_data.clear()
                            registrar_log_auditoria("IMPRESSÃO TERMO FILA", pat_real, f"Termo {id_imp} impresso e ativado.")
                            
                            st.session_state.pdf_termo_pronto = {
                                'bytes': PDFbyte,
                                'nome_arquivo': f"Termo_PROCISA_{pat_real}.pdf",
                                'msg': f"✅ Termo {id_imp} gerado e ativado no sistema! Clique abaixo para baixar."
                            }
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar status: {e}")
                    else:
                        st.error("Erro: Ativo vinculado a este termo não encontrado na base.")
        else:
            st.success("🎉 Nenhum termo pendente na fila de impressão.")
            
        st.divider()

        opcao_termo = st.radio(
            "Outras Operações de Termos:", 
            ["Encerrar Termo (Devolução)", "🔄 Emitir 2ª Via de Termo", "Emitir Novo Termo Excepcional"], 
            horizontal=True
        )
        
        if opcao_termo == "Emitir Novo Termo Excepcional":
            matricula_busca = st.text_input("Digite a Matrícula e pressione Enter para buscar os dados do colaborador:")
            mat_limpa = limpar_texto_matricula(matricula_busca)
            
            emp_dict = {'nome': '', 'cpf': '', 'rg': '', 'projeto': '', 'unidade': ''}
            if mat_limpa and not df_empregados.empty:
                match_emp = df_empregados[df_empregados['matricula'].astype(str) == mat_limpa]
                if not match_emp.empty:
                    emp_dict = match_emp.iloc[0].fillna("").to_dict()
                    st.success(f"✅ Colaborador localizado: {emp_dict.get('nome', '')}")
                else:
                    st.warning("⚠️ Matrícula não encontrada na base. Preencha os campos abaixo manualmente.")
            
            with st.form("form_termo_avulso"):
                colA, colB = st.columns(2)
                with colA:
                    patrimonio_termo = st.text_input("Patrimônio ou Série do Equipamento:")
                    responsavel_termo = st.text_input("Nome do Responsável:", value=emp_dict.get('nome', ''))
                    cpf_termo = st.text_input("CPF:", value=emp_dict.get('cpf', ''))
                    rg_termo = st.text_input("RG:", value=emp_dict.get('rg', ''))
                with colB:
                    matricula_termo = st.text_input("Matrícula (Confirmação):", value=mat_limpa)
                    unidade_termo = st.text_input("Unidade / Área / Coordenação:", value=emp_dict.get('unidade', ''))
                    projeto_termo = st.text_input("Projeto:", value=emp_dict.get('projeto', ''))
                submit_termo = st.form_submit_button("Gerar PDF do Termo", type="primary")
                
            if submit_termo and patrimonio_termo.strip():
                ativo_info_termo = buscar_ativo(patrimonio_termo, df_ativos)
                
                if not ativo_info_termo.empty:
                    pat_real = ativo_info_termo.iloc[0]['patrimonio']
                    mat_salvar = limpar_texto_matricula(matricula_termo)
                    caminho_pdf = gerar_termo_pdf(
                        pat_real, responsavel_termo.strip(), mat_salvar, 
                        cpf_termo.strip(), rg_termo.strip(), projeto_termo.strip(), unidade_termo.strip(), 
                        ativo_info_termo
                    )
                    with open(caminho_pdf, "rb") as pdf_file: 
                        PDFbyte = pdf_file.read()
                    
                    id_termo = f"TRM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    novo_termo = {
                        'id_termo': id_termo, 
                        'patrimonio': pat_real, 
                        'responsavel': responsavel_termo.strip(), 
                        'matricula': mat_salvar, 
                        'unidade': unidade_termo.strip(), 
                        'data_emissao': datetime.now().strftime('%Y-%m-%d'), 
                        'data_baixa': '', 
                        'status_termo': 'Ativo'
                    }
                    try:
                        supabase.table('termos').insert(novo_termo).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria("EMISSÃO DE TERMO (AVULSO)", pat_real, f"Termo {id_termo} emitido manualmente.")
                        
                        st.session_state.pdf_termo_pronto = {
                            'bytes': PDFbyte,
                            'nome_arquivo': f"Termo_PROCISA_{pat_real}.pdf",
                            'msg': "✅ Termo registrado e ativado na nuvem!"
                        }
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar termo: {e}")
                else:
                    st.error("Equipamento não localizado. Verifique o patrimônio/série.")
                    
        elif opcao_termo == "🔄 Emitir 2ª Via de Termo":
            if not df_termos.empty:
                opcoes_2via = df_termos.apply(lambda r: f"{r['id_termo']} | Pat: {r['patrimonio']} | {r['responsavel']} ({r['status_termo']})", axis=1).tolist()
                sel_2via = st.selectbox("Selecione o Termo para Reimpressão (2ª Via):", opcoes_2via)
                if st.button("🖨️ Gerar 2ª Via em PDF", type="primary"):
                    id_2via = sel_2via.split(" | ")[0]
                    t_info = df_termos[df_termos['id_termo'] == id_2via].iloc[0]
                    pat_real = t_info['patrimonio']
                    mat = limpar_texto_matricula(t_info['matricula'])
                    
                    ativo_match = buscar_ativo(pat_real, df_ativos)
                    emp_match = df_empregados[df_empregados['matricula'].astype(str) == mat] if (not df_empregados.empty and mat) else pd.DataFrame()
                    
                    if not ativo_match.empty:
                        emp = emp_match.iloc[0].fillna("").to_dict() if not emp_match.empty else {}
                        caminho_pdf = gerar_termo_pdf(
                            pat_real, t_info['responsavel'], mat, 
                            emp.get('cpf', ''), emp.get('rg', ''), 
                            emp.get('projeto', ativo_match.iloc[0].get('projeto', '')), 
                            t_info['unidade'], ativo_match
                        )
                        with open(caminho_pdf, "rb") as pdf_file:
                            PDFbyte = pdf_file.read()
                        st.session_state.pdf_termo_pronto = {
                            'bytes': PDFbyte,
                            'nome_arquivo': f"2Via_Termo_PROCISA_{pat_real}.pdf",
                            'msg': f"✅ 2ª Via do Termo {id_2via} gerada com sucesso!"
                        }
                        st.rerun()
                    else:
                        st.error("Ativo vinculado não foi encontrado na base mestra.")
            else:
                st.info("Nenhum termo registado no histórico.")
        else:
            pat_baixa = st.text_input("Patrimônio ou Série devolvido:")
            if st.button("Baixar Termo Ativo", type="primary"):
                ativo_info_baixa = buscar_ativo(pat_baixa, df_ativos)
                
                if not ativo_info_baixa.empty:
                    pat_real = ativo_info_baixa.iloc[0]['patrimonio']
                    termos_ativos = df_termos[(df_termos['patrimonio'].astype(str) == str(pat_real)) & (df_termos['status_termo'].isin(['Ativo', 'Pendente Impressão']))] if not df_termos.empty else pd.DataFrame()
                    
                    if not termos_ativos.empty:
                        id_trm = termos_ativos.iloc[0]['id_termo']
                        dados_update_trm = {
                            'data_baixa': datetime.now().strftime('%Y-%m-%d'),
                            'status_termo': 'Encerrado'
                        }
                        try:
                            supabase.table('termos').update(dados_update_trm).eq('id_termo', id_trm).execute()
                            st.cache_data.clear()
                            registrar_log_auditoria("BAIXA DE TERMO", pat_real, f"Termo {id_trm} encerrado por devolução.")
                            st.success("✅ Termo encerrado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao encerrar termo: {e}")
                    else:
                        st.warning("Nenhum termo ativo encontrado para este equipamento.")
                else:
                    st.error("Patrimônio ou série não localizado.")

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
                    try:
                        supabase.table('divergencias').insert(nova_div).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria("DIVERGÊNCIA ABERTA", pat_div.strip(), f"Abertura manual: {obs_abertura}")
                        st.success("Alerta criado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
                        
        with c2:
            st.markdown("###### Resolver Pendência")
            if not pendentes.empty:
                st.dataframe(pendentes[['id_divergencia', 'patrimonio', 'observacoes']], use_container_width=True)
                id_div_selecionada = st.selectbox("Selecione a Divergência:", pendentes['id_divergencia'].tolist())
                obs = st.text_area("Justificativa / Ação Tomada:")
                analista = st.text_input("Analista Responsável:", value=st.session_state.nome_real)
                if st.button("Aplicar Resolução", type="primary"):
                    if obs.strip() and analista.strip():
                        try:
                            dados_update_div = {
                                'status_resolucao': 'Resolvido',
                                'observacoes': obs.strip(),
                                'analista_responsavel': analista.strip()
                            }
                            supabase.table('divergencias').update(dados_update_div).eq('id_divergencia', id_div_selecionada).execute()
                            st.cache_data.clear()
                            
                            div_pat = pendentes[pendentes['id_divergencia'] == id_div_selecionada].iloc[0]['patrimonio']
                            registrar_log_auditoria(
                                "RESOLUÇÃO DIVERGÊNCIA", 
                                div_pat, 
                                f"Divergência {id_div_selecionada} resolvida. Ação: {obs.strip()}"
                            )
                            st.success("✅ Divergência resolvida com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao resolver: {e}")
                    else:
                        st.error("Preencha a justificativa.")
            else:
                st.success("Nenhuma divergência pendente!")

# ==========================================
# MÓDULO 5: DIAGNÓSTICO (LABORATÓRIO)
# ==========================================
def render_modulo_laboratorio(df_ativos):
    st.header("🔬 Laboratório Técnico")
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
                
                registrar_log_auditoria(
                    "LAUDO LABORATÓRIO", 
                    pat_real, 
                    f"Parecer: '{cond_antiga}' -> '{resultado}'. Novo Status: '{novo_status}'."
                )
                st.success(f"✅ Laudo registrado! Ativo atualizado para: {novo_status}")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar laudo: {e}")
        else:
            st.warning("⚠️ Patrimônio ou série não localizado.")
