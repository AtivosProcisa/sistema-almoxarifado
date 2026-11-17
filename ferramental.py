import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import nuvem
from pdf_termo import (
    converter_df_excel_simples, gerar_backup_completo_excel,
    gerar_termo_pdf, gerar_etiquetas_qrcode_pdf
)

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
    'localizacao', 'enderecamento_01', 'enderecamento_02',
    'responsavel_atual', 'matricula', 'projeto', 'coordenacao',
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

def _maior_num_id_fer(df_fer):
    if df_fer.empty or 'id_controle' not in df_fer.columns:
        return 0
    maior = 0
    for val in df_fer['id_controle'].astype(str):
        val_limpo = val.strip().upper()
        if val_limpo.startswith("FER-"):
            num_str = val_limpo.replace("FER-", "").strip()
            if num_str.isdigit():
                maior = max(maior, int(num_str))
    return maior

def gerar_proximo_id_fer(df_fer):
    return f"FER-{_maior_num_id_fer(df_fer) + 1:06d}"

def buscar_ferramenta(termo_busca, df_fer):
    if df_fer.empty or not termo_busca:
        return pd.DataFrame()
    t = str(termo_busca).strip().upper()
    id_c = df_fer['id_controle'].fillna("").astype(str).str.strip().str.upper()
    c_d365 = df_fer['codigo_d365'].fillna("").astype(str).str.strip().str.upper()
    pat = df_fer['patrimonio'].fillna("").astype(str).str.strip().str.upper()
    ser = df_fer['numero_serie'].fillna("").astype(str).str.strip().str.upper()
    e1 = df_fer['enderecamento_01'].fillna("").astype(str).str.strip().str.upper()
    e2 = df_fer['enderecamento_02'].fillna("").astype(str).str.strip().str.upper()
    return df_fer[(id_c == t) | (c_d365 == t) | (pat == t) | (ser == t) | (e1 == t) | (e2 == t)]

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
# SELETOR ESTILO FILTRO DO EXCEL (BUSCA ESPECÍFICA + TABELA COM CHECKBOX)
# ==========================================
def render_seletor_excel_ferramentas(df_fonte, chave_unica, multiplo=True, altura=230):
    """
    Substitui o st.multiselect tradicional por um filtro estilo Excel:
    - Escolha da coluna específica (Cód D365 Exato, ID FER Exato, Descrição, Endereço ou Todos)
    - Opção de Busca Exata (para que digitar '146' traga apenas o código 146 e não 1460)
    - Tabela interativa com caixinha [✓] que preserva os itens marcados mesmo ao trocar o termo de busca.
    """
    state_sel = f"sel_excel_ids_{chave_unica}"
    if state_sel not in st.session_state:
        st.session_state[state_sel] = set()

    if df_fonte.empty:
        st.warning("Nenhum item disponível para seleção.")
        return pd.DataFrame()

    c_f1, c_f2, c_f3, c_f4 = st.columns([1.4, 2.2, 0.9, 0.7])
    with c_f1:
        col_alvo = st.selectbox(
            "Filtrar Coluna:",
            ["Código D365", "Descrição / Nome", "ID FER (Controle)", "Endereçamento 01/02", "Todos os Campos"],
            key=f"col_ex_{chave_unica}",
            label_visibility="collapsed"
        )
    with c_f3:
        padrao_exato = True if col_alvo in ["Código D365", "ID FER (Controle)"] else False
        modo_exato = st.checkbox("🎯 Busca Exata", value=padrao_exato, key=f"exato_{chave_unica}", help="Quando marcado, digitar '146' traz apenas o item de código exatamente igual a '146'.")
    with c_f2:
        termo_b = st.text_input(
            "Digite para filtrar:",
            placeholder="🔍 Digite códigos (separe por vírgula p/ vários) ou texto...",
            key=f"txt_ex_{chave_unica}",
            label_visibility="collapsed"
        )
    with c_f4:
        if st.button(f"🧹 Limpar ({len(st.session_state[state_sel])})", key=f"clr_ex_{chave_unica}", use_container_width=True):
            st.session_state[state_sel] = set()
            st.rerun()

    df_view = df_fonte.copy()
    if termo_b.strip():
        termos_lista = [t.strip().upper() for t in termo_b.replace(";", ",").split(",") if t.strip()]
        mask_total = pd.Series(False, index=df_view.index)

        for t_item in termos_lista:
            if col_alvo == "Código D365":
                s_col = df_view['codigo_d365'].fillna("").astype(str).str.strip().str.upper()
            elif col_alvo == "ID FER (Controle)":
                s_col = df_view['id_controle'].fillna("").astype(str).str.strip().str.upper()
            elif col_alvo == "Descrição / Nome":
                s_col = (df_view['descricao_d365'].fillna("").astype(str) + " " + df_view['descricao_ferramenta'].fillna("").astype(str)).str.upper()
            elif col_alvo == "Endereçamento 01/02":
                s_col = (df_view['enderecamento_01'].fillna("").astype(str) + " " + df_view['enderecamento_02'].fillna("").astype(str)).str.upper()
            else:
                s_col = (
                    df_view['codigo_d365'].fillna("").astype(str) + " " +
                    df_view['id_controle'].fillna("").astype(str) + " " +
                    df_view['descricao_d365'].fillna("").astype(str) + " " +
                    df_view['descricao_ferramenta'].fillna("").astype(str) + " " +
                    df_view['enderecamento_01'].fillna("").astype(str)
                ).str.upper()

            if modo_exato and col_alvo in ["Código D365", "ID FER (Controle)"]:
                mask_total = mask_total | (s_col == t_item)
            elif modo_exato:
                mask_total = mask_total | s_col.str.split().apply(lambda palavras: t_item in palavras)
            else:
                mask_total = mask_total | s_col.str.contains(t_item, regex=False, na=False)

        # Mantém visíveis tanto os resultados da busca atual quanto os itens que o usuário já marcou antes
        mask_ja_marcados = df_view['id_controle'].isin(st.session_state[state_sel])
        df_view = df_view[mask_total | mask_ja_marcados].copy()

    df_grid = pd.DataFrame({
        'Selecionar': df_view['id_controle'].isin(st.session_state[state_sel]),
        'Cód D365': df_view['codigo_d365'].astype(str),
        'Descrição D365': df_view['descricao_d365'].astype(str),
        'Nome / Pesquisa': df_view['descricao_ferramenta'].astype(str),
        'Saldo': df_view['quantidade'].astype(str),
        'Endereço 01': df_view['enderecamento_01'].astype(str),
        'Endereço 02': df_view['enderecamento_02'].astype(str),
        'Condição': df_view['condicao_fisica'].astype(str),
        'ID FER': df_view['id_controle'].astype(str)
    })

    # Ordena colocando os já selecionados no topo da grade
    df_grid = df_grid.sort_values(by=['Selecionar', 'Cód D365'], ascending=[False, True]).reset_index(drop=True)

    editado = st.data_editor(
        df_grid,
        hide_index=True,
        use_container_width=True,
        height=altura,
        disabled=['Cód D365', 'Descrição D365', 'Nome / Pesquisa', 'Saldo', 'Endereço 01', 'Endereço 02', 'Condição', 'ID FER'],
        column_config={
            'Selecionar': st.column_config.CheckboxColumn("☑️ Selecionar", default=False, width="small"),
            'Cód D365': st.column_config.TextColumn("Cód D365", width="small"),
            'Saldo': st.column_config.TextColumn("Saldo", width="small")
        },
        key=f"grid_ex_{chave_unica}"
    )

    ids_visiveis = set(df_grid['ID FER'].tolist())
    ids_marcados_agora = set(editado[editado['Selecionar'] == True]['ID FER'].tolist())

    if not multiplo and len(ids_marcados_agora) > 1:
        # Se for seleção única, mantém apenas o último clicado
        novos_clicados = list(ids_marcados_agora - st.session_state[state_sel])
        id_manter = novos_clicados[0] if novos_clicados else list(ids_marcados_agora)[0]
        st.session_state[state_sel] = {id_manter}
        st.rerun()
    else:
        st.session_state[state_sel] = (st.session_state[state_sel] - ids_visiveis) | ids_marcados_agora

    df_selecionados_final = df_fonte[df_fonte['id_controle'].isin(st.session_state[state_sel])].copy()
    if not df_selecionados_final.empty:
        resumo_sel = ", ".join([f"Cód {r['codigo_d365']} ({r['id_controle']})" for _, r in df_selecionados_final.iterrows()])
        st.caption(f"✅ **{len(df_selecionados_final)} item(ns) marcado(s):** {resumo_sel}")
    return df_selecionados_final

# ==========================================
# F0: DASHBOARD EXECUTIVO - VISÃO GERAL (7 PERGUNTAS DE GESTÃO)
# ==========================================
def render_dashboard_ferramental(df_fer, df_mov_fer, df_caut_fer, df_manut_fer, df_baixa_fer):
    st.markdown("<style>div.block-container{padding-top: 1.2rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("📊 Dashboard Executivo — Visão Geral do Ferramental")
    st.caption("Respostas rápidas de diagnóstico gerencial sobre volume, disponibilidade, localização, composição, inoperância, integridade cadastral e ações imediatas.")

    if df_fer.empty:
        st.info("Nenhuma ferramenta cadastrada na base para gerar indicadores.")
        exibir_marca_desenvolvedor()
        return

    qtd_s = df_fer['quantidade'].apply(lambda x: _parse_int(x, 1))
    st_s = df_fer['status_operacional'].astype(str).str.upper().str.strip()
    cd_s = df_fer['condicao_fisica'].astype(str).str.upper().str.strip()
    dias_s = df_fer['dias_sem_movimentacao'].apply(lambda x: _parse_int(x, 0))
    mask_ativos = ~st_s.isin(['BAIXADO', 'TRANSFERIDO'])

    # 1 & 2. Quantos existem, disponíveis, em uso ou indisponíveis?
    total_pecas = int(qtd_s[mask_ativos].sum())
    total_lotes = int(mask_ativos.sum())
    qtd_disp = int(qtd_s[(st_s == 'DISPONÍVEL') & (cd_s.isin(['NOVO', 'USADO - BOM', 'USADO - REGULAR']))].sum())
    qtd_uso = int(qtd_s[st_s == 'EM CAUTELA'].sum())
    mask_indisp = mask_ativos & (~((st_s == 'DISPONÍVEL') & (cd_s.isin(['NOVO', 'USADO - BOM', 'USADO - REGULAR']))) & (st_s != 'EM CAUTELA'))
    qtd_indisp = int(qtd_s[mask_indisp].sum())

    # 5. Manutenção, inoperantes ou sem movimentação (>90d)
    qtd_manut_insp = int(qtd_s[(st_s.isin(['EM MANUTENÇÃO', 'EM INSPEÇÃO'])) | (cd_s.isin(['EM MANUTENÇÃO', 'EM INSPEÇÃO']))].sum())
    qtd_inoperantes = int(qtd_s[(st_s.isin(['BLOQUEADO', 'AGUARDANDO DESCARTE', 'AGUARDANDO DECISÃO'])) | (cd_s.isin(['COM DEFEITO', 'OBSOLETO', 'DESCARTE', 'SEGREGADO']))].sum())
    qtd_sem_mov = int(qtd_s[(dias_s > 90) & mask_ativos].sum())

    st.markdown("##### 1️⃣ & 2️⃣ Quantos itens existem e qual a disponibilidade atual?")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📦 Total no Parque (Peças)", f"{total_pecas}", f"{total_lotes} lotes registrados")
    k2.metric("🟢 Disponíveis p/ Entrega", f"{qtd_disp}", f"{(qtd_disp/max(1,total_pecas))*100:.1f}% do parque")
    k3.metric("🔵 Em Uso (Em Cautela)", f"{qtd_uso}", f"{(qtd_uso/max(1,total_pecas))*100:.1f}% do parque")
    k4.metric("🔴 Indisponíveis (Triagem/Oficina/Bloq.)", f"{qtd_indisp}", f"{(qtd_indisp/max(1,total_pecas))*100:.1f}% do parque")

    st.markdown("##### 5️⃣ Quantos estão em manutenção, inoperantes ou sem movimentação?")
    m1, m2, m3 = st.columns(3)
    m1.metric("🟠 Em Manutenção / Inspeção", f"{qtd_manut_insp} un")
    m2.metric("⛔ Inoperantes (Defeito / Segregado / Obsoleto)", f"{qtd_inoperantes} un")
    m3.metric("⏳ Sem Movimentação (> 90 Dias)", f"{qtd_sem_mov} un")

    st.divider()

    # 3 & 4. Onde estão localizados e quais tipos representam a maior parte do parque?
    col_loc, col_tipo = st.columns(2)
    df_ativos_parque = df_fer[mask_ativos].copy()
    df_ativos_parque['qtd_num'] = qtd_s[mask_ativos]

    with col_loc:
        st.markdown("##### 3️⃣ Onde as ferramentas estão localizadas?")
        df_ativos_parque['local_consolidado'] = df_ativos_parque.apply(
            lambda r: f"{r.get('localizacao','N/I')} | {r.get('enderecamento_01') or 'Sem End. 01'}", axis=1
        )
        resumo_loc = df_ativos_parque.groupby('local_consolidado', as_index=False).agg(
            Lotes=('id_controle', 'count'),
            Quantidade_Pecas=('qtd_num', 'sum')
        ).sort_values(by='Quantidade_Pecas', ascending=False)
        resumo_loc['% Parque'] = (resumo_loc['Quantidade_Pecas'] / max(1, total_pecas) * 100).round(1).astype(str) + '%'
        st.dataframe(resumo_loc, use_container_width=True, hide_index=True, height=250)

    with col_tipo:
        st.markdown("##### 4️⃣ Quais tipos representam a maior parte do parque?")
        df_ativos_parque['tipo_familia'] = df_ativos_parque.apply(
            lambda r: str(r.get('descricao_d365') or r.get('descricao_ferramenta') or r.get('categoria') or 'NÃO ESPECIFICADO').strip(), axis=1
        )
        resumo_tipo = df_ativos_parque.groupby(['codigo_d365', 'tipo_familia'], as_index=False).agg(
            Lotes=('id_controle', 'count'),
            Quantidade_Pecas=('qtd_num', 'sum')
        ).sort_values(by='Quantidade_Pecas', ascending=False)
        resumo_tipo['% Parque'] = (resumo_tipo['Quantidade_Pecas'] / max(1, total_pecas) * 100).round(1).astype(str) + '%'
        st.dataframe(resumo_tipo.head(15), use_container_width=True, hide_index=True, height=250)

    st.divider()

    # 6 & 7. Qualidade de Cadastro e Situações que precisam de tratamento imediato
    col_inc, col_urg = st.columns(2)
    with col_inc:
        st.markdown("##### 6️⃣ Existem itens sem responsável, localização ou código/série?")
        sem_resp = df_ativos_parque[df_ativos_parque['responsavel_atual'].astype(str).str.strip() == '']
        sem_end = df_ativos_parque[(df_ativos_parque['enderecamento_01'].astype(str).str.strip() == '') & (df_ativos_parque['status_operacional'] == 'DISPONÍVEL')]
        sem_cod = df_ativos_parque[df_ativos_parque['codigo_d365'].astype(str).str.strip() == '']

        ic1, ic2, ic3 = st.columns(3)
        ic1.metric("👤 Sem Responsável", len(sem_resp))
        ic2.metric("📍 Disponível s/ Endereço 01", len(sem_end))
        ic3.metric("🏷️ Sem Código D365", len(sem_cod))

        df_incompletos = pd.concat([sem_resp, sem_end, sem_cod]).drop_duplicates(subset=['id_controle'])
        if not df_incompletos.empty:
            st.dataframe(
                df_incompletos[['id_controle', 'codigo_d365', 'descricao_d365', 'quantidade', 'enderecamento_01', 'responsavel_atual']],
                use_container_width=True, hide_index=True, height=190
            )
        else:
            st.success("✅ Todos os itens ativos possuem responsável, endereço e código preenchidos!")

    with col_urg:
        st.markdown("##### 7️⃣ Quais situações precisam de tratamento imediato?")
        hoje_str = datetime.now().strftime('%Y-%m-%d')
        cautelas_vencidas = pd.DataFrame()
        if not df_caut_fer.empty:
            cautelas_ativas = df_caut_fer[df_caut_fer['status'] == 'EM CAUTELA']
            cautelas_vencidas = cautelas_ativas[(cautelas_ativas['data_prevista_devolucao'].astype(str) != '') & (cautelas_ativas['data_prevista_devolucao'].astype(str) < hoje_str)]

        fila_triagem = df_ativos_parque[
            df_ativos_parque['status_operacional'].isin(['EM INSPEÇÃO', 'BLOQUEADO', 'AGUARDANDO DECISÃO', 'AGUARDANDO DESCARTE']) |
            df_ativos_parque['condicao_fisica'].isin(['COM DEFEITO', 'EM INSPEÇÃO'])
        ]

        u1, u2 = st.columns(2)
        u1.metric("🚨 Cautelas Vencidas", len(cautelas_vencidas))
        u2.metric("⚠️ Pendentes Triagem / Bloqueados", len(fila_triagem))

        alertas_urgentes = []
        for _, rc in cautelas_vencidas.iterrows():
            alertas_urgentes.append({
                'Prioridade': '🚨 CAUTELA VENCIDA',
                'ID / Alvo': rc.get('id_fer', ''),
                'Detalhe': f"Colaborador: {rc.get('colaborador','')} | Previsto: {rc.get('data_prevista_devolucao','')}",
                'Ação Imediata': 'Cobrar devolução ou renovar cautela'
            })
        for _, rf in fila_triagem.iterrows():
            alertas_urgentes.append({
                'Prioridade': '⚠️ TRIAGEM / BLOQUEIO',
                'ID / Alvo': rf.get('id_controle', ''),
                'Detalhe': f"{rf.get('descricao_d365') or rf.get('descricao_ferramenta')} ({rf.get('status_operacional')})",
                'Ação Imediata': 'Inspecionar, reparar ou baixar'
            })

        if alertas_urgentes:
            st.dataframe(pd.DataFrame(alertas_urgentes), use_container_width=True, hide_index=True, height=190)
        else:
            st.success("🎉 Nenhuma pendência crítica ou cautela atrasada no momento!")

    exibir_marca_desenvolvedor()

# ==========================================
# FUNÇÃO AUXILIAR DE MOVIMENTAÇÃO DE QUANTIDADE
# ==========================================
def _executar_movimentacao_quantidade(df_fer, id_origem, qtd_mover, novo_status, nova_condicao, nova_loc, novo_resp, novo_mat="", novo_proj="", novo_coord="", dt_entrega="", dt_devolucao="", obs_extra="", novo_end1=None, novo_end2=None, proximo_num_livre=None):
    reg_orig = df_fer[df_fer['id_controle'] == id_origem].iloc[0].to_dict()
    qtd_atual = _parse_int(reg_orig.get('quantidade', '1'), 1)
    qtd_mover = min(max(1, int(qtd_mover)), qtd_atual)
    hoje_s = datetime.now().strftime('%Y-%m-%d')

    num_seq = proximo_num_livre if proximo_num_livre is not None else (_maior_num_id_fer(df_fer) + 1)
    end1_final = novo_end1 if novo_end1 is not None else reg_orig.get('enderecamento_01', '')
    end2_final = novo_end2 if novo_end2 is not None else reg_orig.get('enderecamento_02', '')

    cod_d365 = str(reg_orig.get('codigo_d365', '')).strip()
    lote_destino_existente = pd.DataFrame()
    if cod_d365 and novo_status == "DISPONÍVEL" and nova_loc == "USADO-DISP":
        mask_consolida = (
            (df_fer['id_controle'] != id_origem) &
            (df_fer['codigo_d365'].astype(str).str.strip() == cod_d365) &
            (df_fer['status_operacional'] == "DISPONÍVEL") &
            (df_fer['condicao_fisica'] == nova_condicao) &
            (df_fer['localizacao'] == "USADO-DISP") &
            (df_fer['enderecamento_01'].astype(str).str.strip() == str(end1_final).strip()) &
            (df_fer['enderecamento_02'].astype(str).str.strip() == str(end2_final).strip())
        )
        lote_destino_existente = df_fer[mask_consolida]

    if qtd_mover < qtd_atual:
        saldo_restante = qtd_atual - qtd_mover
        supabase.table('ferramentas_usadas').update({
            'quantidade': str(saldo_restante),
            'ultima_movimentacao': hoje_s
        }).eq('id_controle', id_origem).execute()

        if not lote_destino_existente.empty:
            id_dest = lote_destino_existente.iloc[0]['id_controle']
            qtd_dest_antiga = _parse_int(lote_destino_existente.iloc[0]['quantidade'], 0)
            supabase.table('ferramentas_usadas').update({
                'quantidade': str(qtd_dest_antiga + qtd_mover),
                'ultima_movimentacao': hoje_s,
                'dias_sem_movimentacao': '0'
            }).eq('id_controle', id_dest).execute()
            return id_dest, num_seq
        else:
            id_novo = f"FER-{num_seq:06d}"
            novo_reg = reg_orig.copy()
            novo_reg['id_controle'] = id_novo
            novo_reg['quantidade'] = str(qtd_mover)
            novo_reg['status_operacional'] = novo_status
            novo_reg['condicao_fisica'] = nova_condicao
            novo_reg['localizacao'] = nova_loc
            novo_reg['enderecamento_01'] = end1_final
            novo_reg['enderecamento_02'] = end2_final
            novo_reg['responsavel_atual'] = novo_resp
            novo_reg['matricula'] = novo_mat
            if novo_proj:
                novo_reg['projeto'] = novo_proj
            if novo_coord:
                novo_reg['coordenacao'] = novo_coord
            if dt_entrega:
                novo_reg['data_entrega'] = dt_entrega
            if dt_devolucao:
                novo_reg['data_devolucao'] = dt_devolucao
            if obs_extra:
                novo_reg['observacoes'] = obs_extra
            novo_reg['ultima_movimentacao'] = hoje_s
            novo_reg['dias_sem_movimentacao'] = '0'
            supabase.table('ferramentas_usadas').insert([novo_reg]).execute()
            return id_novo, num_seq + 1
    else:
        if not lote_destino_existente.empty:
            id_dest = lote_destino_existente.iloc[0]['id_controle']
            qtd_dest_antiga = _parse_int(lote_destino_existente.iloc[0]['quantidade'], 0)
            supabase.table('ferramentas_usadas').update({
                'quantidade': str(qtd_dest_antiga + qtd_mover),
                'ultima_movimentacao': hoje_s,
                'dias_sem_movimentacao': '0'
            }).eq('id_controle', id_dest).execute()
            supabase.table('ferramentas_usadas').delete().eq('id_controle', id_origem).execute()
            return id_dest, num_seq
        else:
            upd = {
                'status_operacional': novo_status,
                'condicao_fisica': nova_condicao,
                'localizacao': nova_loc,
                'enderecamento_01': end1_final,
                'enderecamento_02': end2_final,
                'responsavel_atual': novo_resp,
                'matricula': novo_mat,
                'ultima_movimentacao': hoje_s,
                'dias_sem_movimentacao': '0'
            }
            if novo_proj:
                upd['projeto'] = novo_proj
            if novo_coord:
                upd['coordenacao'] = novo_coord
            if dt_entrega:
                upd['data_entrega'] = dt_entrega
            if dt_devolucao:
                upd['data_devolucao'] = dt_devolucao
            if obs_extra:
                upd['observacoes'] = obs_extra
            supabase.table('ferramentas_usadas').update(upd).eq('id_controle', id_origem).execute()
            return id_origem, num_seq

# ==========================================
# F1: PAINEL OPERACIONAL DE FERRAMENTAS
# ==========================================
def render_painel_ferramental(df_fer, df_mov_fer, df_caut_fer, df_manut_fer, df_baixa_fer, df_conc_d365):
    if 'saved_cols_fer' not in st.session_state:
        prefs = carregar_preferencias_colunas()
        st.session_state.saved_cols_fer = prefs.get('fer', list(COLUNAS_FERRAMENTAS))

    st.markdown("<style>div.block-container{padding-top: 1.2rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("🛠️ Painel Operacional — Ferramentas Usadas / Reutilizáveis")

    abas_principais = [
        "📋 Estoque Segmentado por Status",
        "➕ Cadastrar / Receber Ferramenta",
        "📜 Histórico de Movimentos",
        "📥 Importar / Exportar & Backup"
    ]
    if st.session_state.perfil == 'Master':
        abas_principais.append("❌ Excluir Registos (Master)")

    tabs = st.tabs(abas_principais)

    with tabs[0]:
        cf0, cf1, cf_ex, cf2, cf3, cf4 = st.columns([1.2, 1.8, 0.7, 1.0, 1.0, 0.6])
        with cf0:
            col_filtro_p = st.selectbox("Campo:", ["Todos os Campos", "Código D365", "Descrição / Nome", "ID FER", "Endereçamento 01/02"], label_visibility="collapsed", key="fp_col_fer")
        with cf1:
            fil_txt = st.text_input("🔍 Buscar:", label_visibility="collapsed", placeholder="🔍 Digite Código, Nome ou ID...")
        with cf_ex:
            fil_exato = st.checkbox("🎯 Exato", value=(col_filtro_p in ["Código D365", "ID FER"]), help="Busca exatamente o número/texto digitado.")
        with cf2:
            ends_01 = sorted([e for e in df_fer['enderecamento_01'].unique().tolist() if str(e).strip()]) if not df_fer.empty else []
            fil_end1 = st.selectbox("Endereçamento 01:", ["Todos End. 01"] + ends_01, label_visibility="collapsed")
        with cf3:
            fil_loc = st.selectbox("Localização:", ["Todas Locais"] + LISTA_LOCALIZACOES_FER, label_visibility="collapsed")
        with cf4:
            with st.popover("👁️ Colunas", use_container_width=True):
                st.caption("Selecione as colunas visíveis:")
                if st.button("🔄 Mostrar Todas", key="btn_all_fer_cols", use_container_width=True):
                    st.session_state.saved_cols_fer = list(COLUNAS_FERRAMENTAS)
                    salvar_preferencias_colunas(
                        st.session_state.get('saved_cols_inv'),
                        st.session_state.get('saved_cols_mov'),
                        st.session_state.get('saved_cols_trm'),
                        st.session_state.saved_cols_fer
                    )
                    st.rerun()
                st.multiselect(
                    "Colunas:",
                    options=COLUNAS_FERRAMENTAS,
                    default=[c for c in st.session_state.saved_cols_fer if c in COLUNAS_FERRAMENTAS],
                    key="ms_fer_key",
                    on_change=update_cols_fer,
                    label_visibility="collapsed"
                )

        cols_exibir = [c for c in st.session_state.saved_cols_fer if c in COLUNAS_FERRAMENTAS]
        if not cols_exibir:
            cols_exibir = list(COLUNAS_FERRAMENTAS)

        if not df_fer.empty:
            df_base = df_fer.copy()
            if fil_loc != "Todas Locais":
                df_base = df_base[df_base['localizacao'] == fil_loc]
            if fil_end1 != "Todos End. 01":
                df_base = df_base[df_base['enderecamento_01'] == fil_end1]
            if fil_txt.strip():
                t_up = fil_txt.strip().upper()
                if col_filtro_p == "Código D365":
                    s_alvo = df_base['codigo_d365'].astype(str).str.strip().str.upper()
                elif col_filtro_p == "ID FER":
                    s_alvo = df_base['id_controle'].astype(str).str.strip().str.upper()
                elif col_filtro_p == "Descrição / Nome":
                    s_alvo = (df_base['descricao_d365'].astype(str) + " " + df_base['descricao_ferramenta'].astype(str)).str.upper()
                elif col_filtro_p == "Endereçamento 01/02":
                    s_alvo = (df_base['enderecamento_01'].astype(str) + " " + df_base['enderecamento_02'].astype(str)).str.upper()
                else:
                    s_alvo = df_base.astype(str).apply(lambda x: " ".join(x), axis=1).str.upper()

                if fil_exato and col_filtro_p in ["Código D365", "ID FER"]:
                    df_base = df_base[s_alvo == t_up]
                elif fil_exato:
                    df_base = df_base[s_alvo.str.split().apply(lambda w: t_up in w)]
                else:
                    df_base = df_base[s_alvo.str.contains(t_up, regex=False, na=False)]

            st_s = df_base['status_operacional'].astype(str).str.upper().str.strip()
            cd_s = df_base['condicao_fisica'].astype(str).str.upper().str.strip()
            oc_s = df_base['dias_sem_movimentacao'].apply(lambda x: _parse_int(x, 0))

            df_g_disp = df_base[(st_s == 'DISPONÍVEL') & (cd_s.isin(['NOVO', 'USADO - BOM', 'USADO - REGULAR']))]
            df_g_caut = df_base[st_s == 'EM CAUTELA']
            df_g_insp = df_base[(st_s == 'EM INSPEÇÃO') | (cd_s == 'EM INSPEÇÃO')]
            df_g_manut = df_base[(st_s == 'EM MANUTENÇÃO') | (cd_s == 'EM MANUTENÇÃO')]
            df_g_def = df_base[(st_s == 'BLOQUEADO') | (cd_s == 'COM DEFEITO')]
            df_g_obs = df_base[st_s.isin(['AGUARDANDO DESCARTE', 'BAIXADO', 'AGUARDANDO DECISÃO']) | cd_s.isin(['OBSOLETO', 'DESCARTE', 'SEGREGADO'])]
            df_g_parado = df_base[(oc_s > 90) & (~st_s.isin(['BAIXADO', 'TRANSFERIDO']))]

            def _soma_qtd(d):
                return int(d['quantidade'].apply(lambda x: _parse_int(x, 1)).sum()) if not d.empty else 0

            sub_abas = st.tabs([
                f"🟢 Disponível ({_soma_qtd(df_g_disp)})",
                f"🔵 Em Cautela ({_soma_qtd(df_g_caut)})",
                f"🟡 Em Inspeção ({_soma_qtd(df_g_insp)})",
                f"🟠 Em Manutenção ({_soma_qtd(df_g_manut)})",
                f"🔴 Defeito / Bloqueado ({_soma_qtd(df_g_def)})",
                f"⚪ Obsoleto / Descarte ({_soma_qtd(df_g_obs)})",
                f"⏳ Parado > 90 Dias ({_soma_qtd(df_g_parado)})"
            ])

            grupos_lista = [df_g_disp, df_g_caut, df_g_insp, df_g_manut, df_g_def, df_g_obs, df_g_parado]
            for idx_g, sub_tab in enumerate(sub_abas):
                with sub_tab:
                    df_item_g = grupos_lista[idx_g]
                    if not df_item_g.empty:
                        df_show = df_item_g[cols_exibir].copy()
                        df_show.insert(0, "Alerta", df_item_g.apply(lambda r: formatar_badge_alerta(r.get('status_operacional',''), r.get('condicao_fisica',''), r.get('dias_sem_movimentacao', 0)), axis=1))
                        st.dataframe(df_show, use_container_width=True, hide_index=True, height=440)
                    else:
                        st.info("Nenhuma ferramenta enquadrada nesta categoria no momento.")
        else:
            st.info("Nenhuma ferramenta cadastrada na base.")

    with tabs[1]:
        st.subheader("➕ Recebimento / Cadastro de Ferramenta Usada")
        prox_id = gerar_proximo_id_fer(df_fer)
        st.info(f"💡 Próximo código físico sequencial: **`{prox_id}`**.")

        with st.form("form_cad_ferramenta"):
            c_a, c_b, c_c, c_d = st.columns(4)
            with c_a:
                id_fer_input = st.text_input("ID Controle (ID FER) *", value=prox_id)
                qtd_clones = st.number_input("Gerar quantos lotes individuais?", min_value=1, max_value=50, value=1)
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
                quantidade = st.number_input("Quantidade de Itens no Lote *", min_value=1, value=1)
                unidade = st.selectbox("Unidade", ["UN", "PC", "KIT", "CJ", "PAR", "M"])
                cond_fisica = st.selectbox("Condição Física *", LISTA_CONDICAO_FISICA, index=1)
                status_op = st.selectbox("Status Operacional *", LISTA_STATUS_OPERACIONAL, index=0)
                localizacao = st.selectbox("Localização *", LISTA_LOCALIZACOES_FER, index=0)
            with c_d:
                end_01 = st.text_input("Endereçamento 01 (Ex: US-AC1N1P9)")
                end_02 = st.text_input("Endereçamento 02 (Ex: US-AC1N1P9CX1)")
                resp_atual = st.text_input("Responsável Atual", value="ALMOXARIFADO")
                projeto = st.text_input("Projeto", value="ESTOQUE USADOS")
                coordenacao = st.text_input("Coordenação", value="LOGÍSTICA")

            c_e1, c_e2, c_e3 = st.columns([1, 1, 2])
            with c_e1:
                val_ref = st.text_input("Valor de Referência (R$)", value="0,00")
            with c_e2:
                doc_ref = st.text_input("Documento de Referência / NF")
            with c_e3:
                obs_cad = st.text_input("Observações Técnicas:")

            if st.form_submit_button("💾 Registrar Ferramenta(s) na Base", type="primary"):
                if desc_fer.strip():
                    hoje = datetime.now().strftime('%Y-%m-%d')
                    prox_insp = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
                    novos_registros, movs_iniciais = [], []
                    base_num = _maior_num_id_fer(df_fer) + 1

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
                            'enderecamento_01': end_01.strip().upper(),
                            'enderecamento_02': end_02.strip().upper(),
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
                            'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i+1:02d}",
                            'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'id_fer': id_gerado,
                            'codigo_d365': cod_d365.strip(),
                            'tipo_movimento': 'ENTRADA',
                            'localizacao_origem': 'EXTERNO / CAMPO',
                            'localizacao_destino': f"{localizacao} ({end_01.strip()} {end_02.strip()})".strip(),
                            'responsavel_origem': 'DEVOLUÇÃO / RECUPERAÇÃO',
                            'responsavel_destino': resp_atual.strip(),
                            'projeto': projeto.strip(),
                            'quantidade': str(quantidade),
                            'documento': doc_ref.strip(),
                            'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                            'observacao': f"Cadastro Inicial (Saldo: {quantidade}): {cond_fisica}"
                        })

                    supabase.table('ferramentas_usadas').upsert(novos_registros).execute()
                    supabase.table('mov_ferramentas').insert(movs_iniciais).execute()
                    st.cache_data.clear()
                    st.success(f"✅ {len(novos_registros)} registo(s) gravado(s) com sucesso!")
                    st.rerun()
                else:
                    st.error("Preencha a 'Descrição Operacional da Ferramenta'.")

    with tabs[2]:
        st.dataframe(df_mov_fer, use_container_width=True, hide_index=True, height=450)

    with tabs[3]:
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
                "Ferramentas_Usadas": df_fer, "Movimentacoes": df_mov_fer, "Cautelas": df_caut_fer,
                "Manutencoes": df_manut_fer, "Baixas_Descarte": df_baixa_fer, "Conciliacao_D365": df_conc_d365
            })
            st.download_button("📦 Backup Completo Ferramental", data=bkp_fer, file_name=f"Backup_Ferramental_Procisa_{stamp}.xlsx", type="primary", use_container_width=True)

        st.divider()
        st.subheader("📥 Importar Planilha (Padrão MASSIVO FERRAMENTAL)")
        st.caption("Reconhece automaticamente as colunas Número do item, Nome do produto, Pesquisar nome, Total, Serial, Status, Endereçamento 01 e Endereçamento 02.")
        arq_fer = st.file_uploader("Arraste a planilha Excel (.xlsx)", type=["xlsx"], key="up_fer_mass")
        if arq_fer:
            try:
                df_up_f = pd.read_excel(arq_fer)
                df_up_f.columns = [normalizar_nome_coluna(c) for c in df_up_f.columns]
                de_para_massivo = {
                    'numero_do_item': 'codigo_d365', 'nome_do_produto': 'descricao_d365',
                    'pesquisar_nome': 'descricao_ferramenta', 'total': 'quantidade',
                    'serial': 'numero_serie', 'status': 'condicao_fisica'
                }
                df_up_f = df_up_f.rename(columns=de_para_massivo)

                if 'enderecamento_01' not in df_up_f.columns:
                    df_up_f['enderecamento_01'] = ''
                else:
                    df_up_f['enderecamento_01'] = df_up_f['enderecamento_01'].fillna('').astype(str).str.strip()

                if 'enderecamento_02' not in df_up_f.columns:
                    df_up_f['enderecamento_02'] = ''
                else:
                    df_up_f['enderecamento_02'] = df_up_f['enderecamento_02'].fillna('').astype(str).str.strip()

                df_up_f['condicao_fisica'] = df_up_f['condicao_fisica'].fillna('USADO - BOM').replace('', 'USADO - BOM') if 'condicao_fisica' in df_up_f.columns else 'USADO - BOM'
                if 'status_operacional' not in df_up_f.columns:
                    df_up_f['status_operacional'] = 'DISPONÍVEL'
                if 'localizacao' not in df_up_f.columns:
                    df_up_f['localizacao'] = 'USADO-DISP'
                if 'quantidade' not in df_up_f.columns:
                    df_up_f['quantidade'] = '1'

                for c_limpar in ['marca', 'modelo', 'numero_serie', 'categoria', 'projeto', 'coordenacao']:
                    if c_limpar in df_up_f.columns:
                        df_up_f[c_limpar] = df_up_f[c_limpar].fillna('')

                base_n = _maior_num_id_fer(df_fer)
                if 'id_controle' not in df_up_f.columns:
                    df_up_f['id_controle'] = [f"FER-{base_n + idx + 1:06d}" for idx in range(len(df_up_f))]
                else:
                    faltantes_mask = df_up_f['id_controle'].isnull() | (df_up_f['id_controle'] == '')
                    df_up_f.loc[faltantes_mask, 'id_controle'] = [f"FER-{base_n + idx + 1:06d}" for idx in range(faltantes_mask.sum())]

                df_up_f['responsavel_atual'] = 'ALMOXARIFADO'
                df_up_f['data_entrada'] = datetime.now().strftime('%Y-%m-%d')
                df_up_f['ultima_movimentacao'] = datetime.now().strftime('%Y-%m-%d')
                df_up_f['dias_sem_movimentacao'] = '0'

                st.dataframe(df_up_f[['id_controle', 'codigo_d365', 'descricao_d365', 'quantidade', 'enderecamento_01', 'enderecamento_02']].head(5), use_container_width=True)
                if st.button("🚀 Confirmar Importação de Ferramentas", type="primary"):
                    if salvar_dados_massa('ferramentas_usadas', df_up_f, COLUNAS_FERRAMENTAS):
                        movs_massa = []
                        stamp_t = datetime.now().strftime('%Y%m%d%H%M%S')
                        hoje_dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        for indx, m_r in df_up_f.iterrows():
                            movs_massa.append({
                                'id_movimento': f"MVF-{stamp_t}-{indx:04d}",
                                'data': hoje_dt,
                                'id_fer': m_r['id_controle'],
                                'codigo_d365': str(m_r.get('codigo_d365', '')),
                                'tipo_movimento': 'ENTRADA',
                                'localizacao_origem': 'EXTERNO',
                                'localizacao_destino': f"{m_r.get('localizacao', 'USADO-DISP')} {m_r.get('enderecamento_01', '')} {m_r.get('enderecamento_02', '')}".strip(),
                                'responsavel_origem': 'IMPORTAÇÃO EM MASSA',
                                'responsavel_destino': 'ALMOXARIFADO',
                                'projeto': str(m_r.get('projeto', '')),
                                'quantidade': str(m_r.get('quantidade', '1')),
                                'documento': 'CARGA-INICIAL',
                                'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                                'observacao': "Carga Inicial (Saldo)"
                            })
                        supabase.table('mov_ferramentas').insert(movs_massa).execute()
                        st.success("✅ Ferramentas e Endereçamentos importados com sucesso!")
                        st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar planilha: {e}")

    if st.session_state.perfil == 'Master':
        with tabs[4]:
            if not df_fer.empty:
                df_del_f = df_fer[['id_controle', 'codigo_d365', 'descricao_ferramenta', 'quantidade', 'enderecamento_01', 'enderecamento_02', 'status_operacional']].copy()
                df_del_f.insert(0, "Excluir", False)
                df_ed_f = st.data_editor(
                    df_del_f, hide_index=True, use_container_width=True, height=400,
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
                        st.success("✅ Registos removidos!")
                        st.rerun()
            else:
                st.info("Base vazia.")

    exibir_marca_desenvolvedor()

# ==========================================
# F6: MODO OPERADOR - LEITOR QR CODE AUTOMÁTICO + FOLHA DE ETIQUETAS EM LOTE
# ==========================================
def render_operador_qrcode_fer(df_fer, df_empregados):
    st.subheader("📷 Modo Operador — Leitura Automática de QR Code (Ferramental)")
    st.caption("Ative o '📱 Scanner Ao Vivo (Auto)' no smartphone para leitura contínua automática ou utilize coletor óptico.")

    if st.session_state.get('pdf_etiquetas_fer_pronto'):
        st.success(st.session_state.pdf_etiquetas_fer_pronto['msg'])
        st.download_button(
            "📥 Baixar Folha de Etiquetas QR Code em PDF (A4 - Pronta para Impressão)",
            data=st.session_state.pdf_etiquetas_fer_pronto['bytes'],
            file_name=st.session_state.pdf_etiquetas_fer_pronto['nome'],
            mime="application/pdf",
            type="primary"
        )
        if st.button("✖️ Fechar Folha de Etiquetas"):
            st.session_state.pdf_etiquetas_fer_pronto = None
            st.rerun()
        st.divider()

    aba_bipar, aba_etiquetas = st.tabs([
        "📡 Coletor / Scanner Automático (Reconhecimento e Movimentação)",
        "🏷️ Gerador de Folha de Etiquetas QR Code em Lote (PDF A4)"
    ])

    with aba_bipar:
        render_leitor_fn = getattr(nuvem, 'render_leitor_qrcode_mobile', None)
        if render_leitor_fn:
            termo_qr = render_leitor_fn("fer_qr", "Ex: US-AC1N1P9CX1 ou FER-000001 ou 146...")
        else:
            termo_qr = st.text_input("🔫 Bipe ou Digite o Código:", placeholder="Ex: US-AC1N1P9CX1 ou FER-000001...").strip().upper()

        if termo_qr and not df_fer.empty:
            e1_s = df_fer['enderecamento_01'].fillna("").astype(str).str.strip().str.upper()
            e2_s = df_fer['enderecamento_02'].fillna("").astype(str).str.strip().str.upper()
            id_s = df_fer['id_controle'].fillna("").astype(str).str.strip().str.upper()
            d365_s = df_fer['codigo_d365'].fillna("").astype(str).str.strip().str.upper()
            ser_s = df_fer['numero_serie'].fillna("").astype(str).str.strip().str.upper()

            mask_end = (e1_s == termo_qr) | (e2_s == termo_qr)
            mask_peca = (id_s == termo_qr) | (d365_s == termo_qr) | (ser_s == termo_qr)

            if mask_end.any():
                df_encontrados = df_fer[mask_end].copy()
                qtd_total_local = int(df_encontrados['quantidade'].apply(lambda x: _parse_int(x, 1)).sum())
                st.success(f"📍 **ENDEREÇO RECONHECIDO:** `{termo_qr}` — **{len(df_encontrados)} lote(s)** armazenados neste endereço (Total: **{qtd_total_local} peças**).")
            elif mask_peca.any():
                df_encontrados = df_fer[mask_peca].copy()
                r0 = df_encontrados.iloc[0]
                st.success(
                    f"🛠️ **FERRAMENTA RECONHECIDA:** `{r0['id_controle']}` ({r0.get('descricao_d365') or r0.get('descricao_ferramenta')}) — "
                    f"Armazenada em **Endereçamento 01:** `{r0.get('enderecamento_01') or 'N/I'}` | **Endereçamento 02:** `{r0.get('enderecamento_02') or 'N/I'}`"
                )
            else:
                df_encontrados = pd.DataFrame()
                st.warning(f"⚠️ Nenhum endereço ou ferramenta encontrado com o código `{termo_qr}`.")

            if not df_encontrados.empty:
                st.markdown("##### ⚡ Marque na tabela o item localizado para executar a ação:")
                df_sel_qr = render_seletor_excel_ferramentas(df_encontrados, "qr_op_sel", multiplo=False, altura=180)

                if not df_sel_qr.empty:
                    reg_qr = df_sel_qr.iloc[0].to_dict()
                    id_sel_qr = reg_qr['id_controle']
                    max_q_qr = _parse_int(reg_qr.get('quantidade', '1'), 1)

                    tipo_acao_op = st.radio(
                        "Operação:",
                        [
                            "📦 1. Movimentação Interna de Endereço (Trocar Prateleira / Caixa por Bipe)",
                            "👷 2. Liberação Rápida / Entrega para Colaborador (Cautela)"
                        ],
                        horizontal=True
                    )

                    if tipo_acao_op.startswith("📦"):
                        with st.form("form_qr_mov_interna"):
                            cq1, cq2, cq3, cq4 = st.columns(4)
                            with cq1:
                                qtd_m_qr = st.number_input(f"Qtd a Transferir (Máx: {max_q_qr})", min_value=1, max_value=max_q_qr, value=max_q_qr)
                            with cq2:
                                novo_e1 = st.text_input("Bipar Novo Endereçamento 01:", value=reg_qr.get('enderecamento_01', ''))
                            with cq3:
                                novo_e2 = st.text_input("Bipar Novo Endereçamento 02:", value=reg_qr.get('enderecamento_02', ''))
                            with cq4:
                                nova_loc_qr = st.selectbox("Zona Operacional:", LISTA_LOCALIZACOES_FER, index=LISTA_LOCALIZACOES_FER.index(reg_qr['localizacao']) if reg_qr.get('localizacao') in LISTA_LOCALIZACOES_FER else 0)

                            obs_qr = st.text_input("Observação (Opcional):")
                            if st.form_submit_button("🚀 Confirmar Transferência de Endereço", type="primary"):
                                id_dest_qr, _ = _executar_movimentacao_quantidade(
                                    df_fer, id_sel_qr, qtd_m_qr, reg_qr.get('status_operacional', 'DISPONÍVEL'),
                                    reg_qr.get('condicao_fisica', 'USADO - BOM'), nova_loc_qr,
                                    reg_qr.get('responsavel_atual', 'ALMOXARIFADO'),
                                    novo_end1=novo_e1.strip().upper(), novo_end2=novo_e2.strip().upper()
                                )
                                supabase.table('mov_ferramentas').insert({
                                    'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                                    'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'id_fer': id_dest_qr,
                                    'codigo_d365': reg_qr.get('codigo_d365', ''),
                                    'tipo_movimento': 'TRANSFERÊNCIA',
                                    'localizacao_origem': f"{reg_qr.get('enderecamento_01', '')} / {reg_qr.get('enderecamento_02', '')}",
                                    'localizacao_destino': f"{novo_e1.strip().upper()} / {novo_e2.strip().upper()}",
                                    'responsavel_origem': st.session_state.get('nome_real', 'Operador'),
                                    'responsavel_destino': 'ALMOXARIFADO',
                                    'projeto': reg_qr.get('projeto', ''),
                                    'quantidade': str(qtd_m_qr),
                                    'documento': 'QR-SCAN',
                                    'usuario_registro': st.session_state.get('nome_real', 'Operador'),
                                    'observacao': f"Reendereçamento via Modo Operador. {obs_qr.strip()}"
                                }).execute()
                                st.cache_data.clear()
                                st.success(f"✅ {qtd_m_qr} un transferida(s) para `{novo_e1.strip().upper()}` / `{novo_e2.strip().upper()}`!")
                                st.rerun()
                    else:
                        mat_op = st.text_input("Bipe o Crachá ou Digite a Matrícula do Colaborador:")
                        mat_op_limpa = limpar_texto_matricula(mat_op)
                        emp_qr = {}
                        if mat_op_limpa and not df_empregados.empty:
                            m_eq = df_empregados[df_empregados['matricula'].astype(str) == mat_op_limpa]
                            if not m_eq.empty:
                                emp_qr = m_eq.iloc[0].fillna("").to_dict()
                                st.info(f"👤 Colaborador: **{emp_qr.get('nome')}** | Projeto: {emp_qr.get('projeto')}")

                        with st.form("form_qr_lib_cautela"):
                            cl1, cl2, cl3 = st.columns(3)
                            with cl1:
                                qtd_lib_qr = st.number_input(f"Qtd a Liberar (Máx: {max_q_qr})", min_value=1, max_value=max_q_qr, value=1)
                            with cl2:
                                nome_col_qr = st.text_input("Nome do Colaborador *", value=emp_qr.get('nome', ''))
                            with cl3:
                                proj_col_qr = st.text_input("Projeto *", value=emp_qr.get('projeto', ''))

                            if st.form_submit_button("🚀 Liberar Ferramenta para o Colaborador", type="primary"):
                                if nome_col_qr.strip():
                                    hoje_s = datetime.now().strftime('%Y-%m-%d')
                                    stamp_q = datetime.now().strftime('%Y%m%d%H%M%S')
                                    id_caut_q = f"CAU-{stamp_q}-QR"
                                    id_ent_qr, _ = _executar_movimentacao_quantidade(
                                        df_fer, id_sel_qr, qtd_lib_qr, "EM CAUTELA",
                                        reg_qr.get('condicao_fisica', 'USADO - BOM'), "CAMPO / COLABORADOR",
                                        nome_col_qr.strip(), novo_mat=mat_op_limpa, novo_proj=proj_col_qr.strip(),
                                        novo_coord=emp_qr.get('unidade', ''), dt_entrega=hoje_s
                                    )
                                    supabase.table('cautelas_ferramentas').insert({
                                        'id_cautela': id_caut_q,
                                        'id_fer': id_ent_qr,
                                        'codigo_d365': reg_qr.get('codigo_d365', ''),
                                        'colaborador': nome_col_qr.strip(),
                                        'matricula': mat_op_limpa,
                                        'projeto': proj_col_qr.strip(),
                                        'coordenacao': emp_qr.get('unidade', ''),
                                        'data_entrega': hoje_s,
                                        'condicao_entrega': reg_qr.get('condicao_fisica', 'USADO - BOM'),
                                        'data_prevista_devolucao': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                                        'data_efetiva_devolucao': '',
                                        'condicao_devolucao': '',
                                        'status': 'EM CAUTELA',
                                        'observacao': f"[TRM-QR-{stamp_q}] Qtd: {qtd_lib_qr} (Liberado via Modo Operador)"
                                    }).execute()
                                    supabase.table('mov_ferramentas').insert({
                                        'id_movimento': f"MVF-{stamp_q}-QR",
                                        'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                        'id_fer': id_ent_qr,
                                        'codigo_d365': reg_qr.get('codigo_d365', ''),
                                        'tipo_movimento': 'CAUTELA',
                                        'localizacao_origem': f"{reg_qr.get('enderecamento_01', '')} / {reg_qr.get('enderecamento_02', '')}",
                                        'localizacao_destino': 'CAMPO / COLABORADOR',
                                        'responsavel_origem': 'ALMOXARIFADO',
                                        'responsavel_destino': nome_col_qr.strip(),
                                        'projeto': proj_col_qr.strip(),
                                        'quantidade': str(qtd_lib_qr),
                                        'documento': id_caut_q,
                                        'usuario_registro': st.session_state.get('nome_real', 'Operador'),
                                        'observacao': f"Entrega via Modo Operador QR ({qtd_lib_qr} un)"
                                    }).execute()
                                    st.cache_data.clear()
                                    st.success(f"✅ Ferramenta `{id_ent_qr}` ({qtd_lib_qr} un) liberada para {nome_col_qr.strip()}!")
                                    st.rerun()
                                else:
                                    st.error("Informe o colaborador.")

    with aba_etiquetas:
        st.markdown("###### 🖨️ Impressão em Lote de Folha de Etiquetas QR Code (PDF A4 - 21 Etiquetas por Folha)")
        modo_lote_qr = st.radio(
            "Selecione o Tipo de Folha de Etiquetas:",
            [
                "📍 1. Etiquetas de ENDEREÇAMENTO 01 e 02 (Prateleiras e Caixas da Planilha)",
                "🛠️ 2. Etiquetas Individuais de FERRAMENTAS (Busca Estilo Excel)",
                "✍️ 3. Etiquetas Avulsas / Novos Endereços Personalizados"
            ],
            horizontal=False
        )

        etiquetas_para_gerar = []

        if modo_lote_qr.startswith("📍"):
            ends_map = {}
            if not df_fer.empty:
                for _, r in df_fer.iterrows():
                    e1 = str(r.get('enderecamento_01', '')).strip().upper()
                    e2 = str(r.get('enderecamento_02', '')).strip().upper()
                    if e1:
                        ends_map[e1] = ends_map.get(e1, {'tipo': 'ENDEREÇAMENTO 01', 'lotes': 0, 'vinculo': e2})
                        ends_map[e1]['lotes'] += 1
                    if e2:
                        ends_map[e2] = ends_map.get(e2, {'tipo': 'ENDEREÇAMENTO 02', 'lotes': 0, 'vinculo': f"Estante: {e1}" if e1 else ""})
                        ends_map[e2]['lotes'] += 1

            lista_op_ends = sorted(list(ends_map.keys()))
            if not lista_op_ends:
                st.warning("Nenhum Endereçamento 01 ou 02 preenchido na base ainda.")
            else:
                filtro_tipo_end = st.radio("Filtrar nível de endereço:", ["Ambos (Endereçamento 01 + 02)", "Apenas Endereçamento 01 (Estantes/Prateleiras)", "Apenas Endereçamento 02 (Caixas/Gavetas)"], horizontal=True)
                opcoes_filtradas = [
                    k for k in lista_op_ends
                    if filtro_tipo_end.startswith("Ambos")
                    or (filtro_tipo_end.startswith("Apenas Endereçamento 01") and ends_map[k]['tipo'] == 'ENDEREÇAMENTO 01')
                    or (filtro_tipo_end.startswith("Apenas Endereçamento 02") and ends_map[k]['tipo'] == 'ENDEREÇAMENTO 02')
                ]
                selecionados_end = st.multiselect(
                    f"Endereços selecionados ({len(opcoes_filtradas)} encontrados):",
                    options=opcoes_filtradas,
                    default=opcoes_filtradas
                )
                for cod_e in selecionados_end:
                    info_e = ends_map[cod_e]
                    etiquetas_para_gerar.append({
                        'codigo': cod_e,
                        'tipo': info_e['tipo'],
                        'subtitulo': f"{info_e['vinculo']} ({info_e['lotes']} lotes)".strip()
                    })

        elif modo_lote_qr.startswith("🛠️"):
            if not df_fer.empty:
                st.markdown("Marque na tabela abaixo as ferramentas para gerar etiquetas:")
                df_sel_etq = render_seletor_excel_ferramentas(df_fer, "etq_lote_fer", multiplo=True, altura=220)
                for _, r_f in df_sel_etq.iterrows():
                    etiquetas_para_gerar.append({
                        'codigo': r_f['id_controle'],
                        'tipo': f"D365: {r_f.get('codigo_d365', '')} | {r_f.get('enderecamento_01', '')}",
                        'subtitulo': str(r_f.get('descricao_d365') or r_f.get('descricao_ferramenta', ''))
                    })

        else:
            txt_livre = st.text_area("Digite os códigos (um por linha):", value="US-AC1N1P9\nUS-AC1N1P9CX1")
            sub_livre = st.text_input("Subtítulo padrão:", value="ALMOXARIFADO FERRAMENTAL")
            cods_livres = [c.strip().upper() for c in txt_livre.replace(",", "\n").split("\n") if c.strip()]
            for cl in cods_livres:
                etiquetas_para_gerar.append({'codigo': cl, 'tipo': 'ENDEREÇO / LOCAL', 'subtitulo': sub_livre.strip()})

        if etiquetas_para_gerar:
            if st.button(f"🖨️ Gerar Folha de Etiquetas em PDF ({len(etiquetas_para_gerar)} etiquetas)", type="primary"):
                with st.spinner("Montando grade de QR Codes no PDF A4..."):
                    caminho_pdf_qr = gerar_etiquetas_qrcode_pdf(etiquetas_para_gerar)
                    with open(caminho_pdf_qr, "rb") as f_q:
                        st.session_state.pdf_etiquetas_fer_pronto = {
                            'bytes': f_q.read(),
                            'nome': f"Folha_Etiquetas_QR_Ferramental_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            'msg': f"✅ Folha A4 com {len(etiquetas_para_gerar)} etiquetas QR Code gerada!"
                        }
                    st.rerun()

    exibir_marca_desenvolvedor()

# ==========================================
# F2: FLUXO DE INSPEÇÃO E MOVIMENTAÇÃO (COM BUSCA ESTILO EXCEL)
# ==========================================
def render_inspecao_movimentacao_fer(df_fer):
    st.subheader("🔍 Fluxo de Inspeção, Classificação e Movimentação por Quantidade")

    aba_triagem, aba_mov_geral = st.tabs([
        "🟡 Fila de Inspeção e Decisão Técnica",
        "🔄 Movimentação / Transferência (Busca Estilo Excel)"
    ])

    with aba_triagem:
        st.markdown("###### 1️⃣ Filtre e marque a ferramenta para Inspecionar / Decidir:")
        df_sel_insp = render_seletor_excel_ferramentas(df_fer, "insp_fer", multiplo=False, altura=210)

        if not df_sel_insp.empty:
            reg = df_sel_insp.iloc[0].to_dict()
            id_fer_real = reg['id_controle']
            qtd_max_insp = _parse_int(reg.get('quantidade', '1'), 1)

            decisao = st.radio(
                "Decisão da Inspeção:",
                [
                    "🟢 1. APROVAR (USADO - BOM/REGULAR → DISPONÍVEL em USADO-DISP)",
                    "🟠 2. ENVIAR PARA MANUTENÇÃO (EM MANUTENÇÃO → USADO-MANUT)",
                    "🔴 3. REPROVAR / COM DEFEITO (COM DEFEITO → BLOQUEADO em USADO-DEFEITO)",
                    "⚪ 4. SEGREGAR / OBSOLETO (SEGREGADO/OBSOLETO para Baixa/Descarte)"
                ]
            )

            with st.form("form_decisao_inspecao"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    qtd_inspecionada = st.number_input(f"Quantidade Inspecionada (Máx: {qtd_max_insp})", min_value=1, max_value=qtd_max_insp, value=qtd_max_insp)
                    if decisao.startswith("🟢"):
                        cond_sug = st.selectbox("Classificação Física:", ["USADO - BOM", "USADO - REGULAR", "NOVO"])
                        st_sug, loc_sug, tipo_mv = "DISPONÍVEL", "USADO-DISP", "LIBERAÇÃO"
                    elif decisao.startswith("🟠"):
                        cond_sug, st_sug, loc_sug, tipo_mv = "EM MANUTENÇÃO", "EM MANUTENÇÃO", "USADO-MANUT", "ENVIO PARA MANUTENÇÃO"
                    elif decisao.startswith("🔴"):
                        cond_sug, st_sug, loc_sug, tipo_mv = "COM DEFEITO", "BLOQUEADO", "USADO-DEFEITO", "SEGREGAÇÃO"
                    else:
                        cond_sug = st.selectbox("Classificação Física:", ["SEGREGADO", "OBSOLETO", "DESCARTE"])
                        st_sug = "AGUARDANDO DESCARTE" if cond_sug != "SEGREGADO" else "AGUARDANDO DECISÃO"
                        loc_sug = "USADO-SEGREGADO" if cond_sug == "SEGREGADO" else "USADO-OBSOLETO"
                        tipo_mv = "SEGREGAÇÃO"
                with c2:
                    loc_final = st.selectbox("Endereço Operacional:", LISTA_LOCALIZACOES_FER, index=LISTA_LOCALIZACOES_FER.index(loc_sug))
                    end1_insp = st.text_input("Endereçamento 01:", value=reg.get('enderecamento_01', ''))
                with c3:
                    end2_insp = st.text_input("Endereçamento 02:", value=reg.get('enderecamento_02', ''))
                    obs_insp = st.text_input("Observação da Inspeção:")

                if st.form_submit_button("✅ Aplicar Classificação na Quantidade Informada", type="primary"):
                    id_gerado, _ = _executar_movimentacao_quantidade(
                        df_fer, id_fer_real, qtd_inspecionada, st_sug, cond_sug, loc_final,
                        "ALMOXARIFADO", obs_extra=obs_insp.strip(),
                        novo_end1=end1_insp.strip().upper(), novo_end2=end2_insp.strip().upper()
                    )
                    supabase.table('mov_ferramentas').insert({
                        'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'id_fer': id_gerado,
                        'codigo_d365': reg.get('codigo_d365', ''),
                        'tipo_movimento': tipo_mv,
                        'localizacao_origem': reg.get('localizacao', ''),
                        'localizacao_destino': f"{loc_final} ({end1_insp.strip()} {end2_insp.strip()})".strip(),
                        'responsavel_origem': reg.get('responsavel_atual', ''),
                        'responsavel_destino': 'ALMOXARIFADO',
                        'projeto': reg.get('projeto', ''),
                        'quantidade': str(qtd_inspecionada),
                        'documento': reg.get('documento_referencia', ''),
                        'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                        'observacao': f"Inspeção ({qtd_inspecionada} un): {cond_sug} -> {st_sug}. {obs_insp.strip()}"
                    }).execute()
                    st.cache_data.clear()
                    st.success(f"✅ Quantidade ({qtd_inspecionada}) classificada como {st_sug}!")
                    st.rerun()

    with aba_mov_geral:
        st.markdown("###### 1️⃣ Busque (Estilo Excel) e marque o(s) item(ns) para movimentar:")
        df_sel_mv = render_seletor_excel_ferramentas(df_fer, "mov_fer_excel", multiplo=True, altura=220)

        if not df_sel_mv.empty:
            qtds_mv_map = {}
            st.markdown("###### 2️⃣ Informe a quantidade a movimentar de cada item marcado:")
            cols_qm = st.columns(2)
            for idx_m, (_, r_m) in enumerate(df_sel_mv.iterrows()):
                id_f_m = r_m['id_controle']
                max_q_m = _parse_int(r_m.get('quantidade', '1'), 1)
                with cols_qm[idx_m % 2]:
                    qtds_mv_map[id_f_m] = st.number_input(
                        f"Cód {r_m.get('codigo_d365')} - {r_m.get('descricao_d365') or r_m.get('descricao_ferramenta')} (Máx: {max_q_m})",
                        min_value=1, max_value=max_q_m, value=1, key=f"q_mv_ex_{id_f_m}"
                    )

            r_mv0 = df_sel_mv.iloc[0].to_dict()
            with st.form("form_mov_fer_avulso"):
                cm1, cm2, cm3 = st.columns(3)
                with cm1:
                    t_mov = st.selectbox("Tipo de Movimento:", LISTA_TIPOS_MOV_FER)
                    loc_dest = st.selectbox("Localização Destino:", LISTA_LOCALIZACOES_FER)
                with cm2:
                    idx_st = LISTA_STATUS_OPERACIONAL.index(r_mv0['status_operacional']) if r_mv0['status_operacional'] in LISTA_STATUS_OPERACIONAL else 0
                    idx_cd = LISTA_CONDICAO_FISICA.index(r_mv0['condicao_fisica']) if r_mv0['condicao_fisica'] in LISTA_CONDICAO_FISICA else 1
                    st_novo = st.selectbox("Novo Status Operacional:", LISTA_STATUS_OPERACIONAL, index=idx_st)
                    cd_nova = st.selectbox("Condição Física:", LISTA_CONDICAO_FISICA, index=idx_cd)
                    end1_mv = st.text_input("Endereçamento 01 Destino:", value=r_mv0.get('enderecamento_01', ''))
                with cm3:
                    end2_mv = st.text_input("Endereçamento 02 Destino:", value=r_mv0.get('enderecamento_02', ''))
                    resp_dest = st.text_input("Responsável Destino:", value=r_mv0.get('responsavel_atual', 'ALMOXARIFADO'))
                    proj_dest = st.text_input("Projeto:", value=r_mv0.get('projeto', ''))

                obs_mv = st.text_input("Observação do Movimento:")

                if st.form_submit_button(f"🚀 Confirmar Movimentação ({len(df_sel_mv)} item/itens)", type="primary"):
                    prox_seq = _maior_num_id_fer(df_fer) + 1
                    stamp_m = datetime.now().strftime('%Y%m%d%H%M%S')
                    for idx_k, (id_f_k, qtd_k) in enumerate(qtds_mv_map.items(), start=1):
                        r_atual = df_sel_mv[df_sel_mv['id_controle'] == id_f_k].iloc[0].to_dict()
                        id_movimentado, prox_seq = _executar_movimentacao_quantidade(
                            df_fer, id_f_k, qtd_k, st_novo, cd_nova, loc_dest,
                            resp_dest.strip(), novo_proj=proj_dest.strip(), obs_extra=obs_mv.strip(),
                            novo_end1=end1_mv.strip().upper(), novo_end2=end2_mv.strip().upper(),
                            proximo_num_livre=prox_seq
                        )
                        supabase.table('mov_ferramentas').insert({
                            'id_movimento': f"MVF-{stamp_m}-{idx_k:02d}",
                            'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'id_fer': id_movimentado,
                            'codigo_d365': r_atual.get('codigo_d365', ''),
                            'tipo_movimento': t_mov,
                            'localizacao_origem': f"{r_atual.get('localizacao', '')} ({r_atual.get('enderecamento_01', '')})",
                            'localizacao_destino': f"{loc_dest} ({end1_mv.strip()} {end2_mv.strip()})",
                            'responsavel_origem': r_atual.get('responsavel_atual', ''),
                            'responsavel_destino': resp_dest.strip(),
                            'projeto': proj_dest.strip(),
                            'quantidade': str(qtd_k),
                            'documento': '',
                            'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                            'observacao': obs_mv.strip()
                        }).execute()
                    st.session_state["sel_excel_ids_mov_fer_excel"] = set()
                    st.cache_data.clear()
                    st.success("✅ Movimentação concluída com sucesso!")
                    st.rerun()

    exibir_marca_desenvolvedor()

# ==========================================
# F3: CONTROLE DE CAUTELA MÚLTIPLA (COM SELETOR ESTILO EXCEL) E REIMPRESSÃO
# ==========================================
def render_cautela_ferramentas(df_fer, df_caut_fer, df_empregados):
    st.subheader("👷 Controle de Cautela (Seleção Estilo Excel, Devolução por Quantidade e Reimpressão)")

    if st.session_state.get('pdf_cautela_fer'):
        st.success(st.session_state.pdf_cautela_fer.get('msg', "✅ Termo de Responsabilidade pronto para download!"))
        st.download_button(
            "📥 Baixar Termo de Cautela PDF (PROCISA FR-RH-P-026)",
            data=st.session_state.pdf_cautela_fer['bytes'],
            file_name=st.session_state.pdf_cautela_fer['nome'],
            mime="application/pdf",
            type="primary"
        )
        if st.button("✖️ Fechar Aviso de PDF"):
            st.session_state.pdf_cautela_fer = None
            st.rerun()
        st.divider()

    aba_entrega, aba_devolucao, aba_reimpressao, aba_hist_caut = st.tabs([
        "📤 Nova Entrega / Cautela Múltipla",
        "📥 Registrar Devolução (Total ou Parcial)",
        "🖨️ Termos Emitidos (Reimpressão 2ª Via)",
        "📋 Histórico Geral de Cautelas"
    ])

    with aba_entrega:
        fer_disponiveis = df_fer[
            (df_fer['status_operacional'] == 'DISPONÍVEL') &
            (df_fer['condicao_fisica'].isin(['NOVO', 'USADO - BOM', 'USADO - REGULAR'])) &
            (df_fer['quantidade'].apply(lambda x: _parse_int(x, 0)) > 0)
        ].copy() if not df_fer.empty else pd.DataFrame()

        if fer_disponiveis.empty:
            st.warning("⚠️ Não há ferramentas com status 'DISPONÍVEL' e saldo positivo no momento.")
        else:
            st.markdown("###### 1️⃣ Busque (Estilo Filtro Excel) e marque na tabela as ferramentas a entregar:")
            df_itens_selecionados = render_seletor_excel_ferramentas(fer_disponiveis, "cautela_entrega_excel", multiplo=True, altura=220)

            mat_busca = st.text_input("2️⃣ Digite a Matrícula do Colaborador e pressione Enter:")
            mat_limpa = limpar_texto_matricula(mat_busca)
            emp_info = {}
            if mat_limpa and not df_empregados.empty:
                m_e = df_empregados[df_empregados['matricula'].astype(str) == mat_limpa]
                if not m_e.empty:
                    emp_info = m_e.iloc[0].fillna("").to_dict()
                    st.success(f"👤 Colaborador: **{emp_info.get('nome')}** | Projeto: {emp_info.get('projeto')} | Unidade: {emp_info.get('unidade')}")
                else:
                    st.warning("⚠️ Matrícula não localizada na base.")

            qtds_entregar = {}
            if not df_itens_selecionados.empty:
                st.markdown("###### 3️⃣ Informe a quantidade a debitar de cada ferramenta marcada:")
                cols_q = st.columns(2)
                for idx, (_, row_sel) in enumerate(df_itens_selecionados.iterrows()):
                    id_fer = row_sel['id_controle']
                    saldo_val = _parse_int(row_sel.get('quantidade', '1'), 1)
                    resumo_item = f"Cód D365: {row_sel.get('codigo_d365')} - {row_sel.get('descricao_d365') or row_sel.get('descricao_ferramenta')} [{id_fer}]"
                    with cols_q[idx % 2]:
                        qtds_entregar[id_fer] = st.number_input(
                            f"{resumo_item} (Máx: {saldo_val})",
                            min_value=1, max_value=saldo_val, value=1, key=f"qtd_caut_{id_fer}"
                        )

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

                obs_caut = st.text_input("Observações da Entrega / Acessórios:")
                gerar_pdf_chk = st.checkbox("Gerar Termo de Responsabilidade Único em PDF (Inclui todas as ferramentas marcadas)", value=True)

                if st.form_submit_button("🚀 Confirmar Cautela Múltipla e Debitar Quantidades", type="primary"):
                    if col_nome.strip() and not df_itens_selecionados.empty:
                        try:
                            hoje_s = dt_ent.strftime('%Y-%m-%d')
                            agora_full = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            stamp_lote = datetime.now().strftime('%Y%m%d%H%M%S')
                            termo_lote_id = f"TRM-FER-{stamp_lote}"

                            prox_num = _maior_num_id_fer(df_fer) + 1
                            updates_existentes = []
                            novos_fer_inserir = []
                            cautelas_inserir = []
                            movs_inserir = []
                            lista_fakes_pdf = []

                            for idx_item, (id_fer_sel, qtd_entregar) in enumerate(qtds_entregar.items(), start=1):
                                reg_f = fer_disponiveis[fer_disponiveis['id_controle'] == id_fer_sel].iloc[0].to_dict()
                                qtd_estoque_max = _parse_int(reg_f.get('quantidade', '1'), 1)
                                qtd_entregar = min(int(qtd_entregar), qtd_estoque_max)

                                id_caut_unico = f"CAU-{stamp_lote}-{idx_item:02d}"

                                if qtd_entregar < qtd_estoque_max:
                                    saldo_restante = qtd_estoque_max - qtd_entregar
                                    updates_existentes.append((id_fer_sel, {
                                        'quantidade': str(saldo_restante),
                                        'ultima_movimentacao': hoje_s
                                    }))

                                    id_entregue = f"FER-{prox_num:06d}"
                                    prox_num += 1

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
                                    novo_reg['documento_referencia'] = termo_lote_id
                                    novos_fer_inserir.append(novo_reg)
                                else:
                                    id_entregue = id_fer_sel
                                    updates_existentes.append((id_fer_sel, {
                                        'status_operacional': 'EM CAUTELA',
                                        'localizacao': 'CAMPO / COLABORADOR',
                                        'responsavel_atual': col_nome.strip(),
                                        'matricula': col_mat.strip(),
                                        'projeto': col_proj.strip(),
                                        'coordenacao': col_coord.strip(),
                                        'data_entrega': hoje_s,
                                        'ultima_movimentacao': hoje_s,
                                        'dias_sem_movimentacao': '0',
                                        'documento_referencia': termo_lote_id
                                    }))

                                obs_final_caut = f"[{termo_lote_id}] Qtd: {qtd_entregar}" + (f" | {obs_caut.strip()}" if obs_caut.strip() else "")
                                cautelas_inserir.append({
                                    'id_cautela': id_caut_unico,
                                    'id_fer': id_entregue,
                                    'codigo_d365': str(reg_f.get('codigo_d365', '')),
                                    'colaborador': col_nome.strip(),
                                    'matricula': col_mat.strip(),
                                    'projeto': col_proj.strip(),
                                    'coordenacao': col_coord.strip(),
                                    'data_entrega': hoje_s,
                                    'condicao_entrega': str(reg_f.get('condicao_fisica', 'USADO - BOM')),
                                    'data_prevista_devolucao': dt_prev.strftime('%Y-%m-%d'),
                                    'data_efetiva_devolucao': '',
                                    'condicao_devolucao': '',
                                    'status': 'EM CAUTELA',
                                    'observacao': obs_final_caut
                                })

                                movs_inserir.append({
                                    'id_movimento': f"MVF-{stamp_lote}-{idx_item:02d}",
                                    'data': agora_full,
                                    'id_fer': id_entregue,
                                    'codigo_d365': str(reg_f.get('codigo_d365', '')),
                                    'tipo_movimento': 'CAUTELA',
                                    'localizacao_origem': str(reg_f.get('localizacao', 'USADO-DISP')),
                                    'localizacao_destino': 'CAMPO / COLABORADOR',
                                    'responsavel_origem': 'ALMOXARIFADO',
                                    'responsavel_destino': col_nome.strip(),
                                    'projeto': col_proj.strip(),
                                    'quantidade': str(qtd_entregar),
                                    'documento': termo_lote_id,
                                    'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                                    'observacao': f"Entrega em cautela ({qtd_entregar} un) para {col_nome.strip()}"
                                })

                                lista_fakes_pdf.append({
                                    'marca': reg_f.get('marca', ''),
                                    'modelo': reg_f.get('modelo', ''),
                                    'numero_serie': reg_f.get('numero_serie', ''),
                                    'patrimonio': f"{id_entregue} (Qtd: {qtd_entregar})",
                                    'condicoes_para_uso': reg_f.get('condicao_fisica', 'USADO - BOM'),
                                    'acessorios': obs_caut.strip(),
                                    'codigo_d365': reg_f.get('codigo_d365', ''),
                                    'descricao_d365': reg_f.get('descricao_d365') or reg_f.get('descricao_ferramenta', ''),
                                    'coordenacao': col_coord.strip(),
                                    'nf_procisa': termo_lote_id
                                })

                            if novos_fer_inserir:
                                supabase.table('ferramentas_usadas').insert(novos_fer_inserir).execute()
                            for id_up, dados_up in updates_existentes:
                                supabase.table('ferramentas_usadas').update(dados_up).eq('id_controle', id_up).execute()
                            if cautelas_inserir:
                                supabase.table('cautelas_ferramentas').insert(cautelas_inserir).execute()
                            if movs_inserir:
                                supabase.table('mov_ferramentas').insert(movs_inserir).execute()

                            if gerar_pdf_chk and lista_fakes_pdf:
                                df_fake_ativo = pd.DataFrame(lista_fakes_pdf)
                                caminho = gerar_termo_pdf(
                                    termo_lote_id, col_nome.strip(), col_mat.strip(),
                                    emp_info.get('cpf', ''), emp_info.get('rg', ''),
                                    col_proj.strip(), col_coord.strip(), df_fake_ativo
                                )
                                with open(caminho, "rb") as f_pdf:
                                    st.session_state.pdf_cautela_fer = {
                                        'bytes': f_pdf.read(),
                                        'nome': f"Termo_{termo_lote_id}_{col_nome.strip().replace(' ', '_')}.pdf",
                                        'msg': f"✅ {len(lista_fakes_pdf)} ferramenta(s) entregue(s) sob o Termo {termo_lote_id}! Clique abaixo para baixar."
                                    }

                            st.session_state["sel_excel_ids_cautela_entrega_excel"] = set()
                            registrar_log_auditoria("CAUTELA MÚLTIPLA", termo_lote_id, f"{len(lista_fakes_pdf)} itens entregues para {col_nome.strip()}.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao processar cautela múltipla: {e}")
                    elif df_itens_selecionados.empty:
                        st.error("Marque pelo menos uma ferramenta na tabela acima.")
                    else:
                        st.error("Informe o nome do colaborador.")

    with aba_devolucao:
        cautelas_ativas = df_caut_fer[df_caut_fer['status'] == 'EM CAUTELA'].copy() if not df_caut_fer.empty else pd.DataFrame()
        if cautelas_ativas.empty:
            st.success("🎉 Nenhuma ferramenta pendente de devolução no momento.")
        else:
            busca_dev = st.text_input("🔍 Filtrar Cautelas Ativas (Colaborador, Matrícula, Cód D365 ou ID FER):", placeholder="Digite para filtrar rapidamente...")
            if busca_dev.strip():
                t_dv = busca_dev.strip().lower()
                cautelas_ativas = cautelas_ativas[cautelas_ativas.astype(str).apply(lambda x: x.str.lower().str.contains(t_dv, na=False)).any(axis=1)]

            st.dataframe(cautelas_ativas[['id_cautela', 'id_fer', 'codigo_d365', 'colaborador', 'matricula', 'projeto', 'data_entrega', 'observacao']], use_container_width=True, hide_index=True, height=220)
            if not cautelas_ativas.empty:
                op_dev = cautelas_ativas.apply(lambda r: f"{r['id_cautela']} | {r['id_fer']} (Cód: {r['codigo_d365']}) - {r['colaborador']} | {r['observacao']}", axis=1).tolist()
                sel_dev = st.selectbox("Selecione a Cautela para Devolução:", op_dev)
                id_caut_dev = sel_dev.split(" | ")[0]
                reg_c = cautelas_ativas[cautelas_ativas['id_cautela'] == id_caut_dev].iloc[0].to_dict()
                id_f_dev = reg_c['id_fer']

                f_dev_match = df_fer[df_fer['id_controle'] == id_f_dev] if not df_fer.empty else pd.DataFrame()
                qtd_atual_cautela = _parse_int(f_dev_match.iloc[0]['quantidade'], 1) if not f_dev_match.empty else 1

                with st.form("form_dev_cautela"):
                    cd1, cd2, cd3, cd4 = st.columns(4)
                    with cd1:
                        qtd_devolver = st.number_input(f"Qtd Devolvida (Máx: {qtd_atual_cautela})", min_value=1, max_value=qtd_atual_cautela, value=qtd_atual_cautela)
                    with cd2:
                        cond_dev = st.selectbox("Condição na Devolução:", LISTA_CONDICAO_FISICA, index=1)
                    with cd3:
                        st_pos_dev = st.selectbox("Status Após Devolução:", ["DISPONÍVEL", "EM INSPEÇÃO", "EM MANUTENÇÃO", "BLOQUEADO"], index=0)
                    with cd4:
                        loc_pos_dev = st.selectbox("Localização Destino:", LISTA_LOCALIZACOES_FER, index=0 if st_pos_dev == "DISPONÍVEL" else 1)

                    obs_dev = st.text_input("Observação no Recebimento / Avarias:")

                    if st.form_submit_button("📥 Confirmar Devolução e Recompor Saldo", type="primary"):
                        hoje_d = datetime.now().strftime('%Y-%m-%d')
                        if not f_dev_match.empty:
                            id_retorno, _ = _executar_movimentacao_quantidade(
                                df_fer, id_f_dev, qtd_devolver, st_pos_dev, cond_dev, loc_pos_dev,
                                "ALMOXARIFADO", novo_mat="", dt_devolucao=hoje_d, obs_extra=obs_dev.strip()
                            )
                        else:
                            id_retorno = id_f_dev

                        if qtd_devolver >= qtd_atual_cautela:
                            supabase.table('cautelas_ferramentas').update({
                                'data_efetiva_devolucao': hoje_d,
                                'condicao_devolucao': cond_dev,
                                'status': 'DEVOLVIDO',
                                'observacao': f"{reg_c.get('observacao', '')} | Devolvido total ({qtd_devolver})".strip(" |")
                            }).eq('id_cautela', id_caut_dev).execute()
                        else:
                            restante_caut = qtd_atual_cautela - qtd_devolver
                            supabase.table('cautelas_ferramentas').update({
                                'observacao': f"Qtd Restante em Cautela: {restante_caut} (Devolvido parcial: {qtd_devolver} em {hoje_d})"
                            }).eq('id_cautela', id_caut_dev).execute()

                        supabase.table('mov_ferramentas').insert({
                            'id_movimento': f"MVF-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'id_fer': id_retorno,
                            'codigo_d365': reg_c.get('codigo_d365', ''),
                            'tipo_movimento': 'DEVOLUÇÃO',
                            'localizacao_origem': 'CAMPO / COLABORADOR',
                            'localizacao_destino': loc_pos_dev,
                            'responsavel_origem': reg_c.get('colaborador', ''),
                            'responsavel_destino': 'ALMOXARIFADO',
                            'projeto': reg_c.get('projeto', ''),
                            'quantidade': str(qtd_devolver),
                            'documento': id_caut_dev,
                            'usuario_registro': st.session_state.get('nome_real', 'Sistema'),
                            'observacao': f"Devolução de cautela ({qtd_devolver} un - {cond_dev}). {obs_dev.strip()}"
                        }).execute()

                        st.cache_data.clear()
                        st.success(f"✅ {qtd_devolver} unidade(s) devolvida(s) e contabilizada(s) em {loc_pos_dev}!")
                        st.rerun()

    with aba_reimpressao:
        st.markdown("###### 🖨️ Central de Reimpressão de Termos de Ferramentas (Geração sob demanda)")
        if df_caut_fer.empty:
            st.info("Nenhum termo/cautela emitido até o momento.")
        else:
            df_c_reimp = df_caut_fer.copy()
            def _extrair_grupo_termo(row):
                obs = str(row.get('observacao', ''))
                if obs.startswith("[TRM-") and "]" in obs:
                    return obs.split("]")[0].replace("[", "")
                return f"{row.get('data_entrega', '')} | {row.get('colaborador', '')} ({row.get('matricula', '')})"

            df_c_reimp['grupo_termo'] = df_c_reimp.apply(_extrair_grupo_termo, axis=1)
            grupos_unicos = df_c_reimp['grupo_termo'].unique().tolist()

            opcoes_reimp = []
            mapa_grupos = {}
            for g in reversed(grupos_unicos):
                sub = df_c_reimp[df_c_reimp['grupo_termo'] == g]
                r0 = sub.iloc[0]
                label = f"📄 {g} — Colaborador: {r0.get('colaborador')} | Mat: {r0.get('matricula')} | Itens: {len(sub)} | Data: {r0.get('data_entrega')}"
                opcoes_reimp.append(label)
                mapa_grupos[label] = sub

            sel_termo_reimp = st.selectbox("Selecione o Termo Emitido para Reimprimir:", opcoes_reimp)
            df_itens_termo = mapa_grupos[sel_termo_reimp]
            st.dataframe(df_itens_termo[['id_cautela', 'id_fer', 'codigo_d365', 'colaborador', 'projeto', 'data_entrega', 'status', 'observacao']], use_container_width=True, hide_index=True)

            if st.button("🖨️ Reconstruir e Baixar 2ª Via do Termo em PDF", type="primary"):
                r_base = df_itens_termo.iloc[0].to_dict()
                mat_r = limpar_texto_matricula(r_base.get('matricula', ''))
                emp_r = {}
                if mat_r and not df_empregados.empty:
                    m_er = df_empregados[df_empregados['matricula'].astype(str) == mat_r]
                    if not m_er.empty:
                        emp_r = m_er.iloc[0].fillna("").to_dict()

                lista_pdf_reimp = []
                for _, row_c in df_itens_termo.iterrows():
                    id_f_c = row_c['id_fer']
                    cod_c = str(row_c.get('codigo_d365', '')).strip()
                    m_fer = df_fer[df_fer['id_controle'] == id_f_c] if not df_fer.empty else pd.DataFrame()
                    if m_fer.empty and cod_c and not df_fer.empty:
                        m_fer = df_fer[df_fer['codigo_d365'].astype(str).str.strip() == cod_c]

                    f_info = m_fer.iloc[0].to_dict() if not m_fer.empty else {}
                    lista_pdf_reimp.append({
                        'marca': f_info.get('marca', ''),
                        'modelo': f_info.get('modelo', ''),
                        'numero_serie': f_info.get('numero_serie', ''),
                        'patrimonio': id_f_c,
                        'condicoes_para_uso': row_c.get('condicao_entrega', 'USADO - BOM'),
                        'acessorios': str(row_c.get('observacao', '')),
                        'codigo_d365': cod_c,
                        'descricao_d365': f_info.get('descricao_d365') or f_info.get('descricao_ferramenta', ''),
                        'coordenacao': r_base.get('coordenacao', ''),
                        'nf_procisa': r_base.get('grupo_termo', '')
                    })

                df_fake_reimp = pd.DataFrame(lista_pdf_reimp)
                caminho_2via = gerar_termo_pdf(
                    r_base.get('id_cautela', ''),
                    r_base.get('colaborador', ''),
                    mat_r,
                    emp_r.get('cpf', ''),
                    emp_r.get('rg', ''),
                    r_base.get('projeto', ''),
                    r_base.get('coordenacao', ''),
                    df_fake_reimp
                )
                with open(caminho_2via, "rb") as f_pdf:
                    st.session_state.pdf_cautela_fer = {
                        'bytes': f_pdf.read(),
                        'nome': f"2Via_Termo_{r_base.get('colaborador', 'Colaborador').replace(' ', '_')}.pdf",
                        'msg': "✅ 2ª Via do Termo gerada dinamicamente! Clique abaixo para fazer o download."
                    }
                st.rerun()

    with aba_hist_caut:
        st.dataframe(df_caut_fer, use_container_width=True, hide_index=True, height=420)

    exibir_marca_desenvolvedor()

# ==========================================
# F4: MANUTENÇÃO, OBSOLESCÊNCIA E DESCARTE
# ==========================================
def render_manutencao_baixa_fer(df_fer, df_manut_fer, df_baixa_fer):
    st.subheader("🔧 Oficina / Manutenção & Controle de Obsolescência e Descarte")

    aba_manut, aba_baixa = st.tabs([
        "🟠 Histórico e Retorno de Manutenção",
        "⚪ Obsolescência, Laudo e Descarte"
    ])

    with aba_manut:
        st.markdown("###### Filtre e marque a ferramenta em manutenção:")
        df_sel_m = render_seletor_excel_ferramentas(df_fer, "manut_fer_sel", multiplo=False, altura=190)
        if not df_sel_m.empty:
            rm = df_sel_m.iloc[0].to_dict()
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

        st.dataframe(df_manut_fer, use_container_width=True, hide_index=True, height=300)

    with aba_baixa:
        st.dataframe(df_baixa_fer, use_container_width=True, hide_index=True, height=400)

    exibir_marca_desenvolvedor()

# ==========================================
# F5: DIVERGÊNCIA D365 X CONTROLE OPERACIONAL
# ==========================================
def render_conciliacao_d365_fer(df_fer, df_conc_d365):
    st.subheader("⚖️ Divergência: Saldo D365 x Saldo Operacional de Usados")
    saldos_op_map, desc_map = {}, {}
    if not df_fer.empty:
        df_validos = df_fer[~df_fer['status_operacional'].isin(['BAIXADO'])].copy()
        for _, r in df_validos.iterrows():
            cod = str(r.get('codigo_d365', '')).strip()
            if cod:
                q = _parse_int(r.get('quantidade', '1'), 1)
                saldos_op_map[cod] = saldos_op_map.get(cod, 0) + q
                if cod not in desc_map:
                    desc_map[cod] = r.get('descricao_d365') or r.get('descricao_ferramenta', '')

    with st.expander("➕ Informar / Atualizar Saldo Oficial do D365 para Comparação", expanded=False):
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
        st.dataframe(df_view_c, use_container_width=True, hide_index=True, height=400)

    exibir_marca_desenvolvedor()
