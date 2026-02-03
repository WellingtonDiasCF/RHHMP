from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import Group
from django.db.models import Max

# ==========================================
# MÓDULO: RH (RECURSOS HUMANOS)
# ==========================================

# 1. Tabela de Cargos
class Cargo(models.Model):
    titulo = models.CharField("Nome do Cargo", max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.titulo

    class Meta:
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"
        ordering = ['titulo']


# 2. Tabela de Equipes
class Equipe(models.Model):
    nome = models.CharField(max_length=100)
    gestor = models.ForeignKey('Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='equipes_lideradas')
    local_trabalho = models.CharField(max_length=100, null=True, blank=True)
    gestores = models.ManyToManyField('Funcionario', related_name='equipes_gerenciadas', blank=True)
    
    oculta = models.BooleanField(default=False, verbose_name="Equipe Oculta (Apenas Secundária)", help_text="Se marcado, esta equipe não aparecerá na lista principal de seleção.")

    def __str__(self):
        return self.nome
    
    class Meta:
        verbose_name = "Equipe"
        verbose_name_plural = "Equipes"


# 3. Tabela de Funcionários
class Funcionario(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    nome_completo = models.CharField(max_length=100)
    email = models.EmailField(unique=True, verbose_name="E-mail")
    cpf = models.CharField(max_length=14, unique=True, verbose_name="CPF")
    matricula = models.CharField("Matrícula", max_length=20, null=True, blank=True)
    carteira_trabalho = models.CharField("Carteira de Trabalho (CTPS)", max_length=20, null=True, blank=True)
    serie_ctps = models.CharField("Série", max_length=10, null=True, blank=True)
    registro_geral = models.CharField("Nº Registro (Livro/Ficha)", max_length=20, null=True, blank=True)
    numero_contrato = models.CharField("Nº do Contrato", max_length=20, blank=True, null=True)
    
    primeiro_acesso = models.BooleanField(default=True, verbose_name="Exigir troca de senha?")

    cep = models.CharField("CEP", max_length=9, blank=True, null=True)
    endereco = models.CharField("Endereço", max_length=255, blank=True, null=True)
    bairro = models.CharField("Bairro", max_length=100, blank=True, null=True)
    cidade = models.CharField("Cidade", max_length=100, blank=True, null=True)
    estado = models.CharField("Estado (UF)", max_length=2, blank=True, null=True)
    local_trabalho_estado = models.CharField("Local de Trabalho (Estado)", max_length=100, blank=True, null=True)

    cargo = models.ForeignKey('Cargo', on_delete=models.PROTECT, verbose_name="Cargo")
    equipe = models.ForeignKey('Equipe', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Equipe Principal")
    
    outras_equipes = models.ManyToManyField(
        'Equipe', 
        blank=True, 
        related_name='funcionarios_secundarios',
        verbose_name="Outras Equipes (Secundárias)"
    )
    
    data_admissao = models.DateField("Data de Admissão", default=timezone.now)
    jornada_entrada = models.TimeField("Entrada Padrão", default='08:00')
    jornada_saida = models.TimeField("Saída Padrão", default='18:00')
    intervalo_padrao = models.CharField("Intervalo", max_length=50, default="13:00 às 14:12")
    base = models.CharField("Base de Atendimento", max_length=100, blank=True, null=True)
    tipo_veiculo = models.CharField("Tipo de Veículo", max_length=50, blank=True, null=True, help_text="Ex: Carro Próprio, Moto, etc.")
    banco = models.CharField("Banco", max_length=100, blank=True, null=True)
    agencia = models.CharField("Agência", max_length=20, blank=True, null=True)
    operacao = models.CharField("Operação", max_length=10, blank=True, null=True, help_text="Ex: 013 (Caixa)")
    conta = models.CharField("Conta", max_length=30, blank=True, null=True)
    tipo_chave_pix = models.CharField("Tipo Chave PIX", max_length=20, blank=True, null=True)
    chave_pix = models.CharField("Chave PIX", max_length=100, blank=True, null=True)
    valor_km = models.DecimalField("Valor do KM (R$)", max_digits=5, decimal_places=2, default=0.00, blank=True, null=True)
    
    class Meta:
        verbose_name = "Funcionário"
        verbose_name_plural = "Funcionários"

    def __str__(self):
        return f"{self.nome_completo} - {self.cargo.titulo}"

    def save(self, *args, **kwargs):
        if self.nome_completo and self.usuario:
            partes = self.nome_completo.strip().split()
            if partes:
                self.usuario.first_name = partes[0].title()
                self.usuario.last_name = ' '.join(partes[1:]).title() if len(partes) > 1 else ''
        
        eh_rh = False
        if self.equipe and self.equipe.nome in ['RH', 'Recursos Humanos', 'Gestão de Pessoas']:
            eh_rh = True
        
        if eh_rh:
            self.usuario.is_staff = True
        else:
            if not self.usuario.is_superuser:
                self.usuario.is_staff = False

        self.usuario.save()
        super().save(*args, **kwargs)


# 4. Tabela da Folha de Ponto
class RegistroPonto(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE)
    data = models.DateField()
    
    entrada_manha = models.TimeField("Entrada", null=True, blank=True)
    saida_almoco = models.TimeField("Saída Almoço", null=True, blank=True)
    volta_almoco = models.TimeField("Volta Almoço", null=True, blank=True)
    saida_tarde = models.TimeField("Saída", null=True, blank=True)
    
    extra_entrada = models.TimeField("Extra Entrada", null=True, blank=True)
    extra_saida = models.TimeField("Extra Saída", null=True, blank=True)
    
    observacao = models.CharField("Observação / Faltas", max_length=100, blank=True, null=True)
    arquivo_anexo = models.FileField(upload_to='ponto_assinado/', null=True, blank=True)
    
    assinado_funcionario = models.BooleanField(default=False)
    assinado_gestor = models.BooleanField(default=False)

    class Meta:
        unique_together = ('funcionario', 'data')
        verbose_name = "Registro de Ponto"
        verbose_name_plural = "Folhas de Ponto"
        ordering = ['data']

    def __str__(self):
        return f"{self.funcionario.nome_completo} - {self.data}"

def user_string_representation(self):
    if self.first_name:
        return f"{self.first_name} {self.last_name}".strip()
    return self.username

User.__str__ = user_string_representation

NOMES_EQUIPE_RH = ['RH', 'Recursos Humanos', 'Gestão de Pessoas']

def garantir_acesso_rh(funcionario):
    eh_rh = False
    if funcionario.equipe and funcionario.equipe.nome in NOMES_EQUIPE_RH:
        eh_rh = True
    if not eh_rh and funcionario.outras_equipes.filter(nome__in=NOMES_EQUIPE_RH).exists():
        eh_rh = True
    
    user = funcionario.usuario
    grupo_rh = Group.objects.filter(name='Gestores RH').first()
    
    if eh_rh:
        if not user.is_staff:
            user.is_staff = True
            user.save()
        if grupo_rh and not user.groups.filter(name='Gestores RH').exists():
            user.groups.add(grupo_rh)
    else:
        if not user.is_superuser:
            if user.is_staff:
                user.is_staff = False
                user.save()
            if grupo_rh:
                user.groups.remove(grupo_rh)

@receiver(post_save, sender=Funcionario)
def signal_equipe_principal(sender, instance, created, **kwargs):
    garantir_acesso_rh(instance)

@receiver(m2m_changed, sender=Funcionario.outras_equipes.through)
def signal_equipes_secundarias(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        garantir_acesso_rh(instance)

class Ferias(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, verbose_name="Funcionário")
    periodo_aquisitivo = models.CharField("Período Aquisitivo", max_length=50, help_text="Ex: 2024/2025")
    abono_pecuniario = models.CharField("Abono Pecuniário", max_length=3, choices=[('Sim', 'Sim'), ('Não', 'Não')], default='Não')
    data_inicio = models.DateField("Início das Férias (Saída)")
    data_fim = models.DateField("Fim das Férias (Retorno)")
    arquivo_aviso = models.FileField("Aviso de Férias (Original)", upload_to='ferias/avisos_originais/', null=True, blank=True)
    arquivo_recibo = models.FileField("Recibo de Férias (Original)", upload_to='ferias/recibos_originais/', null=True, blank=True)
    aviso_assinado = models.FileField("Aviso Assinado", upload_to='ferias/avisos_assinados/', null=True, blank=True)
    recibo_assinado = models.FileField("Recibo Assinado", upload_to='ferias/recibos_assinados/', null=True, blank=True)
    status = models.CharField(max_length=20, default='Pendente', choices=[
        ('Pendente', 'Pendente'), ('Enviado', 'Enviado ao RH'), ('Concluido', 'Concluído')
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Agendamento de Férias"
        verbose_name_plural = "Gestão de Férias"
        ordering = ['-data_inicio']

    def __str__(self):
        return f"{self.funcionario.nome_completo} - {self.periodo_aquisitivo}"

def contracheque_upload_path(instance, filename):
    identificador = getattr(instance.funcionario, 'matricula', instance.funcionario.id)
    return f'contracheques/{instance.ano}/{instance.mes}/{identificador}_{filename}'

class Contracheque(models.Model):
    MESES = [
        (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
        (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
        (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro'),
        (13, '13º Salário')
    ]
    funcionario = models.ForeignKey('Funcionario', on_delete=models.CASCADE, related_name='contracheques')
    mes = models.IntegerField(choices=MESES)
    ano = models.IntegerField()
    arquivo = models.FileField(upload_to=contracheque_upload_path)
    data_upload = models.DateTimeField(auto_now_add=True)
    data_ciencia = models.DateTimeField(null=True, blank=True, verbose_name="Data de Recebimento")
    ip_ciencia = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-ano', '-mes']
        unique_together = ['funcionario', 'mes', 'ano']

    def __str__(self):
        return f"{self.funcionario.nome_completo} - {self.get_mes_display()}/{self.ano}"

    @property
    def assinado(self):
        return self.data_ciencia is not None

class Atestado(models.Model):
    TIPO_CHOICES = [
        ('DIAS', 'Atestado Médico (Afastamento em Dias)'),
        ('HORAS', 'Declaração de Comparecimento (Horas)'),
    ]
    STATUS_CHOICES = [('Pendente', 'Pendente'), ('Aprovado', 'Aprovado'), ('Recusado', 'Recusado')]

    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='atestados')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='DIAS')
    data_inicio = models.DateField("Data do Atestado")
    motivo = models.CharField("Motivo / CID (Opcional)", max_length=100, blank=True, null=True)
    arquivo = models.FileField(upload_to='atestados/%Y/%m/')
    qtd_dias = models.IntegerField("Qtd. Dias", default=1, blank=True, null=True)
    hora_inicio = models.TimeField("Hora Início", blank=True, null=True)
    hora_fim = models.TimeField("Hora Fim", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pendente')
    observacao_rh = models.TextField("Obs. do RH", blank=True, null=True)
    data_envio = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.funcionario.nome_completo} - {self.get_tipo_display()}"

class ControleKM(models.Model):
    STATUS_CHOICES = [
        ('Pendente', 'Pendente'),
        ('Aprovado_Regional', 'Aprovado Regional'),
        ('Aprovado_Matriz', 'Aprovado Matriz'),
        ('Aprovado_Financeiro', 'Aprovado Financeiro'),
        ('Pago', 'Pago'),
        ('Rejeitado', 'Rejeitado'),
    ]
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE)
    data = models.DateField()
    total_km = models.DecimalField(max_digits=8, decimal_places=2)
    observacao = models.CharField("Observação", max_length=255, blank=True, null=True) 
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pendente')
    created_at = models.DateTimeField(auto_now_add=True)
    numero_chamado = models.CharField(max_length=50, null=True, blank=True, verbose_name="Nº Chamado")
    nota_recusa = models.TextField("Motivo da Recusa", blank=True, null=True)

    def __str__(self):
        return f"{self.funcionario.nome_completo} - {self.data}"

class DespesaDiversa(models.Model):
    TIPOS = [
        ('Estacionamento', 'Estacionamento'),
        ('Pedagio', 'Pedágio'),
        ('Jantar', 'Jantar'),
        ('Hospedagem', 'Hospedagem'),
        ('Outra', 'Outra'),
    ]
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE)
    data = models.DateField()
    numero_chamado = models.CharField(max_length=50, verbose_name="Nº Chamado")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    especificacao = models.CharField(max_length=255, blank=True, null=True)
    comprovante = models.FileField(upload_to='despesas_diversas/%Y/%m/')
    valor = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=50, default='Pendente')
    created_at = models.DateTimeField(auto_now_add=True)
    nota_recusa = models.TextField("Motivo da Recusa", blank=True, null=True)
    
    def __str__(self):
        return f"{self.tipo} - {self.numero_chamado}"

class TrechoKM(models.Model):
    controle = models.ForeignKey(ControleKM, related_name='trechos', on_delete=models.CASCADE)
    origem = models.TextField(verbose_name="Link ou Origem")
    destino = models.CharField(max_length=255)
    km = models.DecimalField(max_digits=6, decimal_places=2)
    nome_origem = models.CharField("Nome da Origem", max_length=150, blank=True, null=True)
    nome_destino = models.CharField("Nome do Destino", max_length=150, blank=True, null=True)
    
    def __str__(self):
        return f"{self.origem} -> {self.destino}"

# ==========================================
# MÓDULO: ALMOXARIFADO / ESTOQUE DE TI
# ==========================================

class GrupoPeca(models.Model):
    nome = models.CharField(max_length=50, unique=False) # Tire o unique global se tiver
    # Adicione este campo:
    empresa = models.CharField(max_length=20, choices=[('DIVIDATA', 'Dividata'), ('TORINO', 'Torino')], default='DIVIDATA')

    def __str__(self):
        return f"{self.nome} ({self.empresa})"
    
    class Meta:
        # Garante que não existam dois grupos com mesmo nome NA MESMA EMPRESA,
        # mas permite nomes iguais em empresas diferentes.
        unique_together = ('nome', 'empresa')

class Peca(models.Model):
    EMPRESA_CHOICES = [('DIVIDATA', 'DIVIDATA'), ('TORINO', 'TORINO')]

    empresa = models.CharField(max_length=20, choices=EMPRESA_CHOICES, default='DIVIDATA')
    
    # Código Linear Automático
    codigo_material = models.IntegerField(default=0)
    
    nome = models.CharField(max_length=200)
    grupo = models.ForeignKey(GrupoPeca, on_delete=models.SET_NULL, null=True, blank=True)
    ncm = models.CharField(max_length=20, blank=True, null=True, verbose_name="NCM")
    
    # Estoques
    estoque_atual = models.IntegerField(default=0)
    estoque_minimo = models.IntegerField(default=5, verbose_name="Mínimo")
    estoque_ideal = models.IntegerField(default=10, verbose_name="Ideal")
    
    # Valor Base
    preco_custo = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Valor Unitário Base")
    
    imagem = models.ImageField(upload_to='pecas/', blank=True, null=True)
    ativo = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        # Gera código linear se não existir
        if not self.codigo_material:
            max_cod = Peca.objects.aggregate(Max('codigo_material'))['codigo_material__max']
            self.codigo_material = (max_cod or 0) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"#{self.codigo_material} - {self.nome}"

class MovimentacaoPeca(models.Model):
    TIPO_CHOICES = [('E', 'Entrada'), ('S', 'Saída')]
    
    FILIAL_CHOICES = [
        ('CD BRASILIA', 'CD BRASÍLIA'), 
        ('CIAUS/BR', 'CIAUS/BR'),
        ('CIAUS/GO', 'CIAUS/GO'),
        ('CIAUS/MN', 'CIAUS/MN'),
        ('CIAUS/BH', 'CIAUS/BH'),
        ('CIAUS/RJ', 'CIAUS/RJ'),
        ('CIAUS/SP', 'CIAUS/SP'),
        ('CIAUS/PO', 'CIAUS/PO'),
        ('CIAUS/RE', 'CIAUS/RE'),
    ]
    
    peca = models.ForeignKey(Peca, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=1, choices=TIPO_CHOICES)
    
    # CAMPOS DA NOTA FISCAL
    tem_nota_fiscal = models.BooleanField(default=False, verbose_name="Gerar NF?")
    status_nfe = models.CharField(max_length=50, blank=True, null=True, default='Pendente')
    chave_nfe = models.CharField(max_length=100, blank=True, null=True)
    url_pdf_nfe = models.URLField(blank=True, null=True, verbose_name="Link da Danfe")
    mensagem_sefaz = models.TextField(blank=True, null=True)
    
    # Campos de Entrada
    nota_fiscal = models.CharField(max_length=50, blank=True, null=True)
    fornecedor = models.CharField(max_length=100, blank=True, null=True)
    
    # Campos de Saída
    numero_saida = models.IntegerField(blank=True, null=True, editable=False)
    tecnico_nome = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nome do Técnico")
    
    # Comuns
    filial = models.CharField(max_length=20, choices=FILIAL_CHOICES, default='CD BRASILIA')
    quantidade = models.IntegerField()
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    data = models.DateField(default=timezone.now)
    
    # Opcionais (null=True para evitar erros)
    numero_chamado = models.CharField(max_length=50, blank=True, null=True)
    observacao = models.TextField(blank=True, null=True)

    @property
    def valor_total(self):
        return self.quantidade * self.valor_unitario

    def save(self, *args, **kwargs):
        if self.tipo == 'S' and not self.numero_saida:
            max_saida = MovimentacaoPeca.objects.filter(tipo='S').aggregate(Max('numero_saida'))['numero_saida__max']
            self.numero_saida = (max_saida or 0) + 1

        if not self.pk:
            if self.tipo == 'E':
                self.peca.estoque_atual += self.quantidade
                self.peca.preco_custo = self.valor_unitario 
            elif self.tipo == 'S':
                self.peca.estoque_atual -= self.quantidade
            self.peca.save()
            
        super().save(*args, **kwargs)