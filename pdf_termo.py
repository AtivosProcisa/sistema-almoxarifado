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

def formatar_data_br(data_str):
    txt = str(data_str).strip()
    if not txt or txt.lower() in {'none', 'nan', 'null', 'nat'}:
        return datetime.now().strftime("%d/%m/%Y")
    if "/" in txt and len(txt) >= 8:
        return txt[:10]
    try:
        dt = datetime.strptime(txt[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return datetime.now().strftime("%d/%m/%Y")

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
    """
    Desenha o cabeçalho padrão PROCISA com 'FR-RH-P-026 Rev 07 / Jul 13'
    perfeitamente enquadrado dentro da primeira caixa (45mm e fonte 7.5pt).
    """
    # Linha 1 do quadro
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(45, 5.5, txt=limpar_texto_pdf("PROCISA"), border='LTR', align='C')
    pdf.cell(95, 5.5, txt=limpar_texto_pdf("TERMO DE RESPONSABILIDADE DE EQUIPAMENTOS"), border='LTR', align='C')
    pdf.cell(25, 5.5, txt=limpar_texto_pdf("DATA"), border=1, align='C')
    pdf.cell(25, 5.5, txt=limpar_texto_pdf("PÁG."), border=1, ln=True, align='C')
    
    # Linha 2 do quadro (Fonte 7.5pt para FR-RH-P-026 Rev 07 / Jul 13 caber com folga na caixa)
    pdf.set_font("Arial", 'B', 7.5)
    pdf.cell(45, 5.5, txt=limpar_texto_pdf("FR-RH-P-026 Rev 07 / Jul 13"), border='LBR', align='C')
    pdf.set_font("Arial", 'B', 9.5)
    pdf.cell(95, 5.5, txt=limpar_texto_pdf("REF."), border='LBR', align='C')
    pdf.cell(25, 5.5, txt=limpar_texto_pdf(data_atual), border=1, align='C')
    pdf.cell(25, 5.5, txt=limpar_texto_pdf(f"- {num_pag} -"), border=1, ln=True, align='C')
    pdf.ln(4)

def gerar_termo_pdf(patrimonio, responsavel, matricula, cpf, rg, projeto, unidade, info_ativo):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    _desenhar_cabecalho_procisa(pdf, data_atual, 1)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, txt=limpar_texto_pdf("TERMO DE RESPONSABILIDADE DE EQUIPAMENTOS"), ln=True, align='C')
    
    resp_limpo = str(responsavel).strip()
    mat_limpa = str(matricula).strip()
    cpf_limpo = str(cpf).strip()
    rg_limpo = str(rg).strip()
    unid_limpa = str(unidade).strip()
    proj_limpo = str(projeto).strip()

    # Proteção extra: se 'responsavel' for apenas números e 'matricula' estiver vazia, corrige a posição
    if resp_limpo.isdigit() and not mat_limpa:
        mat_limpa = resp_limpo

    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"Usuário: {resp_limpo}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"RG: {rg_limpo}      CPF/MF: {cpf_limpo}      Matrícula: {mat_limpa}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"Área: {unid_limpa}"), ln=True)
    pdf.cell(0, 6, txt=limpar_texto_pdf(f"Projeto: {proj_limpo}"), ln=True)
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
    
    num_pagina_atual = 2
    pdf.add_page()
    _desenhar_cabecalho_procisa(pdf, data_atual, num_pagina_atual)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(95, 8, txt=limpar_texto_pdf(f"ENTREGA: {data_atual}"), border=1)
    pdf.cell(95, 8, txt=limpar_texto_pdf("DEVOLUÇÃO: ___/___/___"), border=1, ln=True)
    pdf.ln(4)
    
    coordenador = unid_limpa
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
        
        cod_d365 = str(reg_ativo.get('codigo_d365') or reg_ativo.get('item') or '').strip()
        desc_d365 = str(reg_ativo.get('descricao_d365') or reg_ativo.get('equipamento') or '').strip()
        
        coordenador = str(reg_ativo.get('coordenacao', unid_limpa)).strip() or unid_limpa
        nf_procisa = str(reg_ativo.get('nf_procisa', '')).strip()

        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 6, txt=limpar_texto_pdf(f"{idx+1}. MARCA/MODELO: {marca_modelo_texto}"), ln=True)
        pdf.cell(0, 6, txt=limpar_texto_pdf(f"   NÚMERO DE SÉRIE: {serie}      NÚMERO DE ATIVO: {pat_id}"), ln=True)
        pdf.multi_cell(0, 6, txt=limpar_texto_pdf(f"   SITUAÇÃO / ACESSÓRIOS: {situacao_completa}"))
        if cod_d365 or desc_d365:
            pdf.cell(0, 6, txt=limpar_texto_pdf(f"   CÓD D365: {cod_d365} - {desc_d365}".strip(" -")), ln=True)
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
# GERADOR DE ETIQUETAS PADRÃO PROCISA (MODELO OFICIAL ALMOXARIFADO - 8 POR FOLHA A4)
# ==========================================
def gerar_etiquetas_qrcode_pdf(lista_etiquetas):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=False)

    cols = 2
    rows = 4
    por_pagina = cols * rows
    margin_x = 8.0
    margin_y = 10.0
    box_w = 94.0
    box_h = 66.0
    gap_x = 6.0
    gap_y = 4.0

    arquivos_temp = []

    for idx, item in enumerate(lista_etiquetas):
        if idx % por_pagina == 0:
            pdf.add_page()
            pdf.set_font("Arial", 'B', 8)
            pdf.set_text_color(80, 80, 80)
            pdf.set_xy(8, 4)
            pdf.cell(194, 4, txt=limpar_texto_pdf(f"PROCISA - ETIQUETAS PADRONIZADAS DE ALMOXARIFADO - Emitido em {datetime.now().strftime('%d/%m/%Y %H:%M')}"), align='C')

        pos_pag = idx % por_pagina
        c_idx = pos_pag % cols
        r_idx = pos_pag // cols

        x = margin_x + c_idx * (box_w + gap_x)
        y = margin_y + r_idx * (box_h + gap_y)

        item_d365 = str(item.get('item_d365') or item.get('codigo_d365') or '').strip().upper()
        ref_interna = str(item.get('ref_interna') or item.get('id_controle') or item.get('codigo') or '').strip().upper()

        tipo_legado = str(item.get('tipo', '')).strip()
        if not item_d365 and "D365:" in tipo_legado.upper():
            partes_t = tipo_legado.split("|")
            item_d365 = partes_t[0].upper().replace("D365:", "").strip()

        descricao = str(item.get('descricao') or item.get('subtitulo') or '').strip().upper()
        placa_licenca = str(item.get('placa_licenca', '')).strip().upper()
        local_end1 = str(item.get('local') or item.get('enderecamento_01') or '').strip().upper()
        desc_local_end2 = str(item.get('descri_local') or item.get('enderecamento_02') or '').strip().upper()

        if not local_end1 and "|" in tipo_legado:
            local_end1 = tipo_legado.split("|")[1].strip().upper()

        quantidade = str(item.get('quantidade', '1')).strip()
        data_criacao = formatar_data_br(item.get('data_criacao') or item.get('data_entrada') or '')
        obs_txt = str(item.get('obs', '0')).strip() or "0"
        lote_txt = str(item.get('lote') or '').strip().upper()

        payload_qr = str(item.get('codigo_qr', '')).strip()
        if not payload_qr:
            end_combinado = f"{local_end1}/{desc_local_end2}".strip("/")
            payload_qr = f"D365:{item_d365}|FER:{ref_interna}|LOC:{end_combinado}|DESC:{descricao[:25]}"

        legenda_abaixo_qr = f"D365:{item_d365}" if item_d365 else ref_interna
        if local_end1:
            legenda_abaixo_qr = f"{legenda_abaixo_qr} | {local_end1}"

        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.35)
        pdf.rect(x, y, box_w, box_h)

        h_logo = 11.0
        w_qr_col = 21.0
        w_esq = box_w - w_qr_col

        pdf.set_xy(x, y + 2.0)
        pdf.set_text_color(60, 62, 95)
        pdf.set_font("Arial", 'B', 15)
        pdf.cell(w_esq, 7.0, txt=limpar_texto_pdf("PROCISA"), align='C')
        pdf.set_text_color(0, 0, 0)

        h_bloco_sup = h_logo + 7.0 + 7.0
        pdf.rect(x + w_esq, y, w_qr_col, h_bloco_sup)
        if payload_qr:
            try:
                url_qr = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&margin=1&data={urllib.parse.quote(payload_qr)}"
                req = urllib.request.Request(url_qr, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    img_bytes = resp.read()
                tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                tmp_img.write(img_bytes)
                tmp_img.close()
                arquivos_temp.append(tmp_img.name)
                pdf.image(tmp_img.name, x=x + w_esq + 1.5, y=y + 1.2, w=18.0, h=18.0)
                pdf.set_xy(x + w_esq + 0.5, y + 19.8)
                pdf.set_font("Arial", 'B', 4.8)
                pdf.cell(w_qr_col - 1.0, 4.0, txt=limpar_texto_pdf(legenda_abaixo_qr[:18]), align='C')
            except Exception:
                pdf.set_xy(x + w_esq + 1.0, y + 10.0)
                pdf.set_font("Arial", 'B', 6)
                pdf.cell(w_qr_col - 2.0, 5.0, txt="[QR CODE]", align='C')

        y_d365 = y + h_logo
        h_row_sup = 7.0
        w_lbl_sup = 22.0
        w_val_sup = w_esq - w_lbl_sup

        pdf.set_xy(x, y_d365)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(w_lbl_sup, h_row_sup, txt=limpar_texto_pdf("ITEM D365"), border=1, align='L', fill=True)

        pdf.set_xy(x + w_lbl_sup, y_d365)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(w_val_sup, h_row_sup, txt=limpar_texto_pdf(item_d365[:20]), border=1, align='C', fill=True)

        y_ref = y_d365 + h_row_sup
        pdf.set_xy(x, y_ref)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 7.5)
        pdf.cell(w_lbl_sup, h_row_sup, txt=limpar_texto_pdf("REF. INTERNA"), border=1, align='L', fill=True)

        pdf.set_xy(x + w_lbl_sup, y_ref)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(w_val_sup, h_row_sup, txt=limpar_texto_pdf(ref_interna[:20]), border=1, align='C', fill=True)

        pdf.set_text_color(0, 0, 0)
        pdf.set_fill_color(255, 255, 255)

        y_desc = y_ref + h_row_sup
        h_desc = 9.0
        pdf.rect(x, y_desc, box_w, h_desc)
        tam_f_desc = 10.0 if len(descricao) <= 32 else (8.5 if len(descricao) <= 45 else 7.2)
        pdf.set_font("Arial", 'B', tam_f_desc)
        pdf.set_xy(x + 1.0, y_desc + 1.8)
        pdf.cell(box_w - 2.0, h_desc - 3.6, txt=limpar_texto_pdf(descricao[:55]), align='C')

        y_placa = y_desc + h_desc
        h_placa = 8.0
        w_lbl_placa = 22.0
        pdf.rect(x, y_placa, w_lbl_placa, h_placa)
        pdf.set_font("Arial", 'B', 7)
        pdf.set_xy(x, y_placa + 1.0)
        pdf.cell(w_lbl_placa, 3.0, txt=limpar_texto_pdf("PLACA DE"), align='C')
        pdf.set_xy(x, y_placa + 4.2)
        pdf.cell(w_lbl_placa, 3.0, txt=limpar_texto_pdf("LICENÇA"), align='C')

        pdf.set_xy(x + w_lbl_placa, y_placa)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(box_w - w_lbl_placa, h_placa, txt=limpar_texto_pdf(placa_licenca), border=1, align='C')

        y_loc = y_placa + h_placa
        h_loc = 8.5
        w_c1 = 16.0
        w_c2 = 28.0
        w_c3 = 18.0
        w_c4 = box_w - (w_c1 + w_c2 + w_c3)

        pdf.set_xy(x, y_loc)
        pdf.set_font("Arial", 'B', 8.5)
        pdf.cell(w_c1, h_loc, txt=limpar_texto_pdf("LOCAL"), border=1, align='L')

        pdf.set_xy(x + w_c1, y_loc)
        tam_f_e1 = 8.2 if len(local_end1) <= 12 else 6.8
        pdf.set_font("Arial", 'B', tam_f_e1)
        pdf.cell(w_c2, h_loc, txt=limpar_texto_pdf(local_end1[:18]), border=1, align='C')

        pdf.set_xy(x + w_c1 + w_c2, y_loc)
        pdf.set_font("Arial", 'B', 7.0)
        pdf.cell(w_c3, h_loc, txt=limpar_texto_pdf("Descri. Local"), border=1, align='C')

        pdf.set_xy(x + w_c1 + w_c2 + w_c3, y_loc)
        tam_f_e2 = 7.5 if len(desc_local_end2) <= 14 else 6.2
        pdf.set_font("Arial", 'B', tam_f_e2)
        pdf.cell(w_c4, h_loc, txt=limpar_texto_pdf(desc_local_end2[:22]), border=1, align='C')

        y_qd = y_loc + h_loc
        h_qd = 7.5
        pdf.set_xy(x, y_qd)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(w_c1, h_qd, txt=limpar_texto_pdf("QUANT."), border=1, align='L')

        pdf.set_xy(x + w_c1, y_qd)
        pdf.set_font("Arial", 'B', 9.5)
        pdf.cell(w_c2, h_qd, txt=limpar_texto_pdf(quantidade), border=1, align='C')

        pdf.set_xy(x + w_c1 + w_c2, y_qd)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(w_c3, h_qd, txt=limpar_texto_pdf("DATA"), border=1, align='C')

        pdf.set_xy(x + w_c1 + w_c2 + w_c3, y_qd)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(w_c4, h_qd, txt=limpar_texto_pdf(data_criacao), border=1, align='C')

        y_obs = y_qd + h_qd
        h_obs = box_h - (y_obs - y)
        pdf.set_xy(x, y_obs)
        pdf.set_font("Arial", 'B', 8.5)
        pdf.cell(w_c1, h_obs, txt=limpar_texto_pdf("OBS:"), border=1, align='L')

        pdf.set_xy(x + w_c1, y_obs)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(w_c2, h_obs, txt=limpar_texto_pdf(obs_txt[:14]), border=1, align='C')

        pdf.set_xy(x + w_c1 + w_c2, y_obs)
        pdf.set_font("Arial", 'B', 8.5)
        pdf.cell(w_c3, h_obs, txt=limpar_texto_pdf("LOTE"), border=1, align='C')

        pdf.set_xy(x + w_c1 + w_c2 + w_c3, y_obs)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(w_c4, h_obs, txt=limpar_texto_pdf(lote_txt[:16]), border=1, align='C')

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        pdf.output(tmp_pdf.name)
        caminho_final = tmp_pdf.name

    for arq in arquivos_temp:
        try:
            os.remove(arq)
        except Exception:
            pass

    return caminho_final
