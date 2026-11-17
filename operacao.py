# ==========================================
# MÓDULO 8 (EQUIPAMENTOS): MODO OPERADOR QR CODE + FOLHA DE ETIQUETAS A4
# ==========================================
def render_operador_qrcode_eqp(df_ativos, df_empregados):
    from pdf_termo import gerar_etiquetas_qrcode_pdf
    st.subheader("📷 Modo Operador — Leitura de QR Code / Endereçamento (Equipamentos)")
    st.caption("Bipe o QR Code / Código de Barras do Endereçamento (01/02) ou do Equipamento (Patrimônio / Nº de Série) para localizar e movimentar.")

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
        "📡 Coletor / Scanner (Equipamentos)",
        "🏷️ Gerador de Folha de Etiquetas QR Code em Lote (PDF A4)"
    ])

    with aba_sc_eqp:
        c1, c2 = st.columns([3, 1])
        with c1:
            cod_eqp_qr = st.text_input(
                "🔫 Bipe ou Digite o Código (Endereçamento 01, Endereçamento 02, Patrimônio ou Nº de Série):",
                placeholder="Ex: US-AC1N1P9 ou Patrimônio...",
                key="input_qr_eqp"
            )
        with c2:
            cam_eqp = st.toggle("📷 Câmera", value=False, key="tog_cam_eqp")

        if cam_eqp:
            st.camera_input("Leitura Óptica (Equipamentos)", key="cam_qr_eqp")

        if cod_eqp_qr.strip() and not df_ativos.empty:
            resultados = buscar_ativo(cod_eqp_qr, df_ativos)
            if not resultados.empty:
                st.success(f"✅ **{len(resultados)} equipamento(s)** localizado(s) para o código `{cod_eqp_qr.strip().upper()}`!")
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
        if not df_ativos.empty:
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
