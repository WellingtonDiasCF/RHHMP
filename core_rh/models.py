from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import Group

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
    nome = models.CharField(max_length=50, verbose_name="Nome da Equipe")
    local_trabalho = models.CharField("Local de Trabalho", max_length=100, default="Matriz", help_text="Ex: Brasília-DF")
    
    # Suporte a múltiplos gestores
    gestores = models.ManyToManyField(
        'Funcionario', 
        blank=True, 
        related_name='equipes_lideradas',
        verbose_name="Gestores Responsáveis"
    )

    class Meta:
        verbose_name = "Equipe"
        verbose_name_plural = "Equipes"

    def __str__(self):
        return self.nome


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

    class Meta:
        verbose_name = "Funcionário"
        verbose_name_plural = "Funcionários"

    def __str__(self):
        return f"{self.nome_completo} - {self.cargo.titulo}"

    def save(self, *args, **kwargs):
        # 1. Sincroniza o Nome do Usuário com o do Funcionário
        if self.nome_completo and self.usuario:
            partes = self.nome_completo.strip().split()
            if partes:
                self.usuario.first_name = partes[0].title()
                self.usuario.last_name = ' '.join(partes[1:]).title() if len(partes) > 1 else ''
        
        # 2. AUTOMATIZAÇÃO RH: Se for da equipe RH, ganha acesso Admin
        eh_rh = False
        if self.equipe and self.equipe.nome in ['RH', 'Recursos Humanos', 'Gestão de Pessoas']:
            eh_rh = True
        
        if eh_rh:
            self.usuario.is_staff = True
        else:
            # Só tira o acesso se não for superusuário (para não te bloquear)
            if not self.usuario.is_superuser:
                self.usuario.is_staff = False

        self.usuario.save() # Salva a permissão no User
        super().save(*args, **kwargs) # Salva o Funcionário


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

# Corrige representação do Usuário no Admin
def user_string_representation(self):
    if self.first_name:
        return f"{self.first_name} {self.last_name}".strip()
    return self.username

User.__str__ = user_string_representation
# Equipes que dão poderes de Admin
NOMES_EQUIPE_RH = ['RH', 'Recursos Humanos', 'Gestão de Pessoas']

def garantir_acesso_rh(funcionario):
    """Verifica se é RH e dá os poderes necessários"""
    eh_rh = False
    
    # 1. Verifica Principal
    if funcionario.equipe and funcionario.equipe.nome in NOMES_EQUIPE_RH:
        eh_rh = True
    
    # 2. Verifica Secundárias
    if not eh_rh and funcionario.outras_equipes.filter(nome__in=NOMES_EQUIPE_RH).exists():
        eh_rh = True
    
    # Aplica ou Remove poderes
    user = funcionario.usuario
    grupo_rh = Group.objects.filter(name='Gestores RH').first()
    
    if eh_rh:
        # Dá acesso ao Admin
        if not user.is_staff:
            user.is_staff = True
            user.save()
        # Adiciona ao Grupo de Permissões (para poder editar)
        if grupo_rh and not user.groups.filter(name='Gestores RH').exists():
            user.groups.add(grupo_rh)
    else:
        # Se saiu do RH, remove os poderes (se não for superusuário)
        if not user.is_superuser:
            if user.is_staff:
                user.is_staff = False
                user.save()
            if grupo_rh:
                user.groups.remove(grupo_rh)

@receiver(post_save, sender=Funcionario)
def signal_equipe_principal(sender, instance, created, **kwargs):
    """Roda toda vez que salva o funcionário (Equipe Principal)"""
    garantir_acesso_rh(instance)

@receiver(m2m_changed, sender=Funcionario.outras_equipes.through)
def signal_equipes_secundarias(sender, instance, action, **kwargs):
    """Roda toda vez que mexe nas equipes secundárias"""
    if action in ["post_add", "post_remove", "post_clear"]:
        garantir_acesso_rh(instance)

# --- Adicione isto ao core_rh/models.py ---

class Ferias(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, verbose_name="Funcionário")
    
    # --- PASSO 1: AGENDAMENTO ---
    periodo_aquisitivo = models.CharField("Período Aquisitivo", max_length=50, help_text="Ex: 2024/2025")
    abono_pecuniario = models.CharField("Abono Pecuniário", max_length=3, choices=[('Sim', 'Sim'), ('Não', 'Não')], default='Não')
    data_inicio = models.DateField("Início das Férias (Saída)")
    data_fim = models.DateField("Fim das Férias (Retorno)")

    # --- PASSO 2: ARQUIVOS GERADOS PELO RH (Para o funcionário assinar) ---
    arquivo_aviso = models.FileField("Aviso de Férias (Original)", upload_to='ferias/avisos_originais/', null=True, blank=True, help_text="Gere o arquivo no Passo 2 e anexe aqui.")
    arquivo_recibo = models.FileField("Recibo de Férias (Original)", upload_to='ferias/recibos_originais/', null=True, blank=True)

    # --- DEVOLUÇÃO DO FUNCIONÁRIO ---
    aviso_assinado = models.FileField("Aviso Assinado (Pelo Colaborador)", upload_to='ferias/avisos_assinados/', null=True, blank=True)
    recibo_assinado = models.FileField("Recibo Assinado (Pelo Colaborador)", upload_to='ferias/recibos_assinados/', null=True, blank=True)

    status = models.CharField(max_length=20, default='Pendente', choices=[
        ('Pendente', 'Pendente'),
        ('Enviado', 'Enviado ao RH'),
        ('Concluido', 'Concluído')
    ])

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Agendamento de Férias"
        verbose_name_plural = "Gestão de Férias"
        ordering = ['-data_inicio']

    def __str__(self):
        return f"{self.funcionario.nome_completo} - {self.periodo_aquisitivo}"
    

 # 1. PRIMEIRO: Defina a função aqui
def contracheque_upload_path(instance, filename):
    # Usa matrícula se existir, senão usa o ID do funcionário para evitar erro
    identificador = getattr(instance.funcionario, 'matricula', instance.funcionario.id)
    return f'contracheques/{instance.ano}/{instance.mes}/{identificador}_{filename}'

# 2. DEPOIS: Defina a classe que usa a função
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
    
    # Aqui a função é chamada, então ela já precisa ter sido lida pelo Python acima
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