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
COLUNAS_ATIVOS = ['codigo_d365', 'patrimonio_placa', 'numero_serie', 'marca', 'modelo', 'categoria', 'status_sistema', 'condicao_fisica', 'localizacao_atual', 'responsavel_atual', 'data_ultima_mov', 'observacoes']
COLUNAS_MOV = ['id_mov', 'data_hora', 'tipo_mov', 'patrimonio', 'origem', 'destino', 'solicitante', 'autorizador', 'status_mov']
COLUNAS_TERMOS = ['id_termo', 'patrimonio', 'responsavel', 'matricula', 'unidade', 'data_emissao', 'data_baixa', 'status_termo']
COLUNAS_DIVERG = ['id_divergencia', 'data_registro', 'patrimonio', 'tipo_divergencia', 'status_resolucao', 'analista_responsavel', 'observacoes']
COLUNAS_USUARIOS = ['usuario', 'senha', 'perfil', 'nome']

ASSINATURA_DEV_HTML = """
<div style='text-align: center; margin-top: 20px; padding: 6px; color: #888888; font-size: 0.75rem;'>
    Desenvolvido por <strong>Marcos Paulo Da Veiga Carvalho</strong>
</div>
"""

def exibir_marca_desenvolvedor():
    """Renderiza a marca do desenvolvedor de forma discreta."""
    st.markdown(ASSINATURA_DEV_HTML, unsafe_allow_html=True)

def normalizar_nome_coluna(col):
    """Remove qualquer acento (õ, ó, ô, ç, ã, é, í, etc.), espaços extras e converte para minúsculas."""
    texto = str(col).strip().lower()
    texto_sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    return texto_sem_acento.replace(' ', '_')

def preparar_para_supabase(df, colunas_validas):
    """Filtra apenas colunas existentes no banco e converte datas/nulos para texto compatível com JSON."""
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
    """Registra eventos de auditoria na nuvem sem exigir criação de nova tabela no Supabase."""
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
        supabase.table('divergencias').upsert([registro]).execute()
    except Exception:
        pass

def calcular_uso_supabase(dfs_lista, limite_mb=500.0):
    """Calcula a estimativa de armazenamento utilizado no PostgreSQL/Supabase (com overhead de índices)."""
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

        df_ativos = pd.DataFrame(ativos_res.data) if ativos_res.data else pd.DataFrame(columns=COLUNAS_ATIVOS)
        df_mov = pd.DataFrame(mov_res.data) if mov_res.data else pd.DataFrame(columns=COLUNAS_MOV)
        df_termos = pd.DataFrame(termos_res.data) if termos_res.data else pd.DataFrame(columns=COLUNAS_TERMOS)
        df_diverg_bruto = pd.DataFrame(diverg_res.data) if diverg_res.data else pd.DataFrame(columns=COLUNAS_DIVERG)
        df_usuarios = pd.DataFrame(usuarios_res.data) if usuarios_res.data else pd.DataFrame(columns=COLUNAS_USUARIOS)
        
        for col in COLUNAS_ATIVOS:
            if col not in df_ativos.columns:
                df_ativos[col] = ""
        if not df_ativos.empty:
            df_ativos['patrimonio_placa'] = df_ativos['patrimonio_placa'].astype(str).str.strip()

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
            
        return df_ativos, df_mov, df_termos, df_diverg, df_usuarios, df_logs
    except Exception as e:
        st.error(f"Erro ao carregar dados da nuvem: {e}")
        return (
            pd.DataFrame(columns=COLUNAS_ATIVOS),
            pd.DataFrame(columns=COLUNAS_MOV),
            pd.DataFrame(columns=COLUNAS_TERMOS),
            pd.DataFrame(columns=COLUNAS_DIVERG),
            pd.DataFrame(columns=COLUNAS_USUARIOS),
            pd.DataFrame(columns=COLUNAS_DIVERG)
        )

df_ativos, df_mov, df_termos, df_diverg, df_usuarios, df_logs = carregar_dados()

def salvar_dados(df_a=pd.DataFrame(), df_m=pd.DataFrame(), df_t=pd.DataFrame(), df_d=pd.DataFrame(), df_u=pd.DataFrame()):
    try:
        if not df_a.empty:
            dados_a = preparar_para_supabase(df_a, COLUNAS_ATIVOS)
            if dados_a:
                supabase.table('ativos_master').upsert(dados_a).execute()
        if not df_m.empty:
            dados_m = preparar_para_supabase(df_m, COLUNAS_MOV)
            if dados_m:
                supabase.table('movimentacoes').upsert(dados_m).execute()
        if not df_t.empty:
            dados_t = preparar_para_supabase(df_t, COLUNAS_TERMOS)
            if dados_t:
                supabase.table('termos').upsert(dados_t).execute()
        if not df_d.empty:
            dados_d = preparar_para_supabase(df_d, COLUNAS_DIVERG)
            if dados_d:
                supabase.table('divergencias').upsert(dados_d).execute()
        if not df_u.empty:
            dados_u = preparar_para_supabase(df_u, COLUNAS_USUARIOS)
            if dados_u:
                supabase.table('usuarios').upsert(dados_u).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao guardar na nuvem: {e}")
        return False

# ==========================================
# SISTEMA DE AUTENTICAÇÃO
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.usuario = None
    st.session_state.perfil = None
    st.session_state.nome_real = None
    st.session_state.modulo_ativo = None

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
# FUNÇÃO GERADORA DE PDF
# ==========================================
def limpar_texto_pdf(texto):
    return str(texto).encode('latin-1', 'replace').decode('latin-1')

def gerar_termo_pdf(patrimonio, responsavel, matricula, unidade, info_ativo):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, txt=limpar_texto_pdf("TERMO DE RESPONSABILIDADE DE EQUIPAMENTO"), ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", '', 11)
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    marca = str(info_ativo.iloc[0].get('marca', ''))
    modelo = str(info_ativo.iloc[0].get('modelo', ''))
    serie = str(info_ativo.iloc[0].get('numero_serie', ''))
    
    linhas = [
        f"Pelo presente termo, o colaborador {responsavel}, matrícula {matricula},",
        f"lotado na unidade {unidade}, declara ter recebido o equipamento abaixo",
        "descrito em perfeitas condições de uso, assumindo o compromisso de zelar",
        "pela sua guarda e conservação.",
        "",
        "DETALHES DO EQUIPAMENTO:",
        f"- Patrimônio: {patrimonio}",
        f"- Marca / Modelo: {marca} {modelo}",
        f"- Número de Série: {serie}",
        f"- Data de Emissão: {data_atual}",
        ""
    ]
    texto = "\n".join(linhas)
    
    pdf.multi_cell(0, 8, txt=limpar_texto_pdf(texto))
    pdf.ln(20)
    pdf.cell(90, 10, txt="___________________________________", align='C')
    pdf.cell(90, 10, txt="___________________________________", ln=True, align='C')
    pdf.cell(90, 10, txt=limpar_texto_pdf("Assinatura do Colaborador"), align='C')
    pdf.cell(90, 10, txt=limpar_texto_pdf("Assinatura do Almoxarifado"), ln=True, align='C')
    
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
        "3. Validação e Movimentação (Almoxarifado)", 
        "4. Diagnóstico (Laboratório)",
        "5. Gestão de Usuários (Admin)",
        "6. 🛡️ Auditoria Geral (Gestor)"
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
    
    if 'resumo_ultima_operacao' in st.session_state and st.session_state.resumo_ultima_operacao:
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

    col1, col2, col3, col4 = st.columns(4)
    total_ativos = len(df_ativos)
    disp_estoque = len(df_ativos[df_ativos['status_sistema'] == 'Disponível']) if not df_ativos.empty else 0
    em_uso = len(df_ativos[df_ativos['status_sistema'] == 'Em uso']) if not df_ativos.empty else 0
    diverg_pend = len(df_diverg[df_diverg['status_resolucao'] != 'Resolvido']) if not df_diverg.empty else 0

    col1.metric("Total de Ativos", total_ativos)
    col2.metric("Disponíveis em Estoque", disp_estoque)
    col3.metric("Em Uso (Campo)", em_uso)
    col4.metric("Divergências Pendentes", diverg_pend, delta_color="inverse")

    aba_inv, aba_hist_mov, aba_hist_termos, aba_cadastro, aba_io = st.tabs([
        "Inventário Geral", "Histórico de Movimentações", "Termos Emitidos", "➕ Novo Cadastro Manual", "🔄 Importar / Exportar"
    ])
    
    with aba_inv:
        st.dataframe(df_ativos[COLUNAS_ATIVOS] if not df_ativos.empty else df_ativos, use_container_width=True)
    with aba_hist_mov:
        st.dataframe(df_mov, use_container_width=True)
    with aba_hist_termos:
        st.dataframe(df_termos, use_container_width=True)
        
    with aba_cadastro:
        st.subheader("Cadastrar ou Atualizar Ativo Individual")
        with st.form("form_novo_ativo"):
            colA, colB, colC = st.columns(3)
            with colA:
                cad_patrimonio = st.text_input("Patrimônio / Placa *")
                cad_codigo = st.text_input("Código D365")
                cad_serie = st.text_input("Número de Série")
            with colB:
                cad_marca = st.text_input("Marca")
                cad_modelo = st.text_input("Modelo")
                cad_categoria = st.selectbox("Categoria", ["OTDR", "Máquina de Fusão", "Ferramenta", "Veículo", "Informática", "Outros"])
            with colC:
                cad_status = st.selectbox("Status", ["Disponível", "Em uso", "Em manutenção", "Em trânsito", "Baixado"])
                cad_condicao = st.selectbox("Condição Física", ["Novo", "Bom", "Regular", "Ruim", "Inservível"])
                cad_loc = st.text_input("Localização Atual", value="Almoxarifado Central")
            
            cad_resp = st.text_input("Responsável Atual", value="Almoxarifado")
            cad_obs = st.text_area("Observações")
            
            submit_cadastro = st.form_submit_button("💾 Salvar Ativo na Nuvem", type="primary")
            
            if submit_cadastro:
                if cad_patrimonio.strip():
                    pat_limpo = cad_patrimonio.strip()
                    qtd_antes = len(df_ativos)
                    ja_existia = (not df_ativos.empty) and (pat_limpo in df_ativos['patrimonio_placa'].astype(str).values)
                    
                    novo_ativo = pd.DataFrame([{
                        'codigo_d365': cad_codigo.strip(),
                        'patrimonio_placa': pat_limpo,
                        'numero_serie': cad_serie.strip(),
                        'marca': cad_marca.strip(),
                        'modelo': cad_modelo.strip(),
                        'categoria': cad_categoria,
                        'status_sistema': cad_status,
                        'condicao_fisica': cad_condicao,
                        'localizacao_atual': cad_loc.strip(),
                        'responsavel_atual': cad_resp.strip(),
                        'data_ultima_mov': datetime.now().strftime('%Y-%m-%d'),
                        'observacoes': cad_obs.strip()
                    }])
                    if salvar_dados(df_a=novo_ativo):
                        qtd_depois = qtd_antes if ja_existia else qtd_antes + 1
                        tipo_op = "ATUALIZAÇÃO MANUAL" if ja_existia else "CADASTRO MANUAL"
                        detalhe_log = f"Ativo {pat_limpo} ({cad_marca} {cad_modelo}) salvo. Base passou de {qtd_antes} para {qtd_depois} ativos."
                        registrar_log_auditoria(tipo_op, pat_limpo, detalhe_log)
                        
                        st.session_state.resumo_ultima_operacao = {
                            'titulo': f"Cadastro Manual Concluído ({pat_limpo})",
                            'hora': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                            'qtd_antes': qtd_antes,
                            'novos': 0 if ja_existia else 1,
                            'atualizados': 1 if ja_existia else 0,
                            'qtd_depois': qtd_depois
                        }
                        st.rerun()
                else:
                    st.error("O campo 'Patrimônio / Placa' é obrigatório.")

    with aba_io:
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
        
        arquivo_up = st.file_uploader("Arraste o arquivo Excel (.xlsx)", type=["xlsx"])
        if arquivo_up:
            try:
                df_up = pd.read_excel(arquivo_up)
                df_up.columns = [normalizar_nome_coluna(c) for c in df_up.columns]
                
                if 'patrimonio_placa' not in df_up.columns:
                    st.error(f"A coluna obrigatória 'patrimonio_placa' não foi encontrada na planilha. Colunas lidas: {list(df_up.columns)}")
                else:
                    df_up = df_up.dropna(subset=['patrimonio_placa'])
                    df_up['patrimonio_placa'] = df_up['patrimonio_placa'].astype(str).str.strip()
                    df_up = df_up[df_up['patrimonio_placa'] != '']
                    df_up = df_up.drop_duplicates(subset=['patrimonio_placa'], keep='last')
                    
                    atuais_set = set(df_ativos['patrimonio_placa'].astype(str).str.strip()) if not df_ativos.empty else set()
                    novos_set = set(df_up['patrimonio_placa'])
                    
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
                            if salvar_dados(df_a=df_up):
                                detalhe_log = (
                                    f"Arquivo '{arquivo_up.name}' enviado ({len(df_up)} itens). "
                                    f"Antes: {qtd_antes} | Novos: +{qtd_novos} | Atualizados: {qtd_atualizados} | Depois: {qtd_depois}."
                                )
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

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 2: SOLICITAÇÃO DE MOVIMENTAÇÃO
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("2"):
    st.header("📝 Solicitação de Movimentação")
    with st.form("form_solicitacao"):
        col1, col2 = st.columns(2)
        with col1:
            opcoes_mov = [
                "MOV-01 | Almoxarifado -> Colaborador", 
                "MOV-02 | Colaborador -> Almoxarifado", 
                "MOV-03 | Unidade -> Unidade", 
                "MOV-04 | Almoxarifado -> Laboratório"
            ]
            tipo_mov = st.selectbox("Tipo de Movimentação", opcoes_mov)
            patrimonio = st.text_input("Placa / Patrimônio do Ativo")
            solicitante = st.text_input("Nome do Solicitante (Matrícula)", value=st.session_state.nome_real)
        with col2:
            origem = st.text_input("Unidade/Equipe de Origem")
            destino = st.text_input("Unidade/Equipe de Destino")
            motivo = st.text_area("Motivo da Movimentação")
        
        if st.form_submit_button("Registrar Solicitação", type="primary"):
            if patrimonio.strip() and solicitante.strip():
                id_mov = f"MOV-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                pat_m = patrimonio.strip()
                nova_mov = pd.DataFrame([{
                    'id_mov': id_mov, 
                    'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                    'tipo_mov': tipo_mov[:6], 
                    'patrimonio': pat_m, 
                    'origem': origem.strip(), 
                    'destino': destino.strip(), 
                    'solicitante': solicitante.strip(), 
                    'autorizador': 'Pendente', 
                    'status_mov': 'Aguardando Conferência'
                }])
                if salvar_dados(df_m=nova_mov):
                    registrar_log_auditoria(
                        "SOLICITAÇÃO MOV.", 
                        pat_m, 
                        f"ID {id_mov} ({tipo_mov[:6]}): de '{origem.strip()}' para '{destino.strip()}'. Solicitante: {solicitante.strip()}."
                    )
                    st.success("✅ Solicitação registrada com sucesso e sistema atualizado! Encaminhe para conferência no Almoxarifado.")
            else:
                st.error("Preencha o Patrimônio e o Solicitante.")

# ==========================================
# MÓDULO 3: ALMOXARIFADO CENTRAL
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("3"):
    st.header("📦 Almoxarifado Central")
    aba1, aba2, aba3 = st.tabs(["Conferência Física", "Gestão de Termos", "Tratar Divergências"])
    
    with aba1:
        patrimonio_busca = st.text_input("Bipar/Digitar Patrimônio:")
        if patrimonio_busca:
            pat_busca_limpo = patrimonio_busca.strip()
            ativo_info = df_ativos[df_ativos['patrimonio_placa'].astype(str) == pat_busca_limpo] if not df_ativos.empty else pd.DataFrame()
            
            if not ativo_info.empty:
                registro_atual = ativo_info.iloc[0].to_dict()
                status_antigo = registro_atual.get('status_sistema', '')
                resp_antigo = registro_atual.get('responsavel_atual', '')
                loc_antiga = registro_atual.get('localizacao_atual', '')
                
                st.info(f"**Ativo Localizado:** {registro_atual.get('marca', '')} {registro_atual.get('modelo', '')} | **Status Atual:** {status_antigo}")
                
                colA, colB, colC = st.columns(3)
                with colA: 
                    novo_status = st.selectbox("Novo Status:", ["Disponível", "Em uso", "Em manutenção", "Em trânsito"])
                with colB: 
                    novo_resp = st.text_input("Novo Responsável", value=str(resp_antigo if resp_antigo else 'Almoxarifado'))
                with colC: 
                    nova_loc = st.text_input("Nova Localização", value=str(loc_antiga if loc_antiga else 'Almoxarifado Central'))
                
                d365_ok = st.checkbox("Status e Localização conferem no D365?")
                eponto_ok = st.checkbox("Movimentação validada no e-Ponto?")
                fisico_ok = st.checkbox("Estado físico, Série e Acessórios conferem?")
                
                if st.button("Validar e Concluir Movimentação", type="primary"):
                    if d365_ok and eponto_ok and fisico_ok:
                        registro_atual['status_sistema'] = novo_status
                        registro_atual['responsavel_atual'] = novo_resp.strip()
                        registro_atual['localizacao_atual'] = nova_loc.strip()
                        registro_atual['data_ultima_mov'] = datetime.now().strftime('%Y-%m-%d')
                        
                        if salvar_dados(df_a=pd.DataFrame([registro_atual])):
                            registrar_log_auditoria(
                                "CONFERÊNCIA ALMOX.", 
                                pat_busca_limpo, 
                                f"Status: '{status_antigo}' -> '{novo_status}' | Resp: '{resp_antigo}' -> '{novo_resp.strip()}' | Loc: '{loc_antiga}' -> '{nova_loc.strip()}'."
                            )
                            st.success("✅ Movimentação concluída e atualizada na nuvem!")
                            st.rerun()
                    else:
                        id_div = f"DIV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        nova_div = pd.DataFrame([{
                            'id_divergencia': id_div, 
                            'data_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                            'patrimonio': pat_busca_limpo, 
                            'tipo_divergencia': 'Inconsistência de Cadastro/Físico', 
                            'status_resolucao': 'Pendente', 
                            'analista_responsavel': st.session_state.nome_real, 
                            'observacoes': 'Bloqueado na conferência física tripla.'
                        }])
                        if salvar_dados(df_d=nova_div):
                            registrar_log_auditoria("DIVERGÊNCIA ABERTA", pat_busca_limpo, f"Divergência {id_div} gerada por bloqueio na conferência tripla.")
                            st.error("DIVERGÊNCIA DETECTADA. Ativo segregado e alerta criado.")
            else:
                st.warning("Patrimônio não localizado na base mestra.")
                
    with aba2:
        opcao_termo = st.radio("Ação:", ["Emitir Novo Termo", "Encerrar Termo (Devolução)"], horizontal=True)
        if opcao_termo == "Emitir Novo Termo":
            with st.form("form_termo"):
                colA, colB = st.columns(2)
                with colA:
                    patrimonio_termo = st.text_input("Patrimônio:")
                    responsavel_termo = st.text_input("Novo Responsável:")
                with colB:
                    matricula_termo = st.text_input("Matrícula:")
                    unidade_termo = st.text_input("Unidade / CC:")
                submit_termo = st.form_submit_button("Criar Documento", type="primary")
                
            if submit_termo and patrimonio_termo.strip():
                pat_termo_limpo = patrimonio_termo.strip()
                ativo_info_termo = df_ativos[df_ativos['patrimonio_placa'].astype(str) == pat_termo_limpo] if not df_ativos.empty else pd.DataFrame()
                if not ativo_info_termo.empty:
                    caminho_pdf = gerar_termo_pdf(
                        pat_termo_limpo, responsavel_termo.strip(), matricula_termo.strip(), unidade_termo.strip(), ativo_info_termo
                    )
                    with open(caminho_pdf, "rb") as pdf_file: 
                        PDFbyte = pdf_file.read()
                    
                    id_termo = f"TRM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    novo_termo = pd.DataFrame([{
                        'id_termo': id_termo, 
                        'patrimonio': pat_termo_limpo, 
                        'responsavel': responsavel_termo.strip(), 
                        'matricula': matricula_termo.strip(), 
                        'unidade': unidade_termo.strip(), 
                        'data_emissao': datetime.now().strftime('%Y-%m-%d'), 
                        'data_baixa': '', 
                        'status_termo': 'Ativo'
                    }])
                    if salvar_dados(df_t=novo_termo):
                        registrar_log_auditoria(
                            "EMISSÃO DE TERMO", 
                            pat_termo_limpo, 
                            f"Termo {id_termo} emitido para {responsavel_termo.strip()} (Mat: {matricula_termo.strip()}, Unid: {unidade_termo.strip()})."
                        )
                        st.success("✅ Termo registrado e sistema atualizado! Clique abaixo para baixar o PDF.")
                        st.download_button(
                            label="📥 Baixar Termo PDF", 
                            data=PDFbyte, 
                            file_name=f"Termo_{pat_termo_limpo}.pdf", 
                            mime='application/pdf'
                        )
                else:
                    st.error("Patrimônio não localizado na base mestra.")
        else:
            pat_baixa = st.text_input("Patrimônio devolvido:")
            if st.button("Baixar Termo Ativo", type="primary"):
                pat_baixa_limpo = pat_baixa.strip()
                termos_ativos = df_termos[(df_termos['patrimonio'].astype(str) == pat_baixa_limpo) & (df_termos['status_termo'] == 'Ativo')] if not df_termos.empty else pd.DataFrame()
                if not termos_ativos.empty:
                    termo_atual = termos_ativos.iloc[0].to_dict()
                    termo_atual['data_baixa'] = datetime.now().strftime('%Y-%m-%d')
                    termo_atual['status_termo'] = 'Encerrado'
                    if salvar_dados(df_t=pd.DataFrame([termo_atual])):
                        registrar_log_auditoria("BAIXA DE TERMO", pat_baixa_limpo, f"Termo {termo_atual.get('id_termo', '')} encerrado por devolução.")
                        st.success("✅ Termo encerrado com sucesso!")
                        st.rerun()
                else:
                    st.warning("Nenhum termo ativo encontrado para este patrimônio.")

    with aba3:
        pendentes = df_diverg[df_diverg['status_resolucao'] != 'Resolvido'] if not df_diverg.empty else pd.DataFrame()
        if not pendentes.empty:
            st.dataframe(pendentes, use_container_width=True)
            id_div_selecionada = st.selectbox("Resolver Divergência:", pendentes['id_divergencia'].tolist())
            obs = st.text_area("Justificativa / Ação Tomada:")
            analista = st.text_input("Analista Responsável:", value=st.session_state.nome_real)
            if st.button("Aplicar Resolução", type="primary"):
                if obs.strip() and analista.strip():
                    div_atual = pendentes[pendentes['id_divergencia'] == id_div_selecionada].iloc[0].to_dict()
                    div_atual['status_resolucao'] = 'Resolvido'
                    div_atual['observacoes'] = obs.strip()
                    div_atual['analista_responsavel'] = analista.strip()
                    if salvar_dados(df_d=pd.DataFrame([div_atual])):
                        registrar_log_auditoria(
                            "RESOLUÇÃO DIVERGÊNCIA", 
                            div_atual.get('patrimonio', id_div_selecionada), 
                            f"Divergência {id_div_selecionada} resolvida. Ação: {obs.strip()}"
                        )
                        st.success("✅ Divergência resolvida com sucesso!")
                        st.rerun()
                else:
                    st.error("Preencha a justificativa e o nome do analista.")
        else:
            st.success("Nenhuma divergência pendente no momento.")

# ==========================================
# MÓDULO 4: DIAGNÓSTICO (LABORATÓRIO)
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("4"):
    st.header("🔬 Laboratório Técnico")
    patrimonio_lab = st.text_input("Patrimônio em Análise:")
    resultado = st.radio("Parecer Técnico:", ["APTO", "APTO COM RESSALVA", "REPARADO", "CALIBRADO", "REPROVADO", "INSERVÍVEL"])
    if st.button("Atualizar Base", type="primary"):
        if patrimonio_lab.strip():
            pat_lab_limpo = patrimonio_lab.strip()
            ativo_match = df_ativos[df_ativos['patrimonio_placa'].astype(str) == pat_lab_limpo] if not df_ativos.empty else pd.DataFrame()
            if not ativo_match.empty:
                ativo_lab = ativo_match.iloc[0].to_dict()
                cond_antiga = ativo_lab.get('condicao_fisica', '')
                ativo_lab['condicao_fisica'] = resultado
                if "INSERVÍVEL" in resultado or "REPROVADO" in resultado:
                    ativo_lab['status_sistema'] = 'Baixado'
                else:
                    ativo_lab['status_sistema'] = 'Disponível'
                ativo_lab['data_ultima_mov'] = datetime.now().strftime('%Y-%m-%d')
                
                if salvar_dados(df_a=pd.DataFrame([ativo_lab])):
                    registrar_log_auditoria(
                        "LAUDO LABORATÓRIO", 
                        pat_lab_limpo, 
                        f"Parecer: '{cond_antiga}' -> '{resultado}'. Novo Status: '{ativo_lab['status_sistema']}'."
                    )
                    st.success(f"✅ Laudo registrado! Ativo atualizado para: {ativo_lab['status_sistema']}")
                    st.rerun()
            else:
                st.error("Patrimônio não localizado na base mestra.")

# ==========================================
# MÓDULO 5: GESTÃO DE USUÁRIOS (MASTER)
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("5"):
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
                        novo_registo = pd.DataFrame([{
                            'usuario': login_limpo, 
                            'senha': str(nova_senha).strip(), 
                            'perfil': novo_perfil, 
                            'nome': novo_nome.strip()
                        }])
                        if salvar_dados(df_u=novo_registo):
                            registrar_log_auditoria("CRIAÇÃO USUÁRIO", login_limpo, f"Usuário '{novo_nome.strip()}' criado com perfil '{novo_perfil}'.")
                            st.success(f"✅ Usuário {novo_nome} cadastrado com sucesso!")
                            st.rerun()
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
                        user_match['senha'] = str(senha_reset).strip()
                        user_match['perfil'] = perfil_edit
                        if salvar_dados(df_u=pd.DataFrame([user_match])):
                            registrar_log_auditoria("EDIÇÃO USUÁRIO", usuario_editar, f"Perfil/Senha atualizados (Perfil atual: {perfil_edit}).")
                            st.success(f"✅ Dados de {usuario_editar} atualizados!")
                            st.rerun()
                with col_bt2:
                    if st.button("❌ Excluir Usuário", type="primary", use_container_width=True):
                        if usuario_editar != 'master':
                            supabase.table('usuarios').delete().eq('usuario', usuario_editar).execute()
                            registrar_log_auditoria("EXCLUSÃO USUÁRIO", usuario_editar, f"Usuário {usuario_editar} removido do sistema.")
                            st.cache_data.clear()
                            st.success("✅ Usuário removido da nuvem!")
                            st.rerun()
                        else:
                            st.warning("Não é possível excluir o usuário Master principal.")

    exibir_marca_desenvolvedor()

# ==========================================
# MÓDULO 6: AUDITORIA GERAL (EXCLUSIVO GESTOR)
# ==========================================
elif selecao_perfil and selecao_perfil.startswith("6"):
    if st.session_state.perfil != 'Master':
        st.error("⛔ Acesso negado. Este módulo é exclusivo para o perfil Gestor (Master).")
        st.stop()
        
    st.header("🛡️ Central de Auditoria e Rastreabilidade (Gestor)")
    
    # --- LINHA DISCRETA DE CAPACIDADE DO SUPABASE ---
    info_cap = calcular_uso_supabase([df_ativos, df_mov, df_termos, df_diverg, df_logs, df_usuarios], limite_mb=500.0)
    st.markdown(
        f"<div style='background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 6px 14px; font-size: 0.80rem; color: #555; display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;'>"
        f"<span>☁️ <b>Armazenamento Supabase (500 MB):</b> Utilizado: <b>{info_cap['usado_mb']:.2f} MB ({info_cap['pct_usado']:.1f}%)</b> &nbsp;|&nbsp; Livre: <b>{info_cap['livre_mb']:.2f} MB ({info_cap['pct_livre']:.1f}%)</b> &nbsp;|&nbsp; Tabelas: {info_cap['dados_puros_kb']:.1f} KB ({info_cap['total_linhas']} reg.)</span>"
        f"<span style='color: #888; font-size: 0.74rem;'>Desenvolvido por Marcos Paulo Da Veiga Carvalho</span>"
        f"</div>",
        unsafe_allow_html=True
    )

    # Consolida logs do sistema + histórico de movimentações + emissões de termos em uma linha do tempo única
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
