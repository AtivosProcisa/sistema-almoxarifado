import streamlit as st
import pandas as pd
import io
from datetime import datetime
from nuvem import (
    supabase, COLUNAS_ATIVOS, COLUNAS_MOV, COLUNAS_TERMOS, COLUNAS_DIVERG, COLUNAS_EMPREGADOS,
    normalizar_nome_coluna, salvar_dados_massa, registrar_log_auditoria,
    calcular_uso_supabase, exibir_marca_desenvolvedor, matricula_valida,
    limpar_texto_matricula, expurgar_linhas_nulas_nuvem
)
from pdf_termo import converter_df_excel_simples, gerar_backup_completo_excel

# ==========================================
# MÓDULO 1: DASHBOARD E CONCILIAÇÃO
# ==========================================
def render_modulo_dashboard(df_ativos, df_mov, df_termos, df_diverg, df_empregados):
    st.header("📊 Painel Gerencial e Conciliação")
    
    if st.session_state.get('resumo_ultima_operacao'):
        info_op = st.session_state.resumo_ultima_operacao
        st.success(f"✅ **{info_op['titulo']}** | Sistema atualizado às {info_op['hora']}")
        c_op1, c_op2, c_op3, c_op4 = st.columns(4)
        c_op1.metric("Quantidade Anterior", info_op['qtd_antes'])
        c_op2.metric("Novos Inseridos", f"+{info_op['novos']}")
        c_op3.metric("Existentes Atualizados", info_op['atualizados'])
        c_op4.metric("Total Atual na Base", info_op['qtd_depois'], delta=f"{info_op['qtd_depois'] - info_op['qtd_antes']} ativos")
        if st.button("✖️ Fechar Resumo de Envio"):
            st.session_state.resumo_ultima_operacao = None
            st.rerun()
        st.divider()

    total_ativos = len(df_ativos)
    if not df_ativos.empty:
        cautela_upper = df_ativos['cautela'].fillna("").astype(str).str.upper()
        status_upper = df_ativos['status_sistema'].fillna("").astype(str).str.upper()
        
        mask_almox = cautela_upper.str.contains('ALMOX')
        mask_disp = status_upper == 'DISPONÍVEL'
        mask_uso = status_upper == 'EM USO'
        mask_manut = status_upper.str.contains('MANUTEN') | cautela_upper.str.contains('LAB')
        
        disp_estoque = len(df_ativos[mask_disp & mask_almox])
        em_uso = len(df_ativos[mask_uso])
        em_manut = len(df_ativos[mask_manut])
    else:
        disp_estoque, em_uso, em_manut = 0, 0, 0
        
    diverg_pend = len(df_diverg[df_diverg['status_resolucao'] != 'Resolvido']) if not df_diverg.empty else 0
    termos_fila = len(df_termos[df_termos['status_termo'] == 'Pendente Impressão']) if not df_termos.empty else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total de Ativos", total_ativos)
    col2.metric("Disponíveis (Almox)", disp_estoque, help="Status 'Disponível' + Cautela 'Almoxarifado'")
    col3.metric("Em Uso (Campo)", em_uso)
    col4.metric("Laboratório / Manut.", em_manut)
    col5.metric("Divergências / Fila Termos", f"{diverg_pend} / {termos_fila}")

    abas_dashboard = [
        "Inventário Geral", 
        "Histórico de Movimentações", 
        "Termos Emitidos", 
        "➕ Novo Cadastro Manual", 
        "📥 Importar / Exportar Relatórios"
    ]
    if st.session_state.perfil == 'Master':
        abas_dashboard.append("❌ Excluir Registos (Master)")
        
    abas = st.tabs(abas_dashboard)
    
    with abas[0]:
        if not df_ativos.empty:
            cf1, cf2, cf3 = st.columns(3)
            with cf1:
                f_status = st.selectbox("Filtrar Status:", ["Todos"] + sorted(df_ativos['status_sistema'].fillna("").unique().tolist()))
            with cf2:
                f_coord = st.selectbox("Filtrar Coordenação:", ["Todas"] + sorted(df_ativos['coordenacao'].fillna("").unique().tolist()))
            with cf3:
                f_busca = st.text_input("Buscar por Patrimônio, Série, Equipamento ou Cautela:")
                
            df_inv_view = df_ativos[COLUNAS_ATIVOS].copy()
            if f_status != "Todos":
                df_inv_view = df_inv_view[df_inv_view['status_sistema'] == f_status]
            if f_coord != "Todas":
                df_inv_view = df_inv_view[df_inv_view['coordenacao'] == f_coord]
            if f_busca.strip():
                t_b = f_busca.strip().lower()
                mask_b = df_inv_view.astype(str).apply(lambda x: x.str.lower().str.contains(t_b, na=False)).any(axis=1)
                df_inv_view = df_inv_view[mask_b]
            st.dataframe(df_inv_view, use_container_width=True)
        else:
            st.dataframe(df_ativos, use_container_width=True)
            
    with abas[1]:
        st.dataframe(df_mov, use_container_width=True)
    with abas[2]:
        st.dataframe(df_termos, use_container_width=True)
        
    with abas[3]:
        st.subheader("Cadastrar ou Atualizar Ativo Individual")
        with st.form("form_novo_ativo"):
            colA, colB, colC = st.columns(3)
            with colA:
                cad_patrimonio = st.text_input("Patrimônio / Placa *")
                cad_equipamento = st.text_input("Equipamento")
                cad_marca = st.text_input("Marca")
                cad_modelo = st.text_input("Modelo")
                cad_serie = st.text_input("Número de Série")
            with colB:
                cad_item = st.text_input("Item")
                cad_valor = st.text_input("Valor")
                cad_cautela = st.text_input("Cautela (Local/Responsável)", value="ALMOXARIFADO CENTRAL")
                cad_projeto = st.text_input("Projeto", value="ESTOQUE ALMOXARIFADO")
                cad_coord = st.text_input("Coordenação", value="LOGÍSTICA / ALMOXARIFADO")
            with colC:
                cad_nf = st.text_input("NF Procisa")
                cad_condicao = st.text_input("Condições para Uso", value="APTO")
                cad_acessorios = st.text_input("Acessórios")
                cad_status = st.selectbox("Status no Sistema", ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"])
            
            submit_cadastro = st.form_submit_button("💾 Salvar Ativo na Nuvem", type="primary")
            
            if submit_cadastro:
                if cad_patrimonio.strip():
                    pat_limpo = cad_patrimonio.strip()
                    qtd_antes = len(df_ativos)
                    ja_existia = (not df_ativos.empty) and (pat_limpo in df_ativos['patrimonio'].astype(str).values)
                    
                    dados_novo = {
                        'item': cad_item.strip(),
                        'valor': cad_valor.strip(),
                        'equipamento': cad_equipamento.strip(),
                        'marca': cad_marca.strip(),
                        'modelo': cad_modelo.strip(),
                        'numero_serie': cad_serie.strip(),
                        'patrimonio': pat_limpo,
                        'cautela': cad_cautela.strip(),
                        'projeto': cad_projeto.strip(),
                        'coordenacao': cad_coord.strip(),
                        'nf_procisa': cad_nf.strip(),
                        'atualizado_em': datetime.now().strftime('%Y-%m-%d'),
                        'condicoes_para_uso': cad_condicao.strip(),
                        'acessorios': cad_acessorios.strip(),
                        'status_sistema': cad_status
                    }
                    
                    try:
                        if ja_existia:
                            supabase.table('ativos_master').update(dados_novo).eq('patrimonio', pat_limpo).execute()
                            tipo_op = "ATUALIZAÇÃO MANUAL"
                            qtd_depois = qtd_antes
                        else:
                            supabase.table('ativos_master').insert(dados_novo).execute()
                            tipo_op = "CADASTRO MANUAL"
                            qtd_depois = qtd_antes + 1
                            
                        st.cache_data.clear()
                        registrar_log_auditoria(tipo_op, pat_limpo, f"Ativo {pat_limpo} ({cad_marca} {cad_modelo}) salvo via formulário.")
                        
                        st.session_state.resumo_ultima_operacao = {
                            'titulo': f"Cadastro/Atualização Concluída ({pat_limpo})",
                            'hora': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                            'qtd_antes': qtd_antes,
                            'novos': 0 if ja_existia else 1,
                            'atualizados': 1 if ja_existia else 0,
                            'qtd_depois': qtd_depois
                        }
                        st.rerun()
                    except Exception as err:
                        st.error(f"Erro ao salvar: {err}")
                else:
                    st.error("O campo 'Patrimônio' é obrigatório.")

    with abas[4]:
        st.subheader("📤 Exportar Relatórios do Sistema (Download)")
        st.write("Extraia a qualquer momento as bases atualizadas diretamente da nuvem em formato Excel (`.xlsx`).")
        
        stamp = datetime.now().strftime('%Y%m%d_%H%M')
        c_exp1, c_exp2, c_exp3 = st.columns(3)
        
        with c_exp1:
            df_a_exp = df_ativos[COLUNAS_ATIVOS] if not df_ativos.empty else pd.DataFrame(columns=COLUNAS_ATIVOS)
            if st.download_button("📥 Baixar Relatório de Ativos (.xlsx)", data=converter_df_excel_simples(df_a_exp, "Ativos"), file_name=f"Ativos_Procisa_{stamp}.xlsx", use_container_width=True):
                registrar_log_auditoria("EXPORTAÇÃO EXCEL", "Ativos", f"Download de {len(df_a_exp)} ativos.")
                
            df_e_exp = df_empregados[COLUNAS_EMPREGADOS] if not df_empregados.empty else pd.DataFrame(columns=COLUNAS_EMPREGADOS)
            if st.download_button("📥 Baixar Base de Colaboradores (.xlsx)", data=converter_df_excel_simples(df_e_exp, "Colaboradores"), file_name=f"Colaboradores_Procisa_{stamp}.xlsx", use_container_width=True):
                registrar_log_auditoria("EXPORTAÇÃO EXCEL", "Colaboradores", f"Download de {len(df_e_exp)} colaboradores.")

        with c_exp2:
            df_m_exp = df_mov[COLUNAS_MOV] if not df_mov.empty else pd.DataFrame(columns=COLUNAS_MOV)
            if st.download_button("📥 Baixar Histórico Movimentações (.xlsx)", data=converter_df_excel_simples(df_m_exp, "Movimentacoes"), file_name=f"Movimentacoes_Procisa_{stamp}.xlsx", use_container_width=True):
                registrar_log_auditoria("EXPORTAÇÃO EXCEL", "Movimentações", f"Download de {len(df_m_exp)} movimentações.")
                
            df_t_exp = df_termos[COLUNAS_TERMOS] if not df_termos.empty else pd.DataFrame(columns=COLUNAS_TERMOS)
            if st.download_button("📥 Baixar Relatório de Termos (.xlsx)", data=converter_df_excel_simples(df_t_exp, "Termos"), file_name=f"Termos_Procisa_{stamp}.xlsx", use_container_width=True):
                registrar_log_auditoria("EXPORTAÇÃO EXCEL", "Termos", f"Download de {len(df_t_exp)} termos.")

        with c_exp3:
            df_d_exp = df_diverg[COLUNAS_DIVERG] if not df_diverg.empty else pd.DataFrame(columns=COLUNAS_DIVERG)
            if st.download_button("📥 Baixar Relatório Divergências (.xlsx)", data=converter_df_excel_simples(df_d_exp, "Divergencias"), file_name=f"Divergencias_Procisa_{stamp}.xlsx", use_container_width=True):
                registrar_log_auditoria("EXPORTAÇÃO EXCEL", "Divergências", f"Download de {len(df_d_exp)} divergências.")
                
            backup_bytes = gerar_backup_completo_excel({
                "Ativos_Master": df_a_exp,
                "Colaboradores": df_e_exp,
                "Movimentacoes": df_m_exp,
                "Termos": df_t_exp,
                "Divergencias": df_d_exp
            })
            if st.download_button("📦 Baixar Backup Completo (Multi-Abas)", data=backup_bytes, file_name=f"Backup_Geral_Procisa_{stamp}.xlsx", type="primary", use_container_width=True):
                registrar_log_auditoria("BACKUP COMPLETO", "Sistema", "Exportação de todas as tabelas em arquivo multi-abas.")

        st.divider()
        st.subheader("📥 Carga Inicial / Atualização em Massa (Upload)")
        
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            st.markdown("##### 📦 Planilha de Equipamentos (V1.2)")
            arquivo_up = st.file_uploader("Arraste o arquivo Excel de EQUIPAMENTOS (.xlsx)", type=["xlsx"])
            if arquivo_up:
                try:
                    df_up = pd.read_excel(arquivo_up)
                    df_up.columns = [normalizar_nome_coluna(c) for c in df_up.columns]
                    
                    if 'status_sistema' not in df_up.columns:
                        df_up['status_sistema'] = 'Disponível'
                    
                    if 'patrimonio' not in df_up.columns:
                        st.error(f"A coluna 'patrimonio' não foi encontrada. Colunas lidas: {list(df_up.columns)}")
                    else:
                        df_up = df_up[df_up['patrimonio'].apply(matricula_valida)].copy()
                        df_up['patrimonio'] = df_up['patrimonio'].apply(limpar_texto_matricula)
                        df_up = df_up.drop_duplicates(subset=['patrimonio'], keep='last')
                        
                        atuais_set = set(df_ativos['patrimonio'].astype(str).str.strip()) if not df_ativos.empty else set()
                        novos_set = set(df_up['patrimonio'])
                        
                        qtd_antes = len(atuais_set)
                        qtd_novos = len(novos_set - atuais_set)
                        qtd_atualizados = len(novos_set.intersection(atuais_set))
                        qtd_depois = len(atuais_set.union(novos_set))
                        
                        st.caption(f"Antes: **{qtd_antes}** | Novos: **+{qtd_novos}** | Atualizados: **{qtd_atualizados}** | Projeção: **{qtd_depois}**")
                        st.dataframe(df_up.head(3), use_container_width=True)
                        
                        if st.button("🚀 Confirmar e Subir Equipamentos", type="primary"):
                            with st.spinner("Enviando equipamentos para o Supabase..."):
                                expurgar_linhas_nulas_nuvem()
                                if salvar_dados_massa('ativos_master', df_up, COLUNAS_ATIVOS):
                                    detalhe_log = f"Arquivo '{arquivo_up.name}' enviado. Novos: +{qtd_novos} | Atualizados: {qtd_atualizados}."
                                    registrar_log_auditoria("UPLOAD PLANILHA", arquivo_up.name, detalhe_log)
                                    st.session_state.resumo_ultima_operacao = {
                                        'titulo': f"Envio da planilha '{arquivo_up.name}' concluído!",
                                        'hora': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                                        'qtd_antes': qtd_antes,
                                        'novos': qtd_novos,
                                        'atualizados': qtd_atualizados,
                                        'qtd_depois': qtd_depois
                                    }
                                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao ler o arquivo Excel: {e}")
                    
        with col_up2:
            st.markdown("##### 👥 Planilha de Colaboradores")
            arquivo_emp = st.file_uploader("Arraste a planilha de COLABORADORES (.xlsx)", type=["xlsx"], key="up_emp")
            if arquivo_emp:
                try:
                    df_emp_up = pd.read_excel(arquivo_emp)
                    df_emp_up.columns = [normalizar_nome_coluna(c) for c in df_emp_up.columns]
                    
                    if 'matricula' not in df_emp_up.columns:
                        st.error("A coluna obrigatória 'matricula' não foi encontrada.")
                    else:
                        total_lido = len(df_emp_up)
                        df_emp_up = df_emp_up[df_emp_up['matricula'].apply(matricula_valida)].copy()
                        df_emp_up['matricula'] = df_emp_up['matricula'].apply(limpar_texto_matricula)
                        df_emp_up = df_emp_up.drop_duplicates(subset=['matricula'], keep='last')
                        ignorados = total_lido - len(df_emp_up)
                        
                        st.caption(f"**{len(df_emp_up)}** colaboradores válidos prontos ({ignorados} linhas sem matrícula ignoradas).")
                        st.dataframe(df_emp_up.head(3), use_container_width=True)
                        
                        if st.button("🚀 Subir Base de Colaboradores", type="primary"):
                            with st.spinner("Atualizando colaboradores no Supabase..."):
                                expurgar_linhas_nulas_nuvem()
                                if salvar_dados_massa('empregados', df_emp_up, COLUNAS_EMPREGADOS):
                                    registrar_log_auditoria("UPLOAD COLABORADORES", arquivo_emp.name, f"Base de {len(df_emp_up)} colaboradores atualizada.")
                                    st.success("✅ Base de colaboradores salva com sucesso na nuvem!")
                                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao ler arquivo: {e}")

    # --- ABA DE EXCLUSÃO POR SELEÇÃO DE LINHAS (MASTER) ---
    if st.session_state.perfil == 'Master':
        with abas[5]:
            st.subheader("❌ Exclusão de Registos por Seleção (Acesso Restrito Master)")
            st.warning("⚠️ Marque a caixa **'🗑️ Excluir?'** nas linhas que deseja remover permanentemente do banco de dados e clique no botão de confirmação abaixo.")
            
            tipo_exclusao = st.radio("Selecione a Tabela para Exclusão:", ["📦 Ativos (Equipamentos)", "👥 Colaboradores (Empregados)"], horizontal=True)
            
            if tipo_exclusao.startswith("📦"):
                if not df_ativos.empty:
                    busca_del = st.text_input("🔍 Filtrar ativos antes de marcar (Patrimônio, Série, Equipamento ou Cautela):")
                    df_del_view = df_ativos[COLUNAS_ATIVOS].copy()
                    if busca_del.strip():
                        t_del = busca_del.strip().lower()
                        mask_del = df_del_view.astype(str).apply(lambda x: x.str.lower().str.contains(t_del, na=False)).any(axis=1)
                        df_del_view = df_del_view[mask_del]
                        
                    df_del_view.insert(0, "Excluir", False)
                    
                    df_editado = st.data_editor(
                        df_del_view,
                        hide_index=True,
                        use_container_width=True,
                        disabled=[c for c in df_del_view.columns if c != "Excluir"],
                        column_config={
                            "Excluir": st.column_config.CheckboxColumn("🗑️ Excluir?", default=False)
                        },
                        key="editor_del_ativos"
                    )
                    
                    selecionados = df_editado[df_editado["Excluir"] == True]
                    if not selecionados.empty:
                        st.error(f"⚠️ Você selecionou **{len(selecionados)} ativo(s)** para exclusão definitiva: `{', '.join(selecionados['patrimonio'].astype(str).tolist())}`")
                        if st.button(f"🗑️ Confirmar Exclusão de {len(selecionados)} Ativo(s)", type="primary"):
                            try:
                                expurgar_linhas_nulas_nuvem()
                                lista_pats = [p for p in selecionados['patrimonio'].astype(str).tolist() if matricula_valida(p)]
                                for p_del in lista_pats:
                                    supabase.table('ativos_master').delete().eq('patrimonio', p_del).execute()
                                registrar_log_auditoria("EXCLUSÃO EM LOTE (ATIVOS)", f"{len(selecionados)} itens", f"Patrimônios excluídos pelo Master: {', '.join(lista_pats)}")
                                st.cache_data.clear()
                                st.success(f"✅ {len(selecionados)} ativo(s) excluído(s) permanentemente!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir ativos: {e}")
                else:
                    st.info("A tabela de ativos está vazia.")
            else:
                if not df_empregados.empty:
                    busca_emp_del = st.text_input("🔍 Filtrar colaborador por Nome ou Matrícula:")
                    df_emp_view = df_empregados[COLUNAS_EMPREGADOS].copy()
                    if busca_emp_del.strip():
                        t_edel = busca_emp_del.strip().lower()
                        mask_edel = df_emp_view.astype(str).apply(lambda x: x.str.lower().str.contains(t_edel, na=False)).any(axis=1)
                        df_emp_view = df_emp_view[mask_edel]
                        
                    df_emp_view.insert(0, "Excluir", False)
                    
                    df_emp_editado = st.data_editor(
                        df_emp_view,
                        hide_index=True,
                        use_container_width=True,
                        disabled=[c for c in df_emp_view.columns if c != "Excluir"],
                        column_config={
                            "Excluir": st.column_config.CheckboxColumn("🗑️ Excluir?", default=False)
                        },
                        key="editor_del_emp"
                    )
                    
                    emp_selecionados = df_emp_editado[df_emp_editado["Excluir"] == True]
                    if not emp_selecionados.empty:
                        st.error(f"⚠️ Você selecionou **{len(emp_selecionados)} colaborador(es)** para exclusão: `{', '.join(emp_selecionados['nome'].astype(str).tolist())}`")
                        if st.button(f"🗑️ Confirmar Exclusão de {len(emp_selecionados)} Colaborador(es)", type="primary"):
                            try:
                                expurgar_linhas_nulas_nuvem()
                                lista_mats = [m for m in emp_selecionados['matricula'].astype(str).tolist() if matricula_valida(m)]
                                for m_del in lista_mats:
                                    supabase.table('empregados').delete().eq('matricula', m_del).execute()
                                registrar_log_auditoria("EXCLUSÃO COLABORADORES", f"{len(emp_selecionados)} itens", f"Matrículas excluídas: {', '.join(lista_mats)}")
                                st.cache_data.clear()
                                st.success(f"✅ {len(emp_selecionados)} colaborador(es) removido(s) com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir colaboradores: {e}")
                else:
                    st.info("A tabela de colaboradores está vazia.")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 6: GESTÃO DE USUÁRIOS (MASTER)
# ==========================================
def render_modulo_usuarios(df_usuarios):
    st.header("👥 Painel Admin - Gestão de Usuários")
    
    aba_listar, aba_novo, aba_editar = st.tabs(["Visão Geral", "Novo Usuário", "Editar / Resetar Senha"])
    
    with aba_listar:
        st.dataframe(df_usuarios, use_container_width=True)
        
    with aba_novo:
        with st.form("form_novo_user"):
            col1, col2 = st.columns(2)
            with col1:
                novo_login = st.text_input("Login de Acesso (Ex: j.silva)")
                novo_nome = st.text_input("Nome Completo")
            with col2:
                nova_senha = st.text_input("Senha Inicial", type="password")
                opcoes_perfis = ["Operador Campo", "Almoxarifado", "Laboratório", "Master"]
                novo_perfil = st.selectbox("Nível de Acesso (Perfil)", opcoes_perfis)
            
            if st.form_submit_button("Cadastrar Usuário", type="primary"):
                if novo_login.strip() and nova_senha.strip() and novo_nome.strip():
                    login_limpo = novo_login.strip()
                    if not df_usuarios.empty and login_limpo in df_usuarios['usuario'].values:
                        st.error("Este login já existe! Escolha outro.")
                    else:
                        novo_registo = {
                            'usuario': login_limpo, 
                            'senha': str(nova_senha).strip(), 
                            'perfil': novo_perfil, 
                            'nome': novo_nome.strip()
                        }
                        try:
                            supabase.table('usuarios').insert(novo_registo).execute()
                            st.cache_data.clear()
                            registrar_log_auditoria("CRIAÇÃO USUÁRIO", login_limpo, f"Usuário '{novo_nome.strip()}' criado com perfil '{novo_perfil}'.")
                            st.success(f"✅ Usuário {novo_nome} cadastrado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao criar usuário: {e}")
                else:
                    st.error("Preencha todos os campos obrigatórios.")
                    
    with aba_editar:
        if not df_usuarios.empty:
            usuario_editar = st.selectbox("Selecione o Usuário para alterar:", df_usuarios['usuario'].tolist())
            if usuario_editar:
                user_match = df_usuarios[df_usuarios['usuario'] == usuario_editar].iloc[0].to_dict()
                
                col_a, col_b = st.columns(2)
                with col_a:
                    senha_reset = st.text_input("Nova Senha", value=str(user_match.get('senha', '')))
                with col_b:
                    lista_perfis = ["Operador Campo", "Almoxarifado", "Laboratório", "Master"]
                    perfil_atual = user_match.get('perfil', 'Operador Campo')
                    idx_p = lista_perfis.index(perfil_atual) if perfil_atual in lista_perfis else 0
                    perfil_edit = st.selectbox("Mudar Perfil", lista_perfis, index=idx_p)
                    
                col_bt1, col_bt2 = st.columns(2)
                with col_bt1:
                    if st.button("💾 Salvar Alterações", use_container_width=True):
                        try:
                            dados_update_user = {'senha': str(senha_reset).strip(), 'perfil': perfil_edit}
                            supabase.table('usuarios').update(dados_update_user).eq('usuario', usuario_editar).execute()
                            st.cache_data.clear()
                            registrar_log_auditoria("EDIÇÃO USUÁRIO", usuario_editar, f"Perfil/Senha atualizados (Perfil atual: {perfil_edit}).")
                            st.success(f"✅ Dados de {usuario_editar} atualizados!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar usuário: {e}")
                with col_bt2:
                    if st.button("❌ Excluir Usuário", type="primary", use_container_width=True):
                        if usuario_editar != 'master':
                            try:
                                supabase.table('usuarios').delete().eq('usuario', usuario_editar).execute()
                                st.cache_data.clear()
                                registrar_log_auditoria("EXCLUSÃO USUÁRIO", usuario_editar, f"Usuário {usuario_editar} removido do sistema.")
                                st.success("✅ Usuário removido da nuvem!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao excluir usuário: {e}")
                        else:
                            st.warning("Não é possível excluir o usuário Master principal.")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 7: AUDITORIA GERAL (EXCLUSIVO GESTOR)
# ==========================================
def render_modulo_auditoria(df_ativos, df_mov, df_termos, df_diverg, df_logs, df_usuarios, df_empregados):
    if st.session_state.perfil != 'Master':
        st.error("⛔ Acesso negado. Este módulo é exclusivo para o perfil Gestor (Master).")
        st.stop()
        
    st.header("🛡️ Central de Auditoria e Rastreabilidade (Gestor)")
    
    info_cap = calcular_uso_supabase([df_ativos, df_mov, df_termos, df_diverg, df_logs, df_usuarios, df_empregados], limite_mb=500.0)
    st.markdown(
        f"<div style='background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 6px 14px; font-size: 0.80rem; color: #555; display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;'>"
        f"<span>☁️ <b>Armazenamento Supabase (500 MB):</b> Utilizado: <b>{info_cap['usado_mb']:.2f} MB ({info_cap['pct_usado']:.1f}%)</b> &nbsp;|&nbsp; Livre: <b>{info_cap['livre_mb']:.2f} MB ({info_cap['pct_livre']:.1f}%)</b> &nbsp;|&nbsp; Tabelas: {info_cap['dados_puros_kb']:.1f} KB ({info_cap['total_linhas']} reg.)</span>"
        f"<span style='color: #888; font-size: 0.74rem;'>Desenvolvido por Marcos Paulo Da Veiga Carvalho</span>"
        f"</div>",
        unsafe_allow_html=True
    )

    lista_eventos = []
    
    if not df_logs.empty:
        for _, r in df_logs.iterrows():
            lista_eventos.append({
                'Data / Hora': str(r.get('data_registro', '')),
                'Tipo de Evento': str(r.get('tipo_divergencia', '')).replace('[LOG-SISTEMA] ', ''),
                'Alvo / Patrimônio': str(r.get('patrimonio', '')),
                'Usuário / Responsável': str(r.get('analista_responsavel', '')),
                'Detalhes da Operação': str(r.get('observacoes', ''))
            })
            
    if not df_mov.empty:
        for _, r in df_mov.iterrows():
            lista_eventos.append({
                'Data / Hora': str(r.get('data_hora', '')),
                'Tipo de Evento': f"MOVIMENTAÇÃO ({r.get('tipo_mov', '')})",
                'Alvo / Patrimônio': str(r.get('patrimonio', '')),
                'Usuário / Responsável': str(r.get('solicitante', '')),
                'Detalhes da Operação': f"Origem: {r.get('origem', '')} -> Destino: {r.get('destino', '')} | Status: {r.get('status_mov', '')}"
            })
            
    if not df_termos.empty:
        for _, r in df_termos.iterrows():
            lista_eventos.append({
                'Data / Hora': str(r.get('data_emissao', '')),
                'Tipo de Evento': "TERMO DE RESPONSABILIDADE",
                'Alvo / Patrimônio': str(r.get('patrimonio', '')),
                'Usuário / Responsável': str(r.get('responsavel', '')),
                'Detalhes da Operação': f"Termo {r.get('id_termo', '')} | Unidade: {r.get('unidade', '')} | Status: {r.get('status_termo', '')} | Baixa: {r.get('data_baixa', '-')}"
            })
            
    df_auditoria = pd.DataFrame(lista_eventos)
    if not df_auditoria.empty:
        df_auditoria = df_auditoria.sort_values(by='Data / Hora', ascending=False).reset_index(drop=True)
        
    col_a1, col_a2, col_a3 = st.columns(3)
    total_ev = len(df_auditoria)
    total_uploads = len(df_auditoria[df_auditoria['Tipo de Evento'].str.contains('UPLOAD|CADASTRO|EXCLUSÃO', na=False)]) if not df_auditoria.empty else 0
    total_movs = len(df_auditoria[df_auditoria['Tipo de Evento'].str.contains('MOV|CONFERÊNCIA|TERMO|VALIDAÇÃO', na=False)]) if not df_auditoria.empty else 0
    
    col_a1.metric("Total de Eventos Auditados", total_ev)
    col_a2.metric("Cargas / Cadastros / Exclusões", total_uploads)
    col_a3.metric("Operações de Campo / Almox.", total_movs)
    
    st.divider()
    
    if not df_auditoria.empty:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            tipos_unicos = ["Todos"] + sorted(df_auditoria['Tipo de Evento'].unique().tolist())
            filtro_tipo = st.selectbox("Filtrar por Tipo de Ação:", tipos_unicos)
        with col_f2:
            busca_texto = st.text_input("Buscar por Patrimônio, Usuário ou Palavra-chave:")
            
        df_filtrado = df_auditoria.copy()
        if filtro_tipo != "Todos":
            df_filtrado = df_filtrado[df_filtrado['Tipo de Evento'] == filtro_tipo]
        if busca_texto.strip():
            termo = busca_texto.strip().lower()
            mask = (
                df_filtrado['Alvo / Patrimônio'].str.lower().str.contains(termo, na=False) |
                df_filtrado['Usuário / Responsável'].str.lower().str.contains(termo, na=False) |
                df_filtrado['Detalhes da Operação'].str.lower().str.contains(termo, na=False)
            )
            df_filtrado = df_filtrado[mask]
            
        st.dataframe(df_filtrado, use_container_width=True, height=450)
        
        out_aud = io.BytesIO()
        with pd.ExcelWriter(out_aud, engine='openpyxl') as writer:
            df_filtrado.to_excel(writer, index=False, sheet_name='Auditoria_Sistema')
        
        st.download_button(
            label="📥 Exportar Relatório de Auditoria (.xlsx)",
            data=out_aud.getvalue(),
            file_name=f"Relatorio_Auditoria_Procisa_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Nenhum evento de auditoria registrado até o momento.")

    exibir_marca_desenvolvedor()
