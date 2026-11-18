import streamlit as st
import pandas as pd
from datetime import datetime
import importlib

st.set_page_config(page_title="Gestão de Ativos e Ferramental - PROCISA", layout="wide")

# Ajusta o espaçamento superior global para evitar que títulos fiquem cortados pela barra fixa do Streamlit
st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)

import nuvem
import pdf_termo
import operacao
import gestor
import ferramental

importlib.reload(nuvem)
importlib.reload(pdf_termo)
importlib.reload(operacao)
importlib.reload(gestor)
importlib.reload(ferramental)

supabase = nuvem.supabase
carregar_dados = nuvem.carregar_dados
carregar_dados_ferramental = nuvem.carregar_dados_ferramental
registrar_log_auditoria = nuvem.registrar_log_auditoria
exibir_marca_desenvolvedor = nuvem.exibir_marca_desenvolvedor
calcular_dias_sem_mov = getattr(nuvem, 'calcular_dias_sem_mov', lambda x: "0")

if not supabase:
    st.warning("⚠️ Não foi possível estabelecer conexão com o banco de dados na nuvem.")
    st.stop()

df_ativos, df_mov, df_termos, df_diverg, df_usuarios, df_logs, df_empregados = carregar_dados()
df_fer, df_mov_fer, df_caut_fer, df_manut_fer, df_baixa_fer, df_conc_d365 = carregar_dados_ferramental()

# ==========================================
# VISÃO GERAL EXECUTIVA DE EQUIPAMENTOS (7 PERGUNTAS DE GESTÃO)
# ==========================================
def render_dashboard_executivo_eqp_fallback(df_ativos, df_mov, df_termos, df_diverg):
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    st.subheader("📊 Dashboard Executivo — Visão Geral de Equipamentos")
    st.caption("Respostas rápidas sobre o parque de equipamentos, disponibilidade, localização, tipos predominantes, inoperância, integridade cadastral e ações imediatas.")

    if df_ativos.empty:
        st.info("Nenhum equipamento cadastrado na base.")
        exibir_marca_desenvolvedor()
        return

    st_s = df_ativos['status_sistema'].astype(str).str.upper().str.strip()
    cd_s = df_ativos['condicoes_para_uso'].astype(str).str.upper().str.strip()
    dias_s = df_ativos['atualizado_em'].apply(lambda d: int(calcular_dias_sem_mov(d)) if str(calcular_dias_sem_mov(d)).isdigit() else 0)
    mask_ativos = st_s != 'BAIXADO'

    # 1 & 2. Quantos existem, disponíveis, em uso ou indisponíveis?
    total_eqp = len(df_ativos)
    qtd_disp = int((st_s == 'DISPONÍVEL').sum())
    qtd_uso = int((st_s == 'EM USO').sum())
    qtd_indisp = int((~st_s.isin(['DISPONÍVEL', 'EM USO'])).sum())

    # 5. Em manutenção, inoperantes ou sem movimentação
    qtd_manut = int((st_s.str.contains('MANUTEN', na=False)).sum())
    qtd_inop = int(((st_s == 'BAIXADO') | cd_s.str.contains('INSERV|REPROV|INAPTO', na=False)).sum())
    qtd_parados = int(((dias_s > 90) & mask_ativos).sum())

    st.markdown("##### 1️⃣ & 2️⃣ Quantos equipamentos existem e qual a disponibilidade?")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📦 Total de Equipamentos", total_eqp)
    k2.metric("🟢 Disponíveis", qtd_disp, f"{(qtd_disp/max(1,total_eqp))*100:.1f}% do parque")
    k3.metric("🔵 Em Uso (Em Campo)", qtd_uso, f"{(qtd_uso/max(1,total_eqp))*100:.1f}% do parque")
    k4.metric("🔴 Indisponíveis (Manut./Baixado/Trânsito)", qtd_indisp, f"{(qtd_indisp/max(1,total_eqp))*100:.1f}% do parque")

    st.markdown("##### 5️⃣ Quantos estão em manutenção, inoperantes ou sem movimentação?")
    m1, m2, m3 = st.columns(3)
    m1.metric("🟠 Em Manutenção / Laboratório", qtd_manut)
    m2.metric("⛔ Inoperantes (Reprovados / Inservíveis / Baixados)", qtd_inop)
    m3.metric("⏳ Sem Movimentação (> 90 Dias)", qtd_parados)

    st.divider()

    # 3 & 4. Onde estão localizados e quais tipos representam a maior parte do parque?
    c_loc, c_tip = st.columns(2)
    with c_loc:
        st.markdown("##### 3️⃣ Onde os equipamentos estão localizados?")
        df_loc = df_ativos.copy()
        df_loc['Local / Cautela'] = df_loc['cautela'].replace('', 'NÃO INFORMADO')
        tb_loc = df_loc.groupby(['coordenacao', 'Local / Cautela'], as_index=False).agg(Quantidade=('patrimonio', 'count')).sort_values(by='Quantidade', ascending=False)
        tb_loc['% Parque'] = (tb_loc['Quantidade'] / max(1, total_eqp) * 100).round(1).astype(str) + '%'
        st.dataframe(tb_loc, use_container_width=True, hide_index=True, height=250)

    with c_tip:
        st.markdown("##### 4️⃣ Quais tipos representam a maior parte do parque?")
        df_tip = df_ativos.copy()
        df_tip['Tipo de Equipamento'] = df_tip['equipamento'].replace('', 'NÃO ESPECIFICADO')
        tb_tip = df_tip.groupby(['Tipo de Equipamento', 'marca'], as_index=False).agg(Quantidade=('patrimonio', 'count')).sort_values(by='Quantidade', ascending=False)
        tb_tip['% Parque'] = (tb_tip['Quantidade'] / max(1, total_eqp) * 100).round(1).astype(str) + '%'
        st.dataframe(tb_tip, use_container_width=True, hide_index=True, height=250)

    st.divider()

    # 6 & 7. Qualidade Cadastral e Tratamento Imediato
    c_inc, c_urg = st.columns(2)
    with c_inc:
        st.markdown("##### 6️⃣ Existem equipamentos sem responsável, localização ou nº de série?")
        sem_caut = df_ativos[df_ativos['cautela'].astype(str).str.strip() == '']
        sem_coord = df_ativos[df_ativos['coordenacao'].astype(str).str.strip() == '']
        sem_ser = df_ativos[df_ativos['numero_serie'].astype(str).str.strip() == '']

        i1, i2, i3 = st.columns(3)
        i1.metric("👤 Sem Responsável/Cautela", len(sem_caut))
        i2.metric("📍 Sem Coordenação/Local", len(sem_coord))
        i3.metric("🏷️ Sem Número de Série", len(sem_ser))

        df_inc_all = pd.concat([sem_caut, sem_coord, sem_ser]).drop_duplicates(subset=['patrimonio'])
        if not df_inc_all.empty:
            st.dataframe(df_inc_all[['patrimonio', 'equipamento', 'marca', 'numero_serie', 'cautela', 'coordenacao']], use_container_width=True, hide_index=True, height=190)
        else:
            st.success("✅ Cadastro 100% íntegro (Todos possuem responsável, local e série)!")

    with c_urg:
        st.markdown("##### 7️⃣ Quais situações precisam de tratamento imediato?")
        div_pend = df_diverg[df_diverg['status_resolucao'] != 'Resolvido'] if not df_diverg.empty else pd.DataFrame()
        mov_pend = df_mov[df_mov['status_mov'] == 'Aguardando Conferência'] if not df_mov.empty else pd.DataFrame()
        trm_pend = df_termos[df_termos['status_termo'] == 'Pendente Impressão'] if not df_termos.empty else pd.DataFrame()

        u1, u2, u3 = st.columns(3)
        u1.metric("🚨 Divergências Abertas", len(div_pend))
        u2.metric("⏳ Movs. Aguardando Validação", len(mov_pend))
        u3.metric("🖨️ Termos s/ Impressão", len(trm_pend))

        urg_list = []
        for _, rd in div_pend.iterrows():
            urg_list.append({'Prioridade': '🚨 DIVERGÊNCIA', 'Patrimônio': rd.get('patrimonio', ''), 'Detalhe': rd.get('observacoes', ''), 'Ação': 'Tratar no Módulo 4'})
        for _, rm in mov_pend.iterrows():
            urg_list.append({'Prioridade': '⏳ VALIDAÇÃO PENDENTE', 'Patrimônio': rm.get('patrimonio', ''), 'Detalhe': f"{rm.get('tipo_mov')} -> {rm.get('destino')}", 'Ação': 'Validar no Módulo 3'})
        for _, rt in trm_pend.iterrows():
            urg_list.append({'Prioridade': '🖨️ TERMO PENDENTE', 'Patrimônio': rt.get('patrimonio', ''), 'Detalhe': f"Resp: {rt.get('responsavel')}", 'Ação': 'Imprimir no Módulo 4'})

        if urg_list:
            st.dataframe(pd.DataFrame(urg_list), use_container_width=True, hide_index=True, height=190)
        else:
            st.success("🎉 Nenhuma situação crítica pendente de tratamento imediato!")

    exibir_marca_desenvolvedor()

# ==========================================
# CONTROLE DE SESSÃO E LOGIN
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.usuario = None
    st.session_state.perfil = None
    st.session_state.nome_real = None
    st.session_state.segmento_ativo = "📦 Equipamentos & Ativos"
    st.session_state.modulo_ativo = None
    st.session_state.pdf_termo_pronto = None
    st.session_state.msg_sucesso = None

def fazer_login(usuario, senha):
    if df_usuarios.empty:
        st.error("Tabela de usuários vazia ou sem conexão com o banco.")
        return
    u_clean = str(usuario).strip()
    s_clean = str(senha).strip()
    match = df_usuarios[(df_usuarios['usuario'] == u_clean) & (df_usuarios['senha'] == s_clean)]
    if not match.empty:
        st.session_state.logged_in = True
        st.session_state.usuario = match.iloc[0]['usuario']
        st.session_state.nome_real = match.iloc[0]['nome']
        st.session_state.perfil = match.iloc[0]['perfil']
        registrar_log_auditoria("LOGIN", u_clean, f"Acesso realizado no sistema com perfil '{st.session_state.perfil}'.")
        st.rerun()
    else:
        st.error("Usuário ou senha incorretos!")

def fazer_logout():
    registrar_log_auditoria("LOGOUT", st.session_state.usuario, "Usuário encerrou a sessão.")
    st.session_state.logged_in = False
    st.session_state.usuario = None
    st.session_state.perfil = None
    st.session_state.nome_real = None
    st.session_state.modulo_ativo = None
    st.session_state.pdf_termo_pronto = None
    st.session_state.msg_sucesso = None
    st.rerun()

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>🔐 Acesso Restrito</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Sistema Integrado de Ativos e Ferramental (NUVEM)</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("form_login"):
            usuario_input = st.text_input("Usuário")
            senha_input = st.text_input("Senha", type="password")
            submit_login = st.form_submit_button("Entrar no Sistema", use_container_width=True)
            if submit_login:
                fazer_login(usuario_input, senha_input)
        exibir_marca_desenvolvedor()
    st.stop()

st.sidebar.title(f"Olá, {st.session_state.nome_real}")
st.sidebar.caption(f"Perfil: {st.session_state.perfil}")

col_sb1, col_sb2 = st.sidebar.columns(2)
with col_sb1:
    if st.button("🔄 Atualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with col_sb2:
    st.button("🚪 Sair", on_click=fazer_logout, use_container_width=True)

st.sidebar.markdown("---")
segmento = st.sidebar.radio(
    "Ambiente Operacional:",
    ["📦 Equipamentos & Ativos", "🛠️ Ferramental Usado / Reutilizável"],
    key="segmento_ativo"
)
st.sidebar.markdown("---")

opcoes_menu = []
if segmento.startswith("📦"):
    st.sidebar.subheader("Módulos: Equipamentos")
    if st.session_state.perfil == 'Master':
        opcoes_menu = [
            "0. 📊 Dashboard (Visão Geral)",
            "1. 📋 Painel (Controle de Equipamentos)", 
            "2. 📝 Solicitação de Movimentação", 
            "3. ✅ Central de Validações (Almoxarifado)", 
            "4. 📄 Gestão de Termos e Divergências",
            "5. 🔬 Diagnóstico (Laboratório)",
            "8. 📷 Modo Operador (QR Code / Endereço)",
            "6. 👥 Gestão de Usuários (Admin)",
            "7. 🛡️ Auditoria Geral (Gestor)"
        ]
    elif st.session_state.perfil == 'Operador Campo':
        opcoes_menu = [
            "2. 📝 Solicitação de Movimentação",
            "8. 📷 Modo Operador (QR Code / Endereço)"
        ]
    elif st.session_state.perfil == 'Almoxarifado':
        opcoes_menu = [
            "0. 📊 Dashboard (Visão Geral)",
            "1. 📋 Painel (Controle de Equipamentos)",
            "2. 📝 Solicitação de Movimentação", 
            "3. ✅ Central de Validações (Almoxarifado)",
            "4. 📄 Gestão de Termos e Divergências",
            "8. 📷 Modo Operador (QR Code / Endereço)"
        ]
    elif st.session_state.perfil in ['Laboratório', 'Laboratorio']:
        opcoes_menu = ["5. 🔬 Diagnóstico (Laboratório)"]
else:
    st.sidebar.subheader("Módulos: Ferramental Usado")
    if st.session_state.perfil == 'Master':
        opcoes_menu = [
            "F0. 📊 Dashboard (Visão Geral)",
            "F1. 📋 Painel (Controle Operacional)",
            "F6. 📷 Modo Operador (QR Code / Endereço)",
            "F2. 🔍 Inspeção, Triagem e Movimentação",
            "F3. 👷 Controle de Cautela (Entrega/Devolução)",
            "F4. 🔧 Manutenção, Obsolescência e Baixa",
            "F5. ⚖️ Divergência D365 x Saldo Operacional",
            "6. 👥 Gestão de Usuários (Admin)",
            "7. 🛡️ Auditoria Geral (Gestor)"
        ]
    elif st.session_state.perfil == 'Operador Campo':
        opcoes_menu = [
            "F6. 📷 Modo Operador (QR Code / Endereço)",
            "F1. 📋 Painel (Controle Operacional)",
            "F3. 👷 Controle de Cautela (Entrega/Devolução)"
        ]
    elif st.session_state.perfil == 'Almoxarifado':
        opcoes_menu = [
            "F0. 📊 Dashboard (Visão Geral)",
            "F1. 📋 Painel (Controle Operacional)",
            "F6. 📷 Modo Operador (QR Code / Endereço)",
            "F2. 🔍 Inspeção, Triagem e Movimentação",
            "F3. 👷 Controle de Cautela (Entrega/Devolução)",
            "F5. ⚖️ Divergência D365 x Saldo Operacional"
        ]
    elif st.session_state.perfil in ['Laboratório', 'Laboratorio']:
        opcoes_menu = [
            "F2. 🔍 Inspeção, Triagem e Movimentação",
            "F4. 🔧 Manutenção, Obsolescência e Baixa"
        ]

if 'modulo_ativo' not in st.session_state or st.session_state.modulo_ativo not in opcoes_menu:
    if opcoes_menu:
        st.session_state.modulo_ativo = opcoes_menu[0]

for opcao in opcoes_menu:
    tipo_botao = "primary" if st.session_state.modulo_ativo == opcao else "secondary"
    if st.sidebar.button(opcao, type=tipo_botao, use_container_width=True):
        st.session_state.modulo_ativo = opcao
        st.rerun()

if st.session_state.perfil == 'Master':
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='text-align: center; color: #888888; font-size: 0.72rem;'>"
        "Desenvolvido por<br><strong>Marcos Paulo Da Veiga Carvalho</strong>"
        "</div>",
        unsafe_allow_html=True
    )

selecao = st.session_state.modulo_ativo

if selecao:
    if selecao.startswith("0"):
        fn_dash_eqp = getattr(gestor, 'render_modulo_visao_geral', None) or getattr(gestor, 'render_dashboard_executivo', None)
        if fn_dash_eqp:
            fn_dash_eqp(df_ativos, df_mov, df_termos, df_diverg, df_empregados)
        else:
            render_dashboard_executivo_eqp_fallback(df_ativos, df_mov, df_termos, df_diverg)
    elif selecao.startswith("1"):
        fn_painel_eqp = getattr(gestor, 'render_modulo_painel', None) or getattr(gestor, 'render_modulo_dashboard', None)
        fn_painel_eqp(df_ativos, df_mov, df_termos, df_diverg, df_empregados)
    elif selecao.startswith("2"):
        operacao.render_modulo_solicitacao(df_ativos, df_empregados)
    elif selecao.startswith("3"):
        operacao.render_modulo_validacoes(df_ativos, df_mov, df_termos, df_empregados)
    elif selecao.startswith("4"):
        operacao.render_modulo_termos_divergencias(df_ativos, df_termos, df_diverg, df_empregados)
    elif selecao.startswith("5"):
        operacao.render_modulo_laboratorio(df_ativos)
    elif selecao.startswith("8"):
        operacao.render_operador_qrcode_eqp(df_ativos, df_empregados)
    elif selecao.startswith("F0"):
        ferramental.render_dashboard_ferramental(df_fer, df_mov_fer, df_caut_fer, df_manut_fer, df_baixa_fer)
    elif selecao.startswith("F1"):
        ferramental.render_painel_ferramental(df_fer, df_mov_fer, df_caut_fer, df_manut_fer, df_baixa_fer, df_conc_d365)
    elif selecao.startswith("F6"):
        ferramental.render_operador_qrcode_fer(df_fer, df_empregados)
    elif selecao.startswith("F2"):
        ferramental.render_inspecao_movimentacao_fer(df_fer)
    elif selecao.startswith("F3"):
        ferramental.render_cautela_ferramentas(df_fer, df_caut_fer, df_empregados)
    elif selecao.startswith("F4"):
        ferramental.render_manutencao_baixa_fer(df_fer, df_manut_fer, df_baixa_fer)
    elif selecao.startswith("F5"):
        ferramental.render_conciliacao_d365_fer(df_fer, df_conc_d365)
    elif selecao.startswith("6"):
        gestor.render_modulo_usuarios(df_usuarios)
    elif selecao.startswith("7"):
        dfs_todos = [df_ativos, df_mov, df_termos, df_diverg, df_logs, df_usuarios, df_empregados]
        gestor.render_modulo_auditoria(*dfs_todos)
