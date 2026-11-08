import streamlit as st
import pandas as pd
from datetime import datetime
import os
import tempfile

try:
    from fpdf import FPDF
except ImportError:
    st.error("A biblioteca 'fpdf' não está instalada. Pare o sistema e rode: pip install fpdf")

try:
    from supabase import create_client, Client
except ImportError:
    st.error("A biblioteca 'supabase' não está instalada. Pare o sistema e rode: pip install supabase")

# Configuração da página
st.set_page_config(page_title="Gestão de Ativos e Equipamentos", layout="wide")

# ==========================================
# CONFIGURAÇÃO DO SUPABASE (NUVEM)
# ==========================================
SUPABASE_URL = "https://qptzxnxjhpfqdkmsblct.supabase.co/rest/v1/"
SUPABASE_KEY = "sb_publishable_y0JUFibeIhU-DBDcGFmREA_IlgsfNa0"

@st.cache_resource
def init_connection():
    if SUPABASE_URL == "https://qptzxnxjhpfqdkmsblct.supabase.co":
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

if not supabase:
    st.warning("⚠️ Insira a sua SUPABASE_URL e SUPABASE_KEY no código para conectar à nuvem.")
    st.stop()

# ==========================================
# GESTÃO DE DADOS (SUPABASE)
# ==========================================
@st.cache_data(ttl=5)
def carregar_dados():
    try:
        ativos_res = supabase.table('ativos_master').select("*").execute()
        mov_res = supabase.table('movimentacoes').select("*").execute()
        termos_res = supabase.table('termos').select("*").execute()
        diverg_res = supabase.table('divergencias').select("*").execute()
        usuarios_res = supabase.table('usuarios').select("*").execute()

        df_ativos = pd.DataFrame(ativos_res.data) if ativos_res.data else pd.DataFrame(columns=['codigo_d365', 'patrimonio_placa', 'numero_serie', 'marca', 'modelo', 'categoria', 'status_sistema', 'condicao_fisica', 'localizacao_atual', 'responsavel_atual', 'data_ultima_mov', 'observacoes'])
        df_mov = pd.DataFrame(mov_res.data) if mov_res.data else pd.DataFrame(columns=['id_mov', 'data_hora', 'tipo_mov', 'patrimonio', 'origem', 'destino', 'solicitante', 'autorizador', 'status_mov'])
        df_termos = pd.DataFrame(termos_res.data) if termos_res.data else pd.DataFrame(columns=['id_termo', 'patrimonio', 'responsavel', 'matricula', 'unidade', 'data_emissao', 'data_baixa', 'status_termo'])
        df_diverg = pd.DataFrame(diverg_res.data) if diverg_res.data else pd.DataFrame(columns=['id_divergencia', 'data_registro', 'patrimonio', 'tipo_divergencia', 'status_resolucao', 'analista_responsavel', 'observacoes'])
        df_usuarios = pd.DataFrame(usuarios_res.data) if usuarios_res.data else pd.DataFrame(columns=['usuario', 'senha', 'perfil', 'nome'])
        
        if not df_diverg.empty:
            df_diverg['status_resolucao'] = df_diverg['status_resolucao'].fillna('Pendente')
            
        return df_ativos, df_mov, df_termos, df_diverg, df_usuarios
    except Exception as e:
        st.error(f"Erro ao carregar dados da nuvem: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_ativos, df_mov, df_termos, df_diverg, df_usuarios = carregar_dados()

def salvar_dados(df_a, df_m, df_t, df_d, df_u):
    try:
        if not df_a.empty: supabase.table('ativos_master').upsert(df_a.fillna("").to_dict(orient='records')).execute()
        if not df_m.empty: supabase.table('movimentacoes').upsert(df_m.fillna("").to_dict(orient='records')).execute()
        if not df_t.empty: supabase.table('termos').upsert(df_t.fillna("").to_dict(orient='records')).execute()
        if not df_d.empty: supabase.table('divergencias').upsert(df_d.fillna("").to_dict(orient='records')).execute()
        if not df_u.empty: supabase.table('usuarios').upsert(df_u.fillna("").to_dict(orient='records')).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao guardar na nuvem: {e}")
        return False

# ==========================================
# SISTEMA DE AUTENTICAÇÃO SIMULADO
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.usuario = None
    st.session_state.perfil = None
    st.session_state.nome_real = None

def fazer_login(usuario, senha):
    match = df_usuarios[(df_usuarios['usuario'] == usuario) & (df_usuarios['senha'] == str(senha))]
    if not match.empty:
        st.session_state.logged_in = True
        st.session_state.usuario = match.iloc[0]['usuario']
        st.session_state.nome_real = match.iloc[0]['nome']
        st.session_state.perfil = match.iloc[0]['perfil']
        st.rerun()
    else:
        st.error("Usuário ou senha incorretos!")

def fazer_logout():
    st.session_state.logged_in = False
    st.session_state.usuario = None
    st.session_state.perfil = None
    st.session_state.nome_real = None
    st.session_state.modulo_ativo = None
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
    st.stop()

# ==========================================
# CÓDIGO PRINCIPAL
# ==========================================

def gerar_termo_pdf(patrimonio, responsavel, matricula, unidade, info_ativo):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="TERMO DE RESPONSABILIDADE DE EQUIPAMENTO", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", '', 11)
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    marca = str(info_ativo.iloc[0]['marca'])
    modelo = str(info_ativo.iloc[0]['modelo'])
    serie = str(info_ativo.iloc[0]['numero_serie'])
    
    linhas = [
        f"Pelo presente termo, o colaborador {responsavel}, matricula {matricula},",
        f"lotado na unidade {unidade}, declara ter recebido o equipamento abaixo",
        "descrito em perfeitas condicoes de uso, assumindo o compromisso de zelar",
        "pela sua guarda e conservacao.",
        "",
        "DETALHES DO EQUIPAMENTO:",
        f"- Patrimonio: {patrimonio}",
        f"- Marca / Modelo: {marca} {modelo}",
        f"- Numero de Serie: {serie}",
        f"- Data de Emissao: {data_atual}",
        ""
    ]
    texto = "\n".join(linhas)
    
    pdf.multi_cell(0, 8, txt=texto)
    pdf.ln(20)
    pdf.cell(90, 10, txt="___________________________________", align='C')
    pdf.cell(90, 10, txt="___________________________________", ln=True, align='C')
    pdf.cell(90, 10, txt="Assinatura do Colaborador", align='C')
    pdf.cell(90, 10, txt="Assinatura do Almoxarifado", ln=True, align='C')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        return tmp.name

# --- BARRA LATERAL E CONTROLE DE ACESSOS ---
st.sidebar.title(f"Olá, {st.session_state.nome_real}")
st.sidebar.caption(f"Perfil: {st.session_state.perfil}")
st.sidebar.button("Sair (Logout)", on_click=fazer_logout, use_container_width=True)
st.sidebar.markdown("---")
st.sidebar.header("Módulos Disponíveis")

opcoes_menu = []
if st.session_state.perfil == 'Master':
    opcoes_menu = [
        "1. Dashboard e Auditoria (Gestão)", 
        "2. Solicitação de Movimentação (Campo)", 
        "3. Validação e Movimentação (Almoxarifado)", 
        "4. Diagnóstico (Laboratório)",
        "5. Gestão de Usuários (Admin)"
    ]
elif st.session_state.perfil == 'Operador Campo':
    opcoes_menu = ["2. Solicitação de Movimentação (Campo)"]
elif st.session_state.perfil == 'Almoxarifado':
    opcoes_menu = [
        "2. Solicitação de Movimentação (Campo)", 
        "3. Validação e Movimentação (Almoxarifado)"
    ]
elif st.session_state.perfil in ['Laboratório', 'Laboratorio']:
    opcoes_menu = ["4. Diagnóstico (Laboratório)"]

if 'modulo_ativo' not in st.session_state or st.session_state.modulo_ativo not in opcoes_menu:
    if opcoes_menu:
        st.session_state.modulo_ativo = opcoes_menu[0]

for opcao in opcoes_menu:
    tipo_botao = "primary" if st.session_state.modulo_ativo == opcao else "secondary"
    if st.sidebar.button(opcao, type=tipo_botao, use_container_width=True):
        st.session_state.modulo_ativo = opcao
        st.rer
