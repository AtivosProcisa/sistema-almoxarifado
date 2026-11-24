import base64
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
normalizar_perfil = getattr(nuvem, 'normalizar_perfil', lambda p: p)
obter_permissao = getattr(nuvem, 'obter_permissao', lambda acao: True)

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

STATUS_FLUXO_DESCARTE_SUPERVISOR = [
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

STATUS_FLUXO_DESCARTE_ARMAZENISTA = [
    "Identificado para descarte",
    "Segregado",
    "Em avaliação",
    "Aguardando aprovação"
]

STATUS_ROUBO_FURTO_SUPERVISOR = [
    "Em análise",
    "B.O. realizado",
    "Baixa solicitada",
    "Baixado"
]

STATUS_ROUBO_FURTO_ARMAZENISTA = [
    "Em análise",
    "B.O. realizado",
    "Baixa solicitada"
]

STATUS_SEM_GIRO_SUPERVISOR = [
    "Sem giro",
    "Em análise",
    "Reaproveitar / Transferir",
    "Descartar",
    "Aprovado para descarte",
    "Baixado"
]

STATUS_SEM_GIRO_ARMAZENISTA = [
    "Sem giro",
    "Em análise",
    "Reaproveitar / Transferir",
    "Descartar"
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

def _codificar_anexo_bo(arquivo_up):
    if arquivo_up is None:
        return ""
    conteudo = arquivo_up.getvalue()
    if len(conteudo) > 4 * 1024 * 1024:
        st.warning("⚠️ O arquivo excede 4 MB. Envie um PDF/imagem mais leve ou informe um link externo (OneDrive).")
        return ""
    b64 = base64.b64encode(conteudo).decode("utf-8")
    nome_limpo = str(arquivo_up.name).replace("|", "_")
    mime = arquivo_up.type or "application/octet-stream"
    return f"B64|{nome_limpo}|{mime}|{b64}"

def _resumir_anexo_tabela(val):
    txt = str(val or "").strip()
    if txt.startswith("B64|"):
        partes = txt.split("|", 3)
        if len(partes) >= 2:
            return f"📎 {partes[1]}"
    return txt

def _extrair_anexo_download(val):
    txt = str(val or "").strip()
    if txt.startswith("B64|"):
        partes = txt.split("|", 3)
        if len(partes) == 4:
            try:
                return partes[1], partes[2], base64.b64decode(partes[3])
            except Exception:
                return None, None, None
    return None, None, None

def _extrair_link_externo(val):
    txt = str(val or "").strip()
    if not txt or txt.startswith("B64|"):
        return None
    if txt.lower().startswith(("http://", "https://")):
        return txt
    if "." in txt and " " not in txt:
        return f"https://{txt}"
    return None

def _gerar_diff_auditoria(reg_antigo, novos_dados, ignorar=None):
    ignorar_set = set(ignorar or [])
    mudancas = []
    for k, v_novo in novos_dados.items():
        if k in ignorar_set:
            continue
        v_ant = str(reg_antigo.get(k, '') or '').strip()
        v_n = str(v_novo or '').strip()
        if k == 'anexo_bo':
            v_ant_ex = _resumir_anexo_tabela(v_ant)
            v_n_ex = _resumir_anexo_tabela(v_n)
            if v_ant != v_n:
                mudancas.append(f"{k}: '{v_ant_ex}' -> '{v_n_ex}'")
        elif v_ant != v_n:
            mudancas.append(f"{k}: '{v_ant}' -> '{v_n}'")
    return mudancas

def render_modulo_governanca_eqp(df_ativos, df_roubo, df_sem_giro, df_descarte):
    perfil_atual = normalizar_perfil(st.session_state.get('perfil', ''))
    is_supervisor = (perfil_atual == "Supervisor")
    is_operacao = (perfil_atual == "Operação Procisa")

    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)

    # ==========================================================
    # MODO RESTRITO: OPERAÇÃO PROCISA (SOMENTE COMUNICAÇÃO DE ROUBO/FURTO E CONSULTA)
    # ==========================================================
    if is_operacao:
        st.subheader("🚨 Comunicar Roubo / Furto (Operação Procisa)")
        st.caption("Utilize este canal para comunicar imediatamente ocorrências de roubo ou furto. O Almoxarifado e o Supervisor serão notificados para conferência e tratativa.")

        aba_com, aba_minhas = st.tabs(["➕ Comunicar Ocorrência", "📋 Minhas Comunicações"])
        with aba_com:
            ativos_eleg = df_ativos[~df_ativos['status_sistema'].astype(str).str.upper().isin(['ROUBADO/FURTADO', 'BAIXADO', 'INATIVADO'])].copy() if not df_ativos.empty else pd.DataFrame()
            df_sel_op = operacao.render_seletor_excel_equipamentos(ativos_eleg, "roubo_op_comunicar", multiplo=False, altura=180)
            if not df_sel_op.empty:
                r_op = df_sel_op.iloc[0].to_dict()
                pat_op = str(r_op['patrimonio']).strip()
                with st.form("form_comunicar_roubo_op"):
                    c1, c2 = st.columns(2)
                    with c1:
                        tipo_op = st.selectbox("Tipo de Ocorrência *", ["Roubo", "Furto"])
                        dt_op = st.date_input("Data da Ocorrência *", datetime.today())
                        resp_op = st.text_input("Responsável na Ocorrência *", value=st.session_state.get('nome_real', ''))
                    with c2:
                        num_bo_op = st.text_input("Nº do B.O. (se já possuir)")
                        link_bo_op = st.text_input("Link do B.O. no OneDrive (Opcional)")
                        obs_op = st.text_area("Relato / Motivo Obrigatório *:")

                    if st.form_submit_button("🚨 Enviar Comunicação ao Almoxarifado", type="primary"):
                        if not obs_op.strip():
                            st.error("⛔ O relato / motivo da ocorrência é obrigatório.")
                        else:
                            id_oc = f"RF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            supabase.table('eqp_roubo_furto').insert({
                                'id_ocorrencia': id_oc,
                                'equipamento': str(r_op.get('equipamento', '')),
                                'fabricante_modelo': f"{r_op.get('marca', '')} {r_op.get('modelo', '')}".strip(),
                                'numero_serie': str(r_op.get('numero_serie', '')),
                                'patrimonio': pat_op,
                                'base_localizacao': str(r_op.get('coordenacao', '')),
                                'responsavel': resp_op.strip(),
                                'data_ocorrencia': dt_op.strftime('%Y-%m-%d'),
                                'tipo': tipo_op,
                                'num_bo': num_bo_op.strip(),
                                'data_bo': '',
                                'anexo_bo': link_bo_op.strip(),
                                'status': 'Em análise',
                                'data_baixa': '',
                                'observacao': f"[Comunicado por {st.session_state.get('nome_real', '')}] {obs_op.strip()}"
                            }).execute()
                            registrar_log_auditoria(f"COMUNICAÇÃO {tipo_op.upper()}", pat_op, f"ID {id_oc} | Comunicado pela Operação. Relato: {obs_op.strip()}")
                            st.session_state["sel_excel_pats_roubo_op_comunicar"] = set()
                            st.cache_data.clear()
                            st.success(f"✅ Comunicação `{id_oc}` enviada ao Almoxarifado e Supervisor!")
                            st.rerun()

        with aba_minhas:
            if not df_roubo.empty:
                nome_u = str(st.session_state.get('nome_real', '')).strip().upper()
                df_minhas_rf = df_roubo[
                    df_roubo['responsavel'].astype(str).str.upper().str.contains(nome_u, regex=False, na=False) |
                    df_roubo['observacao'].astype(str).str.upper().str.contains(nome_u, regex=False, na=False)
                ]
                st.dataframe(df_minhas_rf[['id_ocorrencia', 'patrimonio', 'equipamento', 'data_ocorrencia', 'tipo', 'num_bo', 'status', 'observacao']], use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma comunicação registrada.")
        exibir_marca_desenvolvedor()
        return

    # ==========================================================
    # VISÃO SUPERVISOR E ARMAZENISTA
    # ==========================================================
    st.subheader(f"🚨 Governança de Ativos — Roubo/Furto, Sem Giro e Descarte ({perfil_atual})")
    if is_supervisor:
        st.caption("Nível Supervisor: controle total, aprovação de baixas/descartes e auditoria completa.")
    else:
        st.caption("Nível Armazenista: preenchimento operacional, segregação e envio para aprovação. Baixas definitivas e aprovações finais são exclusivas do Supervisor.")

    aba_roubo, aba_aging, aba_descarte = st.tabs([
        f"🚨 Roubados / Furtados ({len(df_roubo)})",
        f"⏳ Sem Giro / Aging ({len(df_sem_giro)})",
        f"🗑️ Segregados para Descarte ({len(df_descarte)})"
    ])

    # ==========================================================
    # ABA 1: EQUIPAMENTOS ROUBADOS / FURTADOS
    # ==========================================================
    with aba_roubo:
        sub_r1, sub_r2, sub_r3 = st.tabs([
            "📋 Histórico de Ocorrências",
            "➕ Registrar Nova Ocorrência",
            "✏️ Editar / Atualizar Ocorrência"
        ])

        with sub_r1:
            if not df_roubo.empty:
                df_roubo_view = df_roubo.copy()
                if 'anexo_bo' in df_roubo_view.columns:
                    links_series = df_roubo_view['anexo_bo'].apply(_extrair_link_externo)
                    df_roubo_view['anexo_bo'] = df_roubo_view['anexo_bo'].apply(
                        lambda v: _resumir_anexo_tabela(v) if str(v or "").startswith("B64|") else ""
                    )
                    pos_bo = df_roubo_view.columns.get_loc('num_bo') + 1 if 'num_bo' in df_roubo_view.columns else 0
                    df_roubo_view.insert(pos_bo, 'link_direto', links_series)

                st.dataframe(
                    df_roubo_view,
                    use_container_width=True,
                    hide_index=True,
                    height=340,
                    column_config={
                        "link_direto": st.column_config.LinkColumn("Link B.O.", display_text="🔗 Abrir Link"),
                        "anexo_bo": st.column_config.TextColumn("Arquivo Anexado")
                    }
                )

                col_dl1, col_dl2 = st.columns([2, 1])
                with col_dl1:
                    com_evidencia = df_roubo[df_roubo['anexo_bo'].astype(str).str.strip() != ""] if 'anexo_bo' in df_roubo.columns else pd.DataFrame()
                    if not com_evidencia.empty:
                        op_anexos = com_evidencia.apply(lambda r: f"{r['id_ocorrencia']} | Pat: {r['patrimonio']} | B.O.: {r['num_bo']}", axis=1).tolist()
                        sel_anexo = st.selectbox("📎 Acessar / Baixar B.O.:", op_anexos, key="sel_dl_bo")
                        id_sel_dl = sel_anexo.split(" | ")[0]
                        raw_anexo = com_evidencia[com_evidencia['id_ocorrencia'] == id_sel_dl].iloc[0]['anexo_bo']

                        if str(raw_anexo).startswith("B64|"):
                            nome_arq, mime_arq, bytes_arq = _extrair_anexo_download(raw_anexo)
                            if bytes_arq:
                                st.download_button(f"📥 Baixar Arquivo ({nome_arq})", data=bytes_arq, file_name=nome_arq, mime=mime_arq, type="primary")
                        else:
                            url_bo = _extrair_link_externo(raw_anexo)
                            if url_bo:
                                st.link_button("🔗 Abrir Link Externo do B.O.", url_bo, type="primary")
                with col_dl2:
                    st.write("")
                    st.download_button(
                        "📥 Exportar Tabela (.xlsx)",
                        data=converter_df_excel_simples(df_roubo_view, "Roubo_Furto"),
                        file_name=f"Equipamentos_Roubo_Furto_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        use_container_width=True
                    )
            else:
                st.info("Nenhuma ocorrência de roubo ou furto registrada.")

        with sub_r2:
            ativos_elegiveis = df_ativos[~df_ativos['status_sistema'].astype(str).str.upper().isin(['ROUBADO/FURTADO', 'BAIXADO', 'INATIVADO'])].copy() if not df_ativos.empty else pd.DataFrame()
            df_sel_r = operacao.render_seletor_excel_equipamentos(ativos_elegiveis, "roubo_eqp_sel", multiplo=False, altura=180)

            if not df_sel_r.empty:
                r_at = df_sel_r.iloc[0].to_dict()
                pat_r = str(r_at['patrimonio']).strip()
                op_st_rf = STATUS_ROUBO_FURTO_SUPERVISOR if is_supervisor else STATUS_ROUBO_FURTO_ARMAZENISTA

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
                        arq_bo_up = st.file_uploader("📎 Anexar B.O. (PDF, JPG ou PNG - máx. 4 MB)", type=["pdf", "png", "jpg", "jpeg"], key="up_bo_novo")
                        link_bo = st.text_input("Ou Link Externo do B.O. (OneDrive / SharePoint)")
                    with c3:
                        st_oc = st.selectbox("Status da Ocorrência *", op_st_rf, index=0)
                        obs_oc = st.text_area("Relato / Motivo Obrigatório *:")

                    if st.form_submit_button("🚨 Registrar Ocorrência e Bloquear Equipamento", type="primary"):
                        if not obs_oc.strip():
                            st.error("⛔ Controle Especial: É obrigatório preencher o Relato / Motivo da ocorrência.")
                        else:
                            id_oc = f"RF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            anexo_final = _codificar_anexo_bo(arq_bo_up) if arq_bo_up is not None else link_bo.strip()
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
                                'anexo_bo': anexo_final,
                                'status': st_oc,
                                'data_baixa': datetime.now().strftime('%Y-%m-%d') if (st_oc == "Baixado" and is_supervisor) else "",
                                'observacao': obs_oc.strip()
                            }
                            try:
                                supabase.table('eqp_roubo_furto').insert(novo_rf).execute()
                                novo_st_master = "Baixado" if (st_oc == "Baixado" and is_supervisor) else "Roubado/Furtado"
                                supabase.table('ativos_master').update({
                                    'status_sistema': novo_st_master,
                                    'atualizado_em': datetime.now().strftime('%Y-%m-%d')
                                }).eq('patrimonio', pat_r).execute()
                                registrar_log_auditoria(f"OCORRÊNCIA {tipo_oc.upper()}", pat_r, f"ID {id_oc} | Resp: {resp_oc} | B.O.: {num_bo} | Status: {st_oc} | Motivo: {obs_oc.strip()}")
                                st.session_state["sel_excel_pats_roubo_eqp_sel"] = set()
                                st.cache_data.clear()
                                st.success(f"✅ Ocorrência `{id_oc}` registrada! Equipamento `{pat_r}` bloqueado como `{novo_st_master}`.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar ocorrência: {e}")

        with sub_r3:
            if not df_roubo.empty:
                op_rf = df_roubo.apply(lambda r: f"{r['id_ocorrencia']} | Pat: {r['patrimonio']} | {r['equipamento']} ({r['status']})", axis=1).tolist()
                sel_rf = st.selectbox("Selecione a Ocorrência para Editar:", op_rf, key="sel_ed_rf")
                id_rf_ed = sel_rf.split(" | ")[0]
                reg_rf = df_roubo[df_roubo['id_ocorrencia'] == id_rf_ed].iloc[0].to_dict()

                op_st_rf_ed = STATUS_ROUBO_FURTO_SUPERVISOR if is_supervisor else STATUS_ROUBO_FURTO_ARMAZENISTA
                st_atual_rf = str(reg_rf.get('status', 'Em análise'))
                if st_atual_rf not in op_st_rf_ed:
                    op_st_rf_ed = op_st_rf_ed + [st_atual_rf]

                with st.form(f"form_ed_roubo_{id_rf_ed}"):
                    e1, e2, e3 = st.columns(3)
                    with e1:
                        op_tipo_rf = ["Roubo", "Furto"]
                        tp_at_rf = str(reg_rf.get('tipo', 'Roubo'))
                        ed_tipo_rf = st.selectbox("Tipo de Ocorrência:", op_tipo_rf, index=op_tipo_rf.index(tp_at_rf) if tp_at_rf in op_tipo_rf else 0)
                        ed_dt_oc = st.text_input("Data da Ocorrência (AAAA-MM-DD):", value=str(reg_rf.get('data_ocorrencia', '')))
                        ed_resp_rf = st.text_input("Responsável na Ocorrência:", value=str(reg_rf.get('responsavel', '')))
                        ed_base_rf = st.text_input("Base / Localização:", value=str(reg_rf.get('base_localizacao', '')))
                    with e2:
                        ed_bo = st.text_input("Nº do B.O.", value=str(reg_rf.get('num_bo', '')))
                        ed_dt_bo = st.text_input("Data do B.O.", value=str(reg_rf.get('data_bo', '')))
                        ed_arq_bo = st.file_uploader("📎 Anexar / Substituir B.O.", type=["pdf", "png", "jpg", "jpeg"], key=f"up_bo_edit_{id_rf_ed}")
                        ed_link_bo = st.text_input("Ou Link Externo B.O. (OneDrive)", value="" if str(reg_rf.get('anexo_bo', '')).startswith("B64|") else str(reg_rf.get('anexo_bo', '')))
                    with e3:
                        ed_st_rf = st.selectbox("Status:", op_st_rf_ed, index=op_st_rf_ed.index(st_atual_rf))
                        ed_dt_bx = st.text_input("Data da Baixa (AAAA-MM-DD):", value=str(reg_rf.get('data_baixa', '')), disabled=not is_supervisor)
                        ed_obs_rf = st.text_area("Observação / Motivo:", value=str(reg_rf.get('observacao', '')))

                    if st.form_submit_button("💾 Salvar Edição da Ocorrência", type="primary"):
                        if (not is_supervisor) and ed_st_rf == "Baixado" and st_atual_rf != "Baixado":
                            st.error("⛔ Apenas o Supervisor pode concluir a baixa definitiva de equipamento roubado/furtado.")
                            st.stop()

                        dt_bx_final = ed_dt_bx.strip()
                        if ed_st_rf == "Baixado" and not dt_bx_final:
                            dt_bx_final = datetime.now().strftime('%Y-%m-%d')

                        if ed_arq_bo is not None:
                            anexo_upd = _codificar_anexo_bo(ed_arq_bo)
                        elif ed_link_bo.strip():
                            anexo_upd = ed_link_bo.strip()
                        else:
                            anexo_upd = str(reg_rf.get('anexo_bo', ''))

                        novos_rf = {
                            'tipo': ed_tipo_rf,
                            'data_ocorrencia': ed_dt_oc.strip(),
                            'responsavel': ed_resp_rf.strip(),
                            'base_localizacao': ed_base_rf.strip(),
                            'num_bo': ed_bo.strip(),
                            'data_bo': ed_dt_bo.strip(),
                            'anexo_bo': anexo_upd,
                            'status': ed_st_rf,
                            'data_baixa': dt_bx_final,
                            'observacao': ed_obs_rf.strip()
                        }

                        mudancas = _gerar_diff_auditoria(reg_rf, novos_rf)
                        if not mudancas:
                            st.warning("Nenhuma alteração foi feita nos campos.")
                        else:
                            supabase.table('eqp_roubo_furto').update(novos_rf).eq('id_ocorrencia', id_rf_ed).execute()
                            novo_st_m = 'Baixado' if ed_st_rf == "Baixado" else 'Roubado/Furtado'
                            supabase.table('ativos_master').update({'status_sistema': novo_st_m, 'atualizado_em': datetime.now().strftime('%Y-%m-%d')}).eq('patrimonio', reg_rf['patrimonio']).execute()
                            registrar_log_auditoria("EDIÇÃO ROUBO/FURTO", reg_rf['patrimonio'], f"ID {id_rf_ed} | " + " | ".join(mudancas))
                            st.cache_data.clear()
                            st.success(f"✅ Ocorrência `{id_rf_ed}` atualizada!")
                            st.rerun()
            else:
                st.info("Nenhuma ocorrência para editar.")

    # ==========================================================
    # ABA 2: EQUIPAMENTOS SEM GIRO / AGING
    # ==========================================================
    with aba_aging:
        sub_a1, sub_a2, sub_a3, sub_a4 = st.tabs([
            "📊 Radar de Aging do Parque",
            "📋 Itens em Análise / Segregados sem Giro",
            "➕ Enviar Item sem Giro para Análise",
            "✏️ Editar / Atualizar Registro"
        ])

        with sub_a1:
            if not df_ativos.empty:
                df_ag = df_ativos[~df_ativos['status_sistema'].astype(str).str.upper().isin(['BAIXADO', 'ROUBADO/FURTADO', 'INATIVADO'])].copy()
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
                st.dataframe(df_sem_giro, use_container_width=True, hide_index=True, height=340)
                st.download_button("📥 Exportar Sem Giro (.xlsx)", data=converter_df_excel_simples(df_sem_giro, "Sem_Giro"), file_name=f"Equipamentos_Sem_Giro_{datetime.now().strftime('%Y%m%d')}.xlsx")
            else:
                st.info("Nenhum equipamento enviado para análise de sem giro ainda.")

        with sub_a3:
            ativos_sg = df_ativos[~df_ativos['status_sistema'].astype(str).str.upper().isin(['BAIXADO', 'ROUBADO/FURTADO', 'INATIVADO'])].copy() if not df_ativos.empty else pd.DataFrame()
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

        with sub_a4:
            if not df_sem_giro.empty:
                op_sg = df_sem_giro.apply(lambda r: f"{r['id_registro']} | Pat: {r['patrimonio']} | {r['equipamento']} ({r['status']})", axis=1).tolist()
                sel_sg = st.selectbox("Selecione o Registro de Sem Giro para Editar:", op_sg, key="sel_ed_sg")
                id_sg_ed = sel_sg.split(" | ")[0]
                reg_sg = df_sem_giro[df_sem_giro['id_registro'] == id_sg_ed].iloc[0].to_dict()

                op_st_sg = STATUS_SEM_GIRO_SUPERVISOR if is_supervisor else STATUS_SEM_GIRO_ARMAZENISTA
                st_sg_at = str(reg_sg.get('status', 'Em análise'))
                if st_sg_at not in op_st_sg:
                    op_st_sg = op_st_sg + [st_sg_at]

                with st.form(f"form_ed_sem_giro_{id_sg_ed}"):
                    sg1, sg2, sg3 = st.columns(3)
                    with sg1:
                        ed_base_sg = st.text_input("Base:", value=str(reg_sg.get('base', '')))
                        ed_mot_sg = st.text_input("Motivo da Segregação:", value=str(reg_sg.get('motivo_segregacao', '')))
                        op_cond_sg = ["Novo", "Usado", "Avariado", "Obsoleto"]
                        cd_sg_at = str(reg_sg.get('condicao', 'Usado'))
                        ed_cond_sg = st.selectbox("Condição:", op_cond_sg, index=op_cond_sg.index(cd_sg_at) if cd_sg_at in op_cond_sg else 1)
                    with sg2:
                        op_dest_sg = ["Reutilização", "Transferência", "Manutenção", "Descarte"]
                        ds_sg_at = str(reg_sg.get('destinacao_proposta', 'Reutilização'))
                        ed_dest_sg = st.selectbox("Destinação Proposta:", op_dest_sg, index=op_dest_sg.index(ds_sg_at) if ds_sg_at in op_dest_sg else 0)
                        ed_resp_sg = st.text_input("Responsável pela Análise:", value=str(reg_sg.get('responsavel', '')))
                        ap_sg_at = str(reg_sg.get('aprovacao', 'Pendente'))
                        op_ap = ["Pendente", "Aprovado", "Reprovado"]
                        ed_ap_sg = st.selectbox("Aprovação (Exclusivo Supervisor):", op_ap, index=op_ap.index(ap_sg_at) if ap_sg_at in op_ap else 0, disabled=not is_supervisor)
                    with sg3:
                        ed_st_sg = st.selectbox("Status:", op_st_sg, index=op_st_sg.index(st_sg_at))
                        ed_dt_bx_sg = st.text_input("Data da Baixa (AAAA-MM-DD):", value=str(reg_sg.get('data_baixa', '')), disabled=not is_supervisor)
                        ed_obs_sg = st.text_area("Observação / Justificativa:", value=str(reg_sg.get('observacao', '')))

                    if st.form_submit_button("💾 Salvar Edição do Sem Giro", type="primary"):
                        if (not is_supervisor) and ed_st_sg in ["Aprovado para descarte", "Baixado"] and st_sg_at not in ["Aprovado para descarte", "Baixado"]:
                            st.error("⛔ Apenas o Supervisor pode aprovar descarte ou efetuar baixa definitiva.")
                            st.stop()

                        hoje_s = datetime.now().strftime('%Y-%m-%d')
                        dt_ap_sg = str(reg_sg.get('data_aprovacao', ''))
                        if ed_ap_sg != "Pendente" and not dt_ap_sg:
                            dt_ap_sg = hoje_s
                        dt_bx_sg = ed_dt_bx_sg.strip()
                        if ed_st_sg == "Baixado" and not dt_bx_sg:
                            dt_bx_sg = hoje_s

                        novos_sg = {
                            'base': ed_base_sg.strip(),
                            'motivo_segregacao': ed_mot_sg.strip(),
                            'condicao': ed_cond_sg,
                            'destinacao_proposta': ed_dest_sg,
                            'responsavel': ed_resp_sg.strip(),
                            'aprovacao': ed_ap_sg if is_supervisor else ap_sg_at,
                            'data_aprovacao': dt_ap_sg,
                            'status': ed_st_sg,
                            'data_baixa': dt_bx_sg,
                            'observacao': ed_obs_sg.strip()
                        }

                        mudancas_sg = _gerar_diff_auditoria(reg_sg, novos_sg)
                        if not mudancas_sg:
                            st.warning("Nenhuma alteração foi feita nos campos.")
                        else:
                            supabase.table('eqp_sem_giro').update(novos_sg).eq('id_registro', id_sg_ed).execute()
                            if ed_st_sg == "Baixado" and is_supervisor:
                                supabase.table('ativos_master').update({'status_sistema': 'Baixado', 'atualizado_em': hoje_s}).eq('patrimonio', reg_sg['patrimonio']).execute()
                            registrar_log_auditoria("EDIÇÃO SEM GIRO", reg_sg['patrimonio'], f"ID {id_sg_ed} | " + " | ".join(mudancas_sg))
                            st.cache_data.clear()
                            st.success(f"✅ Registro `{id_sg_ed}` atualizado!")
                            st.rerun()
            else:
                st.info("Nenhum registro de sem giro para editar.")

    # ==========================================================
    # ABA 3: EQUIPAMENTOS SEGREGADOS PARA DESCARTE
    # ==========================================================
    with aba_descarte:
        sub_d1, sub_d2, sub_d3 = st.tabs([
            "📋 Base de Segregados / Descarte (Histórico Permanente)",
            "➕ Segregar Equipamento para Descarte",
            "✏️ Editar / Avançar Fluxo de Descarte"
        ])

        with sub_d1:
            if not df_descarte.empty:
                df_desc_view = df_descarte.copy()
                if 'evidencia' in df_desc_view.columns:
                    df_desc_view['evidencia'] = df_desc_view['evidencia'].apply(lambda v: _extrair_link_externo(v) or v)
                if 'comprovante' in df_desc_view.columns:
                    df_desc_view['comprovante'] = df_desc_view['comprovante'].apply(lambda v: _extrair_link_externo(v) or v)

                st.dataframe(
                    df_desc_view,
                    use_container_width=True,
                    hide_index=True,
                    height=380,
                    column_config={
                        "evidencia": st.column_config.LinkColumn("Evidência (OneDrive)", display_text="🔗 Abrir Evidência"),
                        "comprovante": st.column_config.LinkColumn("Comprovante (OneDrive)", display_text="🔗 Abrir Comprovante")
                    }
                )
                st.download_button("📥 Exportar Segregados para Descarte (.xlsx)", data=converter_df_excel_simples(df_descarte, "Segregados_Descarte"), file_name=f"Equipamentos_Descarte_{datetime.now().strftime('%Y%m%d')}.xlsx")
            else:
                st.info("Nenhum equipamento segregado para descarte.")

        with sub_d2:
            ativos_desc = df_ativos[~df_ativos['status_sistema'].astype(str).str.upper().isin(['SEGREGADO PARA DESCARTE', 'BAIXADO', 'ROUBADO/FURTADO', 'INATIVADO'])].copy() if not df_ativos.empty else pd.DataFrame()
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
                        evid_d = st.text_input("Evidência (Link OneDrive Foto / Laudo) *")
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
                sel_ds = st.selectbox("Selecione o Processo de Descarte para Editar / Avançar:", op_ds, key="sel_ed_ds")
                id_ds_ed = sel_ds.split(" | ")[0]
                reg_ds = df_descarte[df_descarte['id_registro'] == id_ds_ed].iloc[0].to_dict()

                op_fluxo_d = STATUS_FLUXO_DESCARTE_SUPERVISOR if is_supervisor else STATUS_FLUXO_DESCARTE_ARMAZENISTA
                st_at_d = str(reg_ds.get('status', 'Segregado'))
                if st_at_d not in op_fluxo_d:
                    op_fluxo_d = op_fluxo_d + [st_at_d]

                with st.form(f"form_fluxo_descarte_{id_ds_ed}"):
                    f1, f2, f3 = st.columns(3)
                    with f1:
                        ed_base_d = st.text_input("Base Responsável:", value=str(reg_ds.get('base', '')))
                        ed_loc_d = st.text_input("Localização Física:", value=str(reg_ds.get('localizacao_fisica', '')))
                        op_est_d = ["Inservível", "Ruim", "Regular", "Bom"]
                        est_at_d = str(reg_ds.get('estado_conservacao', 'Inservível'))
                        ed_est_d = st.selectbox("Estado de Conservação:", op_est_d, index=op_est_d.index(est_at_d) if est_at_d in op_est_d else 0)
                        mot_at_d = str(reg_ds.get('motivo_segregacao', MOTIVOS_SEGREGACAO_DESCARTE[0]))
                        ed_mot_d = st.selectbox("Motivo da Segregação:", MOTIVOS_SEGREGACAO_DESCARTE, index=MOTIVOS_SEGREGACAO_DESCARTE.index(mot_at_d) if mot_at_d in MOTIVOS_SEGREGACAO_DESCARTE else 0)
                    with f2:
                        op_dest_d = ["Descarte", "Sucata", "Reciclagem", "Devolução"]
                        dest_at_d = str(reg_ds.get('destinacao_proposta', 'Descarte'))
                        ed_dest_d = st.selectbox("Destinação Proposta:", op_dest_d, index=op_dest_d.index(dest_at_d) if dest_at_d in op_dest_d else 0)
                        ed_resp_av = st.text_input("Responsável pela Avaliação:", value=str(reg_ds.get('responsavel_avaliacao', '')))
                        evid_ed = st.text_input("Evidência (Link OneDrive Foto / Laudo) *:", value=str(reg_ds.get('evidencia', '')))
                        comp_ed = st.text_input("Comprovante de Descarte (Link OneDrive MTR / Recibo):", value=str(reg_ds.get('comprovante', '')))
                    with f3:
                        novo_st_d = st.selectbox("Etapa / Status do Processo:", op_fluxo_d, index=op_fluxo_d.index(st_at_d))
                        ap_at_d = str(reg_ds.get('aprovacao_descarte', 'Pendente'))
                        op_apd = ["Pendente", "Aprovado", "Reprovado"]
                        nova_ap_d = st.selectbox("Aprovação (Exclusivo Supervisor):", op_apd, index=op_apd.index(ap_at_d) if ap_at_d in op_apd else 0, disabled=not is_supervisor)
                        aprovador_d = st.text_input("Aprovador:", value=str(reg_ds.get('aprovador', '')) or (st.session_state.get('nome_real', '') if is_supervisor else ''), disabled=not is_supervisor)
                        obs_ed_d = st.text_area("Observações / Motivo:", value=str(reg_ds.get('observacoes', '')))

                    if st.form_submit_button("💾 Salvar Edição / Etapa do Descarte", type="primary"):
                        etapas_criticas = ["Aprovado para descarte", "Descartado", "Baixado"]
                        if (not is_supervisor) and novo_st_d in etapas_criticas and st_at_d not in etapas_criticas:
                            st.error("⛔ Apenas o Supervisor pode aprovar descarte, descartar ou dar baixa definitiva.")
                            st.stop()

                        if novo_st_d in etapas_criticas:
                            if not evid_ed.strip() or nova_ap_d != "Aprovado" or not aprovador_d.strip():
                                st.error("⛔ Bloqueio de Governança: Para avançar para Aprovado/Descartado/Baixado, é obrigatório informar Evidência (Foto/Laudo), Aprovação = 'Aprovado' e o nome do Aprovador.")
                                st.stop()
                        if ed_mot_d.startswith("Outro") and not obs_ed_d.strip():
                            st.error("Para o motivo 'Outro', é obrigatório preencher a justificativa em Observações.")
                            st.stop()

                        hoje_s = datetime.now().strftime('%Y-%m-%d')
                        upd_ds = {
                            'base': ed_base_d.strip(),
                            'localizacao_fisica': ed_loc_d.strip(),
                            'estado_conservacao': ed_est_d,
                            'motivo_segregacao': ed_mot_d,
                            'destinacao_proposta': ed_dest_d,
                            'responsavel_avaliacao': ed_resp_av.strip(),
                            'status': novo_st_d,
                            'aprovacao_descarte': nova_ap_d if is_supervisor else ap_at_d,
                            'aprovador': aprovador_d.strip() if is_supervisor else str(reg_ds.get('aprovador', '')),
                            'evidencia': evid_ed.strip(),
                            'comprovante': comp_ed.strip(),
                            'observacoes': obs_ed_d.strip()
                        }
                        if is_supervisor and nova_ap_d in ["Aprovado", "Reprovado"] and not reg_ds.get('data_aprovacao'):
                            upd_ds['data_aprovacao'] = hoje_s
                        if is_supervisor and novo_st_d == "Descartado" and not reg_ds.get('data_descarte'):
                            upd_ds['data_descarte'] = hoje_s
                        if is_supervisor and novo_st_d == "Baixado":
                            upd_ds['data_baixa'] = hoje_s

                        mudancas_d = _gerar_diff_auditoria(reg_ds, upd_ds)
                        if not mudancas_d:
                            st.warning("Nenhuma alteração foi feita nos campos.")
                        else:
                            supabase.table('eqp_descarte').update(upd_ds).eq('id_registro', id_ds_ed).execute()

                            if is_supervisor and novo_st_d == "Baixado":
                                supabase.table('ativos_master').update({'status_sistema': 'Baixado', 'atualizado_em': hoje_s}).eq('patrimonio', reg_ds['patrimonio']).execute()
                            elif is_supervisor and novo_st_d.startswith("Reaproveitamento aprovado"):
                                supabase.table('ativos_master').update({'status_sistema': 'Disponível', 'cautela': 'ALMOXARIFADO CENTRAL', 'atualizado_em': hoje_s}).eq('patrimonio', reg_ds['patrimonio']).execute()

                            registrar_log_auditoria("EDIÇÃO / FLUXO DESCARTE", reg_ds['patrimonio'], f"ID {id_ds_ed} | " + " | ".join(mudancas_d))
                            st.cache_data.clear()
                            st.success(f"✅ Processo `{id_ds_ed}` atualizado!")
                            st.rerun()
            else:
                st.info("Nenhum processo de descarte registrado.")

    exibir_marca_desenvolvedor()
