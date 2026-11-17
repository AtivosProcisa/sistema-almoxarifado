import io
import os
import tempfile
import urllib.request
import urllib.parse
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

def _desenhar_cabecalho_procisa(pdf, data_atual, num_pag):
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 5, txt=limpar_texto_pdf("PROCISA"), border='LTR', align='C')
    pdf.cell(100, 5, txt=limpar_texto_pdf("TERMO DE RESPONSABILIDADE DE EQUIPAMENTOS"), border='LTR', align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf("DATA"), border=1, align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf("PÁG."), border=1, ln=True, align='C')
    
    pdf.cell(40, 5, txt=limpar_texto_pdf("FR-RH-P-026 Rev 07 / Jul 13"), border='LBR', align='C')
    pdf.cell(100, 5, txt=limpar_texto_pdf("REF."), border='LBR', align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf(data_atual), border=1, align='C')
    pdf.cell(25, 5, txt=limpar_texto_pdf(f"- {num_pag} -"), border=1, ln=True, align='C')
    pdf.ln(4)

def gerar_termo_pdf(patrimonio, responsavel, matricula, cpf, rg, projeto, unidade, info_ativo):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    # --- PÁGINA 1: CLÁUSULAS CONTRATUAIS ---
    _desenhar_cabecalho_procisa(pdf, data_atual, 1)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, txt=limpar_texto_pdf("TERMO DE RESPONSABILIDADE DE EQUIPAMENTOS"), ln=True, align='C')
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"Usuário: {responsavel}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"RG: {rg}      CPF/MF: {cpf}      Matrícula: {matricula}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"Área: {unidade}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"Projeto: {projeto}"), ln=True)
    pdf.ln(4)
    
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
        
    pdf.ln(8)
    pdf.cell(90, 10, txt="___________________________________", align='C')
    pdf.cell(90, 10, txt="___________________________________", ln=True, align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("USUÁRIO"), align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("COORDENADOR/RESPONSÁVEL"), ln=True, align='C')
    
    # --- PÁGINA 2 (E SEGUINTES, SE HOUVER MUITAS FERRAMENTAS) ---
    num_pagina_atual = 2
    pdf.add_page()
    _desenhar_cabecalho_procisa(pdf, data_atual, num_pagina_atual)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(95, 8, txt=limpar_texto_pdf(f"ENTREGA: {data_atual}"), border=1)
    pdf.cell(95, 8, txt=limpar_texto_pdf("DEVOLUÇÃO: ___/___/___"), border=1, ln=True)
    pdf.ln(4)
    
    coordenador = unidade
    nf_procisa = ""
    total_itens = len(info_ativo)
    
    for idx, reg_ativo in info_ativo.reset_index(drop=True).iterrows():
        if pdf.get_y() > 225:
            num_pagina_atual += 1
            pdf.add_page()
            _desenhar_cabecalho_procisa(pdf, data_atual, num_pagina_atual)
            pdf.set_font("Arial", 'B', 10)
            
        marca = str(reg_ativo.get('marca', '')).strip()
        modelo = str(reg_ativo.get('modelo', '')).strip()
        serie = str(reg_ativo.get('numero_serie', '')).strip()
        if marca.lower() in {'none', 'nan'}: marca = ""
        if modelo.lower() in {'none', 'nan'}: modelo = ""
        if serie.lower() in {'none', 'nan'}: serie = ""
        
        marca_modelo_texto = f"{marca} {modelo}".strip()
        pat_id = str(reg_ativo.get('patrimonio', patrimonio)).strip()
        
        condicao = str(reg_ativo.get('condicoes_para_uso', 'USADO - BOM')).strip() or "USADO - BOM"
        acessorios = str(reg_ativo.get('acessorios', '')).strip()
        situacao_completa = f"{condicao} - {acessorios}".strip(" -") if acessorios else condicao
        
        cod_d365 = str(reg_ativo.get('codigo_d365', '')).strip()
        desc_d365 = str(reg_ativo.get('descricao_d365', '')).strip()
        
        coordenador = str(reg_ativo.get('coordenacao', unidade)).strip() or unidade
        nf_procisa = str(reg_ativo.get('nf_procisa', '')).strip()

        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 6, txt=limpar_texto_pdf(f"{idx+1}. MARCA/MODELO: {marca_modelo_texto}"), ln=True)
        pdf.cell(0, 6, txt=limpar_texto_pdf(f"   NÚMERO DE SÉRIE: {serie}      NÚMERO DE ATIVO: {pat_id}"), ln=True)
        pdf.multi_cell(0, 6, txt=limpar_texto_pdf(f"   SITUAÇÃO / ACESSÓRIOS: {situacao_completa}"))
        if cod_d365:
            pdf.cell(0, 6, txt=limpar_texto_pdf(f"   CÓD D365: {cod_d365} - {desc_d365}"), ln=True)
        pdf.ln(2)

    if total_itens < 5:
        for i in range(total_itens + 1, 6):
            if pdf.get_y() > 235:
                break
            pdf.cell(0, 5, txt=limpar_texto_pdf(f"{i}. MARCA/MODELO: _________________________________________"), ln=True)
            pdf.cell(0, 5, txt=limpar_texto_pdf("   NÚMERO DE SÉRIE: ___________________  NÚMERO DE ATIVO: ___________________"), ln=True)
            pdf.cell(0, 5, txt=limpar_texto_pdf("   SITUAÇÃO: ______________________________________________"), ln=True)
            pdf.ln(2)

    if pdf.get_y() > 230:
        num_pagina_atual += 1
        pdf.add_page()
        _desenhar_cabecalho_procisa(pdf, data_atual, num_pagina_atual)

    pdf.ln(2)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, txt=limpar_texto_pdf("MOTIVO DA DEVOLUÇÃO:"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf("[  ] MANUTENÇÃO   [  ] DESLIGAMENTO   [  ] CALIBRAÇÃO"), ln=True)
    
    pdf.ln(2)
    pdf.cell(0, 6, txt=limpar_texto_pdf("OBSERVAÇÕES: ____________________________________________________________________"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"COORD. RESPONSÁVEL: {coordenador if coordenador else '______________________'}      NÚMERO DA NF: {nf_procisa if nf_procisa else '______________________'}"), ln=True)
    
    pdf.ln(10)
    pdf.cell(90, 10, txt="___________________________________", align='C')
    pdf.cell(90, 10, txt="___________________________________", ln=True, align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("USUÁRIO"), align='C')
    pdf.cell(90, 5, txt=limpar_texto_pdf("ALMOXARIFADO"), ln=True, align='C')

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        return tmp.name

# ==========================================
# GERADOR DE FOLHA DE ETIQUETAS QR CODE EM LOTE (A4 - 21 POR PÁGINA)
# ==========================================
def gerar_etiquetas_qrcode_pdf(lista_etiquetas):
    """
    Recebe uma lista de dicionários:
    [{'codigo': 'US-AC1N1P9', 'tipo': 'ENDEREÇO 01', 'subtitulo': 'Prateleira Almox.'}, ...]
    Gera um arquivo PDF A4 em grade (3 colunas x 7 linhas = 21 etiquetas por folha).
    """
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=False)

    cols = 3
    rows = 7
    por_pagina = cols * rows
    margin_x = 10.0
    margin_y = 12.0
    box_w = 61.0
    box_h = 38.0
    gap_x = 3.5
    gap_y = 1.5

    arquivos_temp = []

    for idx, item in enumerate(lista_etiquetas):
        if idx % por_pagina == 0:
            pdf.add_page()
            pdf.set_font("Arial", 'B', 8)
            pdf.set_xy(10, 5)
            pdf.cell(190, 4, txt=limpar_texto_pdf(f"PROCISA - FOLHA DE ETIQUETAS QR CODE (ALMOXARIFADO) - Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"), align='C')

        pos_pag = idx % por_pagina
        c_idx = pos_pag % cols
        r_idx = pos_pag // cols

        x = margin_x + c_idx * (box_w + gap_x)
        y = margin_y + r_idx * (box_h + gap_y)

        codigo_qr = str(item.get('codigo', '')).strip().upper()
        tipo_lbl = str(item.get('tipo', 'ENDEREÇO')).strip().upper()
        sub_lbl = str(item.get('subtitulo', '')).strip()

        # Moldura da etiqueta
        pdf.set_draw_color(160, 160, 160)
        pdf.rect(x, y, box_w, box_h)

        # Faixa superior de identificação
        pdf.set_fill_color(240, 240, 240)
        pdf.rect(x + 0.5, y + 0.5, box_w - 1.0, 5.5, 'F')
        pdf.set_xy(x + 1, y + 1)
        pdf.set_font("Arial", 'B', 7)
        pdf.cell(box_w - 2, 4.5, txt=limpar_texto_pdf(f"PROCISA | {tipo_lbl}"[:34]), align='C')

        # Baixa e insere a imagem do QR Code ao lado esquerdo da etiqueta
        try:
            url_qr = f"https://api.qrserver.com/v1/create-qr-code/?size=160x160&margin=1&data={urllib.parse.quote(codigo_qr)}"
            req = urllib.request.Request(url_qr, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                img_bytes = resp.read()
            tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp_img.write(img_bytes)
            tmp_img.close()
            arquivos_temp.append(tmp_img.name)
            pdf.image(tmp_img.name, x=x + 2.0, y=y + 7.5, w=23.0, h=23.0)
        except Exception:
            pdf.set_xy(x + 2.0, y + 15.0)
            pdf.set_font("Arial", 'B', 7)
            pdf.cell(23.0, 5, txt="[QR CODE]", border=1, align='C')

        # Texto principal (Código grande para leitura visual humana)
        pdf.set_xy(x + 26.5, y + 8.5)
        tam_fonte_cod = 10 if len(codigo_qr) <= 12 else (8.5 if len(codigo_qr) <= 16 else 7.5)
        pdf.set_font("Arial", 'B', tam_fonte_cod)
        pdf.multi_cell(box_w - 28.0, 4.8, txt=limpar_texto_pdf(codigo_qr))

        # Subtítulo / Descrição complementar
        if sub_lbl:
            pdf.set_xy(x + 26.5, y + 19.5)
            pdf.set_font("Arial", '', 6.8)
            pdf.multi_cell(box_w - 28.0, 3.5, txt=limpar_texto_pdf(sub_lbl[:58]))

        # Rodapé de instrução na base da etiqueta
        pdf.set_xy(x + 1, y + box_h - 4.5)
        pdf.set_font("Arial", 'I', 6)
        pdf.cell(box_w - 2, 3.5, txt=limpar_texto_pdf("Leitura Óptica - Modo Operador"), align='R')

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        pdf.output(tmp_pdf.name)
        caminho_final = tmp_pdf.name

    for arq in arquivos_temp:
        try:
            os.remove(arq)
        except Exception:
            pass

    return caminho_final
