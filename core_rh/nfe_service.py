import os
import random
import string
from django.conf import settings
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

def emitir_nfe_saida(movimentacao):
    """
    GERA UM PDF SIMULANDO UMA DANFE E SALVA NA PASTA MEDIA.
    """
    
    # 1. Gera dados aleatórios da Nota
    chave_fake = ''.join(random.choices(string.digits, k=44))
    protocolo_fake = ''.join(random.choices(string.digits, k=15))
    numero_nota = random.randint(1000, 9999)
    
    # 2. Define o caminho do arquivo
    nome_arquivo = f"NFE_{numero_nota}_{movimentacao.id}.pdf"
    
    # Garante que a pasta media/nfe existe
    pasta_destino = os.path.join(settings.MEDIA_ROOT, 'nfe')
    os.makedirs(pasta_destino, exist_ok=True)
    
    caminho_completo = os.path.join(pasta_destino, nome_arquivo)
    url_publica = f"{settings.MEDIA_URL}nfe/{nome_arquivo}"

    # 3. Desenha o PDF (Layout Simplificado de DANFE)
    c = canvas.Canvas(caminho_completo, pagesize=A4)
    width, height = A4
    
    # --- CABEÇALHO ---
    c.setLineWidth(1)
    c.rect(10*mm, 260*mm, 190*mm, 30*mm) # Quadro Topo
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(15*mm, 282*mm, "DANFE SIMPLIFICADA - SAÍDA")
    
    c.setFont("Helvetica", 10)
    c.drawString(15*mm, 277*mm, "DIVIDATA PROCESSAMENTO DE DADOS LTDA")
    c.drawString(15*mm, 272*mm, "Praça Governador Benedito Valadares, 84")
    c.drawString(15*mm, 267*mm, "CNPJ: 20.914.172/0001-88")
    
    # Chave de Acesso
    c.setFont("Helvetica-Bold", 9)
    c.drawString(110*mm, 282*mm, "CHAVE DE ACESSO")
    c.setFont("Courier", 10)
    c.drawString(110*mm, 277*mm, chave_fake)
    
    # Protocolo
    c.setFont("Helvetica-Bold", 9)
    c.drawString(110*mm, 268*mm, "PROTOCOLO DE AUTORIZAÇÃO")
    c.setFont("Helvetica", 10)
    c.drawString(110*mm, 263*mm, f"{protocolo_fake} - {movimentacao.data.strftime('%d/%m/%Y')}")

    # --- DESTINATÁRIO ---
    y_dest = 240*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(10*mm, y_dest + 5*mm, "DESTINATÁRIO / REMETENTE")
    c.rect(10*mm, y_dest - 15*mm, 190*mm, 18*mm)
    
    c.setFont("Helvetica", 10)
    c.drawString(15*mm, y_dest - 5*mm, f"NOME/RAZÃO SOCIAL: {movimentacao.tecnico_nome.upper() if movimentacao.tecnico_nome else 'CONSUMIDOR FINAL'}")
    c.drawString(150*mm, y_dest - 5*mm, f"DATA EMISSÃO: {movimentacao.data.strftime('%d/%m/%Y')}")
    c.drawString(15*mm, y_dest - 12*mm, f"DESTINO/FILIAL: {movimentacao.filial}")

    # --- DADOS DO PRODUTO ---
    y_prod = 210*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(10*mm, y_prod + 5*mm, "DADOS DO PRODUTO / SERVIÇO")
    
    # Cabeçalho da Tabela
    c.rect(10*mm, y_prod - 5*mm, 190*mm, 8*mm, fill=1) # Barra preta
    c.setFillColorRGB(1, 1, 1) # Texto branco
    c.setFont("Helvetica-Bold", 9)
    c.drawString(12*mm, y_prod - 1*mm, "CÓDIGO")
    c.drawString(40*mm, y_prod - 1*mm, "DESCRIÇÃO DO PRODUTO")
    c.drawString(130*mm, y_prod - 1*mm, "QTD")
    c.drawString(150*mm, y_prod - 1*mm, "V. UNIT")
    c.drawString(175*mm, y_prod - 1*mm, "V. TOTAL")
    
    c.setFillColorRGB(0, 0, 0) # Volta pra preto
    
    # Linha do Item
    y_item = y_prod - 12*mm
    c.setFont("Helvetica", 10)
    c.drawString(12*mm, y_item, str(movimentacao.peca.codigo_material))
    c.drawString(40*mm, y_item, movimentacao.peca.nome[:50]) # Corta nome longo
    c.drawString(132*mm, y_item, str(movimentacao.quantidade))
    c.drawString(150*mm, y_item, f"R$ {movimentacao.valor_unitario:.2f}")
    c.drawString(175*mm, y_item, f"R$ {movimentacao.valor_total:.2f}")
    
    c.line(10*mm, y_item - 2*mm, 200*mm, y_item - 2*mm)

    # --- TOTAL ---
    y_tot = 150*mm
    c.rect(10*mm, y_tot, 190*mm, 15*mm)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(130*mm, y_tot + 8*mm, "VALOR TOTAL DA NOTA:")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(175*mm, y_tot + 8*mm, f"R$ {movimentacao.valor_total:.2f}")

    # --- RODAPÉ ---
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(10*mm, 20*mm, "Este documento é uma representação gráfica simplificada de uma NF-e apenas para fins de teste no sistema.")
    c.drawString(10*mm, 15*mm, "Desenvolvido pelo time de TI.")

    c.save()

    return {
        'sucesso': True,
        'status': 'Emitida (Ambiente de Teste)',
        'chave': chave_fake,
        'protocolo': protocolo_fake,
        'mensagem': 'PDF Gerado com Sucesso',
        'url_pdf': url_publica, # AQUI ESTÁ O LINK REAL DO SEU COMPUTADOR
        'url_xml': '#'
    }