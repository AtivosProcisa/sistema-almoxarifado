import streamlit as st
import pandas as pd
from datetime import datetime
import nuvem

calcular_dias_sem_mov = getattr(nuvem, 'calcular_dias_sem_mov', lambda x: "0")
exibir_marca_desenvolvedor = getattr(nuvem, 'exibir_marca_desenvolvedor', lambda: None)


def _fmt_pct(valor):
    return f"{valor:.1f}%".replace(".", ",")


def _parse_int(val, default=1):
    try:
        return int(float(str(val).strip()))
    except Exception:
        return default


def _injetar_css_dashboard():
    st.markdown("""
    <style>
    .dg-card {
        background: #ffffff;
        border: 1px solid #e6ebf2;
        border-radius: 14px;
        padding: 18px 20px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
        margin-bottom: 14px;
    }
    .dg-header-card {
        background: #ffffff;
        border: 1px solid #e6ebf2;
        border-top: 4px solid #10b981;
        border-radius: 14px;
        padding: 18px 22px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
        margin-bottom: 14px;
    }
    .dg-eyebrow {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: #2563eb;
        text-transform: uppercase;
        margin-bottom: 4px;
    }
    .dg-title {
        font-size: 1.65rem;
        font-weight: 800;
        color: #0f172a;
        margin: 0 0 4px 0;
        line-height: 1.2;
    }
    .dg-subtitle {
        font-size: 0.88rem;
        color: #64748b;
        margin: 0 0 12px 0;
    }
    .dg-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
    }
    .dg-badge-ok {
        background: #ecfdf5;
        color: #059669;
        border: 1px solid #a7f3d0;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 999px;
    }
    .dg-badge-warn {
        background: #fffbeb;
        color: #d97706;
        border: 1px solid #fde68a;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 999px;
    }
    .dg-badge-crit {
        background: #fef2f2;
        color: #dc2626;
        border: 1px solid #fecaca;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 999px;
    }
    .dg-badge-neutral {
        background: #f1f5f9;
        color: #475569;
        border: 1px solid #e2e8f0;
        font-size: 0.72rem;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 999px;
    }
    .dg-kpi-label {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .dg-kpi-val {
        font-size: 1.95rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.1;
        margin-bottom: 4px;
    }
    .dg-kpi-sub {
        font-size: 0.78rem;
        font-weight: 600;
    }
    .dg-sec-title {
        font-size: 1.02rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
    }
    .dg-sec-sub {
        font-size: 0.78rem;
        color: #64748b;
        margin: 2px 0 12px 0;
    }
    .dg-pill-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 14px;
        border-radius: 10px;
        margin-bottom: 8px;
        font-size: 0.85rem;
        font-weight: 700;
    }
    .dg-prog-wrap {
        margin-bottom: 14px;
    }
    .dg-prog-head {
        display: flex;
        justify-content: space-between;
        font-size: 0.84rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 5px;
    }
    .dg-prog-track {
        width: 100%;
        height: 9px;
        background: #e2e8f0;
        border-radius: 999px;
        overflow: hidden;
    }
    .dg-prog-fill {
        height: 100%;
        border-radius: 999px;
    }
    .dg-alert-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 11px 14px;
        border-radius: 10px;
        margin-bottom: 9px;
        font-size: 0.86rem;
        font-weight: 700;
    }
    .dg-mini-eyebrow {
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 4px;
    }
    .dg-mini-title {
        font-size: 0.96rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 4px;
    }
    .dg-mini-desc {
        font-size: 0.78rem;
        color: #64748b;
        margin-bottom: 10px;
        min-height: 32px;
    }
    .dg-mini-tag {
        display: inline-block;
        font-size: 0.74rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 8px;
    }
    .dg-exec-box {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
    }
    .dg-footer {
        display: flex;
        justify-content: space-between;
        font-size: 0.74rem;
        color: #64748b;
        padding: 6px 4px 0 4px;
        border-top: 1px solid #e2e8f0;
        margin-top: 6px;
    }
    </style>
    """, unsafe_allow_html=True)


def _svg_donut(pct_disp, pct_uso, pct_indisp):
    """Gera o gráfico de rosca SVG com 3 arcos (Disponíveis, Em Uso, Indisponíveis)."""
    r = 52
    c = 2 * 3.14159265 * r  # ~326.73
    len_disp = (pct_disp / 100.0) * c
    len_uso = (pct_uso / 100.0) * c
    len_ind = (pct_indisp / 100.0) * c

    off_disp = 0
    off_uso = -len_disp
    off_ind = -(len_disp + len_uso)

    txt_pct = _fmt_pct(pct_disp)

    return f"""
    <svg width="146" height="146" viewBox="0 0 140 140" style="display:block; margin: 0 auto;">
        <circle cx="70" cy="70" r="{r}" fill="none" stroke="#e2e8f0" stroke-width="18"></circle>
        <g transform="rotate(-90 70 70)">
            <circle cx="70" cy="70" r="{r}" fill="none" stroke="#10b981" stroke-width="18"
                stroke-dasharray="{len_disp:.2f} {c:.2f}" stroke-dashoffset="{off_disp:.2f}"></circle>
            <circle cx="70" cy="70" r="{r}" fill="none" stroke="#3b82f6" stroke-width="18"
                stroke-dasharray="{len_uso:.2f} {c:.2f}" stroke-dashoffset="{off_uso:.2f}"></circle>
            <circle cx="70" cy="70" r="{r}" fill="none" stroke="#ef4444" stroke-width="18"
                stroke-dasharray="{len_ind:.2f} {c:.2f}" stroke-dashoffset="{off_ind:.2f}"></circle>
        </g>
        <text x="70" y="68" text-anchor="middle" font-size="18" font-weight="800" fill="#0f172a">{txt_pct}</text>
        <text x="70" y="84" text-anchor="middle" font-size="9" font-weight="700" fill="#64748b">DISPONÍVEL</text>
    </svg>
    """


def render_dashboard_graficos(
    df_base_in,
    df_mov=None,
    df_termos=None,
    df_diverg=None,
    df_roubo=None,
    df_descarte=None,
    modo="equipamentos"
):
    """
    Dashboard Gráficos Executivo (Equipamentos ou Ferramental).
    """
    _injetar_css_dashboard()
    st.markdown("<style>div.block-container{padding-top: 2.6rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)

    is_fer = (modo == "ferramental")
    prefix = "dg_fer_" if is_fer else "dg_eqp_"
    eyebrow = "PLATAFORMA DE CONTROLE DE FERRAMENTAL" if is_fer else "PLATAFORMA DE CONTROLE DE EQUIPAMENTOS"
    unidade_lbl = "peças" if is_fer else "equipamentos"

    if df_base_in is None or df_base_in.empty:
        st.info("Base vazia. Cadastre ou importe itens para visualizar o Dashboard Gráficos.")
        exibir_marca_desenvolvedor()
        return

    df = df_base_in.copy()

    # Padroniza colunas internas para suportar Equipamentos e Ferramental no mesmo motor
    if is_fer:
        df['_status'] = df['status_operacional'].fillna('').astype(str).str.strip()
        df['_base'] = df['coordenacao'].fillna('').astype(str).str.strip()
        df['_tipo'] = df['descricao_d365'].fillna('').astype(str).str.strip()
        df.loc[df['_tipo'] == '', '_tipo'] = df['descricao_ferramenta'].fillna('').astype(str).str.strip()
        df['_local'] = df['localizacao'].fillna('').astype(str).str.strip()
        df['_data_ref'] = df['ultima_movimentacao'].fillna('').astype(str).str.strip()
        df['_qtd'] = df['quantidade'].apply(lambda x: _parse_int(x, 1))
        df['_cond'] = df['condicao_fisica'].fillna('').astype(str).str.upper().str.strip()
        df['_resp'] = df['responsavel_atual'].fillna('').astype(str).str.strip()
        df['_id_ref'] = df['codigo_d365'].fillna('').astype(str).str.strip()
    else:
        df['_status'] = df['status_sistema'].fillna('').astype(str).str.strip()
        df['_base'] = df['coordenacao'].fillna('').astype(str).str.strip()
        df['_tipo'] = df['equipamento'].fillna('').astype(str).str.strip()
        df['_local'] = df['cautela'].fillna('').astype(str).str.strip()
        df['_data_ref'] = df['atualizado_em'].fillna('').astype(str).str.strip()
        df['_qtd'] = 1
        df['_cond'] = df['condicoes_para_uso'].fillna('').astype(str).str.upper().str.strip()
        df['_resp'] = df['cautela'].fillna('').astype(str).str.strip()
        df['_id_ref'] = df['numero_serie'].fillna('').astype(str).str.strip()

    df['_dias'] = df['_data_ref'].apply(lambda d: int(calcular_dias_sem_mov(d)) if str(calcular_dias_sem_mov(d)).isdigit() else 0)

    # ---------------------------------------------------------
    # 1. FILTROS DO PAINEL (COM LIMPAR FILTROS SEGURO)
    # ---------------------------------------------------------
    k_st = f"{prefix}f_status"
    k_bs = f"{prefix}f_base"
    k_tp = f"{prefix}f_tipo"
    k_lc = f"{prefix}f_local"
    k_pr = f"{prefix}f_periodo"

    def _limpar_filtros():
        st.session_state[k_st] = "Todos os status"
        st.session_state[k_bs] = "Todas as bases"
        st.session_state[k_tp] = "Todos os tipos"
        st.session_state[k_lc] = "Todas as localizações"
        st.session_state[k_pr] = "Todos os períodos"

    op_status = ["Todos os status"] + sorted([x for x in df['_status'].unique().tolist() if x])
    op_bases = ["Todas as bases"] + sorted([x for x in df['_base'].unique().tolist() if x])
    op_tipos = ["Todos os tipos"] + sorted([x for x in df['_tipo'].unique().tolist() if x])
    op_locais = ["Todas as localizações"] + sorted([x for x in df['_local'].unique().tolist() if x])
    op_periodos = ["Todos os períodos", "Últimos 30 dias", "Últimos 90 dias", "Sem movimento > 90 dias"]

    for k, default_v in [(k_st, "Todos os status"), (k_bs, "Todas as bases"), (k_tp, "Todos os tipos"), (k_lc, "Todas as localizações"), (k_pr, "Todos os períodos")]:
        if k not in st.session_state:
            st.session_state[k] = default_v

    # Aplica filtros selecionados
    df_f = df.copy()
    if st.session_state[k_st] != "Todos os status":
        df_f = df_f[df_f['_status'] == st.session_state[k_st]]
    if st.session_state[k_bs] != "Todas as bases":
        df_f = df_f[df_f['_base'] == st.session_state[k_bs]]
    if st.session_state[k_tp] != "Todos os tipos":
        df_f = df_f[df_f['_tipo'] == st.session_state[k_tp]]
    if st.session_state[k_lc] != "Todas as localizações":
        df_f = df_f[df_f['_local'] == st.session_state[k_lc]]
    if st.session_state[k_pr] == "Últimos 30 dias":
        df_f = df_f[df_f['_dias'] <= 30]
    elif st.session_state[k_pr] == "Últimos 90 dias":
        df_f = df_f[df_f['_dias'] <= 90]
    elif st.session_state[k_pr] == "Sem movimento > 90 dias":
        df_f = df_f[df_f['_dias'] > 90]

    # ---------------------------------------------------------
    # 2. CÁLCULO DOS INDICADORES
    # ---------------------------------------------------------
    st_up = df_f['_status'].str.upper()
    cd_up = df_f['_cond'].str.upper()
    qtd_s = df_f['_qtd']

    total_sel = int(qtd_s.sum())
    if is_fer:
        mask_disp = (st_up == 'DISPONÍVEL') & (cd_up.isin(['NOVO', 'USADO - BOM', 'USADO - REGULAR']))
        mask_uso = (st_up == 'EM CAUTELA')
    else:
        mask_disp = (st_up == 'DISPONÍVEL')
        mask_uso = (st_up == 'EM USO')

    mask_indisp = ~(mask_disp | mask_uso)

    qtd_disp = int(qtd_s[mask_disp].sum())
    qtd_uso = int(qtd_s[mask_uso].sum())
    qtd_indisp = int(qtd_s[mask_indisp].sum())

    denom = max(1, total_sel)
    pct_disp = (qtd_disp / denom) * 100.0
    pct_uso = (qtd_uso / denom) * 100.0
    pct_indisp = (qtd_indisp / denom) * 100.0

    # Alertas operacionais
    qtd_manut = int(qtd_s[st_up.str.contains('MANUTEN|INSPE', na=False)].sum())
    qtd_inop = int(qtd_s[
        st_up.isin(['BAIXADO', 'INATIVADO', 'ROUBADO/FURTADO', 'SEGREGADO PARA DESCARTE', 'BLOQUEADO', 'AGUARDANDO DESCARTE']) |
        cd_up.str.contains('INSERV|REPROV|INAPTO|DEFEITO|OBSOLETO|DESCARTE', na=False)
    ].sum())
    qtd_sem_mov = int(qtd_s[(df_f['_dias'] > 90) & (~st_up.isin(['BAIXADO', 'INATIVADO', 'ROUBADO/FURTADO']))].sum())

    # Selo dinâmico de saúde da operação
    if pct_indisp >= 20 or qtd_inop > 10:
        badge_cls, badge_txt = "dg-badge-crit", "• AÇÃO IMEDIATA"
        exec_bg, exec_fg, exec_lbl = "#fef2f2", "#dc2626", "ATENÇÃO CRÍTICA"
    elif pct_indisp >= 5 or qtd_manut > 0 or qtd_sem_mov > 0:
        badge_cls, badge_txt = "dg-badge-warn", "• OPERAÇÃO EM ATENÇÃO"
        exec_bg, exec_fg, exec_lbl = "#fffbeb", "#d97706", "ACOMPANHAMENTO"
    else:
        badge_cls, badge_txt = "dg-badge-ok", "• OPERAÇÃO ESTÁVEL"
        exec_bg, exec_fg, exec_lbl = "#dcfce7", "#059669", "SITUAÇÃO CONTROLADA"

    agora_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ---------------------------------------------------------
    # 3. CABEÇALHO EXECUTIVO
    # ---------------------------------------------------------
    st.markdown(f"""
    <div class="dg-header-card">
        <div class="dg-eyebrow">{eyebrow}</div>
        <div class="dg-title">Dashboard Executivo</div>
        <div class="dg-subtitle">Visão consolidada do parque, disponibilidade, utilização e alertas</div>
        <div class="dg-badges">
            <span class="{badge_cls}">{badge_txt}</span>
            <span class="dg-badge-neutral">Atualização: {agora_str}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # 4. BLOCO DE FILTROS DO PAINEL
    # ---------------------------------------------------------
    filtro_ativo = any([
        st.session_state[k_st] != "Todos os status",
        st.session_state[k_bs] != "Todas as bases",
        st.session_state[k_tp] != "Todos os tipos",
        st.session_state[k_lc] != "Todas as localizações",
        st.session_state[k_pr] != "Todos os períodos"
    ])
    tag_filtro = "Filtro ativo" if filtro_ativo else "Parque completo"

    with st.container(border=True):
        h_f1, h_f2 = st.columns([3, 1])
        h_f1.markdown("<span style='font-size:0.75rem;font-weight:800;color:#475569;letter-spacing:0.05em;'>FILTROS DO PAINEL</span>", unsafe_allow_html=True)
        h_f2.markdown(f"<div style='text-align:right;font-size:0.78rem;font-weight:700;color:#2563eb;'>{tag_filtro}</div>", unsafe_allow_html=True)

        f1, f2 = st.columns(2)
        with f1:
            st.selectbox("Status", op_status, key=k_st, label_visibility="collapsed")
            st.selectbox("Tipo", op_tipos, key=k_tp, label_visibility="collapsed")
            st.selectbox("Período", op_periodos, key=k_pr, label_visibility="collapsed")
        with f2:
            st.selectbox("Base", op_bases, key=k_bs, label_visibility="collapsed")
            st.selectbox("Localização", op_locais, key=k_lc, label_visibility="collapsed")
            st.button("Limpar filtros", on_click=_limpar_filtros, type="primary", use_container_width=True)

        st.caption(f"Exibindo **{total_sel}** {unidade_lbl} ({len(df_f)} registros) de um total de **{int(df['_qtd'].sum())}** na base.")

    # ---------------------------------------------------------
    # 5. CARDS DE KPI (5 INDICADORES PRINCIPAIS)
    # ---------------------------------------------------------
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(f"""
        <div class="dg-card">
            <div class="dg-kpi-label" style="color:#475569;">TOTAL DO PARQUE</div>
            <div class="dg-kpi-val">{total_sel}</div>
            <div class="dg-kpi-sub" style="color:#64748b;">{unidade_lbl.capitalize()} cadastrados</div>
        </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
        <div class="dg-card">
            <div class="dg-kpi-label" style="color:#059669;">DISPONÍVEIS</div>
            <div class="dg-kpi-val">{qtd_disp}</div>
            <div class="dg-kpi-sub" style="color:#059669;">{_fmt_pct(pct_disp)} do selecionado</div>
        </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div class="dg-card">
            <div class="dg-kpi-label" style="color:#2563eb;">EM USO / CAMPO</div>
            <div class="dg-kpi-val">{qtd_uso}</div>
            <div class="dg-kpi-sub" style="color:#2563eb;">{_fmt_pct(pct_uso)} do selecionado</div>
        </div>
        """, unsafe_allow_html=True)
    with k4:
        st.markdown(f"""
        <div class="dg-card">
            <div class="dg-kpi-label" style="color:#dc2626;">INDISPONÍVEIS</div>
            <div class="dg-kpi-val">{qtd_indisp}</div>
            <div class="dg-kpi-sub" style="color:#dc2626;">{_fmt_pct(pct_indisp)} do selecionado</div>
        </div>
        """, unsafe_allow_html=True)
    with k5:
        st.markdown(f"""
        <div class="dg-card">
            <div class="dg-kpi-label" style="color:#0d9488;">DISPONIBILIDADE</div>
            <div class="dg-kpi-val" style="color:#0f766e;">{_fmt_pct(pct_disp)}</div>
            <div class="dg-kpi-sub" style="color:#64748b;">Disponíveis ÷ total</div>
        </div>
        """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # 6. COMPOSIÇÃO DO PARQUE (ROSCA) + DISTRIBUIÇÃO POR STATUS (BARRAS)
    # ---------------------------------------------------------
    col_g1, col_g2 = st.columns([1.15, 1])

    with col_g1:
        svg_rosca = _svg_donut(pct_disp, pct_uso, pct_indisp)
        st.markdown(f"""
        <div class="dg-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
                <div>
                    <div class="dg-sec-title">Composição do Parque</div>
                    <div class="dg-sec-sub" style="margin-bottom:0;">Participação por situação atual</div>
                </div>
                <span style="background:#eff6ff;color:#2563eb;font-size:0.74rem;font-weight:700;padding:4px 10px;border-radius:999px;">
                    {total_sel} selecionados
                </span>
            </div>
            <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;margin-top:8px;">
                <div style="flex:0 0 150px;">{svg_rosca}</div>
                <div style="flex:1;min-width:190px;">
                    <div class="dg-pill-row" style="background:#ecfdf5;color:#059669;">
                        <span>• Disponíveis</span><span>{qtd_disp}</span>
                    </div>
                    <div class="dg-pill-row" style="background:#eff6ff;color:#2563eb;">
                        <span>• Em uso / Campo</span><span>{qtd_uso}</span>
                    </div>
                    <div class="dg-pill-row" style="background:#fef2f2;color:#dc2626;margin-bottom:0;">
                        <span>• Indisponíveis</span><span>{qtd_indisp}</span>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_g2:
        st.markdown(f"""
        <div class="dg-card">
            <div class="dg-sec-title">Distribuição por Status</div>
            <div class="dg-sec-sub">Comparação sobre o total selecionado</div>
            <div class="dg-prog-wrap">
                <div class="dg-prog-head">
                    <span>Disponíveis</span>
                    <span>{qtd_disp} • {_fmt_pct(pct_disp)}</span>
                </div>
                <div class="dg-prog-track">
                    <div class="dg-prog-fill" style="width:{min(100.0, pct_disp):.1f}%;background:#10b981;"></div>
                </div>
            </div>
            <div class="dg-prog-wrap">
                <div class="dg-prog-head">
                    <span>Em uso / Campo</span>
                    <span>{qtd_uso} • {_fmt_pct(pct_uso)}</span>
                </div>
                <div class="dg-prog-track">
                    <div class="dg-prog-fill" style="width:{min(100.0, pct_uso):.1f}%;background:#3b82f6;"></div>
                </div>
            </div>
            <div class="dg-prog-wrap" style="margin-bottom:4px;">
                <div class="dg-prog-head">
                    <span>Indisponíveis</span>
                    <span>{qtd_indisp} • {_fmt_pct(pct_indisp)}</span>
                </div>
                <div class="dg-prog-track">
                    <div class="dg-prog-fill" style="width:{min(100.0, pct_indisp):.1f}%;background:#ef4444;"></div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # 7. ALERTAS OPERACIONAIS + 4 CARTÕES DE INTELIGÊNCIA CONECTADOS
    # ---------------------------------------------------------
    col_al, col_4 = st.columns([1, 1.35])

    with col_al:
        st.markdown(f"""
        <div class="dg-card">
            <div class="dg-sec-title">Alertas Operacionais</div>
            <div class="dg-sec-sub">Exceções para acompanhamento</div>
            <div class="dg-alert-row" style="background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;">
                <span>Manutenção / Laboratório</span><span>{qtd_manut}</span>
            </div>
            <div class="dg-alert-row" style="background:#fef2f2;color:#991b1b;border:1px solid #fecaca;">
                <span>Inoperantes / Segregados / Baixados</span><span>{qtd_inop}</span>
            </div>
            <div class="dg-alert-row" style="background:#fefce8;color:#854d0e;border:1px solid #fef08a;margin-bottom:0;">
                <span>Sem movimento &gt; 90 dias</span><span>{qtd_sem_mov}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Métricas reais para os 4 mini-cards
    qtd_locais_unicos = len([x for x in df_f['_local'].unique().tolist() if x])
    top_local = df_f['_local'].replace('', 'Sem local').value_counts().index[0] if not df_f.empty else "N/I"

    sem_info = int(((df_f['_resp'] == '') | (df_f['_id_ref'] == '') | (df_f['_base'] == '')).sum())
    pct_integ = ((len(df_f) - sem_info) / max(1, len(df_f))) * 100.0

    total_movs = len(df_mov) if (df_mov is not None and not df_mov.empty) else 0
    movs_pend = int((df_mov['status_mov'] == 'Aguardando Conferência').sum()) if (df_mov is not None and not df_mov.empty and 'status_mov' in df_mov.columns) else 0
    trm_pend = int((df_termos['status_termo'] == 'Pendente Impressão').sum()) if (df_termos is not None and not df_termos.empty and 'status_termo' in df_termos.columns) else 0
    div_pend = int((df_diverg['status_resolucao'] != 'Resolvido').sum()) if (df_diverg is not None and not df_diverg.empty and 'status_resolucao' in df_diverg.columns) else 0
    total_pend = movs_pend + trm_pend + div_pend

    with col_4:
        m1, m2 = st.columns(2)
        with m1:
            st.markdown(f"""
            <div class="dg-card">
                <div class="dg-mini-eyebrow" style="color:#7c3aed;">LOCALIZAÇÃO</div>
                <div class="dg-mini-title">Distribuição física</div>
                <div class="dg-mini-desc">Principal: <b>{top_local[:26]}</b> ({qtd_locais_unicos} locais ativos).</div>
                <span class="dg-mini-tag" style="background:#f5f3ff;color:#6d28d9;">{qtd_locais_unicos} localizações</span>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f"""
            <div class="dg-card">
                <div class="dg-mini-eyebrow" style="color:#4f46e5;">MOVIMENTAÇÕES</div>
                <div class="dg-mini-title">Histórico operacional</div>
                <div class="dg-mini-desc">Entregas, devoluções, transferências e baixas registradas.</div>
                <span class="dg-mini-tag" style="background:#eef2ff;color:#4338ca;">{total_movs} registros na base</span>
            </div>
            """, unsafe_allow_html=True)

        with m2:
            cor_int_bg = "#ecfdf5" if sem_info == 0 else "#fffbeb"
            cor_int_fg = "#059669" if sem_info == 0 else "#d97706"
            st.markdown(f"""
            <div class="dg-card">
                <div class="dg-mini-eyebrow" style="color:#0d9488;">INTEGRIDADE CADASTRAL</div>
                <div class="dg-mini-title">Qualidade dos registros</div>
                <div class="dg-mini-desc">Série/código, responsável e base preenchidos ({sem_info} incompletos).</div>
                <span class="dg-mini-tag" style="background:{cor_int_bg};color:{cor_int_fg};">{_fmt_pct(pct_integ)} íntegro</span>
            </div>
            """, unsafe_allow_html=True)

            cor_p_bg = "#eff6ff" if total_pend == 0 else "#fef2f2"
            cor_p_fg = "#2563eb" if total_pend == 0 else "#dc2626"
            txt_pend = "Fluxo em dia" if total_pend == 0 else f"{total_pend} pendência(s) ativa(s)"
            st.markdown(f"""
            <div class="dg-card">
                <div class="dg-mini-eyebrow" style="color:#d97706;">PENDÊNCIAS</div>
                <div class="dg-mini-title">Ações por perfil</div>
                <div class="dg-mini-desc">Validações ({movs_pend}), Termos ({trm_pend}) e Divergências ({div_pend}).</div>
                <span class="dg-mini-tag" style="background:{cor_p_bg};color:{cor_p_fg};">{txt_pend}</span>
            </div>
            """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # 8. LEITURA EXECUTIVA + RODAPÉ
    # ---------------------------------------------------------
    txt_indisp = (
        "Não há registros de indisponibilidade."
        if qtd_indisp == 0
        else f"Há {qtd_indisp} {unidade_lbl} indisponíveis ({_fmt_pct(pct_indisp)}), sendo {qtd_manut} em manutenção/inspeção e {qtd_inop} inoperantes/segregados."
    )
    st.markdown(f"""
    <div class="dg-card">
        <div class="dg-exec-box">
            <div style="flex:1;min-width:260px;">
                <div class="dg-sec-title" style="margin-bottom:4px;">Leitura Executiva</div>
                <div style="font-size:0.86rem;color:#475569;line-height:1.45;">
                    O parque selecionado possui <b>{total_sel} {unidade_lbl}</b>. Atualmente, <b>{qtd_disp}</b> estão disponíveis,
                    representando <b>{_fmt_pct(pct_disp)}</b>, e <b>{qtd_uso}</b> estão em uso ou em campo ({_fmt_pct(pct_uso)}).
                    {txt_indisp}
                </div>
            </div>
            <div style="background:{exec_bg};color:{exec_fg};padding:10px 18px;border-radius:10px;font-weight:800;font-size:0.82rem;text-align:center;min-width:150px;">
                {exec_lbl}
            </div>
        </div>
    </div>
    <div class="dg-footer">
        <span>Dashboard Executivo • Controle de {'Ferramental' if is_fer else 'Equipamentos'}</span>
        <span>Perfis: Supervisor • Armazenista • Operação Procisa</span>
    </div>
    """, unsafe_allow_html=True)

    exibir_marca_desenvolvedor()
