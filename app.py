import streamlit as st
import pandas as pd
from datetime import datetime
import os
import tempfile
import io
import unicodedata
import json

try:
    from fpdf import FPDF
except ImportError:
    st.error("A biblioteca 'fpdf' não está instalada. Verifique o arquivo requirements.txt")

try:
    from supabase import create_client, Client
except ImportError:
    st.error("A biblioteca 'supabase' não está instalada. Verifique o arquivo requirements.txt")

# Configuração da página
st.set_page_config(page_title="Gestão de Ativos e Equipamentos", layout="wide")

# ==========================================
# CONFIGURAÇÃO DO SUPABASE (NUVEM)
# ==========================================
SUPABASE_URL = "https://qptzxnxjhpfqdkmsblct.supabase.co"
SUPABASE_KEY = "sb_publishable_y0JUFibeIhU-DBDcGFmREA_IlgsfNa0"

@st.cache_resource
def init_connection():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Erro ao inicializar conexão com Supabase: {e}")
        return None

supabase = init_connection()

if not supabase:
    st.warning("⚠️ Não foi possível estabelecer conexão com o banco de dados na nuvem.")
    st.stop()

# ==========================================
# FUNÇÕES UTILITÁRIAS E DE HIGIENIZAÇÃO
# ==========================================
COLUNAS_ATIVOS = [
    'item', 'valor', 'equipamento', 'marca', 'modelo', 'numero_serie', 
    'patrimonio', 'cautela', 'projeto', 'coordenacao', 'nf_procisa', 
    'atualizado_em', 'condicoes_para_uso', 'acessorios', 'status_sistema'
]
COLUNAS_MOV = [
    'id_mov', 'data_hora', 'tipo_mov', 'patrimonio', 'origem', 'destino', 
    'solicitante', 'autorizador', 'status_mov', 'nf_procisa', 'projeto', 
    'coordenacao', 'data_efetiva', 'matricula_solicitante'
]
COLUNAS_TERMOS = ['id_termo', 'patrimonio', 'responsavel', 'matricula', 'unidade', 'data_emissao', 'data_baixa', 'status_termo']
COLUNAS_DIVERG = ['id_divergencia', 'data_registro', 'patrimonio', 'tipo_divergencia', 'status_resolucao', 'analista_responsavel', 'observacoes']
COLUNAS_USUARIOS = ['usuario', 'senha', 'perfil', 'nome']
COLUNAS_EMPREGADOS = ['matricula', 'nome', 'cpf', 'rg', 'projeto', 'unidade']

ASSINATURA_DEV_HTML = """
<div style='text-align: center; margin-top: 20px; padding: 6px; color: #888888; font-size: 0.75rem;'>
    Desenvolvido por <strong>Marcos Paulo Da Veiga Carvalho</strong>
</div>
"""

def exibir_marca_desenvolvedor():
    st.markdown(ASSINATURA_DEV_HTML, unsafe_allow_html=True)

def normalizar_nome_coluna(col):
    texto = str(col).strip().lower()
    texto = texto.replace('nº', 'numero').replace('º', '').replace('ª', '')
    texto_sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    return texto_sem_acento.replace(' ', '_').replace('-', '_')

def preparar_para_supabase(df, colunas_validas):
    if df.empty:
        return []
    cols_presentes = [c for c in df.columns if c in colunas_validas]
    df_limpo = df[cols_presentes].copy()
    df_limpo = df_limpo.fillna("")
    
    for col in df_limpo.columns:
        df_limpo[col] = df_limpo[col].apply(
            lambda x: x.strftime('%Y-%m-%d') if isinstance(x, (pd.Timestamp, datetime)) else str(x).strip()
        )
        df_limpo[col] = df_limpo[col].replace({"None": "", "nan": "", "NaT": ""})
    return df_limpo.to_dict(orient='records')

def registrar_log_auditoria(acao, alvo, detalhes):
    try:
        usuario_acao = f"{st.session_state.get('nome_real', 'Sistema')} ({st.session_state.get('usuario', 'auto')})"
        id_log = f"AUD-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:19]}"
        registro = {
            'id_divergencia': id_log,
            'data_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'patrimonio': str(alvo)[:50],
            'tipo_divergencia': f"[LOG-SISTEMA] {acao}",
            'status_resolucao': 'Auditado',
            'analista_responsavel': usuario_acao,
            'observacoes': str(detalhes)
        }
        supabase.table('divergencias').insert(registro).execute()
    except Exception:
        pass

def calcular_uso_supabase(dfs_lista, limite_mb=500.0):
    total_bytes = 0
    total_linhas = 0
    for df in dfs_lista:
        if not df.empty:
            total_linhas += len(df)
            dados_json = json.dumps(df.fillna("").astype(str).to_dict(orient='records'), ensure_ascii=False)
            total_bytes += int(len(dados_json.encode('utf-8')) * 2.2)
            
    bytes_base_sistema = int(8.5 * 1024 * 1024)
    total_bytes_real = total_bytes + bytes_base_sistema
    
    usado_mb = total_bytes_real / (1024 * 1024)
    dados_puros_kb = total_bytes / 1024
    livre_mb = max(0.0, limite_mb - usado_mb)
    pct_usado = min(100.0, (usado_mb / limite_mb) * 100)
    pct_livre = max(0.0, 100.0 - pct_usado)
    
    return {
        'usado_mb': usado_mb,
        'dados_puros_kb': dados_puros_kb,
        'livre_mb': livre_mb,
        'limite_mb': limite_mb,
        'pct_usado': pct_usado,
        'pct_livre': pct_livre,
        'total_linhas': total_linhas
    }

def buscar_ativo(termo_busca, df):
    if df.empty or not termo_busca:
        return pd.DataFrame()
    termo = str(termo_busca).strip().upper()
    patrimonios = df['patrimonio'].fillna("").astype(str).str.strip().str.upper()
    series = df['numero_serie'].fillna("").astype(str).str.strip().str.upper()
    return df[(patrimonios == termo) | (series == termo)]

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
        
        try:
            empregados_res = supabase.table('empregados').select("*").execute()
            df_empregados = pd.DataFrame(empregados_res.data) if empregados_res.data else pd.DataFrame(columns=COLUNAS_EMPREGADOS)
        except Exception:
            df_empregados = pd.DataFrame(columns=COLUNAS_EMPREGADOS)

        df_ativos = pd.DataFrame(ativos_res.data) if ativos_res.data else pd.DataFrame(columns=COLUNAS_ATIVOS)
        df_mov = pd.DataFrame(mov_res.data) if mov_res.data else pd.DataFrame(columns=COLUNAS_MOV)
        df_termos = pd.DataFrame(termos_res.data) if termos_res.data else pd.DataFrame(columns=COLUNAS_TERMOS)
        df_diverg_bruto = pd.DataFrame(diverg_res.data) if diverg_res.data else pd.DataFrame(columns=COLUNAS_DIVERG)
        df_usuarios = pd.DataFrame(usuarios_res.data) if usuarios_res.data else pd.DataFrame(columns=COLUNAS_USUARIOS)
        
        for col in COLUNAS_ATIVOS:
            if col not in df_ativos.columns:
                df_ativos[col] = "Disponível" if col == 'status_sistema' else ""
                
        if not df_ativos.empty:
            df_ativos['patrimonio'] = df_ativos['patrimonio'].astype(str).str.strip()

        if not df_diverg_bruto.empty and 'tipo_divergencia' in df_diverg_bruto.columns:
            df_diverg_bruto['status_resolucao'] = df_diverg_bruto['status_resolucao'].fillna('Pendente').replace("", "Pendente")
            mask_log = df_diverg_bruto['tipo_divergencia'].astype(str).str.startswith('[LOG-SISTEMA]')
            df_logs = df_diverg_bruto[mask_log].copy()
            df_diverg = df_diverg_bruto[~mask_log].copy()
        else:
            df_logs = pd.DataFrame(columns=COLUNAS_DIVERG)
            df_diverg = df_diverg_bruto
            
        if not df_usuarios.empty and 'senha' in df_usuarios.columns:
            df_usuarios['usuario'] = df_usuarios['usuario'].astype(str).str.strip()
            df_usuarios['senha'] = df_usuarios['senha'].astype(str).str.strip()
            
        return df_ativos, df_mov, df_termos, df_diverg, df_usuarios, df_logs, df_empregados
    except Exception as e:
        st.error(f"Erro ao carregar dados da nuvem: {e}")
        return (
            pd.DataFrame(columns=COLUNAS_ATIVOS), pd.DataFrame(columns=COLUNAS_MOV),
            pd.DataFrame(columns=COLUNAS_TERMOS), pd.DataFrame(columns=COLUNAS_DIVERG),
            pd.DataFrame(columns=COLUNAS_USUARIOS), pd.DataFrame(columns=COLUNAS_DIVERG),
            pd.DataFrame(columns=COLUNAS_EMPREGADOS)
        )

df_ativos, df_mov, df_termos, df_diverg, df_usuarios, df_logs, df_empregados = carregar_dados()

def salvar_dados_massa(tabela, df_massa, colunas):
    try:
        dados = preparar_para_supabase(df_massa, colunas)
        if dados:
            supabase.table(tabela).upsert(dados).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao guardar carga em massa: {e}")
        return False

# ==========================================
# SISTEMA DE AUTENTICAÇÃO E VARIÁVEIS GLOBAIS
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
# FUNÇÃO GERADORA DE PDF (MODELO PROCISA FR-RH-P-026)
# ==========================================
def limpar_texto_pdf(texto):
    return str(texto).encode('latin-1', 'replace').decode('latin-1')

def gerar_termo_pdf(patrimonio, responsavel, matricula, cpf, rg, projeto, unidade, info_ativo):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 5, txt=limpar_texto_pdf("PROCISA"), border='LTR', align='C')
    pdf.cell(100, 5, txt=limpar_texto_pdf("TERMO DE RESPONSABILIDADE DE EQUIPAMENTOS"), border='LTR', align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf("DATA"), border=1, align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf("PÁG."), border=1, ln=True, align='C')
    
    pdf.cell(40, 5, txt=limpar_texto_pdf("FR-RH-P-026 Rev 07 / Jul 13"), border='LBR', align='C')
    pdf.cell(100, 5, txt=limpar_texto_pdf("REF."), border='LBR', align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf(data_atual), border=1, align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf("- 1 -"), border=1, ln=True, align='C')
    
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, txt=limpar_texto_pdf("TERMO DE RESPONSABILIDADE DE EQUIPAMENTOS"), ln=True, align='C')
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"Usuário: {responsavel}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"RG: {rg}      CPF/MF: {cpf}      Matrícula: {matricula}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"Área: {unidade}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"Projeto: {projeto}"), ln=True)
    
    pdf.ln(5)
    
    pdf.set_font("Arial", '', 9)
    clausulas = [
        "1. O usuário infra-assinado recebe da PROCISA, nesta data, a expressa concessão do uso do(s) equipamento(s), conforme o estado descrito abaixo, com o objetivo de complementar suas ferramentas profissionais, no estrito exercício de sua função na PROCISA, desde que devidamente aprovado pelo seu Superior ou Responsável, que passa a ter a responsabilidade solidária por todos os atos decorrentes dessa concessão do uso do(s) equipamento(s).",
        "2. Neste ato, compromete-se que, enquanto estiver em sua guarda, fará bom uso do(s) equipamento(s) e mantê-lo(s)-á sempre em bom estado de conservação, tratando-o com o mesmo cuidado e diligência que costuma tratar com aquilo que lhe pertence, observando-se as recomendações da Área de Logística/Patrimonial e do Manual de Instruções do(s) Equipamento(s), disponibilizando-os para manutenções corretivas ou preventivas quando assim solicitado.",
        "3. Ademais, compromete-se a não emprestar, vender, onerar o(s) equipamento(s) ou de qualquer outra forma ceder o uso do(s) equipamento(s) a terceiros, sem a expressa concordância por escrito da PROCISA, devendo devolvê-lo(s) na sua integralidade, com todos os eventuais acessórios que lhe(s) compõem, quando assim for solicitado, pelo Almoxarifado ou pelo seu superior imediato, ou no momento de seu desligamento, de suas férias ou em licenças médicas, sob pena de lhe incorrer as penalidades legalmente previstas. Todos os atos ocorridos no período de uso do usuário serão de sua exclusiva responsabilidade, mesmo que verificados após a sua devolução.",
        "4. Havendo a expressa autorização, por escrito, do superior imediato do usuário, o(s) equipamento(s) poderá(ão) ser cedido(s) a terceiro, desde que o terceiro seja funcionário da PROCISA, que só poderá ocorrer mediante comunicação expressa à Área de Logística/Patrimonial e se assim forem seguidos os devidos procedimentos formais. A transferência só será efetivada com assinatura de novo Termo de Responsabilidade de Equipamentos pelo terceiro.",
        "5. Em casos de furto, roubo, perda ou extravio, parcial ou total, o usuário deverá apresentar de imediato à Área de Logística/Patrimonial o respectivo Boletim de Ocorrência. No entanto, o usuário está ciente de que é sua inteira responsabilidade a falsa notícia de perda, de furto ou de roubo, assim como a má utilização do(s) equipamento(s), e que arcará com seus respectivos custos, concordando ainda, neste ato, com o desconto em folha de pagamento, nos limites estabelecidos em lei, ou a realizar outra forma de acordo, sem prejuízo da apuração das perdas e dos danos incorridos à PROCISA que, desde já, se compromete a ressarci-la, bem como está ciente de que poderá responder pessoalmente pelas eventuais consequências administrativas e/ou judiciais, inclusive de natureza penal.",
        "6. Por fim, está ciente de que o descumprimento de quaisquer das disposições aqui estabelecidas acarretará nas sanções legalmente previstas."
    ]
    
    for clausula in clausulas:
        pdf.multi_cell(0, 5, txt=limpar_texto_pdf(clausula))
        pdf.ln(3)
        
    pdf.ln(10)
    pdf.cell(90, 10, txt="___________________________________", align='C')
    pdf.cell(90, 10, txt="___________________________________", ln=True, align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("USUÁRIO"), align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("COORDENADOR/RESPONSÁVEL"), ln=True, align='C')
    
    # --- PÁGINA 2 ---
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 5, txt=limpar_texto_pdf("PROCISA"), border='LTR', align='C')
    pdf.cell(100, 5, txt=limpar_texto_pdf("TERMO DE RESPONSABILIDADE DE EQUIPAMENTOS"), border='LTR', align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf("DATA"), border=1, align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf("PÁG."), border=1, ln=True, align='C')
    
    pdf.cell(40, 5, txt=limpar_texto_pdf("FR-RH-P-026 Rev 07 / Jul 13"), border='LBR', align='C')
    pdf.cell(100, 5, txt=limpar_texto_pdf("REF."), border='LBR', align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf(data_atual), border=1, align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf("- 2 -"), border=1, ln=True, align='C')
    
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(95, 8, txt=limpar_texto_pdf(f"ENTREGA: {data_atual}"), border=1)
    pdf.cell(95, 8, txt=limpar_texto_pdf("DEVOLUÇÃO: ___/___/___"), border=1, ln=True)
    
    marca = str(info_ativo.iloc[0].get('marca', ''))
    modelo = str(info_ativo.iloc[0].get('modelo', ''))
    serie = str(info_ativo.iloc[0].get('numero_serie', ''))
    condicao = str(info_ativo.iloc[0].get('condicoes_para_uso', ''))
    
    pdf.ln(5)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"1. MARCA/MODELO: {marca} {modelo}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"   NÚMERO DE SÉRIE: {serie}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"   NÚMERO DE ATIVO: {patrimonio}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"   SITUAÇÃO: {condicao}"), ln=True)
    pdf.ln(5)
    
    for i in range(2, 6):
        pdf.cell(0, 6, txt=limpar_texto_pdf(f"{i}. MARCA/MODELO: _________________________________________"), ln=True)
        pdf.cell(0, 6, txt=limpar_texto_pdf("   NÚMERO DE SÉRIE: _______________________________________"), ln=True)
        pdf.cell(0, 6, txt=limpar_texto_pdf("   NÚMERO DE ATIVO: _______________________________________"), ln=True)
        pdf.cell(0, 6, txt=limpar_texto_pdf("   SITUAÇÃO: ______________________________________________"), ln=True)
        pdf.ln(3)
        
    pdf.ln(5)
    pdf.cell(0, 6, txt=limpar_texto_pdf("MOTIVO DA DEVOLUÇÃO:"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf("[  ] MANUTENÇÃO   [  ] DESLIGAMENTO   [  ] CALIBRAÇÃO"), ln=True)
    
    pdf.ln(5)
    pdf.cell(0, 6, txt=limpar_texto_pdf("OBSERVAÇÕES: __________________________________________________________________________"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf("COORD. RESPONSÁVEL: ______________________  NÚMERO DA NF: ______________________"), ln=True)
    
    pdf.ln(15)
    pdf.cell(90, 10, txt="___________________________________", align='C')
    pdf.cell(90, 10, txt="___________________________________", ln=True, align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("USUÁRIO"), align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("ALMOXARIFADO"), ln=True, align='C')

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        return tmp.name

# ==========================================
# BARRA LATERAL E NAVEGAÇÃO POR BOTÕES
# ==========================================
st.sidebar.title(f"Olá, {st.session_state.nome_real}")
st.sidebar.caption(f"Perfil: {st.session_state.perfil}")
st.sidebar.button("Sair (Logout)", on_click=fazer_logout, use_container_width=True)
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

selecao_perfil = st.session_state.modulo_ativo

# ==========================================
# MÓDULO 1: DASHBOARD E CONCILIAÇÃO
# ==========================================
if selecao_perfil and selecao_perfil.startswith("1"):
    st.header("📊 Painel Gerencial e Conciliação")
    
    if st.session_state.get('resumo_ultima_operacao'):
        info_op = st.session_state.resumo_ultima_operacao
        st.success(f"✅ **{info_op['titulo']}** | Sistema atualizado às {info_op['hora']}")
        c_op1, c_op2, c_op3, c_op4 = st.columns(4)
        c_op1.metric("Quantidade Anterior", info_op['qtd_antes'])
        c_op2.metric("Novos Inseridos", f"+{info_op['novos']}")
        c_op3.metric("Existentes Atualizados", info_op['atualizados'])
        c_op4.metric("Total Atual na Base", info_op['qtd_depois'], delta=f"{info_op['qtd_depois'] - info_op['qtd_antes']} ativos")
        if st.button("✖️ Fechar Resumo de Envio"):
            st.session_state.resumo_ultima_operacao = None
            st.rerun()
        st.divider()

    total_ativos = len(df_ativos)
    if not df_ativos.empty:
        cautela_upper = df_ativos['cautela'].fillna("").astype(str).str.upper()
        status_upper = df_ativos['status_sistema'].fillna("").astype(str).str.upper()
        
        mask_almox = cautela_upper.str.contains('ALMOX')
        mask_disp = status_upper == 'DISPONÍVEL'
        mask_uso = status_upper == 'EM USO'
        
        disp_estoque = len(df_ativos[mask_disp & mask_almox])
        em_uso = len(df_ativos[mask_uso])
    else:
        disp_estoque = 0
        em_uso = 0
        
    diverg_pend = len(df_diverg[df_diverg['status_resolucao'] != 'Resolvido']) if not df_diverg.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de Ativos Cadastrados", total_ativos)
    col2.metric("Disponíveis em Estoque (Almox)", disp_estoque, help="Requer status 'Disponível' e Cautela contendo 'Almoxarifado'")
    col3.metric("Em Uso (Campo/Responsáveis)", em_uso)
    col4.metric("Divergências Pendentes", diverg_pend, delta_color="inverse")

    abas_dashboard = ["Inventário Geral", "Histórico de Movimentações", "Termos Emitidos", "➕ Novo Cadastro Manual", "🔄 Importar / Exportar"]
    if st.session_state.perfil == 'Master':
        abas_dashboard.append("❌ Excluir Ativo (Master)")
        
    abas = st.tabs(abas_dashboard)
    
    with abas[0]:
        st.dataframe(df_ativos[COLUNAS_ATIVOS] if not df_ativos.empty else df_ativos, use_container_width=True)
    with abas[1]:
        st.dataframe(df_mov, use_container_width=True)
    with abas[2]:
        st.dataframe(df_termos, use_container_width=True)
        
    with abas[3]:
        st.subheader("Cadastrar ou Atualizar Ativo Individual")
        with st.form("form_novo_ativo"):
            colA, colB, colC = st.columns(3)
            with colA:
                cad_patrimonio = st.text_input("Patrimônio / Placa *")
                cad_equipamento = st.text_input("Equipamento")
                cad_marca = st.text_input("Marca")
                cad_modelo = st.text_input("Modelo")
                cad_serie = st.text_input("Número de Série")
            with colB:
                cad_item = st.text_input("Item")
                cad_valor = st.text_input("Valor")
                cad_cautela = st.text_input("Cautela (Local/Responsável)")
                cad_projeto = st.text_input("Projeto")
                cad_coord = st.text_input("Coordenação")
            with colC:
                cad_nf = st.text_input("NF Procisa")
                cad_condicao = st.text_input("Condições para Uso")
                cad_acessorios = st.text_input("Acessórios")
                cad_status = st.selectbox("Status no Sistema", ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"])
            
            submit_cadastro = st.form_submit_button("💾 Salvar Ativo na Nuvem", type="primary")
            
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
                        'projeto': cad_projeto.strip(),
                        'coordenacao': cad_coord.strip(),
                        'nf_procisa': cad_nf.strip(),
                        'atualizado_em': datetime.now().strftime('%Y-%m-%d'),
                        'condicoes_para_uso': cad_condicao.strip(),
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
                        
                        detalhe_log = f"Ativo {pat_limpo} ({cad_marca} {cad_modelo}) salvo via formulário."
                        registrar_log_auditoria(tipo_op, pat_limpo, detalhe_log)
                        
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

    with abas[4]:
        st.subheader("Exportar Relatórios (Download)")
        st.write("Baixe a base de ativos atualizada diretamente da nuvem para o seu computador.")
        
        def converter_df_excel(df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_export = df[COLUNAS_ATIVOS] if not df.empty else pd.DataFrame(columns=COLUNAS_ATIVOS)
                df_export.to_excel(writer, index=False, sheet_name='Base_Ativos')
            return output.getvalue()

        excel_data = converter_df_excel(df_ativos)
        if st.download_button(
            label="📥 Baixar Base / Modelo de Ativos (.xlsx)", 
            data=excel_data, 
            file_name=f"Base_Ativos_Procisa_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ):
            registrar_log_auditoria("EXPORTAÇÃO EXCEL", "Base Geral", f"Download da planilha de ativos ({len(df_ativos)} registros).")

        st.divider()

        st.subheader("Carga Inicial / Atualização em Massa (Upload)")
        st.info("💡 Os cabeçalhos da planilha são limpos e traduzidos automaticamente (sem acentos e em minúsculas).")
        
        arquivo_up = st.file_uploader("Arraste o arquivo Excel de EQUIPAMENTOS (.xlsx)", type=["xlsx"])
        if arquivo_up:
            try:
                df_up = pd.read_excel(arquivo_up)
                df_up.columns = [normalizar_nome_coluna(c) for c in df_up.columns]
                
                if 'status_sistema' not in df_up.columns:
                    df_up['status_sistema'] = 'Disponível'
                
                if 'patrimonio' not in df_up.columns:
                    st.error(f"A coluna obrigatória 'patrimonio' não foi encontrada na planilha. Colunas lidas: {list(df_up.columns)}")
                else:
                    df_up = df_up.dropna(subset=['patrimonio'])
                    df_up['patrimonio'] = df_up['patrimonio'].astype(str).str.strip()
                    df_up = df_up[df_up['patrimonio'] != '']
                    df_up = df_up.drop_duplicates(subset=['patrimonio'], keep='last')
                    
                    atuais_set = set(df_ativos['patrimonio'].astype(str).str.strip()) if not df_ativos.empty else set()
                    novos_set = set(df_up['patrimonio'])
                    
                    qtd_antes = len(atuais_set)
                    qtd_novos = len(novos_set - atuais_set)
                    qtd_atualizados = len(novos_set.intersection(atuais_set))
                    qtd_depois = len(atuais_set.union(novos_set))
                    
                    st.markdown("##### 📋 Resumo Pré-Envio da Planilha:")
                    c_p1, c_p2, c_p3, c_p4 = st.columns(4)
                    c_p1.metric("Base Atual (Antes)", qtd_antes)
                    c_p2.metric("Novos Cadastros", f"+{qtd_novos}")
                    c_p3.metric("Serão Atualizados", qtd_atualizados)
                    c_p4.metric("Projeção (Depois)", qtd_depois)
                    
                    st.write(f"**Pré-visualização ({len(df_up)} linhas válidas na planilha):**")
                    st.dataframe(df_up.head(5), use_container_width=True)
                    
                    if st.button("🚀 Confirmar e Subir para a Nuvem", type="primary"):
                        with st.spinner("A enviar dados para o Supabase e a atualizar o sistema..."):
                            if salvar_dados_massa('ativos_master', df_up, COLUNAS_ATIVOS):
                                detalhe_log = f"Arquivo '{arquivo_up.name}' enviado. Novos: +{qtd_novos} | Atualizados: {qtd_atualizados}."
                                registrar_log_auditoria("UPLOAD PLANILHA", arquivo_up.name, detalhe_log)
                                
                                st.session_state.resumo_ultima_operacao = {
                                    'titulo': f"Envio da planilha '{arquivo_up.name}' concluído com sucesso!",
                                    'hora': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                                    'qtd_antes': qtd_antes,
                                    'novos': qtd_novos,
                                    'atualizados': qtd_atualizados,
                                    'qtd_depois': qtd_depois
                                }
                                st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler o arquivo Excel: {e}")
                
        st.divider()
        st.subheader("👥 Carga de Base de Colaboradores (Para Movimentação e Termos)")
        arquivo_emp = st.file_uploader("Arraste a planilha de COLABORADORES (.xlsx)", type=["xlsx"], key="up_emp")
        if arquivo_emp:
            try:
                df_emp_up = pd.read_excel(arquivo_emp)
                df_emp_up.columns = [normalizar_nome_coluna(c) for c in df_emp_up.columns]
                
                if 'matricula' not in df_emp_up.columns:
                    st.error("A coluna obrigatória 'matricula' não foi encontrada.")
                else:
                    df_emp_up = df_emp_up.dropna(subset=['matricula'])
                    df_emp_up['matricula'] = df_emp_up['matricula'].astype(str).str.strip()
                    df_emp_up = df_emp_up.drop_duplicates(subset=['matricula'], keep='last')
                    
                    if st.button("🚀 Subir Base de Colaboradores", type="primary"):
                        with st.spinner("Atualizando colaboradores no Supabase..."):
                            if salvar_dados_massa('empregados', df_emp_up, COLUNAS_EMPREGADOS):
                                registrar_log_auditoria("UPLOAD COLABORADORES", arquivo_emp.name, f"Base de {len(df_emp_up)} colaboradores atualizada.")
                                st.success("✅ Base de colaboradores salva com sucesso na nuvem!")
                                st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")
                
    if st.session_state.perfil == 'Master':
        with abas[5]:
            st.subheader("❌ Exclusão Permanente de Ativo")
            st.warning("Atenção: Esta ação removerá o ativo do banco de dados definitivamente. Apenas o Gestor (Master) tem acesso a esta aba.")
            pat_del = st.text_input("Digite o Patrimônio ou Nº de Série exato para exclusão:")
            if st.button("🗑️ Confirmar Exclusão", type="primary"):
                if pat_del.strip():
                    ativo_del = buscar_ativo(pat_del, df_ativos)
                    if not ativo_del.empty:
                        pat_real = ativo_del.iloc[0]['patrimonio']
                        try:
                            supabase.table('ativos_master').delete().eq('patrimonio', pat_real).execute()
                            registrar_log_auditoria("EXCLUSÃO ATIVO", pat_real, "Ativo removido permanentemente pelo Master.")
                            st.cache_data.clear()
                            st.success(f"✅ Ativo {pat_real} excluído permanentemente da nuvem!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao excluir: {e}")
                    else:
                        st.error("Patrimônio ou Série não encontrado na base mestra.")
                else:
                    st.error("Preencha o campo para exclusão.")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 2: SOLICITAÇÃO DE MOVIMENTAÇÃO
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("2"):
    st.header("📝 Solicitação de Movimentação")
    st.write("Identifique o ativo e o colaborador para integrar a solicitação à base de dados.")
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        patrimonio_busca = st.text_input("🔍 Digite o Patrimônio ou Nº de Série (Ativo):")
    with col_b2:
        matricula_busca = st.text_input("🔍 Digite a Matrícula (Colaborador / Solicitante):")
    
    ativo_info = pd.DataFrame()
    emp_dict = {}
    
    if patrimonio_busca:
        ativo_info = buscar_ativo(patrimonio_busca, df_ativos)
        if not ativo_info.empty:
            registro_atual = ativo_info.iloc[0].to_dict()
            pat_real = registro_atual.get('patrimonio', '')
            eqp = registro_atual.get('equipamento', '')
            marca = registro_atual.get('marca', '')
            modelo = registro_atual.get('modelo', '')
            serie = registro_atual.get('numero_serie', '')
            status_atual = registro_atual.get('status_sistema', 'Disponível')
            cautela_atual = registro_atual.get('cautela', '')
            nf_atual = registro_atual.get('nf_procisa', '')
            
            st.success(f"✅ **Ativo Localizado:** {eqp} - {marca} {modelo} (Série: {serie})")
            st.info(f"📍 **Status:** {status_atual} | **Cautela/Local Atual:** {cautela_atual}")
        else:
            st.warning("⚠️ Ativo não localizado.")
            
    if matricula_busca:
        if not df_empregados.empty:
            match_emp = df_empregados[df_empregados['matricula'].astype(str) == matricula_busca.strip()]
            if not match_emp.empty:
                emp_dict = match_emp.iloc[0].fillna("").to_dict()
                st.success(f"👤 **Colaborador Localizado:** {emp_dict.get('nome', '')} | Projeto: {emp_dict.get('projeto', '')} | Coordenação: {emp_dict.get('unidade', '')}")
            else:
                st.warning("⚠️ Colaborador não encontrado na base. Você pode preencher manualmente abaixo.")
    
    if not ativo_info.empty:
        with st.form("form_solicitacao"):
            st.markdown("###### Preencha os detalhes da nova destinação (Cruzamento Colaborador x Ativo):")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                opcoes_mov = [
                    "MOV-01 | Almoxarifado -> Colaborador", 
                    "MOV-02 | Colaborador -> Almoxarifado", 
                    "MOV-03 | Unidade -> Unidade", 
                    "MOV-04 | Almoxarifado -> Laboratório",
                    "MOV-05 | Laboratório -> Almoxarifado"
                ]
                tipo_mov = st.selectbox("Tipo de Movimentação", opcoes_mov)
                origem = st.text_input("Origem (Local Atual)", value=str(cautela_atual))
            with c2:
                destino = st.text_input("Destino / Novo Responsável", value=emp_dict.get('nome', ''))
                projeto = st.text_input("Projeto (Destino)", value=emp_dict.get('projeto', ''))
            with c3:
                coordenacao = st.text_input("Coordenação (Destino)", value=emp_dict.get('unidade', ''))
                matricula_col = st.text_input("Matrícula Solicitante", value=matricula_busca.strip())
                
            c4, c5 = st.columns(2)
            with c4:
                nf_edit = st.text_input("Nota Fiscal / NF Procisa", value=nf_atual)
            with c5:
                data_mov = st.date_input("Data da Movimentação (Efetiva)", datetime.today())
            
            if st.form_submit_button("🚀 Registrar Solicitação", type="primary"):
                if destino.strip():
                    id_mov = f"MOV-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                    nova_mov = {
                        'id_mov': id_mov, 
                        'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                        'tipo_mov': tipo_mov[:6], 
                        'patrimonio': pat_real, 
                        'origem': origem.strip(), 
                        'destino': destino.strip(), 
                        'solicitante': destino.strip(),
                        'matricula_solicitante': matricula_col.strip(),
                        'autorizador': 'Pendente', 
                        'status_mov': 'Aguardando Conferência',
                        'nf_procisa': nf_edit.strip(),
                        'projeto': projeto.strip(),
                        'coordenacao': coordenacao.strip(),
                        'data_efetiva': data_mov.strftime('%Y-%m-%d')
                    }
                    
                    try:
                        supabase.table('movimentacoes').insert(nova_mov).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria(
                            "SOLICITAÇÃO MOV.", 
                            pat_real, 
                            f"ID {id_mov} registrada. Origem: {origem} -> Destino: {destino}."
                        )
                        st.success("✅ Solicitação integrada à base e aguardando validação no Almoxarifado.")
                    except Exception as e:
                        st.error(f"Erro ao salvar solicitação: {e}")
                else:
                    st.error("O campo de Destino / Novo Responsável deve estar preenchido.")

# ==========================================
# MÓDULO 3: CENTRAL DE VALIDAÇÕES (ALMOXARIFADO)
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("3"):
    st.header("✅ Central de Validações (Almoxarifado)")
    
    if st.session_state.get('msg_sucesso'):
        st.success(st.session_state.msg_sucesso)
        if st.button("✖️ Fechar Aviso"):
            st.session_state.msg_sucesso = None
            st.rerun()
        st.divider()
    
    st.markdown("###### 📋 Fila Automática de Movimentações (Aguardando Conferência)")
    movs_pendentes = df_mov[df_mov['status_mov'] == 'Aguardando Conferência'] if not df_mov.empty else pd.DataFrame()
    
    if movs_pendentes.empty:
        st.success("🎉 Excelente! Nenhuma solicitação pendente no momento.")
    else:
        st.dataframe(movs_pendentes[['id_mov', 'data_hora', 'tipo_mov', 'patrimonio', 'origem', 'destino', 'solicitante', 'matricula_solicitante', 'projeto', 'data_efetiva']], use_container_width=True)
        
        id_selecionado = st.selectbox("Selecione o ID da Movimentação para Validar:", movs_pendentes['id_mov'].tolist())
        
        if id_selecionado:
            mov_atual = movs_pendentes[movs_pendentes['id_mov'] == id_selecionado].iloc[0].to_dict()
            pat_real = mov_atual.get('patrimonio', '')
            ativo_info = buscar_ativo(pat_real, df_ativos)
            
            if not ativo_info.empty:
                registro_atual = ativo_info.iloc[0].to_dict()
                status_antigo = registro_atual.get('status_sistema', 'Disponível')
                cautela_antiga = registro_atual.get('cautela', '')
                
                st.info(f"**Ativo Vinculado:** {registro_atual.get('marca', '')} {registro_atual.get('modelo', '')} (Série: {registro_atual.get('numero_serie', '')}) | **Status Atual:** {status_antigo}")
                
                with st.form("form_validacao_pendente"):
                    colA, colB = st.columns(2)
                    with colA: 
                        novo_status = st.selectbox("Novo Status no Sistema:", ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"], index=0 if 'Almoxarifado' in mov_atual.get('destino', '') else 1)
                    with colB: 
                        nova_cautela = st.text_input("Atualizar Cautela (Destino Real)", value=str(mov_atual.get('destino', '')))
                    
                    st.write("Verificações de Segurança:")
                    d365_ok = st.checkbox("Status e Localização conferem no sistema central?")
                    eponto_ok = st.checkbox("Movimentação validada no e-Ponto?")
                    fisico_ok = st.checkbox("Estado físico, Série e Acessórios conferem?")
                    
                    btn_validar = st.form_submit_button("✅ Validar e Concluir Transferência", type="primary")
                    
                    if btn_validar:
                        if d365_ok and eponto_ok and fisico_ok:
                            try:
                                dados_update_ativo = {
                                    'status_sistema': novo_status,
                                    'cautela': nova_cautela.strip(),
                                    'projeto': str(mov_atual.get('projeto', '')).strip(),
                                    'coordenacao': str(mov_atual.get('coordenacao', '')).strip(),
                                    'nf_procisa': str(mov_atual.get('nf_procisa', '')).strip(),
                                    'atualizado_em': str(mov_atual.get('data_efetiva', datetime.now().strftime('%Y-%m-%d'))).strip()
                                }
                                supabase.table('ativos_master').update(dados_update_ativo).eq('patrimonio', pat_real).execute()
                                
                                dados_update_mov = {'status_mov': 'Concluído', 'autorizador': st.session_state.nome_real}
                                supabase.table('movimentacoes').update(dados_update_mov).eq('id_mov', id_selecionado).execute()
                                
                                if str(mov_atual.get('tipo_mov', '')).startswith("MOV-01"):
                                    mat_solic = str(mov_atual.get('matricula_solicitante', '')).strip()
                                    match_emp = df_empregados[df_empregados['matricula'].astype(str) == mat_solic] if not df_empregados.empty else pd.DataFrame()
                                    emp = match_emp.iloc[0].fillna("").to_dict() if not match_emp.empty else {}
                                    
                                    resp_nome = emp.get('nome', mov_atual.get('destino', ''))
                                    resp_unid = emp.get('unidade', mov_atual.get('coordenacao', ''))
                                    
                                    id_termo = f"TRM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                                    novo_termo = {
                                        'id_termo': id_termo, 
                                        'patrimonio': pat_real, 
                                        'responsavel': resp_nome, 
                                        'matricula': mat_solic, 
                                        'unidade': resp_unid, 
                                        'data_emissao': datetime.now().strftime('%Y-%m-%d'), 
                                        'data_baixa': '', 
                                        'status_termo': 'Pendente Impressão'
                                    }
                                    supabase.table('termos').insert(novo_termo).execute()
                                    registrar_log_auditoria("TERMO NA FILA", pat_real, f"Termo {id_termo} gerado e enviado para Fila de Impressão.")
                                    
                                    st.session_state.msg_sucesso = "✅ Validação concluída! O Termo de Responsabilidade foi enviado para a Fila de Impressão (abaixo)."
                                else:
                                    st.session_state.msg_sucesso = "✅ Ciclo de movimentação fechado! Dashboard atualizado em tempo real."
                                
                                st.cache_data.clear()
                                registrar_log_auditoria("VALIDAÇÃO CONCLUÍDA", pat_real, f"Mov. {id_selecionado} concluída. Cautela atual: {nova_cautela}.")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Erro ao concluir movimentação: {e}")
                        else:
                            st.error("Complete as 3 caixas de verificação antes de validar.")
            else:
                st.warning("⚠️ Patrimônio vinculado não foi localizado na base mestra.")

    st.divider()
    with st.expander("🛠️ Movimentação Avulsa (Excepcional / Sem solicitação prévia)"):
        st.info("Utilize esta opção apenas caso o equipamento tenha chegado/saído sem que a equipa tenha aberto uma solicitação no sistema.")
        pat_avulso = st.text_input("Bipar/Digitar Patrimônio ou Série:")
        if pat_avulso:
            ativo_avulso = buscar_ativo(pat_avulso, df_ativos)
            if not ativo_avulso.empty:
                reg_avulso = ativo_avulso.iloc[0].to_dict()
                st.write(f"Ativo: {reg_avulso.get('marca')} {reg_avulso.get('modelo')} | Cautela Atual: {reg_avulso.get('cautela')}")
                
                with st.form("form_avulso"):
                    cA, cB = st.columns(2)
                    with cA:
                        status_av = st.selectbox("Status", ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"])
                    with cB:
                        cautela_av = st.text_input("Nova Cautela", value=reg_avulso.get('cautela', ''))
                    
                    if st.form_submit_button("✅ Forçar Atualização"):
                        dados_update_av = {
                            'status_sistema': status_av,
                            'cautela': cautela_av.strip(),
                            'atualizado_em': datetime.now().strftime('%Y-%m-%d')
                        }
                        try:
                            supabase.table('ativos_master').update(dados_update_av).eq('patrimonio', reg_avulso['patrimonio']).execute()
                            st.cache_data.clear()
                            registrar_log_auditoria("MOVIMENTAÇÃO AVULSA", reg_avulso['patrimonio'], f"Atualizado para {status_av} / {cautela_av}")
                            st.success("✅ Atualizado com sucesso.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro: {e}")
            else:
                st.warning("Não encontrado.")

# ==========================================
# MÓDULO 4: GESTÃO DE TERMOS E DIVERGÊNCIAS
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("4"):
    st.header("📄 Gestão de Termos e Divergências")
    
    if st.session_state.get('pdf_termo_pronto'):
        st.success(st.session_state.pdf_termo_pronto.get('msg', "✅ Termo gerado com sucesso!"))
        st.download_button(
            label="📥 Baixar Termo PDF", 
            data=st.session_state.pdf_termo_pronto['bytes'], 
            file_name=st.session_state.pdf_termo_pronto['nome_arquivo'], 
            mime='application/pdf',
            type="primary"
        )
        if st.button("✖️ Fechar Aviso"):
            st.session_state.pdf_termo_pronto = None
            st.rerun()
        st.divider()

    aba_termos, aba_diverg = st.tabs(["Emissão e Baixa de Termos", "Tratar Divergências"])
    
    with aba_termos:
        # --- FILA DE IMPRESSÃO ---
        st.markdown("###### 🖨️ Fila de Impressão (Termos Pendentes)")
        st.caption("Termos gerados automaticamente pelas Movimentações (MOV-01) e que aguardam impressão e assinatura.")
        termos_pendentes = df_termos[df_termos['status_termo'] == 'Pendente Impressão'] if not df_termos.empty else pd.DataFrame()
        
        if not termos_pendentes.empty:
            st.dataframe(termos_pendentes[['id_termo', 'patrimonio', 'responsavel', 'matricula', 'data_emissao']], use_container_width=True)
            
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                id_imp = st.selectbox("Selecione o Termo para Imprimir:", termos_pendentes['id_termo'].tolist())
            with col_f2:
                st.write("")
                st.write("")
                if st.button("🖨️ Gerar PDF e Ativar", type="primary", use_container_width=True):
                    t_info = termos_pendentes[termos_pendentes['id_termo'] == id_imp].iloc[0]
                    pat_real = t_info['patrimonio']
                    mat = t_info['matricula']
                    
                    ativo_match = buscar_ativo(pat_real, df_ativos)
                    emp_match = df_empregados[df_empregados['matricula'].astype(str) == str(mat)] if not df_empregados.empty else pd.DataFrame()
                    
                    if not ativo_match.empty:
                        emp = emp_match.iloc[0].to_dict() if not emp_match.empty else {}
                        resp_nome = t_info['responsavel']
                        resp_cpf = emp.get('cpf', '')
                        resp_rg = emp.get('rg', '')
                        resp_proj = emp.get('projeto', ativo_match.iloc[0].get('projeto', ''))
                        resp_unid = t_info['unidade']
                        
                        caminho_pdf = gerar_termo_pdf(pat_real, resp_nome, mat, resp_cpf, resp_rg, resp_proj, resp_unid, ativo_match)
                        with open(caminho_pdf, "rb") as pdf_file: 
                            PDFbyte = pdf_file.read()
                        
                        try:
                            supabase.table('termos').update({'status_termo': 'Ativo'}).eq('id_termo', id_imp).execute()
                            st.cache_data.clear()
                            
                            st.session_state.pdf_termo_pronto = {
                                'bytes': PDFbyte,
                                'nome_arquivo': f"Termo_{pat_real}.pdf",
                                'msg': f"✅ Termo {id_imp} gerado e ativado no sistema!"
                            }
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar status: {e}")
                    else:
                        st.error("Erro: Ativo vinculado a este termo não encontrado na base.")
        else:
            st.success("🎉 Nenhum termo pendente na fila de impressão.")
            
        st.divider()

        # --- AÇÕES MANUAIS (AVULSAS E BAIXA) ---
        opcao_termo = st.radio("Outras Ações:", ["Encerrar Termo (Devolução)", "Emitir Novo Termo Excepcional"], horizontal=True)
        
        if opcao_termo == "Emitir Novo Termo Excepcional":
            st.info("Utilize esta opção apenas para emitir termos manuais fora do fluxo padrão de movimentação.")
            st.markdown("###### 🔍 Auto-Preenchimento de Colaborador")
            matricula_busca = st.text_input("Digite a Matrícula e pressione Enter para buscar os dados:")
            
            emp_dict = {'nome': '', 'cpf': '', 'rg': '', 'projeto': '', 'unidade': ''}
            if matricula_busca.strip() and not df_empregados.empty:
                match_emp = df_empregados[df_empregados['matricula'].astype(str) == matricula_busca.strip()]
                if not match_emp.empty:
                    emp_dict = match_emp.iloc[0].fillna("").to_dict()
                    st.success(f"✅ Colaborador localizado: {emp_dict.get('nome', '')}")
                else:
                    st.warning("⚠️ Matrícula não encontrada na base. Preencha os campos abaixo manualmente.")
            
            with st.form("form_termo_avulso"):
                st.markdown("###### 📝 Detalhes do Documento")
                colA, colB = st.columns(2)
                with colA:
                    patrimonio_termo = st.text_input("Patrimônio ou Série do Equipamento:")
                    responsavel_termo = st.text_input("Nome do Responsável:", value=emp_dict.get('nome', ''))
                    cpf_termo = st.text_input("CPF:", value=emp_dict.get('cpf', ''))
                    rg_termo = st.text_input("RG:", value=emp_dict.get('rg', ''))
                with colB:
                    matricula_termo = st.text_input("Matrícula (Confirmação):", value=matricula_busca.strip())
                    unidade_termo = st.text_input("Unidade / Área / Coordenação:", value=emp_dict.get('unidade', ''))
                    projeto_termo = st.text_input("Projeto:", value=emp_dict.get('projeto', ''))
                submit_termo = st.form_submit_button("Gerar PDF do Termo", type="primary")
                
            if submit_termo and patrimonio_termo.strip():
                ativo_info_termo = buscar_ativo(patrimonio_termo, df_ativos)
                
                if not ativo_info_termo.empty:
                    pat_real = ativo_info_termo.iloc[0]['patrimonio']
                    caminho_pdf = gerar_termo_pdf(
                        pat_real, responsavel_termo.strip(), matricula_termo.strip(), 
                        cpf_termo.strip(), rg_termo.strip(), projeto_termo.strip(), unidade_termo.strip(), 
                        ativo_info_termo
                    )
                    with open(caminho_pdf, "rb") as pdf_file: 
                        PDFbyte = pdf_file.read()
                    
                    id_termo = f"TRM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    novo_termo = {
                        'id_termo': id_termo, 
                        'patrimonio': pat_real, 
                        'responsavel': responsavel_termo.strip(), 
                        'matricula': matricula_termo.strip(), 
                        'unidade': unidade_termo.strip(), 
                        'data_emissao': datetime.now().strftime('%Y-%m-%d'), 
                        'data_baixa': '', 
                        'status_termo': 'Ativo'
                    }
                    try:
                        supabase.table('termos').insert(novo_termo).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria("EMISSÃO DE TERMO (AVULSO)", pat_real, f"Termo {id_termo} emitido manualmente.")
                        
                        st.session_state.pdf_termo_pronto = {
                            'bytes': PDFbyte,
                            'nome_arquivo': f"Termo_{pat_real}.pdf",
                            'msg': "✅ Termo registrado e ativado na nuvem!"
                        }
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar termo: {e}")
                else:
                    st.error("Equipamento não localizado. Verifique o patrimônio/série.")
        else:
            pat_baixa = st.text_input("Patrimônio ou Série devolvido:")
            if st.button("Baixar Termo Ativo", type="primary"):
                ativo_info_baixa = buscar_ativo(pat_baixa, df_ativos)
                
                if not ativo_info_baixa.empty:
                    pat_real = ativo_info_baixa.iloc[0]['patrimonio']
                    termos_ativos = df_termos[(df_termos['patrimonio'].astype(str) == str(pat_real)) & (df_termos['status_termo'].isin(['Ativo', 'Pendente Impressão']))] if not df_termos.empty else pd.DataFrame()
                    
                    if not termos_ativos.empty:
                        id_trm = termos_ativos.iloc[0]['id_termo']
                        dados_update_trm = {
                            'data_baixa': datetime.now().strftime('%Y-%m-%d'),
                            'status_termo': 'Encerrado'
                        }
                        try:
                            supabase.table('termos').update(dados_update_trm).eq('id_termo', id_trm).execute()
                            st.cache_data.clear()
                            registrar_log_auditoria("BAIXA DE TERMO", pat_real, f"Termo {id_trm} encerrado por devolução.")
                            st.success("✅ Termo encerrado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao encerrar termo: {e}")
                    else:
                        st.warning("Nenhum termo ativo encontrado para este equipamento.")
                else:
                    st.error("Patrimônio ou série não localizado.")

    with aba_diverg:
        st.write("Abra ou Trate divergências físicas e cadastrais.")
        pendentes = df_diverg[df_diverg['status_resolucao'] != 'Resolvido'] if not df_diverg.empty else pd.DataFrame()
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("###### Reportar Nova Divergência")
            pat_div = st.text_input("Patrimônio com Divergência:")
            if st.button("🚨 Abrir Alerta e Segregar Ativo", type="secondary"):
                if pat_div.strip():
                    id_div = f"DIV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    nova_div = {
                        'id_divergencia': id_div, 
                        'data_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                        'patrimonio': pat_div.strip(), 
                        'tipo_divergencia': 'Inconsistência Relatada pelo Almoxarifado', 
                        'status_resolucao': 'Pendente', 
                        'analista_responsavel': st.session_state.nome_real, 
                        'observacoes': 'Ativo segregado manualmente.'
                    }
                    try:
                        supabase.table('divergencias').insert(nova_div).execute()
                        st.cache_data.clear()
                        registrar_log_auditoria("DIVERGÊNCIA ABERTA", pat_div.strip(), "Abertura manual de divergência.")
                        st.success("Alerta criado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
                        
        with c2:
            st.markdown("###### Resolver Pendência")
            if not pendentes.empty:
                id_div_selecionada = st.selectbox("Selecione a Divergência:", pendentes['id_divergencia'].tolist())
                obs = st.text_area("Justificativa / Ação Tomada:")
                analista = st.text_input("Analista Responsável:", value=st.session_state.nome_real)
                if st.button("Aplicar Resolução", type="primary"):
                    if obs.strip() and analista.strip():
                        try:
                            dados_update_div = {
                                'status_resolucao': 'Resolvido',
                                'observacoes': obs.strip(),
                                'analista_responsavel': analista.strip()
                            }
                            supabase.table('divergencias').update(dados_update_div).eq('id_divergencia', id_div_selecionada).execute()
                            st.cache_data.clear()
                            
                            div_pat = pendentes[pendentes['id_divergencia'] == id_div_selecionada].iloc[0]['patrimonio']
                            registrar_log_auditoria(
                                "RESOLUÇÃO DIVERGÊNCIA", 
                                div_pat, 
                                f"Divergência {id_div_selecionada} resolvida. Ação: {obs.strip()}"
                            )
                            st.success("✅ Divergência resolvida com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao resolver: {e}")
                    else:
                        st.error("Preencha a justificativa.")
            else:
                st.success("Nenhuma divergência pendente!")

# ==========================================
# MÓDULO 5: DIAGNÓSTICO (LABORATÓRIO)
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("5"):
    st.header("🔬 Laboratório Técnico")
    patrimonio_lab = st.text_input("Patrimônio ou Série em Análise:")
    resultado = st.radio("Parecer Técnico:", ["APTO", "APTO COM RESSALVA", "REPARADO", "CALIBRADO", "REPROVADO", "INSERVÍVEL"])
    
    if st.button("Atualizar Base", type="primary"):
        ativo_match = buscar_ativo(patrimonio_lab, df_ativos)
        
        if not ativo_match.empty:
            pat_real = ativo_match.iloc[0]['patrimonio']
            cond_antiga = ativo_match.iloc[0].get('condicoes_para_uso', '')
            
            novo_status = 'Baixado' if ("INSERVÍVEL" in resultado or "REPROVADO" in resultado) else 'Disponível'
            
            dados_update_lab = {
                'condicoes_para_uso': resultado,
                'status_sistema': novo_status,
                'atualizado_em': datetime.now().strftime('%Y-%m-%d')
            }
            
            try:
                supabase.table('ativos_master').update(dados_update_lab).eq('patrimonio', pat_real).execute()
                st.cache_data.clear()
                
                registrar_log_auditoria(
                    "LAUDO LABORATÓRIO", 
                    pat_real, 
                    f"Parecer: '{cond_antiga}' -> '{resultado}'. Novo Status: '{novo_status}'."
                )
                st.success(f"✅ Laudo registrado! Ativo atualizado para: {novo_status}")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar laudo: {e}")
        else:
            st.warning("⚠️ Patrimônio ou série não localizado.")

# ==========================================
# MÓDULO 6: GESTÃO DE USUÁRIOS (MASTER)
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("6"):
    st.header("👥 Painel Admin - Gestão de Usuários")
    
    aba_listar, aba_novo, aba_editar = st.tabs(["Visão Geral", "Novo Usuário", "Editar / Resetar Senha"])
    
    with aba_listar:
        st.dataframe(df_usuarios, use_container_width=True)
        
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
elif selecao_perfil and selecao_perfil.startswith("7"):
    if st.session_state.perfil != 'Master':
        st.error("⛔ Acesso negado. Este módulo é exclusivo para o perfil Gestor (Master).")
        st.stop()
        
    st.header("🛡️ Central de Auditoria e Rastreabilidade (Gestor)")
    
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
        
    col_a1, col_a2, col_a3 = st.columns(3)
    total_ev = len(df_auditoria)
    total_uploads = len(df_auditoria[df_auditoria['Tipo de Evento'].str.contains('UPLOAD|CADASTRO', na=False)]) if not df_auditoria.empty else 0
    total_movs = len(df_auditoria[df_auditoria['Tipo de Evento'].str.contains('MOV|CONFERÊNCIA|TERMO', na=False)]) if not df_auditoria.empty else 0
    
    col_a1.metric("Total de Eventos Auditados", total_ev)
    col_a2.metric("Cargas / Cadastros Realizados", total_uploads)
    col_a3.metric("Operações de Campo / Almox.", total_movs)
    
    st.divider()
    
    if not df_auditoria.empty:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            tipos_unicos = ["Todos"] + sorted(df_auditoria['Tipo de Evento'].unique().tolist())
            filtro_tipo = st.selectbox("Filtrar por Tipo de Ação:", tipos_unicos)
        with col_f2:
            busca_texto = st.text_input("Buscar por Patrimônio, Usuário ou Palavra-chave:")
            
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
            
        st.dataframe(df_filtrado, use_container_width=True, height=450)
        
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
