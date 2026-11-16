import streamlit as st
import pandas as pd
from datetime import datetime
import unicodedata
import json

try:
    from supabase import create_client, Client
except ImportError:
    st.error("A biblioteca 'supabase' não está instalada. Verifique o arquivo requirements.txt")

# ==========================================
# CONFIGURAÇÃO DO SUPABASE (NUVEM)
# ==========================================
SUPABASE_URL = "https://qptzxnxjhpfqdkmsblct.supabase.co"
SUPABASE_KEY = "sb_publishable_y0JUFibeIhU-DBDcGFmREA_IlgsfNa0"

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

# --- COLUNAS DO CONTROLE DE FERRAMENTAS USADAS ---
COLUNAS_FERRAMENTAS = [
    'id_controle', 'codigo_d365', 'descricao_d365', 'descricao_ferramenta',
    'categoria', 'marca', 'modelo', 'numero_serie', 'patrimonio',
    'quantidade', 'unidade', 'condicao_fisica', 'status_operacional',
    'localizacao', 'responsavel_atual', 'matricula', 'projeto', 'coordenacao',
    'data_entrada', 'data_entrega', 'data_devolucao', 'ultima_movimentacao',
    'dias_sem_movimentacao', 'data_ultima_inspecao', 'proxima_inspecao',
    'valor_referencia', 'custo_acumulado_manutencao', 'quantidade_manutencoes',
    'motivo_segregacao', 'destinacao_final', 'documento_referencia', 'observacoes'
]

COLUNAS_MOV_FER = [
    'id_movimento', 'data', 'id_fer', 'codigo_d365', 'tipo_movimento',
    'localizacao_origem', 'localizacao_destino', 'responsavel_origem',
    'responsavel_destino', 'projeto', 'quantidade', 'documento',
    'usuario_registro', 'observacao'
]

COLUNAS_CAUTELA_FER = [
    'id_cautela', 'id_fer', 'codigo_d365', 'colaborador', 'matricula',
    'projeto', 'coordenacao', 'data_entrega', 'condicao_entrega',
    'data_prevista_devolucao', 'data_efetiva_devolucao', 'condicao_devolucao',
    'status', 'observacao'
]

COLUNAS_MANUT_FER = [
    'id_manut', 'id_fer', 'data_envio', 'defeito_informado',
    'fornecedor_oficina', 'numero_os', 'valor_manutencao', 'data_retorno',
    'resultado', 'condicao_apos_manutencao', 'liberado_utilizacao', 'observacoes'
]

COLUNAS_BAIXA_FER = [
    'id_baixa', 'id_fer', 'codigo_d365', 'condicao', 'motivo',
    'data_segregacao', 'laudo_tecnico', 'valor_referencia', 'custo_recuperacao',
    'viabilidade_recuperacao', 'aprovacao_baixa', 'data_baixa', 'destinacao',
    'evidencia_documento', 'observacoes'
]

COLUNAS_CONCILIACAO_D365 = [
    'codigo_d365', 'descricao_d365', 'saldo_d365', 'saldo_operacional_usados',
    'diferenca', 'motivo_diferenca', 'situacao', 'acao_necessaria', 'atualizado_em'
]

LISTA_CONDICAO_FISICA = [
    "NOVO", "USADO - BOM", "USADO - REGULAR", "EM INSPEÇÃO",
    "EM MANUTENÇÃO", "COM DEFEITO", "SEGREGADO", "OBSOLETO", "DESCARTE"
]

LISTA_STATUS_OPERACIONAL = [
    "DISPONÍVEL", "EM CAUTELA", "EM INSPEÇÃO", "EM MANUTENÇÃO",
    "BLOQUEADO", "AGUARDANDO DECISÃO", "AGUARDANDO DESCARTE", "TRANSFERIDO", "BAIXADO"
]

LISTA_LOCALIZACOES_FER = [
    "USADO-DISP", "USADO-INSPECAO", "USADO-MANUT", "USADO-DEFEITO",
    "USADO-SEGREGADO", "USADO-OBSOLETO", "USADO-DESCARTE", "CAMPO / COLABORADOR", "BAIXADO / DESCARTADO"
]

LISTA_TIPOS_MOV_FER = [
    "ENTRADA", "DEVOLUÇÃO", "ENTREGA", "CAUTELA", "TRANSFERÊNCIA",
    "ENVIO PARA MANUTENÇÃO", "RETORNO DE MANUTENÇÃO", "LIBERAÇÃO",
    "SEGREGAÇÃO", "BAIXA", "DESCARTE"
]

VALUES_INVALIDOS = {'', 'none', 'nan', 'null', 'nat', 'undefined', '<na>'}
ID_PREF_COLUNAS = "PREF-COLS-DASHBOARD"

ASSINATURA_DEV_HTML = """
<div style='text-align: center; margin-top: 20px; padding: 6px; color: #888888; font-size: 0.75rem;'>
    Desenvolvido por <strong>Marcos Paulo Da Veiga Carvalho</strong>
</div>
"""

def exibir_marca_desenvolvedor():
    st.markdown(ASSINATURA_DEV_HTML, unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Erro ao inicializar conexão com Supabase: {e}")
        return None

supabase = init_connection()

def normalizar_nome_coluna(col):
    texto = str(col).strip().lower()
    texto = texto.replace('nº', 'numero').replace('º', '').replace('ª', '')
    texto_sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    return texto_sem_acento.replace(' ', '_').replace('-', '_')

def matricula_valida(val):
    if val is None or pd.isna(val):
        return False
    texto = str(val).strip()
    if texto.endswith('.0'):
        texto = texto[:-2]
    return texto.lower() not in VALUES_INVALIDOS

def limpar_texto_matricula(val):
    if val is None or pd.isna(val):
        return ""
    texto = str(val).strip()
    if texto.endswith('.0'):
        texto = texto[:-2]
    return "" if texto.lower() in VALUES_INVALIDOS else texto

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
        df_limpo[col] = df_limpo[col].replace({"None": "", "none": "", "nan": "", "NaN": "", "NaT": "", "null": ""})
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

# ==========================================
# PERSISTÊNCIA DE COLUNAS NA NUVEM (SUPABASE)
# ==========================================
def carregar_preferencias_colunas():
    padrao = {
        'inv': list(COLUNAS_ATIVOS),
        'mov': list(COLUNAS_MOV),
        'trm': list(COLUNAS_TERMOS),
        'fer': list(COLUNAS_FERRAMENTAS)
    }
    try:
        res = supabase.table('divergencias').select("observacoes").eq('id_divergencia', ID_PREF_COLUNAS).execute()
        if res.data and res.data[0].get('observacoes'):
            dados = json.loads(res.data[0]['observacoes'])
            inv = [c for c in dados.get('inv', COLUNAS_ATIVOS) if c in COLUNAS_ATIVOS]
            mov = [c for c in dados.get('mov', COLUNAS_MOV) if c in COLUNAS_MOV]
            trm = [c for c in dados.get('trm', COLUNAS_TERMOS) if c in COLUNAS_TERMOS]
            fer = [c for c in dados.get('fer', COLUNAS_FERRAMENTAS) if c in COLUNAS_FERRAMENTAS]
            return {
                'inv': inv if inv else list(COLUNAS_ATIVOS),
                'mov': mov if mov else list(COLUNAS_MOV),
                'trm': trm if trm else list(COLUNAS_TERMOS),
                'fer': fer if fer else list(COLUNAS_FERRAMENTAS)
            }
    except Exception:
        pass
    return padrao

def salvar_preferencias_colunas(cols_inv, cols_mov, cols_trm, cols_fer=None):
    try:
        if cols_fer is None:
            cols_fer = st.session_state.get('saved_cols_fer', COLUNAS_FERRAMENTAS)
        payload = json.dumps({
            'inv': list(cols_inv) if cols_inv else list(COLUNAS_ATIVOS),
            'mov': list(cols_mov) if cols_mov else list(COLUNAS_MOV),
            'trm': list(cols_trm) if cols_trm else list(COLUNAS_TERMOS),
            'fer': list(cols_fer) if cols_fer else list(COLUNAS_FERRAMENTAS)
        }, ensure_ascii=False)
        registro = {
            'id_divergencia': ID_PREF_COLUNAS,
            'data_registro': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'patrimonio': 'CONFIG',
            'tipo_divergencia': '[CONFIG-SISTEMA] COLUNAS_DASHBOARD',
            'status_resolucao': 'Resolvido',
            'analista_responsavel': st.session_state.get('usuario', 'master'),
            'observacoes': payload
        }
        supabase.table('divergencias').upsert([registro]).execute()
    except Exception:
        pass

def expurgar_linhas_nulas_nuvem():
    try:
        supabase.table('ativos_master').delete().is_('patrimonio', 'null').execute()
    except Exception:
        pass
    try:
        supabase.table('empregados').delete().is_('matricula', 'null').execute()
    except Exception:
        pass
    try:
        supabase.table('ativos_master').delete().is_('equipamento', 'null').is_('marca', 'null').execute()
    except Exception:
        pass

    for val_lixo in ["None", "none", "NONE", "nan", "NaN", "null", "NULL", ""]:
        try:
            supabase.table('ativos_master').delete().eq('patrimonio', val_lixo).execute()
        except Exception:
            pass
        try:
            supabase.table('empregados').delete().eq('matricula', val_lixo).execute()
        except Exception:
            pass

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
        
        precisa_expurgo = False

        if not df_empregados.empty and 'matricula' in df_empregados.columns:
            mask_emp_invalida = ~df_empregados['matricula'].apply(matricula_valida)
            if mask_emp_invalida.any():
                precisa_expurgo = True
                df_empregados = df_empregados[~mask_emp_invalida].copy()
            df_empregados['matricula'] = df_empregados['matricula'].apply(limpar_texto_matricula)

        for col in COLUNAS_ATIVOS:
            if col not in df_ativos.columns:
                df_ativos[col] = "Disponível" if col == 'status_sistema' else ""
                
        if not df_ativos.empty:
            mask_ativo_invalido = ~df_ativos['patrimonio'].apply(matricula_valida)
            if mask_ativo_invalido.any():
                precisa_expurgo = True
                df_ativos = df_ativos[~mask_ativo_invalido].copy()
            df_ativos['patrimonio'] = df_ativos['patrimonio'].apply(limpar_texto_matricula)
            df_ativos = df_ativos.fillna("").replace({"None": "", "none": "", "nan": "", "NaN": "", "null": ""})

        if precisa_expurgo:
            expurgar_linhas_nulas_nuvem()

        if not df_mov.empty and 'matricula_solicitante' in df_mov.columns:
            df_mov['matricula_solicitante'] = df_mov['matricula_solicitante'].apply(limpar_texto_matricula)
        if not df_termos.empty and 'matricula' in df_termos.columns:
            df_termos['matricula'] = df_termos['matricula'].apply(limpar_texto_matricula)

        if not df_diverg_bruto.empty and 'tipo_divergencia' in df_diverg_bruto.columns:
            df_diverg_bruto['status_resolucao'] = df_diverg_bruto['status_resolucao'].fillna('Pendente').replace("", "Pendente")
            tipo_str = df_diverg_bruto['tipo_divergencia'].astype(str)
            mask_log = tipo_str.str.startswith('[LOG-SISTEMA]')
            mask_cfg = tipo_str.str.startswith('[CONFIG-SISTEMA]') | (df_diverg_bruto['id_divergencia'].astype(str) == ID_PREF_COLUNAS)
            
            df_logs = df_diverg_bruto[mask_log].copy()
            df_diverg = df_diverg_bruto[~mask_log & ~mask_cfg].copy()
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

def _ler_tabela_segura(nome_tabela, colunas_padrao):
    try:
        res = supabase.table(nome_tabela).select("*").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=colunas_padrao)
    except Exception:
        df = pd.DataFrame(columns=colunas_padrao)
    for c in colunas_padrao:
        if c not in df.columns:
            df[c] = ""
    if not df.empty:
        df = df.fillna("").replace({"None": "", "none": "", "nan": "", "NaN": "", "null": ""})
    return df[colunas_padrao] if not df.empty else pd.DataFrame(columns=colunas_padrao)

def calcular_dias_sem_mov(data_str):
    if not data_str or str(data_str).strip() == "":
        return "0"
    try:
        dt = datetime.strptime(str(data_str).strip()[:10], "%Y-%m-%d")
        dias = max(0, (datetime.now() - dt).days)
        return str(dias)
    except Exception:
        return "0"

@st.cache_data(ttl=5)
def carregar_dados_ferramental():
    df_fer = _ler_tabela_segura('ferramentas_usadas', COLUNAS_FERRAMENTAS)
    df_mov_fer = _ler_tabela_segura('mov_ferramentas', COLUNAS_MOV_FER)
    df_caut_fer = _ler_tabela_segura('cautelas_ferramentas', COLUNAS_CAUTELA_FER)
    df_manut_fer = _ler_tabela_segura('manutencao_ferramentas', COLUNAS_MANUT_FER)
    df_baixa_fer = _ler_tabela_segura('baixa_ferramentas', COLUNAS_BAIXA_FER)
    df_conc_d365 = _ler_tabela_segura('conciliacao_d365_fer', COLUNAS_CONCILIACAO_D365)

    if not df_fer.empty:
        df_fer['id_controle'] = df_fer['id_controle'].astype(str).str.strip()
        df_fer = df_fer[df_fer['id_controle'].apply(matricula_valida)].copy()
        df_fer['dias_sem_movimentacao'] = df_fer['ultima_movimentacao'].apply(calcular_dias_sem_mov)

    return df_fer, df_mov_fer, df_caut_fer, df_manut_fer, df_baixa_fer, df_conc_d365

def gerar_proximo_id_fer(df_fer):
    """Gera automaticamente o identificador sequencial FER-000001, FER-000002..."""
    if df_fer.empty or 'id_controle' not in df_fer.columns:
        return "FER-000001"
    maior = 0
    for val in df_fer['id_controle'].astype(str):
        val_limpo = val.strip().upper()
        if val_limpo.startswith("FER-"):
            num_str = val_limpo.replace("FER-", "").strip()
            if num_str.isdigit():
                maior = max(maior, int(num_str))
    return f"FER-{maior + 1:06d}"

def buscar_ferramenta(termo_busca, df_fer):
    """Busca universal de ferramenta por ID FER, Código D365, Patrimônio ou Nº de Série."""
    if df_fer.empty or not termo_busca:
        return pd.DataFrame()
    t = str(termo_busca).strip().upper()
    id_c = df_fer['id_controle'].fillna("").astype(str).str.strip().str.upper()
    c_d365 = df_fer['codigo_d365'].fillna("").astype(str).str.strip().str.upper()
    pat = df_fer['patrimonio'].fillna("").astype(str).str.strip().str.upper()
    ser = df_fer['numero_serie'].fillna("").astype(str).str.strip().str.upper()
    return df_fer[(id_c == t) | (c_d365 == t) | (pat == t) | (ser == t)]

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

def buscar_ativo(termo_busca, df):
    if df.empty or not termo_busca:
        return pd.DataFrame()
    termo = str(termo_busca).strip().upper()
    patrimonios = df['patrimonio'].fillna("").astype(str).str.strip().str.upper()
    series = df['numero_serie'].fillna("").astype(str).str.strip().str.upper()
    return df[(patrimonios == termo) | (series == termo)]

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
