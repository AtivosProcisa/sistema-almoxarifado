import streamlit as st
import pandas as pd
from datetime import datetime
import os
import tempfile
import io

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
# GESTÃO DE DADOS (SUPABASE)
# ==========================================
@st.cache_data(ttl=5)
def carregar_dados():
    colunas_ativos = ['codigo_d365', 'patrimonio_placa', 'numero_serie', 'marca', 'modelo', 'categoria', 'status_sistema', 'condicao_fisica', 'localizacao_atual', 'responsavel_atual', 'data_ultima_mov', 'observacoes']
    colunas_mov = ['id_mov', 'data_hora', 'tipo_mov', 'patrimonio', 'origem', 'destino', 'solicitante', 'autorizador', 'status_mov']
    colunas_termos = ['id_termo', 'patrimonio', 'responsavel', 'matricula', 'unidade', 'data_emissao', 'data_baixa', 'status_termo']
    colunas_diverg = ['id_divergencia', 'data_registro', 'patrimonio', 'tipo_divergencia', 'status_resolucao', 'analista_responsavel', 'observacoes']
    colunas_usuarios = ['usuario', 'senha', 'perfil', 'nome']

    try:
        ativos_res = supabase.table('ativos_master').select("*").execute()
        mov_res = supabase.table('movimentacoes').select("*").execute()
        termos_res = supabase.table('termos').select("*").execute()
        diverg_res = supabase.table('divergencias').select("*").execute()
        usuarios_res = supabase.table('usuarios').select("*").execute()

        df_ativos = pd.DataFrame(ativos_res.data) if ativos_res.data else pd.DataFrame(columns=colunas_ativos)
        df_mov = pd.DataFrame(mov_res.data) if mov_res.data else pd.DataFrame(columns=colunas_mov)
        df_termos = pd.DataFrame(termos_res.data) if termos_res.data else pd.DataFrame(columns=colunas_termos)
        df_diverg = pd.DataFrame(diverg_res.data) if diverg_res.data else pd.DataFrame(columns=colunas_diverg)
        df_usuarios = pd.DataFrame(usuarios_res.data) if usuarios_res.data else pd.DataFrame(columns=colunas_usuarios)
        
        if not df_diverg.empty and 'status_resolucao' in df_diverg.columns:
            df_diverg['status_resolucao'] = df_diverg['status_resolucao'].fillna('Pendente')
            
        if not df_usuarios.empty and 'senha' in df_usuarios.columns:
            df_usuarios['senha'] = df_usuarios['senha'].astype(str)
            
        return df_ativos, df_mov, df_termos, df_diverg, df_usuarios
    except Exception as e:
        st.error(f"Erro ao carregar dados da nuvem: {e}")
        return (
            pd.DataFrame(columns=colunas_ativos),
            pd.DataFrame(columns=colunas_mov),
            pd.DataFrame(columns=colunas_termos),
            pd.DataFrame(columns=colunas_diverg),
            pd.DataFrame(columns=colunas_usuarios)
        )

df_ativos, df_mov, df_termos, df_diverg, df_usuarios = carregar_dados()

def salvar_dados(df_a, df_m, df_t, df_d, df_u):
    try:
        if not df_a.empty:
            supabase.table('ativos_master').upsert(df_a.fillna("").to_dict(orient='records')).execute()
        if not df_m.empty:
            supabase.table('movimentacoes').upsert(df_m.fillna("").to_dict(orient='records')).execute()
        if not df_t.empty:
            supabase.table('termos').upsert(df_t.fillna("").to_dict(orient='records')).execute()
        if not df_d.empty:
            supabase.table('divergencias').upsert(df_d.fillna("").to_dict(orient='records')).execute()
        if not df_u.empty:
            supabase.table('usuarios').upsert(df_u.fillna("").to_dict(orient='records')).execute()
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
    match = df_usuarios[(df_usuarios['usuario'] == usuario.strip()) & (df_usuarios['senha'] == str(senha).strip())]
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

    aba_inv, aba_hist_mov, aba_hist_termos, aba_io = st.tabs(["Inventário Geral", "Histórico de Movimentações", "Termos Emitidos", "🔄 Importar / Exportar"])
    
    with aba_inv:
        st.dataframe(df_ativos, use_container_width=True)
    with aba_hist_mov:
        st.dataframe(df_mov, use_container_width=True)
    with aba_hist_termos:
        st.dataframe(df_termos, use_container_width=True)
        
    with aba_io:
        st.subheader("Exportar Relatórios (Download)")
        st.write("Baixe a base de ativos atualizada diretamente da nuvem para o seu computador.")
        
        # Função para converter DataFrame em Excel em memória
        def converter_df_excel(df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Base_Ativos')
            return output.getvalue()

        if not df_ativos.empty:
            excel_data = converter_df_excel(df_ativos)
            st.download_button(
                label="📥 Baixar Base de Ativos (.xlsx)", 
                data=excel_data, 
                file_name=f"Base_Ativos_Procisa_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("A base de ativos está vazia.")

        st.divider()

        st.subheader("Carga Inicial / Atualização em Massa (Upload)")
        st.warning("⚠️ O arquivo Excel deve conter exatamente as mesmas colunas da base de dados. Registros com o mesmo 'patrimonio_placa' serão substituídos.")
        
        arquivo_up = st.file_uploader("Arraste o arquivo Excel (.xlsx)", type=["xlsx"])
        if arquivo_up:
            try:
                df_up = pd.read_excel(arquivo_up)
                st.write("Pré-visualização dos dados a serem importados:")
                st.dataframe(df_up.head(3), use_container_width=True)
                
                if st.button("🚀 Confirmar e Subir para a Nuvem", type="primary"):
                    with st.spinner("A enviar dados para o Supabase..."):
                        if salvar_dados(df_up, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()):
                            st.success("Carga realizada com sucesso! A base de dados foi atualizada.")
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
            solicitante = st.text_input("Nome do Solicitante (Matrícula)")
        with col2:
            origem = st.text_input("Unidade/Equipe de Origem")
            destino = st.text_input("Unidade/Equipe de Destino")
            motivo = st.text_area("Motivo da Movimentação")
        
        if st.form_submit_button("Registrar Solicitação"):
            if patrimonio and solicitante:
                id_mov = f"MOV-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                nova_mov = pd.DataFrame([{
                    'id_mov': id_mov, 
                    'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                    'tipo_mov': tipo_mov[:6], 
                    'patrimonio': patrimonio.strip(), 
                    'origem': origem, 
                    'destino': destino, 
                    'solicitante': solicitante, 
                    'autorizador': 'Pendente', 
                    'status_mov': 'Aguardando Conferência'
                }])
                df_mov = pd.concat([df_mov, nova_mov], ignore_index=True)
                if salvar_dados(pd.DataFrame(), df_mov, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()):
                    st.success("Solicitação registrada com sucesso! Encaminhe para conferência.")
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
            patrimonio_busca = patrimonio_busca.strip()
            ativo_info = df_ativos[df_ativos['patrimonio_placa'] == patrimonio_busca] if not df_ativos.empty else pd.DataFrame()
            if not ativo_info.empty:
                st.info(f"**Ativo Localizado:** {ativo_info.iloc[0]['marca']} {ativo_info.iloc[0]['modelo']} | **Status Atual:** {ativo_info.iloc[0]['status_sistema']}")
                colA, colB, colC = st.columns(3)
                with colA: 
                    novo_status = st.selectbox("Novo Status:", ["Disponível", "Em uso", "Em manutenção", "Em trânsito"])
                with colB: 
                    novo_resp = st.text_input("Novo Responsável", value="Almoxarifado")
                with colC: 
                    nova_loc = st.text_input("Nova Localização", value="Almoxarifado Central")
                
                d365_ok = st.checkbox("Status e Localização conferem no D365?")
                eponto_ok = st.checkbox("Movimentação validada no e-Ponto?")
                fisico_ok = st.checkbox("Estado físico, Série e Acessórios conferem?")
                
                if st.button("Validar e Concluir Movimentação"):
                    if d365_ok and eponto_ok and fisico_ok:
                        idx = df_ativos.index[df_ativos['patrimonio_placa'] == patrimonio_busca].tolist()[0]
                        df_ativos.at[idx, 'status_sistema'] = novo_status
                        df_ativos.at[idx, 'responsavel_atual'] = novo_resp
                        df_ativos.at[idx, 'localizacao_atual'] = nova_loc
                        df_ativos.at[idx, 'data_ultima_mov'] = datetime.now().strftime('%Y-%m-%d')
                        if salvar_dados(df_ativos, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()):
                            st.success("Movimentação concluída na nuvem!")
                    else:
                        id_div = f"DIV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        nova_div = pd.DataFrame([{
                            'id_divergencia': id_div, 
                            'data_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                            'patrimonio': patrimonio_busca, 
                            'tipo_divergencia': 'Inconsistência de Cadastro/Físico', 
                            'status_resolucao': 'Pendente', 
                            'analista_responsavel': st.session_state.nome_real, 
                            'observacoes': 'Bloqueado na conferência física tripla.'
                        }])
                        df_diverg = pd.concat([df_diverg, nova_div], ignore_index=True)
                        salvar_dados(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), df_diverg, pd.DataFrame())
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
                submit_termo = st.form_submit_button("Criar Documento")
                
            if submit_termo and patrimonio_termo:
                patrimonio_termo = patrimonio_termo.strip()
                ativo_info_termo = df_ativos[df_ativos['patrimonio_placa'] == patrimonio_termo] if not df_ativos.empty else pd.DataFrame()
                if not ativo_info_termo.empty:
                    caminho_pdf = gerar_termo_pdf(
                        patrimonio_termo, responsavel_termo, matricula_termo, unidade_termo, ativo_info_termo
                    )
                    with open(caminho_pdf, "rb") as pdf_file: 
                        PDFbyte = pdf_file.read()
                    
                    id_termo = f"TRM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    novo_termo = pd.DataFrame([{
                        'id_termo': id_termo, 
                        'patrimonio': patrimonio_termo, 
                        'responsavel': responsavel_termo, 
                        'matricula': matricula_termo, 
                        'unidade': unidade_termo, 
                        'data_emissao': datetime.now().strftime('%Y-%m-%d'), 
                        'data_baixa': '', 
                        'status_termo': 'Ativo'
                    }])
                    df_termos = pd.concat([df_termos, novo_termo], ignore_index=True)
                    salvar_dados(pd.DataFrame(), pd.DataFrame(), df_termos, pd.DataFrame(), pd.DataFrame())
                    st.success("Termo registrado! Clique abaixo para baixar o PDF.")
                    st.download_button(
                        label="📥 Baixar Termo PDF", 
                        data=PDFbyte, 
                        file_name=f"Termo_{patrimonio_termo}.pdf", 
                        mime='application/pdf'
                    )
                else:
                    st.error("Patrimônio não localizado na base mestra.")
        else:
            pat_baixa = st.text_input("Patrimônio devolvido:")
            if st.button("Baixar Termo Ativo"):
                pat_baixa = pat_baixa.strip()
                termos_ativos = df_termos[(df_termos['patrimonio'] == pat_baixa) & (df_termos['status_termo'] == 'Ativo')] if not df_termos.empty else pd.DataFrame()
                if not termos_ativos.empty:
                    idx = termos_ativos.index[0]
                    df_termos.at[idx, 'data_baixa'] = datetime.now().strftime('%Y-%m-%d')
                    df_termos.at[idx, 'status_termo'] = 'Encerrado'
                    if salvar_dados(pd.DataFrame(), pd.DataFrame(), df_termos, pd.DataFrame(), pd.DataFrame()):
                        st.success("Termo encerrado com sucesso!")
                else:
                    st.warning("Nenhum termo ativo encontrado para este patrimônio.")

    with aba3:
        pendentes = df_diverg[df_diverg['status_resolucao'] != 'Resolvido'] if not df_diverg.empty else pd.DataFrame()
        if not pendentes.empty:
            st.dataframe(pendentes, use_container_width=True)
            id_div_selecionada = st.selectbox("Resolver Divergência:", pendentes['id_divergencia'].tolist())
            obs = st.text_area("Justificativa / Ação Tomada:")
            analista = st.text_input("Analista Responsável:", value=st.session_state.nome_real)
            if st.button("Aplicar Resolução"):
                if obs and analista:
                    idx = df_diverg.index[df_diverg['id_divergencia'] == id_div_selecionada].tolist()[0]
                    df_diverg.at[idx, 'status_resolucao'] = 'Resolvido'
                    df_diverg.at[idx, 'observacoes'] = obs
                    df_diverg.at[idx, 'analista_responsavel'] = analista
                    if salvar_dados(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), df_diverg, pd.DataFrame()):
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
    if st.button("Atualizar Base"):
        if patrimonio_lab:
            patrimonio_lab = patrimonio_lab.strip()
            ativo_idx = df_ativos.index[df_ativos['patrimonio_placa'] == patrimonio_lab].tolist() if not df_ativos.empty else []
            if ativo_idx:
                idx = ativo_idx[0]
                df_ativos.at[idx, 'condicao_fisica'] = resultado
                if "INSERVÍVEL" in resultado or "REPROVADO" in resultado:
                    df_ativos.at[idx, 'status_sistema'] = 'Baixado'
                else:
                    df_ativos.at[idx, 'status_sistema'] = 'Disponível'
                df_ativos.at[idx, 'data_ultima_mov'] = datetime.now().strftime('%Y-%m-%d')
                if salvar_dados(df_ativos, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()):
                    st.success(f"Laudo registrado! Ativo atualizado para: {df_ativos.at[idx, 'status_sistema']}")
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
            
            if st.form_submit_button("Cadastrar Usuário"):
                if novo_login and nova_senha and novo_nome:
                    novo_login = novo_login.strip()
                    if not df_usuarios.empty and novo_login in df_usuarios['usuario'].values:
                        st.error("Este login já existe! Escolha outro.")
                    else:
                        novo_registo = pd.DataFrame([{
                            'usuario': novo_login, 
                            'senha': str(nova_senha).strip(), 
                            'perfil': novo_perfil, 
                            'nome': novo_nome.strip()
                        }])
                        df_usuarios = pd.concat([df_usuarios, novo_registo], ignore_index=True)
                        if salvar_dados(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), df_usuarios):
                            st.success(f"Usuário {novo_nome} cadastrado com sucesso!")
                            st.rerun()
                else:
                    st.error("Preencha todos os campos obrigatórios.")
                    
    with aba_editar:
        if not df_usuarios.empty:
            usuario_editar = st.selectbox("Selecione o Usuário para alterar:", df_usuarios['usuario'].tolist())
            if usuario_editar:
                idx_user = df_usuarios.index[df_usuarios['usuario'] == usuario_editar].tolist()[0]
                
                col_a, col_b = st.columns(2)
                with col_a:
                    senha_reset = st.text_input("Nova Senha", value=str(df_usuarios.at[idx_user, 'senha']))
                with col_b:
                    lista_perfis = ["Operador Campo", "Almoxarifado", "Laboratório", "Master"]
                    perfil_atual = df_usuarios.at[idx_user, 'perfil']
                    idx_p = lista_perfis.index(perfil_atual) if perfil_atual in lista_perfis else 0
                    perfil_edit = st.selectbox("Mudar Perfil", lista_perfis, index=idx_p)
                    
                col_bt1, col_bt2 = st.columns(2)
                with col_bt1:
                    if st.button("💾 Salvar Alterações", use_container_width=True):
                        df_usuarios.at[idx_user, 'senha'] = str(senha_reset).strip()
                        df_usuarios.at[idx_user, 'perfil'] = perfil_edit
                        if salvar_dados(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), df_usuarios):
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
