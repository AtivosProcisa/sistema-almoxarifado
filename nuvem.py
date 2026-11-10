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

VALUES_INVALIDOS = {'', 'none', 'nan', 'null', 'nat', 'undefined', '<na>'}

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
    """Verifica se uma chave (patrimônio ou matrícula) não é nula, vazia nem 'none'/'nan'."""
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

def expurgar_linhas_nulas_nuvem():
    """Remove silenciosamente do Supabase linhas travadas com NULL ou 'None' em ativos_master e empregados."""
    # 1. Remove linhas onde a coluna está realmente NULL no PostgreSQL
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

    # 2. Remove linhas onde foi gravado texto 'None', 'nan' ou vazio
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

        # Verifica e filtra linhas "None"/NULL na tabela de empregados
        if not df_empregados.empty and 'matricula' in df_empregados.columns:
            mask_emp_invalida = ~df_empregados['matricula'].apply(matricula_valida)
            if mask_emp_invalida.any():
                precisa_expurgo = True
                df_empregados = df_empregados[~mask_emp_invalida].copy()
            df_empregados['matricula'] = df_empregados['matricula'].apply(limpar_texto_matricula)

        for col in COLUNAS_ATIVOS:
            if col not in df_ativos.columns:
                df_ativos[col] = "Disponível" if col == 'status_sistema' else ""
                
        # Verifica e filtra linhas "None"/NULL travadas na tabela de ativos_master
        if not df_ativos.empty:
            mask_ativo_invalido = ~df_ativos['patrimonio'].apply(matricula_valida)
            if mask_ativo_invalido.any():
                precisa_expurgo = True
                df_ativos = df_ativos[~mask_ativo_invalido].copy()
            df_ativos['patrimonio'] = df_ativos['patrimonio'].apply(limpar_texto_matricula)
            # Substitui qualquer None residual nas outras colunas por texto vazio para exibição limpa
            df_ativos = df_ativos.fillna("").replace({"None": "", "none": "", "nan": "", "NaN": "", "null": ""})

        if precisa_expurgo:
            expurgar_linhas_nulas_nuvem()

        # Higieniza exibição de matrículas "none" em movimentações e termos
        if not df_mov.empty and 'matricula_solicitante' in df_mov.columns:
            df_mov['matricula_solicitante'] = df_mov['matricula_solicitante'].apply(limpar_texto_matricula)
        if not df_termos.empty and 'matricula' in df_termos.columns:
            df_termos['matricula'] = df_termos['matricula'].apply(limpar_texto_matricula)

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
