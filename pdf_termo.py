import io
import tempfile
from datetime import datetime
import pandas as pd

try:
    from fpdf import FPDF
except ImportError:
    pass

def limpar_texto_pdf(texto):
    val = str(texto).strip()
    if val.lower() in {'none', 'nan', 'null', 'nat'}:
        val = ""
    return val.encode('latin-1', 'replace').decode('latin-1')

def converter_df_excel_simples(df, nome_aba="Relatorio"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=nome_aba[:31])
    return output.getvalue()

def gerar_backup_completo_excel(dict_dfs):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for nome_aba, df_item in dict_dfs.items():
            df_item.to_excel(writer, index=False, sheet_name=nome_aba[:31])
    return output.getvalue()

def gerar_termo_pdf(patrimonio, responsavel, matricula, cpf, rg, projeto, unidade, info_ativo):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    # Cabeçalho Página 1
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
    
    reg_ativo = info_ativo.iloc[0]
    eqp_nome = str(reg_ativo.get('equipamento', '')).strip()
    marca = str(reg_ativo.get('marca', '')).strip()
    modelo = str(reg_ativo.get('modelo', '')).strip()
    serie = str(reg_ativo.get('numero_serie', '')).strip()
    condicao = str(reg_ativo.get('condicoes_para_uso', '')).strip()
    acessorios = str(reg_ativo.get('acessorios', '')).strip()
    coordenador = str(reg_ativo.get('coordenacao', unidade)).strip()
    nf_procisa = str(reg_ativo.get('nf_procisa', '')).strip()
    
    situacao_completa = f"{condicao} - {acessorios}".strip(" -") if acessorios else condicao
    
    pdf.ln(4)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"1. MARCA/MODELO: {eqp_nome} {marca} {modelo}".strip()), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"   NÚMERO DE SÉRIE: {serie}      NÚMERO DE ATIVO: {patrimonio}"), ln=True)
    pdf.multi_cell(0, 6, txt=limpar_texto_pdf(f"   SITUAÇÃO / ACESSÓRIOS: {situacao_completa}"))
    pdf.ln(3)
    
    for i in range(2, 6):
        pdf.cell(0, 5, txt=limpar_texto_pdf(f"{i}. MARCA/MODELO: _________________________________________"), ln=True)
        pdf.cell(0, 5, txt=limpar_texto_pdf("   NÚMERO DE SÉRIE: ___________________  NÚMERO DE ATIVO: ___________________"), ln=True)
        pdf.cell(0, 5, txt=limpar_texto_pdf("   SITUAÇÃO: ______________________________________________"), ln=True)
        pdf.ln(2)
        
    pdf.ln(3)
    pdf.cell(0, 6, txt=limpar_texto_pdf("MOTIVO DA DEVOLUÇÃO:"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf("[  ] MANUTENÇÃO   [  ] DESLIGAMENTO   [  ] CALIBRAÇÃO"), ln=True)
    
    pdf.ln(3)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"OBSERVAÇÕES: {acessorios if acessorios else '________________________________________________________________'}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"COORD. RESPONSÁVEL: {coordenador if coordenador else '______________________'}      NÚMERO DA NF: {nf_procisa if nf_procisa else '______________________'}"), ln=True)
    
    pdf.ln(12)
    pdf.cell(90, 10, txt="___________________________________", align='C')
    pdf.cell(90, 10, txt="___________________________________", ln=True, align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("USUÁRIO"), align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("ALMOXARIFADO"), ln=True, align='C')

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        return tmp.name
