import streamlit as st
import pandas as pd
from datetime import datetime
import nuvem
import operacao
from pdf_termo import converter_df_excel_simples

supabase = nuvem.supabase
registrar_log_auditoria = nuvem.registrar_log_auditoria
exibir_marca_desenvolvedor = nuvem.exibir_marca_desenvolvedor
calcular_dias_sem_mov = getattr(nuvem, 'calcular_dias_sem_mov', lambda x: "0")

MOTIVOS_SEGREGACAO_DESCARTE = [
    "Avariado sem possibilidade de reparo",
    "Obsoleto",
    "Fim de vida útil",
    "Reparo economicamente inviável",
    "Incompatibilidade tecnológica",
    "Sucateado",
    "Dano físico irreversível",
    "Outro (exige justificativa)"
]

STATUS_FLUXO_DESCARTE = [
    "Identificado para descarte",
    "Segregado",
    "Em avaliação",
    "Aguardando aprovação",
    "Aprovado para descarte",
    "Descartado",
    "Baixado",
    "Descarte reprovado -> Retornar para avaliação",
    "Reaproveitamento aprovado -> Retornar ao estoque/operação"
]

STATUS_ROUBO_FURTO = [
    "Em análise",
    "B.O. realizado",
    "Baixa solicitada",
    "Baixado"
]

STATUS_SEM_GIRO = [
    "Sem giro",
    "Em análise",
    "Reaproveitar / Transferir",
    "Descartar",
    "Aprovado para descarte",
    "Baixado"
]

def classificar_faixa_aging(dias):
    try:
        d = int(float(str(dias).strip()))
    except Exception:
        d = 0
    if d <= 90:
        return "🟢 0 a 90 dias (Giro Normal)"
    elif d <= 180:
        return "🟡 91 a 180 dias (Atenção)"
    elif d <= 365:
        return "🟠 181 a 365 dias (Baixo Giro)"
    else:
        return "🔴 > 365 dias (Candidato Obsolescência/Descarte)"

def render_modulo_governanca_eqp(df_ativos, df_roubo, df_sem_giro, df_descarte):
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("🚨 Governança de Ativos — Roubo/Furto, Sem Giro (Aging) e Descarte")
    st.caption("Controle de ocorrências, ociosidade e descarte definitivo com bloqueio automático de movimentação e rastreabilidade integral.")

    aba_roubo, aba_aging, aba_descarte = st.tabs([
        f"🚨 Roubados / Furtados ({len(df_roubo)})",
        f"⏳ Sem Giro / Aging ({len(df_sem_giro)})",
        f"🗑️ Segregados para Descarte ({len(df_descarte)})"
    ])

    # ==========================================================
    # ABA 1: EQUIPAMENTOS ROUBADOS / FURTADOS
    # ==========================================================
    with aba_roubo:
        st.markdown("##### 🚨 Controle de Equipamentos Roubados / Furtados")
        st.caption("Ao registrar uma ocorrência, o equipamento é bloqueado automaticamente na base principal (`Status: Roubado/Furtado`) e deixa de contar como disponível.")

        sub_r1, sub_r2, sub_r3 = st.tabs([
            "📋 Histórico de Ocorrências",
            "➕ Registrar Nova Ocorrência",
            "✏️ Atualizar B.O. / Status / Baixa"
        ])

        with sub_r1:
            if not df_roubo.empty:
                st.dataframe(df_roubo, use_container_width=True, hide_index=True, height=380)
                st.download_button(
                    "📥 Exportar Roubados/Furtados (.xlsx)",
                    data=converter_df_excel_simples(df_roubo, "Roubo_Furto"),
                    file_name=f"Equipamentos_Roubo_Furto_{datetime.now().strftime('%Y%m%d')}.xlsx"
                )
            else:
                st.info("Nenhuma ocorrência de roubo ou furto registrada.")

        with sub_r2:
            ativos_elegiveis = df_ativos[~df_ativos['status_sistema'].astype(str).str.upper().isin(['ROUBADO/FURTADO', 'BAIXADO'])].copy() if not df_ativos.empty else pd.DataFrame()
            st.markdown("###### 1️⃣ Selecione o equipamento na tabela (Estilo Excel):")
            df_sel_r = operacao.render_seletor_excel_equipamentos(ativos_elegiveis, "roubo_eqp_sel", multiplo=False, altura=180)

            if not df_sel_r.empty:
                r_at = df_sel_r.iloc[0].to_dict()
                pat_r = str(r_at['patrimonio']).strip()
                with st.form("form_reg_roubo"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        tipo_oc = st.selectbox("Tipo de Ocorrência *", ["Roubo", "Furto"])
                        dt_oc = st.date_input("Data da Ocorrência *", datetime.today())
                        resp_oc = st.text_input("Responsável na Ocorrência *", value=str(r_at.get('cautela', '')))
                        base_oc = st.text_input("Base / Última Localização Conhecida", value=str(r_at.get('coordenacao', '')))
                    with c2:
                        num_bo = st.text_input("Nº do B.O.")
                        dt_bo = st.text_input("Data do B.O. (DD/MM/AAAA ou AAAA-MM-DD)")
                        anexo_bo = st.text_input("Link / Referência do Anexo do B.O.")
                    with c3:
                        st_oc = st.selectbox("Status da Ocorrência *", STATUS_ROUBO_FURTO, index=0)
                        obs_oc = st.text_area("Observações / Relato:")

                    if st.form_submit_button("🚨 Registrar Ocorrência e Bloquear Equipamento", type="primary"):
                        id_oc = f"RF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        novo_rf = {
                            'id_ocorrencia': id_oc,
                            'equipamento': str(r_at.get('equipamento', '')),
                            'fabricante_modelo': f"{r_at.get('marca', '')} {r_at.get('modelo', '')}".strip(),
                            'numero_serie': str(r_at.get('numero_serie', '')),
                            'patrimonio': pat_r,
                            'base_localizacao': base_oc.strip(),
                            'responsavel': resp_oc.strip(),
                            'data_ocorrencia': dt_oc.strftime('%Y-%m-%d'),
                            'tipo': tipo_oc,
                            'num_bo': num_bo.strip(),
                            'data_bo': dt_bo.strip(),
                            'anexo_bo': anexo_bo.strip(),
                            'status': st_oc,
                            'data_baixa': datetime.now().strftime('%Y-%m-%d') if st_oc == "Baixado" else "",
                            'observacao': obs_oc.strip()
                        }
                        try:
                            supabase.table('eqp_roubo_furto').insert(novo_rf).execute()
                            novo_st_master = "Baixado" if st_oc == "Baixado" else "Roubado/Furtado"
                            supabase.table('ativos_master').update({
                                'status_sistema': novo_st_master,
                                'atualizado_em': datetime.now().strftime('%Y-%m-%d')
                            }).eq('patrimonio', pat_r).execute()
                            registrar_log_auditoria(f"OCORRÊNCIA {tipo_oc.upper()}", pat_r, f"ID {id_oc} | Resp: {resp_oc} | B.O.: {num_bo} | Status: {st_oc}")
                            st.session_state["sel_excel_pats_roubo_eqp_sel"] = set()
                            st.cache_data.clear()
                            st.success(f"✅ Ocorrência `{id_oc}` registrada! Equipamento `{pat_r}` bloqueado como `{novo_st_master}`.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar ocorrência: {e}")

        with sub_r3:
            if not df_roubo.empty:
                op_rf = df_roubo.apply(lambda r: f"{r['id_ocorrencia']} | Pat: {r['patrimonio']} | {r['equipamento']} ({r['status']})", axis=1).tolist()
                sel_rf = st.selectbox("Selecione a Ocorrência para Atualizar:", op_rf)
                id_rf_ed = sel_rf.split(" | ")[0]
                reg_rf = df_roubo[df_roubo['id_ocorrencia'] == id_rf_ed].iloc[0].to_dict()

                with st.form("form_ed_roubo"):
                    e1, e2, e3 = st.columns(3)
                    with e1:
                        ed_bo = st.text_input("Nº do B.O.", value=str(reg_rf.get('num_bo', '')))
                        ed_dt_bo = st.text_input("Data do B.O.", value=str(reg_rf.get('data_bo', '')))
                    with e2:
                        ed_anexo = st.text_input("Anexo / Link B.O.", value=str(reg_rf.get('anexo_bo', '')))
                        st_atual_rf = str(reg_rf.get('status', 'Em análise'))
                        ed_st_rf = st.selectbox("Status:", STATUS_ROUBO_FURTO, index=STATUS_ROUBO_FURTO.index(st_atual_rf) if st_atual_rf in STATUS_ROUBO_FURTO else 0)
                    with e3:
                        ed_obs_rf = st.text_area("Observação:", value=str(reg_rf.get('observacao', '')))

                    if st.form_submit_button("💾 Atualizar Ocorrência", type="primary"):
                        dt_bx = datetime.now().strftime('%Y-%m-%d') if ed_st_rf == "Baixado" else str(reg_rf.get('data_baixa', ''))
                        supabase.table('eqp_roubo_furto').update({
                            'num_bo': ed_bo.strip(),
                            'data_bo': ed_dt_bo.strip(),
                            'anexo_bo': ed_anexo.strip(),
                            'status': ed_st_rf,
                            'data_baixa': dt_bx,
                            'observacao': ed_obs_rf.strip()
                        }).eq('id_ocorrencia', id_rf_ed).execute()
                        if ed_st_rf == "Baixado":
                            supabase.table('ativos_master').update({'status_sistema': 'Baixado'}).eq('patrimonio', reg_rf['patrimonio']).execute()
                        registrar_log_auditoria("ATUALIZAÇÃO ROUBO/FURTO", reg_rf['patrimonio'], f"ID {id_rf_ed} -> Status: {ed_st_rf} | B.O.: {ed_bo}")
                        st.cache_data.clear()
                        st.success("✅ Ocorrência atualizada!")
                        st.rerun()
            else:
                st.info("Nenhuma ocorrência para atualizar.")

    # ==========================================================
    # ABA 2: EQUIPAMENTOS SEM GIRO / AGING
    # ==========================================================
    with aba_aging:
        st.markdown("##### ⏳ Monitoramento de Aging (Dias sem Giro) e Segregação para Análise")
        st.caption("Faixas: 🟢 0–90d (Normal) | 🟡 91–180d (Atenção) | 🟠 181–365d (Baixo Giro) | 🔴 >365d (Candidato à Obsolescência/Descarte)")

        sub_a1, sub_a2, sub_a3 = st.tabs([
            "📊 Radar de Aging do Parque (Automático)",
            "📋 Itens em Análise / Segregados sem Giro",
            "➕ Enviar Item sem Giro para Análise"
        ])

        with sub_a1:
            if not df_ativos.empty:
                df_ag = df_ativos[~df_ativos['status_sistema'].astype(str).str.upper().isin(['BAIXADO', 'ROUBADO/FURTADO'])].copy()
                df_ag['Dias sem Giro'] = df_ag['atualizado_em'].apply(lambda d: int(calcular_dias_sem_mov(d)) if str(calcular_dias_sem_mov(d)).isdigit() else 0)
                df_ag['Faixa Aging'] = df_ag['Dias sem Giro'].apply(classificar_faixa_aging)

                a1, a2, a3, a4 = st.columns(4)
                a1.metric("🟢 0 a 90 dias", int((df_ag['Dias sem Giro'] <= 90).sum()))
                a2.metric("🟡 91 a 180 dias", int(((df_ag['Dias sem Giro'] > 90) & (df_ag['Dias sem Giro'] <= 180)).sum()))
                a3.metric("🟠 181 a 365 dias", int(((df_ag['Dias sem Giro'] > 180) & (df_ag['Dias sem Giro'] <= 365)).sum()))
                a4.metric("🔴 > 365 dias", int((df_ag['Dias sem Giro'] > 365).sum()))

                filtro_faixa = st.selectbox("Filtrar por Faixa de Aging:", ["Todas", "🔴 > 365 dias (Candidato Obsolescência/Descarte)", "🟠 181 a 365 dias (Baixo Giro)", "🟡 91 a 180 dias (Atenção)", "🟢 0 a 90 dias (Giro Normal)"])
                if filtro_faixa != "Todas":
                    df_ag = df_ag[df_ag['Faixa Aging'] == filtro_faixa]

                cols_ag = ['Faixa Aging', 'Dias sem Giro', 'patrimonio', 'equipamento', 'marca', 'modelo', 'numero_serie', 'coordenacao', 'cautela', 'atualizado_em', 'status_sistema']
                st.dataframe(df_ag[[c for c in cols_ag if c in df_ag.columns]].sort_values(by='Dias sem Giro', ascending=False), use_container_width=True, hide_index=True, height=350)
            else:
                st.info("Base de equipamentos vazia.")

        with sub_a2:
            if not df_sem_giro.empty:
                st.dataframe(df_sem_giro, use_container_width=True, hide_index=True, height=280)
                st.download_button(
                    "📥 Exportar Sem Giro (.xlsx)",
                    data=converter_df_excel_simples(df_sem_giro, "Sem_Giro"),
                    file_name=f"Equipamentos_Sem_Giro_{datetime.now().strftime('%Y%m%d')}.xlsx"
                )
                st.divider()
                op_sg = df_sem_giro.apply(lambda r: f"{r['id_registro']} | Pat: {r['patrimonio']} | {r['equipamento']} ({r['status']})", axis=1).tolist()
                sel_sg = st.selectbox("Atualizar Andamento / Aprovação de Item sem Giro:", op_sg)
                id_sg_ed = sel_sg.split(" | ")[0]
                reg_sg = df_sem_giro[df_sem_giro['id_registro'] == id_sg_ed].iloc[0].to_dict()

                with st.form("form_ed_sem_giro"):
                    sg1, sg2, sg3 = st.columns(3)
                    with sg1:
                        st_sg_at = str(reg_sg.get('status', 'Em análise'))
                        ed_st_sg = st.selectbox("Status:", STATUS_SEM_GIRO, index=STATUS_SEM_GIRO.index(st_sg_at) if st_sg_at in STATUS_SEM_GIRO else 0)
                    with sg2:
                        ap_sg_at = str(reg_sg.get('aprovacao', 'Pendente'))
                        op_ap = ["Pendente", "Aprovado", "Reprovado"]
                        ed_ap_sg = st.selectbox("Aprovação:", op_ap, index=op_ap.index(ap_sg_at) if ap_sg_at in op_ap else 0)
                    with sg3:
                        ed_obs_sg = st.text_input("Observação / Justificativa:", value=str(reg_sg.get('observacao', '')))

                    if st.form_submit_button("💾 Atualizar Análise de Sem Giro", type="primary"):
                        hoje_s = datetime.now().strftime('%Y-%m-%d')
                        supabase.table('eqp_sem_giro').update({
                            'status': ed_st_sg,
                            'aprovacao': ed_ap_sg,
                            'data_aprovacao': hoje_s if ed_ap_sg != "Pendente" else "",
                            'data_baixa': hoje_s if ed_st_sg == "Baixado" else "",
                            'observacao': ed_obs_sg.strip()
                        }).eq('id_registro', id_sg_ed).execute()
                        if ed_st_sg == "Baixado":
                            supabase.table('ativos_master').update({'status_sistema': 'Baixado'}).eq('patrimonio', reg_sg['patrimonio']).execute()
                        registrar_log_auditoria("ANÁLISE SEM GIRO", reg_sg['patrimonio'], f"ID {id_sg_ed} -> Status: {ed_st_sg} | Aprovação: {ed_ap_sg}")
                        st.cache_data.clear()
                        st.success("✅ Registro atualizado!")
                        st.rerun()
            else:
                st.info("Nenhum equipamento enviado para análise de sem giro ainda.")

        with sub_a3:
            ativos_sg = df_ativos[~df_ativos['status_sistema'].astype(str).str.upper().isin(['BAIXADO', 'ROUBADO/FURTADO'])].copy() if not df_ativos.empty else pd.DataFrame()
            df_sel_sg = operacao.render_seletor_excel_equipamentos(ativos_sg, "sem_giro_sel", multiplo=False, altura=180)
            if not df_sel_sg.empty:
                r_sg = df_sel_sg.iloc[0].to_dict()
                dias_calc = calcular_dias_sem_mov(r_sg.get('atualizado_em', ''))
                faixa_calc = classificar_faixa_aging(dias_calc)
                st.info(f"⏳ **Aging Calculado:** {dias_calc} dias sem movimentação — **{faixa_calc}**")

                with st.form("form_cad_sem_giro"):
                    g1, g2, g3 = st.columns(3)
                    with g1:
                        mot_sg = st.text_input("Motivo da Segregação *", value="Sem giro prolongado")
                        cond_sg = st.selectbox("Condição:", ["Novo", "Usado", "Avariado", "Obsoleto"], index=1)
                    with g2:
                        dest_sg = st.selectbox("Destinação Proposta:", ["Reutilização", "Transferência", "Manutenção", "Descarte"])
                        resp_sg = st.text_input("Responsável pela Análise *", value=st.session_state.get('nome_real', ''))
                    with g3:
                        obs_sg = st.text_area("Observação / Evidência:")

                    if st.form_submit_button("💾 Registrar em Sem Giro / Análise", type="primary"):
                        id_sg = f"SG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        supabase.table('eqp_sem_giro').insert({
                            'id_registro': id_sg,
                            'equipamento': str(r_sg.get('equipamento', '')),
                            'marca_modelo': f"{r_sg.get('marca', '')} {r_sg.get('modelo', '')}".strip(),
                            'numero_serie': str(r_sg.get('numero_serie', '')),
                            'patrimonio': str(r_sg.get('patrimonio', '')),
                            'base': str(r_sg.get('coordenacao', '')),
                            'data_ultima_mov': str(r_sg.get('atualizado_em', '')),
                            'dias_sem_giro': str(dias_calc),
                            'faixa_aging': faixa_calc,
                            'motivo_segregacao': mot_sg.strip(),
                            'condicao': cond_sg,
                            'destinacao_proposta': dest_sg,
                            'data_segregacao': datetime.now().strftime('%Y-%m-%d'),
                            'responsavel': resp_sg.strip(),
                            'aprovacao': 'Pendente',
                            'data_aprovacao': '',
                            'status': 'Em análise',
                            'data_baixa': '',
                            'observacao': obs_sg.strip()
                        }).execute()
                        registrar_log_auditoria("SEGREGAÇÃO SEM GIRO", r_sg['patrimonio'], f"ID {id_sg} | {dias_calc} dias | Destinação: {dest_sg}")
                        st.session_state["sel_excel_pats_sem_giro_sel"] = set()
                        st.cache_data.clear()
                        st.success(f"✅ Equipamento `{r_sg['patrimonio']}` registrado na fila de Sem Giro!")
                        st.rerun()

    # ==========================================================
    # ABA 3: EQUIPAMENTOS SEGREGADOS PARA DESCARTE
    # ==========================================================
    with aba_descarte:
        st.markdown("##### 🗑️ Controle de Equipamentos Segregados para Descarte")
        st.caption("Fluxo: `Identificado -> Segregado -> Em avaliação -> Aguardando aprovação -> Aprovado para descarte -> Descartado -> Baixado`. Bloqueio automático de movimentação e exigência de evidência.")

        sub_d1, sub_d2, sub_d3 = st.tabs([
            "📋 Base de Segregados / Descarte (Histórico Permanente)",
            "➕ Segregar Equipamento para Descarte",
            "⚖️ Avaliar, Aprovar, Descartar ou Reverter"
        ])

        with sub_d1:
            if not df_descarte.empty:
                st.dataframe(df_descarte, use_container_width=True, hide_index=True, height=380)
                st.download_button(
                    "📥 Exportar Segregados para Descarte (.xlsx)",
                    data=converter_df_excel_simples(df_descarte, "Segregados_Descarte"),
                    file_name=f"Equipamentos_Descarte_{datetime.now().strftime('%Y%m%d')}.xlsx"
                )
            else:
                st.info("Nenhum equipamento segregado para descarte.")

        with sub_d2:
            ativos_desc = df_ativos[~df_ativos['status_sistema'].astype(str).str.upper().isin(['SEGREGADO PARA DESCARTE', 'BAIXADO', 'ROUBADO/FURTADO'])].copy() if not df_ativos.empty else pd.DataFrame()
            st.markdown("###### 1️⃣ Selecione o equipamento para retirar de operação e segregar fisicamente:")
            df_sel_d = operacao.render_seletor_excel_equipamentos(ativos_desc, "descarte_eqp_sel", multiplo=False, altura=180)

            if not df_sel_d.empty:
                r_d = df_sel_d.iloc[0].to_dict()
                pat_d = str(r_d['patrimonio']).strip()
                with st.form("form_segregar_descarte"):
                    d1, d2, d3 = st.columns(3)
                    with d1:
                        base_d = st.text_input("Base Responsável *", value=str(r_d.get('coordenacao', '')))
                        loc_fis_d = st.text_input("Localização Física da Segregação *", value="ÁREA DE SEGREGADOS / DESCARTE")
                        est_cons = st.selectbox("Estado de Conservação *", ["Inservível", "Ruim", "Regular", "Bom"])
                    with d2:
                        mot_d = st.selectbox("Motivo da Segregação *", MOTIVOS_SEGREGACAO_DESCARTE)
                        dest_d = st.selectbox("Destinação Proposta *", ["Descarte", "Sucata", "Reciclagem", "Devolução"])
                        resp_av_d = st.text_input("Responsável pela Segregação / Avaliação *", value=st.session_state.get('nome_real', ''))
                    with d3:
                        evid_d = st.text_input("Evidência (Link Foto / Laudo Técnico) *")
                        obs_d = st.text_area("Justificativa / Observações (Obrigatório se 'Outro'):")

                    if st.form_submit_button("🔒 Segregar Equipamento e Bloquear Movimentação", type="primary"):
                        if mot_d.startswith("Outro") and not obs_d.strip():
                            st.error("Para o motivo 'Outro', é obrigatório preencher a justificativa em Observações.")
                        else:
                            id_desc = f"DSC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            hoje_s = datetime.now().strftime('%Y-%m-%d')
                            supabase.table('eqp_descarte').insert({
                                'id_registro': id_desc,
                                'data_segregacao': hoje_s,
                                'base': base_d.strip(),
                                'localizacao_fisica': loc_fis_d.strip(),
                                'tipo_equipamento': str(r_d.get('equipamento', '')),
                                'marca': str(r_d.get('marca', '')),
                                'modelo': str(r_d.get('modelo', '')),
                                'numero_serie': str(r_d.get('numero_serie', '')),
                                'patrimonio': pat_d,
                                'estado_conservacao': est_cons,
                                'motivo_segregacao': mot_d,
                                'destinacao_proposta': dest_d,
                                'data_avaliacao': hoje_s,
                                'responsavel_avaliacao': resp_av_d.strip(),
                                'evidencia': evid_d.strip(),
                                'aprovacao_descarte': 'Pendente',
                                'aprovador': '',
                                'data_aprovacao': '',
                                'status': 'Segregado',
                                'data_descarte': '',
                                'comprovante': '',
                                'data_baixa': '',
                                'observacoes': obs_d.strip()
                            }).execute()
                            # Bloqueio imediato na base principal (sem baixar ainda!)
                            supabase.table('ativos_master').update({
                                'status_sistema': 'Segregado para Descarte',
                                'cautela': loc_fis_d.strip(),
                                'atualizado_em': hoje_s
                            }).eq('patrimonio', pat_d).execute()
                            registrar_log_auditoria("SEGREGADO P/ DESCARTE", pat_d, f"ID {id_desc} | Motivo: {mot_d} | Bloqueado para operação.")
                            st.session_state["sel_excel_pats_descarte_eqp_sel"] = set()
                            st.cache_data.clear()
                            st.success(f"✅ Equipamento `{pat_d}` segregado (`{id_desc}`) e bloqueado para movimentação operacional!")
                            st.rerun()

        with sub_d3:
            if not df_descarte.empty:
                op_ds = df_descarte.apply(lambda r: f"{r['id_registro']} | Pat: {r['patrimonio']} | {r['tipo_equipamento']} ({r['status']})", axis=1).tolist()
                sel_ds = st.selectbox("Selecione o Processo de Descarte para Avançar / Decidir:", op_ds)
                id_ds_ed = sel_ds.split(" | ")[0]
                reg_ds = df_descarte[df_descarte['id_registro'] == id_ds_ed].iloc[0].to_dict()

                with st.form("form_fluxo_descarte"):
                    f1, f2, f3 = st.columns(3)
                    with f1:
                        st_at_d = str(reg_ds.get('status', 'Segregado'))
                        novo_st_d = st.selectbox("Etapa / Status do Processo:", STATUS_FLUXO_DESCARTE, index=STATUS_FLUXO_DESCARTE.index(st_at_d) if st_at_d in STATUS_FLUXO_DESCARTE else 1)
                        ap_at_d = str(reg_ds.get('aprovacao_descarte', 'Pendente'))
                        op_apd = ["Pendente", "Aprovado", "Reprovado"]
                        nova_ap_d = st.selectbox("Aprovação do Descarte:", op_apd, index=op_apd.index(ap_at_d) if ap_at_d in op_apd else 0)
                        aprovador_d = st.text_input("Aprovador:", value=str(reg_ds.get('aprovador', '')) or st.session_state.get('nome_real', ''))
                    with f2:
                        evid_ed = st.text_input("Evidência (Foto / Laudo Técnico) *:", value=str(reg_ds.get('evidencia', '')))
                        comp_ed = st.text_input("Comprovante de Descarte (MTR / Recibo):", value=str(reg_ds.get('comprovante', '')))
                    with f3:
                        obs_ed_d = st.text_area("Observações / Histórico:", value=str(reg_ds.get('observacoes', '')))

                    if st.form_submit_button("💾 Atualizar Etapa do Descarte", type="primary"):
                        # Controle 2: Evidência obrigatória antes de avançar para Aprovado / Descartado / Baixado
                        etapas_criticas = ["Aprovado para descarte", "Descartado", "Baixado"]
                        if novo_st_d in etapas_criticas:
                            if not evid_ed.strip() or nova_ap_d != "Aprovado" or not aprovador_d.strip():
                                st.error("⛔ Bloqueio de Governança: Para avançar para Aprovado/Descartado/Baixado, é obrigatório informar Evidência (Foto/Laudo), Aprovação = 'Aprovado' e o nome do Aprovador.")
                                st.stop()

                        hoje_s = datetime.now().strftime('%Y-%m-%d')
                        upd_ds = {
                            'status': novo_st_d,
                            'aprovacao_descarte': nova_ap_d,
                            'aprovador': aprovador_d.strip(),
                            'evidencia': evid_ed.strip(),
                            'comprovante': comp_ed.strip(),
                            'observacoes': obs_ed_d.strip()
                        }
                        if nova_ap_d in ["Aprovado", "Reprovado"] and not reg_ds.get('data_aprovacao'):
                            upd_ds['data_aprovacao'] = hoje_s
                        if novo_st_d == "Descartado" and not reg_ds.get('data_descarte'):
                            upd_ds['data_descarte'] = hoje_s
                        if novo_st_d == "Baixado":
                            upd_ds['data_baixa'] = hoje_s

                        supabase.table('eqp_descarte').update(upd_ds).eq('id_registro', id_ds_ed).execute()

                        # Sincroniza status com ativos_master sem excluir o histórico (Rastreabilidade)
                        if novo_st_d == "Baixado":
                            supabase.table('ativos_master').update({'status_sistema': 'Baixado', 'atualizado_em': hoje_s}).eq('patrimonio', reg_ds['patrimonio']).execute()
                        elif novo_st_d.startswith("Reaproveitamento aprovado"):
                            supabase.table('ativos_master').update({'status_sistema': 'Disponível', 'cautela': 'ALMOXARIFADO CENTRAL', 'atualizado_em': hoje_s}).eq('patrimonio', reg_ds['patrimonio']).execute()

                        registrar_log_auditoria("FLUXO DESCARTE", reg_ds['patrimonio'], f"ID {id_ds_ed} -> {novo_st_d} | Aprovação: {nova_ap_d} ({aprovador_d})")
                        st.cache_data.clear()
                        st.success(f"✅ Processo `{id_ds_ed}` atualizado para `{novo_st_d}`!")
                        st.rerun()
            else:
                st.info("Nenhum processo de descarte registrado.")

    exibir_marca_desenvolvedor()
