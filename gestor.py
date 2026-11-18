import streamlit as st
import pandas as pd
import io
from datetime import datetime
import nuvem
import operacao
from pdf_termo import converter_df_excel_simples, gerar_backup_completo_excel

supabase = nuvem.supabase
COLUNAS_ATIVOS = nuvem.COLUNAS_ATIVOS
COLUNAS_MOV = nuvem.COLUNAS_MOV
COLUNAS_TERMOS = nuvem.COLUNAS_TERMOS
COLUNAS_DIVERG = nuvem.COLUNAS_DIVERG
COLUNAS_EMPREGADOS = nuvem.COLUNAS_EMPREGADOS
normalizar_nome_coluna = nuvem.normalizar_nome_coluna
salvar_dados_massa = nuvem.salvar_dados_massa
registrar_log_auditoria = nuvem.registrar_log_auditoria
calcular_uso_supabase = nuvem.calcular_uso_supabase
exibir_marca_desenvolvedor = nuvem.exibir_marca_desenvolvedor
matricula_valida = nuvem.matricula_valida
limpar_texto_matricula = nuvem.limpar_texto_matricula
expurgar_linhas_nulas_nuvem = nuvem.expurgar_linhas_nulas_nuvem
carregar_preferencias_colunas = getattr(nuvem, 'carregar_preferencias_colunas', lambda: {})
salvar_preferencias_colunas = getattr(nuvem, 'salvar_preferencias_colunas', lambda *a, **kw: None)
calcular_dias_sem_mov = getattr(nuvem, 'calcular_dias_sem_mov', lambda x: "0")

def inicializar_prefs_nuvem():
    if 'prefs_carregadas_nuvem' not in st.session_state:
        prefs = carregar_preferencias_colunas()
        st.session_state.saved_cols_inv = prefs.get('inv', list(COLUNAS_ATIVOS))
        st.session_state.saved_cols_mov = prefs.get('mov', list(COLUNAS_MOV))
        st.session_state.saved_cols_trm = prefs.get('trm', list(COLUNAS_TERMOS))
        if 'saved_cols_fer' not in st.session_state:
            st.session_state.saved_cols_fer = prefs.get('fer', [])
        st.session_state.prefs_carregadas_nuvem = True

def update_cols_inv():
    st.session_state.saved_cols_inv = st.session_state.ms_inv_key
    salvar_preferencias_colunas(
        st.session_state.saved_cols_inv,
        st.session_state.saved_cols_mov,
        st.session_state.saved_cols_trm,
        st.session_state.get('saved_cols_fer')
    )

def update_cols_mov():
    st.session_state.saved_cols_mov = st.session_state.ms_mov_key
    salvar_preferencias_colunas(
        st.session_state.saved_cols_inv,
        st.session_state.saved_cols_mov,
        st.session_state.saved_cols_trm,
        st.session_state.get('saved_cols_fer')
    )

def update_cols_trm():
    st.session_state.saved_cols_trm = st.session_state.ms_trm_key
    salvar_preferencias_colunas(
        st.session_state.saved_cols_inv,
        st.session_state.saved_cols_mov,
        st.session_state.saved_cols_trm,
        st.session_state.get('saved_cols_fer')
    )

def formatar_badge_alerta_ativo(status_sis, cond_uso, dias_ociosos=0):
    st_up = str(status_sis).strip().upper()
    cd_up = str(cond_uso).strip().upper()
    try:
        d_oc = int(float(str(dias_ociosos).strip()))
    except Exception:
        d_oc = 0

    if d_oc > 90 and st_up not in ["BAIXADO"]:
        return "⏳ PARADO > 90 DIAS"
    if "INAPTO" in cd_up or "REPROVADO" in cd_up or "INSERV" in cd_up:
        return "🔴 DEFEITO / BLOQUEADO"
    if st_up == "DISPONÍVEL":
        return "🟢 DISPONÍVEL"
    elif st_up == "EM USO":
        return "🔵 EM USO / CAUTELA"
    elif "MANUTEN" in st_up:
        return "🟠 EM MANUTENÇÃO"
    elif "TRÂNSITO" in st_up or "TRANSITO" in st_up:
        return "🟡 EM TRÂNSITO"
    elif st_up == "BAIXADO":
        return "⚪ BAIXADO / DESCARTE"
    return f"⚪ {st_up}"

# ==========================================
# MÓDULO 1: PAINEL OPERACIONAL DE EQUIPAMENTOS (COM EDIÇÃO AUDITADA)
# ==========================================
def render_modulo_dashboard(df_ativos, df_mov, df_termos, df_diverg, df_empregados):
    inicializar_prefs_nuvem()

    # Espaçamento superior de 2.8rem para impedir corte do título
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("📦 Painel Operacional — Equipamentos e Ativos")

    if st.session_state.get('resumo_ultima_operacao'):
        info_op = st.session_state.resumo_ultima_operacao
        st.success(f"✅ **{info_op['titulo']}** | Atualizado às {info_op['hora']} (Antes: {info_op['qtd_antes']} | Novos: +{info_op['novos']} | Atualizados: {info_op['atualizados']} | Total: {info_op['qtd_depois']})")
        if st.button("✖️ Fechar Resumo"):
            st.session_state.resumo_ultima_operacao = None
            st.rerun()

    abas_dashboard = [
        "📋 Estoque Segmentado por Status",
        "✏️ Editar Equipamento Carregado",
        "➕ Cadastrar Novo Equipamento", 
        "📜 Histórico de Movimentações", 
        "📄 Termos Emitidos", 
        "📥 Importar / Exportar & Backup"
    ]
    if st.session_state.perfil == 'Master':
        abas_dashboard.append("❌ Excluir Registos (Master)")
        
    abas = st.tabs(abas_dashboard)
    
    # --- ABA 0: ESTOQUE SEGMENTADO POR STATUS ---
    with abas[0]:
        cf0, cf1, cf_ex, cf2, cf3, cf4 = st.columns([1.2, 1.8, 0.7, 1.0, 1.0, 0.6])
        with cf0:
            col_f_eq = st.selectbox("Campo:", ["Todos os Campos", "Patrimônio", "Número de Série", "Item D365", "Equipamento / Marca"], label_visibility="collapsed", key="fp_col_eqp")
        with cf1:
            f_busca = st.text_input("🔍 Buscar:", label_visibility="collapsed", placeholder="🔍 Digite Patrimônio, Série, Item ou Nome...")
        with cf_ex:
            f_exato = st.checkbox("🎯 Exato", value=(col_f_eq in ["Patrimônio", "Número de Série", "Item D365"]), key="fp_ex_eqp")
        with cf2:
            ends_01 = sorted([e for e in df_ativos['enderecamento_01'].unique().tolist() if str(e).strip()]) if (not df_ativos.empty and 'enderecamento_01' in df_ativos.columns) else []
            f_end1 = st.selectbox("Endereçamento 01:", ["Todos End. 01"] + ends_01, label_visibility="collapsed")
        with cf3:
            coords = sorted([c for c in df_ativos['coordenacao'].unique().tolist() if str(c).strip()]) if not df_ativos.empty else []
            f_coord = st.selectbox("Coordenação:", ["Todas Coord."] + coords, label_visibility="collapsed")
        with cf4:
            with st.popover("👁️ Colunas", use_container_width=True):
                st.caption("Selecione as colunas visíveis:")
                if st.button("🔄 Mostrar Todas", key="btn_reset_inv", use_container_width=True):
                    st.session_state.saved_cols_inv = list(COLUNAS_ATIVOS)
                    salvar_preferencias_colunas(
                        st.session_state.saved_cols_inv,
                        st.session_state.saved_cols_mov,
                        st.session_state.saved_cols_trm,
                        st.session_state.get('saved_cols_fer')
                    )
                    st.rerun()
                st.multiselect(
                    "Colunas (Salvo na nuvem):",
                    options=COLUNAS_ATIVOS,
                    default=[c for c in st.session_state.saved_cols_inv if c in COLUNAS_ATIVOS],
                    key="ms_inv_key",
                    on_change=update_cols_inv,
                    label_visibility="collapsed"
                )

        cols_para_exibir = [c for c in st.session_state.saved_cols_inv if c in COLUNAS_ATIVOS]
        if not cols_para_exibir:
            cols_para_exibir = list(COLUNAS_ATIVOS)
        
        if not df_ativos.empty:
            df_base = df_ativos.copy()
            for c_at in COLUNAS_ATIVOS:
                if c_at not in df_base.columns:
                    df_base[c_at] = ""

            if f_coord != "Todas Coord.":
                df_base = df_base[df_base['coordenacao'] == f_coord]
            if f_end1 != "Todos End. 01":
                df_base = df_base[df_base['enderecamento_01'] == f_end1]
            if f_busca.strip():
                t_up = f_busca.strip().upper()
                if col_f_eq == "Patrimônio":
                    s_al = df_base['patrimonio'].astype(str).str.strip().str.upper()
                elif col_f_eq == "Número de Série":
                    s_al = df_base['numero_serie'].astype(str).str.strip().str.upper()
                elif col_f_eq == "Item D365":
                    s_al = df_base['item'].astype(str).str.strip().str.upper()
                elif col_f_eq == "Equipamento / Marca":
                    s_al = (df_base['equipamento'].astype(str) + " " + df_base['marca'].astype(str) + " " + df_base['modelo'].astype(str)).str.upper()
                else:
                    s_al = df_base.astype(str).apply(lambda x: " ".join(x), axis=1).str.upper()

                if f_exato and col_f_eq in ["Patrimônio", "Número de Série", "Item D365"]:
                    df_base = df_base[s_al == t_up]
                elif f_exato:
                    df_base = df_base[s_al.str.split().apply(lambda w: t_up in w)]
                else:
                    df_base = df_base[s_al.str.contains(t_up, regex=False, na=False)]

            st_s = df_base['status_sistema'].astype(str).str.upper().str.strip()
            cd_s = df_base['condicoes_para_uso'].astype(str).str.upper().str.strip()
            dias_oc = df_base['atualizado_em'].apply(lambda d: int(calcular_dias_sem_mov(d)) if str(calcular_dias_sem_mov(d)).isdigit() else 0)

            df_g_disp = df_base[st_s == 'DISPONÍVEL']
            df_g_uso = df_base[st_s == 'EM USO']
            df_g_manut = df_base[st_s.str.contains('MANUTEN', na=False) | cd_s.str.contains('REPROV|INAPTO', na=False)]
            df_g_trans = df_base[st_s.str.contains('TRÂNSITO|TRANSITO', na=False)]
            df_g_baix = df_base[(st_s == 'BAIXADO') | cd_s.str.contains('INSERV', na=False)]
            df_g_parado = df_base[(dias_oc > 90) & (st_s != 'BAIXADO')]

            sub_abas_eqp = st.tabs([
                f"🟢 Disponível ({len(df_g_disp)})",
                f"🔵 Em Uso / Campo ({len(df_g_uso)})",
                f"🟠 Em Manutenção / Lab ({len(df_g_manut)})",
                f"🟡 Em Trânsito ({len(df_g_trans)})",
                f"⚪ Baixado / Inservível ({len(df_g_baix)})",
                f"⏳ Parado > 90 Dias ({len(df_g_parado)})"
            ])

            grupos_eqp = [df_g_disp, df_g_uso, df_g_manut, df_g_trans, df_g_baix, df_g_parado]
            for idx_e, s_tab in enumerate(sub_abas_eqp):
                with s_tab:
                    df_item_e = grupos_eqp[idx_e]
                    if not df_item_e.empty:
                        df_show_e = df_item_e[cols_para_exibir].copy()
                        df_show_e.insert(
                            0, "Alerta",
                            df_item_e.apply(
                                lambda r: formatar_badge_alerta_ativo(
                                    r.get('status_sistema', ''),
                                    r.get('condicoes_para_uso', ''),
                                    calcular_dias_sem_mov(r.get('atualizado_em', ''))
                                ), axis=1
                            )
                        )
                        st.dataframe(df_show_e, use_container_width=True, hide_index=True, height=430)
                    else:
                        st.info("Nenhum equipamento enquadrado nesta categoria no momento.")
        else:
            st.info("Nenhum ativo registado na base no momento.")

    # --- ABA 1: EDITAR EQUIPAMENTO CARREGADO (COM TRILHA DETALHADA NA AUDITORIA) ---
    with abas[1]:
        st.subheader("✏️ Editar Informações de Equipamento Carregado")
        st.caption("Filtre e marque na tabela abaixo o equipamento que deseja alterar manualmente. Todas as mudanças de valor (Antes -> Depois) ficam registradas na aba Auditoria Geral.")

        seletor_fn = getattr(operacao, 'render_seletor_excel_equipamentos', None)
        if seletor_fn and not df_ativos.empty:
            df_edit_sel = seletor_fn(df_ativos, "edit_manual_eqp", multiplo=False, altura=190)
        else:
            df_edit_sel = pd.DataFrame()

        if not df_edit_sel.empty:
            reg_antigo = df_edit_sel.iloc[0].to_dict()
            pat_alvo = str(reg_antigo['patrimonio']).strip()

            st.info(f"🔧 **Editando Patrimônio:** `{pat_alvo}` — {reg_antigo.get('equipamento', '')} {reg_antigo.get('marca', '')} {reg_antigo.get('modelo', '')}")

            with st.form(f"form_editar_ativo_{pat_alvo}"):
                e1, e2, e3, e4 = st.columns(4)
                with e1:
                    st.text_input("Patrimônio (Chave Fixa)", value=pat_alvo, disabled=True)
                    ed_eqp = st.text_input("Equipamento", value=str(reg_antigo.get('equipamento', '')))
                    ed_marca = st.text_input("Marca", value=str(reg_antigo.get('marca', '')))
                    ed_modelo = st.text_input("Modelo", value=str(reg_antigo.get('modelo', '')))
                with e2:
                    ed_serie = st.text_input("Número de Série", value=str(reg_antigo.get('numero_serie', '')))
                    ed_item = st.text_input("Item / Código D365", value=str(reg_antigo.get('item', '')))
                    ed_valor = st.text_input("Valor (R$)", value=str(reg_antigo.get('valor', '')))
                    ed_nf = st.text_input("NF Procisa", value=str(reg_antigo.get('nf_procisa', '')))
                with e3:
                    ed_cautela = st.text_input("Cautela (Local/Responsável)", value=str(reg_antigo.get('cautela', '')))
                    ed_end1 = st.text_input("Endereçamento 01 (LOCAL)", value=str(reg_antigo.get('enderecamento_01', '')))
                    ed_end2 = st.text_input("Endereçamento 02 (Descri. Local)", value=str(reg_antigo.get('enderecamento_02', '')))
                    op_st = ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"]
                    st_at = str(reg_antigo.get('status_sistema', 'Disponível'))
                    ed_status = st.selectbox("Status no Sistema", op_st, index=op_st.index(st_at) if st_at in op_st else 0)
                with e4:
                    ed_proj = st.text_input("Projeto", value=str(reg_antigo.get('projeto', '')))
                    ed_coord = st.text_input("Coordenação", value=str(reg_antigo.get('coordenacao', '')))
                    op_cd = ["APTO", "APTO COM RESSALVA", "EM MANUTENÇÃO", "REPROVADO", "INSERVÍVEL"]
                    cd_at = str(reg_antigo.get('condicoes_para_uso', 'APTO')).upper()
                    ed_cond = st.selectbox("Condições para Uso", op_cd, index=op_cd.index(cd_at) if cd_at in op_cd else 0)
                    ed_acess = st.text_input("Acessórios / Observações", value=str(reg_antigo.get('acessorios', '')))

                motivo_ed = st.text_input("Motivo da Edição Manual (Para registro na Auditoria):")

                if st.form_submit_button("💾 Salvar Alterações e Auditar", type="primary"):
                    novos_dados = {
                        'item': ed_item.strip(),
                        'valor': ed_valor.strip(),
                        'equipamento': ed_eqp.strip(),
                        'marca': ed_marca.strip(),
                        'modelo': ed_modelo.strip(),
                        'numero_serie': ed_serie.strip(),
                        'cautela': ed_cautela.strip(),
                        'enderecamento_01': ed_end1.strip().upper(),
                        'enderecamento_02': ed_end2.strip().upper(),
                        'projeto': ed_proj.strip(),
                        'coordenacao': ed_coord.strip(),
                        'nf_procisa': ed_nf.strip(),
                        'condicoes_para_uso': ed_cond,
                        'acessorios': ed_acess.strip(),
                        'status_sistema': ed_status,
                        'atualizado_em': datetime.now().strftime('%Y-%m-%d')
                    }

                    mudancas = []
                    for k_campo, v_novo in novos_dados.items():
                        if k_campo == 'atualizado_em':
                            continue
                        v_ant = str(reg_antigo.get(k_campo, '')).strip()
                        if v_ant != str(v_novo).strip():
                            mudancas.append(f"{k_campo}: '{v_ant}' -> '{v_novo}'")

                    if not mudancas:
                        st.warning("Nenhuma alteração foi detectada nos campos.")
                    else:
                        try:
                            supabase.table('ativos_master').update(novos_dados).eq('patrimonio', pat_alvo).execute()
                            resumo_mudancas = " | ".join(mudancas)
                            if motivo_ed.strip():
                                resumo_mudancas = f"[Motivo: {motivo_ed.strip()}] " + resumo_mudancas
                            registrar_log_auditoria("EDIÇÃO MANUAL (EQUIPAMENTO)", pat_alvo, resumo_mudancas)
                            st.session_state.clear() if False else st.cache_data.clear()
                            st.success(f"✅ Equipamento `{pat_alvo}` atualizado e registrado na Auditoria ({len(mudancas)} campo(s) alterado(s))!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar equipamento: {e}")

    # --- ABA 2: CADASTRO MANUAL ---
    with abas[2]:
        st.subheader("➕ Cadastrar Novo Equipamento")
        with st.form("form_novo_ativo"):
            colA, colB, colC, colD = st.columns(4)
            with colA:
                cad_patrimonio = st.text_input("Patrimônio / Placa *")
                cad_equipamento = st.text_input("Equipamento *")
                cad_marca = st.text_input("Marca")
                cad_modelo = st.text_input("Modelo")
            with colB:
                cad_serie = st.text_input("Número de Série")
                cad_item = st.text_input("Item / Código D365")
                cad_valor = st.text_input("Valor (R$)")
                cad_nf = st.text_input("NF Procisa")
            with colC:
                cad_cautela = st.text_input("Cautela (Local/Responsável)", value="ALMOXARIFADO CENTRAL")
                cad_end1 = st.text_input("Endereçamento 01 (Prateleira)")
                cad_end2 = st.text_input("Endereçamento 02 (Caixa/Gaveta)")
                cad_status = st.selectbox("Status no Sistema", ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"])
            with colD:
                cad_projeto = st.text_input("Projeto", value="ESTOQUE ALMOXARIFADO")
                cad_coord = st.text_input("Coordenação", value="LOGÍSTICA / ALMOXARIFADO")
                cad_condicao = st.selectbox("Condições para Uso", ["APTO", "APTO COM RESSALVA", "EM MANUTENÇÃO", "REPROVADO", "INSERVÍVEL"])
                cad_acessorios = st.text_input("Acessórios / Observações")
            
            submit_cadastro = st.form_submit_button("💾 Salvar Equipamento na Nuvem", type="primary")
            
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
                        'enderecamento_01': cad_end1.strip().upper(),
                        'enderecamento_02': cad_end2.strip().upper(),
                        'projeto': cad_projeto.strip(),
                        'coordenacao': cad_coord.strip(),
                        'nf_procisa': cad_nf.strip(),
                        'atualizado_em': datetime.now().strftime('%Y-%m-%d'),
                        'condicoes_para_uso': cad_condicao,
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

    # --- ABA 3: HISTÓRICO DE MOVIMENTAÇÕES ---
    with abas[3]:
        c_hm1, c_hm2 = st.columns([4.3, 0.7])
        with c_hm1:
            busca_hm = st.text_input("🔍 Filtrar Histórico de Movimentações:", label_visibility="collapsed", placeholder="🔍 Buscar por ID Mov, Patrimônio, Origem, Destino ou Solicitante...")
        with c_hm2:
            with st.popover("👁️ Colunas", use_container_width=True):
                st.multiselect(
                    "Colunas (Movimentações):",
                    options=COLUNAS_MOV,
                    default=[c for c in st.session_state.saved_cols_mov if c in COLUNAS_MOV],
                    key="ms_mov_key",
                    on_change=update_cols_mov,
                    label_visibility="collapsed"
                )
        cols_m_exibir = [c for c in (st.session_state.saved_cols_mov if st.session_state.saved_cols_mov else COLUNAS_MOV) if c in df_mov.columns] if not df_mov.empty else COLUNAS_MOV
        df_m_show = df_mov.copy()
        if not df_m_show.empty and busca_hm.strip():
            tm = busca_hm.strip().lower()
            df_m_show = df_m_show[df_m_show.astype(str).apply(lambda x: x.str.lower().str.contains(tm, na=False)).any(axis=1)]
        st.dataframe(df_m_show[cols_m_exibir] if not df_m_show.empty else pd.DataFrame(columns=cols_m_exibir), use_container_width=True, hide_index=True, height=440)

    # --- ABA 4: TERMOS EMITIDOS ---
    with abas[4]:
        c_ht1, c_ht2 = st.columns([4.3, 0.7])
        with c_ht1:
            busca_ht = st.text_input("🔍 Filtrar Termos Emitidos:", label_visibility="collapsed", placeholder="🔍 Buscar por ID Termo, Patrimônio, Responsável ou Matrícula...")
        with c_ht2:
            with st.popover("👁️ Colunas", use_container_width=True):
                st.multiselect(
                    "Colunas (Termos):",
                    options=COLUNAS_TERMOS,
                    default=[c for c in st.session_state.saved_cols_trm if c in COLUNAS_TERMOS],
                    key="ms_trm_key",
                    on_change=update_cols_trm,
                    label_visibility="collapsed"
                )
        cols_t_exibir = [c for c in (st.session_state.saved_cols_trm if st.session_state.saved_cols_trm else COLUNAS_TERMOS) if c in df_termos.columns] if not df_termos.empty else COLUNAS_TERMOS
        df_t_show = df_termos.copy()
        if not df_t_show.empty and busca_ht.strip():
            tt = busca_ht.strip().lower()
            df_t_show = df_t_show[df_t_show.astype(str).apply(lambda x: x.str.lower().str.contains(tt, na=False)).any(axis=1)]
        st.dataframe(df_t_show[cols_t_exibir] if not df_t_show.empty else pd.DataFrame(columns=cols_t_exibir), use_container_width=True, hide_index=True, height=440)

    # --- ABA 5: IMPORTAR / EXPORTAR ---
    with abas[5]:
        st.subheader("📤 Exportar Relatórios do Sistema (.xlsx)")
        stamp = datetime.now().strftime('%Y%m%d_%H%M')
        c_exp1, c_exp2, c_exp3 = st.columns(3)
        
        with c_exp1:
            df_a_exp = df_ativos[[c for c in COLUNAS_ATIVOS if c in df_ativos.columns]] if not df_ativos.empty else pd.DataFrame(columns=COLUNAS_ATIVOS)
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
            st.markdown("##### 📦 Planilha de Equipamentos")
            arquivo_up = st.file_uploader("Arraste o arquivo Excel de EQUIPAMENTOS (.xlsx)", type=["xlsx"])
            if arquivo_up:
                try:
                    df_up = pd.read_excel(arquivo_up)
                    df_up.columns = [normalizar_nome_coluna(c) for c in df_up.columns]
                    
                    if 'status_sistema' not in df_up.columns:
                        df_up['status_sistema'] = 'Disponível'
                    if 'enderecamento_01' not in df_up.columns:
                        df_up['enderecamento_01'] = ''
                    if 'enderecamento_02' not in df_up.columns:
                        df_up['enderecamento_02'] = ''
                    
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

    # --- ABA 6: EXCLUSÃO POR SELEÇÃO DE LINHAS (MASTER) ---
    if st.session_state.perfil == 'Master':
        with abas[6]:
            st.subheader("❌ Exclusão de Registos por Seleção (Acesso Restrito Master)")
            tipo_exclusao = st.radio("Selecione a Tabela para Exclusão:", ["📦 Ativos (Equipamentos)", "👥 Colaboradores (Empregados)"], horizontal=True)
            
            if tipo_exclusao.startswith("📦"):
                if not df_ativos.empty:
                    busca_del = st.text_input("🔍 Filtrar ativos antes de marcar (Patrimônio, Série, Equipamento ou Cautela):")
                    cols_del_at = [c for c in COLUNAS_ATIVOS if c in df_ativos.columns]
                    df_del_view = df_ativos[cols_del_at].copy()
                    if busca_del.strip():
                        t_del = busca_del.strip().lower()
                        mask_del = df_del_view.astype(str).apply(lambda x: x.str.lower().str.contains(t_del, na=False)).any(axis=1)
                        df_del_view = df_del_view[mask_del]
                        
                    df_del_view.insert(0, "Excluir", False)
                    
                    df_editado = st.data_editor(
                        df_del_view,
                        hide_index=True,
                        use_container_width=True,
                        height=400,
                        disabled=[c for c in df_del_view.columns if c != "Excluir"],
                        column_config={"Excluir": st.column_config.CheckboxColumn("🗑️ Excluir?", default=False)},
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
                        height=400,
                        disabled=[c for c in df_emp_view.columns if c != "Excluir"],
                        column_config={"Excluir": st.column_config.CheckboxColumn("🗑️ Excluir?", default=False)},
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
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("👥 Painel Admin - Gestão de Usuários")
    
    aba_listar, aba_novo, aba_editar = st.tabs(["Visão Geral", "Novo Usuário", "Editar / Resetar Senha"])
    
    with aba_listar:
        st.dataframe(df_usuarios, use_container_width=True, hide_index=True)
        
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
        
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("🛡️ Central de Auditoria e Rastreabilidade (Gestor)")
    
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
        
    if not df_auditoria.empty:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            tipos_unicos = ["Todos"] + sorted(df_auditoria['Tipo de Evento'].unique().tolist())
            filtro_tipo = st.selectbox("Filtrar por Tipo de Ação:", tipos_unicos)
        with col_f2:
            busca_texto = st.text_input("Buscar por Patrimônio, ID FER, Usuário ou Palavra-chave:")
            
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
            
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True, height=440)
        
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
