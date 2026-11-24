import streamlit as st
import pandas as pd
from datetime import datetime
import importlib

st.set_page_config(page_title="Gestão de Ativos e Ferramental - PROCISA", layout="wide")
st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)

import nuvem
import pdf_termo
import operacao
import gestor
import ferramental
import governanca_eqp

importlib.reload(nuvem)
importlib.reload(pdf_termo)
importlib.reload(operacao)
importlib.reload(gestor)
importlib.reload(ferramental)
importlib.reload(governanca_eqp)

supabase = nuvem.supabase
carregar_dados = nuvem.carregar_dados
carregar_dados_ferramental = nuvem.carregar_dados_ferramental
registrar_log_auditoria = nuvem.registrar_log_auditoria
exibir_marca_desenvolvedor = nuvem.exibir_marca_desenvolvedor
calcular_dias_sem_mov = getattr(nuvem, 'calcular_dias_sem_mov', lambda x: "0")
normalizar_perfil = getattr(nuvem, 'normalizar_perfil', lambda p: p)

if not supabase:
    st.warning("⚠️ Não foi possível estabelecer conexão com o banco de dados na nuvem.")
    st.stop()

df_ativos, df_mov, df_termos, df_diverg, df_usuarios, df_logs, df_empregados = carregar_dados()
df_fer, df_mov_fer, df_caut_fer, df_manut_fer, df_baixa_fer, df_conc_d365 = carregar_dados_ferramental()

fn_carregar_gov = getattr(nuvem, 'carregar_dados_governanca_eqp', None)
if fn_carregar_gov:
    df_roubo, df_sem_giro, df_descarte = fn_carregar_gov()
else:
    df_roubo, df_sem_giro, df_descarte = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# ==========================================
# VISÃO GERAL EXECUTIVA DE EQUIPAMENTOS
# ==========================================
def render_dashboard_executivo_eqp_fallback(df_ativos, df_mov, df_termos, df_diverg):
    st.markdown("<style>div.block-container{padding-top: 2.8rem; padding-bottom: 1rem;}</style>", unsafe_allow_html=True)
    perfil_atual = normalizar_perfil(st.session_state.get('perfil', ''))
    st.subheader(f"📊 Dashboard — Visão Geral de Equipamentos ({perfil_atual})")

    if df_ativos.empty:
        st.info("Nenhum equipamento cadastrado na base.")
        exibir_marca_desenvolvedor()
        return

    st_s = df_ativos['status_sistema'].astype(str).str.upper().str.strip()
    cd_s = df_ativos['condicoes_para_uso'].astype(str).str.upper().str.strip()
    dias_s = df_ativos['atualizado_em'].apply(lambda d: int(calcular_dias_sem_mov(d)) if str(calcular_dias_sem_mov(d)).isdigit() else 0)
    mask_ativos = ~st_s.isin(['BAIXADO', 'ROUBADO/FURTADO', 'SEGREGADO PARA DESCARTE', 'INATIVADO'])

    total_eqp = len(df_ativos)
    qtd_disp = int((st_s == 'DISPONÍVEL').sum())
    qtd_uso = int((st_s == 'EM USO').sum())
    qtd_indisp = int((~st_s.isin(['DISPONÍVEL', 'EM USO'])).sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📦 Total de Equipamentos", total_eqp)
    k2.metric("🟢 Disponíveis", qtd_disp, f"{(qtd_disp/max(1,total_eqp))*100:.1f}%")
    k3.metric("🔵 Em Uso (Em Campo)", qtd_uso, f"{(qtd_uso/max(1,total_eqp))*100:.1f}%")
    k4.metric("🔴 Indisponíveis", qtd_indisp, f"{(qtd_indisp/max(1,total_eqp))*100:.1f}%")

    if perfil_atual != "Operação Procisa":
        qtd_manut = int((st_s.str.contains('MANUTEN', na=False)).sum())
        qtd_inop = int(((st_s.isin(['BAIXADO', 'ROUBADO/FURTADO', 'SEGREGADO PARA DESCARTE', 'INATIVADO'])) | cd_s.str.contains('INSERV|REPROV|INAPTO', na=False)).sum())
        qtd_parados = int(((dias_s > 90) & mask_ativos).sum())

        m1, m2, m3 = st.columns(3)
        m1.metric("🟠 Em Manutenção / Lab", qtd_manut)
        m2.metric("⛔ Inoperantes / Segregados / Baixados", qtd_inop)
        m3.metric("⏳ Sem Movimentação (> 90 Dias)", qtd_parados)

    st.divider()
    c_loc, c_tip = st.columns(2)
    with c_loc:
        st.markdown("##### 📍 Localização dos Equipamentos")
        df_loc = df_ativos.copy()
        df_loc['Local / Cautela'] = df_loc['cautela'].replace('', 'NÃO INFORMADO')
        tb_loc = df_loc.groupby(['coordenacao', 'Local / Cautela'], as_index=False).agg(Quantidade=('patrimonio', 'count')).sort_values(by='Quantidade', ascending=False)
        st.dataframe(tb_loc, use_container_width=True, hide_index=True, height=240)
    with c_tip:
        st.markdown("##### 🧰 Composição do Parque")
        df_tip = df_ativos.copy()
        df_tip['Tipo de Equipamento'] = df_tip['equipamento'].replace('', 'NÃO ESPECIFICADO')
        tb_tip = df_tip.groupby(['Tipo de Equipamento', 'marca'], as_index=False).agg(Quantidade=('patrimonio', 'count')).sort_values(by='Quantidade', ascending=False)
        st.dataframe(tb_tip, use_container_width=True, hide_index=True, height=240)

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
        perfil_norm = normalizar_perfil(match.iloc[0]['perfil'])
        st.session_state.logged_in = True
        st.session_state.usuario = match.iloc[0]['usuario']
        st.session_state.nome_real = match.iloc[0]['nome']
        st.session_state.perfil = perfil_norm
        registrar_log_auditoria("LOGIN", u_clean, f"Acesso realizado com perfil '{perfil_norm}'.")
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
    st.markdown("<p style='text-align: center;'>Sistema Integrado de Ativos e Ferramental (PROCISA)</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("form_login"):
            usuario_input = st.text_input("Usuário / Matrícula")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar no Sistema", use_container_width=True):
                fazer_login(usuario_input, senha_input)
        exibir_marca_desenvolvedor()
    st.stop()

perfil_user = normalizar_perfil(st.session_state.perfil)
st.session_state.perfil = perfil_user

badge_perfil = {
    "Supervisor": "👑 Nível 1 | Supervisor (Admin)",
    "Armazenista": "📦 Nível 2 | Armazenista (Operacional)",
    "Operação Procisa": "👷 Nível 3 | Operação Procisa (Solicitante)"
}.get(perfil_user, perfil_user)

st.sidebar.title(f"Olá, {st.session_state.nome_real}")
st.sidebar.caption(badge_perfil)

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
    if perfil_user == "Supervisor":
        opcoes_menu = [
            "0. 📊 Dashboard (Visão Geral)",
            "1. 📋 Painel (Controle de Equipamentos)",
            "2. 📝 Solicitação de Movimentação",
            "3. ✅ Central de Validações / Aprovações",
            "4. 📄 Gestão de Termos e Divergências",
            "5. 🔬 Diagnóstico (Laboratório)",
            "8. 📷 Modo Operador (QR Code / Endereço)",
            "9. 🚨 Roubo, Sem Giro e Descarte",
            "6. 👥 Gestão de Usuários (Admin)",
            "7. 🛡️ Auditoria Geral (Total)"
        ]
    elif perfil_user == "Armazenista":
        opcoes_menu = [
            "0. 📊 Dashboard (Operacional)",
            "1. 📋 Painel (Controle de Equipamentos)",
            "2. 📝 Solicitação de Movimentação",
            "3. ✅ Central de Validações (Execução)",
            "4. 📄 Gestão de Termos e Divergências",
            "5. 🔬 Diagnóstico (Laboratório)",
            "8. 📷 Modo Operador (QR Code / Endereço)",
            "9. 🚨 Roubo, Sem Giro e Descarte",
            "7. 🛡️ Auditoria (Consulta)"
        ]
    else:  # Operação Procisa
        opcoes_menu = [
            "0. 📊 Dashboard (Consulta)",
            "1. 📋 Painel (Consulta de Equipamentos)",
            "2. 📝 Solicitar Movimentação",
            "9. 🚨 Comunicar Roubo / Furto",
            "7. 🛡️ Minhas Movimentações"
        ]
else:
    st.sidebar.subheader("Módulos: Ferramental Usado")
    if perfil_user == "Supervisor":
        opcoes_menu = [
            "F0. 📊 Dashboard (Visão Geral)",
            "F1. 📋 Painel (Controle Operacional)",
            "F6. 📷 Modo Operador (QR Code / Endereço)",
            "F2. 🔍 Inspeção, Triagem e Movimentação",
            "F3. 👷 Controle de Cautela (Entrega/Devolução)",
            "F4. 🔧 Manutenção, Obsolescência e Baixa",
            "F5. ⚖️ Divergência D365 x Saldo Operacional",
            "6. 👥 Gestão de Usuários (Admin)",
            "7. 🛡️ Auditoria Geral (Total)"
        ]
    elif perfil_user == "Armazenista":
        opcoes_menu = [
            "F0. 📊 Dashboard (Operacional)",
            "F1. 📋 Painel (Controle Operacional)",
            "F6. 📷 Modo Operador (QR Code / Endereço)",
            "F2. 🔍 Inspeção, Triagem e Movimentação",
            "F3. 👷 Controle de Cautela (Entrega/Devolução)",
            "F4. 🔧 Manutenção e Segregação",
            "F5. ⚖️ Divergência D365 x Saldo Operacional",
            "7. 🛡️ Auditoria (Consulta)"
        ]
    else:  # Operação Procisa
        opcoes_menu = [
            "F0. 📊 Dashboard (Consulta)",
            "F1. 📋 Painel (Consulta Ferramental)",
            "7. 🛡️ Minhas Movimentações"
        ]

if 'modulo_ativo' not in st.session_state or st.session_state.modulo_ativo not in opcoes_menu:
    if opcoes_menu:
        st.session_state.modulo_ativo = opcoes_menu[0]

for opcao in opcoes_menu:
    tipo_botao = "primary" if st.session_state.modulo_ativo == opcao else "secondary"
    if st.sidebar.button(opcao, type=tipo_botao, use_container_width=True):
        st.session_state.modulo_ativo = opcao
        st.rerun()

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
        render_dashboard_executivo_eqp_fallback(df_ativos, df_mov, df_termos, df_diverg)
    elif selecao.startswith("1"):
        gestor.render_modulo_dashboard(df_ativos, df_mov, df_termos, df_diverg, df_empregados)
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
    elif selecao.startswith("9"):
        governanca_eqp.render_modulo_governanca_eqp(df_ativos, df_roubo, df_sem_giro, df_descarte)
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
