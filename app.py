import streamlit as st
import importlib

# Configuração da página (Deve ser sempre o primeiro comando do Streamlit)
st.set_page_config(page_title="Gestão de Ativos e Equipamentos - PROCISA", layout="wide")

import nuvem
import operacao
import gestor

# Força o recarregamento dos módulos no servidor para evitar cache antigo do Python
importlib.reload(nuvem)
importlib.reload(operacao)
importlib.reload(gestor)

from nuvem import (
    supabase, carregar_dados, registrar_log_auditoria, exibir_marca_desenvolvedor
)
from operacao import (
    render_modulo_solicitacao, render_modulo_validacoes, 
    render_modulo_termos_divergencias, render_modulo_laboratorio
)
from gestor import (
    render_modulo_dashboard, render_modulo_usuarios, render_modulo_auditoria
)

if not supabase:
    st.warning("⚠️ Não foi possível estabelecer conexão com o banco de dados na nuvem.")
    st.stop()

# Carrega todas as tabelas higienizadas da nuvem
df_ativos, df_mov, df_termos, df_diverg, df_usuarios, df_logs, df_empregados = carregar_dados()

# ==========================================
# SISTEMA DE AUTENTICAÇÃO E SESSÃO
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.usuario = None
    st.session_state.perfil = None
    st.session_state.nome_real = None
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

# --- TELA DE LOGIN ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>🔐 Acesso Restrito</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Sistema Integrado de Movimentação de Ativos (NUVEM)</p>", unsafe_allow_html=True)
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

# ==========================================
# BARRA LATERAL E NAVEGAÇÃO POR BOTÕES
# ==========================================
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
st.sidebar.header("Módulos Disponíveis")

opcoes_menu = []
if st.session_state.perfil == 'Master':
    opcoes_menu = [
        "1. Dashboard e Conciliação (Gestão)", 
        "2. Solicitação de Movimentação (Campo)", 
        "3. Central de Validações (Almoxarifado)", 
        "4. Gestão de Termos e Divergências (Almoxarifado)",
        "5. Diagnóstico (Laboratório)",
        "6. Gestão de Usuários (Admin)",
        "7. 🛡️ Auditoria Geral (Gestor)"
    ]
elif st.session_state.perfil == 'Operador Campo':
    opcoes_menu = ["2. Solicitação de Movimentação (Campo)"]
elif st.session_state.perfil == 'Almoxarifado':
    opcoes_menu = [
        "2. Solicitação de Movimentação (Campo)", 
        "3. Central de Validações (Almoxarifado)",
        "4. Gestão de Termos e Divergências (Almoxarifado)"
    ]
elif st.session_state.perfil in ['Laboratório', 'Laboratorio']:
    opcoes_menu = ["5. Diagnóstico (Laboratório)"]

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

# ==========================================
# ROTEAMENTO DE MÓDULOS
# ==========================================
selecao = st.session_state.modulo_ativo

if selecao and selecao.startswith("1"):
    render_modulo_dashboard(df_ativos, df_mov, df_termos, df_diverg, df_empregados)
elif selecao and selecao.startswith("2"):
    render_modulo_solicitacao(df_ativos, df_empregados)
elif selecao and selecao.startswith("3"):
    render_modulo_validacoes(df_ativos, df_mov, df_termos, df_empregados)
elif selecao and selecao.startswith("4"):
    render_modulo_termos_divergencias(df_ativos, df_termos, df_diverg, df_empregados)
elif selecao and selecao.startswith("5"):
    render_modulo_laboratorio(df_ativos)
elif selecao and selecao.startswith("6"):
    render_modulo_usuarios(df_usuarios)
elif selecao and selecao.startswith("7"):
    render_modulo_auditoria(df_ativos, df_mov, df_termos, df_diverg, df_logs, df_usuarios, df_empregados)
