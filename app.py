import streamlit as st
import pandas as pd
from datetime import datetime
import os
import tempfile
import io
import unicodedata

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
    
    # Mantém apenas as colunas que pertencem oficialmente à tabela do Supabase
    cols_presentes = [c for c in df.columns if c in colunas_validas]
    df_limpo = df[cols_presentes].copy()
    
    # Substitui NaN, None e NaT por string vazia
    df_limpo = df_limpo.fillna("")
    
    # Converte tudo para string limpa (evita erro de Timestamp do Excel e garante formato texto)
    for col in df_limpo.columns:
        df_limpo[col] = df_limpo[col].apply(
            lambda x: x.strftime('%Y-%m-%d') if isinstance(x, (pd.Timestamp, datetime)) else str(x).strip()
        )
        # Limpa resíduos de texto caso o Pandas tenha convertido None/NaT antes
        df_limpo[col] = df_limpo[col].replace({"None": "", "nan": "", "NaT": ""})
        
    return df_limpo.to_dict(orient='records')

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
        df_diverg = pd.DataFrame(diverg_res.data) if diverg_res.data else pd.DataFrame(columns=COLUNAS_DIVERG)
        df_usuarios = pd.DataFrame(usuarios_res.data) if usuarios_res.data else pd.DataFrame(columns=COLUNAS_USUARIOS)
        
        # Garante que todas as colunas padrão existam mesmo se o banco vier parcial
        for col in COLUNAS_ATIVOS:
            if col not in df_ativos.columns:
                df_ativos[col] = ""
        if not df_ativos.empty:
            df_ativos['patrimonio_placa'] = df_ativos['patrimonio_placa'].astype(str).str.strip()

        if not df_diverg.empty and 'status_resolucao' in df_diverg.columns:
            df_diverg['status_resolucao'] = df_diverg['status_resolucao'].fillna('Pendente').replace("", "Pendente")
            
        if not df_usuarios.empty and 'senha' in df_usuarios.columns:
            df_usuarios['usuario'] = df_usuarios['usuario'].astype(str).str.strip()
            df_usuarios['senha'] = df_usuarios['senha'].astype(str).str.strip()
            
        return df_ativos, df_mov, df_termos, df_diverg, df_usuarios
    except Exception as e:
        st.error(f"Erro ao carregar dados da nuvem: {e}")
        return (
            pd.DataFrame(columns=COLUNAS_ATIVOS),
            pd.DataFrame(columns=COLUNAS_MOV),
            pd.DataFrame(columns=COLUNAS_TERMOS),
            pd.DataFrame(columns=COLUNAS_DIVERG),
            pd.DataFrame(columns=COLUNAS_USUARIOS)
        )

df_ativos, df_mov, df_termos, df_diverg, df_usuarios = carregar_dados()

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
# FUNÇÃO GERADORA DE PDF
# ==========================================
def limpar_texto_pdf(texto):
    """Remove caracteres incompatíveis com a fonte padrão do FPDF (latin-1)."""
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
        st.rerun()

selecao_perfil = st.session_state.modulo_ativo

# ==========================================
# MÓDULO 1: DASHBOARD E AUDITORIA
# ==========================================
if selecao_perfil and selecao_perfil.startswith("1"):
    st.header("📊 Painel Gerencial e Conciliação")
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
                        st.success(f"Ativo '{pat_limpo}' salvo com sucesso na nuvem!")
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
        st.download_button(
            label="📥 Baixar Base / Modelo de Ativos (.xlsx)", 
            data=excel_data, 
            file_name=f"Base_Ativos_Procisa_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.divider()

        st.subheader("Carga Inicial / Atualização em Massa (Upload)")
        st.info("💡 Os cabeçalhos da planilha são limpos e traduzidos automaticamente (sem acentos e em minúsculas).")
        
        arquivo_up = st.file_uploader("Arraste o arquivo Excel (.xlsx)", type=["xlsx"])
        if arquivo_up:
            try:
                df_up = pd.read_excel(arquivo_up)
                
                # Limpeza universal de cabeçalhos (remove õ, ó, ô, ç, ã, é, í, espaços, etc.)
                df_up.columns = [normalizar_nome_coluna(c) for c in df_up.columns]
                
                # Verifica se a coluna chave 'patrimonio_placa' está presente
                if 'patrimonio_placa' not in df_up.columns:
                    st.error(f"A coluna obrigatória 'patrimonio_placa' não foi encontrada na planilha. Colunas lidas: {list(df_up.columns)}")
                else:
                    # Remove linhas onde o patrimônio esteja em branco
                    df_up = df_up.dropna(subset=['patrimonio_placa'])
                    df_up = df_up[df_up['patrimonio_placa'].astype(str).str.strip() != '']
                    
                    st.write(f"**Pré-visualização ({len(df_up)} ativos prontos para importação):**")
                    st.dataframe(df_up.head(5), use_container_width=True)
                    
                    if st.button("🚀 Confirmar e Subir para a Nuvem", type="primary"):
                        with st.spinner("A enviar dados para o Supabase..."):
                            if salvar_dados(df_a=df_up):
                                st.success(f"Carga de {len(df_up)} ativos realizada com sucesso!")
                                st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler o arquivo Excel: {e}")

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
                nova_mov = pd.DataFrame([{
                    'id_mov': id_mov, 
                    'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                    'tipo_mov': tipo_mov[:6], 
                    'patrimonio': patrimonio.strip(), 
                    'origem': origem.strip(), 
                    'destino': destino.strip(), 
                    'solicitante': solicitante.strip(), 
                    'autorizador': 'Pendente', 
                    'status_mov': 'Aguardando Conferência'
                }])
                if salvar_dados(df_m=nova_mov):
                    st.success("Solicitação registrada com sucesso! Encaminhe para conferência no Almoxarifado.")
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
                st.info(f"**Ativo Localizado:** {registro_atual.get('marca', '')} {registro_atual.get('modelo', '')} | **Status Atual:** {registro_atual.get('status_sistema', '')}")
                
                colA, colB, colC = st.columns(3)
                with colA: 
                    novo_status = st.selectbox("Novo Status:", ["Disponível", "Em uso", "Em manutenção", "Em trânsito"])
                with colB: 
                    novo_resp = st.text_input("Novo Responsável", value=str(registro_atual.get('responsavel_atual', 'Almoxarifado')))
                with colC: 
                    nova_loc = st.text_input("Nova Localização", value=str(registro_atual.get('localizacao_atual', 'Almoxarifado Central')))
                
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
                            st.success("Movimentação concluída e atualizada na nuvem!")
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
                        st.success("Termo registrado! Clique abaixo para baixar o PDF.")
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
                        st.success("Termo encerrado com sucesso!")
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
                        st.success("Divergência resolvida com sucesso!")
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
                ativo_lab['condicao_fisica'] = resultado
                if "INSERVÍVEL" in resultado or "REPROVADO" in resultado:
                    ativo_lab['status_sistema'] = 'Baixado'
                else:
                    ativo_lab['status_sistema'] = 'Disponível'
                ativo_lab['data_ultima_mov'] = datetime.now().strftime('%Y-%m-%d')
                
                if salvar_dados(df_a=pd.DataFrame([ativo_lab])):
                    st.success(f"Laudo registrado! Ativo atualizado para: {ativo_lab['status_sistema']}")
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
                            st.success(f"Usuário {novo_nome} cadastrado com sucesso!")
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
                            st.success(f"Dados de {usuario_editar} atualizados!")
                            st.rerun()
                with col_bt2:
                    if st.button("❌ Excluir Usuário", type="primary", use_container_width=True):
                        if usuario_editar != 'master':
                            supabase.table('usuarios').delete().eq('usuario', usuario_editar).execute()
                            st.cache_data.clear()
                            st.success("Usuário removido da nuvem!")
                            st.rerun()
                        else:
                            st.warning("Não é possível excluir o usuário Master principal.")
